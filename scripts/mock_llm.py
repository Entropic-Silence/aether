#!/usr/bin/env python3
"""Mock OpenAI-compatible server for local development and smoke testing.

Use until a real inference server (vLLM/SGLang on the DCU) is available.
Run: python3 scripts/mock_llm.py [--port 8200]
"""
import argparse
import hashlib
import json
import math

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI(title="Mock LLM")

EMBED_DIM = 256


def _hash_embed(text: str) -> list[float]:
    """Deterministic bag-of-tokens hash embedding (for dev/tests only)."""
    vec = [0.0] * EMBED_DIM
    for token in text.lower().split():
        digest = hashlib.md5(token.encode()).digest()
        for i in range(0, 16, 2):
            idx = digest[i] % EMBED_DIM
            vec[idx] += (digest[i + 1] / 255.0) - 0.5
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _message_text(message: dict) -> str:
    content = message.get("content", "")
    if isinstance(content, list):
        return " ".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text")
    return str(content)


def _message_images(message: dict) -> int:
    content = message.get("content", "")
    if isinstance(content, list):
        return sum(1 for p in content if isinstance(p, dict) and p.get("type") == "image_url")
    return 0


@app.get("/v1/models")
async def models():
    return {"data": [{"id": "mock-chat-7b"}, {"id": "mock-reasoner-7b"},
                     {"id": "mock-vision-7b"}, {"id": "mock-embed-1"}]}


@app.post("/v1/embeddings")
async def embeddings(payload: dict):
    inputs = payload.get("input", [])
    if isinstance(inputs, str):
        inputs = [inputs]
    data = [{"index": i, "embedding": _hash_embed(t)} for i, t in enumerate(inputs)]
    return {"data": data, "model": payload.get("model", ""), "usage": {"prompt_tokens": 0, "total_tokens": 0}}


@app.post("/v1/chat/completions")
async def chat(payload: dict):
    last_user = ""
    image_count = 0
    for m in reversed(payload.get("messages", [])):
        if m.get("role") == "user":
            last_user = _message_text(m)
            image_count = _message_images(m)
            break
    model = payload.get("model", "")

    if image_count and "vision" in model:
        reply = (
            "Mock vision description: the image shows a simple test pattern with "
            "clear shapes and a short caption, suitable for development."
        )
    else:
        reply = (
            f"This is the **mock LLM** (`{model}`) echoing back for development.\n\n"
            f"You said: {last_user}\n\n"
            "| Feature | Status |\n|---|---|\n| streaming | ok |\n| markdown | ok |"
        )
    if payload.get("stream"):
        async def gen():
            if "reasoner" in model:
                yield 'data: {"choices":[{"delta":{"reasoning_content":"Let me think about this request step by step..."}}]}\n\n'
            words = reply.split(" ")
            for i in range(0, len(words), 3):
                chunk = " ".join(words[i:i + 3]) + " "
                yield f'data: {json.dumps({"choices": [{"delta": {"content": chunk}}]})}\n\n'
            yield f'data: {json.dumps({"choices": [{"delta": {}, "finish_reason": "stop"}]})}\n\n'
            yield f'data: {json.dumps({"usage": {"prompt_tokens": 10, "completion_tokens": len(words)}})}\n\n'
            yield "data: [DONE]\n\n"
        return StreamingResponse(gen(), media_type="text/event-stream")
    return JSONResponse({
        "choices": [{"message": {"role": "assistant", "content": reply}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": len(reply.split(" "))},
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8200)
    args = parser.parse_args()
    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="warning")
