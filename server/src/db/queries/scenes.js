import { getDb } from '../database.js';

export const sceneQueries = {
  insert(sessionId, scene) {
    const db = getDb();
    return db.prepare(`
      INSERT INTO scenes (id, session_id, name, description, narrative_context, is_dynamic)
      VALUES (@id, @session_id, @name, @description, @narrative_context, @is_dynamic)
    `).run({
      session_id: sessionId,
      is_dynamic: 0,
      ...scene,
    });
  },

  getBySession(sessionId) {
    const db = getDb();
    return db.prepare('SELECT * FROM scenes WHERE session_id = ?').all(sessionId);
  },

  getById(sessionId, sceneId) {
    const db = getDb();
    return db.prepare('SELECT * FROM scenes WHERE session_id = ? AND id = ?')
      .get(sessionId, sceneId);
  },

  markImageGenerated(sessionId, sceneId) {
    const db = getDb();
    return db.prepare(`
      UPDATE scenes SET image_generated = 1 WHERE session_id = ? AND id = ?
    `).run(sessionId, sceneId);
  },
};
