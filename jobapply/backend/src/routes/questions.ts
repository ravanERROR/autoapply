import { Router } from 'express';
import fs from 'node:fs';
import path from 'node:path';
import { QUESTIONS_JSON } from '../config.js';

export const questionsRouter = Router();

function readQuestions(): Record<string, string> {
  if (!fs.existsSync(QUESTIONS_JSON)) {
    return {};
  }
  try {
    const content = fs.readFileSync(QUESTIONS_JSON, 'utf8');
    return JSON.parse(content);
  } catch (error) {
    return {};
  }
}

function writeQuestions(data: Record<string, string>): void {
  fs.mkdirSync(path.dirname(QUESTIONS_JSON), { recursive: true });
  fs.writeFileSync(QUESTIONS_JSON, `${JSON.stringify(data, null, 2)}\n`, 'utf8');
}

// GET /api/questions -> Returns full questions database
questionsRouter.get('/', (_req, res) => {
  try {
    res.json(readQuestions());
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Failed to read questions database';
    res.status(500).json({ error: message });
  }
});

// POST /api/questions -> Upsert single or multiple question-answer pairs
questionsRouter.post('/', (req, res) => {
  if (!req.body || typeof req.body !== 'object' || Array.isArray(req.body)) {
    res.status(400).json({ error: 'Request body must be a JSON object containing question-answer pairs' });
    return;
  }

  try {
    const existing = readQuestions();
    const updated = { ...existing, ...req.body };
    writeQuestions(updated);
    res.json({ success: true, count: Object.keys(updated).length });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Failed to update questions database';
    res.status(500).json({ error: message });
  }
});
