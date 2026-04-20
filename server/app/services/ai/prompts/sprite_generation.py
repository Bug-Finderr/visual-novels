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

    prompt = f"""Generate a visual novel character sprite.

STYLE: {style}
CHARACTER: {character['name']}
APPEARANCE: {character['appearance']}
EXPRESSION: {expr_desc}

REQUIREMENTS:
- Upper body portrait (head to waist), facing slightly towards camera
- TRANSPARENT or solid single-color background (easy to composite)
- Consistent character design{reference_note}
- Character centered in frame
- High quality, clean art suitable for a visual novel game
- Expression must be clearly readable and distinct
- Clothing and accessories identical across all expressions"""

    if has_reference:
        prompt += f"""

CRITICAL: This sprite must depict the EXACT SAME character as the reference image. Same face shape, same hair color and style, same clothing, same proportions. Only the facial expression and minor body language should change to show: {expr_desc}"""

    return prompt


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
