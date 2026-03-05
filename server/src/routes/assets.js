import { Router } from 'express';
import { assetController } from '../controllers/assetController.js';

const router = Router();

router.get('/:sessionId/characters/:characterId/:filename', assetController.serveCharacterSprite);
router.get('/:sessionId/backgrounds/:filename', assetController.serveBackground);

export default router;
