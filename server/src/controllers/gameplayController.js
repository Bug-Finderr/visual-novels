import { dialogueEngine } from '../services/ai/dialogueEngine.js';
import { imageGenerator } from '../services/ai/imageGenerator.js';
import { scriptBuilder } from '../services/scriptBuilder.js';
import { sessionService } from '../services/sessionService.js';
import { characterQueries } from '../db/queries/characters.js';
import { sceneQueries } from '../db/queries/scenes.js';
import { sessionQueries } from '../db/queries/sessions.js';
import logger from '../utils/logger.js';

export const gameplayController = {
  async handleChoice(req, res) {
    try {
      const { id } = req.params;
      const { text, consequence } = req.body;

      const aiOutput = await dialogueEngine.processPlayerAction(id, {
        type: 'choice',
        text,
        consequence,
      });

      const result = await processAiResponse(id, aiOutput);
      res.json(result);
    } catch (err) {
      logger.error('Choice handling error:', err);
      res.status(500).json({ error: err.message });
    }
  },

  async handleFreeInput(req, res) {
    try {
      const { id } = req.params;
      const { text } = req.body;

      const aiOutput = await dialogueEngine.processPlayerAction(id, {
        type: 'free-input',
        text,
      });

      const result = await processAiResponse(id, aiOutput);
      res.json(result);
    } catch (err) {
      logger.error('Free input handling error:', err);
      res.status(500).json({ error: err.message });
    }
  },

  getScript(req, res) {
    const script = scriptBuilder.loadScript(req.params.id);
    res.json(script);
  },
};

async function processAiResponse(sessionId, aiOutput) {
  const session = sessionService.getById(sessionId);

  // Handle new character introduction
  let newCharacter = null;
  if (aiOutput.newCharacterIntroduced) {
    const charData = aiOutput.newCharacterIntroduced;
    const charId = charData.id || charData.name.toLowerCase().replace(/\s+/g, '_');

    characterQueries.insert(sessionId, {
      id: charId,
      name: charData.name,
      color: charData.color || '#FFFFFF',
      role: charData.role || 'supporting',
      personality: charData.personality,
      appearance: charData.appearance,
      backstory: '',
      relationship: '',
      speech_style: charData.speechStyle || '',
      quirks: [],
      is_dynamic: 1,
    });

    // Generate neutral sprite synchronously
    await imageGenerator.generateSingleSprite(
      sessionId,
      { id: charId, name: charData.name, appearance: charData.appearance },
      'neutral',
      session.setup_art_style
    );

    // Queue remaining sprites in background (fire-and-forget)
    generateRemainingSprites(sessionId, charId, charData, session.setup_art_style);

    newCharacter = { id: charId, name: charData.name, color: charData.color || '#FFFFFF' };
  }

  // Handle new scene
  let newScene = null;
  if (aiOutput.sceneChangeNeeded) {
    const sceneData = aiOutput.sceneChangeNeeded;
    sceneQueries.insert(sessionId, {
      id: sceneData.id,
      name: sceneData.name,
      description: sceneData.description,
      narrative_context: 'Dynamic scene',
      is_dynamic: 1,
    });

    // Generate background
    await imageGenerator.generateBackground(
      sessionId,
      sceneData,
      session.setup_art_style
    );
    sceneQueries.markImageGenerated(sessionId, sceneData.id);
    sessionQueries.updateCurrentScene(sessionId, sceneData.id);

    newScene = { id: sceneData.id, name: sceneData.name };
  }

  // Build Monogatari script label
  const { labelName, statements, extraLabels } = scriptBuilder.buildRuntimeLabel(aiOutput);

  // Save all labels to DB
  scriptBuilder.saveLabel(sessionId, labelName, statements);
  for (const [name, stmts] of Object.entries(extraLabels)) {
    scriptBuilder.saveLabel(sessionId, name, stmts);
  }

  // If the AI emitted scene_change statements to existing scenes, pin the latest as current.
  const aiStatements = Array.isArray(aiOutput.statements) ? aiOutput.statements : [];
  const lastSceneSwitch = [...aiStatements].reverse().find((s) => s && s.type === 'scene_change' && s.sceneId);
  if (lastSceneSwitch) {
    sessionQueries.updateCurrentScene(sessionId, lastSceneSwitch.sceneId);
  }

  // Update session current label (resets statement_index too)
  sessionQueries.updateCurrentLabel(sessionId, labelName);

  return {
    newLabel: labelName,
    statements,
    extraLabels,
    choices: aiOutput.choices || [],
    allowFreeInput: aiOutput.allowFreeInput || false,
    newCharacter,
    newScene,
  };
}

async function generateRemainingSprites(sessionId, charId, charData, artStyle) {
  const expressions = [
    'happy', 'sad', 'angry', 'surprised', 'embarrassed',
    'thinking', 'scared', 'determined', 'smug',
  ];

  for (const expr of expressions) {
    try {
      await imageGenerator.generateSingleSprite(
        sessionId,
        { id: charId, name: charData.name, appearance: charData.appearance },
        expr,
        artStyle
      );
    } catch (err) {
      logger.error(`Failed to generate ${expr} sprite for ${charId}:`, err.message);
    }
  }
  characterQueries.markSpritesGenerated(sessionId, charId);
  logger.info(`All sprites generated for dynamic character ${charId}`);
}
