from __future__ import annotations

import os
import json
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..orm import Plugin

REQUIRED_FIELDS = ("id", "name", "version", "entrypoint")
KNOWN_CAPABILITIES = {
    "models", "tools", "skills", "search", "sandbox", "storage",
    "image", "agent_runtime", "ui_extension",
}


def plugins_root() -> Path:
    env = os.environ.get("PLUGINS_ROOT", "")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[4] / "plugins"


def validate_manifest(manifest: dict) -> list[str]:
    problems = []
    for field in REQUIRED_FIELDS:
        if not manifest.get(field):
            problems.append(f"missing required field: {field}")
    perms = manifest.get("permissions")
    if perms is not None and not isinstance(perms, list):
        problems.append("permissions must be a list")
    caps = manifest.get("capabilities")
    if caps is not None:
        if not isinstance(caps, list):
            problems.append("capabilities must be a list")
        else:
            unknown = [c for c in caps if c not in KNOWN_CAPABILITIES]
            if unknown:
                problems.append(f"unknown capabilities: {', '.join(unknown)}")
    api_version = manifest.get("api_version")
    if api_version is not None and int(str(api_version).split(".")[0] or 0) > 1:
        problems.append(f"unsupported plugin api_version: {api_version}")
    return problems


def discover_manifests() -> list[dict]:
    root = plugins_root()
    out = []
    if not root.exists():
        return out
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        manifest_path = child / "plugin.yaml"
        if not manifest_path.exists():
            manifest_path = child / "plugin.yml"
        if not manifest_path.exists():
            package_path = child / "package.json"
            if not package_path.exists():
                continue
            try:
                package = json.loads(package_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as e:
                out.append({"manifest": {"id": child.name, "name": child.name},
                            "problems": [f"invalid package.json: {e}"], "path": str(package_path)})
                continue
            keywords = package.get("keywords") or []
            dsh = package.get("dsh") or package.get("cordis") or {}
            if "dsh-plugin" not in keywords and not dsh and not str(package.get("name", "")).startswith("@deepseek-ai/"):
                continue
            capabilities = list(dsh.get("capabilities") or []) if isinstance(dsh, dict) else []
            if (child / "skills").exists() and "skills" not in capabilities:
                capabilities.append("skills")
            manifest = {
                "id": package.get("name") or child.name,
                "name": package.get("displayName") or package.get("name") or child.name,
                "version": package.get("version", ""),
                "entrypoint": package.get("main") or package.get("module") or "package.json",
                "capabilities": capabilities,
                "permissions": list(dsh.get("permissions") or []) if isinstance(dsh, dict) else [],
                "format": "deepseek-harness-cordis",
                "developer_preview": True,
            }
            out.append({"manifest": manifest, "problems": validate_manifest(manifest),
                        "path": str(package_path)})
            continue
        try:
            manifest = yaml.safe_load(manifest_path.read_text()) or {}
        except yaml.YAMLError as e:
            out.append({"manifest": {"id": child.name, "name": child.name},
                        "problems": [f"invalid YAML: {e}"], "path": str(manifest_path)})
            continue
        if not isinstance(manifest, dict):
            out.append({"manifest": {"id": child.name, "name": child.name},
                        "problems": ["manifest must be a mapping"], "path": str(manifest_path)})
            continue
        out.append({"manifest": manifest, "problems": validate_manifest(manifest),
                    "path": str(manifest_path)})
    return out


async def sync_plugins(db: AsyncSession, workspace_id: str) -> list[dict]:
    """Re-scan the plugins directory and refresh the registry table."""
    discovered = discover_manifests()
    rows = await db.execute(select(Plugin).where(Plugin.workspace_id == workspace_id))
    existing = {p.plugin_id: p for p in rows.scalars().all()}

    results = []
    seen = set()
    for item in discovered:
        manifest = item["manifest"]
        pid = str(manifest.get("id") or "")
        if not pid:
            results.append({"plugin_id": None, "name": str(manifest.get("name", "")),
                            "status": "invalid", "problems": item["problems"] or ["missing plugin id"],
                            "capabilities": []})
            continue
        seen.add(pid)
        status = "invalid" if item["problems"] else "valid"
        p = existing.get(pid)
        if p is None:
            p = Plugin(workspace_id=workspace_id, plugin_id=pid)
            db.add(p)
        p.name = str(manifest.get("name", pid))
        p.version = str(manifest.get("version", ""))
        p.manifest = {**manifest, "_path": item["path"]}
        p.status = status
        p.problems = item["problems"]
        results.append({"plugin_id": pid, "name": p.name, "status": status,
                        "problems": item["problems"],
                        "capabilities": manifest.get("capabilities") or []})
    for pid, p in existing.items():
        if pid not in seen:
            await db.delete(p)
    await db.commit()
    return results
