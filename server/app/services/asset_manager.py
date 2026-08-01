from pathlib import Path

from app.config import config
from app.utils.file_utils import ensure_dir, file_exists, remove_dir, write_file


def get_character_sprite_path(session_id: str, character_id: str, expression: str) -> Path:
    return config.GENERATED_DIR / session_id / "characters" / character_id / f"{expression}.png"


def get_character_overlay_path(session_id: str, character_id: str, overlay: str) -> Path:
    """Character-level animation overlay (eyes_closed / mouth_half / mouth_open).

    Lives alongside the emotion sprites so the existing character-asset route
    serves it without changes. Prefixed `overlay_` to avoid colliding with
    emotion filenames.
    """
    return (
        config.GENERATED_DIR / session_id / "characters" / character_id
        / f"overlay_{overlay}.png"
    )


def save_character_overlay(session_id: str, character_id: str, overlay: str, image_bytes: bytes) -> Path:
    path = get_character_overlay_path(session_id, character_id, overlay)
    write_file(path, image_bytes)
    return path


def get_background_path(session_id: str, scene_id: str) -> Path:
    return config.GENERATED_DIR / session_id / "backgrounds" / f"{scene_id}.png"


def save_character_sprite(session_id: str, character_id: str, expression: str, image_bytes: bytes) -> Path:
    path = get_character_sprite_path(session_id, character_id, expression)
    write_file(path, image_bytes)
    return path


def save_background(session_id: str, scene_id: str, image_bytes: bytes) -> Path:
    path = get_background_path(session_id, scene_id)
    write_file(path, image_bytes)
    return path


def get_cover_path(session_id: str) -> Path:
    """Story cover key-visual (poster). Top-level so it's distinct from the
    per-scene backgrounds and per-character sprites."""
    return config.GENERATED_DIR / session_id / "cover.png"


def save_cover(session_id: str, image_bytes: bytes) -> Path:
    path = get_cover_path(session_id)
    write_file(path, image_bytes)
    return path


def session_assets_exist(session_id: str) -> bool:
    return file_exists(config.GENERATED_DIR / session_id)


def delete_session_assets(session_id: str) -> None:
    remove_dir(config.GENERATED_DIR / session_id)


def ensure_session_dir(session_id: str) -> None:
    ensure_dir(config.GENERATED_DIR / session_id)
