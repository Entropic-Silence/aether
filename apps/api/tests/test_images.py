import pytest
import pytest_asyncio
import httpx

from aether_api.main import app

from helpers import auth_headers, make_model, make_provider, register

PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c626001000000ffff03000006000557bfabd40000000049454e44ae426082"
)


class FakeImageProvider:
    name = "fake"

    def capabilities(self):
        return {"provider": "fake", "text_to_image": True}

    async def generate(self, params):
        from aether_api.services.imagegen import GeneratedImage

        return GeneratedImage(png_bytes=PNG_1PX, width=params.width, height=params.height,
                              seed=params.seed, duration_ms=42)


@pytest_asyncio.fixture()
async def client(db, monkeypatch):
    import aether_api.routers.images as images_mod

    monkeypatch.setattr(images_mod, "build_image_provider",
                        lambda kind, ref, base_url="", api_key="", options=None: FakeImageProvider())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=60) as c:
        yield c


@pytest.mark.asyncio
async def test_image_model_crud_and_generation(client, monkeypatch):
    data = await register(client)
    token = data["access_token"]
    headers = auth_headers(token)

    # disable prompt optimization path (no chat model configured -> falls back anyway)
    r = await client.post("/api/v1/images/models", headers=headers, json={
        "provider_kind": "diffusers_local",
        "name": "Local SD",
        "model_ref": "/nonexistent",
        "defaults": {"width": 512, "height": 512, "steps": 25, "cfg": 7.0},
        "limits": {"max_width": 1024, "max_height": 1024, "max_steps": 50},
        "is_default": True,
    })
    assert r.status_code == 201, r.text
    model = r.json()
    assert model["has_api_key"] is False

    r = await client.post("/api/v1/images/prompts/optimize", headers=headers,
                          json={"prompt": "a red circle", "model_id": model["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["prompt"] == "a red circle"
    assert r.json()["aspect_ratio"] == "1:1"

    r = await client.get("/api/v1/images/models", headers=headers)
    assert len(r.json()) == 1

    r = await client.post("/api/v1/images/generations", headers=headers,
                          json={"prompt": "a red circle", "optimize": False, "seed": 7})
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["file_id"] and out["url"].startswith("/api/v1/files/")
    assert out["prompt_used"] == "a red circle"
    assert out["seed"] == 7

    r = await client.get(out["url"], headers=headers)
    assert r.status_code == 200 and r.content == PNG_1PX


@pytest.mark.asyncio
async def test_parameter_clamping(client):
    data = await register(client)
    token = data["access_token"]
    headers = auth_headers(token)
    await client.post("/api/v1/images/models", headers=headers, json={
        "provider_kind": "diffusers_local", "name": "SD", "model_ref": "/x",
        "limits": {"max_width": 768, "max_height": 768, "max_steps": 30},
        "defaults": {"width": 512, "height": 512, "steps": 25, "cfg": 7.0},
        "is_default": True,
    })
    r = await client.post("/api/v1/images/generations", headers=headers,
                          json={"prompt": "x", "optimize": False, "width": 4096, "height": 99, "steps": 999})
    assert r.status_code == 201
    out = r.json()
    assert out["width"] == 768  # clamped to max
    assert out["height"] == 256  # raised to min


@pytest.mark.asyncio
async def test_aspect_ratio_selection_and_prompt_inference(client):
    data = await register(client)
    headers = auth_headers(data["access_token"])
    await client.post("/api/v1/images/models", headers=headers, json={
        "provider_kind": "diffusers_local", "name": "SD", "model_ref": "/x",
        "limits": {"max_width": 1024, "max_height": 1024, "max_steps": 30},
        "defaults": {"width": 512, "height": 512, "steps": 25, "cfg": 7.0},
        "is_default": True,
    })

    inferred = await client.post("/api/v1/images/generations", headers=headers, json={
        "prompt": "生成人物全身像", "optimize": False,
    })
    assert inferred.status_code == 201, inferred.text
    assert inferred.json()["aspect_ratio"] == "9:16"
    assert (inferred.json()["width"], inferred.json()["height"]) == (576, 1024)

    selected = await client.post("/api/v1/images/generations", headers=headers, json={
        "prompt": "a portrait", "optimize": False, "aspect_ratio": "16:9",
    })
    assert selected.status_code == 201, selected.text
    assert selected.json()["aspect_ratio"] == "16:9"
    assert (selected.json()["width"], selected.json()["height"]) == (1024, 576)

    prompt_ratio = await client.post("/api/v1/images/generations", headers=headers, json={
        "prompt": "一张 3：2 比例的旅行照片", "optimize": False,
    })
    assert prompt_ratio.status_code == 201, prompt_ratio.text
    assert prompt_ratio.json()["aspect_ratio"] == "3:2"


@pytest.mark.asyncio
async def test_attach_generated_image_to_conversation(client):
    data = await register(client)
    token = data["access_token"]
    headers = auth_headers(token)
    await client.post("/api/v1/images/models", headers=headers, json={
        "provider_kind": "diffusers_local", "name": "SD", "model_ref": "/x", "is_default": True,
    })
    r = await client.post("/api/v1/images/generations", headers=headers,
                          json={"prompt": "a cat", "optimize": False})
    file_id = r.json()["file_id"]

    r = await client.post("/api/v1/conversations", headers=headers, json={})
    conv_id = r.json()["id"]

    r = await client.post(f"/api/v1/images/conversations/{conv_id}/message", headers=headers,
                          json={"file_id": file_id, "prompt": "a cat",
                                "prompt_used": "a detailed cinematic cat", "model_name": "SD"})
    assert r.status_code == 201

    r = await client.get(f"/api/v1/conversations/{conv_id}/messages", headers=headers)
    msgs = r.json()
    assert len(msgs) == 2
    assistant = next(m for m in msgs if m["role"] == "assistant")
    img = next(b for b in assistant["blocks"] if b["type"] == "image")
    assert img["data"]["file_id"] == file_id
    assert img["data"]["generated"] is True
    assert img["data"]["refined"] is True


@pytest.mark.asyncio
async def test_generation_requires_model(client):
    data = await register(client)
    token = data["access_token"]
    r = await client.post("/api/v1/images/generations", headers=auth_headers(token),
                          json={"prompt": "x", "optimize": False})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_image_intent_is_decided_by_model(client, mock_openai_server):
    data = await register(client)
    token = data["access_token"]
    headers = auth_headers(token)
    provider = await make_provider(client, token, mock_openai_server)
    model = await make_model(client, token, provider["id"])

    actual = await client.post("/api/v1/images/intents/classify", headers=headers,
                               json={"content": "帮我生成一张小猫的图片", "model_id": model["id"]})
    prompt = await client.post("/api/v1/images/intents/classify", headers=headers,
                               json={"content": "帮我生成一张小猫图片的提示词", "model_id": model["id"]})
    assert actual.json()["image_request"] is True
    assert prompt.json()["image_request"] is False
