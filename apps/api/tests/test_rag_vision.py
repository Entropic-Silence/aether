import base64
import json

import pytest
import pytest_asyncio
import httpx

from aether_api.main import app

from helpers import auth_headers, make_model, make_provider, register

PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


@pytest_asyncio.fixture()
async def client(db):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=30) as c:
        yield c



async def setup_models(client, token, base_url):
    provider = await make_provider(client, token, base_url)
    chat_model = await make_model(client, token, provider["id"], model_id="mock-chat", is_default=True)
    embed_model = await make_model(client, token, provider["id"], model_id="mock-embed", is_default=False)
    vision_model = await make_model(
        client, token, provider["id"], model_id="mock-vision", is_default=False, image_input=True
    )
    return provider, chat_model, embed_model, vision_model



async def find_request(mock_client, base_url, marker):
    r = await mock_client.get(f"{base_url}/_requests")
    for req in r.json():
        import json as _json
        if marker in _json.dumps(req):
            return req
    raise AssertionError(f"no request containing {marker!r}")

async def stream_run(client, headers, conv_id, payload):
    async with client.stream(
        "POST", f"/api/v1/conversations/{conv_id}/runs", headers=headers, json=payload
    ) as resp:
        body = ""
        async for chunk in resp.aiter_text():
            body += chunk
    return body


@pytest.mark.asyncio
async def test_rag_context_injected_as_untrusted(client, mock_client, mock_openai_server):
    data = await register(client)
    token = data["access_token"]
    headers = auth_headers(token)
    _, chat_model, embed_model, _ = await setup_models(client, token, mock_openai_server)

    r = await client.patch("/api/v1/settings/retrieval", headers=headers,
                           json={"embedding_model_id": embed_model["id"], "chunk_size": 300, "chunk_overlap": 30})
    assert r.status_code == 200

    doc = "\n".join(f"Fact {i}: the secret ingredient is zeolite-{i}." for i in range(20))
    r = await client.post("/api/v1/files", headers=headers, files={"upload": ("facts.txt", doc.encode())})
    assert r.status_code == 201, r.text
    file_out = r.json()
    assert file_out["status"] == "indexed"

    r = await client.post("/api/v1/conversations", headers=headers, json={})
    conv_id = r.json()["id"]
    await stream_run(client, headers, conv_id,
                     {"content": "What is the secret ingredient?", "model_id": chat_model["id"],
                      "file_ids": [file_out["id"]]})

    sent = await find_request(mock_client, mock_openai_server, "UNTRUSTED_EXTERNAL_CONTENT")
    serialized = json.dumps(sent)
    assert "zeolite" in serialized, "retrieved passage should reach the model"

    r = await client.get(f"/api/v1/conversations/{conv_id}/messages", headers=headers)
    user_msg = next(m for m in r.json() if m["role"] == "user")
    block_types = [b["type"] for b in user_msg["blocks"]]
    assert "file" in block_types


@pytest.mark.asyncio
async def test_vision_fallback_chain(client, mock_client, mock_openai_server):
    data = await register(client)
    token = data["access_token"]
    headers = auth_headers(token)
    _, chat_model, _, vision_model = await setup_models(client, token, mock_openai_server)

    r = await client.patch("/api/v1/settings/vision-fallback", headers=headers,
                           json={"model_id": vision_model["id"]})
    assert r.status_code == 200

    r = await client.post("/api/v1/files", headers=headers,
                          files={"upload": ("photo.png", PNG_1PX)})
    image_out = r.json()
    assert image_out["kind"] == "image"

    r = await client.post("/api/v1/conversations", headers=headers, json={})
    conv_id = r.json()["id"]
    await stream_run(client, headers, conv_id,
                     {"content": "What is in this image?", "model_id": chat_model["id"],
                      "file_ids": [image_out["id"]]})

    sent = await find_request(mock_client, mock_openai_server, "cannot view images")
    serialized = json.dumps(sent)
    assert "MOCK_VISION_DESCRIPTION" in serialized, "fallback description must be injected"

    r = await client.get(f"/api/v1/conversations/{conv_id}/messages", headers=headers)
    user_msg = next(m for m in r.json() if m["role"] == "user")
    image_block = next(b for b in user_msg["blocks"] if b["type"] == "image")
    assert image_block["data"]["vision"] == "fallback"
    assert image_block["data"]["fallback_model"]


