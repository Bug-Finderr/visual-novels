from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.config import config

router = APIRouter(prefix="/api/assets", tags=["assets"])

# Generated assets are content-addressed (char/expr filename, hash-named wav)
# and never change in place. Aggressive caching eliminates the re-fetch lag
# when the browser swaps between dozens of frames during a single scene.
_IMMUTABLE = {"Cache-Control": "public, max-age=31536000, immutable"}


@router.get("/{session_id}/characters/{character_id}/{filename}")
def serve_character_sprite(session_id: str, character_id: str, filename: str):
    file_path = config.GENERATED_DIR / session_id / "characters" / character_id / filename
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Sprite not found")
    return FileResponse(file_path, media_type="image/png", headers=_IMMUTABLE)


@router.get("/{session_id}/backgrounds/{filename}")
def serve_background(session_id: str, filename: str):
    file_path = config.GENERATED_DIR / session_id / "backgrounds" / filename
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Background not found")
    return FileResponse(file_path, media_type="image/png", headers=_IMMUTABLE)


@router.get("/{session_id}/cover.png")
def serve_cover(session_id: str):
    file_path = config.GENERATED_DIR / session_id / "cover.png"
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Cover not found")
    # Cover can be regenerated; allow the client to revalidate via ?v= cache-bust.
    return FileResponse(file_path, media_type="image/png",
                        headers={"Cache-Control": "public, max-age=3600"})


@router.get("/{session_id}/audio/{filename}")
def serve_audio(session_id: str, filename: str):
    file_path = config.GENERATED_DIR / session_id / "audio" / filename
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Audio not found")
    # manifest.json changes during runtime TTS; short cache
    if filename == "manifest.json":
        return FileResponse(file_path, media_type="application/json",
                            headers={"Cache-Control": "no-cache"})
    return FileResponse(file_path, media_type="audio/wav", headers=_IMMUTABLE)
