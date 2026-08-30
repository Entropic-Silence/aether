from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import AsyncIterator

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from ..db import SessionLocal, get_db
from ..deps import get_current_user
from ..errors import NotFoundError, PermissionError_, ValidationError_
from ..orm import Conversation, File, Message, MessageBlock, Model, Plugin, Provider, User, UserSettings, WorkRun
from ..services.agent_runtime import DEFAULT_WORK_RUNTIME, WorkContext, available_runtimes, get_runtime
from ..services.tools import APPROVAL_POLICY_DEFAULT
from .chat import _approval_policy, _prepare_attachments, _resolve_model, _search_configured, _sse
from ..schemas import RunIn

router = APIRouter(tags=["work"])

RUNS: dict[str, dict] = {}


class WorkIn(BaseModel):
    task: str = Field(min_length=1, max_length=8000)
    runtime: str = DEFAULT_WORK_RUNTIME
    model_id: str | None = None
    file_ids: list[str] = []
    plugin_ids: list[str] = []


class SteerIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class WorkApprovalIn(BaseModel):
    approval_id: str
    decision: str  # allow | deny
    rule: str = "once"  # once | always


def _own_run_check(run: WorkRun, user: User) -> None:
    if run.user_id != user.id and user.role not in ("admin", "owner"):
        raise PermissionError_("Not your work run")


@router.get("/runtimes")
async def list_runtimes(_: User = Depends(get_current_user)):
    return {"runtimes": available_runtimes()}


