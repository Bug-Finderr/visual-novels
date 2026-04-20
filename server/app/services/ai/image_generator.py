import time
from typing import Callable

from google.genai import types

from app.logger import logger
from app.services import asset_manager
from app.services.ai.gemini_client import get_client, models
from app.services.ai.prompts.sprite_generation import (
    build_background_prompt,
    build_sprite_prompt,
)
from app.services.background_remover import remove_sprite_bg

EXPRESSIONS = [
    "happy", "sad", "angry", "surprised", "neutral",
    "embarrassed", "thinking", "scared", "determined", "smug",
]


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
    """Generate ONLY the neutral sprite. The other 9 expressions and 30 animation
    frames are derived by `animation_generator` via THA3 pose deltas — ~10×
    cheaper than burning a Gemini call per expression and guarantees character
    consistency across emotions.
    """
    logger.info("Generating neutral sprite for %s...", character["name"])
    neutral_prompt = build_sprite_prompt(character, "neutral", art_style, has_reference=False)
    neutral_image = _generate_image(neutral_prompt, [], "3:4")
    neutral_image = remove_sprite_bg(neutral_image)
    neutral_path = asset_manager.save_character_sprite(
        session_id, character["id"], "neutral", neutral_image
    )
    if progress_callback:
        progress_callback("neutral", 1, 1)
    return {"neutral": str(neutral_path)}


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
