import io
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from PIL import Image
from google.genai import types

from app.logger import logger
from app.services import asset_manager
from app.services.ai.gemini_client import get_client, models
from app.services.ai.prompts.sprite_generation import (
    build_background_prompt,
    build_cover_prompt,
    build_overlay_prompt,
    build_sprite_prompt,
)
from app.services.background_remover import remove_sprite_bg

# Gemini Image API tolerates a small amount of parallelism; 4 in flight is the
# sweet spot for our pipeline (faster wall-clock without tripping rate limits).
# Lowered from 4: generate_character_overlays runs this ×2 characters at once
# (see animation_generator's outer pool), so this was 8-wide at peak — too
# much concurrent image processing for a 2GB instance. Raise back toward 4
# if the instance is bumped to a larger plan.
_IMAGE_PARALLELISM = 2

EXPRESSIONS = [
    "happy", "sad", "angry", "surprised", "neutral",
    "embarrassed", "thinking", "scared", "determined", "smug",
]

# Animation overlays composited over any emotion base by the browser rig.
OVERLAYS = ["eyes_closed", "mouth_half", "mouth_open"]


def _is_usable_overlay(png_bytes: bytes) -> bool:
    """Reject overlays that aren't mostly transparent.

    A valid overlay paints only a small facial region on a transparent canvas.
    If Gemini returns an opaque image (no/low transparency), compositing it
    would cover the whole character — so we discard it and the rig falls back
    to motion-only (no blink / lip-sync) for that character.
    """
    try:
        with Image.open(io.BytesIO(png_bytes)) as im:
            im = im.convert("RGBA")
            alpha = im.getchannel("A")
            # Fraction of fully/near transparent pixels.
            hist = alpha.histogram()
            total = im.width * im.height
            transparent = sum(hist[:16])  # alpha 0..15
            return total > 0 and (transparent / total) >= 0.5
    except Exception:
        return False


def _generate_image(
    prompt_text: str,
    reference_images: list[bytes] | None = None,
    aspect_ratio: str = "1:1",
    max_retries: int = 3,
) -> bytes:
    parts: list[types.Part] = [types.Part.from_text(text=prompt_text)]
    for ref in reference_images or []:
        parts.append(types.Part.from_bytes(data=ref, mime_type="image/png"))

    client = get_client()

    for attempt in range(1, max_retries + 1):
        try:
            response = client.models.generate_content(
                model=models.image_gen,
                contents=[types.Content(role="user", parts=parts)],
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE"],
                    image_config=types.ImageConfig(
                        aspect_ratio=aspect_ratio,
                    ),
                ),
            )

            if not response.candidates:
                raise RuntimeError("Gemini returned no candidates")

            candidate = response.candidates[0]
            if not candidate.content or not candidate.content.parts:
                reason = getattr(candidate, "finish_reason", "unknown")
                raise RuntimeError(f"Gemini candidate has no content (finishReason: {reason})")

            for part in candidate.content.parts:
                inline = getattr(part, "inline_data", None)
                if inline and inline.data:
                    return inline.data  # bytes

            raise RuntimeError("No image data in Gemini response parts")
        except Exception as err:
            logger.warning("Image generation attempt %d/%d failed: %s", attempt, max_retries, err)
            if attempt == max_retries:
                raise RuntimeError(f"Image generation failed after {max_retries} attempts: {err}") from err
            delay = 2 ** attempt
            logger.info("Retrying in %ds...", delay)
            time.sleep(delay)

    raise RuntimeError("unreachable")  # pragma: no cover


def generate_character_sprites(
    session_id: str,
    character: dict,
    art_style: str,
    progress_callback: Callable[[str, int, int], None] | None = None,
) -> dict[str, str]:
    """Generate 10 Gemini sprites per character — one per emotion.

    The neutral sprite is generated first (no reference) and then used as
    the reference image for every other emotion to keep character identity
    consistent (same face, hair, clothing; only the facial expression + body
    language change per emotion).

    THA3 still animates on top (blink + mouth-flap), but the BASE emotion
    art now comes from Gemini — which can actually render visibly different
    expressions, unlike THA3's continuous-driving pose deltas which are too
    subtle to read as discrete emotion snapshots.
    """
    results: dict[str, str] = {}

    # 1. Neutral first — it's the identity anchor for the other nine.
    logger.info("Generating neutral sprite for %s...", character["name"])
    neutral_prompt = build_sprite_prompt(character, "neutral", art_style, has_reference=False)
    neutral_image = _generate_image(neutral_prompt, [], "3:4")
    neutral_image = remove_sprite_bg(neutral_image)
    neutral_path = asset_manager.save_character_sprite(
        session_id, character["id"], "neutral", neutral_image
    )
    results["neutral"] = str(neutral_path)
    if progress_callback:
        progress_callback("neutral", 1, len(EXPRESSIONS))

    # 2. Other 9 — generated in PARALLEL, each using the neutral bytes as
    #    reference for consistency. Cuts wall-clock from ~108 s (9 sequential
    #    Gemini calls at ~12 s each) to ~36 s (3 batches of 4 parallel calls).
    remaining = [e for e in EXPRESSIONS if e != "neutral"]

    def _gen_one(expr: str) -> tuple[str, str] | tuple[str, None]:
        logger.info("Generating %s sprite for %s...", expr, character["name"])
        try:
            prompt = build_sprite_prompt(character, expr, art_style, has_reference=True)
            image = _generate_image(prompt, [neutral_image], "3:4")
            image = remove_sprite_bg(image)
            path = asset_manager.save_character_sprite(session_id, character["id"], expr, image)
            return expr, str(path)
        except Exception as err:
            logger.warning("emotion sprite %s/%s failed: %s", character["id"], expr, err)
            return expr, None

    done = 1
    with ThreadPoolExecutor(max_workers=_IMAGE_PARALLELISM) as pool:
        for expr, path in pool.map(_gen_one, remaining):
            done += 1
            if path:
                results[expr] = path
            if progress_callback:
                progress_callback(expr, done, len(EXPRESSIONS))

    return results


