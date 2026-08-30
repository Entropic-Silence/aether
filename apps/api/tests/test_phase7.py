import asyncio
import subprocess
import sys
import os

import pytest
import pytest_asyncio
import httpx

from aether_api.main import app

from helpers import auth_headers, make_model, make_provider, register


@pytest_asyncio.fixture()
async def client(db):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=120) as c:
        yield c


@pytest.mark.asyncio
async def test_memory_crud_and_clear(client):
    data = await register(client)
    token = data["access_token"]
    H = auth_headers(token)

    r = await client.post("/api/v1/memories", headers=H, json={"content": "I prefer concise answers", "category": "preference"})
    assert r.status_code == 201, r.text
    mid = r.json()["id"]
    assert r.json()["kind"] == "explicit"

    r = await client.get("/api/v1/memories", headers=H)
    assert len(r.json()) == 1

    r = await client.patch(f"/api/v1/memories/{mid}", headers=H, json={"enabled": False})
    assert r.json()["enabled"] is False

    r = await client.delete("/api/v1/memories", headers=H)
    assert r.status_code == 204
    assert (await client.get("/api/v1/memories", headers=H)).json() == []


@pytest.mark.asyncio
async def test_custom_instructions_and_memory_injected_into_prompt(client, mock_client, mock_openai_server):
    data = await register(client)
    token = data["access_token"]
    H = auth_headers(token)
    provider = await make_provider(client, token, mock_openai_server)
    await make_model(client, token, provider["id"], model_id="mock-chat")

    r = await client.patch("/api/v1/settings/me", headers=H, json={
        "about_me": "I am a marine biologist named Dana.",
        "response_style": "Answer with ocean metaphors.",
        "memory_reference": True,
    })
    assert r.status_code == 200

    r = await client.post("/api/v1/memories", headers=H, json={"content": "Favorite tide: spring tide"})
    assert r.status_code == 201

    conv = await client.post("/api/v1/conversations", headers=H, json={})
    cid = conv.json()["id"]
    async with client.stream("POST", f"/api/v1/conversations/{cid}/runs", headers=H,
                             json={"content": "hello there"}) as resp:
        async for _ in resp.aiter_text():
            pass

    reqs = (await mock_client.get(f"{mock_openai_server}/_requests")).json()
    chat_reqs = [q for q in reqs
                 if any(m.get("role") == "user" and m.get("content") == "hello there"
                        for m in q.get("messages", []))]
    assert chat_reqs, "chat request not found"
    system = next(m for m in chat_reqs[-1]["messages"] if m["role"] == "system")["content"]
    assert "marine biologist named Dana" in system
    assert "ocean metaphors" in system
    assert "Favorite tide: spring tide" in system


@pytest.mark.asyncio
async def test_memory_not_injected_when_disabled(client, mock_client, mock_openai_server):
    data = await register(client)
    token = data["access_token"]
    H = auth_headers(token)
    provider = await make_provider(client, token, mock_openai_server)
    await make_model(client, token, provider["id"], model_id="mock-chat")

    await client.post("/api/v1/memories", headers=H, json={"content": "SECRET_MEMORY_MARKER"})
    await client.patch("/api/v1/settings/me", headers=H, json={"memory_reference": False})

    conv = await client.post("/api/v1/conversations", headers=H, json={})
    cid = conv.json()["id"]
    async with client.stream("POST", f"/api/v1/conversations/{cid}/runs", headers=H,
                             json={"content": "hi"}) as resp:
        async for _ in resp.aiter_text():
            pass

    reqs = (await mock_client.get(f"{mock_openai_server}/_requests")).json()
    chat_reqs = [q for q in reqs if any(m.get("role") == "user" and m.get("content") == "hi"
                                        for m in q.get("messages", []))]
    system = next(m for m in chat_reqs[-1]["messages"] if m["role"] == "system")["content"]
    assert "SECRET_MEMORY_MARKER" not in system


