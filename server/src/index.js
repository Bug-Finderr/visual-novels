import express from 'express';
import cors from 'cors';
import config from './config.js';
import { initDatabase } from './db/database.js';
import sessionsRouter from './routes/sessions.js';
import generationRouter from './routes/generation.js';
import gameplayRouter from './routes/gameplay.js';
import assetsRouter from './routes/assets.js';
import { errorHandler } from './middleware/errorHandler.js';

const app = express();

app.use(cors());
app.use(express.json());

// API routes
app.use('/api/sessions', sessionsRouter);
app.use('/api/sessions', generationRouter);
app.use('/api/sessions', gameplayRouter);
app.use('/api/assets', assetsRouter);

// Health check
app.get('/api/health', (req, res) => {
  res.json({ status: 'ok', name: 'storyplex-server' });
});

// Error handler
app.use(errorHandler);

// Initialize database and start server
initDatabase().then(() => {
  app.listen(config.PORT, () => {
    console.log(`Storyplex server running on http://localhost:${config.PORT}`);
  });
}).catch((err) => {
  console.error('Failed to initialize database:', err);
  process.exit(1);
});
