import { Router } from 'express';
import { generationController } from '../controllers/generationController.js';

const router = Router();

router.post('/:id/generate', generationController.startGeneration);
router.get('/:id/generate/status', generationController.streamProgress);

export default router;
