# Aether

A self-hosted, model-agnostic AI workspace with a polished conversational UI,
long-running agent tasks, multimodal files, image generation, plugins, skills,
and a matching administration console.

中文简介：Aether 是一套可自托管的 AI 工作台。它提供对话、流式思考、工作模式、
文件与知识库、图片生成、插件与 Skills，并通过管理员后台统一配置模型、权限与产品功能。

> Aether is an independent project. It does not include third-party product
> trademarks, logos, model weights, API keys, user data, or provider accounts.

## Highlights

- Unified streaming for answer text, reasoning, tools, usage, and errors.
- Chat and Work modes with history, retry branches, editing, steering, and cancellation.
- Capability-driven providers; behavior is never selected by model or vendor name.
- OpenAI-compatible chat APIs plus Qwen, DeepSeek, GLM, and Kimi-compatible gateways.
- Image backends for OpenAI Images-compatible APIs, ComfyUI, Automatic1111,
  Forge/SD.Next, Stability AI, and local Diffusers-compatible pipelines.
- Automatic image-intent routing, LLM prompt refinement, and composition-aware
  aspect ratio selection.
- PDF, Word, PowerPoint, spreadsheet, SVG, image, audio, video, and text workflows.
- Projects, retrieval, memory, custom instructions, scheduled tasks, and artifacts.
- MCP tools, administrator-approved plugins, importable skills, and tool approvals.
- Central feature controls: disabled capabilities disappear from the user UI and
  reject new requests without interrupting work already in progress.
- Configurable product name, appearance, audio, search, sharing, quotas, and access.

## Architecture

```text
Browser (Next.js 14)
        │ unified HTTP + SSE
FastAPI API ── PostgreSQL
        ├──── Redis
        ├──── model/image/search/audio adapters
        ├──── agent + tool runtimes
        └──── local or external object storage
```

The browser only consumes the unified event and message-block protocols. Provider
wire formats stay inside adapters. See [ARCHITECTURE.md](ARCHITECTURE.md) and the
protocol documents in [docs/](docs/).

## Repository layout

```text
apps/api/       FastAPI service, Alembic migrations, backend tests
apps/web/       Next.js user application and /admin console
apps/worker/    reserved background-worker package
packages/       shared protocol and type packages
plugins/        plugin examples and manifests
scripts/        development, deployment, backup, and verification utilities
docs/           architecture, protocols, deployment, and test coverage
```

Runtime state is intentionally excluded from Git: databases, uploads, generated
files, model weights, caches, logs, credentials, and local environment files.

## Requirements

- Python 3.11+
- Node.js 20+
- PostgreSQL 16+
- Redis 6+
- Optional accelerator runtime for local image or inference providers

No NVIDIA-specific runtime is required. Accelerator access is isolated behind the
`AcceleratorAdapter`, including CPU, CUDA, ROCm, and Hygon DCU environments.

## Quick start

```bash
git clone <your-repository-url> aether
cd aether

cp .env.example .env
# Set a new SECRET_KEY and review DATABASE_URL before continuing.

python3 -m venv .venv
source .venv/bin/activate
pip install -r apps/api/requirements.txt

cd apps/web
npm ci
cd ../..

bash scripts/dev.sh
```

Open <http://localhost:3000>. The first registered account becomes the owner and
can configure providers, models, image backends, plugins, and product permissions
under `/admin`.

For containers:

```bash
export SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
export POSTGRES_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
docker compose up --build
```

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for notebook hosts, persistent model
directories, service startup, reverse proxies, and production notes.

## Provider configuration

1. Register the initial owner.
2. Open **Admin → Providers** and add an endpoint and API key.
3. Open **Admin → Models**, add the provider model ID, then run **Probe**.
4. Review detected capabilities and set a default model.
5. Configure independent image, search, retrieval, and audio providers as needed.

Secrets are encrypted at rest, never returned to the browser, and redacted from
application logs. Use a unique `SECRET_KEY`; changing it invalidates encrypted
provider credentials and access tokens.

## Image providers and aspect ratios

Image generation is separate from chat providers. Supported adapter families:

- OpenAI Images-compatible JSON, base64, and URL responses
- ComfyUI queue/history/view APIs and custom workflow templates
- Automatic1111, Forge, and SD.Next
- Stability AI v2beta
- Local Diffusers-compatible pipelines

Users can select a ratio or leave it on **Auto**. In Auto mode the prompt optimizer
returns a composition-aware ratio; explicit ratios in the prompt take precedence,
with a deterministic fallback for common portrait, full-body, wallpaper, avatar,
landscape, and banner requests. Width and height remain normalized through the
same provider-neutral request object used by existing adapters.

## Feature controls

**Admin → Features & access** controls the user product surface. A disabled feature:

- is removed from navigation and composer actions after settings refresh;
- rejects new API requests for every account, including an administrator using the
  normal user surface;
- leaves historical content readable; and
- does not cancel streams, image jobs, or Work runs that already started.

Administrative control-plane operations remain available where required for setup
and provider testing.

## Development and verification

```bash
# Backend unit and integration tests
cd apps/api && python3 -m pytest -q

# Frontend typecheck and production build
cd apps/web && npx tsc --noEmit
npm run build

# Optional browser E2E; start the stack first
npx playwright test

# Scan tracked source candidates before publishing
cd ../.. && python3 scripts/check_secrets.py
```

Tests use mock providers and placeholder credentials; they do not require real API
keys or transmit prompts to external services. Current coverage is summarized in
[docs/TEST_MATRIX.md](docs/TEST_MATRIX.md).

## Security and data handling

Read [SECURITY.md](SECURITY.md) before exposing a deployment to the Internet.
Important defaults:

- provider secrets are encrypted with the deployment `SECRET_KEY`;
- uploaded and generated content lives under `data/` and is not versioned;
- untrusted retrieved content is isolated from system/tool instructions;
- fetchers block private, link-local, metadata, and unsupported targets;
- tool execution is capability-gated, bounded, and approval-aware;
- public conversation sharing has an administrator kill switch.

Backups can contain user data and encrypted provider credentials. Treat every backup
as sensitive. See [docs/BACKUP.md](docs/BACKUP.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Architecture changes should preserve the
capability-driven adapter model and unified protocols.

## License

No license is granted by default. Add a license appropriate for the intended public
or private distribution before accepting external contributions.
