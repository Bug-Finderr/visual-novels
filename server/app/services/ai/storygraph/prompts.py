"""Per-agent prompt builders for the story-generation graph.

Each builder starts with a stable, greppable banner (e.g. "OVERALL PLOT
AGENT") — node identity that also lets the mock-LLM test route canned
responses by inspecting the prompt.
"""
from __future__ import annotations

import json


def _setup_block(setup: dict) -> str:
    premise = f"\n- Story Premise: {setup['premise']}" if setup.get("premise") else ""
    return (
        f"- Genre: {setup.get('genre')}\n"
        f"- Art Style: {setup.get('artStyle')}\n"
        f"- Setting/World: {setup.get('setting')}\n"
        f"- Protagonist: {setup.get('protagonistName')} - {setup.get('protagonistPersonality')}\n"
        f"- Tone: {setup.get('tone')}"
        f"{premise}"
    )


def _continuation_block(cont: dict | None) -> str:
    if not cont:
        return ""
    pw = cont.get("prior_world") or {}
    pe = cont.get("prior_ending") or {}
    n = cont.get("chapter_number", 2)
    prior_cast = cont.get("prior_characters") or []
    cast_line = (
        "\nEXISTING CAST — your characterBriefs MUST reuse these EXACT ids "
        "(same id, same name); only add briefs for genuinely NEW characters:\n"
        + json.dumps(prior_cast, ensure_ascii=False)
        if prior_cast else ""
    )
    return f"""

THIS IS CHAPTER {n} of an ongoing story.
PREVIOUS WORLD: {pw.get('name', '')}
{pw.get('description', '')}
PREVIOUS CHAPTER'S CHOSEN ENDING ({pe.get('name', '')}):
{pe.get('summary', '')}
{pe.get('epilogueOutline', '')}{cast_line}

CONTINUATION RULES:
- Re-use the SAME world name + key rules and the SAME character ids (above).
- Pick up AFTER the previous ending; do not rewrite history, build forward.
- Produce a FRESH arc + FRESH endings for THIS chapter."""


# ---------------------------------------------------------------------------
# 1. OVERALL PLOT AGENT  (Gemini Flash)
# ---------------------------------------------------------------------------

def plot_prompt(setup: dict, continuation: dict | None = None) -> str:
    return f"""OVERALL PLOT AGENT.
You are the showrunner for an interactive visual novel. Design the high-level
skeleton ONLY — world premise, dramatic arc, the cast roster (as briefs, not
full bios), and the 5-6 STORY-LEVEL endings the whole arc can resolve into.
Do NOT write scenes, beats, or dialogue here — later agents do that.

PLAYER SPECIFICATIONS:
{_setup_block(setup)}{_continuation_block(continuation)}

Respond with valid JSON ONLY:
{{
  "worldLore": {{
    "name": "string - the world/setting name",
    "description": "string - 2-3 paragraph world description",
    "rules": ["string - key rules/facts about this world"],
    "history": "string - brief relevant history"
  }},
  "plotArc": {{
    "premise": "string - the central hook in 1-2 sentences",
    "dramaticQuestion": "string - the question the arc answers",
    "themes": ["string - thematic elements"],
    "arcSummary": "string - 3-5 sentence beginning-middle-end shape"
  }},
  "plotEndings": [
    {{
      "id": "lowercase_snake_case (e.g. plot_redemption)",
      "name": "Human Readable Name",
      "alignmentTag": "one short lowercase word, UNIQUE across endings",
      "summary": "2-3 sentence story-level outcome",
      "tone": "tragic | triumphant | bittersweet | ..."
    }}
  ],
  "characterBriefs": [
    {{
      "id": "lowercase_snake_case (e.g. luna_silver)",
      "name": "Display Name",
      "gender": "female | male | neutral",
      "role": "love interest | rival | mentor | ...",
      "oneLine": "string - one-sentence dramatic function + hook"
    }}
  ]
}}

HARD RULES:
- 5 or 6 plotEndings, each with a DISTINCT single-word alignmentTag.
- 3-5 characterBriefs (NOT counting the player's protagonist).
- gender is EXACTLY 'female', 'male', or 'neutral'.
- ids are valid identifiers (letters/underscores, no spaces)."""


# ---------------------------------------------------------------------------
# 2. WORLD-BUILDING AGENT  (Gemini Flash)
# ---------------------------------------------------------------------------

