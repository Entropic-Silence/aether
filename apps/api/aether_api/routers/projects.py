from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..deps import get_current_user
from ..errors import NotFoundError, PermissionError_
from ..orm import Conversation, File, Project, ProjectFile, User
from .deps_helper import workspace_id_for
from ..services.features import feature_dependency

router = APIRouter(prefix="/projects", tags=["projects"], dependencies=[Depends(feature_dependency("projects"))])


class ProjectIn(BaseModel):
    name: str
    description: str = ""
    icon: str = ""
    instructions: str = ""
    memory_mode: str = "default"


class ProjectPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    icon: str | None = None
    instructions: str | None = None
    memory_mode: str | None = None
    pinned: bool | None = None


def _to_out(p: Project, chat_count: int = 0, file_count: int = 0) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "icon": p.icon,
        "instructions": p.instructions,
        "memory_mode": p.memory_mode,
        "pinned": p.pinned,
        "created_at": p.created_at,
        "chat_count": chat_count,
        "file_count": file_count,
    }


async def _owned_project(db: AsyncSession, project_id: str, user: User) -> Project:
    p = await db.get(Project, project_id)
    if not p:
        raise NotFoundError("Project not found")
    if p.user_id != user.id and user.role not in ("admin", "owner"):
        raise PermissionError_("Not your project")
    return p


async def _counts(db: AsyncSession, project_id: str) -> tuple[int, int]:
    from sqlalchemy import func

    chats = await db.scalar(
        select(func.count()).select_from(Conversation).where(Conversation.project_id == project_id)
    ) or 0
    files = await db.scalar(
        select(func.count()).select_from(ProjectFile).where(ProjectFile.project_id == project_id)
    ) or 0
    return int(chats), int(files)


@router.get("")
async def list_projects(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    rows = await db.execute(
        select(Project).where(Project.user_id == user.id).order_by(Project.pinned.desc(), Project.updated_at.desc())
    )
    out = []
    for p in rows.scalars().all():
        chats, files = await _counts(db, p.id)
        out.append(_to_out(p, chats, files))
    return out


@router.post("", status_code=201)
async def create_project(body: ProjectIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    p = Project(
        workspace_id=await workspace_id_for(db),
        user_id=user.id,
        name=body.name.strip() or "Untitled project",
        description=body.description,
        icon=body.icon,
        instructions=body.instructions,
        memory_mode=body.memory_mode,
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return _to_out(p)


@router.get("/{project_id}")
async def get_project(project_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    p = await _owned_project(db, project_id, user)
    chats, files = await _counts(db, p.id)
    return _to_out(p, chats, files)


@router.get("/{project_id}/conversations")
async def project_conversations(project_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await _owned_project(db, project_id, user)
    rows = await db.execute(
        select(Conversation)
        .where(Conversation.project_id == project_id, Conversation.user_id == user.id)
        .order_by(Conversation.updated_at.desc())
    )
    return [
        {"id": c.id, "title": c.title, "updated_at": c.updated_at, "pinned": c.pinned}
        for c in rows.scalars().all()
    ]


@router.get("/{project_id}/files")
async def project_files(project_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await _owned_project(db, project_id, user)
    rows = await db.execute(
        select(File)
        .join(ProjectFile, ProjectFile.file_id == File.id)
        .where(ProjectFile.project_id == project_id)
        .order_by(File.created_at.desc())
    )
    from .files import _to_out as file_out

    return [file_out(f) for f in rows.scalars().all()]


@router.post("/{project_id}/files/{file_id}", status_code=201)
async def add_file_to_project(project_id: str, file_id: str, db: AsyncSession = Depends(get_db),
                              user: User = Depends(get_current_user)):
    await _owned_project(db, project_id, user)
    f = await db.get(File, file_id)
    if not f or (f.user_id != user.id and user.role not in ("admin", "owner")):
        raise NotFoundError("File not found")
    existing = await db.scalar(
        select(ProjectFile).where(ProjectFile.project_id == project_id, ProjectFile.file_id == file_id)
    )
    if not existing:
        db.add(ProjectFile(project_id=project_id, file_id=file_id))
    f.project_id = project_id
    await db.commit()
    return {"ok": True}


@router.delete("/{project_id}/files/{file_id}", status_code=204)
async def remove_file_from_project(project_id: str, file_id: str, db: AsyncSession = Depends(get_db),
                                   user: User = Depends(get_current_user)):
    await _owned_project(db, project_id, user)
    link = await db.scalar(
        select(ProjectFile).where(ProjectFile.project_id == project_id, ProjectFile.file_id == file_id)
    )
    if link:
        await db.delete(link)
    f = await db.get(File, file_id)
    if f and f.project_id == project_id:
        f.project_id = None
    await db.commit()


@router.patch("/{project_id}")
async def update_project(project_id: str, body: ProjectPatch, db: AsyncSession = Depends(get_db),
                         user: User = Depends(get_current_user)):
    p = await _owned_project(db, project_id, user)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    await db.commit()
    await db.refresh(p)
    chats, files = await _counts(db, p.id)
    return _to_out(p, chats, files)


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    p = await _owned_project(db, project_id, user)
    await db.execute(ProjectFile.__table__.delete().where(ProjectFile.project_id == project_id))
    rows = await db.execute(select(Conversation).where(Conversation.project_id == project_id))
    for c in rows.scalars().all():
        c.project_id = None
    await db.delete(p)
    await db.commit()
