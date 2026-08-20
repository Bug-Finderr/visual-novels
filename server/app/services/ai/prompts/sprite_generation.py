STYLE_MAP = {
    "anime": "anime art style, cel-shaded, vibrant colors, clean linework, visual novel game character sprite",
    "cartoon": "western cartoon style, bold outlines, expressive features, bright colors, visual novel character",
    "realistic": "semi-realistic digital painting style, detailed but slightly stylized, visual novel portrait",
    "fiction": "illustrated fiction book style, painterly, soft edges, storybook aesthetic, visual novel character",
}

EXPRESSION_DESCRIPTIONS = {
    "happy": "genuinely happy, warm smile, bright eyes, relaxed posture",
    "sad": "visibly sad, downcast eyes, slight frown, slumped shoulders",
    "angry": "angry, furrowed brows, clenched jaw, intense glare",
    "surprised": "surprised, wide eyes, raised eyebrows, slightly open mouth",
    "neutral": "neutral calm expression, relaxed face, composed posture",
    "embarrassed": "embarrassed, blushing cheeks, averted gaze, sheepish smile",
    "thinking": "deep in thought, slightly squinted eyes, hand near chin, contemplative",
    "scared": "frightened, wide fearful eyes, tense body, slightly recoiling",
    "determined": "determined, firm jaw, focused eyes, confident stance",
    "smug": "smug, slight smirk, half-lidded eyes, confident tilt of head",
}

BG_STYLE_MAP = {
    "anime": "anime background art style, vivid colors, similar to Makoto Shinkai or Kyoto Animation backgrounds",
    "cartoon": "stylized cartoon environment, bold colors, clean shapes, vibrant",
    "realistic": "semi-realistic digital painting of an environment, atmospheric, detailed",
    "fiction": "illustrated storybook environment, painterly, rich detail, warm lighting",
}


def build_sprite_prompt(character: dict, expression: str, art_style: str, has_reference: bool) -> str:
    style = STYLE_MAP.get(art_style, STYLE_MAP["anime"])
    expr_desc = EXPRESSION_DESCRIPTIONS.get(expression, EXPRESSION_DESCRIPTIONS["neutral"])
    reference_note = " matching the reference image provided" if has_reference else ""

    # Asking for a flat chroma-key color rather than a transparent/alpha
    # background: image models follow "solid color" far more reliably than
    # "transparent," and background_remover.remove_sprite_bg() keys this
    # color out afterward with a plain color-distance threshold.
    from app.services.background_remover import CHROMA_KEY_COLOR
    key_hex = "#%02X%02X%02X" % CHROMA_KEY_COLOR

    prompt = f"""Generate a visual novel character sprite.

STYLE: {style}
CHARACTER: {character['name']}
APPEARANCE: {character['appearance']}
EXPRESSION: {expr_desc}

REQUIREMENTS:
- FULL-BODY portrait, head to feet, facing slightly toward camera (NOT a closeup, NOT cropped at the chest or waist)
- SOLID FLAT background of pure magenta color ({key_hex}), completely uniform across the entire background — no gradient, no shadow, no texture, no scenery. This is a chroma-key background that will be removed programmatically, so it must be a single flat color with nothing else in it.
- Consistent character design{reference_note}
- Character centered horizontally in frame; head near the top edge, feet near the bottom edge
- 3:4 portrait aspect
- High quality, clean art suitable for a visual novel game
- Expression must be clearly readable — make eyes/brows/mouth bold enough to read at full-body scale
- Clothing, hair, accessories, and body proportions IDENTICAL across all expressions
- IMPORTANT: none of the character's clothing, hair, or accessories should be this magenta color, to keep the chroma-key clean"""

    if has_reference:
        prompt += f"""

CRITICAL CONSISTENCY RULES (the reference image is the ground truth):
1. SAME FRAMING — head at the same vertical position, feet at the same vertical position, body at the same scale. Do NOT zoom in or crop. The head should be roughly the same pixel size as in the reference.
2. SAME identity — same face shape, hair color and style, eye color, skin tone, clothing, accessories.
3. SAME body proportions and standing pose silhouette.
4. ONLY the facial expression and minor body language change to show: {expr_desc}.
5. Keep the same flat {key_hex} chroma-key background as the reference."""

    return prompt