@pytest.mark.asyncio
async def test_study_mode_prompt(client, mock_client, mock_openai_server):
    data = await register(client)
    token = data["access_token"]
    H = auth_headers(token)
    provider = await make_provider(client, token, mock_openai_server)
    await make_model(client, token, provider["id"], model_id="mock-chat")

    conv = await client.post("/api/v1/conversations", headers=H, json={"mode": "study"})
    cid = conv.json()["id"]
    async with client.stream("POST", f"/api/v1/conversations/{cid}/runs", headers=H,
                             json={"content": "teach me photosynthesis"}) as resp:
        async for _ in resp.aiter_text():
            pass

    reqs = (await mock_client.get(f"{mock_openai_server}/_requests")).json()
    chat_reqs = [q for q in reqs
                 if any(m.get("role") == "user" and m.get("content") == "teach me photosynthesis"
                        for m in q.get("messages", []))]
    system = next(m for m in chat_reqs[-1]["messages"] if m["role"] == "system")["content"]
    assert "Study mode" in system and "Socratic" in system


@pytest.mark.asyncio
async def test_tasks_crud_validation_and_runs(client, mock_openai_server):
    data = await register(client)
    token = data["access_token"]
    H = auth_headers(token)
    provider = await make_provider(client, token, mock_openai_server)
    model = await make_model(client, token, provider["id"], model_id="mock-chat")

    # invalid cron rejected
    r = await client.post("/api/v1/tasks", headers=H, json={
        "prompt": "x", "schedule_type": "cron", "schedule_value": "not a cron"})
    assert r.status_code == 422

    r = await client.post("/api/v1/tasks", headers=H, json={
        "name": "daily digest", "prompt": "Summarize news",
        "schedule_type": "cron", "schedule_value": "0 8 * * *"})
    assert r.status_code == 201, r.text
    task = r.json()
    assert task["next_run"] is not None

    # manual trigger
    r = await client.post(f"/api/v1/tasks/{task['id']}/run", headers=H)
    assert r.status_code == 202
    for _ in range(60):
        await asyncio.sleep(0.5)
        runs = (await client.get(f"/api/v1/tasks/{task['id']}/runs", headers=H)).json()
        if runs and runs[0]["status"] in ("completed", "failed"):
            break
    assert runs and runs[0]["status"] == "completed", runs
    assert runs[0]["conversation_id"]
    assert "Hello world" in runs[0]["result_summary"]

    r = await client.delete(f"/api/v1/tasks/{task['id']}", headers=H)
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_artifacts_crud_and_download(client):
    data = await register(client)
    token = data["access_token"]
    H = auth_headers(token)

    r = await client.post("/api/v1/artifacts", headers=H, json={
        "kind": "document", "title": "My report", "content": "# Report\n\nFindings here."})
    assert r.status_code == 201, r.text
    aid = r.json()["id"]

    r = await client.get("/api/v1/artifacts", headers=H)
    assert len(r.json()) == 1

    r = await client.get(f"/api/v1/artifacts/{aid}/download", headers=H)
    assert r.status_code == 200 and b"Findings here" in r.content

    r = await client.post("/api/v1/artifacts", headers=H, json={"kind": "bogus", "content": "x"})
    assert r.status_code == 422

    r = await client.delete(f"/api/v1/artifacts/{aid}", headers=H)
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_audio_endpoints_honest_when_unconfigured(client):
    data = await register(client)
    token = data["access_token"]
    H = auth_headers(token)
    r = await client.post("/api/v1/audio/transcribe", headers=H,
                          files={"upload": ("a.webm", b"fakebytes")})
    assert r.status_code == 400
    assert "STT" in r.json()["error"]["message"] or "speech" in r.json()["error"]["message"].lower()

    r = await client.post("/api/v1/audio/tts", headers=H, json={"text": "hello"})
    assert r.status_code == 400

    r = await client.get("/api/v1/settings/ui", headers=H)
    assert r.json()["stt_configured"] is False
    assert r.json()["tts_configured"] is False


@pytest.mark.asyncio
async def test_video_frame_extraction(tmp_path):
    from aether_api.services.video import extract_frames, ffmpeg_available

    assert ffmpeg_available(), "ffmpeg must be installed"
    # generate a real 3-second test video
    vid = tmp_path / "test.mp4"
    subprocess.run([
        "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=duration=3:size=160x120:rate=10",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(vid),
    ], check=True)
    frames = await extract_frames(vid.read_bytes(), ".mp4", max_frames=4)
    assert 1 <= len(frames) <= 4
    for ts, png in frames:
        assert png.startswith(b"\x89PNG")
        assert ts >= 0
