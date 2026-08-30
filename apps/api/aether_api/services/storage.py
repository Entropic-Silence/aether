from __future__ import annotations

import os
import shutil
from abc import ABC, abstractmethod
from pathlib import Path


class StorageProvider(ABC):
    """Object-storage interface. Default is local disk; S3/MinIO adapters plug in later."""

    @abstractmethod
    async def put(self, key: str, data: bytes) -> None: ...

    @abstractmethod
    async def get(self, key: str) -> bytes: ...

    @abstractmethod
    async def delete(self, key: str) -> None: ...

    @abstractmethod
    async def exists(self, key: str) -> bool: ...


class LocalStorage(StorageProvider):
    def __init__(self, root: str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        safe = os.path.normpath(key).lstrip("/").lstrip("\\")
        if ".." in Path(safe).parts:
            raise ValueError("invalid storage key")
        return self.root / safe

    async def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    async def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    async def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()
        parent = path.parent
        try:
            if parent != self.root and not any(parent.iterdir()):
                shutil.rmtree(parent, ignore_errors=True)
        except OSError:
            pass

    async def exists(self, key: str) -> bool:
        return self._path(key).exists()


_storage: StorageProvider | None = None


def get_storage() -> StorageProvider:
    global _storage
    if _storage is None:
        root = os.environ.get("STORAGE_ROOT", "")
        if not root:
            repo_root = Path(__file__).resolve().parents[4]
            root = str(repo_root / "data" / "storage")
        _storage = LocalStorage(root)
    return _storage
