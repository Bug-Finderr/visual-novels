import logger from '../../utils/logger.js';

const TRANSIENT_STATUSES = new Set([408, 429, 500, 502, 503, 504]);

/**
 * Retry an async Gemini call on transient errors (429, 5xx) with exponential backoff.
 * Throws the final error if all attempts fail.
 */
export async function withRetry(fn, { attempts = 4, baseDelayMs = 1500, label = 'gemini' } = {}) {
  let lastErr;
  for (let i = 0; i < attempts; i++) {
    try {
      return await fn();
    } catch (err) {
      const status = err?.status || err?.code;
      const isTransient = status && TRANSIENT_STATUSES.has(Number(status));
      lastErr = err;
      if (!isTransient || i === attempts - 1) throw err;
      const delay = baseDelayMs * Math.pow(2, i) + Math.floor(Math.random() * 500);
      logger.warn(`${label} transient failure (${status}); retrying in ${delay}ms (attempt ${i + 2}/${attempts})`);
      await new Promise((r) => setTimeout(r, delay));
    }
  }
  throw lastErr;
}
