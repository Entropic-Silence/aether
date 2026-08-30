from __future__ import annotations

import json
import mimetypes
import zipfile
from io import BytesIO

TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".rst", ".log", ".csv", ".tsv", ".json", ".jsonl",
    ".py", ".js", ".ts", ".tsx", ".jsx", ".c", ".h", ".cpp", ".hpp", ".java", ".go",
    ".rs", ".rb", ".php", ".sh", ".bash", ".yaml", ".yml", ".toml", ".ini", ".xml",
    ".html", ".css", ".sql", ".swift", ".kt", ".scala", ".r", ".m",
}

IMAGE_MIME_PREFIX = "image/"
AUDIO_MIME_PREFIX = "audio/"
VIDEO_MIME_PREFIX = "video/"


def sniff_mime(data: bytes, filename: str) -> str:
    """Detect MIME from content first (magic bytes), extension only as fallback.

    Never trusts the extension alone.
    """
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"BM"):
        return "image/bmp"
    if data[:2] == b"PK":
        return _sniff_zip(data, filename)
    if data.startswith(b"ID3") or (len(data) > 1 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0):
        return "audio/mpeg"
    if data.startswith(b"OggS"):
        return "audio/ogg"
    if data.startswith(b"fLaC"):
        return "audio/flac"
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "audio/wav"
    if data[4:8] == b"ftyp":
        brand = data[8:12]
        if brand in (b"M4A ", b"M4B "):
            return "audio/mp4"
        return "video/mp4"
    if data.startswith(b"\x1aE\xdf\xa3"):
        return "video/matroska"
    if data[:4] == b"RIFF" and data[8:12] == b"AVI ":
        return "video/avi"

    if _looks_like_text(data[:4096]):
        return _sniff_text(data, filename)

    ext_mime = _from_extension(filename)
    return ext_mime or "application/octet-stream"


def _sniff_zip(data: bytes, filename: str) -> str:
    try:
        with zipfile.ZipFile(BytesIO(data)) as zf:
            names = zf.namelist()
    except zipfile.BadZipFile:
        return "application/zip"
    if any(n.startswith("word/") for n in names):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if any(n.startswith("xl/") for n in names):
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if any(n.startswith("ppt/") for n in names):
        return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    return "application/zip"


def _looks_like_text(sample: bytes) -> bool:
    if not sample:
        return False
    if b"\x00" in sample:
        return False
    try:
        sample.decode("utf-8")
        return True
    except UnicodeDecodeError:
        pass
    try:
        sample.decode("gbk")
        return True
    except UnicodeDecodeError:
        return False


def _sniff_text(data: bytes, filename: str) -> str:
    head = data[:8192]
    try:
        text = head.decode("utf-8", errors="ignore").strip()
    except Exception:  # noqa: BLE001
        text = ""
    if text.startswith("{") or text.startswith("["):
        try:
            json.loads(data.decode("utf-8", errors="ignore"))
            return "application/json"
        except (json.JSONDecodeError, ValueError):
            pass
    ext = _ext(filename)
    if ext in (".csv", ".tsv"):
        return "text/csv" if ext == ".csv" else "text/tab-separated-values"
    if ext in (".md", ".markdown"):
        return "text/markdown"
    if ext in (".html", ".htm"):
        return "text/html"
    if ext in TEXT_EXTENSIONS:
        return "text/plain"
    return "text/plain"


def _ext(filename: str) -> str:
    idx = filename.rfind(".")
    return filename[idx:].lower() if idx != -1 else ""


def _from_extension(filename: str) -> str | None:
    ext = _ext(filename)
    if ext in TEXT_EXTENSIONS:
        return "text/plain"
    mime, _ = mimetypes.guess_type(filename)
    return mime


def file_kind(mime: str) -> str:
    if mime.startswith(IMAGE_MIME_PREFIX):
        return "image"
    if mime.startswith(AUDIO_MIME_PREFIX):
        return "audio"
    if mime.startswith(VIDEO_MIME_PREFIX):
        return "video"
    if mime in ("text/csv", "text/tab-separated-values",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"):
        return "data"
    if mime in (
        "application/pdf", "text/plain", "text/markdown", "text/html", "application/json",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ):
        return "document"
    return "other"


def sanitize_filename(name: str) -> str:
    name = name.replace("\\", "/").split("/")[-1]
    name = "".join(ch for ch in name if ch not in '\x00\r\n')
    name = name.strip().strip(".")
    return name[:240] or "untitled"
