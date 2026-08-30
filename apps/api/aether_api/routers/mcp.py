from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..deps import require_admin
from ..errors import NotFoundError, ValidationError_
from ..orm import McpServer, User
from ..security import decrypt_secret, encrypt_secret
from ..services.mcp import McpClient
from ..services.tools import clear_mcp_cache
from .deps_helper import workspace_id_for

router = APIRouter(prefix="/mcp", tags=["mcp"])

TRANSPORTS = {"stdio", "http", "sse"}


class McpServerIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    transport: str = "stdio"
    config: dict = {}
    enabled: bool = True


class McpServerPatch(BaseModel):
    name: str | None = None
    transport: str | None = None
    config: dict | None = None
    enabled: bool | None = None


def _to_out(s: McpServer) -> dict:
    return {
        "id": s.id, "name": s.name, "transport": s.transport, "enabled": s.enabled,
        "last_status": s.last_status, "last_error": s.last_error,
        "last_tool_count": s.last_tool_count, "created_at": s.created_at,
    }


def _validate(transport: str, config: dict) -> None:
    if transport not in TRANSPORTS:
        raise ValidationError_(f"transport must be one of {sorted(TRANSPORTS)}")
    if transport == "stdio" and not config.get("command"):
        raise ValidationError_("stdio transport requires config.command")
    if transport in ("http", "sse") and not config.get("url"):
        raise ValidationError_(f"{transport} transport requires config.url")


@router.get("/servers")
async def list_servers(db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    rows = await db.execute(select(McpServer).order_by(McpServer.created_at))
    return [_to_out(s) for s in rows.scalars().all()]


@router.post("/servers", status_code=201)
async def create_server(body: McpServerIn, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    _validate(body.transport, body.config)
    s = McpServer(
        workspace_id=await workspace_id_for(db),
        name=body.name, transport=body.transport,
        config_enc=encrypt_secret(json.dumps(body.config)),
        enabled=body.enabled,
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    clear_mcp_cache()
    return _to_out(s)


@router.patch("/servers/{server_id}")
async def update_server(server_id: str, body: McpServerPatch,
                        db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    s = await db.get(McpServer, server_id)
    if not s:
        raise NotFoundError("MCP server not found")
    data = body.model_dump(exclude_unset=True)
    transport = data.get("transport", s.transport)
    if "config" in data:
        _validate(transport, data["config"])
        s.config_enc = encrypt_secret(json.dumps(data["config"]))
    if "transport" in data:
        s.transport = data["transport"]
    if "name" in data:
        s.name = data["name"]
    if "enabled" in data:
        s.enabled = data["enabled"]
    await db.commit()
    await db.refresh(s)
    clear_mcp_cache()
    return _to_out(s)


@router.delete("/servers/{server_id}", status_code=204)
async def delete_server(server_id: str, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    s = await db.get(McpServer, server_id)
    if not s:
        raise NotFoundError("MCP server not found")
    await db.delete(s)
    await db.commit()
    clear_mcp_cache()


@router.post("/servers/{server_id}/test")
async def test_server(server_id: str, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    s = await db.get(McpServer, server_id)
    if not s:
        raise NotFoundError("MCP server not found")
    try:
        config = json.loads(decrypt_secret(s.config_enc) or "{}")
    except json.JSONDecodeError:
        config = {}
    client = McpClient(s.transport, config)
    try:
        tools = await client.list_tools()
        s.last_status = "connected"
        s.last_tool_count = len(tools)
        s.last_error = ""
        await db.commit()
        clear_mcp_cache()
        return {"ok": True, "tool_count": len(tools),
                "tools": [{"name": t.get("name"), "description": (t.get("description") or "")[:200]}
                          for t in tools]}
    except Exception as e:  # noqa: BLE001
        msg = getattr(e, "message", str(e))
        s.last_status = "error"
        s.last_error = msg
        await db.commit()
        return {"ok": False, "error": msg}
