import fs from 'node:fs';
import path from 'node:path';
import express, { type ErrorRequestHandler } from 'express';
import cors from 'cors';
import { FRONTEND_DIST, NODE_ENV } from './config.js';
import { ensureApplicationsCsv } from './services/applicationsStore.js';
import { applicationsRouter } from './routes/applications.js';
import { filtersRouter } from './routes/filters.js';
import { botRouter } from './routes/bot.js';
import { statusRouter } from './routes/status.js';
import { setupLogging } from './middleware/logging.js';

export function createApp() {
  ensureApplicationsCsv();

  const app = express();
  app.disable('x-powered-by');
  app.use(cors());
  app.use(express.json({ limit: '10mb' }));
  setupLogging(app);

  app.get('/health', (_req, res) => {
    res.json({ status: 'ok', timestamp: new Date().toISOString() });
  });

  app.use('/api/applications', applicationsRouter);
  app.use('/api/filters', filtersRouter);
  app.use('/api/bot', botRouter);
  app.use('/api/status', statusRouter);

  const frontendIndex = path.join(FRONTEND_DIST, 'index.html');
  if (NODE_ENV === 'production' && fs.existsSync(frontendIndex)) {
    app.use(express.static(FRONTEND_DIST));
    app.get('*', (req, res, next) => {
      if (req.path.startsWith('/api/')) {
        next();
        return;
      }
      res.sendFile(frontendIndex);
    });
  }

  const errorHandler: ErrorRequestHandler = (error, _req, res, _next) => {
    const message = error instanceof Error ? error.message : 'Unexpected server error';
    console.error('[jobapply] Request failed:', error);
    if (!res.headersSent) {
      res.status(500).json({ error: message });
    }
  };
  app.use(errorHandler);

  return app;
}

export default createApp();
