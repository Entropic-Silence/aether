from __future__ import annotations

from typing import Any

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..config import get_settings
from ..deps import get_current_user
from ..errors import CapabilityUnsupportedError
from ..orm import Setting, User

FEATURE_SETTINGS_KEY = "feature_controls"

FEATURE_DEFAULTS: dict[str, bool] = {
    "chat": True,
    "work": True,
    "image_generation": True,
    "projects": True,
    "tasks": True,
    "library": True,
    "file_uploads": True,
    "plugins": True,
    "web_search": True,
    "deep_research": True,
    "memory": True,
    "custom_instructions": True,
    "audio": True,
}

POLICY_DEFAULTS: dict[str, Any] = {
    "registration_enabled": get_settings().allow_registration,
    "max_upload_mb": 100,
}

FEATURE_DISABLED_MESSAGES: dict[str, str] = {
    "chat": "对话功能已被管理员关闭 / Chat is disabled by the administrator",
    "work": "工作模式已被管理员关闭 / Work mode is disabled by the administrator",
    "image_generation": "图片生成功能已被管理员关闭 / Image generation is disabled by the administrator",
    "projects": "项目功能已被管理员关闭 / Projects are disabled by the administrator",
    "tasks": "任务功能已被管理员关闭 / Tasks are disabled by the administrator",
    "library": "资料库已被管理员关闭 / Library is disabled by the administrator",
    "file_uploads": "文件上传已被管理员关闭 / File uploads are disabled by the administrator",
    "plugins": "插件功能已被管理员关闭 / Plugins are disabled by the administrator",
    "web_search": "网页搜索已被管理员关闭 / Web search is disabled by the administrator",
    "deep_research": "深度研究已被管理员关闭 / Deep research is disabled by the administrator",
    "memory": "记忆功能已被管理员关闭 / Memory is disabled by the administrator",
    "custom_instructions": "自定义指令已被管理员关闭 / Custom instructions are disabled by the administrator",
    "audio": "语音功能已被管理员关闭 / Voice is disabled by the administrator",
}


async def get_feature_controls(db: AsyncSession) -> dict[str, Any]:
    row = await db.get(Setting, FEATURE_SETTINGS_KEY)
    stored = row.value if row and isinstance(row.value, dict) else {}
    stored_features = stored.get("features") if isinstance(stored.get("features"), dict) else {}
    stored_policies = stored.get("policies") if isinstance(stored.get("policies"), dict) else {}
    return {
        "features": {**FEATURE_DEFAULTS, **{k: bool(v) for k, v in stored_features.items() if k in FEATURE_DEFAULTS}},
        "policies": {**POLICY_DEFAULTS, **{k: v for k, v in stored_policies.items() if k in POLICY_DEFAULTS}},
    }


async def update_feature_controls(db: AsyncSession, patch: dict[str, Any]) -> dict[str, Any]:
    current = await get_feature_controls(db)
    features = patch.get("features")
    if isinstance(features, dict):
        current["features"].update({k: bool(v) for k, v in features.items() if k in FEATURE_DEFAULTS})
    policies = patch.get("policies")
    if isinstance(policies, dict):
        if "registration_enabled" in policies:
            current["policies"]["registration_enabled"] = bool(policies["registration_enabled"])
        if "max_upload_mb" in policies:
            current["policies"]["max_upload_mb"] = max(1, min(500, int(policies["max_upload_mb"])))
    row = await db.get(Setting, FEATURE_SETTINGS_KEY)
    if row is None:
        db.add(Setting(key=FEATURE_SETTINGS_KEY, value=current))
    else:
        row.value = current
    await db.commit()
    return current


async def feature_enabled(db: AsyncSession, key: str) -> bool:
    controls = await get_feature_controls(db)
    return bool(controls["features"].get(key, True))


async def ensure_feature(db: AsyncSession, key: str, user: User | None = None) -> None:
    # Administrative roles keep access to the control plane, but the regular
    # product surface follows the same feature policy for every role.  This is
    # intentionally checked only at request creation; an already-running chat
    # stream or work run is not interrupted when an administrator flips a flag.
    if not await feature_enabled(db, key):
        raise CapabilityUnsupportedError(
            FEATURE_DISABLED_MESSAGES.get(
                key, f"{key.replace('_', ' ').title()} is disabled by the administrator",
            )
        )


def feature_dependency(key: str):
    async def dependency(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> None:
        await ensure_feature(db, key, user)

    return dependency
