from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..deps import get_current_user, require_admin
from ..orm import Model, Setting, User
from ..services.retrieval import get_retrieval_settings, update_retrieval_settings
from ..services.search import SEARCH_SETTINGS_KEY, build_router
from ..services.vision import get_vision_fallback_model, set_vision_fallback_model
from ..services.features import get_feature_controls, update_feature_controls

router = APIRouter(prefix="/settings", tags=["settings"])


DEFAULT_SEARCH_SETTINGS = {
    "providers": [
        {"kind": "mock", "priority": 100, "enabled": True},
    ],
}


@router.get("/ui")
async def ui_settings(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    """Feature flags for the frontend, derived from real configuration state."""
    from ..services.audio import get_stt_provider, get_tts_provider

    retrieval = await get_retrieval_settings(db)
    vision = await get_vision_fallback_model(db)
    row = await db.get(Setting, SEARCH_SETTINGS_KEY)
    search_settings = row.value if row and isinstance(row.value, dict) else DEFAULT_SEARCH_SETTINGS
    controls = await get_feature_controls(db)
    sharing_row = await db.get(Setting, "sharing")
    sharing_value = sharing_row.value if sharing_row and isinstance(sharing_row.value, dict) else {}
    return {
        "retrieval_configured": bool(retrieval.get("embedding_model_id")),
        "vision_fallback_configured": vision is not None,
        "search_configured": len(build_router(search_settings).providers) > 0,
        "stt_configured": await get_stt_provider(db) is not None,
        "tts_configured": await get_tts_provider(db) is not None,
        "features": controls["features"],
        "policies": controls["policies"],
        "public_sharing_enabled": sharing_value.get("public_enabled", True),
    }


@router.get("/features")
async def feature_controls(db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    return await get_feature_controls(db)


@router.patch("/features")
async def patch_feature_controls(body: dict, db: AsyncSession = Depends(get_db),
                                 _: User = Depends(require_admin)):
    return await update_feature_controls(db, body)


@router.get("/search")
async def search_settings(db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    row = await db.get(Setting, SEARCH_SETTINGS_KEY)
    settings = row.value if row and isinstance(row.value, dict) else DEFAULT_SEARCH_SETTINGS
    # never leak secrets to the client
    return {
        "providers": [
            {k: ("" if k == "api_key" else v) for k, v in p.items()}
            for p in settings.get("providers", [])
        ]
    }


@router.patch("/search")
async def patch_search(body: dict, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    providers = body.get("providers")
    if not isinstance(providers, list):
        from ..errors import ValidationError_

        raise ValidationError_("providers must be a list")
    for p in providers:
        if p.get("kind") not in ("mock", "searxng", "tavily", "brave", "serper"):
            from ..errors import ValidationError_

            raise ValidationError_(f"Unknown search provider kind: {p.get('kind')}")
    value = {"providers": providers}
    row = await db.get(Setting, SEARCH_SETTINGS_KEY)
    if row is None:
        db.add(Setting(key=SEARCH_SETTINGS_KEY, value=value))
    else:
        row.value = value
    await db.commit()
    return {"ok": True, "configured": len(build_router(value).providers) > 0}


@router.post("/search/test")
async def test_search(db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    row = await db.get(Setting, SEARCH_SETTINGS_KEY)
    settings = row.value if row and isinstance(row.value, dict) else DEFAULT_SEARCH_SETTINGS
    router_ = build_router(settings)
    try:
        outcome = await router_.search("test query", count=3)
        return {"ok": True, "provider": outcome.provider,
                "results": [{"url": r.url, "title": r.title} for r in outcome.results]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": getattr(e, "message", str(e))}


class RetrievalPatch(BaseModel):
    embedding_model_id: str | None = None
    chunk_size: int | None = None
    chunk_overlap: int | None = None
    top_k: int | None = None
    score_threshold: float | None = None


class VisionPatch(BaseModel):
    model_id: str | None = None


@router.get("/retrieval")
async def retrieval_settings(db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    return await get_retrieval_settings(db)


@router.patch("/retrieval")
async def patch_retrieval(body: RetrievalPatch, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    patch = body.model_dump(exclude_unset=True)
    if patch.get("embedding_model_id"):
        model = await db.get(Model, patch["embedding_model_id"])
        if not model:
            from ..errors import NotFoundError

            raise NotFoundError("Embedding model not found")
    return await update_retrieval_settings(db, patch)


@router.get("/vision-fallback")
async def vision_settings(db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    pair = await get_vision_fallback_model(db)
    if not pair:
        return {"model_id": None, "display_name": None}
    return {"model_id": pair[0].id, "display_name": pair[0].display_name}


@router.patch("/vision-fallback")
async def patch_vision(body: VisionPatch, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    if body.model_id:
        model = await db.get(Model, body.model_id)
        if not model or model.effective_caps().get("image_input") is not True:
            from ..errors import ValidationError_

            raise ValidationError_("Selected model does not have image_input capability")
    return await set_vision_fallback_model(db, body.model_id)
