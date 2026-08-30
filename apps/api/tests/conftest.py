import os
import json
import socket
import sys
import threading
import time

# Point the app at a SQLite test database BEFORE importing aether_api.db.
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///" + os.path.join(os.path.dirname(__file__), "test.db")
os.environ["SECRET_KEY"] = "test-secret-key-that-is-long-enough-32b"
os.environ["ALLOW_REGISTRATION"] = "true"
os.environ["STORAGE_ROOT"] = os.path.join(os.path.dirname(__file__), "storage")
os.environ["SANDBOX_ROOT"] = os.path.join(os.path.dirname(__file__), "sandbox")

import httpx
import pytest
import pytest_asyncio
import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse

from aether_api.db import engine, SessionLocal
from aether_api.orm import Base


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


MOCK_PORT = _free_port()
MOCK_BASE_URL = f"http://127.0.0.1:{MOCK_PORT}/v1"


def build_mock_openai() -> FastAPI:
    app = FastAPI()
    state = {"requests": []}

    @app.get("/v1/models")
    async def models():
        return {"data": [{"id": "mock-chat"}, {"id": "mock-reasoner"},
                          {"id": "mock-vision"}, {"id": "mock-embed"}]}

    @app.get("/v1/_requests")
    async def all_requests():
        return state["requests"]

    @app.post("/v1/embeddings")
    async def embeddings(payload: dict):
        import hashlib
        import math

        inputs = payload.get("input", [])
        if isinstance(inputs, str):
            inputs = [inputs]

        def embed(text: str) -> list[float]:
            vec = [0.0] * 64
            for token in str(text).lower().split():
                d = hashlib.md5(token.encode()).digest()
                for i in range(0, 16, 2):
                    vec[d[i] % 64] += (d[i + 1] / 255.0) - 0.5
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            return [v / norm for v in vec]

        return {"data": [{"index": i, "embedding": embed(t)} for i, t in enumerate(inputs)]}

    @app.post("/v1/chat/completions")
    async def chat(payload: dict):
        state["requests"].append(payload)
        messages = payload.get("messages", [])
        last_user_text = ""
        image_parts = 0
        has_tool_result = any(m.get("role") == "tool" for m in messages)
        for m in reversed(messages):
            if m.get("role") == "user":
                content = m.get("content", "")
                if isinstance(content, list):
                    image_parts = sum(1 for p in content if p.get("type") == "image_url")
                    last_user_text = " ".join(p.get("text", "") for p in content if p.get("type") == "text")
                else:
                    last_user_text = str(content)
                break
        model = payload.get("model", "")
        is_image_classifier = any(
            m.get("role") == "system" and "immediate intent" in str(m.get("content", ""))
            for m in messages
        )

        wants_tool = "COMPUTE_TOOL" in last_user_text and not has_tool_result and "tool" in model
        wants_loop = "LOOP_TOOL" in last_user_text and "tool" in model
        wants_echo = "CALL_TOOL" in last_user_text and not has_tool_result and "tool" in model
        wants_search = "SEARCH_TOOL" in last_user_text and not has_tool_result and "tool" in model
        tool_content = next((m.get("content", "") for m in messages if m.get("role") == "tool"), "")
        if is_image_classifier:
            wants_actual_image = "提示词" not in last_user_text and "prompt" not in last_user_text.lower()
            text = json.dumps({"image_request": wants_actual_image})
        elif image_parts and "vision" in model:
            text = "MOCK_VISION_DESCRIPTION a square test image"
        elif wants_echo and False:
            text = ""
        elif has_tool_result and "echo:" in str(tool_content):
            text = "The echo tool replied correctly."
        elif has_tool_result and "Retrieved web passages" in str(tool_content):
            text = "The answer is cited [1] and also supported by [2]."
        elif has_tool_result and "tool" in model:
            text = f"The computation result is 42. (tool said: {str(tool_content)[:60]})"
        else:
            text = "Hello world"

        if payload.get("stream"):
            async def gen():
                if wants_loop:
                    yield 'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_lp","type":"function","function":{"name":"run_python","arguments":""}}]}}]}\n\n'
                    yield 'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{\\"code\\": \\"import time; time.sleep(2); print(1)\\"}"}}]}}]}\n\n'
                    yield 'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}\n\n'
                    yield 'data: {"usage":{"prompt_tokens":5,"completion_tokens":3}}\n\n'
                    yield "data: [DONE]\n\n"
                    return
                if wants_echo:
                    yield 'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_e1","type":"function","function":{"name":"echo","arguments":""}}]}}]}\n\n'
                    yield 'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{\\"text\\": \\"hi\\"}"}}]}}]}\n\n'
                    yield 'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}\n\n'
                    yield 'data: {"usage":{"prompt_tokens":5,"completion_tokens":3}}\n\n'
                    yield "data: [DONE]\n\n"
                    return
                if wants_search:
                    yield 'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_s1","type":"function","function":{"name":"web_search","arguments":""}}]}}]}\n\n'
                    yield 'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{\\"query\\": \\"aether platform\\"}"}}]}}]}\n\n'
                    yield 'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}\n\n'
                    yield 'data: {"usage":{"prompt_tokens":5,"completion_tokens":3}}\n\n'
                    yield "data: [DONE]\n\n"
                    return
                if wants_tool:
                    yield 'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_abc","type":"function","function":{"name":"run_python","arguments":""}}]}}]}\n\n'
                    yield 'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{\\"code\\": \\"print(6*7)\\"}"}}]}}]}\n\n'
                    yield 'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}\n\n'
                    yield 'data: {"usage":{"prompt_tokens":5,"completion_tokens":3}}\n\n'
                    yield "data: [DONE]\n\n"
                    return
                yield 'data: {"choices":[{"delta":{"reasoning_content":"Thinking..."}}]}\n\n'
                yield "data: " + json.dumps({"choices": [{"delta": {"content": text + " "}}]}) + "\n\n"
                yield 'data: {"choices":[{"delta":{"content":"done"},"finish_reason":"stop"}]}\n\n'
                yield 'data: {"usage":{"prompt_tokens":5,"completion_tokens":2}}\n\n'
                yield "data: [DONE]\n\n"
            return StreamingResponse(gen(), media_type="text/event-stream")

        if wants_search:
            return JSONResponse({
                "choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
                    {"id": "call_s1", "type": "function",
                     "function": {"name": "web_search", "arguments": '{"query": "aether platform"}'}}
                ]}, "finish_reason": "tool_calls"}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 1},
            })
        if wants_tool:
            return JSONResponse({
                "choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
                    {"id": "call_abc", "type": "function",
                     "function": {"name": "run_python", "arguments": '{"code": "print(6*7)"}'}}
                ]}, "finish_reason": "tool_calls"}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 1},
            })
        return JSONResponse({
            "choices": [{"message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 1},
        })

    return app


@pytest.fixture(scope="session", autouse=True)
def mock_openai_server():
    config = uvicorn.Config(build_mock_openai(), host="127.0.0.1", port=MOCK_PORT, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while time.time() < deadline and not server.started:
        time.sleep(0.05)
    yield MOCK_BASE_URL
    server.should_exit = True


@pytest_asyncio.fixture()
async def mock_client():
    async with httpx.AsyncClient(timeout=30) as c:
        yield c


@pytest.fixture()
def live_server(tmp_path_factory):
    """Boot the real app under uvicorn in a subprocess.

    Needed because httpx.ASGITransport buffers the whole response and cannot
    deliver incremental SSE (required for mid-stream approval / steering).
    Image warm-up is skipped so startup stays fast and off the DCU.
    """
    import socket
    import subprocess
    import time as _time
    import urllib.request

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()

    db_path = tmp_path_factory.mktemp("live") / "live.db"
    storage = tmp_path_factory.mktemp("live_storage")
    sandbox = tmp_path_factory.mktemp("live_sandbox")

    env = dict(os.environ)
    env.update({
        "DATABASE_URL": f"sqlite+aiosqlite:///{db_path}",
        "SECRET_KEY": "live-server-secret-key-long-enough-32",
        "STORAGE_ROOT": str(storage),
        "SANDBOX_ROOT": str(sandbox),
        "AETHER_SKIP_IMAGE_WARMUP": "1",
    })
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "aether_api.main:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        env=env, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    # Create schema in the fresh sqlite DB before the server boots (no alembic here).
    import asyncio

    from sqlalchemy.ext.asyncio import create_async_engine

    from aether_api.orm import Base

    async def _init_schema():
        eng = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await eng.dispose()

    asyncio.run(_init_schema())

    base = f"http://127.0.0.1:{port}"
    deadline = _time.time() + 60
    ready = False
    while _time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base}/api/health", timeout=2) as r:
                if r.status == 200:
                    ready = True
                    break
        except Exception:
            _time.sleep(0.3)
    if not ready:
        proc.kill()
        raise RuntimeError("live server failed to start")
    yield base
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest_asyncio.fixture()
async def db():
    import shutil

    storage_root = os.path.join(os.path.dirname(__file__), "storage")
    shutil.rmtree(storage_root, ignore_errors=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield SessionLocal
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    shutil.rmtree(storage_root, ignore_errors=True)
