import json

import httpx
import pytest

from aether_api.adapters.openai_compatible import OpenAICompatibleAdapter, _coerce_text


def test_payload_deduplicates_token_limits_and_allows_removing_defaults():
    adapter = OpenAICompatibleAdapter("http://example.test/v1")
    payload = adapter.build_payload(
        [{"role": "user", "content": "hi"}], stream=True, model_id="m",
        generation={"max_tokens": 20, "max_output_tokens": 30},
        extra_body={"stream_options": None},
    )
    assert payload["max_tokens"] == 20
    assert "max_output_tokens" not in payload
    assert "stream_options" not in payload


def test_coerce_multipart_content():
    assert _coerce_text([{"type": "text", "text": "你"}, {"content": "好"}]) == "你好"


@pytest.mark.asyncio
async def test_stream_accepts_ndjson_multipart_and_legacy_function_call():
    chunks = [
        {"choices": [{"delta": {"reasoning": [{"text": "想"}]}}]},
        {"choices": [{"delta": {"content": [{"type": "text", "text": "答"}]}}]},
        {"choices": [{"delta": {"function_call": {"name": "run", "arguments": {"x": 1}}}, "finish_reason": "tool_calls"}]},
    ]
    body = "\n".join(json.dumps(x, ensure_ascii=False) for x in chunks) + "\n"

    async def handler(request: httpx.Request):
        return httpx.Response(200, text=body, headers={"content-type": "application/x-ndjson"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = OpenAICompatibleAdapter("http://example.test/v1", client=client)
    events = [event async for event in adapter.stream_chat(
        [{"role": "user", "content": "hi"}], model_id="m")]
    assert events[0] == {"type": "reasoning.delta", "delta": "想"}
    assert events[1] == {"type": "text.delta", "delta": "答"}
    assert events[2]["tool_calls"][0]["name"] == "run"
    assert events[2]["tool_calls"][0]["arguments"] == {"x": 1}
    await adapter.aclose()
