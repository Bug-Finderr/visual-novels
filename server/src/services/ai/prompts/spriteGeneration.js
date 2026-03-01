const STYLE_MAP = {
  anime: 'anime art style, cel-shaded, vibrant colors, clean linework, visual novel game character sprite',
  cartoon: 'western cartoon style, bold outlines, expressive features, bright colors, visual novel character',
  realistic: 'semi-realistic digital painting style, detailed but slightly stylized, visual novel portrait',
  fiction: 'illustrated fiction book style, painterly, soft edges, storybook aesthetic, visual novel character',
};

const EXPRESSION_DESCRIPTIONS = {
  happy: 'genuinely happy, warm smile, bright eyes, relaxed posture',
  sad: 'visibly sad, downcast eyes, slight frown, slumped shoulders',
  angry: 'angry, furrowed brows, clenched jaw, intense glare',
  surprised: 'surprised, wide eyes, raised eyebrows, slightly open mouth',
  neutral: 'neutral calm expression, relaxed face, composed posture',
  embarrassed: 'embarrassed, blushing cheeks, averted gaze, sheepish smile',
  thinking: 'deep in thought, slightly squinted eyes, hand near chin, contemplative',
  scared: 'frightened, wide fearful eyes, tense body, slightly recoiling',
  determined: 'determined, firm jaw, focused eyes, confident stance',
  smug: 'smug, slight smirk, half-lidded eyes, confident tilt of head',
};

export function buildSpritePrompt(character, expression, artStyle, hasReference) {
  const style = STYLE_MAP[artStyle] || STYLE_MAP.anime;
  const exprDesc = EXPRESSION_DESCRIPTIONS[expression] || EXPRESSION_DESCRIPTIONS.neutral;

  let prompt = `Generate a visual novel character sprite.

STYLE: ${style}
CHARACTER: ${character.name}
APPEARANCE: ${character.appearance}
EXPRESSION: ${exprDesc}

REQUIREMENTS:
- Upper body portrait (head to waist), facing slightly towards camera
- TRANSPARENT or solid single-color background (easy to composite)
- Consistent character design${hasReference ? ' matching the reference image provided' : ''}
- Character centered in frame
- High quality, clean art suitable for a visual novel game
- Expression must be clearly readable and distinct
- Clothing and accessories identical across all expressions`;

  if (hasReference) {
    prompt += `

CRITICAL: This sprite must depict the EXACT SAME character as the reference image. Same face shape, same hair color and style, same clothing, same proportions. Only the facial expression and minor body language should change to show: ${exprDesc}`;
  }

  return prompt;
}

export function buildBackgroundPrompt(scene, artStyle) {
  const bgStyles = {
    anime: 'anime background art style, vivid colors, similar to Makoto Shinkai or Kyoto Animation backgrounds',
    cartoon: 'stylized cartoon environment, bold colors, clean shapes, vibrant',
    realistic: 'semi-realistic digital painting of an environment, atmospheric, detailed',
    fiction: 'illustrated storybook environment, painterly, rich detail, warm lighting',
  };

  const style = bgStyles[artStyle] || bgStyles.anime;

  return `Generate a visual novel background scene.

STYLE: ${style}
SCENE: ${scene.name}
DESCRIPTION: ${scene.description}

REQUIREMENTS:
- Landscape orientation (16:9 aspect ratio)
- High resolution, highly detailed, crisp and sharp
- No characters or people in the scene
- Rich environmental detail and atmosphere
- Suitable as a background for character sprites overlaid on top
- Consistent lighting and color palette
- Should feel like a real location the player can imagine being in`;
}

export { EXPRESSION_DESCRIPTIONS };
