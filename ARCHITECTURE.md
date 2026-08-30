# Aether — Architecture

Aether is a capability-driven, model-agnostic AI web platform that provides a
modern conversational and agentic workspace on top of arbitrary model providers
(including OpenAI-compatible endpoints and self-hosted inference servers).

Product identity (name, logo, icons, accent color) is fully configurable.
No vendor trademark is embedded. Internal vocabulary is generic:
`chat`, `work`, `research`, `project`, `library`.

## Top-level layout

```
apps/
  web/        Next.js user app (chat, library, projects, images, tasks)
  admin/      Admin console (Phase 1 ships inside apps/web under /admin;
              split into its own app when scope grows)
  api/        FastAPI backend, versioned under /api/v1
  worker/     Async task worker (Phase 2+)
packages/
  protocol/   Unified streaming event + message block protocol (TS + Py mirrors)
  shared/     Shared types / utilities
plugins/      Pluggable providers (models, tools, skills, search, image, sandbox)
docs/         Protocol & operations documentation
scripts/      Service launchers, environment checks
```

## Capability-driven core

```
Provider ──> Model ──> ModelCapabilities ──> Adapter ──> Unified Runtime Protocol
```

There is **no `if model == "<vendor>"` logic anywhere**. Feature visibility in
the UI is computed from:

```
ModelCapabilities ∧ UserPermissions ∧ InstalledTools ∧ WorkspaceSettings
```

### Degradation, not deception

If the primary model lacks a capability (vision/audio/video/i2i), the platform
may route to a configured fallback capability provider (vision model, STT,
video pipeline). Every degradation is surfaced in the UI
(e.g. "Reference image converted to description") and is configurable per
workspace.

## Layers

| Layer | Responsibility |
|---|---|
| UI (apps/web) | Renders Message Blocks + streaming events only. Knows nothing about vendors. |
| API (apps/api) | Auth, conversations, routing, orchestration, SSE event stream. |
| Model Router | Selects model by fixed id / fallback chain / capability filter / weights. Never switches mid-generation. |
| Provider Adapters | Translate unified requests to provider wire format; normalize responses to blocks. |
| Tool Runtime | ToolDefinition/ToolCall/ToolResult protocol; parses native/JSON/XML tool calls. |
| Agent Runtime | Pluggable harness. Two built-in engines: `native` (single loop) and `advanced` (plan-then-execute, the Work-mode core). External harnesses register via the same interface. |
| Sandbox | Isolated execution providers (bwrap/nsjail/docker/remote). Network OFF by default. |
| Retrieval | Embedding/Reranker/VectorStore providers; RAG scopes (chat/project/library/workspace/memory). |
| AcceleratorAdapter | `detect_accelerator()`, `get_device()`, `get_device_count()`, `get_device_memory()`, `get_utilization()` — CPU/CUDA/ROCm/Hygon DCU/Auto. |

## Streaming protocol (summary — full spec in docs/MODEL_PROTOCOL.md)

Frontend consumes only unified SSE events:

```
response.created | response.delta | response.completed
reasoning.started | reasoning.delta | reasoning.completed
block.started | block.delta | block.completed
tool.* | search.* | sandbox.* | artifact.created | error
```

Provider-native stream formats never reach the browser.

## Message model

`Message.blocks[]` — typed blocks (text, markdown, reasoning, code, image,
audio, video, file, citation, sources, tool_call, tool_result, search, chart,
table, artifact, writing, sandbox, progress, error). A message is never a
single `content: string`.

Conversations are **trees**: every message has `parent_id`; edit / regenerate /
branch create new leaves; a "current leaf" pointer defines the active path.

## Prompt pipeline (priority order)

```
System Safety → Workspace Prompt → Model Prompt → Project Instructions
→ Custom Instructions → Memory → Skills → Conversation
```

## Security invariants

- Provider API keys: encrypted at rest, never sent to browsers, redacted from logs.
- External web/file content is wrapped as `UNTRUSTED_EXTERNAL_CONTENT`;
  it can never issue tool calls or elevate privileges.
- Sandboxes: non-root, CPU/RAM/PID/time limits, filesystem isolation, network OFF by default.
- Web fetch: SSRF protection (deny private/link-local/metadata ranges), allow/deny rules, size & MIME limits.

## Error taxonomy

`PROVIDER_ERROR · MODEL_NOT_FOUND · MODEL_OVERLOADED · RATE_LIMIT ·
CONTEXT_OVERFLOW · TOOL_ERROR · TOOL_TIMEOUT · SEARCH_ERROR · FETCH_ERROR ·
SANDBOX_ERROR · FILE_ERROR · CAPABILITY_UNSUPPORTED · AUTH_ERROR ·
PERMISSION_ERROR · INTERNAL_ERROR`

User-facing messages are friendly; full detail stays in admin logs with
`request_id / trace_id`.

## Everything behind an interface

LLM, image, vision, audio, video, embedding, rerank, search, web fetch,
browser, sandbox, agent harness, storage, vector DB, auth, notification —
all are provider interfaces with default implementations; all replaceable.
