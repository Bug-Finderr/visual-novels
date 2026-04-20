import asyncio

from fastapi import APIRouter, HTTPException

from app.db.queries import characters as character_queries
from app.db.queries import scenes as scene_queries
from app.db.queries import sessions as session_queries
from app.logger import logger
from app.models.schemas import ChoiceRequest, FreeInputRequest, GameplayResponse
from app.services import animation_generator, script_builder, session_service, tts_generator
from app.services.ai import dialogue_engine, image_generator

router = APIRouter(prefix="/api/sessions", tags=["gameplay"])


def _derive_remaining_for_dynamic_character(session_id: str, char_id: str) -> None:
    """For a runtime-introduced character we already have neutral; derive the
    other expressions + animation frames via the puppeteer (no extra Gemini)."""
    try:
        animation_generator.generate_for_character(session_id, char_id)
    except Exception as err:
        logger.warning("dynamic animation gen failed for %s: %s", char_id, err)
    character_queries.mark_sprites_generated(session_id, char_id)
    logger.info("All frames derived for dynamic character %s", char_id)


def _process_ai_response(session_id: str, ai_output: dict) -> dict:
    session = session_service.get_by_id(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    new_character = None
    if ai_output.get("newCharacterIntroduced"):
        char_data = ai_output["newCharacterIntroduced"]
        char_id = char_data.get("id") or char_data["name"].lower().replace(" ", "_")

        character_queries.insert(session_id, {
            "id": char_id,
            "name": char_data["name"],
            "color": char_data.get("color") or "#FFFFFF",
            "role": char_data.get("role") or "supporting",
            "personality": char_data.get("personality"),
            "appearance": char_data.get("appearance"),
            "backstory": "",
            "relationship": "",
            "speech_style": char_data.get("speechStyle") or "",
            "quirks": [],
            "is_dynamic": 1,
        })

        image_generator.generate_single_sprite(
            session_id,
            {"id": char_id, "name": char_data["name"], "appearance": char_data["appearance"]},
            "neutral",
            session["setup_art_style"],
        )

        # Derive expressions + animation frames in the background (puppeteer only)
        asyncio.get_event_loop().run_in_executor(
            None, _derive_remaining_for_dynamic_character, session_id, char_id,
        )

        new_character = {
            "id": char_id,
            "name": char_data["name"],
            "color": char_data.get("color") or "#FFFFFF",
        }

    new_scene = None
    if ai_output.get("sceneChangeNeeded"):
        scene_data = ai_output["sceneChangeNeeded"]
        scene_queries.insert(session_id, {
            "id": scene_data["id"],
            "name": scene_data["name"],
            "description": scene_data["description"],
            "narrative_context": "Dynamic scene",
            "is_dynamic": 1,
        })
        image_generator.generate_background(session_id, scene_data, session["setup_art_style"])
        scene_queries.mark_image_generated(session_id, scene_data["id"])
        new_scene = {"id": scene_data["id"], "name": scene_data["name"]}

    built = script_builder.build_runtime_label(ai_output)
    label_name = built["labelName"]
    statements = built["statements"]
    extra_labels = built["extraLabels"]

    script_builder.save_label(session_id, label_name, statements)
    for name, stmts in extra_labels.items():
        script_builder.save_label(session_id, name, stmts)

    session_queries.update_current_label(session_id, label_name)

    # Best-effort runtime TTS for the new dialogue lines (synchronous so the
    # response carries the manifest delta; ~1s per line on H100).
    audio_manifest: dict[str, str] = {}
    try:
        audio_manifest = tts_generator.generate_for_statements(
            session_id, ai_output.get("statements") or [],
        )
    except Exception as err:
        logger.warning("runtime TTS failed: %s", err)

    return {
        "newLabel": label_name,
        "statements": statements,
        "extraLabels": extra_labels,
        "choices": ai_output.get("choices") or [],
        "allowFreeInput": bool(ai_output.get("allowFreeInput")),
        "newCharacter": new_character,
        "newScene": new_scene,
        "audioManifest": audio_manifest,
    }


@router.post("/{session_id}/choice", response_model=GameplayResponse)
async def handle_choice(session_id: str, payload: ChoiceRequest):
    try:
        ai_output = await asyncio.to_thread(
            dialogue_engine.process_player_action,
            session_id,
            {"type": "choice", "text": payload.text, "consequence": payload.consequence or ""},
        )
        result = await asyncio.to_thread(_process_ai_response, session_id, ai_output)
        return result
    except HTTPException:
        raise
    except Exception as err:
        logger.exception("Choice handling error: %s", err)
        raise HTTPException(status_code=500, detail=str(err))


@router.post("/{session_id}/free-input", response_model=GameplayResponse)
async def handle_free_input(session_id: str, payload: FreeInputRequest):
    try:
        ai_output = await asyncio.to_thread(
            dialogue_engine.process_player_action,
            session_id,
            {"type": "free-input", "text": payload.text},
        )
        result = await asyncio.to_thread(_process_ai_response, session_id, ai_output)
        return result
    except HTTPException:
        raise
    except Exception as err:
        logger.exception("Free input handling error: %s", err)
        raise HTTPException(status_code=500, detail=str(err))


@router.get("/{session_id}/script")
def get_script(session_id: str):
    return script_builder.load_script(session_id)
