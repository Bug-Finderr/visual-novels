"""Beat-driven dialogue engine.

The 10-beat story spine + 5-ending catalogue are generated upfront (see
story_generator). At runtime, every player action expands the CURRENT beat
into a small block of dialogue + 2-3 choices. Each choice carries an
`alignmentTag` and `magnitude` (1-3) that gets added to alignment_state when
the player picks. When a beat is marked complete, we advance. At the final
beat we pick the highest-scoring ending and ask the model to expand it as a
closing sequence (no further choices).
"""
from __future__ import annotations

import json
import re
from typing import Any

from google.genai import types

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from app.db.queries import beat_expansions as beat_expansions_queries
from app.db.queries import characters as character_queries
from app.db.queries import dialogue_history as dialogue_history_queries
from app.db.queries import ending_dialogue as ending_dialogue_queries
from app.db.queries import scenes as scene_queries
from app.db.queries import sessions as session_queries
from app.logger import logger
from app.services.ai.gemini_client import get_client, models
from app.services.ai.prompts.beat_expansion import (
    build_beat_full_prompt,
    build_beat_rewrite_prompt,
    build_beat_system_prompt,
    build_ending_full_prompt,
)
from app.db.queries import playthroughs as pt_queries


# ---------- session context -------------------------------------------------

def _load_session_context(session_id: str, playthrough: dict | None = None) -> dict:
    session = session_queries.get_by_id(session_id)
    if not session:
        raise ValueError(f"Session {session_id} not found")
    pt = playthrough or {}

    chars = []
    for c in character_queries.get_by_session(session_id):
        chars.append({**c, "quirks": json.loads(c.get("quirks") or "[]")})

    scene_id = pt.get("current_scene_id") or session.get("current_scene_id")
    current_scene = scene_queries.get_by_id(session_id, scene_id) if scene_id else None

    scenes = scene_queries.get_by_session(session_id)

    return {
        "worldLore": json.loads(session.get("world_lore") or "{}"),
        "characters": chars,
        "scenes": scenes,
        "plotArc": json.loads(session.get("plot_arc") or "{}"),
        "storySpine": json.loads(session.get("story_spine") or "[]"),
        "endings": json.loads(session.get("endings") or "[]"),
        "alignmentState": json.loads(pt.get("alignment_state") or session.get("alignment_state") or "{}"),
        "currentBeatIndex": pt.get("current_beat_index") if pt.get("current_beat_index") is not None else (session.get("current_beat_index") or 0),
        "chosenEndingId": pt.get("chosen_ending_id") or session.get("chosen_ending_id"),
        "currentScene": current_scene,
        "protagonistName": session["setup_protagonist_name"],
        "tone": session["setup_tone"],
        "currentLabel": pt.get("current_label") or session.get("current_label"),
        "playthroughId": pt.get("id"),
        # Engine that generated this story — drives free-input handling so it
        # stays consistent regardless of the live STORYGEN_ENGINE flag.
        "storygenEngine": session.get("storygen_engine") or "monolith",
    }


def _build_conversation_history(session_id: str) -> list[types.Content]:
    # Trim to the last 12 turns — runtime expansion only needs immediate
    # context (the last few player actions + the last model output). Each
    # extra historic turn adds ~400-800 tokens of input which directly
    # increases Flash 2.5's processing time. The spine + beat outline in
    # the system prompt carry the long-arc context.
    recent = dialogue_history_queries.get_recent(session_id, 12)
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


# ---------- alignment / ending routing -------------------------------------

def _pick_chosen_ending(endings: list[dict], alignment_state: dict) -> dict | None:
    """Pick the ending with the highest alignment score; tie-break by spine order.

    alignment_state is keyed by ending **id** (set up that way in
    sessions.save_spine and incremented in _apply_choice_alignment). Reading
    by alignmentTag instead — as this code used to — always returned 0 and
    therefore always picked the first ending in the list. The state is keyed
    by id, so we look up by id.
    """
    if not endings:
        return None
    best: dict | None = None
    best_score = -1
    for e in endings:
        score = alignment_state.get(e.get("id"), 0)
        if score > best_score:
            best, best_score = e, score
    return best


