import { getDb } from '../database.js';

export const playedStatementsQueries = {
  insert(sessionId, { kind, speakerId = null, speaker = null, text, labelName = null }) {
    const db = getDb();
    return db.prepare(`
      INSERT INTO played_statements (session_id, kind, speaker_id, speaker, text, label_name)
      VALUES (?, ?, ?, ?, ?, ?)
    `).run(sessionId, kind, speakerId, speaker, text, labelName);
  },

  getAll(sessionId) {
    const db = getDb();
    return db.prepare(`
      SELECT id, kind, speaker_id, speaker, text, label_name, created_at
      FROM played_statements
      WHERE session_id = ?
      ORDER BY id ASC
    `).all(sessionId);
  },

  deleteBySession(sessionId) {
    const db = getDb();
    return db.prepare('DELETE FROM played_statements WHERE session_id = ?').run(sessionId);
  },
};
