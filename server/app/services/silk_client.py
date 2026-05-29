"""Silk / Mulberry TTS client — WebSocket streaming with a WAV-bytes facade.

Mulberry is an expressive English instruct-TTS (rumik.ai):
  - `description`: natural-language voice steering ("warm calm narrator").
  - `speaker`: one of speaker_1..speaker_4 (preset studio voices).
  - `f0_up_key`: semitone pitch shift (-12..+12).

Streaming protocol (per rumik docs):
  1. POST /v1/tts/ws-connect (Bearer auth) -> {ws_url, token}. Both fields
     are returned SEPARATELY — the token MUST be appended as ?token=<token>
     to the ws_url before opening the socket, otherwise the server rejects
     the handshake with close code 4401.
  2. Open the WS at "<ws_url>?token=<token>", send one JSON synthesis frame.
  3. Receive raw int16 little-endian PCM frames @ 24 kHz mono.
  4. Receive {"type": "done"} (text frame) to signal end of stream.
  5. {"type": "error", ...} on failure.
"""
from __future__ import annotations

import asyncio
import io
import json
import wave
from typing import AsyncIterator, Iterable
from urllib.parse import quote, urlparse

import httpx
import websockets
from websockets.exceptions import ConnectionClosed

from app.config import config
from app.logger import logger


SAMPLE_RATE = 24_000
SAMPLE_WIDTH = 2  # int16 LE
CHANNELS = 1


class SilkUnavailable(RuntimeError):
    pass


def is_enabled() -> bool:
    return bool(config.SILK_API_KEY)


def _build_payload(
    text: str,
    *,
    description: str | None,
    speaker: str | None,
    f0_up_key: int,
    model: str | None,
    temperature: float | None,
) -> dict:
    payload: dict = {"text": text, "model": model or config.SILK_MODEL}
    if description:
        payload["description"] = description
    if speaker:
        payload["speaker"] = speaker
    if f0_up_key:
        payload["f0_up_key"] = max(-12, min(12, int(f0_up_key)))
    if temperature is not None:
        payload["temperature"] = temperature
    return payload


def _mint_ws_session(payload: dict) -> dict:
    """POST /v1/tts/ws-connect to mint a one-shot WS session.

    Auth is Bearer on this HTTP step only. The response is `{ws_url, token}`
    — the token is NOT embedded in ws_url; we append it ourselves below.
    Some deployments accept the same synthesis payload as the POST body
    while others want it empty — sending it is harmless and saves a field
    if the server pre-stages the config.
    """
    if not config.SILK_API_KEY:
        raise SilkUnavailable("SILK_API_KEY not configured")

    with httpx.Client(
        base_url=config.SILK_API_URL,
        timeout=config.SILK_TIMEOUT,
        headers={"Authorization": f"Bearer {config.SILK_API_KEY}"},
    ) as c:
        r = c.post("/v1/tts/ws-connect", json=payload)
        r.raise_for_status()
        return r.json()


async def _mint_ws_session_async(payload: dict) -> dict:
    """Async version — used inside `_async_stream` so the event loop is not
    blocked for ~200 ms while the HTTP round-trip completes. Same shape and
    semantics as the sync `_mint_ws_session`.
    """
    if not config.SILK_API_KEY:
        raise SilkUnavailable("SILK_API_KEY not configured")
    async with httpx.AsyncClient(
        base_url=config.SILK_API_URL,
        timeout=config.SILK_TIMEOUT,
        headers={"Authorization": f"Bearer {config.SILK_API_KEY}"},
    ) as c:
        r = await c.post("/v1/tts/ws-connect", json=payload)
        r.raise_for_status()
        return r.json()


def _build_ws_url(session: dict) -> str:
    """Combine the ws_url + token fields from ws-connect into the URL to
    actually open. Handles both naming conventions defensively.
    """
    ws_url = session.get("ws_url") or session.get("wsUrl")
    token = session.get("token") or session.get("access_token")
    if not ws_url:
        raise SilkUnavailable(f"ws-connect response missing ws_url: {session}")
    if not token:
        # Either token is already baked into ws_url (legacy shape) or the
        # server didn't return one — try the bare ws_url and let the server
        # reject if needed.
        return ws_url
    # Don't double-append if the server already included ?token= in ws_url.
    if "token=" in urlparse(ws_url).query:
        return ws_url
    sep = "&" if "?" in ws_url else "?"
    return f"{ws_url}{sep}token={quote(str(token), safe='')}"


