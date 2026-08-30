from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..deps import get_current_user
from ..errors import NotFoundError, ValidationError_
from ..orm import Artifact, File, User
from .deps_helper import workspace_id_for

router = APIRouter(prefix="/artifacts", tags=["artifacts"])

KINDS = {"document", "code", "spreadsheet", "presentation", "chart", "website", "image", "file"}


class ArtifactIn(BaseModel):
    kind: str = "document"
    title: str = Field(default="", max_length=300)
    content: str = ""
    file_id: str | None = None
    conversation_id: str | None = None
    message_id: str | None = None


def _to_out(a: Artifact) -> dict:
    return {
        "id": a.id, "kind": a.kind, "title": a.title,
        "content": a.content, "file_id": a.file_id,
        "conversation_id": a.conversation_id, "message_id": a.message_id,
        "created_at": a.created_at,
    }


@router.get("")
async def list_artifacts(kind: str | None = None,
                         db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    q = select(Artifact).where(Artifact.user_id == user.id)
    if kind:
        q = q.where(Artifact.kind == kind)
    rows = await db.execute(q.order_by(Artifact.created_at.desc()).limit(200))
    return [_to_out(a) for a in rows.scalars().all()]


@router.post("", status_code=201)
async def create_artifact(body: ArtifactIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    if body.kind not in KINDS:
        raise ValidationError_(f"kind must be one of {sorted(KINDS)}")
    if not body.content and not body.file_id:
        raise ValidationError_("artifact needs content or file_id")
    a = Artifact(
        workspace_id=await workspace_id_for(db),
        user_id=user.id, kind=body.kind, title=body.title or "Untitled",
        content=body.content, file_id=body.file_id,
        conversation_id=body.conversation_id, message_id=body.message_id,
    )
    db.add(a)
    await db.commit()
    await db.refresh(a)
    return _to_out(a)


@router.get("/{artifact_id}")
async def get_artifact(artifact_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    a = await db.get(Artifact, artifact_id)
    if not a or a.user_id != user.id:
        raise NotFoundError("Artifact not found")
    return _to_out(a)


@router.get("/{artifact_id}/download")
async def download_artifact(artifact_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    from ..services.storage import get_storage

    a = await db.get(Artifact, artifact_id)
    if not a or a.user_id != user.id:
        raise NotFoundError("Artifact not found")
    if a.file_id:
        f = await db.get(File, a.file_id)
        if not f:
            raise NotFoundError("Artifact file missing")
        data = await get_storage().get(f.storage_key)
        return Response(content=data, media_type=f.mime or "application/octet-stream",
                        headers={"Content-Disposition": f'attachment; filename="{f.name}"'})
    ext = {"document": "md", "code": "txt", "spreadsheet": "csv"}.get(a.kind, "txt")
    name = (a.title or "artifact").replace('"', "")
    return Response(content=a.content.encode(), media_type="text/plain",
                    headers={"Content-Disposition": f'attachment; filename="{name}.{ext}"'})


@router.delete("/{artifact_id}", status_code=204)
async def delete_artifact(artifact_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    a = await db.get(Artifact, artifact_id)
    if not a or a.user_id != user.id:
        raise NotFoundError("Artifact not found")
    await db.delete(a)
    await db.commit()
