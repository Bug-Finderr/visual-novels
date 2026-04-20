import json
from uuid import uuid4

from app.db.queries import characters as character_queries
from app.db.queries import scenes as scene_queries
from app.db.queries import sessions as session_queries
from app.services import asset_manager


def create(setup: dict) -> dict:
    session_id = str(uuid4())
    title = f"{setup['genre']} - {setup['setting'][:40]}"
    session_queries.create({
        "id": session_id,
        "title": title,
        "status": "created",
        "setup_genre": setup["genre"],
        "setup_art_style": setup["artStyle"],
        "setup_setting": setup["setting"],
        "setup_protagonist_name": setup["protagonistName"],
        "setup_protagonist_personality": setup["protagonistPersonality"],
        "setup_tone": setup["tone"],
        "setup_premise": setup.get("premise"),
    })
    return {"id": session_id, "title": title}


def get_all() -> list[dict]:
    return session_queries.get_all()


def get_by_id(session_id: str) -> dict | None:
    session = session_queries.get_by_id(session_id)
    if not session:
        return None
    return {
        **session,
        "world_lore": json.loads(session["world_lore"]) if session.get("world_lore") else None,
        "plot_arc": json.loads(session["plot_arc"]) if session.get("plot_arc") else None,
    }


def delete(session_id: str) -> None:
    asset_manager.delete_session_assets(session_id)
    session_queries.delete(session_id)


def update_status(session_id: str, status: str) -> None:
    session_queries.update_status(session_id, status)


def save_story_data(session_id: str, story_data: dict) -> None:
    session_queries.save_story_data(
        session_id,
        world_lore=story_data["worldLore"],
        plot_arc=story_data["plotArc"],
    )

    for char in story_data["characters"]:
        character_queries.insert(session_id, {
            "id": char["id"],
            "name": char["name"],
            "color": char.get("color") or "#FFFFFF",
            "role": char.get("role"),
            "personality": char.get("personality"),
            "appearance": char.get("appearance"),
            "backstory": char.get("backstory"),
            "relationship": char.get("relationshipToProtagonist"),
            "speech_style": char.get("speechStyle"),
            "quirks": char.get("quirks") or [],
            "voice_caption": char.get("voiceCaption"),
        })

    for scene in story_data["initialScenes"]:
        scene_queries.insert(session_id, {
            "id": scene["id"],
            "name": scene["name"],
            "description": scene["description"],
            "narrative_context": scene.get("narrativeContext"),
        })

    if story_data["initialScenes"]:
        session_queries.update_current_scene(session_id, story_data["initialScenes"][0]["id"])


def patch(session_id: str, fields: dict) -> None:
    session_queries.patch(session_id, fields)


def get_characters(session_id: str) -> list[dict]:
    chars = character_queries.get_by_session(session_id)
    for c in chars:
        c["quirks"] = json.loads(c.get("quirks") or "[]")
    return chars


def get_scenes(session_id: str) -> list[dict]:
    return scene_queries.get_by_session(session_id)
