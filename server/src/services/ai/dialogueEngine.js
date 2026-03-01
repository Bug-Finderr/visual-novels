import { ai, models } from './geminiClient.js';
import { buildDialogueSystemPrompt } from './prompts/dialogueSystem.js';
import { sessionQueries } from '../../db/queries/sessions.js';
import { characterQueries } from '../../db/queries/characters.js';
import { sceneQueries } from '../../db/queries/scenes.js';
import { dialogueHistoryQueries } from '../../db/queries/dialogueHistory.js';
import logger from '../../utils/logger.js';

export const dialogueEngine = {
  async processPlayerAction(sessionId, action) {
    const session = await this._loadSessionContext(sessionId);
    const systemPrompt = buildDialogueSystemPrompt(session);
    const history = this._buildConversationHistory(sessionId);

    const userMessage =
      action.type === 'choice'
        ? `[PLAYER CHOSE: "${action.text}"] (consequence hint: ${action.consequence})`
        : `[PLAYER SAYS: "${action.text}"]`;

    const messages = [
      ...history,
      { role: 'user', parts: [{ text: userMessage }] },
    ];

    logger.info(`Processing player action for session ${sessionId}: ${action.type}`);

    const response = await ai.models.generateContent({
      model: models.dialogueFlash,
      contents: messages,
      config: {
        systemInstruction: systemPrompt,
        temperature: 0.8,
        maxOutputTokens: 3000,
        responseMimeType: 'application/json',
      },
    });

    const responseText = response.candidates[0].content.parts[0].text;
    let aiOutput;
    try {
      aiOutput = JSON.parse(responseText);
    } catch (e) {
      const match = responseText.match(/```(?:json)?\s*([\s\S]*?)```/);
      if (match) {
        aiOutput = JSON.parse(match[1]);
      } else {
        logger.error('Failed to parse dialogue response:', responseText.slice(0, 500));
        throw new Error('Failed to parse dialogue response as JSON');
      }
    }

    // Save to dialogue history
    dialogueHistoryQueries.insert(sessionId, 'user', userMessage, session.currentLabel);
    dialogueHistoryQueries.insert(sessionId, 'model', responseText, session.currentLabel);

    return aiOutput;
  },

  _loadSessionContext(sessionId) {
    const session = sessionQueries.getById(sessionId);
    if (!session) throw new Error(`Session ${sessionId} not found`);

    const characters = characterQueries.getBySession(sessionId).map((c) => ({
      ...c,
      quirks: JSON.parse(c.quirks || '[]'),
    }));

    const currentScene = session.current_scene_id
      ? sceneQueries.getById(sessionId, session.current_scene_id)
      : null;

    return {
      worldLore: JSON.parse(session.world_lore || '{}'),
      characters,
      plotArc: JSON.parse(session.plot_arc || '{}'),
      currentScene,
      protagonistName: session.setup_protagonist_name,
      tone: session.setup_tone,
      currentLabel: session.current_label,
    };
  },

  _buildConversationHistory(sessionId) {
    const recent = dialogueHistoryQueries.getRecent(sessionId, 40);
    return recent.map((entry) => ({
      role: entry.role,
      parts: [{ text: entry.content }],
    }));
  },
};
