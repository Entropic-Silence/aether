from __future__ import annotations

import ipaddress
import os
import re
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from ..errors import FetchError

MAX_FETCH_BYTES = 10 * 1024 * 1024
ALLOWED_CONTENT_TYPES = ("text/html", "text/plain", "application/xhtml+xml")
METADATA_ENDPOINT_HOSTS = {"169.254.169.254", "metadata.google.internal"}

DEFAULT_DENY_HOSTS = {
    "localhost",
    "metadata.google.internal",
}


@dataclass
class WebDocument:
    url: str
    final_url: str
    title: str
    text: str
    domain: str
    published_at: str | None
    fetched_at: str


def _is_private_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True  # unparseable -> refuse
    return (
        addr.is_private or addr.is_loopback or addr.is_link_local
        or addr.is_reserved or addr.is_multicast or addr.is_unspecified
    )


def _proxy_configured() -> bool:
    return bool(os.environ.get("http_proxy") or os.environ.get("https_proxy")
                or os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY"))


def validate_url(url: str, deny_hosts: set[str] | None = None) -> str:
    """SSRF guard: scheme/host policy always enforced; local DNS IP check when
    egress is direct. With an HTTP proxy, DNS happens at the proxy, so the
    host deny-list is the enforcement point (reported honestly in docs)."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise FetchError(f"URL scheme not allowed: {parsed.scheme or 'none'}")
    host = (parsed.hostname or "").lower()
    if not host:
        raise FetchError("URL has no host")
    deny = DEFAULT_DENY_HOSTS | (deny_hosts or set())
    if host in deny or host.endswith(".local") or host.endswith(".internal"):
        raise FetchError(f"Host blocked by policy: {host}")
    if host in METADATA_ENDPOINT_HOSTS:
        raise FetchError("Cloud metadata endpoint is blocked")
    # If the host is an IP literal, block private ranges directly.
    try:
        addr = ipaddress.ip_address(host)
        if (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_reserved or addr.is_multicast or addr.is_unspecified):
            raise FetchError(f"Direct private IP target blocked: {host}")
    except ValueError:
        pass  # hostname, not an IP literal; handled below
    if _proxy_configured():
        return url
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as e:
        raise FetchError(f"Cannot resolve host: {host}") from e
    for info in infos:
        ip = info[4][0]
        if _is_private_ip(ip):
            raise FetchError(f"Host resolves to a private address (blocked): {host} -> {ip}")
    return url


def extract_document(html: str, url: str) -> tuple[str, str, str | None]:
    """Return (title, main_text, published_at) from HTML using heuristics."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "svg", "header", "footer", "nav", "form", "aside"]):
        tag.decompose()

    title = (soup.title.get_text(strip=True) if soup.title else "") or url

    published = None
    for attr in ("article:published_time", "datePublished", "og:article:published_time"):
        node = soup.find("meta", attrs={"property": attr}) or soup.find("meta", attrs={"name": attr})
        if node and node.get("content"):
            published = node["content"]
            break
    if not published:
        tnode = soup.find("time", attrs={"datetime": True})
        if tnode:
            published = tnode.get("datetime")

    candidates = []
    for selector in ("article", "main", '[role="main"]', ".post-content", ".article-content", ".content"):
        for node in soup.select(selector):
            text = node.get_text("\n", strip=True)
            if len(text) > 200:
                candidates.append(text)
    if candidates:
        text = max(candidates, key=len)
    else:
        text = soup.get_text("\n", strip=True)

    text = re.sub(r"\n{3,}", "\n\n", text)
    return title.strip(), text.strip(), published


async def fetch_url(url: str, deny_hosts: set[str] | None = None,
                    timeout_s: float = 20.0) -> WebDocument:
    """Fetch a page safely and extract readable text + metadata."""
    from .search import now_iso

    validate_url(url, deny_hosts)
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; AetherReader/0.1; +research)",
        "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.5",
    }
    async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=True, max_redirects=5) as client:
        try:
            resp = await client.get(url, headers=headers)
        except httpx.HTTPError as e:
            raise FetchError(f"Fetch failed: {type(e).__name__}") from e
    if resp.status_code >= 400:
        raise FetchError(f"HTTP {resp.status_code} fetching page")
    content_type = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
    if content_type and content_type not in ALLOWED_CONTENT_TYPES:
        raise FetchError(f"Content type not readable: {content_type}")
    body = resp.content[:MAX_FETCH_BYTES]
    if len(resp.content) > MAX_FETCH_BYTES:
        raise FetchError("Page exceeds the 10 MB fetch limit")

    if content_type == "text/plain":
        text = body.decode("utf-8", errors="replace")
        return WebDocument(url=url, final_url=str(resp.url), title=url, text=text.strip(),
                           domain=urlparse(url).hostname or "", published_at=None,
                           fetched_at=now_iso())

    title, text, published = extract_document(body.decode("utf-8", errors="replace"), url)
    if len(text) < 50:
        raise FetchError("No readable content extracted")
    return WebDocument(
        url=url, final_url=str(resp.url), title=title, text=text[:60000],
        domain=urlparse(str(resp.url)).hostname or "", published_at=published,
        fetched_at=now_iso(),
    )


def select_passages(docs: list[WebDocument], query: str, max_chars: int = 9000) -> list[dict]:
    """Keyword-overlap passage selection (reranker provider plugs in later)."""
    terms = [t for t in re.findall(r"[\w\u4e00-\u9fff]{2,}", query.lower())]
    selected = []
    budget = max_chars
    for doc in docs:
        paragraphs = [p.strip() for p in doc.text.split("\n") if len(p.strip()) > 60]
        scored = []
        for p in paragraphs:
            low = p.lower()
            score = sum(1 for t in terms if t in low)
            if score > 0:
                scored.append((score, p))
        scored.sort(key=lambda x: -x[0])
        for _, p in scored[:4]:
            if budget <= 0:
                break
            piece = p[:1500]
            selected.append({"text": piece, "url": doc.url, "title": doc.title,
                             "domain": doc.domain, "published_at": doc.published_at})
            budget -= len(piece)
        if budget <= 0:
            break
    return selected
