import { GoogleGenAI } from '@google/genai';
import config from '../../config.js';
import logger from '../../utils/logger.js';

let _ai = null;

function getAi() {
  if (!_ai) {
    if (!config.GEMINI_API_KEY || config.GEMINI_API_KEY === 'your_api_key_here') {
      throw new Error('GEMINI_API_KEY not set in .env — add your real API key');
    }
    _ai = new GoogleGenAI({ apiKey: config.GEMINI_API_KEY });
    logger.info('Gemini AI client initialized');
  }
  return _ai;
}

// Proxy that lazily initializes the client on first use
export const ai = new Proxy(
  {},
  {
    get(_, prop) {
      return getAi()[prop];
    },
  }
);

export const models = config.models;
