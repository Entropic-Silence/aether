from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..deps import get_current_user
from ..errors import NotFoundError, PermissionError_
from ..orm import Memory, User, UserSettings
from ..services.memory import get_user_settings
from ..services.features import feature_dependency

router = APIRouter(prefix="/memories", tags=["memory"], dependencies=[Depends(feature_dependency("memory"))])


class MemoryIn(BaseModel):
    content: str = Field(min_length=1, max_length=1000)
    category: str = "general"
    project_id: str | None = None


class MemoryPatch(BaseModel):
    content: str | None = None
    category: str | None = None
    enabled: bool | None = None


def _to_out(m: Memory) -> dict:
    return {
        "id": m.id, "kind": m.kind, "content": m.content, "category": m.category,
        "project_id": m.project_id, "source": m.source, "confidence": m.confidence,
        "enabled": m.enabled, "created_at": m.created_at, "updated_at": m.updated_at,
    }


@router.get("")
async def list_memories(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    rows = await db.execute(
        select(Memory).where(Memory.user_id == user.id).order_by(Memory.updated_at.desc()).limit(200)
    )
    return [_to_out(m) for m in rows.scalars().all()]


@router.post("", status_code=201)
async def create_memory(body: MemoryIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    m = Memory(user_id=user.id, kind="explicit", content=body.content,
               category=body.category, project_id=body.project_id, source="manual", confidence=1.0)
    db.add(m)
    await db.commit()
    await db.refresh(m)
    return _to_out(m)


@router.patch("/{memory_id}")
async def update_memory(memory_id: str, body: MemoryPatch,
                        db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    m = await db.get(Memory, memory_id)
    if not m or m.user_id != user.id:
        raise NotFoundError("Memory not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(m, k, v)
    await db.commit()
    await db.refresh(m)
    return _to_out(m)


@router.delete("/{memory_id}", status_code=204)
async def delete_memory(memory_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    m = await db.get(Memory, memory_id)
    if not m or m.user_id != user.id:
        raise NotFoundError("Memory not found")
    await db.delete(m)
    await db.commit()


@router.delete("", status_code=204)
async def clear_memories(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await db.execute(delete(Memory).where(Memory.user_id == user.id))
    await db.commit()


# --- User settings (custom instructions + memory toggles) ---


class UserSettingsIn(BaseModel):
    about_me: str | None = None
    response_style: str | None = None
    memory_enabled: bool | None = None
    memory_reference: bool | None = None
    memory_auto_capture: bool | None = None
    daily_message_limit: int | None = None
    daily_token_limit: int | None = None
    daily_image_limit: int | None = None
    daily_search_limit: int | None = None


class UserSettingsOut(BaseModel):
    about_me: str
    response_style: str
    memory_enabled: bool
    memory_reference: bool
    memory_auto_capture: bool
    daily_message_limit: int
    daily_token_limit: int
    daily_image_limit: int
    daily_search_limit: int


settings_router = APIRouter(prefix="/settings", tags=["settings"])


def _settings_out(s) -> UserSettingsOut:
    return UserSettingsOut(
        about_me=s.about_me, response_style=s.response_style,
        memory_enabled=s.memory_enabled, memory_reference=s.memory_reference,
        memory_auto_capture=s.memory_auto_capture,
        daily_message_limit=s.daily_message_limit or 0,
        daily_token_limit=s.daily_token_limit or 0,
        daily_image_limit=s.daily_image_limit or 0,
        daily_search_limit=s.daily_search_limit or 0,
    )


@settings_router.get("/me", response_model=UserSettingsOut)
async def get_my_settings(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    s = await get_user_settings(db, user.id)
    return _settings_out(s)


@settings_router.patch("/me", response_model=UserSettingsOut)
async def patch_my_settings(body: UserSettingsIn, db: AsyncSession = Depends(get_db),
                            user: User = Depends(get_current_user)):
    from ..services.features import ensure_feature

    fields = body.model_fields_set
    if fields & {"about_me", "response_style"}:
        await ensure_feature(db, "custom_instructions", user)
    if fields & {"memory_enabled", "memory_reference", "memory_auto_capture"}:
        await ensure_feature(db, "memory", user)
    s = await get_user_settings(db, user.id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    await db.commit()
    await db.refresh(s)
    return _settings_out(s)
