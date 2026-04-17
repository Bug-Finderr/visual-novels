import logger from '../utils/logger.js';

export function errorHandler(err, req, res, _next) {
  logger.error(`${req.method} ${req.path} failed:`, err);
  const status = err.status || 500;
  const isClientErr = status >= 400 && status < 500;
  res.status(status).json({
    error: isClientErr ? err.message || 'Bad request' : 'Internal server error',
  });
}
