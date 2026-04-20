import asyncio
import json
import math
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.db.queries import characters as character_queries
from app.db.queries import scenes as scene_queries
from app.logger import logger
from app.services import animation_generator, session_service, script_builder, tts_generator
from app.services.ai import image_generator, story_generator

router = APIRouter(prefix="/api/sessions", tags=["generation"])

# In-memory progress store (sessionId -> dict)
_progress: dict[str, dict] = {}


def _set_progress(session_id: str, **payload) -> None:
    _progress[session_id] = payload


def _run_pipeline(session_id: str, session: dict) -> None:
    setup = {
        "genre": session["setup_genre"],
        "artStyle": session["setup_art_style"],
        "setting": session["setup_setting"],
        "protagonistName": session["setup_protagonist_name"],
        "protagonistPersonality": session["setup_protagonist_personality"],
        "tone": session["setup_tone"],
        "premise": session.get("setup_premise"),
    }

    _set_progress(session_id, step="story", progress=5,
                  details="Generating world, characters, and story...")

    story_data = story_generator.generate_world(setup)
    session_service.save_story_data(session_id, story_data)

    _set_progress(
        session_id, step="story_done", progress=20,
        details=f"World \"{story_data['worldLore']['name']}\" created with "
                f"{len(story_data['characters'])} characters",
    )

    total_characters = len(story_data["characters"])
    sprites_done = {"count": 0}

    for ci, character in enumerate(story_data["characters"]):
        # Only the neutral sprite goes through Gemini now (1 call per character).
        # All 9 other expressions + 30 animation frames are derived via THA3.
        def cb(expr: str, _i: int, _t: int, ci=ci, character=character) -> None:
            sprites_done["count"] += 1
            sprite_progress = 20 + (sprites_done["count"] / total_characters) * 25
            _set_progress(
                session_id, step="sprites",
                progress=round(sprite_progress),
                details=f"Generating {character['name']} portrait "
                        f"({sprites_done['count']}/{total_characters})",
                characterIndex=ci, characterName=character["name"], expression=expr,
            )
        image_generator.generate_character_sprites(session_id, character, setup["artStyle"], cb)
        character_queries.mark_sprites_generated(session_id, character["id"])

    # --- Derive 10 expressions × 4 frames each per character via the puppeteer ---
    if animation_generator.puppeteer_client.is_enabled():
        anim_done = {"count": 0}
        anim_total = total_characters * len(animation_generator.EXPRESSIONS)
        for ci, character in enumerate(story_data["characters"]):
            def anim_cb(expr: str, _i: int, _t: int, character=character) -> None:
                anim_done["count"] += 1
                pct = 45 + (anim_done["count"] / anim_total) * 27
                _set_progress(
                    session_id, step="animations",
                    progress=round(pct),
                    details=f"Deriving {character['name']} - {expr} "
                            f"({anim_done['count']}/{anim_total})",
                )
            try:
                animation_generator.generate_for_character(
                    session_id, character["id"], progress_cb=anim_cb,
                )
            except Exception as err:
                logger.warning("animation gen failed for %s: %s", character["id"], err)
    else:
        logger.warning("PUPPETEER_URL unset; only neutral sprite available, no expressions")

    total_scenes = len(story_data["initialScenes"])
    for si, scene in enumerate(story_data["initialScenes"]):
        _set_progress(
            session_id,
            step="backgrounds",
            progress=math.floor(72 + ((si + 1) / total_scenes) * 20),
            details=f"Generating background: {scene['name']} ({si + 1}/{total_scenes})",
        )
        image_generator.generate_background(session_id, scene, setup["artStyle"])
        scene_queries.mark_image_generated(session_id, scene["id"])

    _set_progress(session_id, step="script", progress=92, details="Building game script...")

    script = script_builder.build_initial_script(story_data)
    for label_name, statements in script.items():
        script_builder.save_label(session_id, label_name, statements)

    # --- TTS pass: pre-render Japanese audio per dialogue line (best-effort) ---
    if tts_generator.tts_client.is_enabled():
        opening = story_data.get("openingScript") or []
        def tts_cb(i: int, total: int, preview: str) -> None:
            pct = 94 + (i / max(total, 1)) * 5
            _set_progress(
                session_id, step="voices", progress=round(pct),
                details=f"Synthesizing voices ({i}/{total}): {preview}",
            )
        try:
            written = tts_generator.generate_for_opening_script(
                session_id, opening, progress_cb=tts_cb,
            )
            logger.info("TTS: wrote %d audio files for session %s", written, session_id)
        except Exception as err:
            logger.warning("TTS pass failed: %s", err)

    session_service.update_status(session_id, "ready")
    _set_progress(session_id, step="done", progress=100,
                  details="Generation complete! Your story is ready.")
    logger.info("Generation complete for session %s", session_id)


async def _pipeline_runner(session_id: str, session: dict) -> None:
    try:
        await asyncio.to_thread(_run_pipeline, session_id, session)
    except Exception as err:
        logger.exception("Generation pipeline failed: %s", err)
        session_service.update_status(session_id, "error")
        _set_progress(session_id, step="error", progress=0, details=str(err))


@router.post("/{session_id}/generate")
async def start_generation(session_id: str):
    session = session_service.get_by_id(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["status"] not in ("created", "error"):
        raise HTTPException(
            status_code=400,
            detail=f"Session status is '{session['status']}', expected 'created'",
        )

    session_service.update_status(session_id, "generating")
    _set_progress(session_id, step="starting", progress=0, details="Starting generation...")

    asyncio.create_task(_pipeline_runner(session_id, session))
    return {"status": "started", "sessionId": session_id}


@router.get("/{session_id}/generate/status")
async def stream_progress(session_id: str, request: Request):
    async def event_stream() -> AsyncIterator[bytes]:
        last_payload: str | None = None
        while True:
            if await request.is_disconnected():
                break
            current = _progress.get(session_id)
            if current is not None:
                payload = json.dumps(current)
                if payload != last_payload:
                    yield f"data: {payload}\n\n".encode("utf-8")
                    last_payload = payload
                if current.get("step") in ("done", "error"):
                    break
            await asyncio.sleep(0.5)

        # Cleanup after a delay so late SSE reads still see terminal state
        async def cleanup() -> None:
            await asyncio.sleep(30)
            _progress.pop(session_id, None)

        asyncio.create_task(cleanup())

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