def world_prompt(state: dict) -> str:
    world = state.get("worldLore") or {}
    plot = state.get("plotArc") or {}
    return f"""WORLD-BUILDING AGENT.
Given the world + arc below, produce the COMPLETE catalogue of scenes
(locations) that the story could ever use — including settings suitable for
each of the story-level endings. Every later beat and ending will reference
one of these scene ids; nothing is invented later.

WORLD: {world.get('name', '')}
{world.get('description', '')}
RULES: {json.dumps(world.get('rules') or [], ensure_ascii=False)}
ARC: {plot.get('arcSummary', '')}
THEMES: {json.dumps(plot.get('themes') or [], ensure_ascii=False)}

Respond with valid JSON ONLY:
{{
  "scenes": [
    {{
      "id": "lowercase_snake_case (e.g. school_courtyard)",
      "name": "Display Name",
      "description": "DETAILED visual description for image generation: time of day, lighting, weather, colors, architecture, objects, atmosphere. Be very specific.",
      "narrativeContext": "when this scene appears in the story"
    }}
  ]
}}

HARD RULES:
- Generate 8-14 scenes. Multiple beats may share one scene.
- Descriptions must be EXTREMELY detailed for consistent image generation.
- ids are valid identifiers."""


# ---------------------------------------------------------------------------
# 3. CHARACTER AGENT  (Gemini Flash, one call per brief)
# ---------------------------------------------------------------------------

def character_prompt(brief: dict, world: dict, plot: dict, setup: dict) -> str:
    return f"""CHARACTER AGENT.
Flesh out ONE character into a full, production-ready profile. Stay
consistent with the brief, world, and tone. Output ONE character object.

BRIEF: {json.dumps(brief, ensure_ascii=False)}
WORLD: {world.get('name', '')} — {world.get('description', '')[:400]}
TONE: {setup.get('tone')}
ART STYLE: {setup.get('artStyle')}

Respond with valid JSON ONLY (a single object):
{{
  "id": "{brief.get('id', 'character')}",
  "name": "{brief.get('name', '')}",
  "age": "string",
  "gender": "{brief.get('gender', 'neutral')}",
  "role": "{brief.get('role', '')}",
  "personality": "detailed personality description",
  "appearance": "EXTREMELY detailed physical appearance for image generation: hair color/style, eye color, skin tone, build, clothing, distinguishing features.",
  "backstory": "background and motivation",
  "relationshipToProtagonist": "how they relate to the protagonist",
  "speechStyle": "how they talk (formal, casual, slang, ...)",
  "quirks": ["unique habits"],
  "color": "#RRGGBB hex for their dialogue name",
  "voiceCaption": "ENGLISH one-sentence TTS voice description starting with gender + apparent age, then vocal qualities (warm/raspy/clear), pitch, and default delivery. Stable per character."
}}

HARD RULES:
- Keep the SAME id and gender as the brief.
- appearance must be EXTREMELY detailed.
- voiceCaption must be ENGLISH and match the gender."""


# ---------------------------------------------------------------------------
# 4. CHAPTER GENERATOR AGENT  (Gemini Flash)
# ---------------------------------------------------------------------------

