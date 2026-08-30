#!/usr/bin/env bash
# Back up Aether: PostgreSQL dump + object storage + config into one archive.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TS="$(date +%Y%m%d-%H%M%S)"
DEST="${1:-$ROOT/backups/aether-backup-$TS}"
mkdir -p "$DEST"

DB_URL="${DATABASE_URL:-postgresql+asyncpg://aether:aether_dev_pw@127.0.0.1:5432/aether}"
# Derive pg params from the async URL (postgresql+asyncpg://user:pw@host:port/db)
PG_URI="${DB_URL#postgresql+asyncpg://}"
PG_USERPASS="${PG_URI%%@*}"
PG_HOSTDB="${PG_URI#*@}"
PG_USER="${PG_USERPASS%%:*}"
PG_HOSTPORT="${PG_HOSTDB%%/*}"
PG_DB="${PG_HOSTDB#*/}"
PG_HOST="${PG_HOSTPORT%%:*}"
PG_PORT="${PG_HOSTPORT##*:}"

echo "[backup] dumping PostgreSQL db '$PG_DB' from $PG_HOST:$PG_PORT"
PGPASSWORD="${PG_PASSWORD:-aether_dev_pw}" pg_dump -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" \
  -d "$PG_DB" -F c -f "$DEST/db.dump"

if [ -d "$ROOT/data/storage" ]; then
  echo "[backup] archiving object storage"
  tar -czf "$DEST/storage.tar.gz" -C "$ROOT/data" storage
fi

if [ -d "$ROOT/data/models" ]; then
  echo "[backup] noting model dir (large; copied by reference)"
  echo "$ROOT/data/models" > "$DEST/models_path.txt"
fi

cp "$ROOT/.env.example" "$DEST/env.example" 2>/dev/null || true
echo "$TS" > "$DEST/TIMESTAMP"
echo "[backup] complete: $DEST"
