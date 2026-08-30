#!/usr/bin/env bash
# Launch API + Web fully detached (survives shell exit). Logs in /tmp.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ -f "$ROOT/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

# Accelerator runtimes may not be inherited by detached notebook terminals.
DTK_ENV_FILE="${DTK_ENV_FILE:-/opt/dtk/env.sh}"
if [ -f "$DTK_ENV_FILE" ]; then
  # shellcheck disable=SC1090
  set +u
  source "$DTK_ENV_FILE"
  set -u
fi

# Some notebook platforms terminate descendants of a closed SSH session.
# Delegate startup to a Jupyter-owned terminal when its API is available.
if [ "${AETHER_JUPYTER_CHILD:-0}" != "1" ] && [ -f "$ROOT/scripts/start_via_jupyter.py" ]; then
  if python3 "$ROOT/scripts/start_via_jupyter.py"; then
    exit 0
  fi
  echo "Jupyter process delegation failed; falling back to this shell." >&2
fi

export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://aether:aether_dev_pw@127.0.0.1:5432/aether}"
export ALLOW_REGISTRATION="${ALLOW_REGISTRATION:-false}"

if [ -z "${SECRET_KEY:-}" ]; then
  secret_file="${AETHER_SECRET_FILE:-$ROOT/data/.secret_key}"
  mkdir -p "$(dirname "$secret_file")"
  if [ ! -s "$secret_file" ]; then
    python3 -c 'import secrets; print(secrets.token_urlsafe(48))' >"$secret_file"
    chmod 600 "$secret_file"
  fi
  export SECRET_KEY
  SECRET_KEY="$(tr -d '\r\n' <"$secret_file")"
fi

bash "$ROOT/scripts/restore_persistent_paths.sh"

kill_port() {
  # Kill whatever listens on $1 (hex port), via /proc (no ss/lsof needed).
  local hexport
  hexport=$(printf '%04X' "$1")
  local inodes
  inodes=$(awk -v p="$hexport" '$2 ~ ":"p"$" && $4 == "0A" {print $10}' /proc/net/tcp /proc/net/tcp6 2>/dev/null)
  for inode in $inodes; do
    for fd in /proc/[0-9]*/fd/*; do
      if [ "$(readlink "$fd" 2>/dev/null)" = "socket:[$inode]" ]; then
        local pid
        pid=$(echo "$fd" | cut -d/ -f3)
        kill -9 "$pid" 2>/dev/null || true
        break
      fi
    done
  done
}

pg_isready -q || pg_ctlcluster 16 main start >/dev/null 2>&1 || true
redis-cli ping >/dev/null 2>&1 || redis-server --daemonize yes --port 6379 >/dev/null 2>&1 || true

cd "$ROOT/apps/api"
python3 -m alembic upgrade head >/dev/null 2>&1

kill_port 8123; sleep 1
setsid nohup python3 -m uvicorn aether_api.main:app --host 0.0.0.0 --port 8123 \
  >/tmp/aether-api.log 2>&1 < /dev/null &

kill_port 3000; sleep 1
cd "$ROOT/apps/web"
if [ -f .next/standalone/server.js ]; then
  mkdir -p .next/standalone/.next/static .next/standalone/public
  cp -a .next/static/. .next/standalone/.next/static/
  cp -a public/. .next/standalone/public/
  setsid nohup env PORT=3000 HOSTNAME=0.0.0.0 node .next/standalone/server.js \
    >/tmp/aether-web.log 2>&1 < /dev/null &
else
  setsid nohup npm run start >/tmp/aether-web.log 2>&1 < /dev/null &
fi

api_health=""
for ((attempt = 1; attempt <= 30; attempt++)); do
  api_health=$(curl -fsS -m 2 http://127.0.0.1:8123/api/health 2>/dev/null || true)
  [ -n "$api_health" ] && break
  sleep 1
done

web_status="000"
for ((attempt = 1; attempt <= 30; attempt++)); do
  web_status=$(curl -sS -m 2 -o /dev/null -w '%{http_code}' http://127.0.0.1:3000/ 2>/dev/null || true)
  [ "$web_status" != "000" ] && break
  sleep 1
done

echo "api:  ${api_health:-unavailable}"
echo "web:  HTTP $web_status"
