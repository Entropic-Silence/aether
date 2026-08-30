# Roadmap

Aether only exposes capabilities backed by working implementations. Incomplete
features remain hidden or disabled.

## Available

- Chat with unified text/reasoning streaming, retry branches, editing, usage,
  cancellation, files, citations, and model selection.
- Work mode with planning, tools, approvals, steering, progress, downloadable
  artifacts, and persistent results.
- Model/provider administration with capability probing and encrypted credentials.
- Files, previews, projects, retrieval, memory, custom instructions, and library.
- Image generation, editing, inpainting, prompt refinement, intent routing, and
  automatic or explicit aspect ratios.
- OpenAI Images-compatible, ComfyUI, Automatic1111/Forge/SD.Next, Stability AI,
  and local Diffusers-compatible image adapters.
- Search, deep research, audio provider interfaces, video preprocessing, tasks,
  sharing, quotas, logs, and workspace membership.
- MCP servers, plugins, skills, a bounded sandbox, and configurable approvals.
- Product-wide feature permissions and a matching administration console.
- Backup/restore scripts, Alembic migrations, backend integration tests, and
  Playwright browser tests.

## Next

- Production HA and multi-node operations guidance.
- Optional external object storage and vector-database implementations.
- Broader live compatibility validation for provider-specific image constraints.
- Additional agent runtime bridges through the existing provider interface.
- Accessibility, localization, and mobile-layout audit.
- Security hardening profiles for Internet-facing deployments.

## Contribution rules

- Extend capabilities and adapters; never branch on model/vendor names.
- Keep provider wire formats out of the browser.
- Add tests for new behavior and schema migrations for persistent changes.
- Do not commit model weights, runtime data, logs, real provider endpoints, or secrets.
