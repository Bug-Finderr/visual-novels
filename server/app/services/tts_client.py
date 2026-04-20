"""HTTP client for the Irodori TTS server (Japanese voice synthesis)."""
from __future__ import annotations

import httpx

from app.config import config
from app.logger import logger


class TtsUnavailable(RuntimeError):
    pass


def is_enabled() -> bool:
    return bool(config.TTS_URL)


def _client() -> httpx.Client:
    if not config.TTS_URL:
        raise TtsUnavailable("TTS_URL not configured")
    return httpx.Client(base_url=config.TTS_URL, timeout=config.TTS_TIMEOUT)


def health() -> dict | None:
    if not is_enabled():
        return None
    try:
        with _client() as c:
            r = c.get("/health")
            r.raise_for_status()
            return r.json()
    except Exception as exc:
        logger.warning("tts health check failed: %s", exc)
        return None


def synthesize(text: str, caption: str | None = None, *, num_steps: int = 40,
               seed: int | None = None) -> bytes:
    """Synthesize Japanese text → WAV bytes."""
    payload = {"text": text, "num_steps": num_steps}
    if caption:
        payload["caption"] = caption
    if seed is not None:
        payload["seed"] = seed
    with _client() as c:
        r = c.post("/synthesize", json=payload)
        r.raise_for_status()
        return r.content
