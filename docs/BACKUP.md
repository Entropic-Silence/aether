# Backup & Restore Runbook

Aether's durable state is:
1. **PostgreSQL** — all relational data (users, conversations, messages, models, etc.)
2. **Object storage** — uploaded/generated files (`data/storage/`)
3. **Local models** — large model weights (`data/models/`, referenced, not copied)

## Backup

```bash
bash scripts/backup.sh [destination-dir]
```

Default destination: `backups/aether-backup-<timestamp>/`. Produces:
- `db.dump` — `pg_dump -F c` (custom format, compressed)
- `storage.tar.gz` — the object-storage tree
- `models_path.txt` — path to the (large) model dir, by reference
- `env.example`, `TIMESTAMP`

Database connection is taken from `DATABASE_URL` (or the dev default). The
PostgreSQL password is read from `PG_PASSWORD` (falls back to the dev default).

## Restore

```bash
bash scripts/restore.sh <backup-dir>
```

Restores into the database named by `DATABASE_URL` by dropping and recreating
the `public` schema, then `pg_restore`. Object storage is unpacked over
`data/`. The target database must be owned by the connecting user.

After restoring a backup taken against an older schema, run:

```bash
cd apps/api && python3 -m alembic upgrade head
```

## Security notes

- Backups contain account records, conversations, messages, configuration,
  request metadata, and encrypted provider credentials. Treat the entire backup
  as sensitive even when provider values are encrypted.
- The model directory is intentionally not copied (tens of GB); it is recorded
  by path. Keep it on durable storage or re-download models.
- For point-in-time or multi-host setups, substitute your own `pg_dump`/WAL
  archiving; the scripts are a single-host convenience.
- Never commit a backup or include one in a distributable notebook/container
  image. Before publishing an image, reset the database and clear object storage,
  caches, logs, and shell/tool histories.
