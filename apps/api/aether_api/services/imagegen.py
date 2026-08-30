from __future__ import annotations

import asyncio
import base64
import copy
import io
import json
import os
import threading
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

import httpx

from ..errors import CapabilityUnsupportedError, ProviderError


def _strip_data_uri(value: str) -> str:
    return value.split(",", 1)[1] if value.startswith("data:") and "," in value else value


def _decode_base64_image(value: str) -> bytes:
    try:
        return base64.b64decode(_strip_data_uri(value))
    except Exception as exc:  # noqa: BLE001
        raise ProviderError("Image provider returned invalid base64 data") from exc


async def _download_image(url: str, *, base_url: str = "", headers: dict | None = None) -> bytes:
    if url.startswith("/") and base_url:
        url = base_url.rstrip("/") + url
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.get(url, headers=headers or {})
    if response.status_code != 200:
        raise ProviderError(f"Image download returned {response.status_code}", detail=response.text[:300])
    return response.content


async def _image_bytes_from_response(data: dict, *, base_url: str = "", headers: dict | None = None) -> bytes:
    """Normalize the common image response envelopes used by compatible APIs."""
    candidates: list = []
    if isinstance(data.get("data"), list):
        candidates.extend(data["data"])
    if isinstance(data.get("output"), list):
        candidates.extend(data["output"])
    elif data.get("output"):
        candidates.append(data["output"])
    if data.get("image"):
        candidates.append(data["image"])
    if data.get("images") and isinstance(data["images"], list):
        candidates.extend(data["images"])
    for item in candidates:
        if isinstance(item, str):
            if item.startswith(("http://", "https://", "/")):
                return await _download_image(item, base_url=base_url, headers=headers)
            return _decode_base64_image(item)
        if not isinstance(item, dict):
            continue
        for key in ("b64_json", "base64", "image_base64", "image"):
            if item.get(key):
                return _decode_base64_image(str(item[key]))
        for key in ("url", "image_url"):
            if item.get(key):
                return await _download_image(str(item[key]), base_url=base_url, headers=headers)
    raise ProviderError("Image provider returned no image data")


@dataclass
class ImageParams:
    prompt: str
    negative_prompt: str = ""
    width: int = 512
    height: int = 512
    steps: int = 25
    cfg: float = 7.0
    seed: int | None = None
    strength: float = 0.75  # for img2img / inpaint


@dataclass
class GeneratedImage:
    png_bytes: bytes
    width: int
    height: int
    seed: int | None
    duration_ms: int


class ImageProvider(ABC):
    """Image generation backend. Completely separate from LLM providers."""

    name = "abstract"

    def capabilities(self) -> dict:
        return {"provider": self.name, "text_to_image": True,
                "image_to_image": False, "inpainting": False}

    @abstractmethod
    async def generate(self, params: ImageParams) -> GeneratedImage: ...

    async def generate_img2img(self, params: ImageParams, image_bytes: bytes, mime: str) -> GeneratedImage:
        raise CapabilityUnsupportedError(f"{self.name} does not support image-to-image")

    async def generate_inpaint(self, params: ImageParams, image_bytes: bytes,
                               mask_bytes: bytes, mime: str) -> GeneratedImage:
        raise CapabilityUnsupportedError(f"{self.name} does not support inpainting")


