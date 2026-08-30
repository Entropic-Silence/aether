from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..deps import get_current_user
from ..errors import NotFoundError, PermissionError_, ValidationError_
from ..orm import User, Workspace, WorkspaceMember
from .deps_helper import workspace_id_for

router = APIRouter(prefix="/workspaces", tags=["workspaces"])

MEMBER_ROLES = {"owner", "admin", "member"}


class WorkspaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class MemberIn(BaseModel):
    email: EmailStr
    role: str = "member"


class MemberRoleIn(BaseModel):
    role: str


async def _member_role(db: AsyncSession, workspace_id: str, user_id: str) -> str | None:
    row = await db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
    )
    return row.role if row else None


async def _require_workspace_admin(db: AsyncSession, workspace_id: str, user: User) -> None:
    if user.role in ("owner",):
        return
    role = await _member_role(db, workspace_id, user.id)
    if role not in ("owner", "admin"):
        raise PermissionError_("Workspace admin required")


@router.get("")
async def list_workspaces(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    rows = await db.execute(
        select(Workspace, WorkspaceMember.role)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(WorkspaceMember.user_id == user.id)
    )
    return [
        {"id": w.id, "name": w.name, "role": role, "created_at": w.created_at}
        for w, role in rows.all()
    ]


@router.post("", status_code=201)
async def create_workspace(body: WorkspaceIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    ws = Workspace(name=body.name, settings={})
    db.add(ws)
    await db.flush()
    db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="owner"))
    await db.commit()
    await db.refresh(ws)
    return {"id": ws.id, "name": ws.name, "role": "owner"}


@router.get("/{workspace_id}/members")
async def list_members(workspace_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    role = await _member_role(db, workspace_id, user.id)
    if role is None and user.role not in ("owner",):
        raise PermissionError_("Not a member of this workspace")
    rows = await db.execute(
        select(User, WorkspaceMember.role)
        .join(WorkspaceMember, WorkspaceMember.user_id == User.id)
        .where(WorkspaceMember.workspace_id == workspace_id)
    )
    return [
        {"user_id": u.id, "email": u.email, "name": u.name, "role": role}
        for u, role in rows.all()
    ]


@router.post("/{workspace_id}/members", status_code=201)
async def add_member(workspace_id: str, body: MemberIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await _require_workspace_admin(db, workspace_id, user)
    if body.role not in MEMBER_ROLES:
        raise ValidationError_(f"role must be one of {sorted(MEMBER_ROLES)}")
    target = await db.scalar(select(User).where(User.email == body.email.lower()))
    if not target:
        raise NotFoundError("No user with that email")
    existing = await db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == target.id)
    )
    if existing:
        raise ValidationError_("User is already a member")
    db.add(WorkspaceMember(workspace_id=workspace_id, user_id=target.id, role=body.role))
    await db.commit()
    return {"ok": True, "user_id": target.id, "role": body.role}


@router.patch("/{workspace_id}/members/{user_id}")
async def update_member_role(workspace_id: str, user_id: str, body: MemberRoleIn,
                             db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await _require_workspace_admin(db, workspace_id, user)
    if body.role not in MEMBER_ROLES:
        raise ValidationError_(f"role must be one of {sorted(MEMBER_ROLES)}")
    member = await db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user_id)
    )
    if not member:
        raise NotFoundError("Member not found")
    if member.role == "owner" and body.role != "owner":
        raise ValidationError_("Cannot demote the workspace owner")
    member.role = body.role
    await db.commit()
    return {"ok": True, "user_id": user_id, "role": body.role}


@router.delete("/{workspace_id}/members/{user_id}", status_code=204)
async def remove_member(workspace_id: str, user_id: str,
                        db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await _require_workspace_admin(db, workspace_id, user)
    member = await db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user_id)
    )
    if not member:
        raise NotFoundError("Member not found")
    if member.role == "owner":
        raise ValidationError_("Cannot remove the workspace owner")
    await db.delete(member)
    await db.commit()
