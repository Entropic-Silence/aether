#!/usr/bin/env bash
# Start the full local stack (Postgres, Redis, API with migrations, Web).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ -f "$ROOT/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

bash "$ROOT/scripts/restore_persistent_paths.sh"

export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://aether:aether_dev_pw@127.0.0.1:5432/aether}"
export SECRET_KEY="${SECRET_KEY:-dev-insecure-secret-key-change-me}"

echo "[dev] ensuring postgres is up..."
if command -v pg_lsclusters >/dev/null 2>&1; then
  if ! pg_isready -q 2>/dev/null; then
    pg_ctlcluster 16 main start || true
  fi
fi

echo "[dev] ensuring redis is up..."
if ! redis-cli ping >/dev/null 2>&1; then
  redis-server --daemonize yes --port 6379 >/dev/null 2>&1 || true
fi

echo "[dev] applying migrations..."
cd "$ROOT/apps/api"
python3 -m alembic upgrade head

echo "[dev] starting API on :8123 ..."
cd "$ROOT/apps/api"
python3 -m uvicorn aether_api.main:app --host 0.0.0.0 --port 8123 &
API_PID=$!

echo "[dev] starting Web on :3000 ..."
cd "$ROOT/apps/web"
if [ ! -d node_modules ]; then
  npm install
fi
npm run dev &
WEB_PID=$!

trap 'kill $API_PID $WEB_PID 2>/dev/null || true' INT TERM
echo "[dev] ready: web http://localhost:3000  api http://localhost:8123"
wait
