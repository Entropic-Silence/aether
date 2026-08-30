from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..deps import get_current_user
from ..orm import Conversation, File, Message, MessageBlock, Project, User

router = APIRouter(prefix="/search", tags=["search"])


@router.get("")
async def global_search(q: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    term = q.strip()
    if not term:
        return {"conversations": [], "messages": [], "files": [], "projects": []}
    like = f"%{term}%"

    convs = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == user.id, Conversation.title.ilike(like))
        .order_by(Conversation.updated_at.desc()).limit(20)
    )
    conversations = [{"id": c.id, "title": c.title, "updated_at": c.updated_at}
                     for c in convs.scalars().all()]

    msg_rows = await db.execute(
        select(MessageBlock, Message)
        .join(Message, Message.id == MessageBlock.message_id)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(MessageBlock.type.in_(["text", "markdown"]),
               Conversation.user_id == user.id)
        .limit(500)
    )
    messages = []
    for block, msg in msg_rows.all():
        text = (block.data or {}).get("text", "")
        if term.lower() in text.lower():
            idx = text.lower().find(term.lower())
            snippet = text[max(0, idx - 40): idx + 60]
            messages.append({"conversation_id": msg.conversation_id, "message_id": msg.id,
                             "role": msg.role, "snippet": snippet})
            if len(messages) >= 20:
                break

    files = await db.execute(
        select(File).where(File.user_id == user.id, File.name.ilike(like))
        .order_by(File.created_at.desc()).limit(20)
    )
    file_list = [{"id": f.id, "name": f.name, "kind": f.kind} for f in files.scalars().all()]

    projects = await db.execute(
        select(Project).where(Project.user_id == user.id,
                              or_(Project.name.ilike(like), Project.description.ilike(like)))
        .order_by(Project.updated_at.desc()).limit(20)
    )
    project_list = [{"id": p.id, "name": p.name} for p in projects.scalars().all()]

    return {"conversations": conversations, "messages": messages,
            "files": file_list, "projects": project_list}
