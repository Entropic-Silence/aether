# Database

PostgreSQL is primary (SQLite for local dev via the same SQLAlchemy models +
Alembic migrations). Large binaries go to object storage; the DB stores
metadata. Conversations are **normalized**, not one big JSON blob.

## Tables (core)

```
users            id, email, password_hash, name, role, created_at
workspaces       id, name, settings{}, created_at
workspace_members workspace_id, user_id, role

providers        id, kind, name, base_url, api_key_enc, headers_enc{},
                 proxy, timeout_ms, retry{}, concurrency, enabled
models           id, provider_id, model_id, display_name, description, icon,
                 model_family, model_type, context_window, max_output_tokens,
                 enabled, is_default, priority, weight, generation_defaults{},
                 extra_body{}
model_capabilities model_id (PK), <capability columns>, probe_status,
                 probed_at, override:bool

conversations    id, workspace_id, user_id, title, mode(chat|work), pinned,
                 archived, temporary, project_id?, current_leaf_id?, created_at
messages         id, conversation_id, parent_id?, role, model_id?, status,
                 created_at            # tree via parent_id
message_blocks   id, message_id, seq, type, data{}
branches         id, conversation_id, leaf_message_id, name, active

projects         id, workspace_id, name, description, icon, instructions,
                 memory_mode, created_at
project_files    id, project_id, file_id        (uq project+file)

files            id, workspace_id, user_id, project_id?, name, mime,
                 kind(document|image|audio|video|data|other), size, sha256,
                 storage_key, status(uploaded|processing|extracted|indexed|failed),
                 error, extraction{pages,text,text_chars,notices,indexed_chunks},
                 created_at
file_chunks      id, file_id, chunk_index, text, embedding[], char_start
artifacts        id, conversation_id?, message_id?, kind, title, data_ref,
                 created_at

memories         id, user_id, project_id?, kind(explicit|semantic), content,
                 category, source, confidence, enabled, created_at, updated_at

tools            id, name, definition{}, risk, enabled
skills           id, name, version, manifest{}, enabled, scope
plugins          id, manifest{}, installed, enabled
mcp_servers      id, name, transport(stdio|http|sse), config_enc{}, enabled

tasks            id, user_id, prompt, schedule, timezone, model_id, project_id,
                 enabled, last_run, next_run
task_runs        id, task_id, status, result_ref, started_at, finished_at

usage_events     id, user_id, workspace_id, model_id, provider_id,
                 input_tokens, output_tokens, reasoning_tokens, cached_tokens,
                 image_count, audio_seconds, video_seconds,
                 search_requests, sandbox_seconds, cost, created_at
quota            scope(user|workspace), subject_id, metric, limit, period

shares           id, conversation_id, mode(private|link|workspace|public),
                 token, created_at

settings         key, value{}         # branding, prompts, router, etc.
```

## Design rules

- Message content lives in `message_blocks` (typed), never a single string.
- Tree structure: `messages.parent_id` + `branches` + `current_leaf_id`.
- Secrets stored encrypted (`api_key_enc`, `headers_enc`, MCP `config_enc`),
  never logged, never sent to clients.
- Every request carries `request_id/trace_id/conversation_id/user_id/
  provider_id/model_id` for observability.
- All schema changes go through Alembic migrations.
