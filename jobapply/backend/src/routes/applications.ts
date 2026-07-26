import { Router } from 'express';
import { randomUUID } from 'node:crypto';
import {
  appendApplication,
  clearApplications,
  ensureApplicationsCsv,
  getApplicationsCsvPath,
  readApplications,
  type ApplicationRecord,
} from '../services/applicationsStore.js';

const PLATFORMS = new Set(['linkedin', 'naukri', 'indeed', 'glassdoor', 'foundit']);
const APPLICATION_STATUSES = new Set(['applied', 'pending', 'failed', 'skipped']);

type ValidationResult =
  | { application: ApplicationRecord; errors?: never }
  | { application?: never; errors: string[] };

function validateApplication(body: unknown): ValidationResult {
  if (!body || typeof body !== 'object' || Array.isArray(body)) {
    return { errors: ['Request body must be a JSON object'] };
  }

  const input = body as Record<string, unknown>;
  const errors: string[] = [];
  const platform = input.platform;
  const jobTitle = input.jobTitle;
  const status = input.status;

  if (typeof platform !== 'string' || !PLATFORMS.has(platform)) {
    errors.push(`platform must be one of: ${Array.from(PLATFORMS).join(', ')}`);
  }
  if (typeof jobTitle !== 'string' || jobTitle.trim().length === 0) {
    errors.push('jobTitle must be a non-empty string');
  }
  if (typeof status !== 'string' || !APPLICATION_STATUSES.has(status)) {
    errors.push(`status must be one of: ${Array.from(APPLICATION_STATUSES).join(', ')}`);
  }

  for (const field of ['company', 'location', 'jobUrl', 'notes'] as const) {
    if (input[field] !== undefined && typeof input[field] !== 'string') {
      errors.push(`${field} must be a string`);
    }
  }

  if (errors.length > 0) return { errors };

  const timestamp = new Date().toISOString();
  return {
    application: {
      id: randomUUID(),
      timestamp,
      platform: platform as string,
      jobTitle: (jobTitle as string).trim(),
      company: (input.company as string | undefined) ?? '',
      location: (input.location as string | undefined) ?? '',
      jobUrl: (input.jobUrl as string | undefined) ?? '',
      status: status as string,
      appliedAt: timestamp,
      notes: (input.notes as string | undefined) ?? '',
    },
  };
}

export const applicationsRouter = Router();

applicationsRouter.get('/', (_req, res) => {
  try {
    res.json(readApplications());
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Failed to read applications';
    res.status(500).json({ error: message });
  }
});

applicationsRouter.get('/export', (_req, res) => {
  try {
    ensureApplicationsCsv();
    res.setHeader('Content-Type', 'text/csv; charset=utf-8');
    res.setHeader('Content-Disposition', 'attachment; filename="applications.csv"');
    res.sendFile(getApplicationsCsvPath());
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Failed to export applications';
    res.status(500).json({ error: message });
  }
});

applicationsRouter.post('/log', (req, res) => {
  const validation = validateApplication(req.body);
  if (validation.errors) {
    res.status(400).json({ error: 'Invalid application', details: validation.errors });
    return;
  }

  try {
    appendApplication(validation.application);
    res.json({
      success: true,
      id: validation.application.id,
      timestamp: validation.application.timestamp,
      application: validation.application,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Failed to persist application';
    res.status(500).json({ error: message });
  }
});

applicationsRouter.delete('/clear', (_req, res) => {
  try {
    clearApplications();
    res.json({ success: true });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Failed to clear applications';
    res.status(500).json({ error: message });
  }
});
