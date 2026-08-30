# Tool Protocol

Internal tool contract. LLM output — native OpenAI tools, JSON, XML, special
tokens, or natural language — is normalized into one shape before execution.

## Core types

```
ToolDefinition {
  name, description, parameters: JSONSchema,
  risk: READ | WRITE | EXTERNAL_SIDE_EFFECT | DESTRUCTIVE | SENSITIVE,
  network_required: bool, requires_approval: bool
}

ToolCall    { id, name, arguments{} }
ToolResult  { tool_call_id, output, is_error: false, artifacts[] }
ToolError   { tool_call_id, code, message, retryable }
```

## Execution semantics

Supports single and parallel tool calls, forced tool, auto mode, per-call
timeout, retry with backoff, cancellation, and approval gating.

### Approval

Risk drives the prompt:
- `READ` — auto-allowed per workspace policy.
- `WRITE` — confirm per workspace policy.
- `DESTRUCTIVE` / `SENSITIVE` — always confirm.

UI: "Agent wants to: …" with `Allow once / Always allow / Deny`.

## Tool sources

Built-in tools, plugin tools, and **MCP** servers. MCP (stdio / HTTP / SSE)
tools are discovered and converted to `ToolDefinition`. MCP servers are
managed (connect/discover/test/logs) in the admin console.

## Security

- Only the Agent Runtime can invoke tools; model output can *request* a tool,
  never execute code directly.
- Tool arguments are schema-validated before dispatch.
- Tool results pass **secret redaction** before entering logs or context.
- Tools that read external content must tag it
  `UNTRUSTED_EXTERNAL_CONTENT`; such content can never itself issue tool calls.
