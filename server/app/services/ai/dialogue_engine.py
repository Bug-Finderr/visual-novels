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
    build_beat_system_prompt,
    build_ending_full_prompt,
)


# ---------- session context -------------------------------------------------

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

    scenes = scene_queries.get_by_session(session_id)

    return {
        "worldLore": json.loads(session.get("world_lore") or "{}"),
        "characters": chars,
        "scenes": scenes,
        "plotArc": json.loads(session.get("plot_arc") or "{}"),
        "storySpine": json.loads(session.get("story_spine") or "[]"),
        "endings": json.loads(session.get("endings") or "[]"),
        "alignmentState": json.loads(session.get("alignment_state") or "{}"),
        "currentBeatIndex": session.get("current_beat_index") or 0,
        "chosenEndingId": session.get("chosen_ending_id"),
        "currentScene": current_scene,
        "protagonistName": session["setup_protagonist_name"],
        "tone": session["setup_tone"],
        "currentLabel": session.get("current_label"),
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
    session_id: str,
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
    session_queries.update_alignment(session_id, alignment_state)
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


def _expand_full_beat_live(ctx: dict, beat: dict, next_beat: dict | None) -> list[dict]:
    """One Flash 2.5 call that produces the entire beat's statements."""
    system_prompt = build_beat_full_prompt(
        session=ctx, current_beat=beat, next_beat=next_beat,
    )
    text = _call_flash(system_prompt, "[PRE-RENDER THIS BEAT]",
                       history=None, max_output_tokens=1800)
    parsed = _parse_response(text)
    return parsed.get("statements") or []


# ---------- pre-render pass -------------------------------------------------

def pre_expand_beat(session_id: str, beat_index: int) -> bool:
    """Generate + cache one beat's full content. Idempotent: skips if cached."""
    if beat_expansions_queries.get(session_id, beat_index):
        return False
    ctx = _load_session_context(session_id)
    spine = ctx["storySpine"]
    if not spine or beat_index < 0 or beat_index >= len(spine):
        return False
    beat = spine[beat_index]
    next_beat = spine[beat_index + 1] if beat_index + 1 < len(spine) else None
    try:
        statements = _expand_full_beat_live(ctx, beat, next_beat)
    except Exception as exc:
        logger.warning("pre_expand beat %d failed: %s", beat_index, exc)
        return False
    if not statements:
        return False
    beat_expansions_queries.save(session_id, beat_index, statements)
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
    max_workers: int = 4,
) -> int:
    """Pre-render every beat that isn't already cached, in parallel.

    Skips beat 0 (its content lives in the opening script / Start label) and
    the final beat (its content depends on chosen_ending + alignment_state, so
    it's always live). Used at the end of the generation pipeline and during
    `complete_generation` resume.
    """
    ctx = _load_session_context(session_id)
    spine = ctx["storySpine"]
    if not spine or len(spine) < 2:
        return 0

    already = beat_expansions_queries.beat_indices_for_session(session_id)
    targets = [i for i in range(1, len(spine) - 1) if i not in already]
    if not targets:
        return 0

    logger.info("Pre-rendering %d beat(s) for session %s", len(targets), session_id)
    done = 0
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(pre_expand_beat, session_id, i): i for i in targets}
        for fut in as_completed(futures):
            idx = futures[fut]
            try:
                if fut.result():
                    done += 1
            except Exception as exc:
                logger.warning("pre-render beat %d crashed: %s", idx, exc)
            if progress_cb:
                progress_cb(idx)
    logger.info("Pre-rendered %d/%d beats for session %s", done, len(targets), session_id)
    return done


# ---------- main entry ------------------------------------------------------

def process_player_action(session_id: str, action: dict) -> dict:
    """Resolve the player's action to the next chunk of story.

    Fast paths (no LLM call):
      - choice: apply alignment, advance beat index, return cached beat.
      - advance: return current beat's cached content if available.

    Live LLM paths:
      - free-input: small-chunk LLM with the per-turn prompt.
      - final beat: always live (ending depends on alignment_state).
      - cache miss: fall back to live full-beat LLM call (and cache the result).
    """
    ctx = _load_session_context(session_id)
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
    if action_type == "free-input":
        return _free_input_response(session_id, ctx, action, beat_index, alignment_state)

    # ----- Choice: apply alignment first, then move to next beat.
    if action_type == "choice":
        alignment_state = _apply_choice_alignment(
            session_id, alignment_state, endings,
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
            session_queries.set_chosen_ending(session_id, chosen_ending["id"])
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
            session_queries.advance_beat(session_id, target_index)
        _log_history(session_id, ctx, action_type, action, "[FINAL BEAT]")
        return {
            "statements": statements,
            "choices": [],
            "allowFreeInput": False,
            "beatComplete": True,
            "endingFired": True,
        }

    # ----- Cache lookup. Instant page-turn if hit.
    cached = beat_expansions_queries.get(session_id, target_index)
    if cached:
        statements = cached["statements"]
        logger.info("CACHE HIT beat %d (instant)", target_index)
    else:
        # Cache miss — fall back to live full-beat call. Also save so the
        # next replay through this beat is instant.
        logger.info("CACHE MISS beat %d — generating live", target_index)
        next_beat = spine[target_index + 1] if target_index + 1 < len(spine) else None
        try:
            statements = _expand_full_beat_live(ctx, target_beat, next_beat)
            if statements:
                beat_expansions_queries.save(session_id, target_index, statements)
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
        session_queries.advance_beat(session_id, target_index)

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
