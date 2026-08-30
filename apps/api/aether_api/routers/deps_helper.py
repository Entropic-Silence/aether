from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import get_default_workspace


async def workspace_id_for(db: AsyncSession) -> str:
    ws = await get_default_workspace(db)
    return ws.id
