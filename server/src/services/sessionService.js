import { v4 as uuidv4 } from 'uuid';
import { sessionQueries } from '../db/queries/sessions.js';
import { characterQueries } from '../db/queries/characters.js';
import { sceneQueries } from '../db/queries/scenes.js';
import { assetManager } from './assetManager.js';

export const sessionService = {
  create(setupData) {
    const id = uuidv4();
    const title = `${setupData.genre} - ${setupData.setting.slice(0, 40)}`;
    sessionQueries.create({
      id,
      title,
      status: 'created',
      setup_genre: setupData.genre,
      setup_art_style: setupData.artStyle,
      setup_setting: setupData.setting,
      setup_protagonist_name: setupData.protagonistName,
      setup_protagonist_personality: setupData.protagonistPersonality,
      setup_tone: setupData.tone,
      setup_premise: setupData.premise || null,
    });
    return { id, title };
  },

  getAll() {
    return sessionQueries.getAll();
  },

  getById(id) {
    const session = sessionQueries.getById(id);
    if (!session) return null;
    return {
      ...session,
      world_lore: session.world_lore ? JSON.parse(session.world_lore) : null,
      plot_arc: session.plot_arc ? JSON.parse(session.plot_arc) : null,
    };
  },

  async delete(id) {
    await assetManager.deleteSessionAssets(id);
    sessionQueries.delete(id);
  },

  updateStatus(id, status) {
    sessionQueries.updateStatus(id, status);
  },

  saveStoryData(id, storyData) {
    // Save world lore and plot arc to session
    sessionQueries.saveStoryData(id, {
      worldLore: storyData.worldLore,
      plotArc: storyData.plotArc,
    });

    // Save characters
    for (const char of storyData.characters) {
      characterQueries.insert(id, {
        id: char.id,
        name: char.name,
        color: char.color || '#FFFFFF',
        role: char.role,
        personality: char.personality,
        appearance: char.appearance,
        backstory: char.backstory,
        relationship: char.relationshipToProtagonist,
        speech_style: char.speechStyle,
        quirks: char.quirks || [],
      });
    }

    // Save scenes
    for (const scene of storyData.initialScenes) {
      sceneQueries.insert(id, {
        id: scene.id,
        name: scene.name,
        description: scene.description,
        narrative_context: scene.narrativeContext,
      });
    }

    // Set the first scene as current
    if (storyData.initialScenes.length > 0) {
      sessionQueries.updateCurrentScene(id, storyData.initialScenes[0].id);
    }
  },

  patch(id, fields) {
    sessionQueries.patch(id, fields);
  },

  getCharacters(id) {
    return characterQueries.getBySession(id).map((c) => ({
      ...c,
      quirks: JSON.parse(c.quirks || '[]'),
    }));
  },

  getScenes(id) {
    return sceneQueries.getBySession(id);
  },
};
