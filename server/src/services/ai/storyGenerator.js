import { ai, models } from './geminiClient.js';
import { buildWorldPrompt } from './prompts/worldBuilding.js';
import { withRetry } from './retry.js';
import logger from '../../utils/logger.js';

export const storyGenerator = {
  async generateWorld(setup) {
    const prompt = buildWorldPrompt(setup);

    logger.info('Generating world with Gemini Pro...');
    const response = await withRetry(() => ai.models.generateContent({
      model: models.storyPro,
      contents: [{ role: 'user', parts: [{ text: prompt }] }],
      config: {
        temperature: 0.9,
        maxOutputTokens: 65536,
        responseMimeType: 'application/json',
      },
    }), { label: 'storyGenerator.generateWorld' });

    // Concatenate all text parts from the response
    let text = '';
    for (const part of response.candidates[0].content.parts) {
      if (part.text) text += part.text;
    }

    let parsed;
    try {
      parsed = JSON.parse(text);
    } catch (e) {
      // Try extracting JSON from markdown code blocks
      const match = text.match(/```(?:json)?\s*([\s\S]*?)```/);
      if (match) {
        try {
          parsed = JSON.parse(match[1]);
        } catch (e2) {
          logger.error('Failed to parse extracted JSON:', e2.message);
        }
      }

      if (!parsed) {
        // Try to find first { and last } to extract JSON
        const firstBrace = text.indexOf('{');
        const lastBrace = text.lastIndexOf('}');
        if (firstBrace !== -1 && lastBrace > firstBrace) {
          try {
            parsed = JSON.parse(text.slice(firstBrace, lastBrace + 1));
          } catch (e3) {
            logger.error('All JSON parse attempts failed. Response length:', text.length);
            logger.error('Response start:', text.slice(0, 300));
            logger.error('Response end:', text.slice(-300));
            throw new Error('Failed to parse story generation response as JSON');
          }
        } else {
          logger.error('No JSON object found in response. Length:', text.length);
          throw new Error('Failed to parse story generation response as JSON');
        }
      }
    }

    // Validate required fields
    if (!parsed.worldLore || !parsed.characters || !parsed.initialScenes || !parsed.openingScript) {
      const missing = ['worldLore', 'characters', 'initialScenes', 'openingScript']
        .filter((k) => !parsed[k]);
      throw new Error(`Story generation response missing required fields: ${missing.join(', ')}`);
    }

    if (parsed.characters.length < 3) {
      logger.warn(`Only ${parsed.characters.length} characters generated, expected 3-5`);
    }

    logger.info(
      `World generated: ${parsed.worldLore.name}, ${parsed.characters.length} characters, ${parsed.initialScenes.length} scenes`
    );

    return parsed;
  },
};
