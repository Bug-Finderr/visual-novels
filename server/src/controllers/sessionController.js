import { sessionService } from '../services/sessionService.js';
import { sessionQueries } from '../db/queries/sessions.js';
import { playedStatementsQueries } from '../db/queries/playedStatements.js';

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

  updatePosition(req, res) {
    const { id } = req.params;
    const { label, index } = req.body;
    if (typeof label !== 'string' || typeof index !== 'number') {
      return res.status(400).json({ error: 'label (string) and index (number) required' });
    }
    const session = sessionQueries.getById(id);
    if (!session) return res.status(404).json({ error: 'Session not found' });
    sessionQueries.updatePosition(id, label, index);
    res.json({ ok: true });
  },

  recordPlayed(req, res) {
    const { id } = req.params;
    const { kind, speakerId, speaker, text, labelName } = req.body;
    if (!text || typeof text !== 'string') {
      return res.status(400).json({ error: 'text required' });
    }
    const validKinds = ['narration', 'dialogue', 'player_choice', 'player_input'];
    if (!validKinds.includes(kind)) {
      return res.status(400).json({ error: `kind must be one of ${validKinds.join(', ')}` });
    }
    playedStatementsQueries.insert(id, {
      kind,
      speakerId: speakerId || null,
      speaker: speaker || null,
      text: text.slice(0, 4000),
      labelName: labelName || null,
    });
    res.status(201).json({ ok: true });
  },

  getHistory(req, res) {
    const rows = playedStatementsQueries.getAll(req.params.id);
    res.json(rows);
  },
};
