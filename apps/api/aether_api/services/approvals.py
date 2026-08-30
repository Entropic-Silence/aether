from __future__ import annotations

import asyncio
from dataclasses import dataclass

# In-memory approval registry: pending approvals block the agent loop until
# a human decides. Runs are per-process; a restart clears pending prompts.
_PENDING: dict[str, asyncio.Future] = {}


@dataclass
class ApprovalRequest:
    approval_id: str
    tool_call_id: str
    name: str
    arguments: dict
    risk: str


def open_approval(approval_id: str) -> asyncio.Future:
    loop = asyncio.get_event_loop()
    fut = loop.create_future()
    _PENDING[approval_id] = fut
    return fut


def resolve_approval(approval_id: str, decision: str) -> bool:
    fut = _PENDING.pop(approval_id, None)
    if fut is None or fut.done():
        return False
    fut.set_result(decision)
    return True


def cancel_approval(approval_id: str) -> None:
    fut = _PENDING.pop(approval_id, None)
    if fut and not fut.done():
        fut.cancel()


async def wait_for_approval(approval_id: str, timeout_s: float = 600) -> str:
    fut = _PENDING.get(approval_id)
    if fut is None:
        return "deny"
    try:
        return await asyncio.wait_for(fut, timeout=timeout_s)
    except asyncio.TimeoutError:
        _PENDING.pop(approval_id, None)
        return "timeout"
