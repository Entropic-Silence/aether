#!/usr/bin/env bash
# Restore Aether from a backup produced by scripts/backup.sh.
# Usage: scripts/restore.sh <backup-dir>
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${1:?usage: restore.sh <backup-dir>}"
[ -f "$SRC/db.dump" ] || { echo "no db.dump in $SRC"; exit 1; }

DB_URL="${DATABASE_URL:-postgresql+asyncpg://aether:aether_dev_pw@127.0.0.1:5432/aether}"
PG_URI="${DB_URL#postgresql+asyncpg://}"
PG_USERPASS="${PG_URI%%@*}"
PG_HOSTDB="${PG_URI#*@}"
PG_USER="${PG_USERPASS%%:*}"
PG_HOSTPORT="${PG_HOSTDB%%/*}"
PG_DB="${PG_HOSTDB#*/}"
PG_HOST="${PG_HOSTPORT%%:*}"
PG_PORT="${PG_HOSTPORT##*:}"

echo "[restore] clearing schema in db '$PG_DB'"
export PGPASSWORD="${PG_PASSWORD:-aether_dev_pw}"
psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" \
  -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO $PG_USER;"

echo "[restore] restoring dump"
pg_restore -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" --no-owner "$SRC/db.dump"

if [ -f "$SRC/storage.tar.gz" ]; then
  echo "[restore] restoring object storage"
  mkdir -p "$ROOT/data"
  tar -xzf "$SRC/storage.tar.gz" -C "$ROOT/data"
fi

echo "[restore] complete. Run 'alembic upgrade head' if schema changed since the backup."
