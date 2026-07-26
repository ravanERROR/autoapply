import { Router } from 'express';

export const statusRouter = Router();

statusRouter.get('/', (_req, res) => {
  res.json({
    uptime: process.uptime(),
    memory: process.memoryUsage(),
    environment: process.env.NODE_ENV,
    timestamp: new Date().toISOString(),
  });
});
