from __future__ import annotations

from datetime import datetime, time as dtime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..errors import ApiError
from ..orm import Conversation, File, Message, MessageBlock, UsageEvent, UserSettings


class QuotaExceededError(ApiError):
    code = "QUOTA_EXCEEDED"
    status_code = 429
    retryable = False


def _today_range() -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    start = datetime.combine(now.date(), dtime.min, tzinfo=timezone.utc)
    return start, now


async def _user_quota(db: AsyncSession, user_id: str) -> UserSettings:
    s = await db.get(UserSettings, user_id)
    return s  # may be None -> unlimited


async def _count_today_messages(db: AsyncSession, user_id: str) -> int:
    start, now = _today_range()
    n = await db.scalar(
        select(func.count(Message.id))
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(Message.role == "user", Message.created_at >= start, Message.created_at <= now,
               Conversation.user_id == user_id)
    )
    return int(n or 0)


async def _count_today_tokens(db: AsyncSession, user_id: str) -> int:
    start, now = _today_range()
    total = await db.scalar(
        select(func.coalesce(func.sum(UsageEvent.input_tokens + UsageEvent.output_tokens), 0))
        .where(UsageEvent.user_id == user_id, UsageEvent.created_at >= start, UsageEvent.created_at <= now)
    )
    return int(total or 0)


async def _count_today_images(db: AsyncSession, user_id: str) -> int:
    start, now = _today_range()
    rows = await db.execute(
        select(File).where(File.user_id == user_id, File.kind == "image",
                           File.created_at >= start, File.created_at <= now)
    )
    count = 0
    for f in rows.scalars().all():
        notices = (f.extraction or {}).get("notices", [])
        if any("Generated image" in str(n) for n in notices):
            count += 1
    return count


async def _count_today_searches(db: AsyncSession, user_id: str) -> int:
    start, now = _today_range()
    rows = await db.execute(
        select(MessageBlock.data)
        .join(Message, Message.id == MessageBlock.message_id)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(MessageBlock.type == "tool_call",
               Message.created_at >= start, Message.created_at <= now,
               Conversation.user_id == user_id)
    )
    count = 0
    for (data,) in rows.all():
        if isinstance(data, dict) and data.get("name") == "web_search":
            count += 1
    return count


async def check_message_quota(db: AsyncSession, user_id: str) -> None:
    q = await _user_quota(db, user_id)
    if not q:
        return
    if q.daily_message_limit and q.daily_message_limit > 0:
        used = await _count_today_messages(db, user_id)
        if used >= q.daily_message_limit:
            raise QuotaExceededError(f"Daily message quota reached ({q.daily_message_limit}).")
    if q.daily_token_limit and q.daily_token_limit > 0:
        used = await _count_today_tokens(db, user_id)
        if used >= q.daily_token_limit:
            raise QuotaExceededError(f"Daily token quota reached ({q.daily_token_limit}).")


async def check_image_quota(db: AsyncSession, user_id: str) -> None:
    q = await _user_quota(db, user_id)
    if not q or not q.daily_image_limit or q.daily_image_limit <= 0:
        return
    used = await _count_today_images(db, user_id)
    if used >= q.daily_image_limit:
        raise QuotaExceededError(f"Daily image quota reached ({q.daily_image_limit}).")


async def quota_status(db: AsyncSession, user_id: str) -> dict:
    q = await _user_quota(db, user_id)
    if not q:
        return {"messages": {"limit": 0, "used": 0}, "tokens": {"limit": 0, "used": 0},
                "images": {"limit": 0, "used": 0}}
    return {
        "messages": {"limit": q.daily_message_limit, "used": await _count_today_messages(db, user_id)},
        "tokens": {"limit": q.daily_token_limit, "used": await _count_today_tokens(db, user_id)},
        "images": {"limit": q.daily_image_limit, "used": await _count_today_images(db, user_id)},
    }
