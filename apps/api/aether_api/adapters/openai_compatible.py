from __future__ import annotations

import json
import time
from typing import Any, AsyncIterator

import httpx

from ..errors import (
    ContextOverflowError,
    ModelNotFoundError,
    ModelOverloadedError,
    ProviderError,
    RateLimitError,
)

REASONING_KEYS = ("reasoning_content", "reasoning", "thinking", "analysis")
RETRIABLE_STATUS = {408, 429, 500, 502, 503, 504, 529}


def _coerce_text(value: Any) -> str:
    """Normalize string and multipart content used by compatible gateways."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content") or item.get("value")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    if isinstance(value, dict):
        text = value.get("text") or value.get("content") or value.get("value")
        return text if isinstance(text, str) else ""
    return ""


def _join_url(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + "/" + path.lstrip("/")


def _map_http_error(status_code: int, text: str) -> ProviderError:
    snippet = text[:500]
    if status_code in (401, 403):
        return ProviderError(f"Provider authentication failed ({status_code})", detail=snippet)
    if status_code == 404:
        return ModelNotFoundError(f"Model or endpoint not found at provider ({status_code})", detail=snippet)
    if status_code == 429:
        return RateLimitError("Provider rate limit exceeded", detail=snippet)
    if status_code in (529, 503):
        return ModelOverloadedError("Provider is overloaded", detail=snippet)
    if status_code == 400 and "context" in snippet.lower():
        return ContextOverflowError("Context length exceeded", detail=snippet)
    return ProviderError(f"Provider error ({status_code})", detail=snippet)


class OpenAICompatibleAdapter:
    """Baseline wire protocol. Speaks /chat/completions to any compatible server."""

    kind = "openai_compatible"

    def __init__(self, base_url: str, api_key: str = "", headers: dict | None = None,
                 timeout_ms: int = 120000, proxy: str = "", client: httpx.AsyncClient | None = None):
        self.base_url = base_url
        self.api_key = api_key
        self.extra_headers = headers or {}
        self.timeout_ms = timeout_ms
        self.proxy = proxy or None
        self._client = client

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json", **self.extra_headers}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    async def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout((self.timeout_ms or 120000) / 1000, connect=10),
                proxy=self.proxy,
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def build_payload(self, messages: list[dict], *, stream: bool, model_id: str,
                      generation: dict | None = None, extra_body: dict | None = None,
                      reasoning_effort: str | None = None, tools: list[dict] | None = None) -> dict:
        payload: dict[str, Any] = {"model": model_id, "messages": messages, "stream": stream}
        if stream:
            payload["stream_options"] = {"include_usage": True}
        gen = generation or {}
        passthrough = {
            "temperature", "top_p", "top_k", "min_p", "max_tokens", "max_output_tokens",
            "repetition_penalty", "frequency_penalty", "presence_penalty", "seed", "stop",
            "logprobs",
        }
        for k, v in gen.items():
            if k in passthrough and v is not None:
                payload[k] = v
        # Several gateways reject requests containing both token-limit spellings.
        if "max_tokens" in payload and "max_output_tokens" in payload:
            payload.pop("max_output_tokens", None)
        if reasoning_effort and reasoning_effort != "auto":
            payload["reasoning_effort"] = reasoning_effort
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        if extra_body:
            # A null override intentionally removes an adapter default. This is
            # useful for gateways that reject stream_options or tool_choice.
            for key, value in extra_body.items():
                if value is None:
                    payload.pop(key, None)
                else:
                    payload[key] = value
        return payload

    async def chat(self, messages: list[dict], *, model_id: str, generation: dict | None = None,
                   extra_body: dict | None = None, reasoning_effort: str | None = None) -> dict:
        client = await self.client()
        payload = self.build_payload(
            messages, stream=False, model_id=model_id, generation=generation,
            extra_body=extra_body, reasoning_effort=reasoning_effort,
        )
        resp = await client.post(_join_url(self.base_url, "/chat/completions"),
                                 headers=self._headers(), json=payload)
        if resp.status_code != 200:
            raise _map_http_error(resp.status_code, resp.text)
        return resp.json()

    async def stream_chat(self, messages: list[dict], *, model_id: str,
                          generation: dict | None = None, extra_body: dict | None = None,
                          reasoning_effort: str | None = None,
                          tools: list[dict] | None = None) -> AsyncIterator[dict]:
        """Yield normalized events: reasoning.delta / text.delta / tool_calls / done."""
        client = await self.client()
        payload = self.build_payload(
            messages, stream=True, model_id=model_id, generation=generation,
            extra_body=extra_body, reasoning_effort=reasoning_effort, tools=tools,
        )
        started = time.monotonic()
        first_token_ms = None
        # tool_calls arrive fragmented across chunks; accumulate by index
        tool_acc: dict[int, dict] = {}
        async with client.stream(
            "POST", _join_url(self.base_url, "/chat/completions"),
            headers=self._headers(), json=payload,
        ) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                raise _map_http_error(resp.status_code, body.decode(errors="replace"))
            finish_reason = None
            usage = None
            buffer = ""
            async for chunk in resp.aiter_text():
                buffer += chunk
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line or line.startswith(("event:", ":")):
                        continue
                    data = line[len("data:"):].strip() if line.startswith("data:") else line
                    if not data.startswith("{") and data != "[DONE]":
                        continue
                    if data == "[DONE]":
                        continue
                    try:
                        obj = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("usage"):
                        usage = obj["usage"]
                    choices = obj.get("choices") or []
                    if not choices:
                        continue
                    choice = choices[0]
                    delta = choice.get("delta") or choice.get("message") or {}
                    reasoning_text = None
                    for key in REASONING_KEYS:
                        if delta.get(key):
                            reasoning_text = _coerce_text(delta[key])
                            break
                    if reasoning_text:
                        if first_token_ms is None:
                            first_token_ms = int((time.monotonic() - started) * 1000)
                        yield {"type": "reasoning.delta", "delta": reasoning_text}
                    content = _coerce_text(delta.get("content"))
                    if content:
                        if first_token_ms is None:
                            first_token_ms = int((time.monotonic() - started) * 1000)
                        yield {"type": "text.delta", "delta": content}
                    chunk_tool_calls = list(delta.get("tool_calls") or [])
                    if delta.get("function_call"):
                        chunk_tool_calls.append({"index": 0, "function": delta["function_call"]})
                    for tc in chunk_tool_calls:
                        idx = tc.get("index", 0)
                        slot = tool_acc.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                        if tc.get("id"):
                            slot["id"] = tc["id"]
                        fn = tc.get("function") or {}
                        if fn.get("name"):
                            slot["name"] = fn["name"]
                        if fn.get("arguments"):
                            fragment = fn["arguments"]
                            slot["arguments"] += fragment if isinstance(fragment, str) else json.dumps(fragment)
                    if choice.get("finish_reason"):
                        finish_reason = choice["finish_reason"]
        if tool_acc:
            tool_calls = []
            for idx in sorted(tool_acc):
                slot = tool_acc[idx]
                try:
                    args = json.loads(slot["arguments"]) if slot["arguments"] else {}
                except json.JSONDecodeError:
                    args = {"_raw": slot["arguments"]}
                tool_calls.append({
                    "id": slot["id"] or f"call_{idx}",
                    "name": slot["name"],
                    "arguments": args,
                })
            yield {"type": "tool_calls", "tool_calls": tool_calls}
        yield {
            "type": "done",
            "finish_reason": finish_reason or ("tool_calls" if tool_acc else "stop"),
            "usage": usage,
            "ttft_ms": first_token_ms,
            "latency_ms": int((time.monotonic() - started) * 1000),
        }

    async def list_models(self) -> list[str]:
        client = await self.client()
        resp = await client.get(_join_url(self.base_url, "/models"), headers=self._headers())
        if resp.status_code != 200:
            raise _map_http_error(resp.status_code, resp.text)
        data = resp.json()
        return [m.get("id", "") for m in data.get("data", []) if m.get("id")]

    async def embeddings(self, texts: list[str], *, model_id: str) -> list[list[float]]:
        client = await self.client()
        resp = await client.post(
            _join_url(self.base_url, "/embeddings"),
            headers=self._headers(),
            json={"model": model_id, "input": texts},
        )
        if resp.status_code != 200:
            raise _map_http_error(resp.status_code, resp.text)
        data = resp.json().get("data", [])
        data.sort(key=lambda d: d.get("index", 0))
        return [d.get("embedding", []) for d in data]
