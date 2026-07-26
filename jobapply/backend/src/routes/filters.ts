import { Router } from 'express';
import fs from 'node:fs';
import path from 'node:path';
import { FILTERS_DIR } from '../config.js';

export const filtersRouter = Router();

const SAFE_FILTER_NAME = /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/;

function filterPath(name: string): string | undefined {
  if (!SAFE_FILTER_NAME.test(name)) return undefined;
  const candidate = path.resolve(FILTERS_DIR, `${name}.json`);
  const relative = path.relative(FILTERS_DIR, candidate);
  if (relative.startsWith('..') || path.isAbsolute(relative)) return undefined;
  return candidate;
}

filtersRouter.get('/', (_req, res) => {
  try {
    if (!fs.existsSync(FILTERS_DIR)) {
      res.json([]);
      return;
    }
    const files = fs.readdirSync(FILTERS_DIR)
      .filter((file) => file.endsWith('.json'))
      .map((file) => file.slice(0, -'.json'.length))
      .filter((name) => SAFE_FILTER_NAME.test(name))
      .sort()
      .map((name) => ({
        name,
        data: JSON.parse(fs.readFileSync(filterPath(name) as string, 'utf8')),
      }));
    res.json(files);
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Failed to read filters';
    res.status(500).json({ error: message });
  }
});

filtersRouter.get('/:name', (req, res) => {
  const filePath = filterPath(req.params.name);
  if (!filePath) {
    res.status(400).json({ error: 'Invalid filter name' });
    return;
  }
  if (!fs.existsSync(filePath)) {
    res.status(404).json({ error: 'Filter not found' });
    return;
  }

  try {
    res.json(JSON.parse(fs.readFileSync(filePath, 'utf8')));
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Failed to read filter';
    res.status(500).json({ error: message });
  }
});

filtersRouter.post('/:name', (req, res) => {
  const filePath = filterPath(req.params.name);
  if (!filePath) {
    res.status(400).json({ error: 'Invalid filter name' });
    return;
  }
  if (!req.body || typeof req.body !== 'object' || Array.isArray(req.body)) {
    res.status(400).json({ error: 'Filter must be a JSON object' });
    return;
  }

  try {
    fs.mkdirSync(FILTERS_DIR, { recursive: true });
    fs.writeFileSync(filePath, `${JSON.stringify(req.body, null, 2)}\n`, 'utf8');
    res.json({ success: true, name: req.params.name });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Failed to save filter';
    res.status(500).json({ error: message });
  }
});
