from __future__ import annotations

import json

from ..orm import Provider
from ..security import decrypt_secret
from .openai_compatible import OpenAICompatibleAdapter

_REGISTRY: dict[str, type] = {
    "openai_compatible": OpenAICompatibleAdapter,
}


def register_adapter(kind: str, cls: type) -> None:
    _REGISTRY[kind] = cls


def build_adapter(provider: Provider) -> OpenAICompatibleAdapter:
    """Instantiate the adapter for a provider.

    Native vendor adapters register here; everything falls back to the
    OpenAI-compatible baseline so no business code branches on model names.
    """
    headers = {}
    raw_headers = decrypt_secret(provider.headers_enc)
    if raw_headers:
        try:
            headers = json.loads(raw_headers)
        except json.JSONDecodeError:
            headers = {}
    cls = _REGISTRY.get(provider.kind, OpenAICompatibleAdapter)
    return cls(
        base_url=provider.base_url,
        api_key=decrypt_secret(provider.api_key_enc),
        headers=headers,
        timeout_ms=provider.timeout_ms,
        proxy=provider.proxy,
    )
