from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import Response
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..deps import get_current_user
from ..errors import NotFoundError, PermissionError_, ValidationError_
from ..orm import File, ProjectFile, User
from ..services import mime as mimeutil
from ..services.parsers import get_parser
from ..services.retrieval import PostgresVectorStore, get_retrieval_settings, index_file
from ..services.storage import get_storage

router = APIRouter(prefix="/files", tags=["files"])

MAX_UPLOAD_BYTES = 100 * 1024 * 1024
TEXT_STORE_CAP = 1_500_000


def _to_out(f: File) -> dict:
    extraction = f.extraction or {}
    return {
        "id": f.id,
        "name": f.name,
        "mime": f.mime,
        "kind": f.kind,
        "size": f.size,
        "sha256": f.sha256,
        "status": f.status,
        "error": f.error,
        "project_id": f.project_id,
        "created_at": f.created_at,
        "extraction": {
            "pages": extraction.get("pages", 0),
            "text_chars": extraction.get("text_chars", 0),
            "notices": extraction.get("notices", []),
            "indexed_chunks": extraction.get("indexed_chunks", 0),
        },
    }


async def _owned_file(db: AsyncSession, file_id: str, user: User) -> File:
    f = await db.get(File, file_id)
    if not f:
        raise NotFoundError("File not found")
    if f.user_id != user.id and user.role not in ("admin", "owner"):
        raise PermissionError_("Not your file")
    return f


@router.post("", status_code=201)
async def upload_file(upload: UploadFile, db: AsyncSession = Depends(get_db),
                      user: User = Depends(get_current_user)):
    from .deps_helper import workspace_id_for
    from ..services.features import ensure_feature, get_feature_controls

    await ensure_feature(db, "file_uploads", user)
    controls = await get_feature_controls(db)
    max_upload_bytes = int(controls["policies"]["max_upload_mb"]) * 1024 * 1024

    data = bytearray()
    while True:
        piece = await upload.read(1024 * 1024)
        if not piece:
            break
        data.extend(piece)
        if len(data) > max_upload_bytes:
            raise ValidationError_(f"File exceeds the {controls['policies']['max_upload_mb']} MB upload limit")
    if not data:
        raise ValidationError_("Empty file")

    name = mimeutil.sanitize_filename(upload.filename or "untitled")
    sample = bytes(data) if len(data) <= 262144 else bytes(data[:262144])
    detected_mime = mimeutil.sniff_mime(sample, name)
    kind = mimeutil.file_kind(detected_mime)

    sha = hashlib.sha256(bytes(data)).hexdigest()
    file = File(
        workspace_id=await workspace_id_for(db),
        user_id=user.id,
        name=name,
        mime=detected_mime,
        kind=kind,
        size=len(data),
        sha256=sha,
        storage_key=f"{user.id}/{sha[:2]}/{sha}",
        status="processing",
        extraction={},
    )
    db.add(file)
    await db.commit()
    await db.refresh(file)

    storage = get_storage()
    await storage.put(file.storage_key, bytes(data))

    notices: list[str] = []
    text = ""
    pages = 0
    if kind in ("document", "data"):
        parser = get_parser(detected_mime)
        if parser is None:
            file.status = "extracted"
            notices.append("No parser for this format; file stored only.")
        else:
            try:
                result = parser.parse(bytes(data), detected_mime, name)
                text = result.text
                pages = result.pages
                notices.extend(result.notices)
            except Exception as e:  # noqa: BLE001
                file.status = "failed"
                file.error = f"Extraction failed: {e}"
                await db.commit()
                return _to_out(file)
            if len(text) > TEXT_STORE_CAP:
                text = text[:TEXT_STORE_CAP]
                notices.append("Extracted text truncated for storage.")
            file.status = "extracted"
    elif kind == "image":
        file.status = "extracted"
    else:
        file.status = "extracted"
        notices.append("Audio/video understanding arrives in a later phase.")

    file.extraction = {
        "text": text,
        "text_chars": len(text),
        "pages": pages,
        "notices": notices,
        "indexed_chunks": 0,
    }

    if text.strip():
        settings = await get_retrieval_settings(db)
        if settings.get("embedding_model_id"):
            try:
                n_chunks = await index_file(db, file.id)
                file.extraction = {**file.extraction, "indexed_chunks": n_chunks}
                file.status = "indexed"
            except Exception as e:  # noqa: BLE001
                notices.append(f"Indexing failed: {getattr(e, 'message', str(e))}")
                file.extraction = {**file.extraction, "notices": notices}
        else:
            notices.append("RAG disabled: configure an embedding model in Admin → Retrieval.")
            file.extraction = {**file.extraction, "notices": notices}

    await db.commit()
    await db.refresh(file)
    return _to_out(file)


@router.get("")
async def list_files(q: str = "", project_id: str | None = None,
                     db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    from ..services.features import ensure_feature

    await ensure_feature(db, "library", user)
    query = select(File).where(File.user_id == user.id)
    if project_id:
        query = query.where(File.project_id == project_id)
    if q:
        like = f"%{q.lower()}%"
        query = query.where(or_(File.name.ilike(like)))
    rows = await db.execute(query.order_by(File.created_at.desc()).limit(500))
    return [_to_out(f) for f in rows.scalars().all()]


@router.get("/{file_id}")
async def get_file(file_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    f = await _owned_file(db, file_id, user)
    return _to_out(f)


@router.get("/{file_id}/preview")
async def preview_file(file_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Return a safe browser-preview description; Office documents use extracted text."""
    f = await _owned_file(db, file_id, user)
    mime = (f.mime or "").lower()
    if mime == "application/pdf":
        mode = "pdf"
    elif mime == "image/svg+xml" or f.name.lower().endswith(".svg"):
        mode = "svg"
    else:
        mode = "text"
    text = str((f.extraction or {}).get("text") or "")
    return {"id": f.id, "name": f.name, "mime": f.mime, "mode": mode, "text": text[:300_000]}


@router.get("/{file_id}/download")
async def download_file(file_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    f = await _owned_file(db, file_id, user)
    data = await get_storage().get(f.storage_key)
    quoted = f.name.replace('"', "").encode("ascii", errors="ignore").decode()
    return Response(
        content=data,
        media_type=f.mime or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{quoted}"'},
    )


@router.patch("/{file_id}")
async def update_file(file_id: str, patch: dict, db: AsyncSession = Depends(get_db),
                      user: User = Depends(get_current_user)):
    f = await _owned_file(db, file_id, user)
    if "name" in patch and isinstance(patch["name"], str):
        f.name = mimeutil.sanitize_filename(patch["name"])
    if "project_id" in patch:
        f.project_id = patch["project_id"] or None
    await db.commit()
    await db.refresh(f)
    return _to_out(f)


@router.delete("/{file_id}", status_code=204)
async def delete_file(file_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    f = await _owned_file(db, file_id, user)
    store = PostgresVectorStore(db)
    await store.delete_file(file_id)
    await db.execute(ProjectFile.__table__.delete().where(ProjectFile.file_id == file_id))
    await get_storage().delete(f.storage_key)
    await db.delete(f)
    await db.commit()
