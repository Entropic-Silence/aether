from __future__ import annotations

import base64

from sqlalchemy.ext.asyncio import AsyncSession

from ..adapters import build_adapter
from ..errors import CapabilityUnsupportedError
from ..orm import Model, Provider, Setting

VISION_KEY = "vision_fallback"


async def get_vision_fallback_model(db: AsyncSession) -> tuple[Model, Provider] | None:
    row = await db.get(Setting, VISION_KEY)
    model_pk = (row.value or {}).get("model_id") if row else None
    if not model_pk:
        return None
    model = await db.get(Model, model_pk)
    if not model or not model.enabled or model.effective_caps().get("image_input") is not True:
        return None
    provider = await db.get(Provider, model.provider_id)
    if not provider or not provider.enabled:
        return None
    return model, provider


async def set_vision_fallback_model(db: AsyncSession, model_id: str | None) -> dict:
    row = await db.get(Setting, VISION_KEY)
    value = {"model_id": model_id}
    if row is None:
        db.add(Setting(key=VISION_KEY, value=value))
    else:
        row.value = value
    await db.commit()
    return value


async def describe_image(db: AsyncSession, image_bytes: bytes, mime: str) -> tuple[str, str]:
    """Vision fallback chain: image -> vision model -> text description.

    Raises CapabilityUnsupportedError when no vision fallback is configured.
    """
    pair = await get_vision_fallback_model(db)
    if not pair:
        raise CapabilityUnsupportedError(
            "The selected model cannot read images and no vision fallback model is configured."
        )
    model, provider = pair
    data_url = f"data:{mime};base64,{base64.b64encode(image_bytes).decode()}"
    adapter = build_adapter(provider)
    try:
        resp = await adapter.chat(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text",
                         "text": "Describe this image in thorough detail for someone who cannot see it. "
                                 "Cover subject, text, layout, charts and notable details."},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            model_id=model.model_id,
            generation={"max_tokens": 2048},
        )
    finally:
        await adapter.aclose()
    choice = (resp.get("choices") or [{}])[0]
    description = ((choice.get("message") or {}).get("content") or "").strip()
    if not description:
        raise CapabilityUnsupportedError("Vision fallback returned no description")
    return description, model.display_name
