# Contributing

## Development setup

Follow the Quick start in [README.md](README.md). Use mock providers and placeholder
credentials for tests.

## Before submitting changes

```bash
python3 scripts/check_secrets.py
cd apps/api && python3 -m pytest -q
cd ../web && npx tsc --noEmit && npm run build
```

## Engineering rules

- Extend adapters and capability flags; never branch on model/vendor names.
- Provider wire formats must not reach the browser.
- Messages are typed blocks, not a single content string.
- Schema changes require a reviewed Alembic migration.
- Do not weaken tests to make a change pass.
- Hide unsupported features instead of implementing placeholders.
- Keep secrets, endpoints, account data, logs, model weights, and runtime files out
  of commits and fixtures.
- Document new configuration fields in `.env.example` and README/docs.

## Pull requests

Keep each change focused. Explain behavior, compatibility impact, migrations, tests,
and screenshots for visible UI changes. Security-sensitive reports should follow
[SECURITY.md](SECURITY.md) instead of a public issue.
