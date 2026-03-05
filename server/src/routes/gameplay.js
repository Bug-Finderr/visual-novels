import { Router } from 'express';
import { gameplayController } from '../controllers/gameplayController.js';

const router = Router();

router.post('/:id/choice', gameplayController.handleChoice);
router.post('/:id/free-input', gameplayController.handleFreeInput);
router.get('/:id/script', gameplayController.getScript);

export default router;
