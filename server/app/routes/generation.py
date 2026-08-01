import asyncio
import json
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.auth.deps import require_owner, require_readable

from app.db.queries import characters as character_queries
from app.db.queries import scenes as scene_queries
from app.db.queries import sessions as session_queries
from app.logger import logger
from app.services import animation_generator, asset_manager, session_service, script_builder, tts_generator
from app.services.ai import image_generator, story_generator

router = APIRouter(prefix="/api/v1/sessions", tags=["generation"])

# In-memory progress store (sessionId -> dict)
_progress: dict[str, dict] = {}

# Gemini Image API concurrency — keep aligned with image_generator's
# internal cap. Going above 6 trips rate limits intermittently.
_PIPELINE_WORKERS = 6


def _set_progress(session_id: str, **payload) -> None:
    _progress[session_id] = payload


def _build_continuation_context(session: dict) -> dict | None:
    """If this is a child chapter (parent_session_id set), pull the parent's
    world + chosen ending so the world-build prompt picks up the thread.
    """
    parent_id = session.get("parent_session_id")
    if not parent_id:
        return None
    parent = session_service.get_by_id(parent_id)
    if not parent or not parent.get("chosen_ending_id"):
        return None
    parent_endings = parent.get("endings")
    if isinstance(parent_endings, str):
        try:
            parent_endings = json.loads(parent_endings)
        except Exception:
            parent_endings = []
    if not isinstance(parent_endings, list):
        parent_endings = []
    chosen = next(
        (e for e in parent_endings if e.get("id") == parent["chosen_ending_id"]),
        None,
    )
    if not chosen:
        return None
    # Prior cast (id/name/role) so a continuation chapter REUSES the same
    # character ids instead of minting new ones (the graph plot agent is told
    # to reuse these; the monolith continuation prompt does the same).
    prior_characters = [
        {"id": c.get("id"), "name": c.get("name"), "role": c.get("role")}
        for c in character_queries.get_by_session(parent_id)
    ]
    return {
        "prior_session": parent,
        "prior_world": parent.get("world_lore") or {},
        "prior_ending": chosen,
        "prior_characters": prior_characters,
        "chapter_number": int(session.get("chapter_number") or 2),
    }


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
    art_style = setup["artStyle"]

    _set_progress(session_id, step="story", progress=5,
                  details="Weaving world, characters, spine, and endings...")

    continuation = _build_continuation_context(session)
    story_data = story_generator.generate_world(
        setup, continuation=continuation, session_id=session_id,
    )
    # Record the engine that actually produced this story (graph may fall back
    # to monolith) so runtime free-input routing stays consistent later.
    engine_used = story_data.pop("__engine__", "monolith")
    session_queries.update_engine(session_id, engine_used)
    session_service.save_story_data(session_id, story_data)

    characters = story_data["characters"]
    # Scenes = full catalogue + any ending scenes that only live in endings[].
    scenes = list(story_data.get("scenes") or [])
    scene_ids = {s["id"] for s in scenes}
    for ending in story_data.get("endings") or []:
        fid = ending.get("finalSceneId")
        if fid and fid not in scene_ids:
            scenes.append({
                "id": fid,
                "name": f"{ending.get('name', 'Ending')} scene",
                "description": ending.get("epilogueOutline") or ending.get("summary") or "",
            })
            scene_ids.add(fid)

    _set_progress(
        session_id, step="story_done", progress=12,
        details=f"World \"{story_data['worldLore']['name']}\" — "
                f"{len(characters)} characters, {len(scenes)} scenes, "
                f"{len(story_data.get('storySpine', []))} beats, "
                f"{len(story_data.get('endings', []))} endings",
    )

    # =====================================================================
    # PHASE A: Neutral sprite per character (identity anchor for emotions).
    # Parallel across characters. ~12 s instead of ~48 s for 4 chars.
    # =====================================================================
    neutral_images: dict[str, bytes] = {}
    neutrals_done = {"n": 0}

    def _gen_neutral(c: dict) -> tuple[str, bytes | None]:
        try:
            return c["id"], image_generator.generate_neutral_only(session_id, c, art_style)
        except Exception as err:
            logger.warning("neutral sprite for %s failed: %s", c["id"], err)
            return c["id"], None

    with ThreadPoolExecutor(max_workers=_PIPELINE_WORKERS) as pool:
        for cid, img in pool.map(_gen_neutral, characters):
            if img:
                neutral_images[cid] = img
            neutrals_done["n"] += 1
            _set_progress(
                session_id, step="sprites",
                progress=12 + round(neutrals_done["n"] / max(len(characters), 1) * 8),
                details=f"Drawing anchor portraits ({neutrals_done['n']}/{len(characters)})",
            )

    # =====================================================================
    # PHASE B: All non-neutral emotion sprites AND all scene backgrounds in
    # one shared parallel pool. They share the Gemini Image quota so batching
    # them together prevents idle workers waiting on different stages.
    # =====================================================================
    sprite_tasks: list[tuple[dict, str]] = []
    for c in characters:
        if c["id"] not in neutral_images:
            continue
        for expr in image_generator.EXPRESSIONS:
            if expr == "neutral":
                continue
            sprite_tasks.append((c, expr))

    scene_tasks: list[dict] = list(scenes)
    total_images = len(sprite_tasks) + len(scene_tasks)
    images_done = {"n": 0}

    def _emit_image_progress(step: str, label: str) -> None:
        images_done["n"] += 1
        _set_progress(
            session_id, step=step,
            progress=20 + round(images_done["n"] / max(total_images, 1) * 50),
            details=f"{label} ({images_done['n']}/{total_images})",
        )

    def _do_sprite(task: tuple[dict, str]) -> None:
        c, expr = task
        try:
            image_generator.generate_single_sprite(
                session_id, c, expr, art_style,
                reference_image=neutral_images.get(c["id"]),
            )
        except Exception as err:
            logger.warning("sprite %s/%s failed: %s", c["id"], expr, err)
        _emit_image_progress("sprites", f"Painting {c['name']} — {expr}")

    def _do_scene(scene: dict) -> None:
        try:
            image_generator.generate_background(session_id, scene, art_style)
            scene_queries.mark_image_generated(session_id, scene["id"])
        except Exception as err:
            logger.warning("background %s failed: %s", scene["id"], err)
        _emit_image_progress("backgrounds", f"Painting background — {scene['name']}")

    # Story cover key-visual — one portrait illustration of the main cast in
    # the setting, used on story cards / library. Runs in the shared image pool
    # so it overlaps sprite + background generation. Kept out of the progress
    # count (it's a single bonus image) so the ratio stays clean.
    cover_ref = next(iter(neutral_images.values()), None)

    def _do_cover() -> None:
        try:
            cover_ctx = {
                "title": session.get("title") or story_data.get("worldLore", {}).get("name") or "",
                "genre": setup["genre"],
                "tone": setup["tone"],
                "setting": setup["setting"],
                "protagonist": setup["protagonistName"],
                "characters": [
                    {"name": c["name"], "appearance": c.get("appearance", "")}
                    for c in characters[:3]
                ],
            }
            image_generator.generate_cover(session_id, cover_ctx, art_style, reference_image=cover_ref)
            logger.info("cover generated for session %s", session_id)
        except Exception as err:
            logger.warning("cover generation failed: %s", err)

    with ThreadPoolExecutor(max_workers=_PIPELINE_WORKERS) as pool:
        futures = []
        for task in sprite_tasks:
            futures.append(pool.submit(_do_sprite, task))
        for scene in scene_tasks:
            futures.append(pool.submit(_do_scene, scene))
        futures.append(pool.submit(_do_cover))
        for _ in as_completed(futures):
            pass

    # Mark sprites_generated for any character that got its neutral done.
    for c in characters:
        if c["id"] in neutral_images:
            character_queries.mark_sprites_generated(session_id, c["id"])

    # =====================================================================
    # PHASE C: Overlays (transparent blink/mouth layers) + script binding +
    # beat pre-generation, in parallel.
    #   - Overlays use Gemini Image API.
    #   - Beat pre-gen uses Gemini Flash (text) — different API, no contention.
    # We start the beat pre-gen first so it has the entire overlay phase to
    # complete before Phase D.
    # =====================================================================
    from app.services.ai import dialogue_engine  # local import — heavy module

    pregen_future = None
    # 3 variants per beat × (spine - 2) beats — each beat after the opening
    # gets one variant per choice the player could have taken to get here,
    # so the next scene reacts to the actual choice.
    pregen_total = max(0, (len(story_data.get("storySpine") or []) - 2) * 3)
    if pregen_total > 0:
        pregen_done = {"n": 0}
        def _pregen_progress(idx: int) -> None:
            pregen_done["n"] += 1
            _set_progress(
                session_id, step="pre_render",
                progress=72 + round(pregen_done["n"] / max(pregen_total, 1) * 15),
                details=f"Pre-rendering branch variants "
                        f"({pregen_done['n']}/{pregen_total})",
            )
        # Run pre-gen in its own pool. It returns when all variants are cached.
        pregen_executor = ThreadPoolExecutor(max_workers=6, thread_name_prefix="pregen")
        pregen_future = pregen_executor.submit(
            dialogue_engine.pre_expand_remaining_beats,
            session_id, _pregen_progress,
        )

    # Overlays in parallel — internal parallelism handled inside the function.
    overlay_done = {"n": 0}
    overlay_total = len(characters) * len(animation_generator.OVERLAYS)
    def _overlay_cb(overlay: str, _i: int, _t: int) -> None:
        overlay_done["n"] += 1
        pct = 72 + round(overlay_done["n"] / max(overlay_total, 1) * 8)
        _set_progress(
            session_id, step="animations", progress=pct,
            details=f"Rigging overlays ({overlay_done['n']}/{overlay_total})",
        )

    def _gen_overlays(c: dict) -> None:
        if c["id"] not in neutral_images:
            return
        try:
            animation_generator.generate_for_character(
                session_id, c, art_style,
                neutral_image=neutral_images[c["id"]],
                progress_cb=_overlay_cb,
            )
        except Exception as err:
            logger.warning("overlay gen failed for %s: %s", c["id"], err)

    with ThreadPoolExecutor(max_workers=2) as pool:
        # Overlay generator itself uses 4 internal workers per char — only
        # run 2 chars at a time to stay under the image API ceiling.
        list(pool.map(_gen_overlays, characters))

    # Wait for beat pre-gen to finish (almost certainly already done by now
    # because images are slower than text).
    if pregen_future:
        try:
            pregen_future.result(timeout=180)
        except Exception as err:
            logger.warning("beat pre-gen pool failed: %s", err)
        finally:
            pregen_executor.shutdown(wait=False)

    # =====================================================================
    # PHASE D: Script + voice profiles + ending pre-render.
    # =====================================================================
    _set_progress(session_id, step="script", progress=83, details="Binding the script...")

    script = script_builder.build_initial_script(story_data)
    for label_name, statements in script.items():
        script_builder.save_label(session_id, label_name, statements)

    if tts_generator.is_enabled():
        try:
            n_voices = tts_generator.ensure_all_character_voices(session_id)
            logger.info("voice profiles assigned for %d characters", n_voices)
        except Exception as err:
            logger.warning("voice profile pass failed: %s", err)

    # Pre-render every candidate ending in parallel (4 workers).
    ending_count = len(story_data.get("endings") or [])
    if ending_count:
        ending_done = {"n": 0}
        def _ending_progress(eid: str) -> None:
            ending_done["n"] += 1
            _set_progress(
                session_id, step="endings",
                progress=83 + round(ending_done["n"] / max(ending_count, 1) * 5),
                details=f"Pre-rendering endings ({ending_done['n']}/{ending_count})",
            )
        try:
            dialogue_engine.pre_expand_all_endings(session_id, _ending_progress)
        except Exception as err:
            logger.warning("ending pre-render failed: %s", err)

    # =====================================================================
    # PHASE E: Pre-render ALL audio.
    # Every opening line + every cached beat line + every cached ending line
    # gets synthesized upfront so the player never waits for Mulberry mid-play.
    # tts_generator handles Mulberry's sliding-window rate limit with a
    # 35 s backoff + retry per line.
    # =====================================================================
    if tts_generator.is_enabled():
        _set_progress(session_id, step="voices", progress=88,
                      details="Recording voices (this is the longest phase)...")
        audio_done = {"n": 0, "last": 0}
        def _tts_progress(i: int, total: int, preview: str) -> None:
            audio_done["n"] = i
            pct = 88 + round(i / max(total, 1) * 11)
            if pct != audio_done["last"]:
                audio_done["last"] = pct
                _set_progress(
                    session_id, step="voices", progress=pct,
                    details=f"Recording voices ({i}/{total}): {preview[:30]}",
                )
        try:
            n_audio = tts_generator.generate_for_all_session_lines(
                session_id, progress_cb=_tts_progress,
            )
            logger.info("TTS: wrote %d audio files", n_audio)
        except Exception as err:
            logger.warning("TTS pre-gen pass failed: %s", err)

    session_service.update_status(session_id, "ready")
    _set_progress(session_id, step="done", progress=100,
                  details="Your story is ready.")
    logger.info("Generation complete for session %s", session_id)


async def _pipeline_runner(session_id: str, session: dict) -> None:
    try:
        await asyncio.to_thread(_run_pipeline, session_id, session)
    except Exception as err:
        logger.exception("Generation pipeline failed: %s", err)
        session_service.update_status(session_id, "error")
        _set_progress(session_id, step="error", progress=0, details=str(err))


@router.post("/{session_id}/generate")
async def start_generation(session_id: str, _s: dict = Depends(require_owner)):
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
async def stream_progress(session_id: str, request: Request, _s: dict = Depends(require_readable)):
    async def event_stream() -> AsyncIterator[bytes]:
        session = session_service.get_by_id(session_id)
        if not session or session.get("status") in ("ready", "error"):
            step = "done" if session and session.get("status") == "ready" else "error"
            yield f"data: {json.dumps({'step': step, 'progress': 100 if step == 'done' else 0, 'details': ''})}\n\n".encode("utf-8")
            return

        last_payload: str | None = None
        max_iters = 15 * 60 * 2  # 0.5s per iter
        for _ in range(max_iters):
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
