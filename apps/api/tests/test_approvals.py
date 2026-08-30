import asyncio

import pytest

from aether_api.services.approvals import (
    cancel_approval,
    open_approval,
    resolve_approval,
    wait_for_approval,
)


@pytest.mark.asyncio
async def test_open_resolve_wait():
    open_approval("a1")
    async def resolver():
        await asyncio.sleep(0.05)
        assert resolve_approval("a1", "allow") is True
    task = asyncio.create_task(resolver())
    decision = await wait_for_approval("a1", timeout_s=5)
    assert decision == "allow"
    await task


@pytest.mark.asyncio
async def test_wait_unknown_returns_deny():
    decision = await wait_for_approval("missing", timeout_s=1)
    assert decision == "deny"


@pytest.mark.asyncio
async def test_timeout_returns_timeout():
    open_approval("a2")
    decision = await wait_for_approval("a2", timeout_s=0.2)
    assert decision == "timeout"


@pytest.mark.asyncio
async def test_cancel():
    open_approval("a3")
    cancel_approval("a3")
    decision = await wait_for_approval("a3", timeout_s=1)
    assert decision == "deny"


@pytest.mark.asyncio
async def test_resolve_after_done_is_false():
    open_approval("a4")
    assert resolve_approval("a4", "allow") is True
    assert resolve_approval("a4", "deny") is False
