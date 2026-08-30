import json

import pytest
import pytest_asyncio
import httpx

from aether_api.main import app

from helpers import auth_headers, make_model, make_provider, register


@pytest_asyncio.fixture()
async def client(db):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=30) as c:
        yield c


def parse_sse(raw: str) -> list[tuple[str, dict]]:
    events = []
    current_event = None
    for line in raw.splitlines():
        if line.startswith("event:"):
            current_event = line[len("event:"):].strip()
        elif line.startswith("data:"):
            data = line[len("data:"):].strip()
            try:
                events.append((current_event, json.loads(data)))
            except json.JSONDecodeError:
                pass
    return events


@pytest.mark.asyncio
async def test_full_streaming_chat(client, mock_openai_server):
    data = await register(client)
    token = data["access_token"]
    headers = auth_headers(token)
    provider = await make_provider(client, token, mock_openai_server)
    await make_model(client, token, provider["id"])

    r = await client.post("/api/v1/conversations", headers=headers, json={"title": "New chat"})
    assert r.status_code == 201
    conv_id = r.json()["id"]

    async with client.stream(
        "POST",
        f"/api/v1/conversations/{conv_id}/runs",
        headers=headers,
        json={"content": "Say hello"},
    ) as resp:
        assert resp.status_code == 200
        body = ""
        async for chunk in resp.aiter_text():
            body += chunk

    events = parse_sse(body)
    types = [e for e, _ in events]
    assert "response.created" in types
    assert "reasoning.started" in types
    assert "reasoning.delta" in types
    assert "block.started" in types
    assert "block.delta" in types
    assert "response.completed" in types

    text_deltas = "".join(d["delta"] for e, d in events if e == "block.delta")
    assert text_deltas == "Hello world done"

    completed = next(d for e, d in events if e == "response.completed")
    assert completed["usage"]["output_tokens"] == 2

    r = await client.get(f"/api/v1/conversations/{conv_id}/messages", headers=headers)
    assert r.status_code == 200
    messages = r.json()
    assert len(messages) == 2
    assistant = next(m for m in messages if m["role"] == "assistant")
    block_types = [b["type"] for b in assistant["blocks"]]
    assert "reasoning" in block_types
    assert "markdown" in block_types
    md = next(b for b in assistant["blocks"] if b["type"] == "markdown")
    assert md["data"]["text"] == "Hello world done"


@pytest.mark.asyncio
async def test_auto_title_generated(client, mock_openai_server):
    data = await register(client)
    token = data["access_token"]
    headers = auth_headers(token)
    provider = await make_provider(client, token, mock_openai_server)
    await make_model(client, token, provider["id"])

    r = await client.post("/api/v1/conversations", headers=headers, json={"title": "New chat"})
    conv_id = r.json()["id"]

    async with client.stream(
        "POST", f"/api/v1/conversations/{conv_id}/runs",
        headers=headers, json={"content": "What is the capital of France?"},
    ) as resp:
        body = ""
        async for chunk in resp.aiter_text():
            body += chunk

    events = parse_sse(body)
    title_events = [d for e, d in events if e == "conversation.title"]
    assert title_events, "expected a conversation.title event"

    r = await client.get(f"/api/v1/conversations/{conv_id}", headers=headers)
    assert r.json()["title"] != "New chat"


@pytest.mark.asyncio
async def test_conversation_tree_branching(client, mock_openai_server):
    data = await register(client)
    token = data["access_token"]
    headers = auth_headers(token)
    provider = await make_provider(client, token, mock_openai_server)
    await make_model(client, token, provider["id"])

    r = await client.post("/api/v1/conversations", headers=headers, json={})
    conv_id = r.json()["id"]

    async def run(content, parent_id=None):
        payload = {"content": content}
        if parent_id:
            payload["parent_id"] = parent_id
        async with client.stream(
            "POST", f"/api/v1/conversations/{conv_id}/runs", headers=headers, json=payload
        ) as resp:
            async for _ in resp.aiter_text():
                pass

    await run("first question")
    r = await client.get(f"/api/v1/conversations/{conv_id}/messages", headers=headers)
    first_user = next(m for m in r.json() if m["role"] == "user")

    # Branch a second user message off the same parent (regenerate/edit semantics).
    async with client.stream(
        "POST", f"/api/v1/conversations/{conv_id}/runs", headers=headers,
        json={"content": "retry", "parent_id": first_user["parent_id"]},
    ) as resp:
        async for _ in resp.aiter_text():
            pass

    r = await client.get(f"/api/v1/conversations/{conv_id}/messages", headers=headers)
    users = [m for m in r.json() if m["role"] == "user"]
    assert len(users) == 2
    assert users[0]["parent_id"] == users[1]["parent_id"]


