import { removeBackground } from '@imgly/background-removal-node';
import sharp from 'sharp';
import { fileURLToPath } from 'url';
import path from 'path';
import logger from '../utils/logger.js';

// Resolve the actual dist/ folder (handles npm workspace hoisting)
const entryUrl = import.meta.resolve('@imgly/background-removal-node');
const distDir = path.dirname(fileURLToPath(entryUrl));
const publicPath = `file://${distDir}/`;

/**
 * Remove background from a character sprite image buffer.
 * Returns a PNG buffer with transparent background.
 */
export async function removeSpriteBg(imageBuffer) {
  try {
    logger.info('Removing background from sprite...');

    // @imgly/background-removal-node expects a Blob or ArrayBuffer
    const blob = new Blob([imageBuffer], { type: 'image/png' });
    const result = await removeBackground(blob, {
      publicPath,
      output: { format: 'image/png', quality: 1 },
    });

    // Convert result Blob to Buffer
    const arrayBuffer = await result.arrayBuffer();
    const outputBuffer = Buffer.from(arrayBuffer);

    // Use sharp to ensure clean PNG with alpha channel
    const finalBuffer = await sharp(outputBuffer)
      .png({ quality: 100 })
      .toBuffer();

    logger.info('Background removed successfully');
    return finalBuffer;
  } catch (err) {
    logger.error('Background removal failed, returning original image:', err.message);
    return imageBuffer;
  }
}
