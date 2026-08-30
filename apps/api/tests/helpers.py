async def register(client, email="owner@example.com", password="password123"):
    r = await client.post("/api/v1/auth/register", json={"email": email, "password": password, "name": "Owner"})
    assert r.status_code == 200, r.text
    return r.json()


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


async def make_provider(client, token, base_url, name="Mock Provider"):
    r = await client.post(
        "/api/v1/providers",
        headers=auth_headers(token),
        json={"name": name, "base_url": base_url, "kind": "openai_compatible", "api_key": "sk-test"},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def make_model(client, token, provider_id, model_id="mock-chat", is_default=True, **caps):
    capabilities = {"text_input": True, "text_output": True, "streaming": True, "system_prompt": True}
    capabilities.update(caps)
    r = await client.post(
        "/api/v1/models",
        headers=auth_headers(token),
        json={
            "provider_id": provider_id,
            "model_id": model_id,
            "display_name": model_id,
            "is_default": is_default,
            "capabilities": capabilities,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()
