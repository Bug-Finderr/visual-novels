"""Beat-expansion system prompts.

Two variants:
  - `build_beat_system_prompt`  — short per-turn variant (2-4 statements).
    Used by free-input and as a fallback when the cache misses.
  - `build_beat_full_prompt`    — full-beat variant (6-12 statements). Used
    by the pre-render pass to bake an entire beat's content into the cache
    so runtime page-advances are instant.

In both, the cast and scene catalogue are LOCKED — only show/hide existing
characters. Choices are pre-baked in the spine and never generated here.
"""
from __future__ import annotations


def build_beat_system_prompt(
    *,
    session: dict,
    current_beat: dict,
    next_beat: dict | None,
    is_final_beat: bool,
    chosen_ending: dict | None,
    alignment_state: dict,
) -> str:
    characters = session.get("characters") or []
    current_scene = session.get("currentScene")
    protagonist_name = session["protagonistName"]
    tone = session["tone"]

    # Only include cast actually expected to appear in this beat — drops
    # several hundred tokens off the system prompt vs. dumping every char.
    in_beat = set(current_beat.get("castIds") or [])
    beat_chars = [c for c in characters if c["id"] in in_beat] or characters
    character_profiles = "\n".join(
        f"- {c['id']} ({c['name']}): {(c.get('personality') or '')[:120]}. "
        f"speech: {(c.get('speech_style') or c.get('speechStyle') or '')[:60]}"
        for c in beat_chars
    )

    scene_text = (
        f"{current_scene['name']} — {(current_scene.get('description') or '')[:140]}"
        if current_scene
        else current_beat.get("sceneId", "")
    )

    if is_final_beat and chosen_ending:
        epilogue = chosen_ending.get("epilogueOutline") or chosen_ending.get("summary", "")
        ending_directive = f"""

FINAL BEAT — EXPAND THE ENDING:
Active ending: {chosen_ending['id']} — {chosen_ending.get('name','')} (tone: {chosen_ending.get('tone','')})
Outline: {epilogue}

Build to and through this epilogue. Set "beatComplete": true and
"endingFired": true. The last statement is the closing narration line."""
    else:
        ending_directive = (
            f"\n\nNext beat after this: "
            f"{next_beat.get('title','')} — {next_beat.get('outline','')}"
            if next_beat else ""
        )

    return f"""You write the next short segment of an interactive visual novel.
Everything is pre-architected — characters, scenes, and the post-beat choices
already exist; your job is JUST the next chunk of dialogue and which sprites
to show.

TONE: {tone}
PROTAGONIST (player-controlled — never speak as them): {protagonist_name}
SCENE: {scene_text}

CHARACTERS IN THIS BEAT:
{character_profiles}

CURRENT BEAT ({current_beat.get('index', 0) + 1}/10): {current_beat.get('title','')}
goal: {current_beat.get('narrativeGoal','')}
outline: {current_beat.get('outline','')}{ending_directive}

YOUR TASK:
Respond to the player's last action with the NEXT 2-4 statements. Output strict JSON:

{{
  "statements": [
    {{ "type": "narration", "text": "..." }},
    {{ "type": "dialogue", "speaker": "<character_id>", "expression": "happy|sad|angry|surprised|neutral|embarrassed|thinking|scared|determined|smug", "text": "..." }},
    {{ "type": "show_character", "characterId": "<existing_id>", "position": "left|center|right" }},
    {{ "type": "hide_character", "characterId": "<existing_id>" }}
  ],
  "beatComplete": false,
  "endingFired": false
}}

RULES:
- 2-4 statements per response. Keep it short — the player advances frequently.
- DO NOT include a `choices` array; the runtime appends the beat's pre-baked
  choices once you mark beatComplete: true.
- DO NOT introduce new characters or new scenes. Use only the cast above.
- Set "beatComplete": true when this beat's narrativeGoal is fulfilled.
- Stay in character. Never speak as the protagonist.
- Expressions are EXACTLY one of: happy, sad, angry, surprised, neutral,
  embarrassed, thinking, scared, determined, smug.
- Plain ASCII English."""


