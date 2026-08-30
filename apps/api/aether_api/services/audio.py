from __future__ import annotations

from abc import ABC, abstractmethod

import httpx

from ..errors import CapabilityUnsupportedError
from ..security import decrypt_secret

AUDIO_SETTINGS_KEY = "audio"


class SpeechToTextProvider(ABC):
    name = "abstract"

    @abstractmethod
    async def transcribe(self, audio_bytes: bytes, filename: str) -> str: ...


class TextToSpeechProvider(ABC):
    name = "abstract"

    @abstractmethod
    async def synthesize(self, text: str, voice: str | None) -> tuple[bytes, str]:
        """Return (audio_bytes, content_type)."""


class OpenAICompatSTT(SpeechToTextProvider):
    name = "openai_compatible"

    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    async def transcribe(self, audio_bytes: bytes, filename: str) -> str:
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(
                f"{self.base_url}/audio/transcriptions",
                headers=headers,
                files={"file": (filename, audio_bytes)},
                data={"model": self.model},
            )
        if resp.status_code != 200:
            raise CapabilityUnsupportedError(f"STT provider returned {resp.status_code}")
        return resp.json().get("text", "")


class OpenAICompatTTS(TextToSpeechProvider):
    name = "openai_compatible"

    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    async def synthesize(self, text: str, voice: str | None) -> tuple[bytes, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(
                f"{self.base_url}/audio/speech",
                headers=headers,
                json={"model": self.model, "input": text, "voice": voice or "alloy"},
            )
        if resp.status_code != 200:
            raise CapabilityUnsupportedError(f"TTS provider returned {resp.status_code}")
        ctype = (resp.headers.get("content-type") or "audio/mpeg").split(";")[0]
        return resp.content, ctype


async def get_audio_settings(db) -> dict:
    from ..orm import Setting

    row = await db.get(Setting, AUDIO_SETTINGS_KEY)
    return (row.value if row and isinstance(row.value, dict) else {})


async def get_stt_provider(db) -> SpeechToTextProvider | None:
    s = await get_audio_settings(db)
    stt = s.get("stt") or {}
    if stt.get("kind") == "openai_compatible" and stt.get("base_url") and stt.get("model"):
        raw_key = stt.get("api_key", "")
        api_key = decrypt_secret(raw_key) or (raw_key if raw_key and not raw_key.startswith("gAAAA") else "")
        return OpenAICompatSTT(stt["base_url"], api_key, stt["model"])
    return None


async def get_tts_provider(db) -> TextToSpeechProvider | None:
    s = await get_audio_settings(db)
    tts = s.get("tts") or {}
    if tts.get("kind") == "openai_compatible" and tts.get("base_url") and tts.get("model"):
        raw_key = tts.get("api_key", "")
        api_key = decrypt_secret(raw_key) or (raw_key if raw_key and not raw_key.startswith("gAAAA") else "")
        return OpenAICompatTTS(tts["base_url"], api_key, tts["model"])
    return None