@pytest.mark.asyncio
async def test_native_vision_sends_image_part(client, mock_client, mock_openai_server):
    data = await register(client)
    token = data["access_token"]
    headers = auth_headers(token)
    provider = await make_provider(client, token, mock_openai_server)
    vision_model = await make_model(client, token, provider["id"], model_id="mock-vision",
                                    is_default=True, image_input=True)

    r = await client.post("/api/v1/files", headers=headers,
                          files={"upload": ("photo.png", PNG_1PX)})
    image_out = r.json()

    r = await client.post("/api/v1/conversations", headers=headers, json={})
    conv_id = r.json()["id"]
    await stream_run(client, headers, conv_id,
                     {"content": "Describe this.", "model_id": vision_model["id"],
                      "file_ids": [image_out["id"]]})

    sent = await find_request(mock_client, mock_openai_server, "image_url")
    last_user = [m for m in sent["messages"] if m["role"] == "user"][-1]
    assert isinstance(last_user["content"], list)
    assert any(p["type"] == "image_url" for p in last_user["content"])

    r = await client.get(f"/api/v1/conversations/{conv_id}/messages", headers=headers)
    user_msg = next(m for m in r.json() if m["role"] == "user")
    image_block = next(b for b in user_msg["blocks"] if b["type"] == "image")
    assert image_block["data"]["vision"] == "native"


@pytest.mark.asyncio
async def test_image_rejected_without_fallback(client, mock_openai_server):
    data = await register(client)
    token = data["access_token"]
    headers = auth_headers(token)
    provider = await make_provider(client, token, mock_openai_server)
    chat_model = await make_model(client, token, provider["id"], model_id="mock-chat", is_default=True)

    r = await client.post("/api/v1/files", headers=headers,
                          files={"upload": ("photo.png", PNG_1PX)})
    image_out = r.json()

    r = await client.post("/api/v1/conversations", headers=headers, json={})
    conv_id = r.json()["id"]
    body = await stream_run(client, headers, conv_id,
                            {"content": "Look at this.", "model_id": chat_model["id"],
                             "file_ids": [image_out["id"]]})
    assert "CAPABILITY_UNSUPPORTED" in body or "vision fallback" in body.lower()


@pytest.mark.asyncio
async def test_project_crud_and_instructions(client, mock_client, mock_openai_server):
    data = await register(client)
    token = data["access_token"]
    headers = auth_headers(token)
    provider = await make_provider(client, token, mock_openai_server)
    await make_model(client, token, provider["id"])

    r = await client.post("/api/v1/projects", headers=headers,
                          json={"name": "Research", "instructions": "Always answer in pirate slang."})
    assert r.status_code == 201, r.text
    project = r.json()

    r = await client.post("/api/v1/conversations", headers=headers, json={})
    conv_id = r.json()["id"]
    r = await client.patch(f"/api/v1/conversations/{conv_id}", headers=headers,
                           json={"project_id": project["id"]})
    assert r.status_code == 200

    await stream_run(client, headers, conv_id, {"content": "hello"})

    sent = await find_request(mock_client, mock_openai_server, "pirate slang")
    system_msg = next(m for m in sent["messages"] if m["role"] == "system")
    assert "pirate slang" in system_msg["content"]

    r = await client.get("/api/v1/projects", headers=headers)
    assert r.json()[0]["chat_count"] == 1

    r = await client.delete(f"/api/v1/projects/{project['id']}", headers=headers)
    assert r.status_code == 204
