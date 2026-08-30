from __future__ import annotations

import asyncio
import json
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from ..adapters import build_adapter
from ..db import SessionLocal
from ..errors import ApiError
from ..orm import ApprovalDecision, Conversation, Message, MessageBlock, Model, Provider, User
from .tools import (
    MAX_TOOL_ITERATIONS,
    build_tool_definitions,
    execute_tool,
    load_mcp_tools_cached,
    needs_approval,
    tool_result_to_model_text,
    tool_risk,
)


@dataclass
class WorkContext:
    conversation: Conversation
    user: User
    model: Model
    provider: Provider
    task: str
    assistant_message_id: str
    steering: asyncio.Queue
    cancel: asyncio.Event
    search_configured: bool = False
    approval_policy: dict = field(default_factory=dict)
    tools_enabled: bool = True
    attachment_context: str = ""
    native_image_parts: list[dict] = field(default_factory=list)
    skills_text: str = ""


class AgentRuntimeProvider(ABC):
    """Pluggable agent harness. The native runtime is built-in; external
    harnesses (e.g. a DeepSeek Harness bridge) implement the same interface
    and register here. Nothing in the platform is hard-bound to one harness."""

    name = "abstract"

    @abstractmethod
    def run(self, ctx: WorkContext) -> AsyncIterator[tuple[str, dict]]: ...


_STEP_FOR_TOOL = {
    "web_search": "Searching",
    "run_python": "Running code",
}