def _apply_choice_alignment(
    playthrough_id: str,
    alignment_state: dict,
    endings: list[dict],
    chosen_choice: dict | None,
) -> dict:
    """Add the chosen choice's magnitude to its alignmentTag's score and persist."""
    if not chosen_choice:
        return alignment_state
    tag = chosen_choice.get("alignmentTag")
    if not tag:
        return alignment_state
    magnitude = int(chosen_choice.get("magnitude") or 1)
    magnitude = max(1, min(3, magnitude))
    # Map tag → ending_id (alignment_state is keyed by ending_id so we always
    # converge on a real ending even if the AI invents a new tag).
    target_id = next((e["id"] for e in endings if e.get("alignmentTag") == tag), None)
    if not target_id:
        return alignment_state
    alignment_state = dict(alignment_state)
    alignment_state[target_id] = alignment_state.get(target_id, 0) + magnitude
    pt_queries.update_alignment(playthrough_id, alignment_state)
    return alignment_state


# ---------- LLM helpers -----------------------------------------------------

def _call_flash(system_prompt: str, user_message: str,
                history: list[types.Content] | None = None,
                max_output_tokens: int = 1500) -> str:
    history = history or []
    messages = history + [
        types.Content(role="user", parts=[types.Part.from_text(text=user_message)])
    ]
    client = get_client()
    response = client.models.generate_content(
        model=models.dialogue_flash,
        contents=messages,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.8,
            max_output_tokens=max_output_tokens,
            response_mime_type="application/json",
            # Skip Gemini 2.5's internal revision pass — first-token latency
            # drops noticeably and our output schema is constrained anyway.
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    return response.candidates[0].content.parts[0].text


def _expand_full_beat_live(
    ctx: dict,
    beat: dict,
    next_beat: dict | None,
    *,
    previous_choice_text: str | None = None,
    previous_choice_tag: str | None = None,
) -> list[dict]:
    """One Flash 2.5 call that produces the entire beat's statements.

    Pass the previous beat's chosen choice so the first 1-2 statements of
    this beat react to it — the variant won't read as 'any random next page'.
    """
    system_prompt = build_beat_full_prompt(
        session=ctx, current_beat=beat, next_beat=next_beat,
        previous_choice_text=previous_choice_text,
        previous_choice_tag=previous_choice_tag,
    )
    text = _call_flash(system_prompt, "[PRE-RENDER THIS BEAT]",
                       history=None, max_output_tokens=1800)
    parsed = _parse_response(text)
    return parsed.get("statements") or []


# ---------- pre-render pass -------------------------------------------------

def pre_expand_beat(
    session_id: str,
    beat_index: int,
    *,
    previous_choice_text: str | None = None,
    previous_choice_tag: str | None = None,
) -> bool:
    """Generate + cache one beat variant. Idempotent: skips if the
    (beat_index, source_choice_tag) variant is already cached.
    """
    tag = previous_choice_tag or ""
    if beat_expansions_queries.get(session_id, beat_index, tag):
        return False
    ctx = _load_session_context(session_id)
    spine = ctx["storySpine"]
    if not spine or beat_index < 0 or beat_index >= len(spine):
        return False
    beat = spine[beat_index]
    next_beat = spine[beat_index + 1] if beat_index + 1 < len(spine) else None
    try:
        statements = _expand_full_beat_live(
            ctx, beat, next_beat,
            previous_choice_text=previous_choice_text,
            previous_choice_tag=previous_choice_tag,
        )
    except Exception as exc:
        logger.warning("pre_expand beat %d (tag=%s) failed: %s",
                       beat_index, tag, exc)
        return False
    if not statements:
        return False
    beat_expansions_queries.save(session_id, beat_index, tag, statements)
    return True


def pre_expand_ending(session_id: str, ending: dict) -> bool:
    """Generate + cache one ending's epilogue dialogue. Idempotent."""
    if ending_dialogue_queries.get(session_id, ending["id"]):
        return False
    ctx = _load_session_context(session_id)
    system_prompt = build_ending_full_prompt(session=ctx, ending=ending)
    try:
        text = _call_flash(
            system_prompt, "[PRE-RENDER THIS ENDING]",
            history=None, max_output_tokens=1500,
        )
        parsed = _parse_response(text)
        statements = parsed.get("statements") or []
    except Exception as exc:
        logger.warning("pre_expand ending %s failed: %s", ending.get("id"), exc)
        return False
    if not statements:
        return False
    ending_dialogue_queries.save(session_id, ending["id"], statements)
    return True


def pre_expand_all_endings(
    session_id: str,
    progress_cb: Callable[[str], None] | None = None,
    max_workers: int = 4,
) -> int:
    """Bake every candidate ending's epilogue dialogue into the cache so the
    final-beat runtime path becomes a DB lookup."""
    ctx = _load_session_context(session_id)
    endings = ctx.get("endings") or []
    if not endings:
        return 0
    already = ending_dialogue_queries.ending_ids_for_session(session_id)
    targets = [e for e in endings if e.get("id") and e["id"] not in already]
    if not targets:
        return 0

    logger.info("Pre-rendering %d ending(s) for session %s", len(targets), session_id)
    done = 0
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(pre_expand_ending, session_id, e): e for e in targets}
        for fut in as_completed(futures):
            ending = futures[fut]
            try:
                if fut.result():
                    done += 1
            except Exception as exc:
                logger.warning("pre-render ending %s crashed: %s", ending.get("id"), exc)
            if progress_cb:
                progress_cb(ending.get("id", "?"))
    return done


