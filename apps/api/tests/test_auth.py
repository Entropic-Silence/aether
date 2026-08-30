import pytest
import pytest_asyncio
import httpx

from aether_api.main import app


@pytest_asyncio.fixture()
async def client(db):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def register(client, email="owner@example.com", password="password123"):
    r = await client.post("/api/v1/auth/register", json={"email": email, "password": password, "name": "Owner"})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.asyncio
async def test_register_and_me(client):
    data = await register(client)
    token = data["access_token"]
    assert data["user"]["role"] == "owner"
    r = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == "owner@example.com"


@pytest.mark.asyncio
async def test_login_and_bad_password(client):
    await register(client)
    r = await client.post("/api/v1/auth/login", json={"email": "owner@example.com", "password": "password123"})
    assert r.status_code == 200
    r = await client.post("/api/v1/auth/login", json={"email": "owner@example.com", "password": "wrong"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_me_requires_auth(client):
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 401
