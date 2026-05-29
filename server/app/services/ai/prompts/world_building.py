def build_continuation_prompt(
    prior: dict, prior_world: dict, prior_ending: dict, chapter_number: int,
) -> str:
    """Continuation chapter — same world + cast, new spine + new endings, with
    the previous chapter's chosen ending as the new chapter's starting state.
    """
    base = build_world_prompt({
        "genre": prior["setup_genre"],
        "artStyle": prior["setup_art_style"],
        "setting": prior["setup_setting"],
        "protagonistName": prior["setup_protagonist_name"],
        "protagonistPersonality": prior["setup_protagonist_personality"],
        "tone": prior["setup_tone"],
        "premise": prior.get("setup_premise"),
    })
    continuation = f"""

THIS IS CHAPTER {chapter_number} of an ongoing story. The previous chapter
established this world and ended like this:

PREVIOUS WORLD: {prior_world.get('name', '')}
{prior_world.get('description', '')}

PREVIOUS CHAPTER'S CHOSEN ENDING ({prior_ending.get('name', '')}):
{prior_ending.get('summary', '')}
{prior_ending.get('epilogueOutline', '')}

CONTINUATION RULES (in addition to all rules above):
- Re-use the SAME world name and key world rules.
- Re-use the SAME characters (their ids must match the previous chapter
  exactly — re-emit the full character entries with their established
  personalities and backstories preserved, and add any NEW characters this
  chapter introduces with brand-new ids).
- Pick up time AFTER the previous ending. The opening beat (beat 0) must
  acknowledge the previous ending's outcome explicitly.
- Generate a FRESH 10-beat spine and 5 NEW candidate endings for THIS
  chapter — they should be different beats and different endings than
  chapter {chapter_number - 1} had.
- The chosen previous-ending should constrain what's possible: do NOT
  rewrite history, build forward from it.
"""
    return base + continuation


