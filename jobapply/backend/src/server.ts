import path from 'node:path';
import { fileURLToPath } from 'node:url';
import type { Server } from 'node:http';
import app from './app.js';
import { PORT } from './config.js';
import { shutdownBots } from './routes/bot.js';

let server: Server | undefined;
let shuttingDown = false;

export function startServer(port = PORT): Server {
  server = app.listen(port, () => {
    const address = server?.address();
    const listeningPort = typeof address === 'object' && address ? address.port : port;
    console.log(`[jobapply] Backend running on http://localhost:${listeningPort}`);
  });

  const gracefulShutdown = async (signal: NodeJS.Signals) => {
    if (shuttingDown) return;
    shuttingDown = true;
    console.log(`[jobapply] ${signal} received; shutting down...`);

    const forceExitTimer = setTimeout(() => {
      console.error('[jobapply] Graceful shutdown timed out');
      server?.closeAllConnections?.();
      process.exit(1);
    }, 10_000);
    forceExitTimer.unref();

    const closeServer = new Promise<void>((resolve, reject) => {
      server?.close((error) => error ? reject(error) : resolve());
    });

    const results = await Promise.allSettled([closeServer, shutdownBots()]);
    clearTimeout(forceExitTimer);
    const failed = results.some((result) => result.status === 'rejected');
    if (failed) {
      for (const result of results) {
        if (result.status === 'rejected') console.error('[jobapply] Shutdown error:', result.reason);
      }
    }
    process.exit(failed ? 1 : 0);
  };

  process.once('SIGINT', () => void gracefulShutdown('SIGINT'));
  process.once('SIGTERM', () => void gracefulShutdown('SIGTERM'));
  return server;
}

const currentFile = path.resolve(fileURLToPath(import.meta.url));
const entryFile = process.argv[1] ? path.resolve(process.argv[1]) : '';
if (currentFile === entryFile) {
  startServer();
}

export default app;