def build_beat_full_prompt(
    *,
    session: dict,
    current_beat: dict,
    next_beat: dict | None,
    previous_choice_text: str | None = None,
    previous_choice_tag: str | None = None,
) -> str:
    """Pre-render variant: produces the entire beat in one response (6-12
    statements) so it can be cached and replayed at runtime instantly.

    `previous_choice_text` / `previous_choice_tag` describe the choice the
    player took at the END of the previous beat. The first 1-2 statements
    of this beat must REACT to that choice so the player feels their
    decision shaped the next scene. Pass None for the opening / no source.
    """
    characters = session.get("characters") or []
    current_scene = session.get("currentScene")
    protagonist_name = session["protagonistName"]
    tone = session["tone"]

    in_beat = set(current_beat.get("castIds") or [])
    beat_chars = [c for c in characters if c["id"] in in_beat] or characters
    character_profiles = "\n".join(
        f"- {c['id']} ({c['name']}): {(c.get('personality') or '')[:160]}. "
        f"speech: {(c.get('speech_style') or c.get('speechStyle') or '')[:80]}"
        for c in beat_chars
    )

    scene_text = (
        f"{current_scene['name']} — {(current_scene.get('description') or '')[:180]}"
        if current_scene
        else current_beat.get("sceneId", "")
    )

    next_block = (
        f"\nNEXT BEAT (after this one): {next_beat.get('title','')} — {next_beat.get('outline','')}"
        if next_beat else ""
    )

    prev_choice_block = ""
    if previous_choice_text:
        prev_choice_block = f"""

PLAYER JUST CHOSE (in the previous beat): "{previous_choice_text.strip()}"
  alignment tag: {previous_choice_tag or '(unknown)'}

The FIRST 1–2 statements of this beat MUST openly react to that choice —
characters mention it, narration calls back to it, the world responds.
The rest of the beat follows the outline below. Do not contradict the
choice or pretend it didn't happen."""

    return f"""You write the complete dialogue + sprite directives for ONE beat of an
interactive visual novel, in a single response. Characters and scenes are
locked — they were generated upfront and you must only reference existing ids.
Choices are NOT generated here (they come from the spine).

TONE: {tone}
PROTAGONIST (player-controlled — never speak as them): {protagonist_name}
SCENE: {scene_text}

CHARACTERS IN THIS BEAT:
{character_profiles}

THIS BEAT ({current_beat.get('index', 0) + 1}/10): {current_beat.get('title','')}
goal:    {current_beat.get('narrativeGoal','')}
outline: {current_beat.get('outline','')}{next_block}{prev_choice_block}

OUTPUT — strict JSON:
{{
  "statements": [
    {{ "type": "scene_change", "sceneId": "<existing_scene_id>" }},
    {{ "type": "show_character", "characterId": "<existing_id>", "position": "left|center|right" }},
    {{ "type": "narration", "text": "..." }},
    {{ "type": "dialogue", "speaker": "<character_id>", "expression": "happy|sad|angry|surprised|neutral|embarrassed|thinking|scared|determined|smug", "text": "..." }},
    {{ "type": "hide_character", "characterId": "<existing_id>" }}
  ],
  "beatComplete": true
}}

RULES:
- 6-12 statements TOTAL covering the entire beat — fulfill the narrativeGoal.
- Open with show_character / scene_change directives as needed so the stage
  is set, then play out the dialogue and narration.
- Do NOT include a `choices` array — the runtime appends pre-baked choices.
- Do NOT introduce new characters or scenes — use only the ids above.
- Always set `beatComplete: true` (this IS the whole beat).
- Stay in character. Never speak as the protagonist.
- Expressions are EXACTLY one of: happy, sad, angry, surprised, neutral,
  embarrassed, thinking, scared, determined, smug.
- Plain ASCII English."""


def build_ending_full_prompt(*, session: dict, ending: dict) -> str:
    """Pre-render variant for a specific ending's epilogue.

    Used at generation time to bake every candidate ending's dialogue into
    the cache so the final-beat runtime path is a DB lookup (no live LLM).
    """
    characters = session.get("characters") or []
    protagonist_name = session["protagonistName"]
    tone = session["tone"]
    scenes_by_id = {s["id"]: s for s in (session.get("scenes") or [])}
    final_scene = scenes_by_id.get(ending.get("finalSceneId"))

    scene_text = (
        f"{final_scene['name']} — {(final_scene.get('description') or '')[:180]}"
        if final_scene
        else ending.get("finalSceneId", "")
    )

    character_profiles = "\n".join(
        f"- {c['id']} ({c['name']}): {(c.get('personality') or '')[:160]}. "
        f"speech: {(c.get('speech_style') or c.get('speechStyle') or '')[:80]}"
        for c in characters
    )

    return f"""You write the complete epilogue dialogue for ONE ending of an
interactive visual novel, in a single response. Characters and scenes are
locked — only reference existing ids.

TONE: {tone}  (this ending's tone: {ending.get('tone','')})
PROTAGONIST (player-controlled — never speak as them): {protagonist_name}
ENDING SCENE: {scene_text}

CHARACTERS (use only those that fit the ending's tone):
{character_profiles}

ENDING: {ending.get('name','')} (id: {ending.get('id','')})
summary:  {ending.get('summary','')}
epilogue: {ending.get('epilogueOutline','')}

OUTPUT — strict JSON:
{{
  "statements": [
    {{ "type": "scene_change", "sceneId": "<finalSceneId>" }},
    {{ "type": "show_character", "characterId": "<existing_id>", "position": "left|center|right" }},
    {{ "type": "narration", "text": "..." }},
    {{ "type": "dialogue", "speaker": "<character_id>", "expression": "happy|sad|angry|surprised|neutral|embarrassed|thinking|scared|determined|smug", "text": "..." }},
    {{ "type": "hide_character", "characterId": "<existing_id>" }}
  ],
  "endingFired": true
}}

RULES:
- 6-10 statements total — open with a scene_change to the finalSceneId,
  show the surviving cast, then play the closing dialogue + narration.
- The FINAL statement must be a closing narration line that gives the
  reader a clear "the story has ended" feeling — match the ending's tone.
- Do NOT include a `choices` array — there are no choices after an ending.
- Do NOT introduce new characters or scenes.
- Plain ASCII English.
- Always set `endingFired: true`."""


