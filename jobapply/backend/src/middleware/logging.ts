import type { Express, NextFunction, Request, Response } from 'express';

export function setupLogging(app: Express) {
  app.use((req: Request, _res: Response, next: NextFunction) => {
    const start = Date.now();
    const requestId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    _res.once('finish', () => {
      const ms = Date.now() - start;
      console.log(`[${requestId}] ${req.method} ${req.path} ${_res.statusCode} ${ms}ms`);
    });
    next();
  });
}
