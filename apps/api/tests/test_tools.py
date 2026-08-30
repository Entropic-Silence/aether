import pytest
import pytest_asyncio
import httpx

from aether_api.main import app

from helpers import auth_headers, make_provider, register


@pytest_asyncio.fixture()
async def client(db):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=60) as c:
        yield c


async def make_tool_model(client, token, base_url):
    provider = await make_provider(client, token, base_url)
    r = await client.post(
        "/api/v1/models",
        headers=auth_headers(token),
        json={
            "provider_id": provider["id"],
            "model_id": "mock-tool",
            "display_name": "Mock Tool Model",
            "is_default": True,
            "capabilities": {
                "text_input": True, "text_output": True, "streaming": True,
                "system_prompt": True, "tool_calling": True,
            },
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.asyncio
async def test_agent_loop_executes_tool_and_continues(client, mock_openai_server):
    data = await register(client)
    token = data["access_token"]
    headers = auth_headers(token)
    model = await make_tool_model(client, token, mock_openai_server)

    r = await client.post("/api/v1/conversations", headers=headers, json={})
    conv_id = r.json()["id"]

    async with client.stream(
        "POST", f"/api/v1/conversations/{conv_id}/runs", headers=headers,
        json={"content": "COMPUTE_TOOL 6*7", "model_id": model["id"]},
    ) as resp:
        body = ""
        async for chunk in resp.aiter_text():
            body += chunk

    assert "event: tool.started" in body
    assert "event: tool.completed" in body
    assert "event: response.completed" in body
    assert "run_python" in body

    r = await client.get(f"/api/v1/conversations/{conv_id}/messages", headers=headers)
    assistant = next(m for m in r.json() if m["role"] == "assistant")
    types = [b["type"] for b in assistant["blocks"]]
    assert "tool_call" in types
    assert "tool_result" in types
    assert "markdown" in types

    tool_call = next(b for b in assistant["blocks"] if b["type"] == "tool_call")
    assert tool_call["data"]["name"] == "run_python"

    tool_result = next(b for b in assistant["blocks"] if b["type"] == "tool_result")
    assert tool_result["data"]["exit_code"] == 0
    assert "42" in tool_result["data"]["stdout"]

    md = next(b for b in assistant["blocks"] if b["type"] == "markdown")
    assert "42" in md["data"]["text"]


@pytest.mark.asyncio
async def test_tool_result_fed_back_to_model(client, mock_client, mock_openai_server):
    data = await register(client)
    token = data["access_token"]
    headers = auth_headers(token)
    model = await make_tool_model(client, token, mock_openai_server)

    r = await client.post("/api/v1/conversations", headers=headers, json={})
    conv_id = r.json()["id"]

    async with client.stream(
        "POST", f"/api/v1/conversations/{conv_id}/runs", headers=headers,
        json={"content": "COMPUTE_TOOL 6*7", "model_id": model["id"]},
    ) as resp:
        async for _ in resp.aiter_text():
            pass

    r = await mock_client.get(f"{mock_openai_server}/_requests")
    requests = r.json()
    # Find the request that carries THIS test's tool result (run_python -> "42")
    # back to the model. The shared session mock may hold tool requests from
    # earlier tests (e.g. MCP echo), so match on the result content.
    tool_requests = [
        req for req in requests
        if any(m.get("role") == "tool" and "42" in str(m.get("content", ""))
               for m in req.get("messages", []))
    ]
    assert tool_requests, "tool result must be returned to the model"
    tool_msg = next(m for m in tool_requests[-1]["messages"] if m["role"] == "tool" and "42" in str(m.get("content", "")))
    assert "42" in tool_msg["content"]
    # The assistant message preceding it must carry the native tool_calls shape.
    asst = next(m for m in tool_requests[-1]["messages"] if m.get("tool_calls"))
    assert asst["tool_calls"][0]["function"]["name"] == "run_python"


@pytest.mark.asyncio
async def test_no_tools_when_capability_absent(client, mock_client, mock_openai_server):
    data = await register(client)
    token = data["access_token"]
    headers = auth_headers(token)
    provider = await make_provider(client, token, mock_openai_server)
    r = await client.post(
        "/api/v1/models",
        headers=headers,
        json={
            "provider_id": provider["id"],
            "model_id": "mock-tool",  # mock would emit a tool call if asked
            "display_name": "No Tool Capability",
            "is_default": True,
            "capabilities": {"streaming": True, "system_prompt": True, "tool_calling": False},
        },
    )
    model = r.json()

    r = await client.post("/api/v1/conversations", headers=headers, json={})
    conv_id = r.json()["id"]

    async with client.stream(
        "POST", f"/api/v1/conversations/{conv_id}/runs", headers=headers,
        json={"content": "COMPUTE_TOOL 6*7", "model_id": model["id"]},
    ) as resp:
        body = ""
        async for chunk in resp.aiter_text():
            body += chunk

    assert "event: tool.started" not in body, "tools must be gated by capability"
