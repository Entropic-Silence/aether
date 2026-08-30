import pytest
import pytest_asyncio
import httpx

from aether_api.main import app

from helpers import auth_headers, make_model, make_provider, register


@pytest_asyncio.fixture()
async def client(db):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=60) as c:
        yield c


@pytest.mark.asyncio
async def test_skill_crud_import_export(client):
    data = await register(client)
    token = data["access_token"]
    headers = auth_headers(token)

    r = await client.post("/api/v1/skills", headers=headers, json={
        "name": "pirate-tone", "description": "Speak like a pirate",
        "instructions": "Respond in pirate slang.", "scope": "global", "priority": 10,
    })
    assert r.status_code == 201, r.text
    skill = r.json()
    assert skill["source"] == "manual"

    r = await client.post("/api/v1/skills", headers=headers, json={
        "name": "bad", "instructions": "x", "scope": "not-a-scope",
    })
    assert r.status_code == 422

    r = await client.get(f"/api/v1/skills/{skill['id']}/export", headers=headers)
    exported = r.json()["skill"]
    assert "id" not in exported and exported["name"] == "pirate-tone"

    r = await client.post("/api/v1/skills/import", headers=headers,
                          json={"skill": {**exported, "name": "pirate-tone-copy"}})
    assert r.status_code == 201
    assert r.json()["source"] == "file"

    r = await client.get("/api/v1/skills", headers=headers)
    assert len(r.json()) == 2

    r = await client.patch(f"/api/v1/skills/{skill['id']}", headers=headers, json={"enabled": False})
    assert r.json()["enabled"] is False

    r = await client.delete(f"/api/v1/skills/{skill['id']}", headers=headers)
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_global_skill_injected_into_system_prompt(client, mock_client, mock_openai_server):
    data = await register(client)
    token = data["access_token"]
    headers = auth_headers(token)
    provider = await make_provider(client, token, mock_openai_server)
    await make_model(client, token, provider["id"], model_id="mock-chat")

    r = await client.post("/api/v1/skills", headers=headers, json={
        "name": "magic-marker", "instructions": "MAGIC_SKILL_MARKER_INSTRUCTION", "scope": "global",
    })
    assert r.status_code == 201

    r = await client.post("/api/v1/conversations", headers=headers, json={})
    conv_id = r.json()["id"]
    async with client.stream(
        "POST", f"/api/v1/conversations/{conv_id}/runs", headers=headers,
        json={"content": "hello"},
    ) as resp:
        async for _ in resp.aiter_text():
            pass

    r = await mock_client.get(f"{mock_openai_server}/_requests")
    requests = r.json()
    chat_reqs = [
        req for req in requests
        if any(m.get("role") == "user" and m.get("content") == "hello" for m in req.get("messages", []))
        and any(m.get("role") == "system" for m in req.get("messages", []))
    ]
    chat_req = chat_reqs[-1]
    system_msg = next(m for m in chat_req["messages"] if m["role"] == "system")
    assert "MAGIC_SKILL_MARKER_INSTRUCTION" in system_msg["content"]
    assert "Skill: magic-marker" in system_msg["content"]


@pytest.mark.asyncio
async def test_import_deepseek_skill_markdown(client):
    data = await register(client)
    headers = auth_headers(data["access_token"])
    markdown = """---
name: repo-review
version: 2.1.0
description: Review a repository carefully
when-to-use: When a user asks for a code review
capabilities: [tools]
priority: 25
---
Inspect the relevant files, run focused tests, and report concrete findings.
"""

    response = await client.post(
        "/api/v1/skills/import-markdown",
        headers=headers,
        json={"filename": "SKILL.md", "content": markdown},
    )

    assert response.status_code == 201, response.text
    skill = response.json()
    assert skill["name"] == "repo-review"
    assert skill["version"] == "2.1.0"
    assert skill["source"] == "deepseek-harness"
    assert skill["trigger"] == "When a user asks for a code review"
    assert skill["capabilities"] == ["tools"]
    assert "run focused tests" in skill["instructions"]
