# @aether/protocol

Canonical unified streaming event + message block protocol. Backends must
emit only these events; provider-native stream formats never reach clients.

## Streaming events (SSE)

| Event | Payload | Meaning |
|---|---|---|
| `response.created` | `{conversation_id, user_message_id, assistant_message_id, model}` | Run accepted, assistant message allocated |
| `reasoning.started` | `{message_id}` | Reasoning stream begins |
| `reasoning.delta` | `{delta}` | Reasoning token chunk |
| `reasoning.completed` | `{message_id, duration_ms?}` | Reasoning finished |
| `block.started` | `{message_id?, type}` | Content block begins (`markdown`, `code`, `image`, ...) |
| `block.delta` | `{type, delta}` | Block content chunk |
| `block.completed` | `{type}` | Block finished |
| `tool.started` / `tool.completed` / `tool.failed` | `{tool_call_id, name, ...}` | Tool lifecycle (Phase 3+) |
| `search.started` / `search.result` | `{...}` | Search pipeline (Phase 4+) |
| `sandbox.started` / `sandbox.output` / `sandbox.completed` | `{...}` | Sandbox lifecycle (Phase 3+) |
| `artifact.created` | `{artifact_id, kind}` | Artifact produced (Phase 7+) |
| `conversation.title` | `{conversation_id, title}` | Auto-title updated |
| `response.completed` | `{message_id, finish_reason, usage, latency_ms, ttft_ms}` | Run finished |
| `error` | `{code, message, retryable}` | Terminal error (taxonomy codes) |

## Message blocks

`text` `markdown` `reasoning` `code` `image` `audio` `video` `file`
`citation` `sources` `tool_call` `tool_result` `search` `chart` `table`
`artifact` `writing` `sandbox` `progress` `error`

A message is `blocks[]`, never a single content string.
