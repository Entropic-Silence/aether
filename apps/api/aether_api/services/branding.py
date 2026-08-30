from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..orm import Setting

BRANDING_KEY = "branding"


async def get_branding(db: AsyncSession) -> dict:
    settings = get_settings()
    default = {
        "product_name": settings.default_product_name,
        "logo_url": None,
        "accent_color": settings.default_accent,
        "icon_set": "lucide",
        "tagline": "",
    }
    row = await db.get(Setting, BRANDING_KEY)
    if row and isinstance(row.value, dict):
        default.update(row.value)
    return default


async def update_branding(db: AsyncSession, patch: dict) -> dict:
    current = await get_branding(db)
    current.update({k: v for k, v in patch.items() if v is not None})
    row = await db.get(Setting, BRANDING_KEY)
    if row is None:
        row = Setting(key=BRANDING_KEY, value=current)
        db.add(row)
    else:
        row.value = current
    await db.commit()
    return current
