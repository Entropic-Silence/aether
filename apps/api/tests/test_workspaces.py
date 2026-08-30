import pytest
import pytest_asyncio
import httpx

from aether_api.main import app

from helpers import auth_headers, register


@pytest_asyncio.fixture()
async def client(db):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=60) as c:
        yield c


@pytest.mark.asyncio
async def test_first_user_becomes_workspace_owner(client):
    data = await register(client)
    token = data["access_token"]
    H = auth_headers(token)
    r = await client.get("/api/v1/workspaces", headers=H)
    assert r.status_code == 200
    ws = r.json()
    assert len(ws) == 1
    assert ws[0]["role"] == "owner"


@pytest.mark.asyncio
async def test_second_user_added_as_member(client):
    owner = await register(client, email="owner@example.com")
    member = await register(client, email="member@example.com")
    mH = auth_headers(member["access_token"])
    r = await client.get("/api/v1/workspaces", headers=mH)
    assert r.status_code == 200
    ws = r.json()
    assert len(ws) == 1
    assert ws[0]["role"] == "member"


@pytest.mark.asyncio
async def test_add_and_remove_member(client):
    owner = await register(client, email="owner@example.com")
    await register(client, email="member@example.com")
    oH = auth_headers(owner["access_token"])

    ws_list = (await client.get("/api/v1/workspaces", headers=oH)).json()
    ws_id = ws_list[0]["id"]

    r = await client.post(f"/api/v1/workspaces/{ws_id}/members", headers=oH,
                          json={"email": "member@example.com", "role": "admin"})
    # member already auto-added on register -> duplicate rejected
    assert r.status_code == 422

    # list members
    r = await client.get(f"/api/v1/workspaces/{ws_id}/members", headers=oH)
    members = r.json()
    assert len(members) == 2
    member_row = next(m for m in members if m["email"] == "member@example.com")
    assert member_row["role"] == "member"

    # promote
    r = await client.patch(f"/api/v1/workspaces/{ws_id}/members/{member_row['user_id']}",
                           headers=oH, json={"role": "admin"})
    assert r.status_code == 200 and r.json()["role"] == "admin"

    # cannot remove owner
    owner_row = next(m for m in members if m["email"] == "owner@example.com")
    r = await client.delete(f"/api/v1/workspaces/{ws_id}/members/{owner_row['user_id']}", headers=oH)
    assert r.status_code == 422

    # remove member
    r = await client.delete(f"/api/v1/workspaces/{ws_id}/members/{member_row['user_id']}", headers=oH)
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_member_cannot_manage_members(client):
    await register(client, email="owner@example.com")
    member = await register(client, email="member@example.com")
    mH = auth_headers(member["access_token"])
    ws_list = (await client.get("/api/v1/workspaces", headers=mH)).json()
    ws_id = ws_list[0]["id"]
    r = await client.post(f"/api/v1/workspaces/{ws_id}/members", headers=mH,
                          json={"email": "other@example.com", "role": "member"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_create_workspace(client):
    owner = await register(client, email="owner@example.com")
    oH = auth_headers(owner["access_token"])
    r = await client.post("/api/v1/workspaces", headers=oH, json={"name": "Team B"})
    assert r.status_code == 201 and r.json()["role"] == "owner"
    r = await client.get("/api/v1/workspaces", headers=oH)
    assert len(r.json()) == 2
