import json
import re
from typing import Any

from google.genai import types

from app.logger import logger
from app.services.ai.gemini_client import get_client, models
from app.services.ai.prompts.world_building import build_world_prompt


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


def generate_world(setup: dict) -> dict:
    prompt = build_world_prompt(setup)
    client = get_client()

    logger.info("Generating world with Gemini Pro...")
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

    required = ["worldLore", "characters", "initialScenes", "openingScript"]
    missing = [k for k in required if not parsed.get(k)]
    if missing:
        raise ValueError(f"Story generation response missing required fields: {', '.join(missing)}")

    if len(parsed["characters"]) < 3:
        logger.warning("Only %d characters generated, expected 3-5", len(parsed["characters"]))

    logger.info(
        "World generated: %s, %d characters, %d scenes",
        parsed["worldLore"].get("name"),
        len(parsed["characters"]),
        len(parsed["initialScenes"]),
    )
    return parsed