def pre_expand_remaining_beats(
    session_id: str,
    progress_cb: Callable[[int], None] | None = None,
    max_workers: int = 6,
) -> int:
    """Pre-render every beat VARIANT not already cached, in parallel.

    For each beat N in [1, len(spine)-1), enumerate spine[N-1].choices and
    pre-generate a variant per choice tag so beat N reacts to whichever of
    the 3 choices the player picked at beat N-1.

    Total target count is up to 3 × (len(spine) - 2) = 24 for a 10-beat
    spine. Skips beat 0 (its content is the opening / Start label) and the
    final beat (which uses ending_dialogue, keyed by chosen_ending).
    """
    ctx = _load_session_context(session_id)
    spine = ctx["storySpine"]
    if not spine or len(spine) < 2:
        return 0

    targets: list[tuple[int, str, str]] = []  # (beat_index, prev_tag, prev_text)
    for beat_idx in range(1, len(spine) - 1):
        prev_beat = spine[beat_idx - 1]
        prev_choices = prev_beat.get("choices") or []
        if not prev_choices:
            # Beat with no source choices (only beat 1 if the opening had
            # no spine choices — rare). Render the default '' variant once.
            targets.append((beat_idx, "", ""))
            continue
        for ch in prev_choices[:3]:
            tag = (ch.get("alignmentTag") or "").strip()
            text = (ch.get("text") or "").strip()
            if not tag:
                continue
            targets.append((beat_idx, tag, text))

    already = beat_expansions_queries.variants_for_session(session_id)
    targets = [t for t in targets if (t[0], t[1]) not in already]
    if not targets:
        return 0

    logger.info("Pre-rendering %d beat variant(s) for session %s",
                len(targets), session_id)
    done = 0
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(
                pre_expand_beat, session_id, beat_idx,
                previous_choice_text=text or None,
                previous_choice_tag=tag or None,
            ): (beat_idx, tag)
            for beat_idx, tag, text in targets
        }
        for fut in as_completed(futures):
            beat_idx, tag = futures[fut]
            try:
                if fut.result():
                    done += 1
            except Exception as exc:
                logger.warning("pre-render beat %d/%s crashed: %s",
                               beat_idx, tag, exc)
            if progress_cb:
                progress_cb(beat_idx)
    logger.info("Pre-rendered %d/%d variants for session %s",
                done, len(targets), session_id)
    return done


# ---------- main entry ------------------------------------------------------

