from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..db import get_db
from ..deps import get_current_user, require_admin
from ..errors import NotFoundError, PermissionError_, ValidationError_
from ..orm import Conversation, Message, Setting, Share, User
from .deps_helper import workspace_id_for

router = APIRouter(prefix="/shares", tags=["shares"])

SHARE_SETTINGS_KEY = "sharing"

MODES = {"private", "link", "workspace", "public"}


class ShareIn(BaseModel):
    conversation_id: str
    mode: str = "link"


def _conversation_payload(conv: Conversation) -> dict:
    messages = []
    for m in sorted(conv.messages, key=lambda x: x.created_at):
        messages.append({
            "id": m.id, "role": m.role,
            "blocks": [{"type": b.type, "data": b.data} for b in sorted(m.blocks, key=lambda b: b.seq)],
        })
    return {"id": conv.id, "title": conv.title, "messages": messages}


async def _public_sharing_enabled(db: AsyncSession) -> bool:
    row = await db.get(Setting, SHARE_SETTINGS_KEY)
    value = row.value if row and isinstance(row.value, dict) else {}
    return value.get("public_enabled", True)


@router.post("", status_code=201)
async def create_share(body: ShareIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    if body.mode not in MODES:
        raise ValidationError_(f"mode must be one of {sorted(MODES)}")
    if body.mode == "public" and not await _public_sharing_enabled(db):
        raise PermissionError_("Public sharing is disabled by the administrator")
    conv = await db.get(Conversation, body.conversation_id)
    if not conv or conv.user_id != user.id:
        raise NotFoundError("Conversation not found")
    existing = await db.scalar(select(Share).where(Share.conversation_id == conv.id))
    if existing:
        existing.mode = body.mode
        await db.commit()
        await db.refresh(existing)
        return {"id": existing.id, "mode": existing.mode, "token": existing.token,
                "url": f"/share/{existing.token}"}
    share = Share(conversation_id=conv.id, user_id=user.id, mode=body.mode,
                  token=secrets.token_urlsafe(24))
    db.add(share)
    await db.commit()
    await db.refresh(share)
    return {"id": share.id, "mode": share.mode, "token": share.token, "url": f"/share/{share.token}"}


@router.get("")
async def list_my_shares(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    rows = await db.execute(select(Share).where(Share.user_id == user.id).order_by(Share.created_at.desc()))
    return [{"id": s.id, "conversation_id": s.conversation_id, "mode": s.mode,
             "url": f"/share/{s.token}", "created_at": s.created_at} for s in rows.scalars().all()]


@router.delete("/{share_id}", status_code=204)
async def delete_share(share_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    share = await db.get(Share, share_id)
    if not share or share.user_id != user.id:
        raise NotFoundError("Share not found")
    await db.delete(share)
    await db.commit()


@router.get("/public/{token}")
async def get_shared_conversation(token: str, db: AsyncSession = Depends(get_db)):
    """Public share access: no auth required, respects the admin kill-switch."""
    share = await db.scalar(select(Share).where(Share.token == token))
    if not share:
        raise NotFoundError("Share not found")
    if share.mode == "private":
        raise NotFoundError("Share not found")
    if share.mode == "public" and not await _public_sharing_enabled(db):
        raise PermissionError_("Public sharing is disabled")
    conv = await db.scalar(
        select(Conversation)
        .options(selectinload(Conversation.messages).selectinload(Message.blocks))
        .where(Conversation.id == share.conversation_id)
    )
    if not conv:
        raise NotFoundError("Conversation not found")
    return _conversation_payload(conv)


class SharingSettingsIn(BaseModel):
    public_enabled: bool


@router.get("/settings")
async def sharing_settings(db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    return {"public_enabled": await _public_sharing_enabled(db)}


@router.patch("/settings")
async def patch_sharing_settings(body: SharingSettingsIn, db: AsyncSession = Depends(get_db),
                                 _: User = Depends(require_admin)):
    row = await db.get(Setting, SHARE_SETTINGS_KEY)
    value = {"public_enabled": body.public_enabled}
    if row is None:
        db.add(Setting(key=SHARE_SETTINGS_KEY, value=value))
    else:
        row.value = value
    await db.commit()
    return value