def generate_character_overlays(
    session_id: str,
    character: dict,
    art_style: str,
    neutral_image: bytes | None = None,
    progress_callback: Callable[[str, int, int], None] | None = None,
) -> dict[str, str]:
    """Generate the 3 transparent animation overlays for a character.

    These are derived ONCE per character from the neutral sprite (the rig's
    framing anchor) and composited by the browser over any emotion base to
    produce blink + lip-sync — no GPU, replacing the old THA3 derivation.

    Overlays that come back non-transparent (would cover the character) are
    rejected; the rig then runs motion-only for that character.
    """
    if neutral_image is None:
        neutral_image = asset_manager.read_character_sprite(session_id, character["id"], "neutral")
        if neutral_image is None:
            logger.warning("no neutral sprite for %s; skipping overlays", character["id"])
            return {}

    # 3 overlays per character, generated in parallel (they share the
    # neutral reference and don't depend on each other).
    def _gen_overlay(overlay: str) -> tuple[str, str | None]:
        logger.info("Generating %s overlay for %s...", overlay, character["name"])
        try:
            prompt = build_overlay_prompt(character, overlay, art_style)
            image = _generate_image(prompt, [neutral_image], "3:4")
            if not _is_usable_overlay(image):
                logger.warning(
                    "overlay %s/%s not transparent enough — discarding",
                    character["id"], overlay,
                )
                return overlay, None
            path = asset_manager.save_character_overlay(
                session_id, character["id"], overlay, image,
            )
            return overlay, str(path)
        except Exception as err:
            logger.warning("overlay %s/%s failed: %s", character["id"], overlay, err)
            return overlay, None

    results: dict[str, str] = {}
    done = 0
    with ThreadPoolExecutor(max_workers=_IMAGE_PARALLELISM) as pool:
        for overlay, path in pool.map(_gen_overlay, OVERLAYS):
            done += 1
            if path:
                results[overlay] = path
            if progress_callback:
                progress_callback(overlay, done, len(OVERLAYS))

    return results


def generate_background(
    session_id: str,
    scene: dict,
    art_style: str,
    progress_callback: Callable[[str], None] | None = None,
) -> str:
    logger.info("Generating background for %s...", scene["name"])
    prompt = build_background_prompt(scene, art_style)
    image = _generate_image(prompt, [], "16:9")
    path = asset_manager.save_background(session_id, scene["id"], image)
    if progress_callback:
        progress_callback(scene["id"])
    return str(path)


def generate_single_sprite(
    session_id: str,
    character: dict,
    expression: str,
    art_style: str,
    reference_image: bytes | None = None,
) -> str:
    prompt = build_sprite_prompt(character, expression, art_style, has_reference=bool(reference_image))
    refs = [reference_image] if reference_image else []
    image = _generate_image(prompt, refs, "3:4")
    image = remove_sprite_bg(image)
    return str(asset_manager.save_character_sprite(session_id, character["id"], expression, image))


def generate_neutral_only(session_id: str, character: dict, art_style: str) -> bytes:
    """Render JUST the neutral sprite and return its image bytes.

    Used by the parallel pipeline as Phase A — the bytes are then handed off
    as the reference for every other emotion + every overlay, kept in memory
    so the disk file is not re-read for each downstream call.
    """
    prompt = build_sprite_prompt(character, "neutral", art_style, has_reference=False)
    image = _generate_image(prompt, [], "3:4")
    image = remove_sprite_bg(image)
    asset_manager.save_character_sprite(session_id, character["id"], "neutral", image)
    return image


def generate_cover(
    session_id: str,
    cover_ctx: dict,
    art_style: str,
    reference_image: bytes | None = None,
) -> str:
    """Generate the story's portrait cover key-visual and save it as cover.png.

    Unlike sprites, the background is KEPT — this is a full illustration, not a
    transparent cut-out. An optional main-character neutral sprite is passed as
    a reference so the cover's cast stays on-model.
    """
    prompt = build_cover_prompt(cover_ctx, art_style, has_reference=bool(reference_image))
    refs = [reference_image] if reference_image else []
    image = _generate_image(prompt, refs, "3:4")
    return str(asset_manager.save_cover(session_id, image))
