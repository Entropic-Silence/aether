from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..deps import require_admin
from ..orm import RequestLog, User

router = APIRouter(prefix="/logs", tags=["observability"])


@router.get("")
async def list_logs(limit: int = 100, status: int | None = None,
                    db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    limit = max(1, min(limit, 500))
    q = select(RequestLog).order_by(RequestLog.created_at.desc()).limit(limit)
    if status is not None:
        q = q.where(RequestLog.status == status)
    rows = await db.execute(q)
    return [
        {"id": r.id, "user_id": r.user_id, "method": r.method, "path": r.path,
         "status": r.status, "latency_ms": r.latency_ms, "error_code": r.error_code,
         "created_at": r.created_at}
        for r in rows.scalars().all()
    ]
