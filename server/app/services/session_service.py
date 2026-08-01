import json
from uuid import uuid4

from app.db.queries import characters as character_queries
from app.db.queries import scenes as scene_queries
from app.db.queries import sessions as session_queries
from app.services import asset_manager


def create(setup: dict, owner_id: str | None = None) -> dict:
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
        "owner_id": owner_id,
    })
    return {"id": session_id, "title": title}


def create_continuation(parent: dict) -> dict:
    """Create a child session that picks up where `parent` left off.

    Copies the parent's setup verbatim and increments chapter_number; the
    generation pipeline will detect the parent_session_id + chapter > 1
    and call story_generator.generate_world with the continuation context.
    """
    session_id = str(uuid4())
    parent_chapter = int(parent.get("chapter_number") or 1)
    chapter_number = parent_chapter + 1
    title = f"Chapter {chapter_number} — {parent.get('setup_setting', '')[:40]}"
    session_queries.create({
        "id": session_id,
        "title": title,
        "status": "created",
        "setup_genre": parent["setup_genre"],
        "setup_art_style": parent["setup_art_style"],
        "setup_setting": parent["setup_setting"],
        "setup_protagonist_name": parent["setup_protagonist_name"],
        "setup_protagonist_personality": parent["setup_protagonist_personality"],
        "setup_tone": parent["setup_tone"],
        "setup_premise": parent.get("setup_premise"),
        "owner_id": parent.get("owner_id"),  # chapters inherit the parent's owner
    })
    session_queries.set_chapter_parent(session_id, parent["id"], chapter_number)
    return {"id": session_id, "title": title, "chapterNumber": chapter_number}


def get_all() -> list[dict]:
    return session_queries.get_all()


def list_public(sort: str = "new") -> list[dict]:
    return session_queries.get_public(sort)


def list_for_owner(owner_id: str) -> list[dict]:
    return session_queries.get_for_owner(owner_id)


def ownerless_count() -> int:
    return session_queries.count_ownerless()


def claim_ownerless(owner_id: str) -> int:
    return session_queries.claim_ownerless(owner_id)


def set_visibility(session_id: str, visibility: str) -> None:
    session_queries.set_visibility(session_id, visibility)


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
        gender = (char.get("gender") or "").lower().strip() or None
        if gender not in {"female", "male", "neutral", None}:
            gender = None
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
            "gender": gender,
        })

    # `scenes` is the COMPLETE list — opening scenes, mid-arc settings, and
    # every ending's finalSceneId — generated together so no asset is needed
    # at runtime.
    scenes = story_data.get("scenes") or story_data.get("initialScenes") or []
    for scene in scenes:
        scene_queries.insert(session_id, {
            "id": scene["id"],
            "name": scene["name"],
            "description": scene["description"],
            "narrative_context": scene.get("narrativeContext"),
        })

    if scenes:
        session_queries.update_current_scene(session_id, scenes[0]["id"])

    # Persist the spine + ending catalogue + seed alignment_state.
    spine = story_data.get("storySpine") or []
    endings = story_data.get("endings") or []
    if spine and endings:
        session_queries.save_spine(session_id, story_spine=spine, endings=endings)


def patch(session_id: str, fields: dict) -> None:
    session_queries.patch(session_id, fields)


def get_characters(session_id: str) -> list[dict]:
    chars = character_queries.get_by_session(session_id)
    for c in chars:
        c["quirks"] = json.loads(c.get("quirks") or "[]")
    return chars


def get_scenes(session_id: str) -> list[dict]:
    return scene_queries.get_by_session(session_id)
