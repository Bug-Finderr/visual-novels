import { Router } from 'express';
import { sessionController } from '../controllers/sessionController.js';
import { validateBody } from '../middleware/validateRequest.js';

const router = Router();

router.post(
  '/',
  validateBody(['genre', 'artStyle', 'setting', 'protagonistName', 'protagonistPersonality', 'tone']),
  sessionController.create
);
router.get('/', sessionController.getAll);
router.get('/:id', sessionController.getById);
router.delete('/:id', sessionController.delete);
router.patch('/:id', sessionController.patch);
router.get('/:id/characters', sessionController.getCharacters);
router.get('/:id/scenes', sessionController.getScenes);
router.post('/:id/position', sessionController.updatePosition);
router.post('/:id/played', sessionController.recordPlayed);
router.get('/:id/history', sessionController.getHistory);

export default router;
