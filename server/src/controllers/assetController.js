import path from 'path';
import config from '../config.js';

export const assetController = {
  serveCharacterSprite(req, res) {
    const { sessionId, characterId, filename } = req.params;
    const filePath = path.join(
      config.GENERATED_DIR, sessionId, 'characters', characterId, filename
    );
    res.sendFile(filePath, (err) => {
      if (err) res.status(404).json({ error: 'Sprite not found' });
    });
  },

  serveBackground(req, res) {
    const { sessionId, filename } = req.params;
    const filePath = path.join(
      config.GENERATED_DIR, sessionId, 'backgrounds', filename
    );
    res.sendFile(filePath, (err) => {
      if (err) res.status(404).json({ error: 'Background not found' });
    });
  },
};
