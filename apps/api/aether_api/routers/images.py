from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
import time

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..deps import get_current_user, require_admin
from ..errors import ApiError, CapabilityUnsupportedError, NotFoundError, ValidationError_
from ..orm import Conversation, File, ImageModel, Message, MessageBlock, Model, Provider, User
from ..security import decrypt_secret, encrypt_secret
from ..services.imagegen import ImageParams, build_image_provider
from .deps_helper import workspace_id_for

router = APIRouter(prefix="/images", tags=["images"])


class ImageModelIn(BaseModel):
    provider_kind: str = "diffusers_local"
    name: str = Field(min_length=1, max_length=200)
    model_ref: str = ""
    base_url: str = ""
    api_key: str = ""
    capabilities: dict = {}
    defaults: dict = {}
    limits: dict = {}
    skill_text: str = ""
    enabled: bool = True
    is_default: bool = False


class ImageModelPatch(BaseModel):
    provider_kind: str | None = None
    name: str | None = None
    model_ref: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    capabilities: dict | None = None
    defaults: dict | None = None
    limits: dict | None = None
    skill_text: str | None = None
    enabled: bool | None = None
    is_default: bool | None = None


def _effective_caps(m: ImageModel) -> dict:
    """Merge the provider's real runtime capabilities with admin overrides."""
    try:
        provider = build_image_provider(
            m.provider_kind, m.model_ref, base_url=m.base_url,
            api_key=decrypt_secret(m.api_key_enc),
            options=m.defaults or {},
        )
        caps = dict(provider.capabilities())
    except Exception:  # noqa: BLE001
        caps = {"text_to_image": True}
    caps.update(m.capabilities or {})
    caps.pop("provider", None)
    return caps


def _to_out(m: ImageModel) -> dict:
    return {
        "id": m.id,
        "provider_kind": m.provider_kind,
        "name": m.name,
        "model_ref": m.model_ref,
        "base_url": m.base_url,
        "has_api_key": bool(m.api_key_enc),
        "capabilities": _effective_caps(m),
        "defaults": m.defaults or {},
        "limits": m.limits or {},
        "skill_text": m.skill_text,
        "enabled": m.enabled,
        "is_default": m.is_default,
        "created_at": m.created_at,
    }


