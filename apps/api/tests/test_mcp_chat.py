import json
import os
import sys

import pytest
import pytest_asyncio
import httpx

from aether_api.main import app

from helpers import auth_headers

FAKE_SERVER = os.path.join(os.path.dirname(__file__), "fake_mcp_server.py")


@pytest_asyncio.fixture()
async def client(db):
    """ASGI client for non-streaming endpoints (CRUD, discovery)."""
    from aether_api.services.tools import clear_mcp_cache

    clear_mcp_cache()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=120) as c:
        yield c
    clear_mcp_cache()


async def setup_owner(live: httpx.AsyncClient) -> str:
    r = await live.post("/api/v1/auth/register",
                        json={"email": "owner@example.com", "password": "password123"})
    if r.status_code != 200:
        r = await live.post("/api/v1/auth/login",
                            json={"email": "owner@example.com", "password": "password123"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_mcp_server_crud_and_discovery(client, mock_openai_server):
    data = await client.post("/api/v1/auth/register",
                             json={"email": "admin2@example.com", "password": "password123"})
    token = data.json()["access_token"]
    headers = auth_headers(token)
    r = await client.post("/api/v1/mcp/servers", headers=headers, json={
        "name": "fake", "transport": "stdio",
        "config": {"command": sys.executable, "args": [FAKE_SERVER]},
    })
    assert r.status_code == 201, r.text
    server = r.json()

    r = await client.post(f"/api/v1/mcp/servers/{server['id']}/test", headers=headers)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["ok"] is True and out["tool_count"] == 1
    assert out["tools"][0]["name"] == "echo"

    r = await client.get("/api/v1/mcp/servers", headers=headers)
    assert r.json()[0]["last_status"] == "connected"


@pytest.mark.asyncio
async def test_mcp_tool_approval_allow_then_runs(live_server, mock_openai_server):
    async with httpx.AsyncClient(base_url=live_server, timeout=120) as live:
        token = await setup_owner(live)
        headers = auth_headers(token)
        await live.post("/api/v1/providers", headers=headers,
                        json={"name": "Mock", "base_url": mock_openai_server})
        models = await live.get("/api/v1/models", headers=headers)
        # create a tool-capable model
        providers = await live.get("/api/v1/providers", headers=headers)
        pid = providers.json()[0]["id"]
        m = await live.post("/api/v1/models", headers=headers, json={
            "provider_id": pid, "model_id": "mock-tool", "display_name": "MT",
            "is_default": True,
            "capabilities": {"text_input": True, "text_output": True, "streaming": True,
                             "system_prompt": True, "tool_calling": True}})
        mid = m.json()["id"]
        s = await live.post("/api/v1/mcp/servers", headers=headers, json={
            "name": "fake", "transport": "stdio",
            "config": {"command": sys.executable, "args": [FAKE_SERVER]}})
        assert s.status_code == 201, s.text

        conv = await live.post("/api/v1/conversations", headers=headers, json={})
        cid = conv.json()["id"]

        approved = False
        events = []
        async with live.stream("POST", f"/api/v1/conversations/{cid}/runs", headers=headers,
                               json={"content": "CALL_TOOL echo", "model_id": mid}) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("event:"):
                    events.append(line[6:].strip())
                if line.startswith("data:") and "approval_id" in line and not approved:
                    d = json.loads(line[5:])
                    ra = await live.post(f"/api/v1/conversations/{cid}/approvals", headers=headers,
                                         json={"approval_id": d["approval_id"],
                                               "decision": "allow", "rule": "once"})
                    assert ra.status_code == 200
                    approved = True

        assert "tool.approval_required" in events
        assert "tool.completed" in events
        assert approved

        msgs = (await live.get(f"/api/v1/conversations/{cid}/messages", headers=headers)).json()
        assistant = next(mm for mm in msgs if mm["role"] == "assistant")
        md = next(b for b in assistant["blocks"] if b["type"] == "markdown")
        assert "echo tool replied" in md["data"]["text"]


@pytest.mark.asyncio
async def test_mcp_tool_denied(live_server, mock_openai_server):
    async with httpx.AsyncClient(base_url=live_server, timeout=120) as live:
        token = await setup_owner(live)
        headers = auth_headers(token)
        await live.post("/api/v1/providers", headers=headers,
                        json={"name": "Mock", "base_url": mock_openai_server})
        providers = await live.get("/api/v1/providers", headers=headers)
        pid = providers.json()[0]["id"]
        m = await live.post("/api/v1/models", headers=headers, json={
            "provider_id": pid, "model_id": "mock-tool", "display_name": "MT",
            "is_default": True,
            "capabilities": {"text_input": True, "text_output": True, "streaming": True,
                             "system_prompt": True, "tool_calling": True}})
        mid = m.json()["id"]
        await live.post("/api/v1/mcp/servers", headers=headers, json={
            "name": "fake", "transport": "stdio",
            "config": {"command": sys.executable, "args": [FAKE_SERVER]}})

        conv = await live.post("/api/v1/conversations", headers=headers, json={})
        cid = conv.json()["id"]

        denied = False
        events = []
        async with live.stream("POST", f"/api/v1/conversations/{cid}/runs", headers=headers,
                               json={"content": "CALL_TOOL echo", "model_id": mid}) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("event:"):
                    events.append(line[6:].strip())
                if line.startswith("data:") and "approval_id" in line and not denied:
                    d = json.loads(line[5:])
                    await live.post(f"/api/v1/conversations/{cid}/approvals", headers=headers,
                                    json={"approval_id": d["approval_id"],
                                          "decision": "deny", "rule": "once"})
                    denied = True

        assert "tool.approval_required" in events
        assert "tool.denied" in events

        msgs = (await live.get(f"/api/v1/conversations/{cid}/messages", headers=headers)).json()
        assistant = next(mm for mm in msgs if mm["role"] == "assistant")
        # denied tool must not have produced an MCP echo result block
        tool_calls = [b for b in assistant["blocks"] if b["type"] == "tool_call"]
        assert tool_calls and tool_calls[0]["data"].get("denied") is True
