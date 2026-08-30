from __future__ import annotations

import asyncio
import time
from typing import AsyncIterator

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from ..db import SessionLocal, get_db
from ..deps import get_current_user
from ..errors import ApiError, CapabilityUnsupportedError, NotFoundError
from ..orm import Conversation, Message, MessageBlock, Model, Provider, Setting, User
from ..services.research import run_research
from ..services.search import SEARCH_SETTINGS_KEY, build_router
from .chat import _resolve_model, _set_leaf, _set_title, _sse

router = APIRouter(tags=["research"])


class ResearchIn(BaseModel):
    goal: str = Field(min_length=3, max_length=2000)
    model_id: str | None = None


@router.post("/conversations/{conversation_id}/research")
async def deep_research(conversation_id: str, body: ResearchIn, request: Request,
                        db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    from ..services.features import ensure_feature

    await ensure_feature(db, "deep_research", user)
    conv = await db.get(Conversation, conversation_id)
    if not conv or (conv.user_id != user.id and user.role not in ("admin", "owner")):
        raise NotFoundError("Conversation not found")

    row = await db.get(Setting, SEARCH_SETTINGS_KEY)
    settings = row.value if row and isinstance(row.value, dict) else {"providers": [{"kind": "mock", "enabled": True}]}
    search_router = build_router(settings)
    if not search_router.providers:
        raise CapabilityUnsupportedError("No search provider configured. Admin → Search.")

    from ..schemas import RunIn

    model = await _resolve_model(db, RunIn(model_id=body.model_id), conv)
    provider = await db.get(Provider, model.provider_id)
    if not provider or not provider.enabled:
        raise NotFoundError("Provider for the selected model is not available")

    user_message = Message(conversation_id=conv.id, parent_id=conv.current_leaf_id, role="user")
    db.add(user_message)
    await db.flush()
    db.add(MessageBlock(message_id=user_message.id, seq=0, type="text",
                        data={"text": f"Deep research: {body.goal}", "research_goal": True}))
    assistant_message = Message(conversation_id=conv.id, parent_id=user_message.id, role="assistant",
                                model_id=model.id, status="streaming")
    db.add(assistant_message)
    conv.current_leaf_id = user_message.id
    await db.commit()

    started = time.monotonic()

    async def event_stream() -> AsyncIterator[dict]:
        yield _sse("response.created", {
            "conversation_id": conv.id,
            "user_message_id": user_message.id,
            "assistant_message_id": assistant_message.id,
            "model": {"id": model.id, "display_name": model.display_name},
            "mode": "research",
        })
        report_buf: list[str] = []
        sources: list[dict] = []
        block_open = False
        try:
            async for event, data in run_research(db, model, provider, search_router, body.goal):
                if await request.is_disconnected():
                    break
                if event == "report.delta":
                    if not block_open:
                        block_open = True
                        yield _sse("block.started", {"message_id": assistant_message.id, "type": "markdown"})
                    report_buf.append(data["delta"])
                    yield _sse("block.delta", {"type": "markdown", "delta": data["delta"]})
                elif event == "report":
                    sources = data.get("sources", [])
                    if not report_buf and data.get("text"):
                        report_buf.append(data["text"])
                        yield _sse("block.started", {"message_id": assistant_message.id, "type": "markdown"})
                        yield _sse("block.delta", {"type": "markdown", "delta": data["text"]})
                        block_open = True
                else:
                    yield _sse(event, data)
        except ApiError as e:
            await _finalize(assistant_message.id, "".join(report_buf), sources, e.to_dict())
            yield _sse("error", e.to_dict())
            return
        except asyncio.CancelledError:
            pass
        except Exception as e:  # noqa: BLE001
            err = {"code": "INTERNAL_ERROR", "message": f"Research failed: {e}", "retryable": False}
            await _finalize(assistant_message.id, "".join(report_buf), sources, err)
            yield _sse("error", err)
            return

        if block_open:
            yield _sse("block.completed", {"type": "markdown"})
        await _finalize(assistant_message.id, "".join(report_buf), sources, None)
        await _set_leaf(conv.id, assistant_message.id)
        yield _sse("response.completed", {
            "message_id": assistant_message.id,
            "finish_reason": "stop",
            "latency_ms": int((time.monotonic() - started) * 1000),
            "source_count": len(sources),
        })
        title = f"Research: {body.goal.strip()[:60]}"
        await _set_title(conv.id, title)
        yield _sse("conversation.title", {"conversation_id": conv.id, "title": title})

    return EventSourceResponse(event_stream())


async def _finalize(message_id: str, report_text: str, sources: list[dict], error: dict | None) -> None:
    async with SessionLocal() as db:
        message = await db.get(Message, message_id)
        if not message:
            return
        seq = 0
        if report_text:
            db.add(MessageBlock(message_id=message_id, seq=seq, type="markdown", data={"text": report_text}))
            seq += 1
        if sources:
            db.add(MessageBlock(message_id=message_id, seq=seq, type="sources", data={"sources": sources}))
            seq += 1
        if error:
            db.add(MessageBlock(message_id=message_id, seq=seq, type="error", data=error))
            message.status = "failed"
            message.error = error
        else:
            message.status = "completed"
        await db.commit()
