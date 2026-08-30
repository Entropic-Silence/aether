from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..adapters import build_adapter
from ..errors import CapabilityUnsupportedError, ProviderError
from ..orm import File, FileChunk, Model, Provider, Setting
from .chunking import chunk_text

RETRIEVAL_KEY = "retrieval"

DEFAULTS = {
    "embedding_model_id": None,
    "chunk_size": 1200,
    "chunk_overlap": 150,
    "top_k": 6,
    "score_threshold": 0.0,
}


async def get_retrieval_settings(db: AsyncSession) -> dict:
    row = await db.get(Setting, RETRIEVAL_KEY)
    settings = dict(DEFAULTS)
    if row and isinstance(row.value, dict):
        settings.update(row.value)
    return settings


async def update_retrieval_settings(db: AsyncSession, patch: dict) -> dict:
    settings = await get_retrieval_settings(db)
    settings.update({k: v for k, v in patch.items() if k in DEFAULTS})
    row = await db.get(Setting, RETRIEVAL_KEY)
    if row is None:
        db.add(Setting(key=RETRIEVAL_KEY, value=settings))
    else:
        row.value = settings
    await db.commit()
    return settings


async def _embedding_model(db: AsyncSession) -> tuple[Model, Provider]:
    settings = await get_retrieval_settings(db)
    model_pk = settings.get("embedding_model_id")
    if not model_pk:
        raise CapabilityUnsupportedError(
            "No embedding model configured. Add one in Admin → Retrieval to enable RAG."
        )
    model = await db.get(Model, model_pk)
    if not model or not model.enabled:
        raise CapabilityUnsupportedError("Configured embedding model is unavailable")
    provider = await db.get(Provider, model.provider_id)
    if not provider or not provider.enabled:
        raise CapabilityUnsupportedError("Embedding provider is unavailable")
    return model, provider


class VectorStoreProvider(ABC):
    """Default implementation stores embeddings in Postgres; Qdrant/pgvector plug in later."""

    @abstractmethod
    async def upsert(self, file_id: str, chunks: list[dict]) -> None: ...

    @abstractmethod
    async def search(self, file_ids: list[str], vector: list[float], top_k: int,
                     score_threshold: float) -> list[dict]: ...

    @abstractmethod
    async def delete_file(self, file_id: str) -> None: ...


class PostgresVectorStore(VectorStoreProvider):
    def __init__(self, db: AsyncSession):
        self.db = db

    async def upsert(self, file_id: str, chunks: list[dict]) -> None:
        await self.db.execute(delete(FileChunk).where(FileChunk.file_id == file_id))
        for c in chunks:
            self.db.add(FileChunk(
                file_id=file_id, chunk_index=c["index"], text=c["text"],
                embedding=c["embedding"], char_start=c["char_start"],
            ))
        await self.db.commit()

    async def search(self, file_ids: list[str], vector: list[float], top_k: int,
                     score_threshold: float) -> list[dict]:
        rows = await self.db.execute(
            select(FileChunk).where(FileChunk.file_id.in_(file_ids))
        )
        chunks = rows.scalars().all()
        if not chunks:
            return []
        q = np.asarray(vector, dtype=np.float32)
        qn = np.linalg.norm(q)
        if qn == 0:
            return []
        results = []
        for c in chunks:
            if not c.embedding:
                continue
            v = np.asarray(c.embedding, dtype=np.float32)
            vn = np.linalg.norm(v)
            if vn == 0:
                continue
            score = float(np.dot(q, v) / (qn * vn))
            if score >= score_threshold:
                results.append({
                    "file_id": c.file_id, "chunk_index": c.chunk_index,
                    "text": c.text, "score": score,
                })
        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:top_k]

    async def delete_file(self, file_id: str) -> None:
        await self.db.execute(delete(FileChunk).where(FileChunk.file_id == file_id))
        await self.db.commit()


async def embed_texts(db: AsyncSession, texts: list[str]) -> list[list[float]]:
    model, provider = await _embedding_model(db)
    adapter = build_adapter(provider)
    try:
        return await adapter.embeddings(texts, model_id=model.model_id)
    finally:
        await adapter.aclose()


async def index_file(db: AsyncSession, file_id: str) -> int:
    """Chunk + embed an already-extracted file. Returns chunk count."""
    file = await db.get(File, file_id)
    if not file:
        raise CapabilityUnsupportedError("File not found")
    text = (file.extraction or {}).get("text", "")
    if not text.strip():
        return 0
    settings = await get_retrieval_settings(db)
    chunks = chunk_text(text, int(settings["chunk_size"]), int(settings["chunk_overlap"]))
    if not chunks:
        return 0
    vectors = []
    texts = [c.text for c in chunks]
    batch = 32
    for i in range(0, len(texts), batch):
        vectors.extend(await embed_texts(db, texts[i:i + batch]))
    store = PostgresVectorStore(db)
    await store.upsert(file_id, [
        {"index": c.index, "text": c.text, "char_start": c.char_start, "embedding": v}
        for c, v in zip(chunks, vectors)
    ])
    return len(chunks)


async def query_files(db: AsyncSession, file_ids: list[str], query: str,
                      top_k: int | None = None, score_threshold: float | None = None) -> list[dict]:
    settings = await get_retrieval_settings(db)
    k = top_k or int(settings["top_k"])
    threshold = settings["score_threshold"] if score_threshold is None else score_threshold
    try:
        vector = (await embed_texts(db, [query]))[0]
    except (CapabilityUnsupportedError, ProviderError) as e:
        raise CapabilityUnsupportedError(f"Retrieval unavailable: {e.message}") from e
    store = PostgresVectorStore(db)
    return await store.search(file_ids, vector, k, float(threshold))