@router.post("/conversations/{conversation_id}/work", status_code=201)
async def start_work(conversation_id: str, body: WorkIn,
                     db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    from ..services.features import ensure_feature

    await ensure_feature(db, "work", user)
    conv = await db.get(Conversation, conversation_id)
    if not conv or (conv.user_id != user.id and user.role not in ("admin", "owner")):
        raise NotFoundError("Conversation not found")
    if body.runtime not in available_runtimes():
        raise ValidationError_(f"Unknown agent runtime: {body.runtime}")

    model = await _resolve_model(db, RunIn(model_id=body.model_id), conv)
    provider = await db.get(Provider, model.provider_id)
    if not provider or not provider.enabled:
        raise NotFoundError("Provider for the selected model is not available")
    from .skills import global_skills_text
    installed_skills = await global_skills_text(db)
    from ..services.features import feature_enabled

    plugins_available = await feature_enabled(db, "plugins")
    settings = await db.get(UserSettings, user.id)
    allowed_plugin_ids = set(settings.enabled_plugins or []) if settings else set()
    requested_plugin_ids = (set(body.plugin_ids) & allowed_plugin_ids) if plugins_available else set()
    plugin_text = ""
    if requested_plugin_ids:
        rows = await db.execute(select(Plugin).where(Plugin.plugin_id.in_(requested_plugin_ids), Plugin.status == "valid"))
        enabled_plugins = rows.scalars().all()
        plugin_text = "\n\nEnabled DeepSeek Harness-compatible plugin manifests:\n" + "\n".join(
            f"- {plugin.name} ({plugin.plugin_id}): capabilities={','.join((plugin.manifest or {}).get('capabilities') or [])}; "
            f"description={(plugin.manifest or {}).get('description') or ''}"
            for plugin in enabled_plugins
        )
    parent = None
    if conv.current_leaf_id:
        cand = await db.get(Message, conv.current_leaf_id)
        if cand and cand.conversation_id == conv.id:
            parent = cand

    user_msg = Message(conversation_id=conv.id, parent_id=parent.id if parent else None, role="user")
    db.add(user_msg)
    await db.flush()
    db.add(MessageBlock(message_id=user_msg.id, seq=0, type="text", data={"text": body.task, "work_task": True}))
    attachment_context, native_image_parts = await _prepare_attachments(
        db,
        RunIn(content=body.task, model_id=body.model_id, file_ids=body.file_ids),
        user,
        model,
        user_msg.id,
    )

    assistant_msg = Message(conversation_id=conv.id, parent_id=user_msg.id, role="assistant",
                            model_id=model.id, status="working")
    db.add(assistant_msg)
    await db.flush()

    run_row = WorkRun(
        conversation_id=conv.id, user_id=user.id, runtime=body.runtime,
        assistant_message_id=assistant_msg.id, task=body.task, status="working", timeline=[],
    )
    db.add(run_row)
    conv.current_leaf_id = assistant_msg.id
    conv.mode = "work"
    await db.commit()
    await db.refresh(run_row)

    RUNS[run_row.id] = {
        "events": [],
        "steering": asyncio.Queue(),
        "cancel": asyncio.Event(),
        "pending_approval_id": None,
        "done": False,
    }

    task = asyncio.create_task(_execute_work(
        run_id=run_row.id,
        conversation_id=conv.id,
        user_id=user.id,
        assistant_message_id=assistant_msg.id,
        task=body.task,
        runtime_name=body.runtime,
        model_id=model.id,
        tools_enabled=model.effective_caps().get("tool_calling") is True,
        attachment_context=attachment_context,
        native_image_parts=native_image_parts,
        skills_text=installed_skills + plugin_text,
    ))
    RUNS[run_row.id]["task"] = task

    return {"run_id": run_row.id, "assistant_message_id": assistant_msg.id, "status": "working"}


async def _execute_work(run_id: str, conversation_id: str, user_id: str,
                        assistant_message_id: str, task: str, runtime_name: str, model_id: str,
                        tools_enabled: bool, attachment_context: str,
                        native_image_parts: list[dict], skills_text: str = "") -> None:
    handle = RUNS.get(run_id)
    if handle is None:
        return
    reasoning_parts: list[str] = []
    text_parts: list[str] = []
    timeline: list[dict] = []
    created_files: list[dict] = []
    final_status = "completed"
    error_text = ""
    usage: dict = {"input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "source": "provider_reported"}
    started = asyncio.get_running_loop().time()

    try:
        async with SessionLocal() as db:
            conv = await db.get(Conversation, conversation_id)
            user = await db.get(User, user_id)
            model = await db.get(Model, model_id)
            provider = await db.get(Provider, model.provider_id)
            from ..services.features import feature_enabled

            search_configured = await feature_enabled(db, "web_search") and await _search_configured(db)
            policy = await _approval_policy(db)

        ctx = WorkContext(
            conversation=conv, user=user, model=model, provider=provider, task=task,
            assistant_message_id=assistant_message_id,
            steering=handle["steering"], cancel=handle["cancel"],
            search_configured=search_configured, approval_policy=policy,
            tools_enabled=tools_enabled,
            attachment_context=attachment_context,
            native_image_parts=native_image_parts,
            skills_text=skills_text,
        )
        runtime = get_runtime(runtime_name)
        async for event, data in runtime.run(ctx):
            stamp = datetime.now(timezone.utc).isoformat()
            record = {"event": event, "data": data, "at": stamp}
            handle["events"].append(record)
            if event == "reasoning.delta":
                reasoning_parts.append(data.get("delta", ""))
            elif event == "block.delta":
                text_parts.append(data.get("delta", ""))
            elif event == "work.usage":
                usage.update(data or {})
            elif event in ("work.planning", "work.plan", "work.status", "work.step", "work.waiting_approval", "work.steered",
                           "work.approved", "tool.denied", "tool.completed"):
                timeline.append({"event": event, **(data or {}), "at": stamp})
                if event == "work.waiting_approval":
                    handle["pending_approval_id"] = data.get("approval_id")
                    await _set_run_status(run_id, "waiting_approval")
                elif event == "work.approved":
                    handle["pending_approval_id"] = None
                    await _set_run_status(run_id, "working")
                elif event == "tool.completed":
                    for item in data.get("files") or []:
                        if item.get("file_id") and not any(existing.get("file_id") == item.get("file_id") for existing in created_files):
                            created_files.append(dict(item))
            elif event == "work.completed":
                final_status = "completed"
            elif event == "work.failed":
                final_status = "failed"
                error_text = str(data.get("error", ""))
            elif event == "work.cancelled":
                final_status = "cancelled"
    except asyncio.CancelledError:
        final_status = "cancelled"
        handle["events"].append({"event": "work.cancelled", "data": {},
                                 "at": datetime.now(timezone.utc).isoformat()})
    except Exception as e:  # noqa: BLE001
        final_status = "failed"
        error_text = str(e)
        handle["events"].append({"event": "work.failed", "data": {"error": error_text},
                                 "at": datetime.now(timezone.utc).isoformat()})

    await _finalize_work(run_id, conversation_id, assistant_message_id,
                         "".join(reasoning_parts), "".join(text_parts), timeline,
                         final_status, error_text, {**usage, "duration_ms": int((asyncio.get_running_loop().time() - started) * 1000)},
                         created_files)
    handle["done"] = True


async def _set_run_status(run_id: str, status: str) -> None:
    async with SessionLocal() as db:
        run = await db.get(WorkRun, run_id)
        if run:
            run.status = status
            await db.commit()


async def _finalize_work(run_id: str, conversation_id: str, assistant_message_id: str,
                         reasoning_text: str, text: str, timeline: list[dict],
                         status: str, error_text: str, usage: dict,
                         created_files: list[dict] | None = None) -> None:
    async with SessionLocal() as db:
        run = await db.get(WorkRun, run_id)
        if run:
            run.status = status
            run.timeline = timeline
            run.error = error_text
            run.finished_at = datetime.now(timezone.utc)
        message = await db.get(Message, assistant_message_id)
        if message:
            seq = 0
            if reasoning_text:
                db.add(MessageBlock(message_id=message.id, seq=seq, type="reasoning", data={"text": reasoning_text}))
                seq += 1
            if timeline:
                db.add(MessageBlock(message_id=message.id, seq=seq, type="progress", data={"timeline": timeline}))
                seq += 1
            if text:
                db.add(MessageBlock(message_id=message.id, seq=seq, type="markdown", data={"text": text}))
                seq += 1
            for item in created_files or []:
                file = await db.get(File, str(item.get("file_id")))
                if not file:
                    continue
                db.add(MessageBlock(message_id=message.id, seq=seq, type="file", data={
                    "file_id": file.id, "name": file.name, "mime": file.mime,
                    "kind": file.kind, "size": file.size, "generated": True,
                    "url": f"/api/v1/files/{file.id}/download",
                }))
                seq += 1
            if error_text:
                db.add(MessageBlock(message_id=message.id, seq=seq, type="error",
                                    data={"code": "WORK_FAILED", "message": error_text, "retryable": False}))
            message.status = "completed" if status == "completed" else status
            message.usage = usage
            if error_text:
                message.error = {"code": "WORK_FAILED", "message": error_text, "retryable": False}
        conv = await db.get(Conversation, conversation_id)
        if conv:
            conv.current_leaf_id = assistant_message_id
        await db.commit()


@router.get("/work/runs/{run_id}/events")
async def work_events(run_id: str, request: Request,
                      db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    run = await db.get(WorkRun, run_id)
    if not run:
        raise NotFoundError("Work run not found")
    _own_run_check(run, user)

    async def stream() -> AsyncIterator[dict]:
        handle = RUNS.get(run_id)
        if handle is None:
            # Already finished and evicted: replay persisted timeline.
            for step in run.timeline or []:
                yield _sse(step.get("event", "work.step"), step)
            yield _sse("work.done", {"status": run.status})
            return
        idx = 0
        while True:
            if await request.is_disconnected():
                return
            events = handle["events"]
            while idx < len(events):
                rec = events[idx]
                yield _sse(rec["event"], rec["data"])
                idx += 1
            if handle["done"]:
                yield _sse("work.done", {"status": run.status})
                return
            await asyncio.sleep(0.3)

    return EventSourceResponse(stream())


@router.post("/work/runs/{run_id}/steer")
async def steer_work(run_id: str, body: SteerIn,
                     db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    run = await db.get(WorkRun, run_id)
    if not run:
        raise NotFoundError("Work run not found")
    _own_run_check(run, user)
    handle = RUNS.get(run_id)
    if not handle or handle["done"]:
        raise ValidationError_("Work run is not active")
    handle["steering"].put_nowait(body.content)
    return {"ok": True}


@router.post("/work/runs/{run_id}/cancel")
async def cancel_work(run_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    run = await db.get(WorkRun, run_id)
    if not run:
        raise NotFoundError("Work run not found")
    _own_run_check(run, user)
    handle = RUNS.get(run_id)
    if handle:
        handle["cancel"].set()
        approval_id = handle.get("pending_approval_id")
        if approval_id:
            from ..services.approvals import resolve_approval
            resolve_approval(approval_id, "deny")
        task = handle.get("task")
        if task and not task.done():
            task.cancel()
        run.status = "cancelled"
        await db.commit()
    return {"ok": True}


@router.post("/work/runs/{run_id}/approvals")
async def approve_work_tool(run_id: str, body: WorkApprovalIn,
                            db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    from ..services.approvals import resolve_approval

    run = await db.get(WorkRun, run_id)
    if not run:
        raise NotFoundError("Work run not found")
    _own_run_check(run, user)
    if body.decision not in ("allow", "deny"):
        raise ValidationError_("decision must be allow or deny")
    decision = "allow_always" if body.decision == "allow" and body.rule == "always" else body.decision
    resolved = resolve_approval(body.approval_id, decision)
    return {"ok": resolved}


@router.get("/conversations/{conversation_id}/work-runs")
async def list_work_runs(conversation_id: str,
                         db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    conv = await db.get(Conversation, conversation_id)
    if not conv or (conv.user_id != user.id and user.role not in ("admin", "owner")):
        raise NotFoundError("Conversation not found")
    rows = await db.execute(
        select(WorkRun).where(WorkRun.conversation_id == conversation_id).order_by(WorkRun.started_at.desc())
    )
    return [
        {"id": r.id, "task": r.task, "status": r.status, "runtime": r.runtime,
         "assistant_message_id": r.assistant_message_id,
         "started_at": r.started_at, "finished_at": r.finished_at, "error": r.error}
        for r in rows.scalars().all()
    ]
