import dotenv from 'dotenv';
import path from 'path';
import { fileURLToPath } from 'url';

dotenv.config({ path: path.resolve(fileURLToPath(import.meta.url), '../../../.env') });

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default {
  GEMINI_API_KEY: process.env.GEMINI_API_KEY,
  PORT: parseInt(process.env.PORT_SERVER || '3001', 10),
  DATA_DIR: path.resolve(__dirname, '../data'),
  DB_PATH: path.resolve(__dirname, '../data/storyplex.db'),
  GENERATED_DIR: path.resolve(__dirname, '../data/generated'),

  models: {
    storyPro: 'gemini-2.5-pro',
    dialogueFlash: 'gemini-2.5-flash',
    imageGen: 'gemini-2.5-flash-image',
  },
};
