from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..deps import get_current_user, require_admin
from ..orm import Message, Model, UsageEvent, User
from ..services.quota import quota_status

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("/me")
async def my_usage(days: int = 7, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    days = max(1, min(days, 90))
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = await db.execute(
        select(UsageEvent).where(UsageEvent.user_id == user.id, UsageEvent.created_at >= since)
    )
    events = rows.scalars().all()
    by_model: dict[str, dict] = {}
    for e in events:
        key = e.model_id or "unknown"
        slot = by_model.setdefault(key, {"requests": 0, "input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0})
        slot["requests"] += 1
        slot["input_tokens"] += e.input_tokens
        slot["output_tokens"] += e.output_tokens
        slot["reasoning_tokens"] += e.reasoning_tokens
    total = {
        "requests": len(events),
        "input_tokens": sum(e.input_tokens for e in events),
        "output_tokens": sum(e.output_tokens for e in events),
        "reasoning_tokens": sum(e.reasoning_tokens for e in events),
    }
    return {"window_days": days, "total": total, "by_model": by_model,
            "quota": await quota_status(db, user.id)}


@router.get("/dashboard")
async def dashboard(days: int = 1, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    days = max(1, min(days, 90))
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = await db.execute(select(UsageEvent).where(UsageEvent.created_at >= since))
    events = rows.scalars().all()
    models = {m.id: m.display_name for m in (await db.execute(select(Model))).scalars().all()}
    by_model: dict[str, dict] = {}
    for e in events:
        key = models.get(e.model_id, e.model_id or "unknown")
        slot = by_model.setdefault(key, {"requests": 0, "input_tokens": 0, "output_tokens": 0})
        slot["requests"] += 1
        slot["input_tokens"] += e.input_tokens
        slot["output_tokens"] += e.output_tokens
    users_today = len({e.user_id for e in events})
    return {
        "window_days": days,
        "requests": len(events),
        "active_users": users_today,
        "input_tokens": sum(e.input_tokens for e in events),
        "output_tokens": sum(e.output_tokens for e in events),
        "errors": sum(1 for e in events if e.status == "failed"),
        "by_model": by_model,
    }
