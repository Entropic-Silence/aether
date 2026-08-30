import pytest
import pytest_asyncio
import httpx

from aether_api.main import app
from aether_api.services.plugins import validate_manifest

from helpers import auth_headers, register


@pytest_asyncio.fixture()
async def client(db):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=60) as c:
        yield c


def test_manifest_validation():
    good = {
        "api_version": 1, "id": "x.y", "name": "Y", "version": "1.0.0",
        "entrypoint": "index.js", "permissions": ["network:api.x.com"],
        "capabilities": ["search"],
    }
    assert validate_manifest(good) == []

    assert validate_manifest({"id": "x"})  # missing fields
    problems = validate_manifest({**good, "capabilities": ["warp_drive"]})
    assert any("unknown capabilities" in p for p in problems)
    problems = validate_manifest({**good, "api_version": 9})
    assert any("api_version" in p for p in problems)


@pytest.mark.asyncio
async def test_plugin_rescan_empty_is_honest(client, monkeypatch, tmp_path):
    data = await register(client)
    token = data["access_token"]
    headers = auth_headers(token)

    import aether_api.services.plugins as plugins_mod

    monkeypatch.setattr(plugins_mod, "plugins_root", lambda: tmp_path)
    monkeypatch.setattr("aether_api.routers.plugins.plugins_root", lambda: tmp_path)

    r = await client.post("/api/v1/plugins/rescan", headers=headers)
    assert r.status_code == 200 and r.json()["found"] == 0

    r = await client.get("/api/v1/plugins", headers=headers)
    assert r.json()["plugins"] == []


@pytest.mark.asyncio
async def test_plugin_discovery_valid_and_invalid(client, monkeypatch, tmp_path):
    data = await register(client)
    token = data["access_token"]
    headers = auth_headers(token)

    good = tmp_path / "good-plugin"
    good.mkdir()
    (good / "plugin.yaml").write_text(
        "api_version: 1\nid: test.good\nname: Good\nversion: 0.1.0\n"
        "entrypoint: main.py\npermissions: []\ncapabilities: [tools]\n"
    )
    bad = tmp_path / "bad-plugin"
    bad.mkdir()
    (bad / "plugin.yaml").write_text("name: NoId\n")

    import aether_api.services.plugins as plugins_mod

    monkeypatch.setattr(plugins_mod, "plugins_root", lambda: tmp_path)
    monkeypatch.setattr("aether_api.routers.plugins.plugins_root", lambda: tmp_path)

    r = await client.post("/api/v1/plugins/rescan", headers=headers)
    assert r.json()["found"] == 2
    scanned = {str(p.get("plugin_id")): p for p in r.json()["plugins"]}
    assert scanned["test.good"]["status"] == "valid"
    bad_scanned = next(p for p in r.json()["plugins"] if p["status"] == "invalid")
    assert bad_scanned["problems"]

    r = await client.get("/api/v1/plugins", headers=headers)
    registered = r.json()["plugins"]
    assert len(registered) == 1  # only the valid plugin is registered
    assert registered[0]["plugin_id"] == "test.good"
    assert registered[0]["capabilities"] == ["tools"]


@pytest.mark.asyncio
async def test_deepseek_harness_package_manifest(client, monkeypatch, tmp_path):
    data = await register(client)
    headers = auth_headers(data["access_token"])
    plugin = tmp_path / "dsh-example"
    plugin.mkdir()
    (plugin / "package.json").write_text(
        '{"name":"dsh-example","version":"1.2.0","main":"dist/index.js",'
        '"keywords":["dsh-plugin"],"dsh":{"capabilities":["tools"]}}'
    )
    import aether_api.services.plugins as plugins_mod
    monkeypatch.setattr(plugins_mod, "plugins_root", lambda: tmp_path)
    monkeypatch.setattr("aether_api.routers.plugins.plugins_root", lambda: tmp_path)
    result = await client.post("/api/v1/plugins/rescan", headers=headers)
    assert result.status_code == 200
    item = result.json()["plugins"][0]
    assert item["plugin_id"] == "dsh-example"
    assert item["status"] == "valid"
