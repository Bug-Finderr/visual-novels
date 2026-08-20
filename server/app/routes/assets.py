from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, RedirectResponse

from app.config import config
from app.services import asset_manager, storage, tts_generator

router = APIRouter(prefix="/api/v1/assets", tags=["assets"])

# Generated assets are content-addressed (char/expr filename, hash-named wav)
# and never change in place. Aggressive caching eliminates the re-fetch lag
# when the browser swaps between dozens of frames during a single scene.
_IMMUTABLE = {"Cache-Control": "public, max-age=31536000, immutable"}
_SHORT = {"Cache-Control": "public, max-age=3600"}
_NO_CACHE = {"Cache-Control": "no-cache"}


def _serve(key: str, media_type: str, headers: dict, not_found: str):
    """Serve an asset by storage key. In dev the file streams straight off
    local disk; in prod the browser normally loads it from the CDN
    (VITE_ASSET_BASE) and this route is only a fallback, so it redirects to the
    public object URL rather than proxying the bytes through Cloud Run."""
    path = storage.backend.local_path(key)
    if path is not None:
        return FileResponse(path, media_type=media_type, headers=headers)
    if config.ASSET_BACKEND == "gcs":
        return RedirectResponse(storage.backend.public_url(key))
    raise HTTPException(status_code=404, detail=not_found)


@router.get("/{session_id}/characters/{character_id}/{filename}")
def serve_character_sprite(session_id: str, character_id: str, filename: str):
    key = f"{session_id}/characters/{character_id}/{filename}"
    if not filename.startswith("overlay_") and not storage.backend.exists(key):
        # Expression sprites are now generated selectively — only the ones
        # the story's actual script uses (see routes/generation.py's usage
        # scan) — so a live/runtime path can legitimately ask for an
        # expression that was never pre-rendered (e.g. the free-text
        # Beat-Rewrite Agent choosing one no pre-rendered beat happened to
        # use). Fall back to the neutral sprite, which is always generated,
        # instead of 404ing to a blank character. Overlays are exempt — a
        # missing overlay is expected already (see _is_usable_overlay) and
        # the client handles that by running motion-only for that character.
        key = f"{session_id}/characters/{character_id}/neutral.png"
    return _serve(key, "image/png", _IMMUTABLE, "Sprite not found")


@router.get("/{session_id}/backgrounds/{filename}")
def serve_background(session_id: str, filename: str):
    key = f"{session_id}/backgrounds/{filename}"
    return _serve(key, "image/png", _IMMUTABLE, "Background not found")


@router.get("/{session_id}/cover.png")
def serve_cover(session_id: str):
    # Cover can be regenerated; allow the client to revalidate via ?v= cache-bust.
    return _serve(asset_manager.cover_key(session_id), "image/png", _SHORT, "Cover not found")


@router.get("/{session_id}/audio/{filename}")
def serve_audio(session_id: str, filename: str):
    key = f"{session_id}/audio/{filename}"
    if filename == "manifest.json":
        # manifest.json changes during runtime TTS; short cache
        return _serve(key, "application/json", _NO_CACHE, "Audio not found")
    return _serve(key, "audio/wav", _IMMUTABLE, "Audio not found")