@pytest.mark.asyncio
async def test_regenerate_branches_assistant_under_same_user(client, mock_openai_server):
    data = await register(client)
    token = data["access_token"]
    headers = auth_headers(token)
    provider = await make_provider(client, token, mock_openai_server)
    await make_model(client, token, provider["id"])

    r = await client.post("/api/v1/conversations", headers=headers, json={})
    conv_id = r.json()["id"]

    async with client.stream(
        "POST", f"/api/v1/conversations/{conv_id}/runs", headers=headers, json={"content": "hello"}
    ) as resp:
        async for _ in resp.aiter_text():
            pass

    r = await client.get(f"/api/v1/conversations/{conv_id}/messages", headers=headers)
    msgs = r.json()
    user_msg = next(m for m in msgs if m["role"] == "user")
    assistants_before = [m for m in msgs if m["role"] == "assistant"]
    assert len(assistants_before) == 1

    # Regenerate: empty content + parent_id = existing user message.
    async with client.stream(
        "POST", f"/api/v1/conversations/{conv_id}/runs", headers=headers,
        json={"content": "", "parent_id": user_msg["id"]},
    ) as resp:
        async for _ in resp.aiter_text():
            pass

    r = await client.get(f"/api/v1/conversations/{conv_id}/messages", headers=headers)
    msgs = r.json()
    users = [m for m in msgs if m["role"] == "user"]
    assistants = [m for m in msgs if m["role"] == "assistant"]
    assert len(users) == 1, "regenerate must not duplicate the user message"
    assert len(assistants) == 2
    assert all(a["parent_id"] == user_msg["id"] for a in assistants)


@pytest.mark.asyncio
async def test_switching_old_retry_preserves_later_turns(client, mock_openai_server):
    data = await register(client)
    token = data["access_token"]
    headers = auth_headers(token)
    provider = await make_provider(client, token, mock_openai_server)
    await make_model(client, token, provider["id"])

    conv_id = (await client.post("/api/v1/conversations", headers=headers, json={})).json()["id"]

    async def run(content: str, parent_id: str | None = None):
        payload = {"content": content}
        if parent_id is not None:
            payload["parent_id"] = parent_id
        async with client.stream(
            "POST", f"/api/v1/conversations/{conv_id}/runs", headers=headers, json=payload,
        ) as response:
            async for _ in response.aiter_text():
                pass

    await run("first")
    initial = (await client.get(f"/api/v1/conversations/{conv_id}/messages", headers=headers)).json()
    first_user = next(message for message in initial if message["role"] == "user")
    first_assistant = next(message for message in initial if message["role"] == "assistant")

    await run("", first_user["id"])
    await run("second")
    before = (await client.get(f"/api/v1/conversations/{conv_id}/messages?active_only=true", headers=headers)).json()
    assert len(before) == 4
    later_user = next(message for message in before if message["role"] == "user" and message["id"] != first_user["id"])

    activated = await client.post(
        f"/api/v1/conversations/{conv_id}/branches/{first_assistant['id']}/activate",
        headers=headers,
    )
    assert activated.status_code == 200, activated.text

    after = (await client.get(f"/api/v1/conversations/{conv_id}/messages?active_only=true", headers=headers)).json()
    assert len(after) == 4, "changing an earlier retry must not hide downstream turns"
    assert after[1]["id"] == first_assistant["id"]
    assert next(message for message in after if message["id"] == later_user["id"])["parent_id"] == first_assistant["id"]


@pytest.mark.asyncio
async def test_multi_turn_chains_on_leaf(client, mock_openai_server):
    data = await register(client)
    token = data["access_token"]
    headers = auth_headers(token)
    provider = await make_provider(client, token, mock_openai_server)
    await make_model(client, token, provider["id"])

    r = await client.post("/api/v1/conversations", headers=headers, json={})
    conv_id = r.json()["id"]

    async def run(content):
        async with client.stream(
            "POST", f"/api/v1/conversations/{conv_id}/runs", headers=headers, json={"content": content}
        ) as resp:
            async for _ in resp.aiter_text():
                pass

    await run("first turn")
    await run("second turn")
    await run("third turn")

    r = await client.get(f"/api/v1/conversations/{conv_id}/messages", headers=headers)
    msgs = r.json()
    assert len(msgs) == 6
    by_id = {m["id"]: m for m in msgs}
    # Each message must chain on the previous one (a single path, not new roots).
    roots = [m for m in msgs if m["parent_id"] is None]
    assert len(roots) == 1, "turns after the first must not create new roots"
    # Walk the chain: user1 <- assistant1 <- user2 <- assistant2 <- user3 <- assistant3
    current = roots[0]
    depth = 1
    children = {m["parent_id"]: m for m in msgs if m["parent_id"]}
    while current["id"] in children:
        current = children[current["id"]]
        depth += 1
    assert depth == 6, f"expected a 6-deep chain, got {depth}"

    conv = await client.get(f"/api/v1/conversations/{conv_id}", headers=headers)
    assert conv.json()["current_leaf_id"] == current["id"]


@pytest.mark.asyncio
async def test_disconnect_finalizes_partial_message(client, mock_openai_server):
    data = await register(client)
    token = data["access_token"]
    headers = auth_headers(token)
    provider = await make_provider(client, token, mock_openai_server)
    await make_model(client, token, provider["id"])

    r = await client.post("/api/v1/conversations", headers=headers, json={})
    conv_id = r.json()["id"]

    async with client.stream(
        "POST", f"/api/v1/conversations/{conv_id}/runs", headers=headers, json={"content": "hi"}
    ) as resp:
        async for chunk in resp.aiter_text():
            if "block.delta" in chunk:
                break  # abandon the stream early like a client disconnect

    import asyncio

    await asyncio.sleep(0.5)

    r = await client.get(f"/api/v1/conversations/{conv_id}/messages", headers=headers)
    assistant = next(m for m in r.json() if m["role"] == "assistant")
    assert assistant["status"] in ("completed", "failed"), assistant["status"]


@pytest.mark.asyncio
async def test_pre_stream_error_is_saved_as_retryable_conversation_message(client):
    data = await register(client)
    headers = auth_headers(data["access_token"])
    conversation = await client.post("/api/v1/conversations", headers=headers, json={})
    conversation_id = conversation.json()["id"]

    response = await client.post(
        f"/api/v1/conversations/{conversation_id}/errors",
        headers=headers,
        json={
            "content": "帮我生成一张小猫的图片",
            "message": "图片服务暂时不可用",
            "code": "IMAGE_GENERATION_FAILED",
            "retry_kind": "image_generation",
            "duration_ms": 321,
        },
    )

    assert response.status_code == 201, response.text
    messages = (await client.get(
        f"/api/v1/conversations/{conversation_id}/messages", headers=headers
    )).json()
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assistant = messages[-1]
    assert assistant["status"] == "failed"
    assert assistant["error"] == {
        "code": "IMAGE_GENERATION_FAILED",
        "message": "图片服务暂时不可用",
        "retryable": True,
        "kind": "image_generation",
    }
    assert assistant["usage"]["duration_ms"] == 321
    assert assistant["blocks"][0]["type"] == "error"

    retry = await client.post(
        f"/api/v1/conversations/{conversation_id}/errors",
        headers=headers,
        json={
            "content": "帮我生成一张小猫的图片",
            "message": "图片服务仍不可用",
            "code": "IMAGE_GENERATION_FAILED",
            "retry_kind": "image_generation",
            "parent_user_message_id": messages[0]["id"],
        },
    )
    assert retry.status_code == 201, retry.text
    retried_messages = (await client.get(
        f"/api/v1/conversations/{conversation_id}/messages", headers=headers
    )).json()
    assert len([message for message in retried_messages if message["role"] == "user"]) == 1
    assert len([message for message in retried_messages if message["role"] == "assistant"]) == 2
    assert retried_messages[-1]["parent_id"] == messages[0]["id"]