class DiffusersLocalProvider(ImageProvider):
    """Runs a local diffusers pipeline on the accelerator (DCU/CUDA/CPU).

    The pipeline is loaded lazily once and kept resident. Generation is
    serialized through a lock so concurrent requests queue instead of OOMing.
    """

    name = "diffusers_local"

    def __init__(self, model_path: str, device: str | None = None):
        self.model_path = model_path
        self.device = device
        self._pipe = None
        self._lock = threading.Lock()

    def capabilities(self) -> dict:
        return {
            "provider": self.name,
            "text_to_image": True,
            "image_to_image": True,
            "inpainting": True,
            "negative_prompt": True,
            "seed": True,
            "steps": True,
            "cfg": True,
        }

    def _load(self):
        if self._pipe is not None:
            return self._pipe
        import torch
        from diffusers import StableDiffusionPipeline
        from diffusers.models.attention_processor import AttnProcessor

        device = self.device or ("cuda" if torch.cuda.is_available() else "cpu")
        dtype = torch.float16 if device == "cuda" else torch.float32
        pipe = StableDiffusionPipeline.from_pretrained(
            self.model_path, torch_dtype=dtype, safety_checker=None,
        )
        try:
            pipe.text_encoder.config._attn_implementation = "eager"
            pipe.unet.set_attn_processor(AttnProcessor())
        except Exception:  # noqa: BLE001
            pass
        pipe = pipe.to(device)
        self._pipe = pipe
        return pipe

    def _generate_sync(self, params: ImageParams) -> GeneratedImage:
        import torch

        started = time.monotonic()
        with self._lock:
            pipe = self._load()
            generator = None
            if params.seed is not None:
                generator = torch.Generator(device=pipe.device).manual_seed(int(params.seed))
            result = pipe(
                prompt=params.prompt,
                negative_prompt=params.negative_prompt or None,
                width=params.width,
                height=params.height,
                num_inference_steps=params.steps,
                guidance_scale=params.cfg,
                generator=generator,
            )
            image = result.images[0]
            buf = io.BytesIO()
            image.save(buf, format="PNG")
            seed = params.seed
            if seed is None and hasattr(result, "generator"):
                seed = None
        duration = int((time.monotonic() - started) * 1000)
        return GeneratedImage(png_bytes=buf.getvalue(), width=params.width,
                              height=params.height, seed=seed, duration_ms=duration)

    async def generate(self, params: ImageParams) -> GeneratedImage:
        return await asyncio.to_thread(self._generate_sync, params)

    def _load_img2img(self):
        if getattr(self, "_pipe_img2img", None) is not None:
            return self._pipe_img2img
        import torch
        from diffusers import StableDiffusionImg2ImgPipeline
        from diffusers.models.attention_processor import AttnProcessor

        device = self.device or ("cuda" if torch.cuda.is_available() else "cpu")
        dtype = torch.float16 if device == "cuda" else torch.float32
        pipe = StableDiffusionImg2ImgPipeline.from_pretrained(
            self.model_path, torch_dtype=dtype, safety_checker=None,
        )
        try:
            pipe.text_encoder.config._attn_implementation = "eager"
            pipe.unet.set_attn_processor(AttnProcessor())
        except Exception:  # noqa: BLE001
            pass
        pipe = pipe.to(device)
        self._pipe_img2img = pipe
        return pipe

    def _load_inpaint(self):
        if getattr(self, "_pipe_inpaint", None) is not None:
            return self._pipe_inpaint
        import torch
        from diffusers import StableDiffusionInpaintPipeline
        from diffusers.models.attention_processor import AttnProcessor

        device = self.device or ("cuda" if torch.cuda.is_available() else "cpu")
        dtype = torch.float16 if device == "cuda" else torch.float32
        pipe = StableDiffusionInpaintPipeline.from_pretrained(
            self.model_path, torch_dtype=dtype, safety_checker=None,
        )
        try:
            pipe.text_encoder.config._attn_implementation = "eager"
            pipe.unet.set_attn_processor(AttnProcessor())
        except Exception:  # noqa: BLE001
            pass
        pipe = pipe.to(device)
        self._pipe_inpaint = pipe
        return pipe

    def _generate_img2img_sync(self, params: ImageParams, image_bytes: bytes) -> GeneratedImage:
        import torch
        from PIL import Image as PILImage

        started = time.monotonic()
        with self._lock:
            pipe = self._load_img2img()
            init_image = PILImage.open(io.BytesIO(image_bytes)).convert("RGB")
            init_image = init_image.resize((params.width, params.height))
            generator = None
            if params.seed is not None:
                generator = torch.Generator(device=pipe.device).manual_seed(int(params.seed))
            result = pipe(
                prompt=params.prompt,
                negative_prompt=params.negative_prompt or None,
                image=init_image,
                strength=params.strength,
                num_inference_steps=params.steps,
                guidance_scale=params.cfg,
                generator=generator,
            )
            image = result.images[0]
            buf = io.BytesIO()
            image.save(buf, format="PNG")
        duration = int((time.monotonic() - started) * 1000)
        return GeneratedImage(png_bytes=buf.getvalue(), width=params.width,
                              height=params.height, seed=params.seed, duration_ms=duration)

    def _generate_inpaint_sync(self, params: ImageParams, image_bytes: bytes, mask_bytes: bytes) -> GeneratedImage:
        import torch
        from PIL import Image as PILImage

        started = time.monotonic()
        with self._lock:
            pipe = self._load_inpaint()
            init_image = PILImage.open(io.BytesIO(image_bytes)).convert("RGB")
            init_image = init_image.resize((params.width, params.height))
            mask = PILImage.open(io.BytesIO(mask_bytes)).convert("L")
            mask = mask.resize((params.width, params.height))
            generator = None
            if params.seed is not None:
                generator = torch.Generator(device=pipe.device).manual_seed(int(params.seed))
            result = pipe(
                prompt=params.prompt,
                negative_prompt=params.negative_prompt or None,
                image=init_image,
                mask_image=mask,
                width=params.width,
                height=params.height,
                num_inference_steps=params.steps,
                guidance_scale=params.cfg,
                generator=generator,
            )
            image = result.images[0]
            buf = io.BytesIO()
            image.save(buf, format="PNG")
        duration = int((time.monotonic() - started) * 1000)
        return GeneratedImage(png_bytes=buf.getvalue(), width=params.width,
                              height=params.height, seed=params.seed, duration_ms=duration)

    async def generate_img2img(self, params: ImageParams, image_bytes: bytes, mime: str) -> GeneratedImage:
        return await asyncio.to_thread(self._generate_img2img_sync, params, image_bytes)

    async def generate_inpaint(self, params: ImageParams, image_bytes: bytes,
                               mask_bytes: bytes, mime: str) -> GeneratedImage:
        return await asyncio.to_thread(self._generate_inpaint_sync, params, image_bytes, mask_bytes)


