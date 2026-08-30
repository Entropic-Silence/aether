from __future__ import annotations

import json
import re
from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..deps import get_current_user, require_admin
from ..errors import NotFoundError, ValidationError_
from ..orm import Plugin, User, UserSettings
from ..services.plugins import plugins_root, sync_plugins
from ..services.features import feature_dependency
from .deps_helper import workspace_id_for

router = APIRouter(prefix="/plugins", tags=["plugins"], dependencies=[Depends(feature_dependency("plugins"))])


@router.get("")
async def list_plugins(rescan: bool = False,
                       db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    ws_id = await workspace_id_for(db)
    if rescan and user.role in ("admin", "owner"):
        await sync_plugins(db, ws_id)
    settings = await db.get(UserSettings, user.id)
    enabled = set(settings.enabled_plugins or []) if settings else set()
    rows = await db.execute(select(Plugin).where(Plugin.workspace_id == ws_id).order_by(Plugin.name))
    plugins = rows.scalars().all()
    return {
        "plugins_dir": str(plugins_root()),
        "plugins": [
            {"plugin_id": p.plugin_id, "name": p.name, "version": p.version,
             "status": p.status, "problems": p.problems or [],
             "capabilities": (p.manifest or {}).get("capabilities") or [],
             "permissions": (p.manifest or {}).get("permissions") or [],
             "description": (p.manifest or {}).get("description") or "",
             "format": (p.manifest or {}).get("format") or "aether",
             "enabled": p.plugin_id in enabled,
             "installed_at": p.installed_at}
            for p in plugins
        ],
    }


@router.put("/enabled")
async def set_plugin_enabled(body: dict,
                             db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    plugin_id = str(body.get("plugin_id") or "")
    if not plugin_id:
        raise ValidationError_("plugin_id is required")
    ws_id = await workspace_id_for(db)
    plugin = await db.scalar(select(Plugin).where(Plugin.workspace_id == ws_id, Plugin.plugin_id == plugin_id))
    if not plugin or plugin.status != "valid":
        raise NotFoundError("Valid plugin not found")
    settings = await db.get(UserSettings, user.id)
    if settings is None:
        settings = UserSettings(user_id=user.id)
        db.add(settings)
    enabled = set(settings.enabled_plugins or [])
    if body.get("enabled") is True:
        enabled.add(plugin_id)
    else:
        enabled.discard(plugin_id)
    settings.enabled_plugins = sorted(enabled)
    await db.commit()
    return {"ok": True, "plugin_id": plugin_id, "enabled": plugin_id in enabled}


@router.post("/import", status_code=201)
async def import_plugin(upload: UploadFile, db: AsyncSession = Depends(get_db),
                        user: User = Depends(get_current_user)):
    """Import a DeepSeek Harness/Cordis package manifest without executing untrusted code."""
    if not (upload.filename or "").lower().endswith(".json"):
        raise ValidationError_("Import a DeepSeek Harness package.json file")
    raw = await upload.read(512 * 1024 + 1)
    if len(raw) > 512 * 1024:
        raise ValidationError_("Plugin manifest is too large")
    try:
        package = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError_(f"Invalid package.json: {exc}") from exc
    if not isinstance(package, dict):
        raise ValidationError_("package.json must contain an object")
    keywords = package.get("keywords") or []
    dsh = package.get("dsh") or package.get("cordis") or {}
    if "dsh-plugin" not in keywords and not dsh and not str(package.get("name", "")).startswith("@deepseek-ai/"):
        raise ValidationError_("Not a recognized DeepSeek Harness/Cordis plugin manifest")
    name = str(package.get("name") or "plugin")
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "-", name).strip("-.")[:100] or "plugin"
    target = plugins_root() / f"user-{user.id[:8]}-{safe}"
    target.mkdir(parents=True, exist_ok=True)
    (target / "package.json").write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
    await sync_plugins(db, await workspace_id_for(db))
    plugin = await db.scalar(select(Plugin).where(Plugin.plugin_id == name))
    if not plugin or plugin.status != "valid":
        raise ValidationError_("Plugin manifest did not pass validation")
    settings = await db.get(UserSettings, user.id)
    if settings is None:
        settings = UserSettings(user_id=user.id)
        db.add(settings)
    settings.enabled_plugins = sorted(set(settings.enabled_plugins or []) | {name})
    await db.commit()
    return {"ok": True, "plugin_id": name}


@router.post("/rescan")
async def rescan_plugins(db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    ws_id = await workspace_id_for(db)
    results = await sync_plugins(db, ws_id)
    return {"ok": True, "found": len(results), "plugins": results}
