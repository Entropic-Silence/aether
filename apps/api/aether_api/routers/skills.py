from __future__ import annotations

import os
from pathlib import Path

import yaml
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..deps import get_current_user, require_admin
from ..errors import NotFoundError, ValidationError_
from ..orm import Skill, User
from .deps_helper import workspace_id_for

router = APIRouter(prefix="/skills", tags=["skills"])

SCOPES = {"global", "workspace", "project", "user", "model", "tool", "image_model"}


def _parse_skill_markdown(text: str, fallback_name: str) -> dict:
    metadata: dict = {}
    body = text.strip()
    if body.startswith("---"):
        parts = body.split("---", 2)
        if len(parts) == 3:
            parsed = yaml.safe_load(parts[1]) or {}
            if isinstance(parsed, dict):
                metadata = parsed
            body = parts[2].strip()
    name = str(metadata.get("name") or fallback_name).strip().lower().replace("_", "-").replace(" ", "-")
    if not name or not body:
        raise ValidationError_("Skill markdown requires a name and instructions")
    return {
        "name": name[:200],
        "version": str(metadata.get("version", "1.0.0"))[:40],
        "description": str(metadata.get("description", "")),
        "instructions": body,
        "trigger": str(metadata.get("when-to-use") or metadata.get("trigger") or ""),
        "capabilities": list(metadata.get("capabilities") or []),
        "priority": int(metadata.get("priority", 100)),
        "scope": "global",
        "enabled": not bool(metadata.get("disabled", False)),
    }


def _deepseek_skill_files() -> list[Path]:
    project_root = Path(os.environ.get("AETHER_ROOT", Path(__file__).resolve().parents[4]))
    dsh_home = Path(os.environ.get("DSH_HOME", "/root/.dsh"))
    agents_home = Path(os.environ.get("AGENTS_HOME", "/root/.agents"))
    roots = [
        project_root / ".dsh" / "skills", project_root / ".agents" / "skills",
        dsh_home / "skills", agents_home / "skills", project_root / "plugins",
    ]
    found: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.glob("*/SKILL.md"):
            if path.is_file() and not path.is_symlink():
                found.append(path)
        for path in root.glob("*/skills/*/SKILL.md"):
            if path.is_file() and not path.is_symlink():
                found.append(path)
    return sorted(set(found))


class SkillIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    version: str = "1.0.0"
    description: str = ""
    instructions: str = ""
    trigger: str = ""
    capabilities: list[str] = []
    allowed_models: list[str] = []
    allowed_tools: list[str] = []
    input_schema: dict = {}
    output_schema: dict = {}
    priority: int = 100
    scope: str = "global"
    enabled: bool = True


class SkillPatch(BaseModel):
    name: str | None = None
    version: str | None = None
    description: str | None = None
    instructions: str | None = None
    trigger: str | None = None
    capabilities: list[str] | None = None
    allowed_models: list[str] | None = None
    allowed_tools: list[str] | None = None
    input_schema: dict | None = None
    output_schema: dict | None = None
    priority: int | None = None
    scope: str | None = None
    enabled: bool | None = None


def _to_out(s: Skill) -> dict:
    return {
        "id": s.id, "name": s.name, "version": s.version, "description": s.description,
        "instructions": s.instructions, "trigger": s.trigger,
        "capabilities": s.capabilities or [], "allowed_models": s.allowed_models or [],
        "allowed_tools": s.allowed_tools or [],
        "input_schema": s.input_schema or {}, "output_schema": s.output_schema or {},
        "priority": s.priority, "scope": s.scope, "source": s.source,
        "enabled": s.enabled, "created_at": s.created_at,
    }


