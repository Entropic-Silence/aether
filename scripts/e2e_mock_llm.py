#!/usr/bin/env python3
"""Standalone mock OpenAI-compatible LLM for E2E tests.

Streams reasoning + text, supports CALL_TOOL (run_python) and SEARCH_TOOL
(web_search) markers, echoing a tool result back as the final answer.
"""
import argparse
import asyncio
import json

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI()
STATE = {"requests": []}


@app.get("/v1/models")
async def models():
    return {"data": [{"id": "mock-chat"}, {"id": "mock-tool"}]}


@app.get("/v1/_requests")
async def requests():
    return STATE["requests"]


@app.post("/v1/chat/completions")
async def chat(payload: dict):
    STATE["requests"].append(payload)
    messages = payload.get("messages", [])
    last_user_text = ""
    has_tool_result = any(m.get("role") == "tool" for m in messages)
    is_image_classifier = any(
        m.get("role") == "system" and "immediate intent" in str(m.get("content", ""))
        for m in messages
    )
    for m in reversed(messages):
        if m.get("role") == "user":
            c = m.get("content", "")
            if isinstance(c, list):
                last_user_text = " ".join(p.get("text", "") for p in c if p.get("type") == "text")
            else:
                last_user_text = str(c)
            break
    wants_tool = "CALL_TOOL" in last_user_text and not has_tool_result
    wants_search = "SEARCH_TOOL" in last_user_text and not has_tool_result
    tool_content = next((m.get("content", "") for m in messages if m.get("role") == "tool"), "")

    if is_image_classifier:
        # Deliberately slow so the UI regression test can prove the user's
        # message is visible before intent routing finishes.
        await asyncio.sleep(2)
        wants_image = "提示词" not in last_user_text and "prompt" not in last_user_text.lower()
        return JSONResponse({
            "choices": [{"message": {"role": "assistant", "content": json.dumps({"image_request": wants_image})}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 3},
        })

    if has_tool_result and "42" in str(tool_content):
        text = "The tool computed the answer: 42."
    elif has_tool_result:
        text = "The tool returned a result. Done."
    else:
        text = "This is a streamed mock reply to: " + last_user_text[:60]

    if payload.get("stream"):
        async def gen():
            if wants_tool:
                yield 'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_e2e","type":"function","function":{"name":"run_python","arguments":""}}]}}]}\n\n'
                yield 'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{\\"code\\": \\"print(6*7)\\"}"}}]}}]}\n\n'
                yield 'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}\n\n'
                yield "data: [DONE]\n\n"
                return
            if wants_search:
                yield 'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_s","type":"function","function":{"name":"web_search","arguments":""}}]}}]}\n\n'
                yield 'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{\\"query\\": \\"e2e query\\"}"}}]}}]}\n\n'
                yield 'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}\n\n'
                yield "data: [DONE]\n\n"
                return
            yield 'data: {"choices":[{"delta":{"reasoning_content":"Thinking briefly..."}}]}\n\n'
            yield f'data: {json.dumps({"choices": [{"delta": {"content": text}}]})}\n\n'
            yield 'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
            yield 'data: {"usage":{"prompt_tokens":5,"completion_tokens":10}}\n\n'
            yield "data: [DONE]\n\n"
        return StreamingResponse(gen(), media_type="text/event-stream")

    return JSONResponse({
        "choices": [{"message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 5},
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8300)
    args = parser.parse_args()
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
