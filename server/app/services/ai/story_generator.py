import json
import re
from typing import Any

from google.genai import types

from app.logger import logger
from app.services.ai.gemini_client import get_client, models
from app.services.ai.prompts.world_building import build_continuation_prompt, build_world_prompt


def _parse_json_loose(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try fenced markdown
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        try:
            return json.loads(fence.group(1))
        except json.JSONDecodeError as e2:
            logger.error("Failed to parse extracted JSON: %s", e2)

    # Fall back to first { ... last } slice
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last > first:
        try:
            return json.loads(text[first : last + 1])
        except json.JSONDecodeError:
            pass

    logger.error("All JSON parse attempts failed. Length=%d", len(text))
    logger.error("Response start: %s", text[:300])
    logger.error("Response end:   %s", text[-300:])
    raise ValueError("Failed to parse story generation response as JSON")


def generate_world(setup: dict, *, continuation: dict | None = None) -> dict:
    """Generate a complete world. If `continuation` is provided, treat this as
    the next chapter of an existing story — same world + cast, new spine +
    endings, picking up after the previous chapter's chosen ending.

    `continuation` keys: prior_session (row dict), prior_world (dict),
    prior_ending (dict), chapter_number (int).
    """
    if continuation:
        prompt = build_continuation_prompt(
            prior=continuation["prior_session"],
            prior_world=continuation["prior_world"],
            prior_ending=continuation["prior_ending"],
            chapter_number=continuation["chapter_number"],
        )
    else:
        prompt = build_world_prompt(setup)
    client = get_client()

    logger.info(
        "Generating %s with Gemini Pro...",
        "continuation chapter" if continuation else "world",
    )
    response = client.models.generate_content(
        model=models.story_pro,
        contents=[
            types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
        ],
        config=types.GenerateContentConfig(
            temperature=0.9,
            max_output_tokens=65536,
            response_mime_type="application/json",
        ),
    )

    text = ""
    for part in response.candidates[0].content.parts:
        if getattr(part, "text", None):
            text += part.text

    parsed = _parse_json_loose(text)

    required = ["worldLore", "characters", "scenes", "storySpine", "endings", "openingScript"]
    missing = [k for k in required if not parsed.get(k)]
    if missing:
        raise ValueError(f"Story generation response missing required fields: {', '.join(missing)}")

    if len(parsed["characters"]) < 3:
        logger.warning("Only %d characters generated, expected 3-5", len(parsed["characters"]))
    if len(parsed["storySpine"]) != 10:
        logger.warning("storySpine has %d beats, expected 10", len(parsed["storySpine"]))
    if len(parsed["endings"]) != 5:
        logger.warning("endings has %d entries, expected 5", len(parsed["endings"]))

    # Validate every beat's sceneId + castIds, beat choices, every ending's
    # finalSceneId. Surfacing this here means the pipeline fails fast instead
    # of at runtime when a player walks into a beat that points at a missing
    # asset or has no choices to offer.
    scene_ids = {s["id"] for s in parsed["scenes"]}
    char_ids = {c["id"] for c in parsed["characters"]}
    ending_tags = {e.get("alignmentTag") for e in parsed["endings"] if e.get("alignmentTag")}
    for beat in parsed["storySpine"]:
        if beat.get("sceneId") not in scene_ids:
            logger.warning("beat %s references missing sceneId %s", beat.get("id"), beat.get("sceneId"))
        for cid in beat.get("castIds") or []:
            if cid not in char_ids:
                logger.warning("beat %s references unknown castId %s", beat.get("id"), cid)
        choices = beat.get("choices") or []
        if len(choices) < 2:
            logger.warning("beat %s has only %d choices, expected 3", beat.get("id"), len(choices))
        for ch in choices:
            if ch.get("alignmentTag") not in ending_tags:
                logger.warning("beat %s choice %r references unknown alignmentTag %s",
                               beat.get("id"), (ch.get("text") or "")[:40], ch.get("alignmentTag"))
    for ending in parsed["endings"]:
        if ending.get("finalSceneId") not in scene_ids:
            logger.warning("ending %s references missing finalSceneId %s",
                           ending.get("id"), ending.get("finalSceneId"))

    logger.info(
        "World generated: %s, %d chars, %d scenes, %d beats, %d endings",
        parsed["worldLore"].get("name"),
        len(parsed["characters"]),
        len(parsed["scenes"]),
        len(parsed["storySpine"]),
        len(parsed["endings"]),
    )
    return parsed
