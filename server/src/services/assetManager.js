import path from 'path';
import config from '../config.js';
import { writeFile, ensureDir, removeDir, fileExists } from '../utils/fileUtils.js';

export const assetManager = {
  async saveCharacterSprite(sessionId, characterId, expression, imageBuffer) {
    const filePath = this.getCharacterSpritePath(sessionId, characterId, expression);
    await writeFile(filePath, imageBuffer);
    return filePath;
  },

  async saveBackground(sessionId, sceneId, imageBuffer) {
    const filePath = this.getBackgroundPath(sessionId, sceneId);
    await writeFile(filePath, imageBuffer);
    return filePath;
  },

  getCharacterSpritePath(sessionId, characterId, expression) {
    return path.join(config.GENERATED_DIR, sessionId, 'characters', characterId, `${expression}.png`);
  },

  getBackgroundPath(sessionId, sceneId) {
    return path.join(config.GENERATED_DIR, sessionId, 'backgrounds', `${sceneId}.png`);
  },

  async sessionAssetsExist(sessionId) {
    const dir = path.join(config.GENERATED_DIR, sessionId);
    return fileExists(dir);
  },

  async deleteSessionAssets(sessionId) {
    const dir = path.join(config.GENERATED_DIR, sessionId);
    await removeDir(dir);
  },

  async ensureSessionDir(sessionId) {
    const dir = path.join(config.GENERATED_DIR, sessionId);
    await ensureDir(dir);
  },
};
