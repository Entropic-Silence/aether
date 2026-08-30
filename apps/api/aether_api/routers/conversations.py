from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..db import get_db
from ..deps import get_current_user
from ..errors import NotFoundError, PermissionError_
from ..orm import Conversation, Message, MessageBlock, User
from ..schemas import ConversationIn, ConversationOut, ConversationPatch, MessageOut

router = APIRouter(prefix="/conversations", tags=["conversations"])


async def _owned_conversation(db: AsyncSession, conversation_id: str, user: User) -> Conversation:
    conv = await db.get(Conversation, conversation_id)
    if not conv:
        raise NotFoundError("Conversation not found")
    if conv.user_id != user.id and user.role not in ("admin", "owner"):
        raise PermissionError_("Not your conversation")
    return conv


def _to_out(c: Conversation, preview: str = "") -> ConversationOut:
    out = ConversationOut.model_validate(c)
    out.preview = preview
    return out


@router.get("/{conversation_id}/branches")
async def get_message_branches(conversation_id: str, db: AsyncSession = Depends(get_db),
                               user: User = Depends(get_current_user)):
    """Return assistant alternatives created by retries, grouped by their user prompt."""
    conv = await _owned_conversation(db, conversation_id, user)
    rows = await db.execute(
        select(Message).where(Message.conversation_id == conv.id).order_by(Message.created_at)
    )
    messages = rows.scalars().all()
    by_id = {message.id: message for message in messages}
    active_ids: set[str] = set()
    current = by_id.get(conv.current_leaf_id) if conv.current_leaf_id else None
    while current and current.id not in active_ids:
        active_ids.add(current.id)
        current = by_id.get(current.parent_id) if current.parent_id else None
    groups: dict[str, list[Message]] = {}
    for message in messages:
        if message.role == "assistant" and message.parent_id:
            groups.setdefault(message.parent_id, []).append(message)
    return [
        {
            "parent_user_message_id": parent_id,
            "active_message_id": next((item.id for item in alternatives if item.id in active_ids), alternatives[-1].id),
            "alternatives": [
                {"message_id": item.id, "status": item.status, "created_at": item.created_at}
                for item in alternatives
            ],
        }
        for parent_id, alternatives in groups.items() if len(alternatives) > 1
    ]


