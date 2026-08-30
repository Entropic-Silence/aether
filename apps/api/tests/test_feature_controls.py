import httpx
import pytest
import pytest_asyncio

from aether_api.main import app
from helpers import auth_headers, register


@pytest_asyncio.fixture()
async def client(db):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=30) as value:
        yield value


@pytest.mark.asyncio
async def test_admin_feature_controls_drive_ui_and_server_access(client):
    owner = await register(client)
    owner_headers = auth_headers(owner["access_token"])
    member = await register(client, email="member@example.com")
    member_headers = auth_headers(member["access_token"])
    conversation = await client.post("/api/v1/conversations", headers=member_headers, json={})
    conversation_id = conversation.json()["id"]
    work_conversation = await client.post(
        "/api/v1/conversations", headers=member_headers, json={"mode": "work"},
    )
    work_conversation_id = work_conversation.json()["id"]

    updated = await client.patch("/api/v1/settings/features", headers=owner_headers, json={
        "features": {"chat": False, "work": False, "image_generation": False, "projects": False, "file_uploads": False},
        "policies": {"registration_enabled": False, "max_upload_mb": 7},
    })
    assert updated.status_code == 200, updated.text
    assert updated.json()["features"]["chat"] is False
    assert updated.json()["policies"]["max_upload_mb"] == 7

    ui = await client.get("/api/v1/settings/ui", headers=member_headers)
    assert ui.status_code == 200
    assert ui.json()["features"]["projects"] is False
    assert ui.json()["policies"]["registration_enabled"] is False

    project_list = await client.get("/api/v1/projects", headers=member_headers)
    assert project_list.status_code == 400
    upload = await client.post("/api/v1/files", headers=member_headers,
                               files={"upload": ("hello.txt", b"hello")})
    assert upload.status_code == 400
    run = await client.post(f"/api/v1/conversations/{conversation_id}/runs", headers=member_headers,
                            json={"content": "hello"})
    assert run.status_code == 400
    assert "管理员关闭" in run.json()["error"]["message"]

    # Existing conversations stay readable, but new work requests are denied.
    history = await client.get(f"/api/v1/conversations/{work_conversation_id}", headers=member_headers)
    assert history.status_code == 200
    blocked_work = await client.post(
        f"/api/v1/conversations/{work_conversation_id}/work",
        headers=member_headers,
        json={"task": "continue the old task"},
    )
    assert blocked_work.status_code == 400
    assert "工作模式" in blocked_work.json()["error"]["message"]

    # Control-plane access remains available, while the owner's user-side
    # product requests follow the same policy as every other account.
    owner_user_request = await client.post("/api/v1/conversations", headers=owner_headers, json={})
    assert owner_user_request.status_code == 400
    blocked_image = await client.post(
        "/api/v1/images/generations", headers=owner_headers,
        json={"prompt": "a cat", "optimize": False},
    )
    assert blocked_image.status_code == 400

    blocked_registration = await client.post("/api/v1/auth/register", json={
        "email": "blocked@example.com", "password": "password123", "name": "Blocked",
    })
    assert blocked_registration.status_code == 403

    # Administrators retain control-plane access even while a user feature is disabled.
    admin_read = await client.get("/api/v1/settings/features", headers=owner_headers)
    assert admin_read.status_code == 200