class OpenAIImagesProvider(ImageProvider):
    """OpenAI-compatible /v1/images/generations endpoint."""

    name = "openai_images"

    def __init__(self, base_url: str, api_key: str = "", model_id: str = "", options: dict | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_id = model_id
        self.options = options or {}

    def capabilities(self) -> dict:
        return {"provider": self.name, "text_to_image": True}

    async def generate(self, params: ImageParams) -> GeneratedImage:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body: dict = {
            "model": self.model_id,
            "prompt": params.prompt,
            "n": 1,
            "size": f"{params.width}x{params.height}",
        }
        body.update(self.options.get("request_extra") or {})
        endpoint = str(self.options.get("endpoint") or "/images/generations")
        started = time.monotonic()
        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(f"{self.base_url}/{endpoint.lstrip('/')}",
                                     headers=headers, json=body)
        if resp.status_code != 200:
            raise ProviderError(f"Image provider returned {resp.status_code}", detail=resp.text[:300])
        data = resp.json()
        duration = int((time.monotonic() - started) * 1000)
        png = await _image_bytes_from_response(data, base_url=self.base_url, headers=headers)
        return GeneratedImage(png_bytes=png, width=params.width, height=params.height,
                              seed=params.seed, duration_ms=duration)


class Automatic1111Provider(ImageProvider):
    """Automatic1111, Forge and SD.Next `/sdapi/v1/*` adapter."""

    name = "automatic1111"

    def __init__(self, base_url: str, api_key: str = "", options: dict | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.options = options or {}

    def capabilities(self) -> dict:
        return {"provider": self.name, "text_to_image": True, "image_to_image": True,
                "inpainting": True, "negative_prompt": True, "seed": True,
                "steps": True, "cfg": True}

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    def _payload(self, params: ImageParams) -> dict:
        body = {
            "prompt": params.prompt, "negative_prompt": params.negative_prompt,
            "width": params.width, "height": params.height,
            "steps": params.steps, "cfg_scale": params.cfg,
            "seed": -1 if params.seed is None else int(params.seed), "batch_size": 1,
        }
        body.update(self.options.get("request_extra") or {})
        return body

    async def _post(self, path: str, body: dict, params: ImageParams) -> GeneratedImage:
        started = time.monotonic()
        async with httpx.AsyncClient(timeout=600) as client:
            response = await client.post(f"{self.base_url}{path}", headers=self._headers(), json=body)
        if response.status_code != 200:
            raise ProviderError(f"Automatic1111 returned {response.status_code}", detail=response.text[:300])
        png = await _image_bytes_from_response(response.json(), base_url=self.base_url, headers=self._headers())
        return GeneratedImage(png_bytes=png, width=params.width, height=params.height,
                              seed=params.seed, duration_ms=int((time.monotonic() - started) * 1000))

    async def generate(self, params: ImageParams) -> GeneratedImage:
        return await self._post("/sdapi/v1/txt2img", self._payload(params), params)

    async def generate_img2img(self, params: ImageParams, image_bytes: bytes, mime: str) -> GeneratedImage:
        body = self._payload(params)
        body.update({"init_images": [base64.b64encode(image_bytes).decode()],
                     "denoising_strength": params.strength})
        return await self._post("/sdapi/v1/img2img", body, params)

    async def generate_inpaint(self, params: ImageParams, image_bytes: bytes,
                               mask_bytes: bytes, mime: str) -> GeneratedImage:
        body = self._payload(params)
        body.update({"init_images": [base64.b64encode(image_bytes).decode()],
                     "mask": base64.b64encode(mask_bytes).decode(),
                     "denoising_strength": params.strength, "inpainting_fill": 1})
        return await self._post("/sdapi/v1/img2img", body, params)


class StabilityAIProvider(ImageProvider):
    """Stability AI v2beta Stable Image API (core/ultra/sd3 endpoints)."""

    name = "stability_api"

    def __init__(self, base_url: str, api_key: str = "", model_ref: str = "core", options: dict | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_ref = model_ref or "core"
        self.options = options or {}

    def capabilities(self) -> dict:
        return {"provider": self.name, "text_to_image": True,
                "negative_prompt": True, "seed": True}

    @staticmethod
    def _aspect(width: int, height: int) -> str:
        ratios = {"1:1": 1, "16:9": 16 / 9, "9:16": 9 / 16, "3:2": 3 / 2,
                  "2:3": 2 / 3, "4:5": 4 / 5, "5:4": 5 / 4, "21:9": 21 / 9, "9:21": 9 / 21}
        target = width / max(height, 1)
        return min(ratios, key=lambda key: abs(ratios[key] - target))

    async def generate(self, params: ImageParams) -> GeneratedImage:
        endpoint = str(self.options.get("endpoint") or f"/stable-image/generate/{self.model_ref}")
        data: dict = {"prompt": params.prompt, "output_format": "png",
                      "aspect_ratio": self._aspect(params.width, params.height)}
        if params.negative_prompt:
            data["negative_prompt"] = params.negative_prompt
        if params.seed is not None:
            data["seed"] = int(params.seed)
        data.update(self.options.get("request_extra") or {})
        headers = {"Accept": "image/*", "Authorization": f"Bearer {self.api_key}"}
        started = time.monotonic()
        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.post(f"{self.base_url}/{endpoint.lstrip('/')}", headers=headers,
                                         files={"none": (None, "")}, data=data)
        if response.status_code != 200:
            raise ProviderError(f"Stability API returned {response.status_code}", detail=response.text[:300])
        content_type = response.headers.get("content-type", "")
        png = response.content if content_type.startswith("image/") else await _image_bytes_from_response(response.json())
        return GeneratedImage(png_bytes=png, width=params.width, height=params.height,
                              seed=params.seed, duration_ms=int((time.monotonic() - started) * 1000))


class ComfyUIProvider(ImageProvider):
    """Adapter for a ComfyUI server. Builds minimal workflows for txt2img,
    img2img, and inpainting, queues them via /prompt, polls /history, and
    fetches the output image via /view. This is the adapter path for locally
    deployed ComfyUI models (e.g. Krea 2, z-image, SD/SDXL, FLUX)."""

    name = "comfyui"

    def __init__(self, base_url: str, checkpoint: str = "", api_key: str = "", options: dict | None = None):
        self.base_url = base_url.rstrip("/")
        self.checkpoint = checkpoint  # ckpt_name inside ComfyUI's models dir
        self.api_key = api_key
        self.options = options or {}

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    def capabilities(self) -> dict:
        return {"provider": self.name, "text_to_image": True,
                "image_to_image": True, "inpainting": True,
                "negative_prompt": True, "seed": True, "steps": True, "cfg": True}

    def _txt2img_workflow(self, params: ImageParams) -> dict:
        seed = params.seed if params.seed is not None else 0
        return {
            "3": {"class_type": "KSampler", "inputs": {
                "seed": seed, "steps": params.steps, "cfg": params.cfg,
                "sampler_name": "euler", "scheduler": "normal",
                "denoise": 1.0, "model": ["4", 0],
                "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0]}},
            "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": self.checkpoint}},
            "5": {"class_type": "EmptyLatentImage", "inputs": {
                "width": params.width, "height": params.height, "batch_size": 1}},
            "6": {"class_type": "CLIPTextEncode", "inputs": {"text": params.prompt, "clip": ["4", 1]}},
            "7": {"class_type": "CLIPTextEncode", "inputs": {"text": params.negative_prompt or "", "clip": ["4", 1]}},
            "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
            "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "aether", "images": ["8", 0]}},
        }

    def _custom_workflow(self, mode: str, params: ImageParams,
                         source_image: str = "", mask_image: str = "") -> dict | None:
        workflows = self.options.get("workflows") or {}
        template = workflows.get(mode) if isinstance(workflows, dict) else None
        if template is None and mode == "txt2img":
            template = self.options.get("workflow")
        if not isinstance(template, dict):
            return None
        values = {
            "prompt": params.prompt, "negative_prompt": params.negative_prompt,
            "width": params.width, "height": params.height, "steps": params.steps,
            "cfg": params.cfg, "seed": params.seed if params.seed is not None else 0,
            "strength": params.strength, "checkpoint": self.checkpoint,
            "source_image": source_image, "mask_image": mask_image,
        }

        def render(value):
            if isinstance(value, dict):
                return {k: render(v) for k, v in value.items()}
            if isinstance(value, list):
                return [render(v) for v in value]
            if not isinstance(value, str):
                return value
            if value.startswith("${") and value.endswith("}") and value[2:-1] in values:
                return values[value[2:-1]]
            rendered = value
            for key, replacement in values.items():
                rendered = rendered.replace("${" + key + "}", str(replacement))
            return rendered

        return render(copy.deepcopy(template))

    async def _queue_and_wait(self, workflow: dict, timeout_s: float = 600) -> bytes:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{self.base_url}/prompt", headers=self._headers(),
                                     json={"prompt": workflow, "client_id": f"aether-{uuid.uuid4().hex}"})
            if resp.status_code != 200:
                raise ProviderError(f"ComfyUI queue returned {resp.status_code}", detail=resp.text[:300])
            prompt_id = resp.json().get("prompt_id")
            if not prompt_id:
                raise ProviderError("ComfyUI did not return a prompt_id")
            deadline = time.monotonic() + timeout_s
            while time.monotonic() < deadline:
                await asyncio.sleep(1.0)
                h = await client.get(f"{self.base_url}/history/{prompt_id}", headers=self._headers())
                if h.status_code != 200:
                    continue
                hist = h.json()
                if prompt_id not in hist:
                    continue
                outputs = hist[prompt_id].get("outputs", {})
                for node_out in outputs.values():
                    images = node_out.get("images") or []
                    if images:
                        img = images[0]
                        view = await client.get(
                            f"{self.base_url}/view",
                            headers=self._headers(),
                            params={"filename": img["filename"],
                                    "subfolder": img.get("subfolder", ""),
                                    "type": img.get("type", "output")})
                        if view.status_code == 200:
                            return view.content
                status = hist[prompt_id].get("status", {})
                if status.get("status_str") == "error":
                    raise ProviderError("ComfyUI workflow failed", detail=str(status)[:300])
            raise ProviderError("ComfyUI workflow timed out")

    async def generate(self, params: ImageParams) -> GeneratedImage:
        started = time.monotonic()
        workflow = self._custom_workflow("txt2img", params) or self._txt2img_workflow(params)
        png = await self._queue_and_wait(workflow)
        duration = int((time.monotonic() - started) * 1000)
        return GeneratedImage(png_bytes=png, width=params.width, height=params.height,
                              seed=params.seed, duration_ms=duration)

    async def _upload_image(self, image_bytes: bytes, filename: str) -> str:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.base_url}/upload/image",
                headers=self._headers(), files={"image": (filename, image_bytes, "image/png")},
                data={"overwrite": "true"})
            if resp.status_code != 200:
                raise ProviderError(f"ComfyUI image upload failed ({resp.status_code})")
            return resp.json().get("name", filename)

    def _img2img_workflow(self, params: ImageParams, image_name: str) -> dict:
        wf = self._txt2img_workflow(params)
        wf["3"]["inputs"]["denoise"] = params.strength
        wf["10"] = {"class_type": "LoadImage", "inputs": {"image": image_name}}
        wf["11"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["10", 0], "vae": ["4", 2]}}
        wf["3"]["inputs"]["latent_image"] = ["11", 0]
        del wf["5"]
        return wf

    def _inpaint_workflow(self, params: ImageParams, image_name: str, mask_name: str) -> dict:
        wf = self._txt2img_workflow(params)
        wf["10"] = {"class_type": "LoadImage", "inputs": {"image": image_name}}
        wf["12"] = {"class_type": "LoadImage", "inputs": {"image": mask_name}}
        wf["13"] = {"class_type": "VAEInpaint", "inputs": {
            "pixels": ["10", 0], "mask": ["12", 1], "vae": ["4", 2]}}
        wf["3"]["inputs"]["latent_image"] = ["13", 0]
        del wf["5"]
        return wf

    async def generate_img2img(self, params: ImageParams, image_bytes: bytes, mime: str) -> GeneratedImage:
        name = await self._upload_image(image_bytes, f"aether_src_{uuid.uuid4().hex}.png")
        started = time.monotonic()
        workflow = self._custom_workflow("img2img", params, source_image=name) or self._img2img_workflow(params, name)
        png = await self._queue_and_wait(workflow)
        duration = int((time.monotonic() - started) * 1000)
        return GeneratedImage(png_bytes=png, width=params.width, height=params.height,
                              seed=params.seed, duration_ms=duration)

    async def generate_inpaint(self, params: ImageParams, image_bytes: bytes,
                               mask_bytes: bytes, mime: str) -> GeneratedImage:
        img_name = await self._upload_image(image_bytes, f"aether_src_{uuid.uuid4().hex}.png")
        mask_name = await self._upload_image(mask_bytes, f"aether_mask_{uuid.uuid4().hex}.png")
        started = time.monotonic()
        workflow = self._custom_workflow("inpaint", params, source_image=img_name, mask_image=mask_name) or self._inpaint_workflow(params, img_name, mask_name)
        png = await self._queue_and_wait(workflow)
        duration = int((time.monotonic() - started) * 1000)
        return GeneratedImage(png_bytes=png, width=params.width, height=params.height,
                              seed=params.seed, duration_ms=duration)


