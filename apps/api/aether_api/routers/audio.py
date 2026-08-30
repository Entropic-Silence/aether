from __future__ import annotations

from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..deps import get_current_user, require_admin
from ..errors import CapabilityUnsupportedError
from ..orm import Setting, User
from ..services.audio import AUDIO_SETTINGS_KEY, get_audio_settings, get_stt_provider, get_tts_provider
from ..security import encrypt_secret

router = APIRouter(prefix="/audio", tags=["audio"])


@router.post("/transcribe")
async def transcribe(upload: UploadFile, db: AsyncSession = Depends(get_db),
                     user: User = Depends(get_current_user)):
    from ..services.features import ensure_feature

    await ensure_feature(db, "audio", user)
    provider = await get_stt_provider(db)
    if provider is None:
        raise CapabilityUnsupportedError("No speech-to-text provider configured (Admin → Audio).")
    data = await upload.read()
    if len(data) > 25 * 1024 * 1024:
        raise CapabilityUnsupportedError("Audio exceeds the 25 MB limit")
    text = await provider.transcribe(data, upload.filename or "audio.webm")
    return {"text": text}


class TTSIn(BaseModel):
    text: str
    voice: str | None = None


@router.post("/tts")
async def tts(body: TTSIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    from ..services.features import ensure_feature

    await ensure_feature(db, "audio", user)
    provider = await get_tts_provider(db)
    if provider is None:
        raise CapabilityUnsupportedError("No text-to-speech provider configured (Admin → Audio).")
    audio, ctype = await provider.synthesize(body.text, body.voice)
    return Response(content=audio, media_type=ctype)


class AudioSettingsIn(BaseModel):
    stt: dict | None = None
    tts: dict | None = None


@router.get("/settings")
async def audio_settings(db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    s = await get_audio_settings(db)
    # mask keys
    out = {}
    for side in ("stt", "tts"):
        cfg = dict(s.get(side) or {})
        if cfg.get("api_key"):
            cfg["api_key"] = ""
            cfg["has_api_key"] = True
        out[side] = cfg
    return out


@router.patch("/settings")
async def patch_audio_settings(body: AudioSettingsIn, db: AsyncSession = Depends(get_db),
                               _: User = Depends(require_admin)):
    current = await get_audio_settings(db)
    if body.stt is not None:
        if body.stt.get("api_key"):
            body.stt["api_key"] = encrypt_secret(body.stt["api_key"])
        elif current.get("stt", {}).get("api_key"):
            body.stt["api_key"] = current["stt"]["api_key"]
        current["stt"] = body.stt
    if body.tts is not None:
        if body.tts.get("api_key"):
            body.tts["api_key"] = encrypt_secret(body.tts["api_key"])
        elif current.get("tts", {}).get("api_key"):
            body.tts["api_key"] = current["tts"]["api_key"]
        current["tts"] = body.tts
    row = await db.get(Setting, AUDIO_SETTINGS_KEY)
    if row is None:
        db.add(Setting(key=AUDIO_SETTINGS_KEY, value=current))
    else:
        row.value = current
    await db.commit()
    return {"ok": True}