def process_player_action(session_id: str, action: dict, playthrough: dict) -> dict:
    """Resolve the player's action to the next chunk of story.

    Fast paths (no LLM call):
      - choice: apply alignment, advance beat index, return cached beat.
      - advance: return current beat's cached content if available.

    Live LLM paths:
      - free-input: small-chunk LLM with the per-turn prompt.
      - final beat: always live (ending depends on alignment_state).
      - cache miss: fall back to live full-beat LLM call (and cache the result).
    """
    ctx = _load_session_context(session_id, playthrough)
    playthrough_id = playthrough["id"]
    spine: list[dict] = ctx["storySpine"]
    endings: list[dict] = ctx["endings"]
    alignment_state: dict = ctx["alignmentState"] or {}

    if not spine or not endings:
        raise ValueError(
            "Session is missing a story spine / endings — regenerate from setup."
        )

    beat_index = int(ctx["currentBeatIndex"] or 0)
    beat_index = max(0, min(beat_index, len(spine) - 1))

    action_type = action.get("type")

    # ----- Free-input: always live (custom user text needs a real response).
    # With the multi-agent engine, route custom text through the Beat-Rewrite
    # Agent, which folds it into the current beat and steers back to the
    # pre-defined choices without changing the spine/endings.
    if action_type == "free-input":
        if ctx.get("storygenEngine") == "graph":
            return _beat_rewrite_response(session_id, ctx, action, beat_index, alignment_state)
        return _free_input_response(session_id, ctx, action, beat_index, alignment_state)

    # ----- Choice: apply alignment first, then move to next beat.
    if action_type == "choice":
        alignment_state = _apply_choice_alignment(
            playthrough_id, alignment_state, endings,
            {
                "alignmentTag": action.get("alignmentTag"),
                "magnitude": action.get("magnitude"),
            },
        )
        target_index = min(beat_index + 1, len(spine) - 1)
    else:  # advance
        target_index = beat_index

    target_beat = spine[target_index]
    is_final = target_index == len(spine) - 1

    # ----- Final beat: serve from pre-cached ending dialogue. Falls back to
    # a live LLM call only if the cache is missing for the chosen ending.
    if is_final:
        chosen_ending = _pick_chosen_ending(endings, alignment_state)
        if chosen_ending:
            pt_queries.set_chosen_ending(playthrough_id, chosen_ending["id"])
        statements: list[dict] = []
        if chosen_ending:
            cached_ending = ending_dialogue_queries.get(session_id, chosen_ending["id"])
            if cached_ending:
                statements = cached_ending["statements"]
                logger.info("ENDING CACHE HIT (%s)", chosen_ending["id"])
            else:
                logger.info("ENDING CACHE MISS (%s) — generating live", chosen_ending["id"])
                try:
                    statements = _expand_ending_live(ctx, chosen_ending)
                    if statements:
                        ending_dialogue_queries.save(session_id, chosen_ending["id"], statements)
                except Exception as exc:
                    logger.warning("live ending gen failed: %s", exc)
                    statements = _live_final_beat(ctx, target_beat, chosen_ending)
        else:
            statements = _live_final_beat(ctx, target_beat, None)
        if chosen_ending and chosen_ending.get("finalSceneId"):
            statements = _ensure_scene_change(statements, chosen_ending["finalSceneId"])
        if target_index != beat_index:
            pt_queries.advance_beat(playthrough_id, target_index)
        _log_history(session_id, ctx, action_type, action, "[FINAL BEAT]")
        return {
            "statements": statements,
            "choices": [],
            "allowFreeInput": False,
            "beatComplete": True,
            "endingFired": True,
        }

    # ----- Cache lookup, keyed by the choice the player just took.
    # Each beat has up to 3 variants (one per source choice tag) so the
    # next scene reacts to which choice was picked.
    source_tag = (action.get("alignmentTag") or "").strip() if action_type == "choice" else ""
    source_text = (action.get("text") or "").strip() if action_type == "choice" else ""

    cached = beat_expansions_queries.get(session_id, target_index, source_tag)
    if cached:
        statements = cached["statements"]
        logger.info("CACHE HIT beat %d (tag=%s)", target_index, source_tag or "<none>")
    else:
        # Specific variant missing. Try any pre-rendered variant for this
        # beat so we don't block the player on a live call.
        fallback = beat_expansions_queries.get_any(session_id, target_index)
        if fallback:
            statements = fallback["statements"]
            logger.info("CACHE PARTIAL beat %d (tag=%s not pre-rendered; "
                        "served an alternate variant)", target_index, source_tag)
        else:
            logger.info("CACHE MISS beat %d (tag=%s) — generating live",
                        target_index, source_tag or "<none>")
            next_beat = spine[target_index + 1] if target_index + 1 < len(spine) else None
            try:
                statements = _expand_full_beat_live(
                    ctx, target_beat, next_beat,
                    previous_choice_text=source_text or None,
                    previous_choice_tag=source_tag or None,
                )
                if statements:
                    beat_expansions_queries.save(
                        session_id, target_index, source_tag, statements,
                    )
            except Exception as exc:
                logger.warning("live full-beat failed for %d: %s — empty result",
                               target_index, exc)
                statements = []

    spine_choices = target_beat.get("choices") or _fallback_choices(endings)
    if target_beat.get("sceneId"):
        statements = _ensure_scene_change(statements, target_beat["sceneId"])
    # Clear lingering characters from prior beats — only those NOT named in
    # this beat's spine cast survive. Safe to over-hide; client no-ops it.
    all_char_ids = [c["id"] for c in (ctx.get("characters") or [])]
    statements = _ensure_cast(statements, target_beat.get("castIds"), all_char_ids)
    if target_index != beat_index:
        pt_queries.advance_beat(playthrough_id, target_index)

    _log_history(session_id, ctx, action_type, action,
                 f"[BEAT {target_index} → {len(statements)} statements]")

    return {
        "statements": statements,
        "choices": spine_choices,
        "allowFreeInput": True,
        "beatComplete": True,
        "endingFired": False,
    }