def chapter_prompt(state: dict, feedback: dict | None = None) -> str:
    world = state.get("worldLore") or {}
    plot = state.get("plotArc") or {}
    plot_endings = state.get("plot_endings") or []
    scenes = state.get("scenes") or []
    characters = state.get("characters") or []
    cont = state.get("continuation")

    scene_ref = [{"id": s.get("id"), "name": s.get("name")} for s in scenes]
    char_ref = [{"id": c.get("id"), "name": c.get("name"), "role": c.get("role")} for c in characters]
    plot_end_ref = [{"id": e.get("id"), "name": e.get("name"), "alignmentTag": e.get("alignmentTag")} for e in plot_endings]

    fb = ""
    if feedback and feedback.get("issues"):
        fb = (
            "\n\nThe Memory gate REJECTED the previous attempt. Fix EVERY issue:\n- "
            + "\n- ".join(feedback["issues"])
        )

    opening_ack = ""
    if cont:
        opening_ack = " The opening must acknowledge the previous chapter's ending."

    return f"""CHAPTER GENERATOR AGENT.
Using the FIXED world, scenes, cast, and story-level endings below, write THIS
chapter: a 10-beat spine, the chapter's 5 candidate endings (each routes toward
one story-level ending), and the opening script for beat 0.{opening_ack}

WORLD: {world.get('name', '')}
ARC: {plot.get('arcSummary', '')}
DRAMATIC QUESTION: {plot.get('dramaticQuestion', '')}
SCENES (use these ids only): {json.dumps(scene_ref, ensure_ascii=False)}
CHARACTERS (use these ids only): {json.dumps(char_ref, ensure_ascii=False)}
STORY-LEVEL ENDINGS: {json.dumps(plot_end_ref, ensure_ascii=False)}{fb}

Respond with valid JSON ONLY:
{{
  "storySpine": [
    {{
      "id": "lowercase_snake_case (e.g. beat_1_arrival)",
      "index": 0,
      "title": "short beat title",
      "outline": "2-3 sentence summary of what happens",
      "sceneId": "a scene id from SCENES",
      "castIds": ["character ids present in this beat"],
      "narrativeGoal": "what this beat accomplishes",
      "choices": [
        {{
          "text": "the choice the player sees (1 short sentence)",
          "consequence": "1-line hint shown on hover",
          "alignmentTag": "one of THIS chapter's ending alignmentTags",
          "magnitude": 1
        }}
      ]
    }}
  ],
  "endings": [
    {{
      "id": "lowercase_snake_case (e.g. ending_noble_sacrifice)",
      "name": "Human Readable Name",
      "alignmentTag": "short lowercase tag, UNIQUE across the 5 chapter endings",
      "summary": "2-3 sentence outcome",
      "tone": "tragic | triumphant | bittersweet | ...",
      "finalSceneId": "a scene id from SCENES",
      "epilogueOutline": "3-4 sentence outline the runtime expands into the closing dialogue",
      "plotEndingId": "the story-level ending id this chapter ending feeds"
    }}
  ],
  "openingScript": [
    {{
      "type": "narration | dialogue | scene_change | show_character | hide_character",
      "speaker": "character id (dialogue only, else null)",
      "expression": "happy | sad | angry | surprised | neutral | embarrassed | thinking | scared | determined | smug",
      "text": "narration or dialogue text",
      "sceneId": "for scene_change only",
      "characterId": "for show_character/hide_character only",
      "position": "left | center | right (for show_character only)"
    }}
  ]
}}

HARD RULES:
- EXACTLY 10 beats, index 0..9. Beat 0 = opening, beat 9 = climax.
- EXACTLY 5 endings with DISTINCT single-word alignmentTags.
- EVERY beat has EXACTLY 3 choices; each choice.alignmentTag MUST be one of
  THIS chapter's 5 ending tags. Across the 10 beats, the choices must make ALL
  5 chapter endings reachable.
- Every beat.sceneId and ending.finalSceneId MUST be an id from SCENES.
- Every beat.castIds entry MUST be an id from CHARACTERS.
- openingScript covers ONLY beat 0: 12-20 statements, NO choices."""


# ---------------------------------------------------------------------------
# 5. MEMORY AGENT  (gate, optional semantic pass — Gemini Flash)
# ---------------------------------------------------------------------------

def memory_prompt(state: dict) -> str:
    plot = state.get("plotArc") or {}
    spine = state.get("storySpine") or []
    endings = state.get("chapter_endings") or []
    beat_digest = [
        {"index": b.get("index"), "title": b.get("title"),
         "tags": [c.get("alignmentTag") for c in (b.get("choices") or [])]}
        for b in spine
    ]
    end_digest = [{"name": e.get("name"), "tag": e.get("alignmentTag"), "tone": e.get("tone")} for e in endings]
    return f"""MEMORY AGENT — continuity & payoff critic.
The structural checks already passed. Judge ONLY higher-order quality:
pacing across the 10 beats, whether each ending is dramatically earned, and
whether choices are meaningful (not cosmetic). Be strict but fair.

DRAMATIC QUESTION: {plot.get('dramaticQuestion', '')}
THEMES: {json.dumps(plot.get('themes') or [], ensure_ascii=False)}
BEATS: {json.dumps(beat_digest, ensure_ascii=False)}
ENDINGS: {json.dumps(end_digest, ensure_ascii=False)}

Respond with valid JSON ONLY:
{{
  "revise": false,
  "route": "chapter",
  "concerns": ["short concern strings; empty if none"]
}}
Set "revise": true ONLY for a real dramatic flaw worth regenerating the spine."""
