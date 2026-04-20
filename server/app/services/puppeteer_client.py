"""HTTP client for the THA3 character-puppeteer running on a remote GPU VM."""
from __future__ import annotations

import base64
import io

import httpx

from app.config import config
from app.logger import logger


class PuppeteerUnavailable(RuntimeError):
    pass


def is_enabled() -> bool:
    return bool(config.PUPPETEER_URL)


def _client() -> httpx.Client:
    if not config.PUPPETEER_URL:
        raise PuppeteerUnavailable("PUPPETEER_URL not configured")
    return httpx.Client(base_url=config.PUPPETEER_URL, timeout=config.PUPPETEER_TIMEOUT)


def health() -> dict | None:
    if not is_enabled():
        return None
    try:
        with _client() as c:
            r = c.get("/health")
            r.raise_for_status()
            return r.json()
    except Exception as exc:
        logger.warning("puppeteer health check failed: %s", exc)
        return None


def upload_portrait(image_bytes: bytes) -> str:
    """Upload a portrait, get back a portrait_id the puppeteer caches features for."""
    with _client() as c:
        files = {"file": ("portrait.png", io.BytesIO(image_bytes), "image/png")}
        r = c.post("/portrait", files=files)
        r.raise_for_status()
        return r.json()["portrait_id"]


def animate_batch(portrait_id: str, poses: dict[str, dict[str, float]]) -> dict[str, bytes]:
    """Generate N animated frames in one call. Returns {frame_name: png_bytes}."""
    with _client() as c:
        r = c.post("/animate_batch", json={"portrait_id": portrait_id, "poses": poses})
        r.raise_for_status()
        data = r.json()
    return {name: base64.b64decode(b64) for name, b64 in data["frames"].items()}


def delete_portrait(portrait_id: str) -> None:
    try:
        with _client() as c:
            c.delete(f"/portrait/{portrait_id}")
    except Exception:
        pass  # best-effort cleanup
