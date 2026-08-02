"""Generated-asset keys + save/read helpers over the storage backend.

Assets are addressed by relative KEYS (``{session_id}/cover.png`` etc.), not
absolute paths, so they persist to local disk in dev and to a public GCS bucket
in prod without any caller changes. save_* return the key (a stable string the
browser can turn into a URL via the asset base).
"""
from app.services import storage


# ---- key builders -------------------------------------------------------
def character_sprite_key(session_id: str, character_id: str, expression: str) -> str:
    return f"{session_id}/characters/{character_id}/{expression}.png"


def character_overlay_key(session_id: str, character_id: str, overlay: str) -> str:
    """Character-level animation overlay (eyes_closed / mouth_half / mouth_open),
    stored alongside the emotion sprites and prefixed `overlay_` so it can't
    collide with an emotion filename."""
    return f"{session_id}/characters/{character_id}/overlay_{overlay}.png"


def background_key(session_id: str, scene_id: str) -> str:
    return f"{session_id}/backgrounds/{scene_id}.png"


def cover_key(session_id: str) -> str:
    """Story cover key-visual (poster), top-level so it's distinct from the
    per-scene backgrounds and per-character sprites."""
    return f"{session_id}/cover.png"


# ---- writes -------------------------------------------------------------
def save_character_sprite(session_id: str, character_id: str, expression: str, image_bytes: bytes) -> str:
    key = character_sprite_key(session_id, character_id, expression)
    storage.backend.save(key, image_bytes, content_type="image/png")
    return key


def save_character_overlay(session_id: str, character_id: str, overlay: str, image_bytes: bytes) -> str:
    key = character_overlay_key(session_id, character_id, overlay)
    storage.backend.save(key, image_bytes, content_type="image/png")
    return key


def save_background(session_id: str, scene_id: str, image_bytes: bytes) -> str:
    key = background_key(session_id, scene_id)
    storage.backend.save(key, image_bytes, content_type="image/png")
    return key


def save_cover(session_id: str, image_bytes: bytes) -> str:
    key = cover_key(session_id)
    storage.backend.save(key, image_bytes, content_type="image/png")
    return key


# ---- reads / lifecycle --------------------------------------------------
def read_character_sprite(session_id: str, character_id: str, expression: str) -> bytes | None:
    return storage.backend.read(character_sprite_key(session_id, character_id, expression))


def session_assets_exist(session_id: str) -> bool:
    return storage.backend.has_prefix(session_id)


def delete_session_assets(session_id: str) -> None:
    storage.backend.delete_prefix(session_id)
