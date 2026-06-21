"""Browser-facing TTS WebSocket — tunnels Mulberry's stream to the client.

Flow:
  1. Client opens WS at /api/sessions/{sid}/tts/stream
  2. Client sends one JSON frame: {scriptString, text, characterId?, expression?}
  3. Server resolves the character's voice profile (deterministic), checks the
     on-disk cache. If a WAV is already cached, server re-streams its PCM
     payload back to the browser in 100 ms chunks (no Mulberry call, no cost).
  4. Otherwise the server opens an upstream Mulberry WS, forwards each raw PCM
     frame straight to the client AS IT ARRIVES, accumulates a copy, and after
     the upstream {type:done}, writes the WAV file + manifest entry so the next
     replay hits the cache.
  5. Server sends {"type":"done"} text frame when finished; {"type":"error", ...}
     on failure.

All audio frames are raw int16 LE @ 24 kHz mono — same as Mulberry's native
format. The client decodes them into AudioBuffers and queues for playback so
the line starts speaking before the synthesis is complete.
"""
from __future__ import annotations

import asyncio
import json
import wave
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.db.queries import characters as character_queries
from app.logger import logger
from app.services import silk_client, tts_generator

router = APIRouter(prefix="/api/sessions", tags=["tts-stream"])


def _resolve_profile(session_id: str, character_id: str | None) -> dict:
    if not character_id:
        return tts_generator.NARRATOR_PROFILE
    row = character_queries.get_by_id(session_id, character_id) or {}
    return tts_generator._character_profile(
        character_id,
        row.get("voice_caption"),
        gender=row.get("gender"),
    )


async def _stream_cached_pcm(ws: WebSocket, wav_path: Path) -> None:
    """Stream a cached WAV's PCM payload as 100 ms chunks."""
    with wave.open(str(wav_path), "rb") as wf:
        sr = wf.getframerate()
        chunk_frames = max(sr // 10, 1)
        while True:
            pcm = wf.readframes(chunk_frames)
            if not pcm:
                break
            await ws.send_bytes(pcm)
            # Yield so the WebSocket flushes mid-file instead of dumping
            # several megabytes in one go.
            await asyncio.sleep(0)


@router.websocket("/{session_id}/tts/stream")
async def tts_stream(ws: WebSocket, session_id: str):
    await ws.accept()
    try:
        cfg = await ws.receive_json()
    except Exception:
        await ws.close()
        return

    script_string = (cfg.get("scriptString") or "").strip()
    text = (cfg.get("text") or script_string).strip()
    character_id = cfg.get("characterId")
    expression = cfg.get("expression")

    if not text:
        try:
            await ws.send_json({"type": "error", "message": "empty text"})
        finally:
            await ws.close()
        return

    profile = _resolve_profile(session_id, character_id)
    key = tts_generator._audio_key_for(script_string) if script_string else tts_generator._audio_key_for(text)
    out_path = tts_generator.audio_path(session_id, key)

    try:
        if out_path.exists():
            await _stream_cached_pcm(ws, out_path)
            await ws.send_json({"type": "done", "cached": True})
            await ws.close()
            return

        if not silk_client.is_enabled():
            await ws.send_json({"type": "error", "message": "SILK_API_KEY not configured"})
            await ws.close()
            return

        payload = silk_client._build_payload(
            text,
            description=tts_generator._compose_description(profile.get("description"), expression),
            speaker=profile.get("speaker"),
            f0_up_key=profile.get("f0_up_key", 0),
            model=None, temperature=None,
        )

        chunks: list[bytes] = []
        try:
            async for chunk in silk_client._async_stream(payload):
                if not chunk:
                    continue
                await ws.send_bytes(chunk)
                # Yield once per frame so the WS writer flushes the chunk to
                # the browser BEFORE the next upstream recv()  — without this
                # tiny yield Starlette can coalesce frames and the browser
                # only sees a burst at the very end.
                await asyncio.sleep(0)
                chunks.append(chunk)
        except WebSocketDisconnect:
            return
        except Exception as exc:
            logger.warning("tts upstream failed: %s", exc)
            try:
                await ws.send_json({"type": "error", "message": str(exc)})
            except Exception:
                pass
            return

        total_pcm = sum(len(c) for c in chunks)
        if total_pcm == 0:
            try:
                await ws.send_json({"type": "error", "message": "0 PCM bytes (likely rate-limit)"})
            except Exception:
                pass
            return

        # Tell the browser we're done BEFORE writing the cache — playback
        # can start tearing down its WS immediately, and the disk write
        # happens off the hot path.
        await ws.send_json({"type": "done", "cached": False})
        await ws.close()

        wav = silk_client._wrap_pcm_as_wav(chunks)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(wav)
        if script_string:
            manifest = tts_generator._load_manifest(session_id)
            manifest[script_string] = f"{key}.wav"
            tts_generator._save_manifest(session_id, manifest)
    except WebSocketDisconnect:
        return
    except Exception as exc:
        logger.exception("tts ws unexpected error: %s", exc)
        try:
            await ws.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass
