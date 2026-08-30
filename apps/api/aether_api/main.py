from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .errors import ApiError
from .routers import artifacts, audio, auth, branding, chat, conversations, files, images, logs, mcp, memory, models, plugins, projects, prompts, providers, research, search, settings_api, shares, skills, system, tasks, usage, work, workspaces

settings = get_settings()


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, version="0.1.0")

    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins or ["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def observability_middleware(request: Request, call_next):
        import time

        from .db import SessionLocal
        from .orm import RequestLog
        from .security import decode_access_token

        # Best-effort user attribution from the bearer token (no DB hit).
        user_id = None
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            claims = decode_access_token(auth[7:])
            if claims:
                user_id = claims.get("sub")
        request.state.user_id = user_id

        started = time.monotonic()
        response = await call_next(request)
        latency = int((time.monotonic() - started) * 1000)
        path = request.url.path
        if path not in ("/api/health",):
            try:
                async with SessionLocal() as db:
                    db.add(RequestLog(
                        user_id=user_id, method=request.method, path=path[:400],
                        status=response.status_code, latency_ms=latency,
                    ))
                    await db.commit()
            except Exception:  # noqa: BLE001
                pass
        return response

    @app.on_event("startup")
    async def warm_image_pipelines() -> None:
        import os
        import threading

        if os.environ.get("AETHER_SKIP_IMAGE_WARMUP") == "1":
            return

        from sqlalchemy import select

        from .db import SessionLocal
        from .orm import ImageModel
        from .services.imagegen import build_image_provider

        async def collect() -> list[tuple[str, str]]:
            try:
                async with SessionLocal() as db:
                    rows = await db.execute(
                        select(ImageModel).where(
                            ImageModel.enabled.is_(True),
                            ImageModel.provider_kind == "diffusers_local",
                        )
                    )
                    return [(m.model_ref, m.name) for m in rows.scalars().all() if m.model_ref]
            except Exception:  # noqa: BLE001
                return []

        targets = await collect()

        def loader():
            for ref, name in targets:
                try:
                    provider = build_image_provider("diffusers_local", ref)
                    provider._load()  # noqa: SLF001 - intentional warm-up
                    print(f"[startup] warmed image pipeline: {name}")
                except Exception as e:  # noqa: BLE001
                    print(f"[startup] image pipeline warm-up failed ({name}): {e}")

        if targets:
            threading.Thread(target=loader, daemon=True).start()

    @app.on_event("startup")
    async def start_task_scheduler() -> None:
        import asyncio
        import os

        if os.environ.get("AETHER_DISABLE_SCHEDULER") == "1":
            return
        from .services.tasks import scheduler_loop

        asyncio.create_task(scheduler_loop())

    @app.exception_handler(ApiError)
    async def api_error_handler(_: Request, exc: ApiError):
        return JSONResponse(status_code=exc.status_code, content={"error": exc.to_dict()})

    prefix = settings.api_prefix
    app.include_router(auth.router, prefix=prefix)
    app.include_router(providers.router, prefix=prefix)
    app.include_router(models.router, prefix=prefix)
    app.include_router(conversations.router, prefix=prefix)
    app.include_router(chat.router, prefix=prefix)
    app.include_router(files.router, prefix=prefix)
    app.include_router(projects.router, prefix=prefix)
    app.include_router(images.router, prefix=prefix)
    app.include_router(research.router, prefix=prefix)
    app.include_router(work.router, prefix=prefix)
    app.include_router(settings_api.router, prefix=prefix)
    app.include_router(memory.router, prefix=prefix)
    app.include_router(memory.settings_router, prefix=prefix)
    app.include_router(tasks.router, prefix=prefix)
    app.include_router(audio.router, prefix=prefix)
    app.include_router(artifacts.router, prefix=prefix)
    app.include_router(skills.router, prefix=prefix)
    app.include_router(mcp.router, prefix=prefix)
    app.include_router(plugins.router, prefix=prefix)
    app.include_router(shares.router, prefix=prefix)
    app.include_router(usage.router, prefix=prefix)
    app.include_router(workspaces.router, prefix=prefix)
    app.include_router(logs.router, prefix=prefix)
    app.include_router(search.router, prefix=prefix)
    app.include_router(prompts.router, prefix=prefix)
    app.include_router(system.router, prefix=prefix)
    app.include_router(branding.router, prefix=prefix)

    @app.get("/api/health")
    async def health():
        return {"ok": True, "service": settings.app_name}

    return app


app = create_app()
