import json
import re
from typing import Any

from google.genai import types

from app.db.queries import characters as character_queries
from app.db.queries import dialogue_history as dialogue_history_queries
from app.db.queries import scenes as scene_queries
from app.db.queries import sessions as session_queries
from app.logger import logger
from app.services.ai.gemini_client import get_client, models
from app.services.ai.prompts.dialogue_system import build_dialogue_system_prompt


def _load_session_context(session_id: str) -> dict:
    session = session_queries.get_by_id(session_id)
    if not session:
        raise ValueError(f"Session {session_id} not found")

    chars = []
    for c in character_queries.get_by_session(session_id):
        chars.append({**c, "quirks": json.loads(c.get("quirks") or "[]")})

    current_scene = None
    if session.get("current_scene_id"):
        current_scene = scene_queries.get_by_id(session_id, session["current_scene_id"])

    return {
        "worldLore": json.loads(session.get("world_lore") or "{}"),
        "characters": chars,
        "plotArc": json.loads(session.get("plot_arc") or "{}"),
        "currentScene": current_scene,
        "protagonistName": session["setup_protagonist_name"],
        "tone": session["setup_tone"],
        "currentLabel": session.get("current_label"),
    }


def _build_conversation_history(session_id: str) -> list[types.Content]:
    recent = dialogue_history_queries.get_recent(session_id, 40)
    return [
        types.Content(role=entry["role"], parts=[types.Part.from_text(text=entry["content"])])
        for entry in recent
    ]


def _parse_response(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if match:
            return json.loads(match.group(1))
        logger.error("Failed to parse dialogue response: %s", text[:500])
        raise ValueError("Failed to parse dialogue response as JSON")


def process_player_action(session_id: str, action: dict) -> dict:
    session = _load_session_context(session_id)
    system_prompt = build_dialogue_system_prompt(session)
    history = _build_conversation_history(session_id)

    if action["type"] == "choice":
        user_message = f"[PLAYER CHOSE: \"{action['text']}\"] (consequence hint: {action.get('consequence', '')})"
    else:
        user_message = f"[PLAYER SAYS: \"{action['text']}\"]"

    messages = history + [
        types.Content(role="user", parts=[types.Part.from_text(text=user_message)])
    ]

    logger.info("Processing player action for session %s: %s", session_id, action["type"])

    client = get_client()
    response = client.models.generate_content(
        model=models.dialogue_flash,
        contents=messages,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.8,
            max_output_tokens=3000,
            response_mime_type="application/json",
        ),
    )

    response_text = response.candidates[0].content.parts[0].text
    ai_output = _parse_response(response_text)

    dialogue_history_queries.insert(session_id, "user", user_message, session.get("currentLabel"))
    dialogue_history_queries.insert(session_id, "model", response_text, session.get("currentLabel"))

    return ai_output