def build_beat_rewrite_prompt(
    *,
    session: dict,
    current_beat: dict,
    choices: list[dict],
    endings: list[dict],
) -> str:
    """Beat-Rewrite Agent: the player typed CUSTOM text instead of picking one
    of the 3 choices. Weave their input into the CURRENT beat without changing
    the overall story — same characters, same scene, same spine, same set of
    endings — then steer them back toward the pre-defined choices so the
    pre-architected branches and endings still drive the arc.
    """
    characters = session.get("characters") or []
    current_scene = session.get("currentScene")
    protagonist_name = session["protagonistName"]
    tone = session["tone"]

    in_beat = set(current_beat.get("castIds") or [])
    beat_chars = [c for c in characters if c["id"] in in_beat] or characters
    character_profiles = "\n".join(
        f"- {c['id']} ({c['name']}): {(c.get('personality') or '')[:120]}. "
        f"speech: {(c.get('speech_style') or c.get('speechStyle') or '')[:60]}"
        for c in beat_chars
    )

    scene_text = (
        f"{current_scene['name']} — {(current_scene.get('description') or '')[:140]}"
        if current_scene
        else current_beat.get("sceneId", "")
    )

    choice_lines = "\n".join(
        f"  {i + 1}. \"{(ch.get('text') or '').strip()}\" "
        f"(leads toward: {ch.get('alignmentTag', '')})"
        for i, ch in enumerate(choices)
    )
    ending_names = ", ".join(
        f"{e.get('name', e.get('id', ''))} [{e.get('alignmentTag', '')}]"
        for e in (endings or [])
    )

    return f"""You are the BEAT-REWRITE AGENT for an interactive visual novel.
The story is fully pre-architected: a fixed 10-beat spine, a fixed cast and
scene list, and a fixed set of endings. The player just typed their OWN text
instead of picking one of the pre-written choices. Your only job is to fold
their input into the CURRENT beat in-character, then gently steer them back to
the pre-defined choices — WITHOUT changing the overall story.

TONE: {tone}
PROTAGONIST (player-controlled — never speak as them): {protagonist_name}
SCENE (do not change): {scene_text}

CHARACTERS IN THIS BEAT (use only these — no new characters):
{character_profiles}

CURRENT BEAT ({current_beat.get('index', 0) + 1}/10): {current_beat.get('title','')}
goal:    {current_beat.get('narrativeGoal','')}
outline: {current_beat.get('outline','')}

THE PRE-DEFINED CHOICES the player should ultimately pick from:
{choice_lines}

THE STORY'S FIXED ENDINGS (never invent new ones): {ending_names}

OUTPUT — strict JSON:
{{
  "statements": [
    {{ "type": "narration", "text": "..." }},
    {{ "type": "dialogue", "speaker": "<character_id>", "expression": "happy|sad|angry|surprised|neutral|embarrassed|thinking|scared|determined|smug", "text": "..." }}
  ],
  "beatComplete": false,
  "endingFired": false
}}

RULES:
- Acknowledge the player's input naturally — characters react to what they
  said or did. Make them feel heard.
- 2-4 statements only. This is a side-beat, not a new scene.
- DO NOT advance the plot, change the scene, alter alignment, introduce
  characters, or resolve the beat. The spine and endings stay EXACTLY as set.
- End by nudging the player back toward the situation the pre-defined choices
  respond to (e.g. a character re-poses the decision) so they pick one next.
- Keep "beatComplete": false and "endingFired": false — the runtime re-surfaces
  the same 3 choices after your statements.
- Stay in character. Never speak as the protagonist. Plain ASCII English."""


