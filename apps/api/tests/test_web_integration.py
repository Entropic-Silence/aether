import pytest
import pytest_asyncio
import httpx

from aether_api.main import app

from helpers import auth_headers, make_provider, register

FAKE_HTML = """
<html><head><title>Fake page</title></head>
<body><article><p>%s</p></article></body></html>
""" % ("Aether is a capability-driven platform with a pluggable search pipeline. " * 10)


@pytest_asyncio.fixture()
async def client(db):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=60) as c:
        yield c


@pytest.fixture()
def patch_fetch(monkeypatch):
    from aether_api.services import webfetch
    from aether_api.services.webfetch import WebDocument
    from aether_api.services.search import now_iso

    async def fake_fetch(url, deny_hosts=None, timeout_s=20.0):
        return WebDocument(
            url=url, final_url=url, title="Fake page",
            text="Aether is a capability-driven platform with a pluggable search pipeline. " * 10,
            domain="example.com", published_at=None, fetched_at=now_iso(),
        )

    monkeypatch.setattr(webfetch, "fetch_url", fake_fetch)
    import aether_api.services.research as research_mod

    monkeypatch.setattr(research_mod, "fetch_url", fake_fetch)
    import aether_api.services.tools as tools_mod

    return fake_fetch


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
async def test_web_search_tool_produces_citations(client, mock_openai_server, patch_fetch):
    data = await register(client)
    token = data["access_token"]
    headers = auth_headers(token)
    model = await make_tool_model(client, token, mock_openai_server)

    # Configure the mock search provider
    r = await client.patch("/api/v1/settings/search", headers=headers,
                           json={"providers": [{"kind": "mock", "priority": 1, "enabled": True}]})
    assert r.status_code == 200 and r.json()["configured"] is True

    r = await client.post("/api/v1/conversations", headers=headers, json={})
    conv_id = r.json()["id"]

    async with client.stream(
        "POST", f"/api/v1/conversations/{conv_id}/runs", headers=headers,
        json={"content": "SEARCH_TOOL what is aether", "model_id": model["id"]},
    ) as resp:
        body = ""
        async for chunk in resp.aiter_text():
            body += chunk

    assert "event: search.started" in body
    assert "event: search.result" in body
    assert "event: tool.started" in body

    r = await client.get(f"/api/v1/conversations/{conv_id}/messages", headers=headers)
    assistant = next(m for m in r.json() if m["role"] == "assistant")
    types = [b["type"] for b in assistant["blocks"]]
    assert "sources" in types
    sources_block = next(b for b in assistant["blocks"] if b["type"] == "sources")
    sources = sources_block["data"]["sources"]
    assert len(sources) > 0
    assert sources[0]["citation_number"] == 1
    assert sources[0]["url"].startswith("http")

    md = next(b for b in assistant["blocks"] if b["type"] == "markdown")
    assert "[1]" in md["data"]["text"]


@pytest.mark.asyncio
async def test_web_search_disabled_without_config_or_capability(client, mock_openai_server):
    data = await register(client)
    token = data["access_token"]
    headers = auth_headers(token)
    provider = await make_provider(client, token, mock_openai_server)
    r = await client.post(
        "/api/v1/models", headers=headers,
        json={"provider_id": provider["id"], "model_id": "mock-tool", "display_name": "no tool cap",
              "is_default": True, "capabilities": {"streaming": True, "tool_calling": False}},
    )
    model = r.json()
    r = await client.post("/api/v1/conversations", headers=headers, json={})
    conv_id = r.json()["id"]
    async with client.stream(
        "POST", f"/api/v1/conversations/{conv_id}/runs", headers=headers,
        json={"content": "SEARCH_TOOL hello", "model_id": model["id"]},
    ) as resp:
        body = ""
        async for chunk in resp.aiter_text():
            body += chunk
    assert "event: search.started" not in body


@pytest.mark.asyncio
async def test_deep_research_end_to_end(client, mock_openai_server, patch_fetch):
    data = await register(client)
    token = data["access_token"]
    headers = auth_headers(token)
    model = await make_tool_model(client, token, mock_openai_server)

    await client.patch("/api/v1/settings/search", headers=headers,
                       json={"providers": [{"kind": "mock", "priority": 1, "enabled": True}]})

    r = await client.post("/api/v1/conversations", headers=headers, json={})
    conv_id = r.json()["id"]

    async with client.stream(
        "POST", f"/api/v1/conversations/{conv_id}/research", headers=headers,
        json={"goal": "Investigate how capability-driven AI platforms handle search.",
              "model_id": model["id"]},
    ) as resp:
        assert resp.status_code == 200, await resp.aread()
        body = ""
        async for chunk in resp.aiter_text():
            body += chunk

    assert "event: research.planning" in body
    assert "event: research.plan" in body
    assert "event: research.searching" in body
    assert "event: research.reading" in body
    assert "event: research.synthesizing" in body
    assert "event: block.delta" in body
    assert "event: response.completed" in body

    r = await client.get(f"/api/v1/conversations/{conv_id}/messages", headers=headers)
    assistant = next(m for m in r.json() if m["role"] == "assistant")
    types = [b["type"] for b in assistant["blocks"]]
    assert "markdown" in types
    assert "sources" in types
    sources = next(b for b in assistant["blocks"] if b["type"] == "sources")["data"]["sources"]
    assert sources and sources[0]["url"]
