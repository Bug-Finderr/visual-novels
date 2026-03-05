import { storyGenerator } from '../services/ai/storyGenerator.js';
import { imageGenerator } from '../services/ai/imageGenerator.js';
import { scriptBuilder } from '../services/scriptBuilder.js';
import { sessionService } from '../services/sessionService.js';
import { characterQueries } from '../db/queries/characters.js';
import { sceneQueries } from '../db/queries/scenes.js';
import logger from '../utils/logger.js';

// In-memory progress store (sessionId -> progress data)
const progressStore = new Map();

export const generationController = {
  async startGeneration(req, res) {
    const { id } = req.params;
    const session = sessionService.getById(id);
    if (!session) return res.status(404).json({ error: 'Session not found' });
    if (session.status !== 'created' && session.status !== 'error') {
      return res.status(400).json({ error: `Session status is '${session.status}', expected 'created'` });
    }

    sessionService.updateStatus(id, 'generating');
    progressStore.set(id, { step: 'starting', progress: 0, details: 'Starting generation...' });

    res.json({ status: 'started', sessionId: id });

    // Fire off async generation pipeline
    generatePipeline(id, session).catch((err) => {
      logger.error('Generation pipeline failed:', err);
      sessionService.updateStatus(id, 'error');
      progressStore.set(id, { step: 'error', progress: 0, details: err.message });
    });
  },

  streamProgress(req, res) {
    const { id } = req.params;
    res.writeHead(200, {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      Connection: 'keep-alive',
    });

    const interval = setInterval(() => {
      const progress = progressStore.get(id);
      if (progress) {
        res.write(`data: ${JSON.stringify(progress)}\n\n`);
        if (progress.step === 'done' || progress.step === 'error') {
          clearInterval(interval);
          res.end();
          // Clean up after a delay
          setTimeout(() => progressStore.delete(id), 30000);
        }
      }
    }, 500);

    req.on('close', () => {
      clearInterval(interval);
    });
  },
};

async function generatePipeline(sessionId, session) {
  const setup = {
    genre: session.setup_genre,
    artStyle: session.setup_art_style,
    setting: session.setup_setting,
    protagonistName: session.setup_protagonist_name,
    protagonistPersonality: session.setup_protagonist_personality,
    tone: session.setup_tone,
    premise: session.setup_premise,
  };

  // Step 1: Generate world + characters + plot
  progressStore.set(sessionId, {
    step: 'story',
    progress: 5,
    details: 'Generating world, characters, and story...',
  });

  const storyData = await storyGenerator.generateWorld(setup);
  sessionService.saveStoryData(sessionId, storyData);

  progressStore.set(sessionId, {
    step: 'story_done',
    progress: 20,
    details: `World "${storyData.worldLore.name}" created with ${storyData.characters.length} characters`,
  });

  // Step 2: Generate character sprites
  const totalCharacters = storyData.characters.length;
  const totalExpressions = totalCharacters * 10;
  let generatedExpressions = 0;

  for (let ci = 0; ci < totalCharacters; ci++) {
    const character = storyData.characters[ci];
    await imageGenerator.generateCharacterSprites(
      sessionId,
      character,
      setup.artStyle,
      (expr, current, total) => {
        generatedExpressions++;
        const spriteProgress = 20 + (generatedExpressions / totalExpressions) * 50;
        progressStore.set(sessionId, {
          step: 'sprites',
          progress: Math.round(spriteProgress),
          details: `Generating ${character.name} - ${expr} (${generatedExpressions}/${totalExpressions})`,
          characterIndex: ci,
          characterName: character.name,
          expression: expr,
        });
      }
    );
    characterQueries.markSpritesGenerated(sessionId, character.id);
  }

  // Step 3: Generate background scenes
  const totalScenes = storyData.initialScenes.length;
  for (let si = 0; si < totalScenes; si++) {
    const scene = storyData.initialScenes[si];
    progressStore.set(sessionId, {
      step: 'backgrounds',
      progress: 70 + ((si + 1) / totalScenes) * 20,
      details: `Generating background: ${scene.name} (${si + 1}/${totalScenes})`,
    });
    await imageGenerator.generateBackground(sessionId, scene, setup.artStyle);
    sceneQueries.markImageGenerated(sessionId, scene.id);
  }

  // Step 4: Build initial Monogatari script
  progressStore.set(sessionId, {
    step: 'script',
    progress: 92,
    details: 'Building game script...',
  });

  const script = scriptBuilder.buildInitialScript(storyData);
  for (const [labelName, statements] of Object.entries(script)) {
    scriptBuilder.saveLabel(sessionId, labelName, statements);
  }

  // Step 5: Mark ready
  sessionService.updateStatus(sessionId, 'ready');
  progressStore.set(sessionId, {
    step: 'done',
    progress: 100,
    details: 'Generation complete! Your story is ready.',
  });

  logger.info(`Generation complete for session ${sessionId}`);
}
