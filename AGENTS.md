# Agent Guidelines

## Commands

- Backend tests: `cd apps/api && python3 -m pytest -q`
- Web typecheck: `cd apps/web && tsc --noEmit`
- Web build: `cd apps/web && npm run build`
- Full local stack: `bash scripts/dev.sh`
- Environment report (read-only): `bash scripts/check_env.sh`

## Hard rules

1. **Capability-driven only.** Never branch on model/vendor names
   (`if model == "qwen"` etc.). Extend adapters/capabilities instead.
2. **No fake implementations.** No dead buttons, no hardcoded demo data,
   no "TODO → done". Unimplemented = disabled or hidden.
3. **Never assume NVIDIA CUDA.** All device access via
   `aether_api/services/accelerator.py` (Hygon DCU host; DTK torch exposes
   the DCU through the CUDA API surface — still report `hygon_dcu`).
4. **Schema changes require Alembic migrations.**
   `cd apps/api && python3 -m alembic revision --autogenerate -m "..."`
   then review the generated file before `alembic upgrade head`.
5. **Secrets**: encrypt at rest (`security.encrypt_secret`), never return to
   clients, never log.
6. **Streaming**: providers emit only the unified event protocol
   (`docs/MODEL_PROTOCOL.md`); provider wire formats never reach the browser.
7. **Messages are blocks** (`message_blocks`), never a single content string.
8. Don't delete or weaken tests to make them pass; find the root cause.

## Layout

- `apps/api` FastAPI (`aether_api/`): routers/, adapters/, services/, orm.py
- `apps/web` Next.js app router: pages in `app/`, shared logic in
  `components/` and `lib/`
- Design docs: `docs/*.md`, `ARCHITECTURE.md`, `ROADMAP.md`

## Supported local environment

- Python 3.11+, Node 20+, PostgreSQL 16+, and Redis 6+.
- Docker is optional; notebook hosts without systemd can use
  `scripts/start_services.sh`.
- Database and proxy configuration belong in an untracked `.env`.
