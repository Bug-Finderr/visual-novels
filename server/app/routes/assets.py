from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.config import config

router = APIRouter(prefix="/api/assets", tags=["assets"])


@router.get("/{session_id}/characters/{character_id}/{filename}")
def serve_character_sprite(session_id: str, character_id: str, filename: str):
    file_path = config.GENERATED_DIR / session_id / "characters" / character_id / filename
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Sprite not found")
    return FileResponse(file_path, media_type="image/png")


@router.get("/{session_id}/backgrounds/{filename}")
def serve_background(session_id: str, filename: str):
    file_path = config.GENERATED_DIR / session_id / "backgrounds" / filename
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Background not found")
    return FileResponse(file_path, media_type="image/png")


@router.get("/{session_id}/audio/{filename}")
def serve_audio(session_id: str, filename: str):
    file_path = config.GENERATED_DIR / session_id / "audio" / filename
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Audio not found")
    return FileResponse(file_path, media_type="audio/wav")