@router.get("/models")
async def list_image_models(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    rows = await db.execute(select(ImageModel).where(ImageModel.enabled.is_(True)).order_by(ImageModel.created_at))
    return [_to_out(m) for m in rows.scalars().all()]


@router.post("/models", status_code=201)
async def create_image_model(body: ImageModelIn, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    m = ImageModel(
        workspace_id=await workspace_id_for(db),
        provider_kind=body.provider_kind,
        name=body.name,
        model_ref=body.model_ref,
        base_url=body.base_url,
        api_key_enc=encrypt_secret(body.api_key),
        capabilities=body.capabilities,
        defaults=body.defaults,
        limits=body.limits,
        skill_text=body.skill_text,
        enabled=body.enabled,
        is_default=body.is_default,
    )
    db.add(m)
    await db.commit()
    await db.refresh(m)
    return _to_out(m)


@router.patch("/models/{model_id}")
async def update_image_model(model_id: str, body: ImageModelPatch, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    m = await db.get(ImageModel, model_id)
    if not m:
        raise NotFoundError("Image model not found")
    data = body.model_dump(exclude_unset=True)
    if "api_key" in data:
        key = data.pop("api_key")
        if key:
            m.api_key_enc = encrypt_secret(key)
    for k, v in data.items():
        setattr(m, k, v)
    await db.commit()
    await db.refresh(m)
    return _to_out(m)


@router.delete("/models/{model_id}", status_code=204)
async def delete_image_model(model_id: str, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    m = await db.get(ImageModel, model_id)
    if not m:
        raise NotFoundError("Image model not found")
    await db.delete(m)
    await db.commit()


class GenerateIn(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    model_id: str | None = None
    width: int | None = None
    height: int | None = None
    steps: int | None = None
    cfg: float | None = None
    seed: int | None = None
    negative_prompt: str | None = None
    optimize: bool = True
    mode: str = "txt2img"  # txt2img | img2img | inpaint
    source_file_id: str | None = None
    mask_file_id: str | None = None
    strength: float = 0.75
    aspect_ratio: str | None = None
    admin_test: bool = False


class OptimizePromptIn(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    model_id: str | None = None
    optimizer_model_id: str | None = None
    aspect_ratio: str | None = None


class ImageIntentIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    model_id: str | None = None


ASPECT_RATIOS: dict[str, tuple[int, int]] = {
    "1:1": (1, 1),
    "16:9": (16, 9),
    "9:16": (9, 16),
    "3:2": (3, 2),
    "2:3": (2, 3),
    "4:3": (4, 3),
    "3:4": (3, 4),
    "5:4": (5, 4),
    "4:5": (4, 5),
    "21:9": (21, 9),
    "9:21": (9, 21),
}


def _normalize_aspect_ratio(value: str | None) -> str | None:
    if not value or value.strip().lower() in {"auto", "automatic", "智能", "自动"}:
        return None
    text = value.strip().lower().replace("：", ":").replace("比", ":").replace("×", ":").replace("x", ":")
    match = re.fullmatch(r"\s*(\d{1,2})\s*[:/]\s*(\d{1,2})\s*", text)
    if not match:
        aliases = {
            "square": "1:1", "landscape": "16:9", "portrait": "9:16",
            "横版": "16:9", "横屏": "16:9", "竖版": "9:16", "竖屏": "9:16",
        }
        return aliases.get(text)
    width, height = int(match.group(1)), int(match.group(2))
    if width <= 0 or height <= 0:
        return None
    divisor = math.gcd(width, height)
    normalized = f"{width // divisor}:{height // divisor}"
    return normalized if normalized in ASPECT_RATIOS else None


def _prompt_aspect_ratio(prompt: str) -> str | None:
    match = re.search(r"(?<!\d)(\d{1,2})\s*(?:[:：比x×/])\s*(\d{1,2})(?!\d)", prompt.lower())
    if match:
        normalized = _normalize_aspect_ratio(f"{match.group(1)}:{match.group(2)}")
        if normalized:
            return normalized
    text = prompt.lower()
    if re.search(r"(?:全身像|全身照|全身人像|人物全身|手机壁纸|手机竖屏|竖版海报|full[- ]?body|phone wallpaper)", text):
        return "9:16"
    if re.search(r"(?:超宽|宽银幕|电影横幅|ultrawide|cinematic banner)", text):
        return "21:9"
    if re.search(r"(?:横屏|横版|桌面壁纸|风景照|landscape|desktop wallpaper|wide shot)", text):
        return "16:9"
    if re.search(r"(?:头像|方形图标|profile picture|avatar|square icon)", text):
        return "1:1"
    if re.search(r"(?:证件照|半身人像|portrait photo|headshot)", text):
        return "4:5"
    return None


def _fallback_aspect_ratio(prompt: str) -> str:
    return _prompt_aspect_ratio(prompt) or "1:1"


def _dimensions_for_aspect(
    aspect_ratio: str,
    default_width: int,
    default_height: int,
    max_width: int,
    max_height: int,
) -> tuple[int, int]:
    """Choose model-safe multiples of eight while preserving the requested ratio."""
    ratio = ASPECT_RATIOS.get(aspect_ratio)
    if not ratio:
        return (
            int(min(max(default_width, 256), max_width)),
            int(min(max(default_height, 256), max_height)),
        )
    width_units, height_units = ratio
    divisor = math.gcd(width_units, height_units)
    width_units //= divisor
    height_units //= divisor
    short_units = min(width_units, height_units)
    target_short = max(256, min(default_width, default_height))
    unit = max(8, math.ceil((target_short / short_units) / 8) * 8)
    max_unit = max(1, min(max_width // width_units, max_height // height_units))
    unit = min(unit, max_unit)
    unit = max(1, (unit // 8) * 8)
    min_unit = math.ceil(256 / short_units)
    if max_unit >= min_unit:
        unit = max(unit, min_unit)
    return width_units * unit, height_units * unit


def _fallback_image_intent(content: str) -> bool:
    """Conservative fallback for explicit requests when the classifier is unavailable."""
    text = content.strip().lower()
    if re.search(r"(?:提示词|prompt|描述词|怎么写|如何写|教程|方法|分析|解释)", text):
        return False
    zh_action = r"(?:生成|创建|制作|画|绘制|设计)(?:给我|一下|一张|一个|一幅|些)?"
    zh_target = r"(?:图片|图像|照片|海报|插画|头像|壁纸|logo|角色图|一张|一幅)"
    if re.search(zh_action + r".{0,24}" + zh_target, text) or re.search(r"(?:生成|创建|制作)(?:一张|一幅)", text):
        return True
    return bool(re.search(r"\b(?:generate|create|draw|paint|make)\b.{0,40}\b(?:image|picture|photo|illustration|poster|artwork)\b", text))


def _is_prompt_only_request(content: str) -> bool:
    text = content.strip().lower()
    return bool(re.search(
        r"(?:图片|图像|绘画|生图|image|picture).{0,18}(?:提示词|prompt|描述词)"
        r"|(?:提示词|prompt|描述词).{0,18}(?:图片|图像|绘画|生图|image|picture)",
        text,
    ))


@router.post("/intents/classify")
async def classify_image_intent(body: ImageIntentIn, db: AsyncSession = Depends(get_db),
                                user: User = Depends(get_current_user)):
    """Let the selected language model decide whether the user wants an image now."""
    from ..adapters import build_adapter
    from ..services.features import ensure_feature

    await ensure_feature(db, "image_generation", user)

    # These two intents differ by only a few Chinese characters and small
    # classifiers frequently confuse them. Apply precise guards before the
    # semantic classifier, leaving genuinely ambiguous requests to the model.
    if _is_prompt_only_request(body.content):
        return {"image_request": False, "source": "explicit_prompt_request"}
    if _fallback_image_intent(body.content):
        return {"image_request": True, "source": "explicit_image_request"}

    model = await db.get(Model, body.model_id) if body.model_id else None
    if not model or not model.enabled:
        model = await db.scalar(
            select(Model).where(Model.enabled.is_(True), Model.is_default.is_(True)).limit(1)
        )
    if not model:
        return {"image_request": False, "source": "unavailable"}
    provider = await db.get(Provider, model.provider_id)
    if not provider or not provider.enabled:
        return {"image_request": False, "source": "unavailable"}
    adapter = build_adapter(provider)
    try:
        response = await asyncio.wait_for(adapter.chat(
            [
                {"role": "system", "content": (
                    "Classify the user's immediate intent. Return ONLY JSON: "
                    "{\"image_request\": boolean}. Set true only when they want the assistant "
                    "to create or edit an actual image now. Set false when they ask for an image "
                    "prompt, instructions, analysis, translation, or discussion about images. "
                    "Examples: '生成一张小猫图片' => true; '生成一张小猫图片的提示词' => false."
                )},
                {"role": "user", "content": body.content},
            ],
            model_id=model.model_id,
            generation={"max_tokens": 40, "temperature": 0},
        ), timeout=20)
        message = ((response.get("choices") or [{}])[0].get("message") or {})
        content = message.get("content", "") or message.get("reasoning_content", "")
        if isinstance(content, list):
            content = "".join(str(p.get("text", "")) for p in content if isinstance(p, dict))
        text = str(content or "")
        obj = json.loads(text[text.index("{"):text.rindex("}") + 1])
        return {"image_request": obj.get("image_request") is True, "source": "model"}
    except Exception:  # noqa: BLE001
        return {"image_request": _fallback_image_intent(body.content), "source": "fallback"}
    finally:
        await adapter.aclose()


async def _resolve_image_model(db: AsyncSession, model_id: str | None) -> ImageModel:
    if model_id:
        m = await db.get(ImageModel, model_id)
        if not m or not m.enabled:
            raise NotFoundError("Image model not available")
        return m
    m = await db.scalar(select(ImageModel).where(ImageModel.enabled.is_(True), ImageModel.is_default.is_(True)).limit(1))
    if not m:
        m = await db.scalar(select(ImageModel).where(ImageModel.enabled.is_(True)).limit(1))
    if not m:
        raise NotFoundError("No image model configured. Admin → Images.")
    return m


async def _optimize_prompt(db: AsyncSession, image_model: ImageModel, user_prompt: str,
                           optimizer_model_id: str | None = None,
                           requested_aspect_ratio: str | None = None) -> tuple[str, str, str]:
    """Skill-guided prompt optimization with capability-driven model fallback.

    Falls back to the raw prompt when no chat model is available — never fakes.
    """
    from ..adapters import build_adapter

    skill = image_model.skill_text.strip()
    explicit_aspect = _normalize_aspect_ratio(requested_aspect_ratio) or _prompt_aspect_ratio(user_prompt)
    allowed_ratios = ", ".join(ASPECT_RATIOS)
    system = (
        "You rewrite image-generation requests into optimized prompts. "
        "Return ONLY JSON: {\"prompt\": string, \"negative_prompt\": string, \"aspect_ratio\": string}. "
        "The prompt should be detailed, concrete and in English. "
        f"aspect_ratio must be one of: {allowed_ratios}. Respect an explicit ratio in the request. "
        "Otherwise choose composition-aware framing: use 9:16 for a full-body person or phone wallpaper, "
        "16:9 for wide landscapes, 1:1 for avatars, and a suitable portrait or landscape ratio for other scenes. "
        + (f"The user explicitly selected {explicit_aspect}; return that exact aspect_ratio. " if explicit_aspect else "")
        + (f"\n\nModel skill guidance:\n{skill}" if skill else "")
    )
    candidates: list[Model] = []
    if optimizer_model_id:
        requested = await db.get(Model, optimizer_model_id)
        if requested and requested.enabled:
            candidates.append(requested)
    rows = await db.execute(
        select(Model).where(Model.enabled.is_(True)).order_by(Model.is_default.desc(), Model.created_at)
    )
    candidates.extend(model for model in rows.scalars().all() if all(model.id != c.id for c in candidates))

    for model in candidates[:3]:
        provider = await db.get(Provider, model.provider_id)
        if not provider or not provider.enabled:
            continue
        adapter = build_adapter(provider)
        try:
            resp = await asyncio.wait_for(adapter.chat(
                [{"role": "system", "content": system},
                 {"role": "user", "content": user_prompt}],
                model_id=model.model_id,
                generation={"max_tokens": 500, "temperature": 0.35},
            ), timeout=25)
            content = ((resp.get("choices") or [{}])[0].get("message") or {}).get("content", "")
            if isinstance(content, list):
                text = "".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
            else:
                text = str(content or "")
            start = text.index("{")
            end = text.rindex("}") + 1
            obj = json.loads(text[start:end])
            opt = str(obj.get("prompt") or "").strip()
            neg = str(obj.get("negative_prompt") or "").strip()
            aspect = explicit_aspect or _normalize_aspect_ratio(str(obj.get("aspect_ratio") or "")) or _fallback_aspect_ratio(user_prompt)
            if opt and (opt != user_prompt or neg):
                return opt[:2000], neg[:500], aspect
            if opt:
                return opt[:2000], neg[:500], aspect
        except Exception:  # noqa: BLE001
            continue
        finally:
            await adapter.aclose()
    return user_prompt, "", explicit_aspect or _fallback_aspect_ratio(user_prompt)


@router.post("/prompts/optimize")
async def optimize_image_prompt(body: OptimizePromptIn, db: AsyncSession = Depends(get_db),
                                user: User = Depends(get_current_user)):
    """Expose prompt refinement as its own visible stage before image generation."""
    from ..services.features import ensure_feature

    await ensure_feature(db, "image_generation", user)
    image_model = await _resolve_image_model(db, body.model_id)
    prompt, negative, aspect_ratio = await _optimize_prompt(
        db, image_model, body.prompt, body.optimizer_model_id, body.aspect_ratio,
    )
    return {
        "original_prompt": body.prompt,
        "prompt": prompt,
        "negative_prompt": negative,
        "optimized": prompt != body.prompt or bool(negative),
        "aspect_ratio": aspect_ratio,
        "model": {"id": image_model.id, "name": image_model.name},
    }


def _clamp(value, lo, hi, default):
    if value is None:
        return default
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return int(min(max(v, lo), hi))


@router.post("/generations", status_code=201)
async def generate_image(body: GenerateIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    from ..services.quota import check_image_quota
    from ..services.features import ensure_feature

    if not (body.admin_test and user.role in ("owner", "admin")):
        await ensure_feature(db, "image_generation", user)
    await check_image_quota(db, user.id)
    image_model = await _resolve_image_model(db, body.model_id)
    defaults = image_model.defaults or {}
    limits = image_model.limits or {}
    max_width = int(limits.get("max_width", 1024))
    max_height = int(limits.get("max_height", 1024))
    default_width = int(defaults.get("width", 512))
    default_height = int(defaults.get("height", 512))
    steps = _clamp(body.steps, 1, int(limits.get("max_steps", 60)), int(defaults.get("steps", 25)))
    cfg = float(min(max(body.cfg if body.cfg is not None else float(defaults.get("cfg", 7.0)), 1.0), 20.0))

    if body.optimize:
        prompt, negative, aspect_ratio = await _optimize_prompt(
            db, image_model, body.prompt, requested_aspect_ratio=body.aspect_ratio,
        )
    else:
        prompt, negative = body.prompt, body.negative_prompt or ""
        aspect_ratio = (
            _normalize_aspect_ratio(body.aspect_ratio)
            or _prompt_aspect_ratio(body.prompt)
            or _fallback_aspect_ratio(body.prompt)
        )
    if body.negative_prompt:
        negative = body.negative_prompt

    if body.width is None and body.height is None:
        width, height = _dimensions_for_aspect(
            aspect_ratio, default_width, default_height, max_width, max_height,
        )
    else:
        width = _clamp(body.width, 256, max_width, default_width)
        height = _clamp(body.height, 256, max_height, default_height)

    provider = build_image_provider(
        image_model.provider_kind, image_model.model_ref,
        base_url=image_model.base_url, api_key=decrypt_secret(image_model.api_key_enc),
        options=defaults,
    )
    params = ImageParams(prompt=prompt, negative_prompt=negative, width=width, height=height,
                         steps=steps, cfg=cfg, seed=body.seed, strength=body.strength)

    from ..services.storage import get_storage

    try:
        if body.mode == "img2img":
            if not body.source_file_id:
                raise CapabilityUnsupportedError("img2img requires source_file_id")
            if not provider.capabilities().get("image_to_image"):
                raise CapabilityUnsupportedError("This image model does not support image-to-image")
            src = await db.get(File, body.source_file_id)
            if not src:
                raise NotFoundError("Source image not found")
            src_bytes = await get_storage().get(src.storage_key)
            result = await provider.generate_img2img(params, src_bytes, src.mime)
        elif body.mode == "inpaint":
            if not body.source_file_id or not body.mask_file_id:
                raise CapabilityUnsupportedError("inpaint requires source_file_id and mask_file_id")
            if not provider.capabilities().get("inpainting"):
                raise CapabilityUnsupportedError("This image model does not support inpainting")
            src = await db.get(File, body.source_file_id)
            mask = await db.get(File, body.mask_file_id)
            if not src or not mask:
                raise NotFoundError("Source or mask image not found")
            src_bytes = await get_storage().get(src.storage_key)
            mask_bytes = await get_storage().get(mask.storage_key)
            result = await provider.generate_inpaint(params, src_bytes, mask_bytes, src.mime)
        else:
            result = await provider.generate(params)
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        raise CapabilityUnsupportedError(f"Image generation failed: {e}") from e

    sha = hashlib.sha256(result.png_bytes).hexdigest()
    f = File(
        workspace_id=image_model.workspace_id,
        user_id=user.id,
        name=f"generated-{int(time.time())}.png",
        mime="image/png",
        kind="image",
        size=len(result.png_bytes),
        sha256=sha,
        storage_key=f"{user.id}/{sha[:2]}/{sha}",
        status="extracted",
        extraction={"text": "", "text_chars": 0, "pages": 0,
                    "notices": ["Generated image"], "indexed_chunks": 0},
    )
    db.add(f)
    await db.flush()

    await get_storage().put(f.storage_key, result.png_bytes)
    await db.commit()
    await db.refresh(f)

    return {
        "file_id": f.id,
        "url": f"/api/v1/files/{f.id}/download",
        "width": result.width,
        "height": result.height,
        "seed": result.seed,
        "duration_ms": result.duration_ms,
        "prompt_used": prompt,
        "negative_prompt_used": negative,
        "optimized": body.optimize and (prompt != body.prompt or bool(negative)),
        "aspect_ratio": aspect_ratio,
        "mode": body.mode,
        "model": {"id": image_model.id, "name": image_model.name},
    }


class ChatImageIn(BaseModel):
    file_id: str
    prompt: str = ""
    prompt_used: str = ""
    negative_prompt_used: str = ""
    model_name: str = ""
    aspect_ratio: str = ""
    width: int | None = None
    height: int | None = None
    parent_user_message_id: str | None = None


@router.post("/conversations/{conversation_id}/message", status_code=201)
async def attach_generated_image_to_chat(conversation_id: str, body: ChatImageIn,
                                         db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Record a generated image in a conversation as a user prompt + assistant image."""
    from ..services.features import ensure_feature

    await ensure_feature(db, "image_generation", user)
    conv = await db.get(Conversation, conversation_id)
    if not conv or (conv.user_id != user.id and user.role not in ("admin", "owner")):
        raise NotFoundError("Conversation not found")
    f = await db.get(File, body.file_id)
    if not f or (f.user_id != user.id and user.role not in ("admin", "owner")):
        raise NotFoundError("Image not found")

    user_msg = None
    if body.parent_user_message_id:
        candidate = await db.get(Message, body.parent_user_message_id)
        if candidate and candidate.conversation_id == conv.id and candidate.role == "user":
            user_msg = candidate
    if user_msg is None:
        parent = None
        if conv.current_leaf_id:
            cand = await db.get(Message, conv.current_leaf_id)
            if cand and cand.conversation_id == conv.id:
                parent = cand
        user_msg = Message(conversation_id=conv.id, parent_id=parent.id if parent else None, role="user")
        db.add(user_msg)
        await db.flush()
        db.add(MessageBlock(message_id=user_msg.id, seq=0, type="text",
                            data={"text": body.prompt or "Create an image"}))
    assistant_msg = Message(conversation_id=conv.id, parent_id=user_msg.id, role="assistant", status="completed")
    db.add(assistant_msg)
    await db.flush()
    db.add(MessageBlock(message_id=assistant_msg.id, seq=0, type="image",
                        data={"file_id": f.id, "name": f.name, "mime": f.mime,
                              "url": f"/api/v1/files/{f.id}/download", "generated": True,
                              "prompt_used": body.prompt_used or body.prompt,
                              "negative_prompt_used": body.negative_prompt_used,
                              "model_name": body.model_name,
                              "aspect_ratio": body.aspect_ratio,
                              "width": body.width,
                              "height": body.height,
                              "refined": bool(body.prompt_used and body.prompt_used != body.prompt)}))
    conv.current_leaf_id = assistant_msg.id
    await db.commit()
    return {"ok": True, "user_message_id": user_msg.id, "assistant_message_id": assistant_msg.id}
