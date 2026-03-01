import { sessionService } from '../services/sessionService.js';

export const sessionController = {
  create(req, res) {
    const { genre, artStyle, setting, protagonistName, protagonistPersonality, tone, premise } = req.body;
    const session = sessionService.create({
      genre,
      artStyle,
      setting,
      protagonistName,
      protagonistPersonality,
      tone,
      premise,
    });
    res.status(201).json(session);
  },

  getAll(req, res) {
    const sessions = sessionService.getAll();
    res.json(sessions);
  },

  getById(req, res) {
    const session = sessionService.getById(req.params.id);
    if (!session) return res.status(404).json({ error: 'Session not found' });
    res.json(session);
  },

  async delete(req, res) {
    const session = sessionService.getById(req.params.id);
    if (!session) return res.status(404).json({ error: 'Session not found' });
    await sessionService.delete(req.params.id);
    res.json({ ok: true });
  },

  patch(req, res) {
    const session = sessionService.getById(req.params.id);
    if (!session) return res.status(404).json({ error: 'Session not found' });
    sessionService.patch(req.params.id, req.body);
    res.json({ ok: true });
  },

  getCharacters(req, res) {
    const chars = sessionService.getCharacters(req.params.id);
    res.json(chars);
  },

  getScenes(req, res) {
    const scenes = sessionService.getScenes(req.params.id);
    res.json(scenes);
  },
};
