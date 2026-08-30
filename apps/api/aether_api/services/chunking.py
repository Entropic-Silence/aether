from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Chunk:
    index: int
    text: str
    char_start: int


def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 150) -> list[Chunk]:
    """Paragraph-aware character chunking with overlap."""
    if chunk_size <= 0:
        chunk_size = 1200
    overlap = max(0, min(overlap, chunk_size // 2))
    paragraphs = text.split("\n")
    chunks: list[Chunk] = []
    buffer = ""
    buffer_start = 0
    cursor = 0

    def flush() -> None:
        nonlocal buffer, buffer_start
        if buffer.strip():
            chunks.append(Chunk(index=len(chunks), text=buffer.strip(), char_start=buffer_start))
        buffer = ""

    for para in paragraphs:
        piece = para + "\n"
        if not buffer:
            buffer_start = cursor
        if len(buffer) + len(piece) > chunk_size and buffer:
            flush()
            if overlap and buffer == "":
                tail = chunks[-1].text[-overlap:] if chunks else ""
                buffer = tail
                buffer_start = cursor - len(tail)
        buffer += piece
        cursor += len(piece)
    flush()

    # Split oversized buffers (e.g. a single giant paragraph)
    final: list[Chunk] = []
    for c in chunks:
        if len(c.text) <= chunk_size * 2:
            c.index = len(final)
            final.append(c)
            continue
        pos = 0
        while pos < len(c.text):
            seg = c.text[pos:pos + chunk_size]
            final.append(Chunk(index=len(final), text=seg, char_start=c.char_start + pos))
            pos += chunk_size - overlap
    return final
