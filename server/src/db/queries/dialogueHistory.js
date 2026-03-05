import { getDb } from '../database.js';

export const dialogueHistoryQueries = {
  insert(sessionId, role, content, labelContext = null) {
    const db = getDb();
    return db.prepare(`
      INSERT INTO dialogue_history (session_id, role, content, label_context)
      VALUES (?, ?, ?, ?)
    `).run(sessionId, role, content, labelContext);
  },

  getRecent(sessionId, limit = 50) {
    const db = getDb();
    return db.prepare(`
      SELECT role, content, label_context, created_at
      FROM dialogue_history
      WHERE session_id = ?
      ORDER BY created_at DESC
      LIMIT ?
    `).all(sessionId, limit).reverse();
  },

  getAll(sessionId) {
    const db = getDb();
    return db.prepare(`
      SELECT role, content, label_context, created_at
      FROM dialogue_history
      WHERE session_id = ?
      ORDER BY created_at ASC
    `).all(sessionId);
  },

  deleteBySession(sessionId) {
    const db = getDb();
    return db.prepare('DELETE FROM dialogue_history WHERE session_id = ?').run(sessionId);
  },
};
