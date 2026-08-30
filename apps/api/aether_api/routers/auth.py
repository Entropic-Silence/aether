from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..deps import get_current_user
from ..errors import AuthError, PermissionError_
from ..orm import User, Workspace, WorkspaceMember
from ..schemas import LoginIn, RegisterIn, TokenOut, UserOut
from ..security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenOut)
async def register(body: RegisterIn, db: AsyncSession = Depends(get_db)):
    count = await db.scalar(select(func.count()).select_from(User))
    from ..services.features import get_feature_controls

    controls = await get_feature_controls(db)
    if count and not controls["policies"]["registration_enabled"]:
        raise PermissionError_("Registration is disabled. Ask an administrator for an account.")
    existing = await db.scalar(select(User).where(User.email == body.email.lower()))
    if existing:
        raise AuthError("An account with this email already exists")
    role = "owner" if count == 0 else "user"
    user = User(email=body.email.lower(), name=body.name, password_hash=hash_password(body.password), role=role)
    db.add(user)
    await db.flush()
    if count == 0:
        ws = Workspace(name="Default", settings={})
        db.add(ws)
        await db.flush()
        db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="owner"))
    else:
        ws = await db.scalar(select(Workspace).order_by(Workspace.created_at.asc()).limit(1))
        if ws:
            db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="member"))
    await db.commit()
    await db.refresh(user)
    token = create_access_token(user.id, user.role)
    return TokenOut(access_token=token, user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(User).where(User.email == body.email.lower()))
    if not user or not verify_password(body.password, user.password_hash):
        raise AuthError("Invalid email or password")
    token = create_access_token(user.id, user.role)
    return TokenOut(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user)
