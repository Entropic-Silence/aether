import pytest
import pytest_asyncio
import httpx

from aether_api.main import app
from aether_api.services.imagegen import (
    Automatic1111Provider,
    ComfyUIProvider,
    ImageParams,
    Krea2LocalProvider,
    StabilityAIProvider,
    _image_bytes_from_response,
)

from helpers import auth_headers, register


@pytest_asyncio.fixture()
async def client(db):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=60) as c:
        yield c


def test_comfyui_txt2img_workflow_structure():
    p = ComfyUIProvider("http://localhost:8188", checkpoint="sd_xl.safetensors")
    params = ImageParams(prompt="a cat", width=512, height=512, steps=20, cfg=7.0, seed=42)
    wf = p._txt2img_workflow(params)
    assert wf["4"]["inputs"]["ckpt_name"] == "sd_xl.safetensors"
    assert wf["6"]["inputs"]["text"] == "a cat"
    assert wf["3"]["inputs"]["seed"] == 42
    assert wf["3"]["inputs"]["steps"] == 20
    assert wf["5"]["inputs"]["width"] == 512
    assert "SaveImage" in wf["9"]["class_type"]
    assert p.capabilities()["image_to_image"] is True
    assert p.capabilities()["inpainting"] is True


def test_comfyui_img2img_workflow_replaces_latent():
    p = ComfyUIProvider("http://localhost:8188", checkpoint="m.safetensors")
    params = ImageParams(prompt="x", strength=0.7)
    wf = p._img2img_workflow(params, "src.png")
    assert wf["10"]["inputs"]["image"] == "src.png"
    assert wf["3"]["inputs"]["denoise"] == 0.7
    assert wf["3"]["inputs"]["latent_image"] == ["11", 0]
    assert "5" not in wf  # EmptyLatentImage removed


def test_comfyui_inpaint_workflow_uses_mask():
    p = ComfyUIProvider("http://localhost:8188", checkpoint="m.safetensors")
    params = ImageParams(prompt="x")
    wf = p._inpaint_workflow(params, "src.png", "mask.png")
    assert wf["10"]["inputs"]["image"] == "src.png"
    assert wf["12"]["inputs"]["image"] == "mask.png"
    assert wf["3"]["inputs"]["latent_image"] == ["13", 0]


def test_comfyui_custom_workflow_substitutes_typed_placeholders():
    p = ComfyUIProvider("http://localhost:8188", checkpoint="flux.safetensors", options={
        "workflows": {"txt2img": {
            "1": {"class_type": "CustomNode", "inputs": {
                "text": "${prompt}", "width": "${width}", "seed": "${seed}",
                "label": "model=${checkpoint}",
            }},
        }},
    })
    wf = p._custom_workflow("txt2img", ImageParams(prompt="一只猫", width=768, seed=7))
    assert wf["1"]["inputs"]["text"] == "一只猫"
    assert wf["1"]["inputs"]["width"] == 768
    assert wf["1"]["inputs"]["seed"] == 7
    assert wf["1"]["inputs"]["label"] == "model=flux.safetensors"


def test_automatic1111_payload_and_stability_aspect():
    params = ImageParams(prompt="cat", negative_prompt="blur", width=1024, height=576,
                         steps=30, cfg=5.5, seed=9)
    payload = Automatic1111Provider("http://localhost:7860")._payload(params)
    assert payload["cfg_scale"] == 5.5
    assert payload["negative_prompt"] == "blur"
    assert payload["seed"] == 9
    assert StabilityAIProvider._aspect(1024, 576) == "16:9"


@pytest.mark.asyncio
async def test_image_response_envelope_normalization():
    raw = b"fake-png"
    encoded = __import__("base64").b64encode(raw).decode()
    assert await _image_bytes_from_response({"data": [{"b64_json": encoded}]}) == raw
    assert await _image_bytes_from_response({"images": [f"data:image/png;base64,{encoded}"]}) == raw


def test_krea2_capabilities():
    p = Krea2LocalProvider("/nonexistent")
    caps = p.capabilities()
    assert caps["text_to_image"] is True
    assert caps["image_to_image"] is True  # native via Qwen3-VL encoder
    assert caps["inpainting"] is False


@pytest_asyncio.fixture()
async def comfyui_model(client):
    """Register a comfyui image model (no local path needed) so the generate
    endpoint reaches mode validation."""
    data = await register(client)
    token = data["access_token"]
    H = auth_headers(token)
    r = await client.post("/api/v1/images/models", headers=H, json={
        "provider_kind": "comfyui", "name": "Comfy Test", "model_ref": "m.safetensors",
        "base_url": "http://localhost:8188", "is_default": True,
    })
    assert r.status_code == 201, r.text
    return token


@pytest.mark.asyncio
async def test_img2img_requires_source(client, comfyui_model):
    H = auth_headers(comfyui_model)
    r = await client.post("/api/v1/images/generations", headers=H,
                          json={"prompt": "x", "mode": "img2img"})
    assert r.status_code == 400
    assert "source_file_id" in r.json()["error"]["message"]


@pytest.mark.asyncio
async def test_inpaint_requires_mask(client, comfyui_model):
    H = auth_headers(comfyui_model)
    r = await client.post("/api/v1/images/generations", headers=H,
                          json={"prompt": "x", "mode": "inpaint", "source_file_id": "abc"})
    assert r.status_code == 400
    assert "mask_file_id" in r.json()["error"]["message"]
