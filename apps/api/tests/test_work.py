import asyncio
import json

import pytest
import pytest_asyncio
import httpx

from helpers import auth_headers


async def register_or_login(live, email):
    r = await live.post("/api/v1/auth/register",
                        json={"email": email, "password": "password123"})
    if r.status_code != 200:
        r = await live.post("/api/v1/auth/login",
                            json={"email": email, "password": "password123"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]

SANDBOX_SLEEP_CODE = "import time; time.sleep(2); print(1)"


async def setup_owner_tool(live, mock_base):
    token = await register_or_login(live, "owner@example.com")
    H = auth_headers(token)
    await live.post("/api/v1/providers", headers=H, json={"name": "Mock", "base_url": mock_base})
    providers = await live.get("/api/v1/providers", headers=H)
    pid = providers.json()[0]["id"]
    m = await live.post("/api/v1/models", headers=H, json={
        "provider_id": pid, "model_id": "mock-tool", "display_name": "MT", "is_default": True,
        "capabilities": {"text_input": True, "text_output": True, "streaming": True,
                         "system_prompt": True, "tool_calling": True}})
    return token, m.json()["id"]


async def consume_until(live, url, headers, stop_event, timeout=90):
    events = []
    async with live.stream("GET", url, headers=headers, timeout=timeout) as resp:
        async for line in resp.aiter_lines():
            if line.startswith("event:"):
                ev = line[6:].strip()
                events.append(ev)
                if ev == stop_event:
                    break
    return events


async def consume_until_full(live, url, headers, stop_event, timeout=90):
    """Return a list of (event, data_json) tuples up to (and including) stop_event."""
    pairs = []
    current = None
    async with live.stream("GET", url, headers=headers, timeout=timeout) as resp:
        async for line in resp.aiter_lines():
            if line.startswith("event:"):
                current = line[6:].strip()
            elif line.startswith("data:") and current is not None:
                try:
                    pairs.append((current, json.loads(line[5:].strip())))
                except json.JSONDecodeError:
                    pairs.append((current, {}))
                if current == stop_event:
                    break
    return pairs


@pytest.mark.asyncio
async def test_runtimes_listed(live_server):
    async with httpx.AsyncClient(base_url=live_server, timeout=60) as live:
        token = await register_or_login(live, "owner@example.com")
        r = await live.get("/api/v1/runtimes", headers=auth_headers(token))
        assert r.status_code == 200
        runtimes = r.json()["runtimes"]
        assert "native" in runtimes
        assert "advanced" in runtimes


@pytest.mark.asyncio
async def test_work_run_completes_and_persists(live_server, mock_openai_server):
    async with httpx.AsyncClient(base_url=live_server, timeout=120) as live:
        token, mid = await setup_owner_tool(live, mock_openai_server)
        H = auth_headers(token)
        conv = await live.post("/api/v1/conversations", headers=H, json={"mode": "work"})
        cid = conv.json()["id"]
        r = await live.post(f"/api/v1/conversations/{cid}/work", headers=H,
                            json={"task": "Say hello", "runtime": "native", "model_id": mid})
        assert r.status_code == 201, r.text
        run_id = r.json()["run_id"]

        events = await consume_until(live, f"/api/v1/work/runs/{run_id}/events", H, "work.done")
        assert "work.planning" in events
        assert "work.completed" in events
        assert "work.done" in events

        runs = (await live.get(f"/api/v1/conversations/{cid}/work-runs", headers=H)).json()
        assert runs[0]["status"] == "completed"

        msgs = (await live.get(f"/api/v1/conversations/{cid}/messages", headers=H)).json()
        assistant = next(mm for mm in msgs if mm["role"] == "assistant")
        types = [b["type"] for b in assistant["blocks"]]
        assert "markdown" in types
        assert "progress" in types


@pytest.mark.asyncio
async def test_work_run_with_tools_timeline(live_server, mock_openai_server):
    async with httpx.AsyncClient(base_url=live_server, timeout=120) as live:
        token, mid = await setup_owner_tool(live, mock_openai_server)
        H = auth_headers(token)
        conv = await live.post("/api/v1/conversations", headers=H, json={})
        cid = conv.json()["id"]
        r = await live.post(f"/api/v1/conversations/{cid}/work", headers=H,
                            json={"task": "COMPUTE_TOOL then summarize", "model_id": mid})
        run_id = r.json()["run_id"]

        events = await consume_until(live, f"/api/v1/work/runs/{run_id}/events", H, "work.done", timeout=120)
        assert "work.step" in events
        assert "tool.completed" in events
        assert "work.completed" in events

        msgs = (await live.get(f"/api/v1/conversations/{cid}/messages", headers=H)).json()
        assistant = next(mm for mm in msgs if mm["role"] == "assistant")
        progress = next(b for b in assistant["blocks"] if b["type"] == "progress")
        steps = [t["event"] for t in progress["data"]["timeline"]]
        assert "work.step" in steps


@pytest.mark.asyncio
async def test_work_steering_and_cancel(live_server, mock_openai_server):
    async with httpx.AsyncClient(base_url=live_server, timeout=120) as live:
        token, mid = await setup_owner_tool(live, mock_openai_server)
        H = auth_headers(token)
        conv = await live.post("/api/v1/conversations", headers=H, json={})
        cid = conv.json()["id"]
        # LOOP_TOOL keeps calling run_python (with a 2s sleep) each iteration
        r = await live.post(f"/api/v1/conversations/{cid}/work", headers=H,
                            json={"task": "LOOP_TOOL forever", "model_id": mid})
        run_id = r.json()["run_id"]
        await asyncio.sleep(1.0)

        # steering while active is accepted
        r = await live.post(f"/api/v1/work/runs/{run_id}/steer", headers=H,
                            json={"content": "also consider edge cases"})
        assert r.status_code == 200, r.text

        r = await live.post(f"/api/v1/work/runs/{run_id}/cancel", headers=H)
        assert r.status_code == 200

        events = await consume_until(live, f"/api/v1/work/runs/{run_id}/events", H, "work.done", timeout=60)
        assert "work.cancelled" in events

        runs = (await live.get(f"/api/v1/conversations/{cid}/work-runs", headers=H)).json()
        assert runs[0]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_work_without_tool_capability_degrades_to_text(live_server, mock_openai_server):
    async with httpx.AsyncClient(base_url=live_server, timeout=120) as live:
        token = await register_or_login(live, "owner@example.com")
        H = auth_headers(token)
        await live.post("/api/v1/providers", headers=H, json={"name": "Mock", "base_url": mock_openai_server})
        providers = await live.get("/api/v1/providers", headers=H)
        pid = providers.json()[0]["id"]
        m = await live.post("/api/v1/models", headers=H, json={
            "provider_id": pid, "model_id": "mock-chat", "display_name": "no tools",
            "is_default": True, "capabilities": {"streaming": True, "tool_calling": False}})
        mid = m.json()["id"]
        conv = await live.post("/api/v1/conversations", headers=H, json={})
        cid = conv.json()["id"]
        r = await live.post(f"/api/v1/conversations/{cid}/work", headers=H,
                            json={"task": "hello", "model_id": mid})
        assert r.status_code == 201, r.text
        events = await consume_until(live, f"/api/v1/work/runs/{r.json()['run_id']}/events", H, "work.done")
        assert "work.completed" in events


@pytest.mark.asyncio
async def test_advanced_runtime_emits_plan(live_server, mock_openai_server):
    async with httpx.AsyncClient(base_url=live_server, timeout=120) as live:
        token, mid = await setup_owner_tool(live, mock_openai_server)
        H = auth_headers(token)
        conv = await live.post("/api/v1/conversations", headers=H, json={"mode": "work"})
        cid = conv.json()["id"]
        r = await live.post(f"/api/v1/conversations/{cid}/work", headers=H,
                            json={"task": "COMPUTE_TOOL then summarize", "runtime": "advanced", "model_id": mid})
        assert r.status_code == 201, r.text
        run_id = r.json()["run_id"]

        events = await consume_until_full(live, f"/api/v1/work/runs/{run_id}/events", H, "work.done", timeout=120)
        names = [e for e, _ in events]
        assert "work.planning" in names
        assert "work.plan" in names  # advanced runtime emits an explicit plan
        assert "work.completed" in names
        assert "work.done" in names
        plan = next(d for e, d in events if e == "work.plan")
        assert isinstance(plan.get("steps"), list) and len(plan["steps"]) >= 1

        runs = (await live.get(f"/api/v1/conversations/{cid}/work-runs", headers=H)).json()
        assert runs[0]["status"] == "completed"
        assert runs[0]["runtime"] == "advanced"
