import path from 'node:path';
import { fileURLToPath } from 'node:url';
import dotenv from 'dotenv';

const moduleDirectory = path.dirname(fileURLToPath(import.meta.url));

/** Absolute repository/application root, independent of the process cwd. */
export const APP_ROOT = path.resolve(moduleDirectory, '..', '..');
export const ROOT_ENV_PATH = path.join(APP_ROOT, '.env');

// This module is a dependency of every route that evaluates environment-backed
// configuration, so the root .env is loaded before those values are read.
dotenv.config({ path: ROOT_ENV_PATH });

function appRootPath(value: string | undefined, fallback: string): string {
  const configuredPath = value?.trim() || fallback;
  return path.resolve(APP_ROOT, configuredPath);
}

function configuredPort(value: string | undefined): number {
  const port = Number(value ?? 5000);
  return Number.isInteger(port) && port >= 0 && port <= 65_535 ? port : 5000;
}

export const PORT = configuredPort(process.env.PORT);
export const NODE_ENV = process.env.NODE_ENV ?? 'development';
export const PYTHON_PATH = process.env.PYTHON_PATH?.trim() || 'python';
export const BOTS_DIR = appRootPath(process.env.BOTS_DIR, 'bots');
export const ORCHESTRATOR_PATH = path.join(BOTS_DIR, 'orchestrator.py');
export const APPLICATIONS_CSV = appRootPath(
  process.env.APPLICATIONS_CSV,
  path.join('logs', 'applications.csv'),
);
export const FILTERS_DIR = appRootPath(
  process.env.FILTERS_DIR,
  path.join('configs', 'filters'),
);
export const QUESTIONS_JSON = appRootPath(
  process.env.QUESTIONS_JSON,
  path.join('configs', 'questions.json'),
);
export const FRONTEND_DIST = appRootPath(
  process.env.FRONTEND_DIST,
  path.join('frontend', 'dist'),
);