def _ensure_cast(
    statements: list[dict],
    beat_cast_ids: list[str] | None,
    all_character_ids: list[str],
) -> list[dict]:
    """Hide every character NOT in this beat's cast at the start of the beat.

    Why: the cached LLM output usually opens by show_character'ing the active
    cast, but it rarely emits hide_character for the previous beat's cast
    that should be leaving the scene. That leaves stale characters lingering
    on stage across beats. Preemptive hides are safe because the client's
    `_hideCharacter` is a no-op for characters that aren't currently mounted.

    Inserted AFTER any leading scene_change so the scene transitions first,
    then the cast is cleared, then the LLM's content shows the new cast.
    """
    cast = set(beat_cast_ids or [])
    if not cast or not all_character_ids:
        return statements
    to_hide = [cid for cid in all_character_ids if cid not in cast]
    if not to_hide:
        return statements
    hide_stmts = [
        {"type": "hide_character", "characterId": cid} for cid in to_hide
    ]
    insert_at = 0
    if (statements and isinstance(statements[0], dict)
            and statements[0].get("type") == "scene_change"):
        insert_at = 1
    return statements[:insert_at] + hide_stmts + statements[insert_at:]


def _ensure_scene_change(statements: list[dict], canonical_scene_id: str) -> list[dict]:
    """Guarantee the first statement is a scene_change to a known-good scene.

    Why: the cached statements were produced by Flash 2.5, which sometimes
    omits the opening scene_change or invents a scene id that doesn't
    exist in the asset folder. Either case leaves the client showing the
    underlying black .game-view because the bg-image URL silently 404s.
    The spine's beat sceneId (or the ending's finalSceneId) was generated
    by the pipeline and is guaranteed to have a backgrounds/<id>.png file.
    """
    if not canonical_scene_id:
        return statements
    leading = statements[0] if statements else None
    if isinstance(leading, dict) and leading.get("type") == "scene_change":
        # Trust the LLM's choice ONLY if it points at the canonical scene;
        # otherwise replace so we never serve a 404.
        if leading.get("sceneId") == canonical_scene_id:
            return statements
        return [{"type": "scene_change", "sceneId": canonical_scene_id}, *statements[1:]]
    return [{"type": "scene_change", "sceneId": canonical_scene_id}, *statements]


def _expand_ending_live(ctx: dict, ending: dict) -> list[dict]:
    """Single Flash 2.5 call producing the chosen ending's epilogue."""
    system_prompt = build_ending_full_prompt(session=ctx, ending=ending)
    text = _call_flash(
        system_prompt, "[PLAYER REACHES THIS ENDING]",
        history=None, max_output_tokens=1500,
    )
    parsed = _parse_response(text)
    return parsed.get("statements") or []


def _live_final_beat(ctx: dict, beat: dict, chosen_ending: dict | None) -> list[dict]:
    """One LLM call for the final beat — must reference chosen_ending."""
    if chosen_ending is None:
        # Edge case: no alignment was ever incremented. Just use the first.
        endings = ctx.get("endings") or []
        chosen_ending = endings[0] if endings else None
    system_prompt = build_beat_system_prompt(
        session=ctx, current_beat=beat, next_beat=None,
        is_final_beat=True, chosen_ending=chosen_ending,
        alignment_state=ctx.get("alignmentState") or {},
    )
    text = _call_flash(system_prompt, "[PLAYER REACHES THE FINAL BEAT]",
                       history=None, max_output_tokens=1800)
    parsed = _parse_response(text)
    return parsed.get("statements") or []