async def _async_stream(payload: dict) -> AsyncIterator[bytes]:
    """Async generator yielding raw PCM bytes from the streaming endpoint."""
    session = await _mint_ws_session_async(payload)
    ws_url = _build_ws_url(session)

    async with websockets.connect(ws_url, max_size=None) as ws:
        await ws.send(json.dumps(payload))
        while True:
            try:
                msg = await ws.recv()
            except ConnectionClosed as cc:
                # Surface abnormal closes so quota / rate-limit / server errors
                # don't masquerade as a clean done. 1000 (normal) and 1001
                # (going away) are clean; everything else is suspect.
                code = getattr(cc, "code", None) or getattr(cc.rcvd, "code", None) if hasattr(cc, "rcvd") else None
                if code is not None and code not in (1000, 1001):
                    raise SilkUnavailable(f"ws closed with code {code}: {cc}")
                return
            if isinstance(msg, (bytes, bytearray)):
                if msg:
                    yield bytes(msg)
            else:
                try:
                    obj = json.loads(msg)
                except json.JSONDecodeError:
                    continue
                t = obj.get("type")
                if t == "done":
                    return
                if t == "error":
                    raise SilkUnavailable(f"silk error: {obj}")


def _wrap_pcm_as_wav(pcm_chunks: Iterable[bytes]) -> bytes:
    """Concatenate int16 LE PCM @ 24kHz mono into a standard RIFF WAV blob."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(SAMPLE_RATE)
        total = 0
        for chunk in pcm_chunks:
            if chunk:
                wf.writeframes(chunk)
                total += len(chunk)
    return buf.getvalue()


async def _collect_pcm(payload: dict) -> list[bytes]:
    chunks: list[bytes] = []
    async for chunk in _async_stream(payload):
        chunks.append(chunk)
    return chunks


async def synthesize_async(
    text: str,
    *,
    description: str | None = None,
    speaker: str | None = None,
    f0_up_key: int = 0,
    model: str | None = None,
    temperature: float | None = None,
) -> AsyncIterator[bytes]:
    """Async generator of raw PCM int16 LE @ 24 kHz mono chunks.

    Use from async contexts (e.g. a FastAPI WS relay to the browser). Sync
    callers should use `synthesize()` which collects + wraps in WAV.
    """
    payload = _build_payload(
        text,
        description=description, speaker=speaker,
        f0_up_key=f0_up_key, model=model, temperature=temperature,
    )
    async for chunk in _async_stream(payload):
        yield chunk


def synthesize(
    text: str,
    *,
    description: str | None = None,
    speaker: str | None = None,
    f0_up_key: int = 0,
    model: str | None = None,
    temperature: float | None = None,
) -> bytes:
    """Synthesize `text` and return a finished WAV blob (raw PCM wrapped in a
    standard RIFF header). Internally streams the PCM via the Mulberry WS.

    Called from worker threads (the generation pipeline runs in
    asyncio.to_thread), so spinning up a fresh event loop per call via
    asyncio.run is safe — there is no outer loop to clash with.
    """
    payload = _build_payload(
        text,
        description=description, speaker=speaker,
        f0_up_key=f0_up_key, model=model, temperature=temperature,
    )
    chunks = asyncio.run(_collect_pcm(payload))
    # 0 PCM bytes means the server opened the WS, accepted the payload, and
    # immediately closed — typically a quota/rate-limit signal masquerading as
    # a clean done. Raise instead of writing a header-only WAV; the caller
    # then skips the manifest entry so a re-run can retry.
    if not chunks or sum(len(c) for c in chunks) == 0:
        raise SilkUnavailable(
            "synthesis returned 0 PCM bytes (likely quota/rate-limit)"
        )
    return _wrap_pcm_as_wav(chunks)


def health() -> bool:
    """Cheap reachability check — does NOT consume synthesis quota."""
    if not is_enabled():
        return False
    try:
        with httpx.Client(
            base_url=config.SILK_API_URL,
            timeout=10.0,
            headers={"Authorization": f"Bearer {config.SILK_API_KEY}"},
        ) as c:
            r = c.get("/v1/tts/ws-connect", headers={})
            # 401/405 still mean the host is up; 5xx is a real fail.
            return r.status_code < 500
    except Exception as exc:
        logger.warning("silk health check failed: %s", exc)
        return False
