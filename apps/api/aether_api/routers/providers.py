from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..adapters import build_adapter
from ..db import get_db
from ..deps import get_default_workspace, require_admin
from ..errors import NotFoundError, ProviderError
from ..orm import Provider, User
from ..schemas import ProviderIn, ProviderOut
from ..security import encrypt_secret
import json

router = APIRouter(prefix="/providers", tags=["providers"])


def _to_out(p: Provider) -> ProviderOut:
    out = ProviderOut.model_validate(p)
    out.has_api_key = bool(p.api_key_enc)
    return out


@router.get("", response_model=list[ProviderOut])
async def list_providers(db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    ws = await get_default_workspace(db)
    rows = await db.execute(
        select(Provider).where(Provider.workspace_id == ws.id).order_by(Provider.created_at)
    )
    return [_to_out(p) for p in rows.scalars().all()]


@router.post("", response_model=ProviderOut, status_code=201)
async def create_provider(body: ProviderIn, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    ws = await get_default_workspace(db)
    provider = Provider(
        workspace_id=ws.id,
        kind=body.kind,
        name=body.name,
        base_url=body.base_url,
        api_key_enc=encrypt_secret(body.api_key),
        headers_enc=encrypt_secret(json.dumps(body.headers)) if body.headers else "",
        proxy=body.proxy,
        timeout_ms=body.timeout_ms,
        retry=body.retry,
        concurrency=body.concurrency,
        organization=body.organization,
        project=body.project,
        enabled=body.enabled,
    )
    db.add(provider)
    await db.commit()
    await db.refresh(provider)
    return _to_out(provider)


@router.patch("/{provider_id}", response_model=ProviderOut)
async def update_provider(provider_id: str, body: ProviderIn, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    provider = await db.get(Provider, provider_id)
    if not provider:
        raise NotFoundError("Provider not found")
    provider.kind = body.kind
    provider.name = body.name
    provider.base_url = body.base_url
    if body.api_key:
        provider.api_key_enc = encrypt_secret(body.api_key)
    provider.headers_enc = encrypt_secret(json.dumps(body.headers)) if body.headers else ""
    provider.proxy = body.proxy
    provider.timeout_ms = body.timeout_ms
    provider.retry = body.retry
    provider.concurrency = body.concurrency
    provider.organization = body.organization
    provider.project = body.project
    provider.enabled = body.enabled
    await db.commit()
    await db.refresh(provider)
    return _to_out(provider)


@router.delete("/{provider_id}", status_code=204)
async def delete_provider(provider_id: str, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    provider = await db.get(Provider, provider_id)
    if not provider:
        raise NotFoundError("Provider not found")
    await db.delete(provider)
    await db.commit()


@router.get("/{provider_id}/remote-models", response_model=list[str])
async def remote_models(provider_id: str, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    provider = await db.get(Provider, provider_id)
    if not provider:
        raise NotFoundError("Provider not found")
    adapter = build_adapter(provider)
    try:
        return await adapter.list_models()
    except ProviderError:
        raise
    finally:
        await adapter.aclose()


@router.post("/{provider_id}/test")
async def test_provider(provider_id: str, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    provider = await db.get(Provider, provider_id)
    if not provider:
        raise NotFoundError("Provider not found")
    adapter = build_adapter(provider)
    try:
        models = await adapter.list_models()
        return {"ok": True, "models": models}
    except ProviderError as e:
        return {"ok": False, "error": e.to_dict()}
    finally:
        await adapter.aclose()
