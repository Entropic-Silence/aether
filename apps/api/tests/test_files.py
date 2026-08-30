import base64

import pytest
import pytest_asyncio
import httpx

from aether_api.main import app

from helpers import auth_headers, make_model, make_provider, register

PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


@pytest_asyncio.fixture()
async def client(db):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=30) as c:
        yield c


async def upload(client, token, content: bytes, filename: str):
    r = await client.post(
        "/api/v1/files",
        headers={"Authorization": f"Bearer {token}"},
        files={"upload": (filename, content)},
    )
    return r


@pytest.mark.asyncio
async def test_upload_text_file_extracts(client, mock_openai_server):
    data = await register(client)
    token = data["access_token"]
    body = b"Aether retrieval test document.\nThe capital of testing is Assertville."
    r = await upload(client, token, body, "notes.txt")
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["mime"] == "text/plain"
    assert out["kind"] == "document"
    assert out["status"] == "extracted"
    assert out["extraction"]["text_chars"] == len(body.decode())

    r = await client.get("/api/v1/files", headers=auth_headers(token))
    assert len(r.json()) == 1

    r = await client.get(f"/api/v1/files/{out['id']}/download", headers=auth_headers(token))
    assert r.status_code == 200 and r.content == body


@pytest.mark.asyncio
async def test_mime_sniffing_ignores_extension(client, mock_openai_server):
    data = await register(client)
    token = data["access_token"]
    r = await upload(client, token, PNG_1PX, "definitely_text.txt")
    assert r.status_code == 201
    out = r.json()
    assert out["mime"] == "image/png", "content sniffing must override the extension"
    assert out["kind"] == "image"


@pytest.mark.asyncio
async def test_pdf_parse_or_honest_notice(client, mock_openai_server):
    data = await register(client)
    token = data["access_token"]
    minimal_pdf = (
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
        b"trailer<</Root 1 0 R>>\n%%EOF"
    )
    r = await upload(client, token, minimal_pdf, "doc.pdf")
    assert r.status_code == 201
    out = r.json()
    assert out["mime"] == "application/pdf"
    assert out["status"] in ("extracted", "failed")


@pytest.mark.asyncio
async def test_rename_and_delete(client, mock_openai_server):
    data = await register(client)
    token = data["access_token"]
    r = await upload(client, token, b"hello", "a.txt")
    fid = r.json()["id"]

    r = await client.patch(f"/api/v1/files/{fid}", headers=auth_headers(token), json={"name": "b.txt"})
    assert r.status_code == 200 and r.json()["name"] == "b.txt"

    r = await client.delete(f"/api/v1/files/{fid}", headers=auth_headers(token))
    assert r.status_code == 204
    r = await client.get("/api/v1/files", headers=auth_headers(token))
    assert r.json() == []


@pytest.mark.asyncio
async def test_indexed_when_embedding_configured(client, mock_openai_server):
    data = await register(client)
    token = data["access_token"]
    headers = auth_headers(token)
    provider = await make_provider(client, token, mock_openai_server)
    embed_model = await make_model(client, token, provider["id"], model_id="mock-embed", is_default=False)

    r = await client.patch("/api/v1/settings/retrieval", headers=headers,
                           json={"embedding_model_id": embed_model["id"], "chunk_size": 200, "chunk_overlap": 20})
    assert r.status_code == 200

    long_text = "\n".join(f"Paragraph {i} about topic-{i} with enough words to matter." for i in range(30))
    r = await upload(client, token, long_text.encode(), "knowledge.txt")
    out = r.json()
    assert out["status"] == "indexed", out
    assert out["extraction"]["indexed_chunks"] > 0


@pytest.mark.asyncio
async def test_path_traversal_filename_sanitized(client, mock_openai_server):
    data = await register(client)
    token = data["access_token"]
    r = await upload(client, token, b"x", "../../etc/passwd")
    assert r.status_code == 201
    assert r.json()["name"] == "passwd"