class Krea2LocalProvider(DiffusersLocalProvider):
    """Krea 2 (Qwen3-VL text encoder + Qwen-Image VAE + Krea2 transformer).

    The read-only checkpoint ships as an `anima_models/` layout without a
    model_index.json, so the pipeline is assembled manually from components.
    Qwen3-VL as the text encoder means image+text conditioning is native.
    Loading is best-effort; failures surface a clear capability error.
    """

    name = "krea2_local"

    def __init__(self, model_path: str, device: str | None = None):
        super().__init__(model_path, device)
        self._assembled = False

    def capabilities(self) -> dict:
        return {
            "provider": self.name,
            "text_to_image": True,
            "image_to_image": True,   # native via Qwen3-VL encoder
            "inpainting": False,
            "negative_prompt": True,
            "seed": True, "steps": True, "cfg": True,
        }

    def _load(self):
        if self._pipe is not None:
            return self._pipe
        import torch

        device = self.device or ("cuda" if torch.cuda.is_available() else "cpu")
        dtype = torch.bfloat16 if device == "cuda" else torch.float32
        root = Path(self.model_path)
        te_dir = root / "anima_models" / "text_encoders" / "Qwen3-VL-4B-Instruct"
        vae_path = root / "anima_models" / "vae" / "qwen_image_vae.safetensors"
        transformer_path = root / "anima_models" / "transformers" / "raw.safetensors"
        for p in (te_dir, vae_path, transformer_path):
            if not p.exists():
                raise CapabilityUnsupportedError(f"Krea2 component missing: {p}")
        try:
            from diffusers import (
                AutoencoderKLQwenImage,
                FlowMatchEulerDiscreteScheduler,
                Krea2Pipeline,
                Krea2Transformer2DModel,
            )
            from transformers import AutoTokenizer, Qwen3VLModel

            tokenizer = AutoTokenizer.from_pretrained(str(te_dir))
            text_encoder = Qwen3VLModel.from_pretrained(str(te_dir), torch_dtype=dtype)
            vae = AutoencoderKLQwenImage.from_single_file(str(vae_path), torch_dtype=dtype)
            transformer = Krea2Transformer2DModel.from_single_file(str(transformer_path), torch_dtype=dtype)
            scheduler = FlowMatchEulerDiscreteScheduler()
            pipe = Krea2Pipeline(
                scheduler=scheduler, vae=vae, text_encoder=text_encoder,
                tokenizer=tokenizer, transformer=transformer,
            )
        except Exception as e:  # noqa: BLE001
            raise CapabilityUnsupportedError(f"Krea2 pipeline assembly failed: {e}") from e
        pipe = pipe.to(device)
        self._pipe = pipe
        self._assembled = True
        return pipe


