"""Per-character expression + animation frame generation via the THA3 puppeteer.

We only ask Gemini for ONE sprite per character (a clean neutral portrait) and
derive everything else by feeding pose deltas into THA3:

    Per emotion (10):
        <expr>.png             → emotion base (e.g. eyebrows + mouth shape)
        <expr>_blink.png       → emotion + eyes-closed
        <expr>_mouth_half.png  → emotion + mouth slightly open
        <expr>_mouth_open.png  → emotion + mouth wide open ("aaa")

This is ~10× cheaper than burning a separate Gemini Image call per expression
and guarantees character consistency (every frame is a warp of the same source
portrait — no Gemini drift across expressions).

If the puppeteer is unavailable, only the neutral sprite is available and the
frontend falls back to static.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Callable

from PIL import Image

from app.logger import logger
from app.services import asset_manager, puppeteer_client

# All 10 emotions Storyplex's prompts can output. Order matters for stable progress.
EXPRESSIONS = [
    "neutral", "happy", "sad", "angry", "surprised",
    "embarrassed", "thinking", "scared", "determined", "smug",
]

# Pose deltas per emotion, in puppeteer alias keys.
# Empty for neutral — the source portrait IS the neutral.
EXPRESSION_POSES: dict[str, dict[str, float]] = {
    "neutral":     {},
    "happy":       {"eyebrow_happy_l": 0.7, "eyebrow_happy_r": 0.7,
                    "mouth_raised_corner_l": 0.6, "mouth_raised_corner_r": 0.6,
                    "mouth_smirk": 0.3},
    "sad":         {"eyebrow_troubled_l": 0.85, "eyebrow_troubled_r": 0.85,
                    "eye_relaxed_l": 0.4, "eye_relaxed_r": 0.4,
                    "mouth_lowered_corner_l": 0.55, "mouth_lowered_corner_r": 0.55},
    "angry":       {"eyebrow_angry_l": 0.9, "eyebrow_angry_r": 0.9,
                    "eye_unimpressed_l": 0.3, "eye_unimpressed_r": 0.3,
                    "mouth_lowered_corner_l": 0.4, "mouth_lowered_corner_r": 0.4},
    "surprised":   {"eyebrow_raised_l": 0.85, "eyebrow_raised_r": 0.85,
                    "eye_surprised_l": 0.7, "eye_surprised_r": 0.7,
                    "mouth_aaa": 0.45},
    "embarrassed": {"eyebrow_troubled_l": 0.45, "eyebrow_troubled_r": 0.45,
                    "eye_unimpressed_l": 0.35, "eye_unimpressed_r": 0.35,
                    "mouth_smirk": 0.25, "iris_rotation_y": -0.2},
    "thinking":    {"eyebrow_lowered_l": 0.5, "eyebrow_lowered_r": 0.5,
                    "eye_unimpressed_l": 0.4, "eye_unimpressed_r": 0.4,
                    "iris_rotation_y": 0.3, "iris_rotation_x": -0.15},
    "scared":      {"eyebrow_raised_l": 0.55, "eyebrow_troubled_l": 0.4,
                    "eyebrow_raised_r": 0.55, "eyebrow_troubled_r": 0.4,
                    "eye_surprised_l": 0.65, "eye_surprised_r": 0.65,
                    "mouth_aaa": 0.2},
    "determined":  {"eyebrow_serious_l": 0.7, "eyebrow_serious_r": 0.7,
                    "eye_unimpressed_l": 0.3, "eye_unimpressed_r": 0.3,
                    "mouth_smirk": 0.3},
    "smug":        {"eyebrow_lowered_l": 0.4, "eyebrow_lowered_r": 0.4,
                    "eye_unimpressed_l": 0.5, "eye_unimpressed_r": 0.5,
                    "mouth_smirk": 0.7, "iris_rotation_x": -0.15},
}

# Animation deltas, ADDED on top of an emotion's base pose for the per-frame variants.
ANIMATION_POSES: dict[str, dict[str, float]] = {
    "blink":      {"eye_blink_l": 1.0, "eye_blink_r": 1.0},
    "mouth_half": {"mouth_aaa": 0.45},
    "mouth_open": {"mouth_aaa": 0.95},
}


def _expr_base_path(session_id: str, character_id: str, expression: str) -> Path:
    return asset_manager.get_character_sprite_path(session_id, character_id, expression)


def _anim_path(session_id: str, character_id: str, expression: str, frame: str) -> Path:
    base = asset_manager.get_character_sprite_path(session_id, character_id, expression)
    return base.with_name(f"{expression}_{frame}.png")


def _merge_pose(base: dict[str, float], overlay: dict[str, float]) -> dict[str, float]:
    return {**base, **overlay}


def _crop_face_region(neutral_rgba: Image.Image) -> tuple[Image.Image, tuple[int, int, int, int]]:
    """Heuristic face crop for an anime sprite: take a square region centered
    horizontally on the topmost opaque cluster, sized to ~1/3 of the character
    height. Returns (face_crop, (x, y, w, h)) — the crop and its location in
    the source image.
    """
    w, h = neutral_rgba.size
    alpha = neutral_rgba.split()[-1]
    bbox = alpha.getbbox()
    if bbox is None:
        # All transparent — fall back to a centered top crop
        size = min(w, h) // 2
        x = (w - size) // 2
        return neutral_rgba.crop((x, 0, x + size, size)), (x, 0, size, size)

    char_left, char_top, char_right, char_bottom = bbox
    char_h = char_bottom - char_top

    # Face is roughly the top 30% of the character.
    face_height = int(char_h * 0.30)
    face_top = char_top
    face_bottom = char_top + face_height

    # Find horizontal center of character within that strip
    strip_alpha = alpha.crop((0, face_top, w, face_bottom))
    strip_bbox = strip_alpha.getbbox()
    if strip_bbox:
        face_cx = (strip_bbox[0] + strip_bbox[2]) // 2
    else:
        face_cx = (char_left + char_right) // 2

    # Build a SQUARE crop around the face with extra context (hair, neck).
    crop_size = int(face_height * 1.7)
    x0 = max(0, face_cx - crop_size // 2)
    y0 = max(0, face_top - int(face_height * 0.15))
    x1 = min(w, x0 + crop_size)
    y1 = min(h, y0 + crop_size)
    # Re-square if clamped
    side = min(x1 - x0, y1 - y0)
    face_crop = neutral_rgba.crop((x0, y0, x0 + side, y0 + side))
    return face_crop, (x0, y0, side, side)


def _pil_to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _composite_face_onto_body(
    body: Image.Image,
    animated_face_512: bytes,
    face_box: tuple[int, int, int, int],
) -> bytes:
    """Resize the animated face to the original face-crop size, then paste it
    onto a copy of the pristine body sprite using alpha for masking. The body
    stays Gemini-sharp; only the face region is THA3-derived."""
    x, y, w, h = face_box
    with Image.open(io.BytesIO(animated_face_512)) as f:
        face_resized = f.convert("RGBA").resize((w, h), Image.LANCZOS)
    composite = body.copy()
    composite.alpha_composite(face_resized, dest=(x, y))
    buf = io.BytesIO()
    composite.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def generate_for_character(
    session_id: str,
    character_id: str,
    expressions: list[str] | None = None,
    progress_cb: Callable[[str, int, int], None] | None = None,
) -> dict[str, dict[str, str]]:
    """Derive expression bases + animation frames from the character's neutral sprite.

    Source portrait MUST exist at `<character_id>/neutral.png` already. Outputs
    `<expr>.png` for each non-neutral emotion plus `<expr>_<frame>.png` for
    each animation variant of every emotion (including neutral).
    """
    if not puppeteer_client.is_enabled():
        logger.info("puppeteer disabled; only neutral sprite available for %s", character_id)
        return {}

    neutral_path = _expr_base_path(session_id, character_id, "neutral")
    if not neutral_path.exists():
        logger.error("missing neutral sprite for %s/%s", session_id, character_id)
        return {}

    expressions = expressions or list(EXPRESSIONS)
    results: dict[str, dict[str, str]] = {}

    sprite_bytes = neutral_path.read_bytes()
    body_pil = Image.open(io.BytesIO(sprite_bytes)).convert("RGBA")

    # Crop the face region — that's what we feed to THA3 (face-prominent input
    # is what the model was trained on; gives much sharper results than a
    # squished full-body sprite).
    face_crop, face_box = _crop_face_region(body_pil)
    logger.info("face crop for %s at %s (size %dx%d)", character_id, face_box, *face_crop.size)
    face_bytes = _pil_to_png_bytes(face_crop)

    # Upload the FACE crop. The puppeteer caches features so subsequent batches are fast.
    try:
        portrait_id = puppeteer_client.upload_portrait(face_bytes)
    except Exception as err:
        logger.warning("puppeteer upload failed for %s: %s", character_id, err)
        return {}

    try:
        for i, expr in enumerate(expressions, start=1):
            base_pose = EXPRESSION_POSES.get(expr, {})

            # 4 poses per expression: emotion base + 3 animation variants on top
            poses_for_expr = {"base": base_pose}
            for anim_name, anim_pose in ANIMATION_POSES.items():
                poses_for_expr[anim_name] = _merge_pose(base_pose, anim_pose)

            # Idempotent skip if everything already exists
            wanted = {
                "base": _expr_base_path(session_id, character_id, expr),
                "blink": _anim_path(session_id, character_id, expr, "blink"),
                "mouth_half": _anim_path(session_id, character_id, expr, "mouth_half"),
                "mouth_open": _anim_path(session_id, character_id, expr, "mouth_open"),
            }
            if expr != "neutral" and all(p.exists() for p in wanted.values()):
                results[expr] = {k: str(v) for k, v in wanted.items()}
                if progress_cb:
                    progress_cb(expr, i, len(expressions))
                continue

            try:
                frames = puppeteer_client.animate_batch(portrait_id, poses_for_expr)
            except Exception as err:
                logger.warning("puppeteer batch failed for %s/%s: %s", character_id, expr, err)
                if progress_cb:
                    progress_cb(expr, i, len(expressions))
                continue

            wrote: dict[str, str] = {}
            for frame_name, png in frames.items():
                # THA3 returned 512×512 of just the face. Composite back onto
                # a copy of the pristine body sprite so the body stays sharp.
                composite_bytes = _composite_face_onto_body(body_pil, png, face_box)
                out = wanted[frame_name]
                if expr == "neutral" and frame_name == "base":
                    continue  # keep the verbatim Gemini neutral.png
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(composite_bytes)
                wrote[frame_name] = str(out)
            if expr == "neutral":
                wrote["base"] = str(neutral_path)
            results[expr] = wrote

            if progress_cb:
                progress_cb(expr, i, len(expressions))
    finally:
        puppeteer_client.delete_portrait(portrait_id)

    return results