def build_world_prompt(setup: dict) -> str:
    premise_line = f"- Story Premise: {setup['premise']}" if setup.get("premise") else ""
    return f"""You are a master visual novel writer and world builder. You create rich,
interconnected story worlds with compelling characters and pre-architected story
arcs that branch toward multiple distinct endings.

TASK: Generate a COMPLETE visual novel foundation — world, full cast, every
scene that will appear in the story (including ending scenes), a 10-beat story
spine, and 5 distinct candidate endings. Everything must be known at generation
time; the runtime will only expand individual beats into actual dialogue. No
character or scene is introduced later.

PLAYER SPECIFICATIONS:
- Genre: {setup['genre']}
- Art Style: {setup['artStyle']}
- Setting/World: {setup['setting']}
- Protagonist: {setup['protagonistName']} - {setup['protagonistPersonality']}
- Tone: {setup['tone']}
{premise_line}

OUTPUT FORMAT: You MUST respond with valid JSON matching this exact schema:
{{
  "worldLore": {{
    "name": "string - name of this world/setting",
    "description": "string - 2-3 paragraph world description",
    "rules": ["string - key rules/facts about this world"],
    "history": "string - brief relevant history"
  }},
  "characters": [
    {{
      "id": "string - lowercase_snake_case identifier (e.g., luna_silver)",
      "name": "string - display name",
      "age": "string",
      "gender": "string - EXACTLY one of: 'female', 'male', or 'neutral'. Determines which TTS voice path is used (female -> speaker_1 preset; male/neutral -> description-driven). Always pick female or male if the character clearly is one; reserve 'neutral' for animals, non-binary, or unknown.",
      "role": "string - their role in the story (e.g., love interest, rival, mentor)",
      "personality": "string - detailed personality description",
      "appearance": "string - DETAILED physical appearance for image generation. Include: hair color/style, eye color, skin tone, build, clothing style, distinguishing features. Be very specific.",
      "backstory": "string - background and motivation",
      "relationshipToProtagonist": "string - how they relate to the protagonist",
      "speechStyle": "string - how they talk (formal, casual, uses slang, etc.)",
      "quirks": ["string - unique personality quirks or habits"],
      "color": "string - a hex color code for their dialogue name display (e.g., #FF6B9D)",
      "voiceCaption": "string - ENGLISH one-sentence description of this character's voice for the Mulberry TTS engine. Start with gender + apparent age (matching the `gender` field above), then describe vocal qualities (warm/raspy/clear/breathy), pitch (low/mid/high), and default delivery (calm/animated/measured/quick). Reused as the steering prompt for every line. Examples: 'A cheerful young woman with a bright, warm voice and quick, animated delivery.' / 'A measured middle-aged man with a low, gravelly voice that lingers on consonants.' / 'A soft-spoken teenage boy with a clear mid-range voice and slightly hesitant pacing.'"
    }}
  ],
  "plotArc": {{
    "premise": "string - the main story hook in 1-2 sentences",
    "themes": ["string - thematic elements"]
  }},
  "scenes": [
    {{
      "id": "string - lowercase_snake_case (e.g., school_courtyard)",
      "name": "string - display name",
      "description": "string - DETAILED visual description for image generation. Include: time of day, lighting, weather, colors, architecture, objects, atmosphere. Be very specific.",
      "narrativeContext": "string - when this scene appears in the story"
    }}
  ],
  "storySpine": [
    {{
      "id": "string - lowercase_snake_case beat id (e.g., beat_1_arrival)",
      "index": 0,
      "title": "string - short beat title",
      "outline": "string - 2-3 sentence summary of what happens in this beat",
      "sceneId": "string - which scene (from scenes[]) this beat takes place in",
      "castIds": ["string - character ids present in this beat"],
      "narrativeGoal": "string - what this beat accomplishes for the story",
      "choices": [
        {{
          "text": "string - the choice text the player sees (1 short sentence)",
          "consequence": "string - 1-line hint about where this leads, shown on hover",
          "alignmentTag": "string - one of the 5 ending alignmentTag values",
          "magnitude": 1
        }}
      ]
    }}
  ],
  "endings": [
    {{
      "id": "string - lowercase_snake_case (e.g., ending_noble_sacrifice)",
      "name": "string - human-readable name (e.g., 'Noble Sacrifice')",
      "alignmentTag": "string - short tag the alignment system uses (e.g., 'noble', 'shadow', 'love', 'truth', 'escape')",
      "summary": "string - 2-3 sentence summary of how this ending plays out",
      "tone": "string - emotional tone (tragic, triumphant, bittersweet, etc.)",
      "finalSceneId": "string - which scene from scenes[] is the setting for this ending",
      "epilogueOutline": "string - 3-4 sentence outline of the final sequence the runtime will expand into dialogue when this ending fires"
    }}
  ],
  "openingScript": [
    {{
      "type": "narration | dialogue | scene_change | show_character | hide_character",
      "speaker": "string - character id (for dialogue only, null otherwise)",
      "expression": "string - one of: happy, sad, angry, surprised, neutral, embarrassed, thinking, scared, determined, smug (for dialogue only)",
      "text": "string - the narration or dialogue text",
      "sceneId": "string - for scene_change type only",
      "characterId": "string - for show_character/hide_character type only",
      "position": "left | center | right - for show_character type only"
    }}
  ]
}}

HARD RULES:
- Generate exactly 3-5 characters (NOT including the protagonist, who is the player)
- The "scenes" array is the COMPLETE list — every location that will ever appear, including each ending's finalSceneId. Generate enough scenes (8-14 typically) so every beat AND every ending has a referenced scene. Multiple beats can share a scene.
- Generate EXACTLY 10 beats in storySpine, ordered by index 0..9. Beat 0 is the opening; beat 9 is the climax.
- Generate EXACTLY 5 endings with DISTINCT alignmentTag values (each tag a single lowercase word). Each ending must reference a finalSceneId that exists in scenes[].
- Each beat MUST have EXACTLY 3 choices (no fewer, no more) that fire after the beat's narrative concludes. Each choice MUST include alignmentTag (matching one of the 5 endings) and magnitude (integer 1-3). Across the 10 beats, the choices together must offer meaningful pivots for ALL 5 endings — beat 0 might tilt 3 ways, beat 5 might tilt 3 ways, etc.
- Character appearances must be EXTREMELY detailed for consistent image generation.
- Scene descriptions must be EXTREMELY detailed for image generation.
- All ids must be valid JavaScript identifiers (no spaces, start with letter, use underscores).
- The openingScript covers ONLY beat 0; keep it 12-20 statements; do not include `choices` (choices are added dynamically when the beat is expanded at runtime).
- voiceCaption must be in ENGLISH — it is the steering description for the Mulberry TTS model and must be stable per character.
- Match every castIds[] entry to a real character id; match every sceneId to a real scene id."""
