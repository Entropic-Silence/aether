import pytest
import pytest_asyncio
import httpx

from aether_api.main import app

from helpers import auth_headers, make_model, make_provider, register


@pytest_asyncio.fixture()
async def client(db):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=120) as c:
        yield c


@pytest.mark.asyncio
async def test_share_link_public_access_and_delete(client):
    data = await register(client)
    token = data["access_token"]
    H = auth_headers(token)
    provider = await make_provider(client, token, "http://mock")
    await make_model(client, token, provider["id"], model_id="mock-chat")

    conv = await client.post("/api/v1/conversations", headers=H, json={})
    cid = conv.json()["id"]

    r = await client.post("/api/v1/shares", headers=H, json={"conversation_id": cid, "mode": "link"})
    assert r.status_code == 201, r.text
    share = r.json()
    assert share["token"] and share["url"].startswith("/share/")

    # Public access needs no auth
    r = await client.get(f"/api/v1/shares/public/{share['token']}")
    assert r.status_code == 200, r.text
    assert r.json()["id"] == cid

    # Private mode blocks public access
    r = await client.post("/api/v1/shares", headers=H, json={"conversation_id": cid, "mode": "private"})
    assert r.json()["mode"] == "private"
    r = await client.get(f"/api/v1/shares/public/{share['token']}")
    assert r.status_code == 404

    r = await client.delete(f"/api/v1/shares/{share['id']}", headers=H)
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_public_share_killswitch(client):
    data = await register(client)
    token = data["access_token"]
    H = auth_headers(token)
    provider = await make_provider(client, token, "http://mock")
    await make_model(client, token, provider["id"], model_id="mock-chat")
    conv = await client.post("/api/v1/conversations", headers=H, json={})
    cid = conv.json()["id"]

    # admin disables public sharing
    r = await client.patch("/api/v1/shares/settings", headers=H, json={"public_enabled": False})
    assert r.json()["public_enabled"] is False

    r = await client.post("/api/v1/shares", headers=H, json={"conversation_id": cid, "mode": "public"})
    assert r.status_code == 403

    # link mode still allowed
    r = await client.post("/api/v1/shares", headers=H, json={"conversation_id": cid, "mode": "link"})
    assert r.status_code == 201
    token_s = r.json()["token"]
    # existing link still accessible (mode is link, not public)
    r = await client.get(f"/api/v1/shares/public/{token_s}")
    assert r.status_code == 200

    # re-enable
    await client.patch("/api/v1/shares/settings", headers=H, json={"public_enabled": True})


@pytest.mark.asyncio
async def test_message_quota_enforced(client, mock_openai_server):
    data = await register(client)
    token = data["access_token"]
    H = auth_headers(token)
    provider = await make_provider(client, token, mock_openai_server)
    await make_model(client, token, provider["id"], model_id="mock-chat")

    # set a tiny message quota
    r = await client.patch("/api/v1/settings/me", headers=H, json={"daily_message_limit": 1})
    assert r.json()["daily_message_limit"] == 1

    conv = await client.post("/api/v1/conversations", headers=H, json={})
    cid = conv.json()["id"]

    # first message allowed
    async with client.stream("POST", f"/api/v1/conversations/{cid}/runs", headers=H,
                             json={"content": "hello"}) as resp:
        async for _ in resp.aiter_text():
            pass

    # second message blocked
    r = await client.post(f"/api/v1/conversations/{cid}/runs", headers=H,
                          json={"content": "hello again"})
    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "QUOTA_EXCEEDED"

    # reset quota
    await client.patch("/api/v1/settings/me", headers=H, json={"daily_message_limit": 0})


@pytest.mark.asyncio
async def test_quota_status_endpoint(client):
    data = await register(client)
    token = data["access_token"]
    H = auth_headers(token)
    r = await client.get("/api/v1/usage/me", headers=H)
    assert r.status_code == 200
    body = r.json()
    assert "total" in body and "quota" in body


@pytest.mark.asyncio
async def test_global_search(client):
    data = await register(client)
    token = data["access_token"]
    H = auth_headers(token)
    conv = await client.post("/api/v1/conversations", headers=H, json={"title": "Quantum research notes"})
    r = await client.get("/api/v1/search?q=quantum", headers=H)
    assert r.status_code == 200
    assert any("Quantum" in c["title"] for c in r.json()["conversations"])
    r = await client.get("/api/v1/search?q=nonexistentterm123", headers=H)
    assert r.json()["conversations"] == []


@pytest.mark.asyncio
async def test_system_prompts_crud_and_activation(client, mock_client, mock_openai_server):
    data = await register(client)
    token = data["access_token"]
    H = auth_headers(token)
    provider = await make_provider(client, token, mock_openai_server)
    await make_model(client, token, provider["id"], model_id="mock-chat")

    r = await client.post("/api/v1/system-prompts", headers=H,
                          json={"name": "pirate", "text": "Respond like a pirate. MARKER_PROMPT_XYZ"})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert r.json()["version"] == 1

    # draft cannot be activated
    r = await client.post(f"/api/v1/system-prompts/{pid}/activate", headers=H)
    assert r.status_code == 422

    # publish then activate
    r = await client.patch(f"/api/v1/system-prompts/{pid}", headers=H, json={"status": "published"})
    assert r.json()["status"] == "published"
    r = await client.post(f"/api/v1/system-prompts/{pid}/activate", headers=H)
    assert r.json()["ok"] is True

    # run a chat and verify the active prompt is used
    conv = await client.post("/api/v1/conversations", headers=H, json={})
    cid = conv.json()["id"]
    async with client.stream("POST", f"/api/v1/conversations/{cid}/runs", headers=H,
                             json={"content": "ahoy"}) as resp:
        async for _ in resp.aiter_text():
            pass
    reqs = (await mock_client.get(f"{mock_openai_server}/_requests")).json()
    chat_reqs = [q for q in reqs if any(m.get("role") == "user" and m.get("content") == "ahoy"
                                        for m in q.get("messages", []))]
    system = next(m for m in chat_reqs[-1]["messages"] if m["role"] == "system")["content"]
    assert "MARKER_PROMPT_XYZ" in system

    # active prompt cannot be deleted
    r = await client.delete(f"/api/v1/system-prompts/{pid}", headers=H)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_request_logs_recorded(client):
    data = await register(client)
    token = data["access_token"]
    H = auth_headers(token)
    await client.get("/api/v1/conversations", headers=H)
    r = await client.get("/api/v1/logs", headers=H)
    assert r.status_code == 200
    logs = r.json()
    assert len(logs) > 0
    assert any(l["path"] == "/api/v1/conversations" for l in logs)
