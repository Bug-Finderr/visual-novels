import { getDb } from '../database.js';

export const sessionQueries = {
  create(session) {
    const db = getDb();
    return db.prepare(`
      INSERT INTO sessions (id, title, status, setup_genre, setup_art_style, setup_setting,
        setup_protagonist_name, setup_protagonist_personality, setup_tone, setup_premise)
      VALUES (@id, @title, @status, @setup_genre, @setup_art_style, @setup_setting,
        @setup_protagonist_name, @setup_protagonist_personality, @setup_tone, @setup_premise)
    `).run(session);
  },

  getAll() {
    const db = getDb();
    return db.prepare(`
      SELECT id, title, status, setup_genre, setup_art_style, setup_tone,
        created_at, updated_at, last_played_at
      FROM sessions ORDER BY updated_at DESC
    `).all();
  },

  getById(id) {
    const db = getDb();
    return db.prepare('SELECT * FROM sessions WHERE id = ?').get(id);
  },

  updateStatus(id, status) {
    const db = getDb();
    return db.prepare(`
      UPDATE sessions SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?
    `).run(status, id);
  },

  saveStoryData(id, { worldLore, plotArc }) {
    const db = getDb();
    return db.prepare(`
      UPDATE sessions
      SET world_lore = ?, plot_arc = ?, updated_at = CURRENT_TIMESTAMP
      WHERE id = ?
    `).run(JSON.stringify(worldLore), JSON.stringify(plotArc), id);
  },

  updateCurrentScene(id, sceneId) {
    const db = getDb();
    return db.prepare(`
      UPDATE sessions SET current_scene_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?
    `).run(sceneId, id);
  },

  updateCurrentLabel(id, label) {
    const db = getDb();
    return db.prepare(`
      UPDATE sessions SET current_label = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?
    `).run(label, id);
  },

  updateLastPlayed(id) {
    const db = getDb();
    return db.prepare(`
      UPDATE sessions SET last_played_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = ?
    `).run(id);
  },

  delete(id) {
    const db = getDb();
    return db.prepare('DELETE FROM sessions WHERE id = ?').run(id);
  },

  patch(id, fields) {
    const db = getDb();
    const allowed = ['title', 'status', 'current_scene_id', 'current_label'];
    const updates = Object.entries(fields)
      .filter(([key]) => allowed.includes(key))
      .map(([key]) => `${key} = @${key}`);
    if (updates.length === 0) return;
    return db.prepare(`
      UPDATE sessions SET ${updates.join(', ')}, updated_at = CURRENT_TIMESTAMP WHERE id = @id
    `).run({ ...fields, id });
  },
};
