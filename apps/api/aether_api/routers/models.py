from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..adapters import build_adapter
from ..db import get_db
from ..deps import get_default_workspace, require_admin
from ..errors import NotFoundError
from ..orm import Model, Provider, User, default_capabilities
from ..schemas import ModelIn, ModelOut, ModelPatch

router = APIRouter(prefix="/models", tags=["models"])


def _to_out(m: Model, provider_name: str = "") -> ModelOut:
    out = ModelOut.model_validate(m)
    out.effective_capabilities = m.effective_caps()
    out.provider_name = provider_name
    return out


async def _provider_name(db: AsyncSession, provider_id: str) -> str:
    p = await db.get(Provider, provider_id)
    return p.name if p else ""


@router.get("", response_model=list[ModelOut])
async def list_models(db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    ws = await get_default_workspace(db)
    rows = await db.execute(select(Model).where(Model.workspace_id == ws.id).order_by(Model.created_at))
    models = rows.scalars().all()
    names = {}
    for m in models:
        if m.provider_id not in names:
            names[m.provider_id] = await _provider_name(db, m.provider_id)
    return [_to_out(m, names.get(m.provider_id, "")) for m in models]


@router.post("", response_model=ModelOut, status_code=201)
async def create_model(body: ModelIn, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    ws = await get_default_workspace(db)
    provider = await db.get(Provider, body.provider_id)
    if not provider:
        raise NotFoundError("Provider not found")
    caps = default_capabilities()
    caps.update(body.capabilities or {})
    model = Model(
        workspace_id=ws.id,
        provider_id=body.provider_id,
        model_id=body.model_id,
        display_name=body.display_name or body.model_id,
        description=body.description,
        icon=body.icon,
        model_family=body.model_family,
        model_type=body.model_type,
        category=body.category,
        context_window=body.context_window,
        max_output_tokens=body.max_output_tokens,
        enabled=body.enabled,
        is_default=body.is_default,
        priority=body.priority,
        weight=body.weight,
        generation_defaults=body.generation_defaults,
        extra_body=body.extra_body,
        capabilities=caps,
        capability_overrides=body.capability_overrides,
    )
    db.add(model)
    await db.flush()
    if body.is_default:
        await _clear_other_defaults(db, ws.id, except_id=model.id)
    await db.commit()
    await db.refresh(model)
    return _to_out(model, provider.name)


async def _clear_other_defaults(db: AsyncSession, workspace_id: str, except_id: str | None = None) -> None:
    rows = await db.execute(select(Model).where(Model.workspace_id == workspace_id, Model.is_default.is_(True)))
    for m in rows.scalars().all():
        if m.id != except_id:
            m.is_default = False


@router.patch("/{model_id}", response_model=ModelOut)
async def update_model(model_id: str, body: ModelPatch, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    model = await db.get(Model, model_id)
    if not model:
        raise NotFoundError("Model not found")
    data = body.model_dump(exclude_unset=True)
    if data.get("is_default"):
        await _clear_other_defaults(db, model.workspace_id, except_id=model.id)
    for k, v in data.items():
        setattr(model, k, v)
    await db.commit()
    await db.refresh(model)
    return _to_out(model, await _provider_name(db, model.provider_id))


@router.delete("/{model_id}", status_code=204)
async def delete_model(model_id: str, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    model = await db.get(Model, model_id)
    if not model:
        raise NotFoundError("Model not found")
    await db.delete(model)
    await db.commit()


@router.post("/{model_id}/probe", response_model=ModelOut)
async def probe_model(model_id: str, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    """Capability probe: exercise basic chat + streaming, report results.

    Results are written to capabilities but flagged as probe-derived; an admin
    can override any field. Never fully trusted automatically.
    """
    from datetime import datetime, timezone

    model = await db.get(Model, model_id)
    if not model:
        raise NotFoundError("Model not found")
    provider = await db.get(Provider, model.provider_id)
    if not provider:
        raise NotFoundError("Provider not found")
    adapter = build_adapter(provider)
    report: dict = {"basic_chat": "failed", "streaming": "failed", "system_prompt": "failed"}
    try:
        try:
            resp = await adapter.chat(
                [{"role": "system", "content": "Reply with the single word: ok"},
                 {"role": "user", "content": "ping"}],
                model_id=model.model_id, generation={"max_tokens": 8},
            )
            ok = bool(resp.get("choices"))
            report["basic_chat"] = "supported" if ok else "failed"
            report["system_prompt"] = "supported" if ok else "uncertain"
        except Exception:
            pass
        try:
            saw_delta = False
            async for ev in adapter.stream_chat(
                [{"role": "user", "content": "Say hi"}],
                model_id=model.model_id, generation={"max_tokens": 8},
            ):
                if ev["type"] in ("text.delta", "reasoning.delta"):
                    saw_delta = True
                if ev["type"] == "done":
                    break
            report["streaming"] = "supported" if saw_delta else "failed"
        except Exception:
            pass
    finally:
        await adapter.aclose()

    caps = dict(model.capabilities or {})
    caps["streaming"] = report["streaming"] == "supported"
    caps["system_prompt"] = report["system_prompt"] == "supported"
    model.capabilities = caps
    model.probe_status = "probed"
    model.probed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(model)
    out = _to_out(model, provider.name)
    out.effective_capabilities["_probe_report"] = report
    return out


@router.post("/{model_id}/test")
async def test_model(model_id: str, prompt: str = "Hello", db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    """Playground-style non-streaming completion for compatibility debugging."""
    import time

    model = await db.get(Model, model_id)
    if not model:
        raise NotFoundError("Model not found")
    provider = await db.get(Provider, model.provider_id)
    if not provider:
        raise NotFoundError("Provider not found")
    adapter = build_adapter(provider)
    started = time.monotonic()
    try:
        resp = await adapter.chat(
            [{"role": "user", "content": prompt}],
            model_id=model.model_id, generation=model.generation_defaults, extra_body=model.extra_body,
        )
        latency = int((time.monotonic() - started) * 1000)
        choice = (resp.get("choices") or [{}])[0]
        return {
            "ok": True,
            "text": (choice.get("message") or {}).get("content", ""),
            "usage": resp.get("usage"),
            "latency_ms": latency,
            "raw": resp,
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": getattr(e, "to_dict", lambda: {"message": str(e)})()}
    finally:
        await adapter.aclose()