# --- Animation overlays (layered 2.5D rig) -------------------------------
# Each overlay is a TRANSPARENT image the exact size/framing of the neutral
# sprite, with only the changed facial region painted. The browser rig
# composites these over any emotion base to produce blink + lip-sync without
# a GPU. They are generated ONCE per character from the neutral sprite.
OVERLAY_DESCRIPTIONS = {
    "eyes_closed": (
        "the character's eyes fully CLOSED (relaxed eyelids, as mid-blink), "
        "drawn exactly over where the open eyes are in the reference"
    ),
    "mouth_half": (
        "the character's mouth slightly OPEN (small gap, mid-speech), "
        "drawn exactly over where the closed mouth is in the reference"
    ),
    "mouth_open": (
        "the character's mouth WIDE OPEN saying \"ah\" (clearly open), "
        "drawn exactly over where the closed mouth is in the reference"
    ),
}


def build_overlay_prompt(character: dict, overlay: str, art_style: str) -> str:
    """Prompt for a transparent facial overlay aligned to the neutral sprite.

    The neutral sprite is passed as the reference image (ground-truth framing).
    The model must return ONLY the changed region on a transparent canvas of
    the SAME dimensions so the browser can stack it pixel-aligned over the base.
    """
    style = STYLE_MAP.get(art_style, STYLE_MAP["anime"])
    region = OVERLAY_DESCRIPTIONS.get(overlay, OVERLAY_DESCRIPTIONS["eyes_closed"])

    return f"""Generate a TRANSPARENT animation overlay for a visual novel character sprite.

The reference image is the character's neutral full-body sprite — the ground truth
for size, position, framing, art style, and identity.

STYLE: {style}
TASK: Produce an image the EXACT SAME dimensions and framing as the reference, showing
{region}.

CRITICAL REQUIREMENTS:
- FULLY TRANSPARENT everywhere EXCEPT the small facial region described above.
- The painted region must sit at the IDENTICAL pixel position and scale as in the reference
  (same head position, same eye/mouth location). Do NOT move, zoom, or re-pose the character.
- Match the reference's exact art style, line weight, skin tone, and shading.
- Do NOT redraw the whole character, hair, body, or background — ONLY the changed facial region.
- Output must be a clean PNG with an alpha channel."""


def build_background_prompt(scene: dict, art_style: str) -> str:
    style = BG_STYLE_MAP.get(art_style, BG_STYLE_MAP["anime"])
    return f"""Generate a visual novel background scene.

STYLE: {style}
SCENE: {scene['name']}
DESCRIPTION: {scene['description']}

REQUIREMENTS:
- Landscape orientation (16:9 aspect ratio)
- High resolution, highly detailed, crisp and sharp
- No characters or people in the scene
- Rich environmental detail and atmosphere
- Suitable as a background for character sprites overlaid on top
- Consistent lighting and color palette
- Should feel like a real location the player can imagine being in"""


def build_cover_prompt(ctx: dict, art_style: str, has_reference: bool = False) -> str:
    """Portrait key-visual / poster cover for a story — the image shown on
    story cards and the library. No text is rendered (the UI overlays titles).
    """
    style = STYLE_MAP.get(art_style, STYLE_MAP["anime"])
    chars = ctx.get("characters") or []
    if chars:
        cast = "\n".join(f"- {c['name']}: {c.get('appearance', '')}" for c in chars[:3])
    else:
        cast = f"- {ctx.get('protagonist', 'the protagonist')}"
    reference_note = (
        "\n- The provided reference image is one of the main characters — keep that "
        "character's face, hair, and overall design consistent with it."
        if has_reference else ""
    )
    tone = ctx.get("tone", "")
    return f"""Generate a VERTICAL cover illustration (key visual / poster) for a visual novel.

STYLE: {style}; dramatic cover key-visual, cinematic composition, polished and richly detailed.
STORY TITLE (context only — do NOT render any text): {ctx.get('title', '')}
GENRE / MOOD: {ctx.get('genre', '')}, {tone} in tone
SETTING: {ctx.get('setting', '')}
FEATURED CHARACTERS:
{cast}

REQUIREMENTS:
- Portrait / vertical 3:4 composition, like a light-novel or visual-novel cover.
- Feature the main character(s) prominently in an evocative pose within the setting.
- Convey the {tone} mood through lighting, color, and atmosphere.
- Cohesive color palette, high quality, clean polished illustration.
- Leave a little visual breathing room near the top (as if a title could sit there).
- ABSOLUTELY NO text, letters, words, logos, signatures, or watermarks anywhere in the image.{reference_note}"""
