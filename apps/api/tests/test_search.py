import pytest

from aether_api.errors import FetchError
from aether_api.services.search import MockSearchProvider, SearchRouter, dedupe_results, SearchResult
from aether_api.services.webfetch import extract_document, validate_url
import httpx


def test_validate_url_blocks_schemes():
    for bad in ("ftp://x.com", "file:///etc/passwd", "javascript:alert(1)", "gopher://x"):
        with pytest.raises(FetchError):
            validate_url(bad)


def test_validate_url_blocks_internal_hosts(monkeypatch):
    monkeypatch.delenv("http_proxy", raising=False)
    monkeypatch.delenv("https_proxy", raising=False)
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    for bad in ("http://localhost/x", "http://127.0.0.1/x", "http://169.254.169.254/latest/meta-data",
                "http://10.0.0.5/x", "http://192.168.1.1/x", "http://svc.internal/x",
                "http://[::1]/x", "http://myhost.local/x"):
        with pytest.raises(FetchError):
            validate_url(bad)


def test_validate_url_allows_public_when_direct(monkeypatch):
    monkeypatch.delenv("http_proxy", raising=False)
    monkeypatch.delenv("https_proxy", raising=False)
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.setattr("socket.getaddrinfo", lambda host, port: [(2, 1, 6, "", ("93.184.216.34", 443))])
    assert validate_url("https://example.com/page") == "https://example.com/page"


def test_validate_url_blocks_private_dns_answer(monkeypatch):
    monkeypatch.delenv("http_proxy", raising=False)
    monkeypatch.delenv("https_proxy", raising=False)
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.setattr("socket.getaddrinfo", lambda host, port: [(2, 1, 6, "", ("10.1.2.3", 443))])
    with pytest.raises(FetchError):
        validate_url("https://evil.example.com/")


def test_extract_document_metadata():
    html = """
    <html><head><title> Test Title </title>
    <meta property="article:published_time" content="2026-01-02T00:00:00Z">
    <style>body{}</style><script>var x=1;</script></head>
    <body><nav>menu menu menu</nav>
    <article><p>%s</p></article>
    <footer>footer stuff</footer></body></html>
    """ % ("A substantial paragraph about retrieval pipelines. " * 8)
    title, text, published = extract_document(html, "https://example.com/a")
    assert title == "Test Title"
    assert published == "2026-01-02T00:00:00Z"
    assert "retrieval pipelines" in text
    assert "var x=1" not in text
    assert "menu menu" not in text


def test_dedupe_results():
    results = [
        SearchResult(url="https://a.com/x/", title="1", snippet=""),
        SearchResult(url="https://a.com/x", title="2", snippet=""),
        SearchResult(url="https://b.com/", title="3", snippet=""),
    ]
    assert len(dedupe_results(results)) == 2


@pytest.mark.asyncio
async def test_mock_provider_and_router():
    provider = MockSearchProvider()
    async with httpx.AsyncClient() as client:
        results = await provider.search("search pipeline citations", 5, client)
    assert results
    router = SearchRouter([provider])
    outcome = await router.search("search pipeline", count=3)
    assert outcome.provider == "mock" and outcome.results


@pytest.mark.asyncio
async def test_router_falls_back_on_failure():
    class Broken:
        name = "broken"

        async def search(self, query, count, client):
            raise RuntimeError("boom")

    router = SearchRouter([Broken(), MockSearchProvider()])
    outcome = await router.search("anything", count=3)
    assert outcome.provider == "mock"
