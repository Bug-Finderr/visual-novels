import { ai, models } from './geminiClient.js';
import { assetManager } from '../assetManager.js';
import { buildSpritePrompt, buildBackgroundPrompt } from './prompts/spriteGeneration.js';
import { removeSpriteBg } from '../backgroundRemover.js';
import logger from '../../utils/logger.js';

const EXPRESSIONS = [
  'happy', 'sad', 'angry', 'surprised', 'neutral',
  'embarrassed', 'thinking', 'scared', 'determined', 'smug',
];

export const imageGenerator = {
  async generateCharacterSprites(sessionId, character, artStyle, progressCallback) {
    const results = {};

    // Generate neutral sprite first as consistency anchor
    logger.info(`Generating neutral sprite for ${character.name}...`);
    const neutralPrompt = buildSpritePrompt(character, 'neutral', artStyle, false);
    let neutralImage = await this._generateImage(neutralPrompt, [], '3:4');
    neutralImage = await removeSpriteBg(neutralImage);
    const neutralPath = await assetManager.saveCharacterSprite(
      sessionId, character.id, 'neutral', neutralImage
    );
    results.neutral = neutralPath;
    if (progressCallback) progressCallback('neutral', 1, EXPRESSIONS.length);

    // Generate remaining expressions using neutral as reference
    const remaining = EXPRESSIONS.filter((e) => e !== 'neutral');
    for (let i = 0; i < remaining.length; i++) {
      const expr = remaining[i];
      logger.info(`Generating ${expr} sprite for ${character.name}...`);
      const prompt = buildSpritePrompt(character, expr, artStyle, true);

      let image = await this._generateImage(prompt, [
        { mimeType: 'image/png', data: neutralImage.toString('base64') },
      ], '3:4');
      image = await removeSpriteBg(image);

      const path = await assetManager.saveCharacterSprite(
        sessionId, character.id, expr, image
      );
      results[expr] = path;
      if (progressCallback) progressCallback(expr, i + 2, EXPRESSIONS.length);
    }

    return results;
  },

  async generateBackground(sessionId, scene, artStyle, progressCallback) {
    logger.info(`Generating background for ${scene.name}...`);
    const prompt = buildBackgroundPrompt(scene, artStyle);
    // No background removal for scene backgrounds — they stay as-is, high-res 16:9
    const image = await this._generateImage(prompt, [], '16:9');
    const path = await assetManager.saveBackground(sessionId, scene.id, image);
    if (progressCallback) progressCallback(scene.id);
    return path;
  },

  async generateSingleSprite(sessionId, character, expression, artStyle, referenceImage = null) {
    const prompt = buildSpritePrompt(character, expression, artStyle, !!referenceImage);
    const refs = referenceImage
      ? [{ mimeType: 'image/png', data: referenceImage.toString('base64') }]
      : [];
    let image = await this._generateImage(prompt, refs, '3:4');
    image = await removeSpriteBg(image);
    return assetManager.saveCharacterSprite(sessionId, character.id, expression, image);
  },

  async _generateImage(promptText, referenceImages = [], aspectRatio = '1:1', maxRetries = 3) {
    const contents = [{ text: promptText }];
    for (const ref of referenceImages) {
      contents.push({ inlineData: ref });
    }

    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      try {
        const response = await ai.models.generateContent({
          model: models.imageGen,
          contents,
          config: {
            responseModalities: ['IMAGE'],
            imageConfig: {
              numberOfImages: 1,
              aspectRatio,
            },
          },
        });

        if (!response.candidates || response.candidates.length === 0) {
          throw new Error('Gemini returned no candidates');
        }

        const candidate = response.candidates[0];
        if (!candidate.content || !candidate.content.parts) {
          const reason = candidate.finishReason || 'unknown';
          throw new Error(`Gemini candidate has no content (finishReason: ${reason})`);
        }

        for (const part of candidate.content.parts) {
          if (part.inlineData) {
            return Buffer.from(part.inlineData.data, 'base64');
          }
        }

        throw new Error('No image data in Gemini response parts');
      } catch (err) {
        logger.warn(`Image generation attempt ${attempt}/${maxRetries} failed: ${err.message}`);
        if (attempt === maxRetries) {
          throw new Error(`Image generation failed after ${maxRetries} attempts: ${err.message}`);
        }
        // Exponential backoff: 2s, 4s, 8s
        const delay = Math.pow(2, attempt) * 1000;
        logger.info(`Retrying in ${delay / 1000}s...`);
        await new Promise((r) => setTimeout(r, delay));
      }
    }
  },
};
