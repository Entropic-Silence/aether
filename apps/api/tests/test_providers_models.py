import pytest
import pytest_asyncio
import httpx

from aether_api.main import app

from helpers import auth_headers, make_model, make_provider, register


@pytest_asyncio.fixture()
async def client(db):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_provider_crud(client, mock_openai_server):
    data = await register(client)
    token = data["access_token"]
    provider = await make_provider(client, token, mock_openai_server)
    assert provider["has_api_key"] is True
    assert "api_key" not in provider or provider.get("api_key") is None

    r = await client.get("/api/v1/providers", headers=auth_headers(token))
    assert r.status_code == 200 and len(r.json()) == 1

    r = await client.post(f"/api/v1/providers/{provider['id']}/test", headers=auth_headers(token))
    assert r.status_code == 200 and r.json()["ok"] is True

    r = await client.get(f"/api/v1/providers/{provider['id']}/remote-models", headers=auth_headers(token))
    assert "mock-chat" in r.json()

    r = await client.delete(f"/api/v1/providers/{provider['id']}", headers=auth_headers(token))
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_model_crud_and_probe(client, mock_openai_server):
    data = await register(client)
    token = data["access_token"]
    provider = await make_provider(client, token, mock_openai_server)
    model = await make_model(client, token, provider["id"])
    assert model["effective_capabilities"]["streaming"] is True

    r = await client.get("/api/v1/models", headers=auth_headers(token))
    assert r.status_code == 200 and len(r.json()) == 1

    r = await client.post(f"/api/v1/models/{model['id']}/probe", headers=auth_headers(token))
    assert r.status_code == 200
    assert r.json()["probe_status"] == "probed"

    r = await client.patch(
        f"/api/v1/models/{model['id']}",
        headers=auth_headers(token),
        json={"capability_overrides": {"image_input": True}},
    )
    assert r.status_code == 200
    assert r.json()["effective_capabilities"]["image_input"] is True

    r = await client.post(
        f"/api/v1/models/{model['id']}/test",
        headers=auth_headers(token),
        params={"prompt": "hello"},
    )
    assert r.status_code == 200 and r.json()["ok"] is True


@pytest.mark.asyncio
async def test_admin_required(client, mock_openai_server):
    r = await client.get("/api/v1/providers")
    assert r.status_code == 401
