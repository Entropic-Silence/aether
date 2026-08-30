# Model Protocol

Unified contract between the platform and any LLM provider. The platform
never branches on model/vendor names; adapters translate to/from this
protocol.

## Entities

```
Provider {
  id, kind: "openai_compatible" | "native:<vendor>" | "custom_rest",
  name, base_url, api_key_ref, headers{}, proxy, timeout_ms,
  retry{max, backoff_ms}, concurrency, organization?, project?
}

Model {
  id, provider_id, model_id, display_name, description, icon,
  model_family, model_type, context_window, max_output_tokens,
  enabled, priority, weight, capabilities: ModelCapabilities,
  generation_defaults{...}, extra_body{}   # vLLM/SGLang passthrough
}

ModelCapabilities {
  text_input, text_output,
  image_input, audio_input, video_input,
  image_generation, image_edit, image_variation,
  audio_output, tts, stt,
  streaming,
  reasoning, reasoning_effort_levels[],
  tool_calling, parallel_tool_calling, forced_tool_calling,
  structured_output, json_schema, json_mode,
  embeddings, rerank, logprobs, system_prompt, file_input,
  web_search_native, code_execution_native,
  max_images, max_files, max_audio_length, max_video_length,
  context_window, max_output_tokens
}
```

Capabilities come from **Capability Probe** (automated) but an admin can
always **manually override**; probe results are `Supported / Unsupported /
Uncertain / Failed` and never auto-trusted.

## Unified request

```
ChatRequest {
  model_ref, messages[], tools[], tool_choice,            # auto|required/none/{name}
  response_format?, reasoning_effort?: auto|low|medium|high|extra_high,
  generation{temperature, top_p, top_k, min_p, max_tokens,
             repetition_penalty, frequency_penalty, presence_penalty,
             seed, stop[], logprobs},
  extra_body{}, stream
}
```

Only parameters the provider advertises are sent; the rest are dropped, not
errored. `extra_body` is merged last for engine-specific flags.

## Reasoning normalization

Whatever the provider returns — `reasoning_content`, `thinking`, `analysis`,
`reasoning` — is mapped to a single `ReasoningBlock`. Adapters also apply a
`ReasoningParser` for models that emit reasoning inside content with
delimiters. Reasoning effort is translated per provider; internal enum stays
fixed.

## Unified streaming events (SSE)

```
response.created      {message_id}
block.started         {block_id, type}
block.delta           {block_id, delta}
block.completed       {block_id}
reasoning.started     {block_id}
reasoning.delta       {block_id, delta}
reasoning.completed   {block_id, duration_ms}
response.delta        {block_id?}            # convenience alias for text
response.completed    {usage, finish_reason}
error                 {code, message, retryable}
```

Usage must distinguish `exact | estimated | provider_reported` token counts.

## Chat template / parsing adapters

Models without native OpenAI tool calling are handled by:

```
ChatTemplateAdapter  (native | openai | hermes | qwen | deepseek | glm | llama | jinja-import)
ToolCallParser       (JSON / XML / special-token / natural-language → ToolCall)
ResponseParser
```

Never assume native OpenAI tool calling.

## Model Router

Selection strategies: `fixed | fallback | weighted | latency | availability |
capability`. Capability filters (e.g. `image_input=true`) narrow candidates.
Fallback triggers only on `timeout | overload | unavailable | policy failure`
— **never mid-generation** (no silent model swap after output began).

## Error mapping

Provider failures map to the platform error taxonomy
(`PROVIDER_ERROR`, `MODEL_NOT_FOUND`, `MODEL_OVERLOADED`, `RATE_LIMIT`,
`CONTEXT_OVERFLOW`, …) with `retryable` hints for the router.
