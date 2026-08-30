# Deployment

## Environment

Copy `.env.example` to `.env` and replace every placeholder. At minimum:

- `SECRET_KEY`: unique random value, at least 32 bytes;
- `DATABASE_URL`: PostgreSQL connection URL;
- `API_PROXY_TARGET`: API origin used by the Next.js reverse proxy.

Never reuse a development secret in a published image. Provider credentials are
encrypted with `SECRET_KEY`; rotating it requires re-entering those credentials.

## Conventional host

```bash
cd apps/api
python3 -m alembic upgrade head
python3 -m uvicorn aether_api.main:app --host 0.0.0.0 --port 8123

cd ../web
npm ci
npm run build
npm run start
```

Run PostgreSQL and Redis under the host's normal service manager. Put a TLS reverse
proxy in front of the web service and do not expose PostgreSQL or Redis publicly.

## Docker Compose

Set `SECRET_KEY` and `POSTGRES_PASSWORD`, then run:

```bash
docker compose up --build
```

The Compose file is a single-host baseline, not an HA topology.

## Notebook platforms

`scripts/start_services.sh` starts PostgreSQL and Redis when host commands are
available, applies migrations, and launches API/Web services. If the notebook exposes
the standard Jupyter terminal API, the launcher delegates processes to a
Jupyter-owned terminal so they can survive an SSH disconnect.

```bash
cd /path/to/aether
bash scripts/start_services.sh
```

When `SECRET_KEY` is unset, this launcher creates a random deployment key under
`data/.secret_key`. The `data/` directory must remain private and persistent.

## Persistent model storage

Model weights are not part of this repository. To link a persistent directory:

```bash
export AETHER_PERSISTED_MODELS_DIR=/persistent/path/models
bash scripts/restore_persistent_paths.sh
```

The script only creates `data/models` when no file, directory, or link already
occupies that path. Configure local image models in the admin console after the
weights are available.

## Production checklist

- Use unique database and application secrets.
- Keep `.env`, `data/`, backups, logs, caches, and model weights outside Git.
- Restrict database, Redis, model APIs, ComfyUI, and sandbox endpoints by network.
- Disable open registration after the initial owner is created.
- Review Admin → Features & access, sharing, quotas, search, audio, and sandbox.
- Configure backup retention and test restore on a separate database.
- Terminate TLS at a trusted reverse proxy.
- Monitor disk use for uploads, generated media, sandbox outputs, and logs.
- Run `python3 scripts/check_secrets.py` before publishing a source archive.
