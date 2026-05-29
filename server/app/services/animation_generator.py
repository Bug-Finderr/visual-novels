"""Animation overlay derivation (layered 2.5D rig).

Replaces the former THA3 puppeteer path. Each character gets up to 3
TRANSPARENT facial overlays — eyes_closed, mouth_half, mouth_open — generated
ONCE from the neutral sprite via Gemini. The browser rig composites these over
any emotion base to produce blink + lip-sync, with continuous procedural idle
motion (breathing + head sway) on top. No GPU required.

If an overlay can't be produced (or comes back non-transparent), the rig
gracefully runs motion-only for that character.
"""
from __future__ import annotations

from typing import Callable

from app.logger import logger
from app.services.ai import image_generator

# Re-exported so callers (generation pipeline) can size progress bars.
EXPRESSIONS = image_generator.EXPRESSIONS
OVERLAYS = image_generator.OVERLAYS


def generate_for_character(
    session_id: str,
    character: dict,
    art_style: str,
    neutral_image: bytes | None = None,
    progress_cb: Callable[[str, int, int], None] | None = None,
) -> dict[str, str]:
    """Generate the character's animation overlays. `character` needs at least
    `id` and `name`. Returns {overlay_name: path} for the ones that succeeded.
    """
    try:
        return image_generator.generate_character_overlays(
            session_id, character, art_style,
            neutral_image=neutral_image, progress_callback=progress_cb,
        )
    except Exception as err:
        logger.warning("overlay generation failed for %s: %s", character.get("id"), err)
        return {}