_PROVIDER_CACHE: dict[str, ImageProvider] = {}


def build_image_provider(kind: str, model_ref: str, base_url: str = "", api_key: str = "",
                         options: dict | None = None) -> ImageProvider:
    # Local pipeline providers are cached so the (large) pipeline loads once
    # and stays resident across requests. Remote/stateless providers are cheap
    # and are built fresh.
    if kind == "diffusers_local":
        if not model_ref or not os.path.isdir(model_ref):
            raise CapabilityUnsupportedError(f"Diffusers model path not found: {model_ref or '(empty)'}")
        key = f"diffusers_local:{model_ref}"
        if key not in _PROVIDER_CACHE:
            _PROVIDER_CACHE[key] = DiffusersLocalProvider(model_ref)
        return _PROVIDER_CACHE[key]
    if kind == "krea2_local":
        if not model_ref or not os.path.isdir(model_ref):
            raise CapabilityUnsupportedError(f"Krea2 model path not found: {model_ref or '(empty)'}")
        key = f"krea2_local:{model_ref}"
        if key not in _PROVIDER_CACHE:
            _PROVIDER_CACHE[key] = Krea2LocalProvider(model_ref)
        return _PROVIDER_CACHE[key]
    if kind == "openai_images":
        if not base_url:
            raise CapabilityUnsupportedError("openai_images provider needs a base_url")
        return OpenAIImagesProvider(base_url, api_key=api_key, model_id=model_ref, options=options)
    if kind == "comfyui":
        if not base_url:
            raise CapabilityUnsupportedError("comfyui provider needs a base_url")
        return ComfyUIProvider(base_url, checkpoint=model_ref, api_key=api_key, options=options)
    if kind == "automatic1111":
        if not base_url:
            raise CapabilityUnsupportedError("automatic1111 provider needs a base_url")
        return Automatic1111Provider(base_url, api_key=api_key, options=options)
    if kind == "stability_api":
        if not base_url:
            raise CapabilityUnsupportedError("stability_api provider needs a base_url")
        return StabilityAIProvider(base_url, api_key=api_key, model_ref=model_ref, options=options)
    raise CapabilityUnsupportedError(f"Unknown image provider kind: {kind}")
