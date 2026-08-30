from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..deps import require_admin
from ..errors import NotFoundError, ValidationError_
from ..orm import SystemPrompt, User
from .deps_helper import workspace_id_for

router = APIRouter(prefix="/system-prompts", tags=["prompts"])


class PromptIn(BaseModel):
    name: str = "default"
    text: str = Field(default="", max_length=20000)


class PromptPatch(BaseModel):
    text: str | None = None
    status: str | None = None  # draft|published


def _to_out(p: SystemPrompt) -> dict:
    return {"id": p.id, "name": p.name, "text": p.text, "version": p.version,
            "status": p.status, "is_active": p.is_active, "created_at": p.created_at}


@router.get("")
async def list_prompts(db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    rows = await db.execute(select(SystemPrompt).order_by(SystemPrompt.created_at.desc()).limit(100))
    return [_to_out(p) for p in rows.scalars().all()]


@router.post("", status_code=201)
async def create_prompt(body: PromptIn, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    ws_id = await workspace_id_for(db)
    last_version = await db.scalar(
        select(SystemPrompt.version).where(SystemPrompt.workspace_id == ws_id, SystemPrompt.name == body.name)
        .order_by(SystemPrompt.version.desc()).limit(1)
    )
    p = SystemPrompt(workspace_id=ws_id, name=body.name, text=body.text,
                     version=(last_version or 0) + 1, status="draft")
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return _to_out(p)


@router.patch("/{prompt_id}")
async def update_prompt(prompt_id: str, body: PromptPatch,
                        db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    p = await db.get(SystemPrompt, prompt_id)
    if not p:
        raise NotFoundError("Prompt not found")
    if body.text is not None:
        p.text = body.text
    if body.status is not None:
        if body.status not in ("draft", "published"):
            raise ValidationError_("status must be draft or published")
        p.status = body.status
    await db.commit()
    await db.refresh(p)
    return _to_out(p)


@router.post("/{prompt_id}/activate")
async def activate_prompt(prompt_id: str, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    p = await db.get(SystemPrompt, prompt_id)
    if not p:
        raise NotFoundError("Prompt not found")
    if p.status != "published":
        raise ValidationError_("Only published prompts can be activated")
    rows = await db.execute(select(SystemPrompt).where(SystemPrompt.workspace_id == p.workspace_id))
    for other in rows.scalars().all():
        other.is_active = (other.id == p.id)
    await db.commit()
    return {"ok": True, "active_id": p.id}


@router.delete("/{prompt_id}", status_code=204)
async def delete_prompt(prompt_id: str, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    p = await db.get(SystemPrompt, prompt_id)
    if not p:
        raise NotFoundError("Prompt not found")
    if p.is_active:
        raise ValidationError_("Cannot delete the active prompt; activate another first")
    await db.delete(p)
    await db.commit()


async def get_active_system_prompt(db: AsyncSession, workspace_id: str) -> str | None:
    row = await db.scalar(
        select(SystemPrompt).where(SystemPrompt.workspace_id == workspace_id, SystemPrompt.is_active.is_(True)).limit(1)
    )
    return row.text if row and row.text.strip() else None
