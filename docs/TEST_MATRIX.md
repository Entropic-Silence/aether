# Test and Compatibility Matrix

This document intentionally contains no real provider endpoints, account identifiers,
API keys, user prompts, user data, or host-specific benchmark results.

## Automated backend coverage

| Area | Coverage |
|---|---|
| Authentication and roles | registration, login, token validation, ownership |
| Feature controls | UI settings, server denial, historical access, admin control plane |
| Conversations | creation, active branches, edit, retry, error persistence, cancellation |
| Streaming | reasoning deltas, text deltas, tool events, usage, completion, failures |
| Providers and models | CRUD, capability probe, default selection, encrypted secrets |
| Files and projects | MIME detection, extraction, preview, storage, project context |
| Retrieval and memory | chunking, injection order, enable/disable behavior |
| Tools and sandbox | parsing, limits, execution, approvals, generated artifacts |
| Search and research | routing, fallback, SSRF rules, citations, report pipeline |
| Image generation | adapter envelopes, workflow rendering, intent classification, ratios |
| Work mode | planning, runtime events, steering, cancellation, result persistence |
| Plugins, MCP, skills | validation, discovery, import, enablement, permission gating |
| Tasks and media | schedules, artifacts, audio configuration, video preprocessing |
| Sharing and quotas | public/private access, kill switch, metering, limits |

Run:

```bash
cd apps/api
python3 -m pytest -q
```

Tests use mock services and placeholder credentials. They do not contact production
model providers.

## Frontend verification

```bash
cd apps/web
npx tsc --noEmit
npm run build
npx playwright test
```

The browser suite covers the main composer, streaming, retry, model selection, tool
execution, library, projects, and sharing surfaces.

## Provider compatibility contract

Chat providers must normalize into the unified streaming protocol documented in
[MODEL_PROTOCOL.md](MODEL_PROTOCOL.md). Image providers consume the common
`ImageParams` object and may expose capability flags for text-to-image,
image-to-image, inpainting, negative prompts, seeds, steps, and guidance.

Supported adapter families:

- OpenAI-compatible chat and embeddings
- OpenAI Images-compatible responses
- ComfyUI API workflows, including custom templates
- Automatic1111, Forge, and SD.Next
- Stability AI v2beta
- Local Diffusers-compatible pipelines

Before enabling an untested provider in production, validate:

1. authentication and error redaction;
2. streaming termination and usage reporting;
3. tool-call serialization if applicable;
4. context and output limits;
5. supported image dimensions/aspect ratios; and
6. timeout, overload, and retry behavior.
