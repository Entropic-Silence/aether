# Agent Runtime (Work-mode core)

Work mode is driven by a pluggable **agent runtime**. Two engines are built in;
both implement the same `AgentRuntimeProvider` interface, so any external
harness can register without platform changes.

| Runtime | Behavior | Use |
|---|---|---|
| `native` | Single agentic tool loop: task → tool loop → summary | quick work runs |
| `advanced` | **Plan-then-execute**: decompose → tool loop with plan context → summary | default Work-mode engine |

The advanced engine is the **default engine for Work mode**. It is exposed only
as `advanced`; no upstream branding is surfaced anywhere.

## Advanced engine flow

```
work.planning            # decompose the task
work.plan {steps[]}      # ordered plan (2-6 steps)
work.step {step, tool}   # per-step progress
tool.completed {...}     # tool results
work.text {...}          # interim notes
block.delta {...}        # streamed final summary (markdown)
work.completed           # done
```

The plan is produced by the model (graceful single-step fallback if the model
does not return a JSON plan). The tool loop then works through the plan with
tools, supports steering/cancel/approval, respects the iteration budget, and
always ends with a written summary (forced tool-free completion if the budget
is exhausted).

## Shared agentic tool loop

Both engines reuse one tool loop that provides:
- Tool discovery (built-in + MCP) and dispatch
- Approval gating (risk-based; allow once / always / deny)
- Live steering (inject instructions mid-run) and cancel
- Iteration budget with a forced final summary

## Selecting a runtime

- Per-run: `POST /conversations/{id}/work` body `runtime` (`advanced` default).
- Work UI: engine toggle (Advanced / Native).
- Registry: `GET /api/v1/runtimes`.

## Extending

Register another harness by implementing `AgentRuntimeProvider.run(ctx)` and
calling `register_runtime(...)`. The runtime receives a `WorkContext`
(conversation, model, provider, task, steering queue, cancel event) and yields
`(event, data)` tuples consumed by the Work run executor and the frontend
timeline.