@router.post("/{conversation_id}/branches/{message_id}/activate")
async def activate_message_branch(conversation_id: str, message_id: str,
                                  db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    conv = await _owned_conversation(db, conversation_id, user)
    message = await db.get(Message, message_id)
    if not message or message.conversation_id != conv.id or message.role != "assistant":
        raise NotFoundError("Response branch not found")
    rows = await db.execute(select(Message).where(Message.conversation_id == conv.id))
    all_messages = rows.scalars().all()
    by_id = {item.id: item for item in all_messages}
    active_path: list[Message] = []
    current = by_id.get(conv.current_leaf_id) if conv.current_leaf_id else None
    seen: set[str] = set()
    while current and current.id not in seen:
        seen.add(current.id)
        active_path.append(current)
        current = by_id.get(current.parent_id) if current.parent_id else None
    active_sibling = next(
        (item for item in active_path if item.role == "assistant" and item.parent_id == message.parent_id),
        None,
    )
    if active_sibling and active_sibling.id != message.id:
        # Keep the continuation below this logical turn. Moving its first child
        # between sibling assistant variants makes version browsing non-destructive.
        continuation = next((item for item in active_path if item.parent_id == active_sibling.id), None)
        if continuation:
            continuation.parent_id = message.id
        elif conv.current_leaf_id == active_sibling.id:
            conv.current_leaf_id = message.id
    elif not active_sibling:
        conv.current_leaf_id = message.id
    await db.commit()
    return {"ok": True, "active_message_id": message.id}


@router.get("", response_model=list[ConversationOut])
async def list_conversations(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    include_archived: bool = False,
    temporary: bool | None = None,
):
    q = select(Conversation).where(Conversation.user_id == user.id)
    if not include_archived:
        q = q.where(Conversation.archived.is_(False))
    if temporary is not None:
        q = q.where(Conversation.temporary.is_(temporary))
    rows = await db.execute(q.order_by(Conversation.pinned.desc(), Conversation.updated_at.desc()).limit(200))
    convs = rows.scalars().all()
    out = []
    for c in convs:
        preview = await db.scalar(
            select(MessageBlock.data)
            .join(Message, Message.id == MessageBlock.message_id)
            .where(Message.conversation_id == c.id, Message.role == "user", MessageBlock.type.in_(["text", "markdown"]))
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        text = ""
        if isinstance(preview, dict):
            text = (preview.get("text") or "")[:120]
        out.append(_to_out(c, text))
    return out


@router.post("", response_model=ConversationOut, status_code=201)
async def create_conversation(body: ConversationIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    from .deps_helper import workspace_id_for
    from ..services.features import ensure_feature

    await ensure_feature(db, "work" if body.mode == "work" else "chat", user)

    conv = Conversation(
        workspace_id=await workspace_id_for(db),
        user_id=user.id,
        title=body.title,
        mode=body.mode,
        model_id=body.model_id,
        temporary=body.temporary,
    )
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return _to_out(conv)


@router.get("/{conversation_id}", response_model=ConversationOut)
async def get_conversation(conversation_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    conv = await _owned_conversation(db, conversation_id, user)
    return _to_out(conv)


@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
async def get_messages(conversation_id: str, active_only: bool = False,
                       db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    conv = await _owned_conversation(db, conversation_id, user)
    rows = await db.execute(
        select(Message)
        .options(selectinload(Message.blocks))
        .where(Message.conversation_id == conv.id)
        .order_by(Message.created_at)
    )
    messages = rows.scalars().all()
    # A regeneration creates a sibling assistant branch.  Only return the
    # active path so old branches never appear as duplicate messages.
    if active_only and conv.current_leaf_id:
        by_id = {m.id: m for m in messages}
        active_path = []
        current = by_id.get(conv.current_leaf_id)
        seen: set[str] = set()
        while current and current.id not in seen:
            seen.add(current.id)
            active_path.append(current)
            current = by_id.get(current.parent_id) if current.parent_id else None
        if active_path:
            messages = list(reversed(active_path))
    out = []
    for m in messages:
        blocks = [
            {"id": b.id, "seq": b.seq, "type": b.type, "data": b.data}
            for b in sorted(m.blocks, key=lambda b: b.seq)
        ]
        mo = MessageOut(
            id=m.id,
            conversation_id=m.conversation_id,
            parent_id=m.parent_id,
            role=m.role,
            model_id=m.model_id,
            status=m.status,
            error=m.error,
            usage=m.usage,
            created_at=m.created_at,
            blocks=blocks,
        )
        out.append(mo)
    return out


class MessageTextPatch(BaseModel):
    text: str = Field(min_length=1, max_length=20000)


class ConversationErrorIn(BaseModel):
    content: str = Field(default="", max_length=20000)
    message: str = Field(min_length=1, max_length=4000)
    code: str = "RESPONSE_FAILED"
    retry_kind: str = "chat"
    model_id: str | None = None
    parent_user_message_id: str | None = None
    duration_ms: int = 0


@router.post("/{conversation_id}/errors", status_code=201)
async def record_conversation_error(
    conversation_id: str,
    body: ConversationErrorIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Persist failures that happen before a streaming assistant is created."""
    conv = await _owned_conversation(db, conversation_id, user)
    parent = await db.get(Message, conv.current_leaf_id) if conv.current_leaf_id else None
    user_message = None
    if body.parent_user_message_id:
        candidate = await db.get(Message, body.parent_user_message_id)
        if candidate and candidate.conversation_id == conv.id and candidate.role == "user":
            user_message = candidate
    if parent and parent.role == "user":
        block = await db.scalar(
            select(MessageBlock).where(MessageBlock.message_id == parent.id, MessageBlock.type == "text").limit(1)
        )
        if user_message is None and block and str((block.data or {}).get("text", "")).strip() == body.content.strip():
            user_message = parent
    if user_message is None:
        user_message = Message(
            conversation_id=conv.id, parent_id=parent.id if parent else None,
            role="user", status="completed",
        )
        db.add(user_message)
        await db.flush()
        db.add(MessageBlock(message_id=user_message.id, seq=0, type="text", data={"text": body.content}))
    error = {
        "code": body.code, "message": body.message, "retryable": True,
        "kind": body.retry_kind,
    }
    assistant = Message(
        conversation_id=conv.id, parent_id=user_message.id, role="assistant",
        model_id=body.model_id, status="failed", error=error,
        usage={"input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0,
               "duration_ms": max(0, body.duration_ms), "source": "unavailable"},
    )
    db.add(assistant)
    await db.flush()
    db.add(MessageBlock(message_id=assistant.id, seq=0, type="error", data=error))
    conv.current_leaf_id = assistant.id
    await db.commit()
    return {"ok": True, "assistant_message_id": assistant.id}


@router.patch("/{conversation_id}/messages/{message_id}")
async def update_last_user_message(
    conversation_id: str,
    message_id: str,
    body: MessageTextPatch,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Edit only the final user prompt on the active branch."""
    conv = await _owned_conversation(db, conversation_id, user)
    message = await db.scalar(
        select(Message).options(selectinload(Message.blocks)).where(Message.id == message_id)
    )
    if not message or message.conversation_id != conv.id or message.role != "user":
        raise NotFoundError("User message not found")
    leaf = await db.get(Message, conv.current_leaf_id) if conv.current_leaf_id else None
    final_user_id = leaf.parent_id if leaf and leaf.role == "assistant" else (leaf.id if leaf else None)
    if final_user_id != message.id:
        raise PermissionError_("Only the last prompt can be edited")
    text_block = next((b for b in message.blocks if b.type in ("text", "markdown")), None)
    if text_block:
        text_block.data = {**(text_block.data or {}), "text": body.text.strip()}
    else:
        db.add(MessageBlock(message_id=message.id, seq=0, type="text", data={"text": body.text.strip()}))
    await db.commit()
    return {"ok": True, "message_id": message.id}


@router.patch("/{conversation_id}", response_model=ConversationOut)
async def update_conversation(conversation_id: str, body: ConversationPatch, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    conv = await _owned_conversation(db, conversation_id, user)
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(conv, k, v)
    await db.commit()
    await db.refresh(conv)
    return _to_out(conv)


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    conv = await _owned_conversation(db, conversation_id, user)
    await db.delete(conv)
    await db.commit()
    import shutil

    from ..services.sandbox import get_sandbox

    try:
        workspace = get_sandbox().root / conversation_id
        if workspace.exists():
            shutil.rmtree(workspace, ignore_errors=True)
    except Exception:  # noqa: BLE001
        pass
