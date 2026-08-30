from __future__ import annotations

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_db
from .errors import AuthError, PermissionError_
from .orm import User, Workspace
from .security import decode_access_token

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials if credentials else None
    if not token:
        raise AuthError("Not authenticated")
    payload = decode_access_token(token)
    if not payload:
        raise AuthError("Invalid or expired token")
    user = await db.get(User, payload.get("sub", ""))
    if not user:
        raise AuthError("User no longer exists")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role not in ("admin", "owner", "moderator"):
        raise PermissionError_("Admin access required")
    return user


async def get_default_workspace(db: AsyncSession) -> Workspace:
    result = await db.execute(select(Workspace).order_by(Workspace.created_at.asc()).limit(1))
    ws = result.scalar_one_or_none()
    if ws is None:
        ws = Workspace(name="Default", settings={})
        db.add(ws)
        await db.commit()
        await db.refresh(ws)
    return ws