class NativeAgentRuntime(AgentRuntimeProvider):
    name = "native"

    # System prompt used when no explicit plan is provided.
    system_prompt = (
        "You are an autonomous work agent. Break the task into steps, use tools when "
        "they help, verify results by executing code when possible, and finish with a "
        "clear Markdown summary. Report progress succinctly between tool calls."
    )

    async def run(self, ctx: WorkContext) -> AsyncIterator[tuple[str, dict]]:
        adapter = build_adapter(ctx.provider)
        try:
            async for ev in self._loop(ctx, adapter):
                yield ev
        finally:
            await adapter.aclose()

    async def _loop(self, ctx: WorkContext, adapter, plan: list[str] | None = None,
                    announce_planning: bool = True) -> AsyncIterator[tuple[str, dict]]:
        mcp_definitions: list[dict] = []
        mcp_dispatch: dict[str, dict] = {}
        async with SessionLocal() as db:
            try:
                mcp_definitions, mcp_dispatch = await load_mcp_tools_cached(db)
            except Exception:  # noqa: BLE001
                pass
        tools = (build_tool_definitions(ctx.search_configured) + mcp_definitions) if ctx.tools_enabled else []
        always_allowed: set[str] = set()

        system = self.system_prompt
        if ctx.skills_text:
            system = f"{system}\n\n# Installed skills\n{ctx.skills_text}"
        user_content = ctx.task
        if plan:
            plan_text = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(plan))
            user_content = f"Task: {ctx.task}\n\nPlan:\n{plan_text}"
        if ctx.attachment_context:
            user_content += f"\n\nAttached context:\n{ctx.attachment_context}"
        user_message_content: str | list[dict] = user_content
        if ctx.native_image_parts:
            user_message_content = [{"type": "text", "text": user_content}, *ctx.native_image_parts]
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_message_content},
        ]
        usage = {"input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0}

        if announce_planning:
            yield ("work.planning", {"task": ctx.task, "status": "Understanding the task"})
        if plan:
            yield ("work.plan", {"steps": plan})

        try:
            for iteration in range(1, MAX_TOOL_ITERATIONS + 1):
                if ctx.cancel.is_set():
                    yield ("work.cancelled", {})
                    return
                while not ctx.steering.empty():
                    try:
                        steer = ctx.steering.get_nowait()
                        messages.append({"role": "user", "content": f"[New instruction from user]: {steer}"})
                        yield ("work.steered", {"content": steer})
                    except asyncio.QueueEmpty:
                        break

                text_buf: list[str] = []
                reasoning_buf: list[str] = []
                pending_tool_calls = None
                for provider_attempt in range(3):
                    try:
                        gen = adapter.stream_chat(
                            messages,
                            model_id=ctx.model.model_id,
                            generation=ctx.model.generation_defaults or None,
                            extra_body=ctx.model.extra_body or None,
                            tools=tools or None,
                        )
                        async for ev in gen:
                            if ctx.cancel.is_set():
                                break
                            if ev["type"] == "reasoning.delta":
                                reasoning_buf.append(ev["delta"])
                                yield ("reasoning.delta", {"delta": ev["delta"]})
                            elif ev["type"] == "text.delta":
                                text_buf.append(ev["delta"])
                                yield ("block.delta", {"type": "markdown", "delta": ev["delta"]})
                            elif ev["type"] == "tool_calls":
                                pending_tool_calls = ev["tool_calls"]
                            elif ev["type"] == "done":
                                raw = ev.get("usage") or {}
                                usage["input_tokens"] += raw.get("prompt_tokens") or raw.get("input_tokens") or 0
                                usage["output_tokens"] += raw.get("completion_tokens") or raw.get("output_tokens") or 0
                                details = raw.get("completion_tokens_details") or {}
                                usage["reasoning_tokens"] += details.get("reasoning_tokens", 0) or 0
                        break
                    except Exception as exc:  # noqa: BLE001
                        retryable = bool(getattr(exc, "retryable", False)) or any(
                            marker in str(exc).lower() for marker in ("504", "timeout", "temporarily unavailable", "rate limit")
                        )
                        if provider_attempt >= 2 or not retryable or text_buf:
                            raise
                        reasoning_buf.clear()
                        pending_tool_calls = None
                        yield ("work.status", {"status": f"模型服务暂时超时，正在重试（{provider_attempt + 1}/2）"})
                        await asyncio.sleep(1.5 * (provider_attempt + 1))

                if ctx.cancel.is_set():
                    yield ("work.cancelled", {})
                    return

                if text_buf:
                    yield ("work.text", {"text": "".join(text_buf)})

                if not pending_tool_calls:
                    yield ("work.status", {"status": "Preparing the final response"})
                    yield ("work.usage", usage)
                    yield ("work.completed", {"iterations": iteration})
                    return

                messages.append({
                    "role": "assistant",
                    "content": "".join(text_buf) or None,
                    "tool_calls": [
                        {"id": tc["id"], "type": "function",
                         "function": {"name": tc["name"],
                                      "arguments": json.dumps(tc["arguments"], ensure_ascii=False)}}
                        for tc in pending_tool_calls
                    ],
                })

                for tc in pending_tool_calls:
                    if ctx.cancel.is_set():
                        yield ("work.cancelled", {})
                        return
                    risk = tool_risk(tc["name"], mcp_dispatch)
                    step = _STEP_FOR_TOOL.get(tc["name"], "Using tool")
                    yield ("work.step", {"step": step, "tool": tc["name"], "tool_call_id": tc["id"]})

                    if needs_approval(tc["name"], ctx.approval_policy, always_allowed, mcp_dispatch):
                        from .approvals import open_approval, wait_for_approval

                        approval_id = str(uuid.uuid4())
                        open_approval(approval_id)
                        yield ("work.waiting_approval", {
                            "approval_id": approval_id, "tool_call_id": tc["id"],
                            "name": tc["name"], "arguments": tc["arguments"], "risk": risk,
                        })
                        decision = await wait_for_approval(approval_id)
                        always_rule = decision == "allow_always"
                        base_decision = "allow" if always_rule else decision
                        async with SessionLocal() as appr_db:
                            appr_db.add(ApprovalDecision(
                                conversation_id=ctx.conversation.id, tool_name=tc["name"],
                                rule="always" if always_rule else "once", decision=base_decision,
                            ))
                            await appr_db.commit()
                        if base_decision != "allow":
                            yield ("tool.denied", {"tool_call_id": tc["id"], "name": tc["name"]})
                            messages.append({
                                "role": "tool", "tool_call_id": tc["id"],
                                "content": f"Tool use denied by the user ({decision}). Do not retry it.",
                            })
                            continue
                        if always_rule:
                            always_allowed.add(tc["name"])
                        yield ("work.approved", {"tool_call_id": tc["id"], "name": tc["name"]})

                    started = time.monotonic()
                    async with SessionLocal() as tool_db:
                        try:
                            result = await execute_tool(
                                tool_db, ctx.conversation, ctx.user, tc["name"], tc["arguments"],
                                tools, mcp_dispatch,
                            )
                        except ApiError as e:
                            result = {"ok": False, "error": e.message}
                    duration = int((time.monotonic() - started) * 1000)
                    files = result.get("files") or []
                    if files:
                        yield ("work.step", {"step": "Creating file", "tool": tc["name"],
                                             "tool_call_id": tc["id"], "files": files})
                    yield ("tool.completed", {
                        "tool_call_id": tc["id"], "name": tc["name"], "ok": result.get("ok"),
                        "exit_code": result.get("exit_code"), "duration_ms": duration,
                        "stdout": (result.get("stdout") or result.get("output") or "")[:2000],
                        "stderr": (result.get("stderr") or result.get("error") or "")[:1000],
                        "files": files or None,
                    })
                    messages.append({
                        "role": "tool", "tool_call_id": tc["id"],
                        "content": tool_result_to_model_text(result),
                    })

            # Iteration budget exhausted: force one tool-free completion so the
            # run always ends with a written summary.
            if not ctx.cancel.is_set():
                messages.append({
                    "role": "user",
                    "content": "Tool budget exhausted. Write the final summary now; no tools.",
                })
                gen = adapter.stream_chat(
                    messages,
                    model_id=ctx.model.model_id,
                    generation=ctx.model.generation_defaults or None,
                    extra_body=ctx.model.extra_body or None,
                    tools=None,
                )
                async for ev in gen:
                    if ctx.cancel.is_set():
                        break
                    if ev["type"] == "text.delta":
                        yield ("block.delta", {"type": "markdown", "delta": ev["delta"]})
                    elif ev["type"] == "done":
                        raw = ev.get("usage") or {}
                        usage["input_tokens"] += raw.get("prompt_tokens") or raw.get("input_tokens") or 0
                        usage["output_tokens"] += raw.get("completion_tokens") or raw.get("output_tokens") or 0
            yield ("work.usage", usage)
            yield ("work.completed", {"iterations": MAX_TOOL_ITERATIONS, "note": "iteration limit reached"})
        except asyncio.CancelledError:
            yield ("work.cancelled", {})
            raise
        except Exception as e:  # noqa: BLE001
            yield ("work.failed", {"error": str(e)})


class AdvancedAgentRuntime(NativeAgentRuntime):
    """Advanced agent engine: explicit plan-then-execute with step tracking.

    Decomposes the task into an ordered plan, then drives the agentic tool loop
    with the plan as guiding context. This is the default engine for Work mode.
    """

    name = "advanced"

    system_prompt = (
        "You are an advanced autonomous agent. You are given a plan of steps. "
        "Work through the plan in order, using tools where they help, verifying "
        "results by executing code when possible. Keep the plan in mind as you "
        "go, and finish with a clear Markdown summary that addresses every step."
    )

    async def run(self, ctx: WorkContext) -> AsyncIterator[tuple[str, dict]]:
        adapter = build_adapter(ctx.provider)
        try:
            # Emit immediately, before the non-streaming planning request.
            yield ("work.planning", {"task": ctx.task, "status": "Understanding the task and making a plan"})
            plan = await self._plan(ctx, adapter)
            async for ev in self._loop(ctx, adapter, plan=plan, announce_planning=False):
                yield ev
        finally:
            await adapter.aclose()

    async def _plan(self, ctx: WorkContext, adapter) -> list[str]:
        """Ask the model to decompose the task; fall back to a single step."""
        try:
            resp = await asyncio.wait_for(adapter.chat(
                [
                    {"role": "system",
                     "content": "Decompose the task into 2-6 ordered, concrete steps. Return "
                                "ONLY a JSON array of short step strings. No prose."},
                    {"role": "user", "content": ctx.task},
                ],
                model_id=ctx.model.model_id,
                generation={"max_tokens": 300, "temperature": 0.2},
            ), timeout=60)
            text = ((resp.get("choices") or [{}])[0].get("message") or {}).get("content", "")
            start = text.index("[")
            end = text.rindex("]") + 1
            steps = json.loads(text[start:end])
            steps = [str(s).strip() for s in steps if str(s).strip()][:6]
            if steps:
                return steps
        except Exception:  # noqa: BLE001
            pass
        return [ctx.task]


class DeepSeekHarnessCompatibleRuntime(AdvancedAgentRuntime):
    """Cordis/DSH-compatible composition surface for Aether Work.

    Installed DeepSeek Harness SKILL.md packages are mounted into the run and
    Aether/MCP tools retain the same streamed event contract.
    """

    name = "deepseek-harness"


_RUNTIMES: dict[str, AgentRuntimeProvider] = {
    "native": NativeAgentRuntime(),
    "advanced": AdvancedAgentRuntime(),
    "deepseek-harness": DeepSeekHarnessCompatibleRuntime(),
}

# Default engine for Work mode.
DEFAULT_WORK_RUNTIME = "deepseek-harness"


def register_runtime(runtime: AgentRuntimeProvider) -> None:
    _RUNTIMES[runtime.name] = runtime


def get_runtime(name: str | None) -> AgentRuntimeProvider:
    if not name:
        return _RUNTIMES[DEFAULT_WORK_RUNTIME]
    return _RUNTIMES.get(name) or _RUNTIMES[DEFAULT_WORK_RUNTIME]


def available_runtimes() -> list[str]:
    return sorted(_RUNTIMES.keys())