def _free_input_response(
    session_id: str,
    ctx: dict,
    action: dict,
    beat_index: int,
    alignment_state: dict,
) -> dict:
    """Small-chunk live response to a player's typed text. Stays on the
    current beat and re-surfaces the same set of choices when done.
    """
    spine = ctx["storySpine"]
    endings = ctx["endings"]
    current_beat = spine[beat_index]
    next_beat = spine[beat_index + 1] if beat_index + 1 < len(spine) else None
    is_final = beat_index == len(spine) - 1

    system_prompt = build_beat_system_prompt(
        session=ctx, current_beat=current_beat, next_beat=next_beat,
        is_final_beat=is_final,
        chosen_ending=_pick_chosen_ending(endings, alignment_state) if is_final else None,
        alignment_state=alignment_state,
    )
    history = _build_conversation_history(session_id)
    user_message = f"[PLAYER SAYS: \"{action.get('text', '')}\"]"
    text = _call_flash(system_prompt, user_message, history=history, max_output_tokens=700)
    parsed = _parse_response(text)

    dialogue_history_queries.insert(session_id, "user", user_message, ctx.get("currentLabel"))
    dialogue_history_queries.insert(session_id, "model", text, ctx.get("currentLabel"))

    statements = parsed.get("statements") or []
    return {
        "statements": statements,
        # Re-surface the current beat's pre-baked choices so the player can
        # still progress after their side-conversation.
        "choices": current_beat.get("choices") or _fallback_choices(endings),
        "allowFreeInput": True,
        "beatComplete": False,
        "endingFired": False,
    }


def _beat_rewrite_response(
    session_id: str,
    ctx: dict,
    action: dict,
    beat_index: int,
    alignment_state: dict,
) -> dict:
    """Beat-Rewrite Agent (multi-agent engine): fold the player's custom text
    into the CURRENT beat in-character, then re-surface the same pre-defined
    choices. Never changes the spine, alignment, scene, or endings — it only
    keeps the player feeling heard while steering them back onto the rails.
    """
    spine = ctx["storySpine"]
    endings = ctx["endings"]
    # On the final beat there are no onward choices to steer toward; defer to
    # the shared free-input handler so both engines behave identically there.
    if beat_index == len(spine) - 1:
        return _free_input_response(session_id, ctx, action, beat_index, alignment_state)

    current_beat = spine[beat_index]
    choices = current_beat.get("choices") or _fallback_choices(endings)

    system_prompt = build_beat_rewrite_prompt(
        session=ctx, current_beat=current_beat, choices=choices, endings=endings,
    )
    history = _build_conversation_history(session_id)
    user_message = f"[PLAYER WRITES: \"{action.get('text', '')}\"]"
    try:
        text = _call_flash(system_prompt, user_message, history=history, max_output_tokens=650)
        parsed = _parse_response(text)
        statements = parsed.get("statements") or []
    except Exception as exc:
        logger.warning("beat-rewrite failed: %s — empty result", exc)
        text = "{}"
        statements = []

    dialogue_history_queries.insert(session_id, "user", user_message, ctx.get("currentLabel"))
    dialogue_history_queries.insert(session_id, "model", text, ctx.get("currentLabel"))

    return {
        "statements": statements,
        "choices": choices,
        "allowFreeInput": True,
        "beatComplete": False,
        "endingFired": False,
    }


def _log_history(
    session_id: str, ctx: dict, action_type: str, action: dict, marker: str,
) -> None:
    """Compact dialogue_history entry for cache-hit paths — keeps the
    free-input prompt's history coherent without storing the full statements
    (those live in beat_expansions / script_labels)."""
    if action_type == "choice":
        msg = (
            f"[PLAYER CHOSE: \"{action.get('text','')}\"] "
            f"(tag: {action.get('alignmentTag','')}, "
            f"magnitude: {action.get('magnitude','')}) {marker}"
        )
    elif action_type == "advance":
        msg = f"[PLAYER CONTINUES THE STORY] {marker}"
    else:
        msg = f"[ACTION: {action_type}] {marker}"
    dialogue_history_queries.insert(session_id, "user", msg, ctx.get("currentLabel"))


_FALLBACK_TEMPLATES = [
    ("Press on cautiously.",     "stay safe and weigh the risks"),
    ("Take a bold step forward.", "act decisively and accept the cost"),
    ("Listen and observe.",       "gather information before acting"),
]


def _fallback_choices(endings: list[dict]) -> list[dict]:
    if not endings:
        return []
    tags = [e.get("alignmentTag") for e in endings if e.get("alignmentTag")]
    if not tags:
        return []
    out = []
    for i, (text, consequence) in enumerate(_FALLBACK_TEMPLATES):
        tag = tags[i % len(tags)]
        out.append({
            "text": text,
            "consequence": consequence,
            "alignmentTag": tag,
            "magnitude": 1,
        })
    return out
