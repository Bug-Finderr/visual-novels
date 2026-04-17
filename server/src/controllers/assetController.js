import path from 'path';
import config from '../config.js';

const SAFE_FILENAME = /^[a-zA-Z0-9_-]+\.(png|jpg|jpeg|webp)$/;
const SAFE_ID = /^[a-zA-Z0-9_-]+$/;

function reject(res, reason) {
  return res.status(400).json({ error: reason });
}

export const assetController = {
  serveCharacterSprite(req, res) {
    const { sessionId, characterId, filename } = req.params;
    if (!SAFE_ID.test(sessionId)) return reject(res, 'invalid sessionId');
    if (!SAFE_ID.test(characterId)) return reject(res, 'invalid characterId');
    if (!SAFE_FILENAME.test(filename)) return reject(res, 'invalid filename');

    const base = path.resolve(config.GENERATED_DIR, sessionId, 'characters', characterId);
    const filePath = path.resolve(base, filename);
    if (!filePath.startsWith(base + path.sep)) return reject(res, 'invalid path');

    res.sendFile(filePath, (err) => {
      if (err) res.status(404).json({ error: 'Sprite not found' });
    });
  },

  serveBackground(req, res) {
    const { sessionId, filename } = req.params;
    if (!SAFE_ID.test(sessionId)) return reject(res, 'invalid sessionId');
    if (!SAFE_FILENAME.test(filename)) return reject(res, 'invalid filename');

    const base = path.resolve(config.GENERATED_DIR, sessionId, 'backgrounds');
    const filePath = path.resolve(base, filename);
    if (!filePath.startsWith(base + path.sep)) return reject(res, 'invalid path');

    res.sendFile(filePath, (err) => {
      if (err) res.status(404).json({ error: 'Background not found' });
    });
  },
};