@router.get("")
async def list_skills(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    rows = await db.execute(select(Skill).order_by(Skill.priority.asc(), Skill.created_at))
    return [_to_out(s) for s in rows.scalars().all()]


@router.post("", status_code=201)
async def create_skill(body: SkillIn, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    if body.scope not in SCOPES:
        raise ValidationError_(f"scope must be one of {sorted(SCOPES)}")
    s = Skill(workspace_id=await workspace_id_for(db), **body.model_dump())
    s.source = "manual"
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return _to_out(s)


@router.get("/{skill_id}")
async def get_skill(skill_id: str, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    s = await db.get(Skill, skill_id)
    if not s:
        raise NotFoundError("Skill not found")
    return _to_out(s)


@router.patch("/{skill_id}")
async def update_skill(skill_id: str, body: SkillPatch, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    s = await db.get(Skill, skill_id)
    if not s:
        raise NotFoundError("Skill not found")
    data = body.model_dump(exclude_unset=True)
    if "scope" in data and data["scope"] not in SCOPES:
        raise ValidationError_(f"scope must be one of {sorted(SCOPES)}")
    for k, v in data.items():
        setattr(s, k, v)
    await db.commit()
    await db.refresh(s)
    return _to_out(s)


@router.delete("/{skill_id}", status_code=204)
async def delete_skill(skill_id: str, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    s = await db.get(Skill, skill_id)
    if not s:
        raise NotFoundError("Skill not found")
    await db.delete(s)
    await db.commit()


@router.get("/{skill_id}/export")
async def export_skill(skill_id: str, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    s = await db.get(Skill, skill_id)
    if not s:
        raise NotFoundError("Skill not found")
    out = _to_out(s)
    out.pop("id", None)
    out.pop("created_at", None)
    return {"skill": out}


@router.post("/import", status_code=201)
async def import_skill(payload: dict, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    data = payload.get("skill") or payload
    if not data.get("name") or not data.get("instructions"):
        raise ValidationError_("Skill import requires name and instructions")
    scope = data.get("scope", "global")
    if scope not in SCOPES:
        raise ValidationError_(f"scope must be one of {sorted(SCOPES)}")
    s = Skill(
        workspace_id=await workspace_id_for(db),
        name=str(data["name"])[:200],
        version=str(data.get("version", "1.0.0"))[:40],
        description=str(data.get("description", "")),
        instructions=str(data["instructions"]),
        trigger=str(data.get("trigger", "")),
        capabilities=list(data.get("capabilities") or []),
        allowed_models=list(data.get("allowed_models") or []),
        allowed_tools=list(data.get("allowed_tools") or []),
        input_schema=dict(data.get("input_schema") or {}),
        output_schema=dict(data.get("output_schema") or {}),
        priority=int(data.get("priority", 100)),
        scope=scope,
        source=str(data.get("source", "file"))[:30] if data.get("source") in ("builtin", "git", "plugin") else "file",
        enabled=bool(data.get("enabled", True)),
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return _to_out(s)


class MarkdownSkillIn(BaseModel):
    filename: str = "skill.md"
    content: str = Field(min_length=1, max_length=500_000)


@router.post("/import-markdown", status_code=201)
async def import_markdown_skill(body: MarkdownSkillIn, db: AsyncSession = Depends(get_db),
                                _: User = Depends(require_admin)):
    fallback = Path(body.filename).stem
    if fallback.upper() == "SKILL":
        fallback = "imported-skill"
    data = _parse_skill_markdown(body.content, fallback)
    skill = Skill(workspace_id=await workspace_id_for(db), **data, source="deepseek-harness")
    db.add(skill)
    await db.commit()
    await db.refresh(skill)
    return _to_out(skill)


@router.post("/sync-deepseek", status_code=200)
async def sync_deepseek_skills(db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    """Import skills from DeepSeek Harness-compatible filesystem roots."""
    rows = await db.execute(select(Skill))
    existing = {s.name: s for s in rows.scalars().all() if s.source == "deepseek-harness"}
    imported = []
    for path in _deepseek_skill_files():
        data = _parse_skill_markdown(path.read_text(encoding="utf-8"), path.parent.name)
        skill = existing.get(data["name"])
        if skill is None:
            skill = Skill(workspace_id=await workspace_id_for(db), source="deepseek-harness")
            db.add(skill)
        for key, value in data.items():
            setattr(skill, key, value)
        imported.append(data["name"])
    await db.commit()
    return {"ok": True, "found": len(imported), "skills": imported}


async def global_skills_text(db: AsyncSession) -> str:
    rows = await db.execute(
        select(Skill).where(Skill.enabled.is_(True), Skill.scope == "global")
        .order_by(Skill.priority.asc())
    )
    parts = []
    for s in rows.scalars().all():
        if s.instructions.strip():
            parts.append(f"## Skill: {s.name}\n{s.instructions.strip()}")
    return "\n\n".join(parts)
