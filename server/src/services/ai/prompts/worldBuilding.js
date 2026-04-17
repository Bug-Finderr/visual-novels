export function buildWorldPrompt(setup) {
  return `You are a master visual novel writer and world builder. You create rich,
interconnected story worlds with compelling characters.

TASK: Generate a complete visual novel foundation based on the player's specifications.

PLAYER SPECIFICATIONS:
- Genre: ${setup.genre}
- Art Style: ${setup.artStyle}
- Setting/World: ${setup.setting}
- Protagonist: ${setup.protagonistName} - ${setup.protagonistPersonality}
- Tone: ${setup.tone}
${setup.premise ? `- Story Premise: ${setup.premise}` : ''}

OUTPUT FORMAT: You MUST respond with valid JSON matching this exact schema:
{
  "worldLore": {
    "name": "string - name of this world/setting",
    "description": "string - 2-3 paragraph world description",
    "rules": ["string - key rules/facts about this world"],
    "history": "string - brief relevant history"
  },
  "characters": [
    {
      "id": "string - lowercase_snake_case identifier (e.g., luna_silver)",
      "name": "string - display name",
      "age": "string",
      "role": "string - their role in the story (e.g., love interest, rival, mentor)",
      "personality": "string - detailed personality description",
      "appearance": "string - DETAILED physical appearance for image generation. Include: hair color/style, eye color, skin tone, build, clothing style, distinguishing features. Be very specific.",
      "backstory": "string - background and motivation",
      "relationshipToProtagonist": "string - how they relate to the protagonist",
      "speechStyle": "string - how they talk (formal, casual, uses slang, etc.)",
      "quirks": ["string - unique personality quirks or habits"],
      "color": "string - a hex color code for their dialogue name display (e.g., #FF6B9D)"
    }
  ],
  "plotArc": {
    "premise": "string - the main story hook",
    "act1": "string - setup and inciting incident",
    "act2": "string - rising action and complications",
    "act3": "string - climax possibilities",
    "themes": ["string - thematic elements"],
    "possibleEndings": ["string - 2-3 possible ending directions"]
  },
  "initialScenes": [
    {
      "id": "string - lowercase_snake_case (e.g., school_courtyard)",
      "name": "string - display name",
      "description": "string - DETAILED visual description for image generation. Include: time of day, lighting, weather, colors, architecture, objects, atmosphere. Be very specific.",
      "narrativeContext": "string - when this scene appears in the story"
    }
  ],
  "openingScript": [
    {
      "type": "narration | dialogue | scene_change | show_character | hide_character",
      "speaker": "string - character id (for dialogue only, null otherwise)",
      "expression": "string - one of: happy, sad, angry, surprised, neutral, embarrassed, thinking, scared, determined, smug (for dialogue only)",
      "text": "string - the narration or dialogue text",
      "sceneId": "string - for scene_change type only",
      "characterId": "string - for show_character/hide_character type only",
      "position": "left | center | right - for show_character type only",
      "choices": [
        {
          "text": "string - choice label shown to the player",
          "consequence": "string - brief description of where this leads"
        }
      ]
    }
  ]
}

RULES:
- Generate exactly 3-5 characters (NOT including the protagonist, who is the player)
- Generate exactly 5 initial background scenes
- The openingScript should have 12-20 statements covering the first scene — tight, punchy pacing
- Each statement's text must be under 220 characters; favor dialogue over long narration
- Never stack more than 2 narration statements in a row
- Include at least 1 choice point in the opening (statement with type "choice" that has a "choices" array)
- Character appearances must be EXTREMELY detailed for consistent image generation
- Scene descriptions must be EXTREMELY detailed for image generation
- All character IDs must be valid JavaScript identifiers (no spaces, start with letter, use underscores)
- Opening script must establish the setting, introduce at least 2 characters, and present the first conflict
- Each choice should have 2-3 options; choice text ≤ 60 chars each
- Use only these expressions: happy, sad, angry, surprised, neutral, embarrassed, thinking, scared, determined, smug`;
}
