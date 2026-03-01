import { getDb } from '../database.js';

export const characterQueries = {
  insert(sessionId, character) {
    const db = getDb();
    return db.prepare(`
      INSERT INTO characters (id, session_id, name, color, role, personality, appearance,
        backstory, relationship, speech_style, quirks, is_dynamic)
      VALUES (@id, @session_id, @name, @color, @role, @personality, @appearance,
        @backstory, @relationship, @speech_style, @quirks, @is_dynamic)
    `).run({
      session_id: sessionId,
      color: '#FFFFFF',
      is_dynamic: 0,
      ...character,
      quirks: JSON.stringify(character.quirks || []),
    });
  },

  getBySession(sessionId) {
    const db = getDb();
    return db.prepare('SELECT * FROM characters WHERE session_id = ?').all(sessionId);
  },

  getById(sessionId, characterId) {
    const db = getDb();
    return db.prepare('SELECT * FROM characters WHERE session_id = ? AND id = ?')
      .get(sessionId, characterId);
  },

  markSpritesGenerated(sessionId, characterId) {
    const db = getDb();
    return db.prepare(`
      UPDATE characters SET sprites_generated = 1 WHERE session_id = ? AND id = ?
    `).run(sessionId, characterId);
  },
};
