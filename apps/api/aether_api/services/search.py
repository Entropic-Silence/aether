from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx

from ..errors import SearchError

SEARCH_SETTINGS_KEY = "search"


@dataclass
class SearchResult:
    url: str
    title: str
    snippet: str
    published_at: str | None = None


@dataclass
class SearchOutcome:
    results: list[SearchResult] = field(default_factory=list)
    provider: str = ""


class SearchProvider(ABC):
    name = "abstract"

    @abstractmethod
    async def search(self, query: str, count: int, client: httpx.AsyncClient) -> list[SearchResult]: ...


class MockSearchProvider(SearchProvider):
    """Deterministic provider for tests/offline dev. Never fabricates live-web claims."""

    name = "mock"

    def __init__(self, corpus: list[dict] | None = None):
        # URLs must be real, fetchable pages so the read/extract stage of the
        # pipeline works end-to-end even without a live search API key.
        self.corpus = corpus or [
            {"url": "https://example.com/", "title": "Example Domain",
             "snippet": "An illustrative domain used in documentation and examples."},
            {"url": "https://www.iana.org/domains/reserved", "title": "IANA Reserved Domains",
             "snippet": "Reserved top-level and second-level domains for documentation and testing."},
            {"url": "https://www.rfc-editor.org/rfc/rfc2606", "title": "RFC 2606 Reserved TLDs",
             "snippet": "Reserved top level domains such as .test, .example, .invalid and .localhost."},
        ]

    async def search(self, query: str, count: int, client: httpx.AsyncClient) -> list[SearchResult]:
        terms = set(query.lower().split())
        scored = []
        for doc in self.corpus:
            hay = (doc["title"] + " " + doc["snippet"]).lower()
            score = sum(1 for t in terms if t in hay)
            scored.append((score, doc))
        scored.sort(key=lambda x: -x[0])
        return [SearchResult(url=d["url"], title=d["title"], snippet=d["snippet"])
                for _, d in scored[:count]]


class SearXNGProvider(SearchProvider):
    name = "searxng"

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    async def search(self, query: str, count: int, client: httpx.AsyncClient) -> list[SearchResult]:
        resp = await client.get(
            f"{self.base_url}/search",
            params={"q": query, "format": "json"},
        )
        if resp.status_code != 200:
            raise SearchError(f"SearXNG returned {resp.status_code}")
        data = resp.json()
        out = []
        for r in data.get("results", [])[:count]:
            if r.get("url"):
                out.append(SearchResult(
                    url=r["url"], title=r.get("title", ""), snippet=r.get("content", ""),
                    published_at=r.get("publishedDate"),
                ))
        return out


class TavilyProvider(SearchProvider):
    name = "tavily"

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def search(self, query: str, count: int, client: httpx.AsyncClient) -> list[SearchResult]:
        resp = await client.post(
            "https://api.tavily.com/search",
            json={"api_key": self.api_key, "query": query, "max_results": count},
        )
        if resp.status_code != 200:
            raise SearchError(f"Tavily returned {resp.status_code}")
        data = resp.json()
        return [
            SearchResult(url=r.get("url", ""), title=r.get("title", ""),
                         snippet=r.get("content", ""), published_at=r.get("published_date"))
            for r in data.get("results", [])[:count] if r.get("url")
        ]


class BraveProvider(SearchProvider):
    name = "brave"

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def search(self, query: str, count: int, client: httpx.AsyncClient) -> list[SearchResult]:
        resp = await client.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers={"X-Subscription-Token": self.api_key},
            params={"q": query, "count": count},
        )
        if resp.status_code != 200:
            raise SearchError(f"Brave returned {resp.status_code}")
        data = resp.json()
        return [
            SearchResult(url=r.get("url", ""), title=r.get("title", ""),
                         snippet=r.get("description", ""),
                         published_at=(r.get("page_age") or None))
            for r in data.get("web", {}).get("results", [])[:count] if r.get("url")
        ]


class SerperProvider(SearchProvider):
    name = "serper"

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def search(self, query: str, count: int, client: httpx.AsyncClient) -> list[SearchResult]:
        resp = await client.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": self.api_key},
            json={"q": query, "num": count},
        )
        if resp.status_code != 200:
            raise SearchError(f"Serper returned {resp.status_code}")
        data = resp.json()
        return [
            SearchResult(url=r.get("link", ""), title=r.get("title", ""),
                         snippet=r.get("snippet", ""), published_at=r.get("date"))
            for r in data.get("organic", [])[:count] if r.get("link")
        ]


class SearchRouter:
    """Tries providers by configured priority; falls back to the next on failure."""

    def __init__(self, providers: list[SearchProvider]):
        self.providers = providers

    async def search(self, query: str, count: int = 8) -> SearchOutcome:
        if not self.providers:
            raise SearchError("No search provider configured (Admin → Search).")
        errors = []
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            for provider in self.providers:
                try:
                    results = await provider.search(query, count, client)
                    if results:
                        return SearchOutcome(results=results, provider=provider.name)
                    errors.append(f"{provider.name}: empty")
                except SearchError as e:
                    errors.append(f"{provider.name}: {e.message}")
                except Exception as e:  # noqa: BLE001
                    errors.append(f"{provider.name}: {e}")
        raise SearchError("All search providers failed: " + "; ".join(errors))


def build_router(settings: dict) -> SearchRouter:
    """Build the router from stored settings (priority order already applied)."""
    providers: list[SearchProvider] = []
    entries = settings.get("providers") or []
    for entry in sorted(entries, key=lambda e: e.get("priority", 100)):
        if not entry.get("enabled", True):
            continue
        kind = entry.get("kind")
        if kind == "mock":
            providers.append(MockSearchProvider())
        elif kind == "searxng" and entry.get("base_url"):
            providers.append(SearXNGProvider(entry["base_url"]))
        elif kind == "tavily" and entry.get("api_key"):
            providers.append(TavilyProvider(entry["api_key"]))
        elif kind == "brave" and entry.get("api_key"):
            providers.append(BraveProvider(entry["api_key"]))
        elif kind == "serper" and entry.get("api_key"):
            providers.append(SerperProvider(entry["api_key"]))
    return SearchRouter(providers)


def dedupe_results(results: list[SearchResult]) -> list[SearchResult]:
    seen: set[str] = set()
    out = []
    for r in results:
        key = r.url.rstrip("/").lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
