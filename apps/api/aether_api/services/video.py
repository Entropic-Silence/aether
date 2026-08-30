from __future__ import annotations

import asyncio
import base64
import os
import shutil
import tempfile

from ..errors import CapabilityUnsupportedError

MAX_FRAMES = 6


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


async def _run(cmd: list[str], timeout_s: float = 120) -> tuple[int, bytes, bytes]:
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        proc.kill()
        raise CapabilityUnsupportedError("ffmpeg timed out")
    return proc.returncode or 0, out, err


async def extract_frames(video_bytes: bytes, suffix: str, max_frames: int = MAX_FRAMES) -> list[tuple[float, bytes]]:
    """Sample up to max_frames frames uniformly; return (seconds, png_bytes)."""
    if not ffmpeg_available():
        raise CapabilityUnsupportedError("ffmpeg is not installed on this host")
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, f"input{suffix}")
        with open(src, "wb") as f:
            f.write(video_bytes)
        # probe duration
        rc, out, err = await _run([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", src,
        ])
        try:
            duration = float(out.decode().strip()) if rc == 0 and out.strip() else 0.0
        except ValueError:
            duration = 0.0
        pattern = os.path.join(td, "frame_%03d.png")
        if duration > 0:
            fps = max_frames / duration
            cmd = ["ffmpeg", "-v", "error", "-i", src, "-vf", f"fps={fps:.5f}",
                   "-frames:v", str(max_frames), pattern]
        else:
            cmd = ["ffmpeg", "-v", "error", "-i", src, "-frames:v", str(max_frames), pattern]
        rc, _, err = await _run(cmd)
        if rc != 0:
            raise CapabilityUnsupportedError(f"frame extraction failed: {err.decode()[:200]}")
        frames = []
        names = sorted(n for n in os.listdir(td) if n.startswith("frame_"))
        for i, name in enumerate(names[:max_frames]):
            ts = (i + 0.5) * (duration / len(names)) if duration > 0 else float(i)
            with open(os.path.join(td, name), "rb") as f:
                frames.append((round(ts, 1), f.read()))
        if not frames:
            raise CapabilityUnsupportedError("no frames could be extracted")
        return frames


async def extract_audio_transcript(db, video_bytes: bytes, suffix: str) -> str | None:
    """Transcribe the audio track if an STT provider is configured; else None."""
    from .audio import get_stt_provider

    provider = await get_stt_provider(db)
    if provider is None:
        return None
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, f"input{suffix}")
        dst = os.path.join(td, "audio.wav")
        with open(src, "wb") as f:
            f.write(video_bytes)
        rc, _, err = await _run([
            "ffmpeg", "-v", "error", "-i", src, "-vn", "-ac", "1", "-ar", "16000", dst,
        ])
        if rc != 0 or not os.path.exists(dst) or os.path.getsize(dst) < 1000:
            return None
        with open(dst, "rb") as f:
            audio = f.read()
        try:
            text = await provider.transcribe(audio, "audio.wav")
        except Exception:  # noqa: BLE001
            return None
        return text.strip() or None


async def describe_video(db, vision_model, vision_provider, video_bytes: bytes,
                         mime: str) -> str:
    """Frames → vision model descriptions (+ optional transcript) → timeline text."""
    from ..adapters import build_adapter

    suffix = ".mp4" if "mp4" in mime else (".webm" if "webm" in mime else ".mkv" if "matroska" in mime else ".mov" if "quicktime" in mime else ".mp4")
    frames = await extract_frames(video_bytes, suffix)
    transcript = await extract_audio_transcript(db, video_bytes, suffix)

    adapter = build_adapter(vision_provider)
    parts = []
    try:
        for ts, png in frames:
            b64 = base64.b64encode(png).decode()
            resp = await asyncio.wait_for(adapter.chat(
                [
                    {"role": "system", "content": "Describe this single video frame precisely and briefly (2-4 sentences): scene, subjects, on-screen text, actions."},
                    {"role": "user", "content": [
                        {"type": "text", "text": f"Frame at ~{ts}s:"},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                    ]},
                ],
                model_id=vision_model.model_id,
                generation={"max_tokens": 300},
            ), timeout=60)
            text = ((resp.get("choices") or [{}])[0].get("message") or {}).get("content", "")
            if text.strip():
                parts.append(f"[{ts}s] {text.strip()}")
    finally:
        await adapter.aclose()
    if not parts:
        raise CapabilityUnsupportedError("vision model produced no frame descriptions")
    out = "Frame-by-frame description of the video:\n" + "\n".join(parts)
    if transcript:
        out += f"\n\nAudio transcript:\n{transcript[:4000]}"
    else:
        out += "\n\n(No audio transcript: no STT provider configured.)"
    return out
