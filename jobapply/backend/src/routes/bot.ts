import fs from 'node:fs';
import { randomUUID } from 'node:crypto';
import { spawn, type ChildProcess } from 'node:child_process';
import { Router } from 'express';
import {
  APPLICATIONS_CSV,
  APP_ROOT,
  BOTS_DIR,
  FILTERS_DIR,
  ORCHESTRATOR_PATH,
  PYTHON_PATH,
} from '../config.js';
import { ensureApplicationsCsv } from '../services/applicationsStore.js';

export const botRouter = Router();

const SUPPORTED_PLATFORMS = ['linkedin', 'naukri', 'indeed', 'glassdoor', 'foundit'] as const;
const MAX_LOG_LINES = 200;
const MAX_LOG_LINE_LENGTH = 2_000;
const MAX_PENDING_LOG_LENGTH = 8_000;
const MAX_HISTORY_RECORDS = 100;
const TERMINAL_RETENTION_MS = 60 * 60 * 1_000;

type Platform = (typeof SUPPORTED_PLATFORMS)[number];
type BotStatus = 'starting' | 'running' | 'completed' | 'error' | 'stopped';

interface BotConfig {
  platform: Platform;
  filters: string[];
  headless: boolean;
  slowMo: number;
  maxApplications: number;
  exportCsv: boolean;
}

interface BotRecord {
  id: string;
  platform: Platform;
  status: BotStatus;
  startedAt: string;
  endedAt?: string;
  config: BotConfig;
  recentLogs: string[];
  exitCode?: number | null;
  signal?: NodeJS.Signals | null;
  error?: string;
  child?: ChildProcess;
  stopRequested: boolean;
  stdoutRemainder: string;
  stderrRemainder: string;
  endedAtMs?: number;
}

const botHistory = new Map<string, BotRecord>();

function isTerminal(status: BotStatus): boolean {
  return status === 'completed' || status === 'error' || status === 'stopped';
}

function addLog(record: BotRecord, source: 'stdout' | 'stderr' | 'system', message: string): void {
  const cleaned = message.replace(/\0/g, '').replace(/\r$/, '');
  if (!cleaned) return;
  const bounded = cleaned.length > MAX_LOG_LINE_LENGTH
    ? `${cleaned.slice(0, MAX_LOG_LINE_LENGTH)}…`
    : cleaned;
  record.recentLogs.push(`${new Date().toISOString()} [${source}] ${bounded}`);
  if (record.recentLogs.length > MAX_LOG_LINES) {
    record.recentLogs.splice(0, record.recentLogs.length - MAX_LOG_LINES);
  }
}

function consumeOutput(
  record: BotRecord,
  source: 'stdout' | 'stderr',
  chunk: Buffer | string,
): void {
  const remainderKey = source === 'stdout' ? 'stdoutRemainder' : 'stderrRemainder';
  const combined = record[remainderKey] + chunk.toString();
  const lines = combined.split(/\r?\n/);
  record[remainderKey] = lines.pop() ?? '';
  for (const line of lines) addLog(record, source, line);

  if (record[remainderKey].length > MAX_PENDING_LOG_LENGTH) {
    addLog(record, source, record[remainderKey]);
    record[remainderKey] = '';
  }
}

function flushOutput(record: BotRecord): void {
  if (record.stdoutRemainder) addLog(record, 'stdout', record.stdoutRemainder);
  if (record.stderrRemainder) addLog(record, 'stderr', record.stderrRemainder);
  record.stdoutRemainder = '';
  record.stderrRemainder = '';
}

function serializeBot(record: BotRecord) {
  return {
    id: record.id,
    platform: record.platform,
    status: record.status,
    startedAt: record.startedAt,
    ...(record.endedAt ? { endedAt: record.endedAt } : {}),
    config: { ...record.config, filters: [...record.config.filters] },
    recentLogs: [...record.recentLogs],
    ...(record.exitCode !== undefined ? { exitCode: record.exitCode } : {}),
    ...(record.signal !== undefined ? { signal: record.signal } : {}),
    ...(record.error ? { error: record.error } : {}),
  };
}

function pruneHistory(): void {
  const now = Date.now();
  for (const [id, record] of botHistory) {
    if (isTerminal(record.status) && record.endedAtMs && now - record.endedAtMs > TERMINAL_RETENTION_MS) {
      botHistory.delete(id);
    }
  }

  if (botHistory.size <= MAX_HISTORY_RECORDS) return;
  const terminalRecords = Array.from(botHistory.values())
    .filter((record) => isTerminal(record.status))
    .sort((a, b) => (a.endedAtMs ?? 0) - (b.endedAtMs ?? 0));
  while (botHistory.size > MAX_HISTORY_RECORDS && terminalRecords.length > 0) {
    const record = terminalRecords.shift();
    if (record) botHistory.delete(record.id);
  }
}

function validateConfig(body: unknown): { config?: BotConfig; errors?: string[] } {
  if (!body || typeof body !== 'object' || Array.isArray(body)) {
    return { errors: ['Request body must be a flat BotConfig JSON object'] };
  }

  const input = body as Record<string, unknown>;
  const errors: string[] = [];

  if (typeof input.platform !== 'string' || !SUPPORTED_PLATFORMS.includes(input.platform as Platform)) {
    errors.push(`platform must be one of: ${SUPPORTED_PLATFORMS.join(', ')}`);
  }
  if (typeof input.headless !== 'boolean') errors.push('headless must be a boolean');
  if (!Number.isInteger(input.slowMo) || (input.slowMo as number) < 0 || (input.slowMo as number) > 60_000) {
    errors.push('slowMo must be an integer between 0 and 60000');
  }
  if (!Number.isInteger(input.maxApplications)
    || (input.maxApplications as number) < 1
    || (input.maxApplications as number) > 200) {
    errors.push('maxApplications must be an integer between 1 and 200');
  }
  if (typeof input.exportCsv !== 'boolean') errors.push('exportCsv must be a boolean');

  const filters = input.filters ?? [];
  let normalizedFilters: string[] = [];
  if (!Array.isArray(filters)
    || filters.length > 50
    || filters.some((filter) => typeof filter !== 'string' || filter.length === 0 || filter.length > 128)) {
    errors.push('filters must be an array of 1-128 character strings (maximum 50)');
  } else {
    normalizedFilters = [...filters] as string[];
  }

  if (errors.length > 0) return { errors };
  return {
    config: {
      platform: input.platform as Platform,
      filters: normalizedFilters,
      headless: input.headless as boolean,
      slowMo: input.slowMo as number,
      maxApplications: input.maxApplications as number,
      exportCsv: input.exportCsv as boolean,
    },
  };
}

function childHasExited(child: ChildProcess): boolean {
  return child.exitCode !== null || child.signalCode !== null;
}

function waitForChildExit(child: ChildProcess, timeoutMs: number): Promise<boolean> {
  if (childHasExited(child)) return Promise.resolve(true);
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      child.off('close', onClose);
      resolve(childHasExited(child));
    }, timeoutMs);
    timer.unref();
    const onClose = () => {
      clearTimeout(timer);
      resolve(true);
    };
    child.once('close', onClose);
  });
}

function runTaskkill(child: ChildProcess, pid: number): Promise<void> {
  return new Promise((resolve, reject) => {
    const killer = spawn('taskkill', ['/pid', String(pid), '/T', '/F'], {
      stdio: 'ignore',
      windowsHide: true,
    });
    killer.once('error', reject);
    killer.once('close', (code) => {
      if (code === 0 || childHasExited(child)) {
        resolve();
      } else {
        reject(new Error(`taskkill exited with code ${code ?? 'unknown'}`));
      }
    });
  });
}

async function terminateProcessTree(child: ChildProcess): Promise<void> {
  if (childHasExited(child)) return;
  const pid = child.pid;
  if (!pid) {
    child.kill('SIGTERM');
    await waitForChildExit(child, 2_000);
    return;
  }

  if (process.platform === 'win32') {
    await runTaskkill(child, pid);
    await waitForChildExit(child, 3_000);
    return;
  }

  try {
    process.kill(-pid, 'SIGTERM');
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    if (code !== 'ESRCH') throw error;
  }

  if (await waitForChildExit(child, 5_000)) return;

  try {
    process.kill(-pid, 'SIGKILL');
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    if (code !== 'ESRCH') throw error;
  }
  await waitForChildExit(child, 2_000);
}

async function stopRecord(record: BotRecord, reason: string): Promise<void> {
  const child = record.child;
  if (!child || childHasExited(child)) {
    if (!isTerminal(record.status)) {
      record.status = 'stopped';
      record.endedAt = new Date().toISOString();
      record.endedAtMs = Date.now();
    }
    return;
  }

  record.stopRequested = true;
  addLog(record, 'system', reason);
  try {
    await terminateProcessTree(child);
    record.status = 'stopped';
    record.endedAt ??= new Date().toISOString();
    record.endedAtMs ??= Date.now();
  } catch (error) {
    record.stopRequested = false;
    record.status = childHasExited(child) ? 'error' : 'running';
    record.error = error instanceof Error ? error.message : 'Failed to stop bot process';
    addLog(record, 'system', record.error);
    throw error;
  }
}

botRouter.get('/active', (_req, res) => {
  pruneHistory();
  res.json(Array.from(botHistory.values()).map(serializeBot));
});

botRouter.post('/start', (req, res) => {
  const validation = validateConfig(req.body);
  if (!validation.config) {
    res.status(400).json({ error: 'Invalid bot configuration', details: validation.errors });
    return;
  }
  if (!fs.existsSync(ORCHESTRATOR_PATH)) {
    res.status(500).json({ error: `Bot orchestrator not found at ${ORCHESTRATOR_PATH}` });
    return;
  }

  ensureApplicationsCsv();
  pruneHistory();

  const config = validation.config;
  const id = `${config.platform}-${Date.now()}-${randomUUID().slice(0, 8)}`;
  const record: BotRecord = {
    id,
    platform: config.platform,
    status: 'starting',
    startedAt: new Date().toISOString(),
    config,
    recentLogs: [],
    stopRequested: false,
    stdoutRemainder: '',
    stderrRemainder: '',
  };
  botHistory.set(id, record);

  const filtersJson = JSON.stringify(config.filters);
  try {
    const child = spawn(PYTHON_PATH, [ORCHESTRATOR_PATH, '--platform', config.platform], {
      cwd: APP_ROOT,
      detached: process.platform !== 'win32',
      env: {
        ...process.env,
        PYTHON_PATH,
        BOTS_DIR,
        APPLICATIONS_CSV,
        FILTERS_DIR,
        HEADLESS: String(config.headless),
        SLOW_MO: String(config.slowMo),
        MAX_APPLICATIONS: String(config.maxApplications),
        EXPORT_CSV: String(config.exportCsv),
        FILTERS: filtersJson,
        BOT_FILTERS: filtersJson,
        BOT_CONFIG: JSON.stringify(config),
      },
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
    });
    record.child = child;

    child.stdout?.on('data', (chunk: Buffer) => consumeOutput(record, 'stdout', chunk));
    child.stderr?.on('data', (chunk: Buffer) => consumeOutput(record, 'stderr', chunk));
    child.once('spawn', () => {
      if (!record.stopRequested && record.status === 'starting') record.status = 'running';
      addLog(record, 'system', `Process started with PID ${child.pid ?? 'unknown'}`);
    });
    child.once('error', (error) => {
      record.status = 'error';
      record.error = error.message;
      record.endedAt = new Date().toISOString();
      record.endedAtMs = Date.now();
      addLog(record, 'system', `Process error: ${error.message}`);
    });
    child.once('close', (code, signal) => {
      flushOutput(record);
      record.exitCode = code;
      record.signal = signal;
      record.endedAt = new Date().toISOString();
      record.endedAtMs = Date.now();
      if (record.stopRequested) {
        record.status = 'stopped';
      } else if (code === 0) {
        record.status = 'completed';
      } else {
        record.status = 'error';
        record.error ??= `Bot process exited with code ${code ?? 'unknown'}${signal ? ` (${signal})` : ''}`;
      }
      addLog(record, 'system', `Process ${record.status}${code !== null ? ` with exit code ${code}` : ''}`);
      record.child = undefined;
      pruneHistory();
    });

    res.status(202).json({
      success: true,
      botId: id,
      message: `Bot process starting for ${config.platform}`,
      bot: serializeBot(record),
    });
  } catch (error) {
    record.status = 'error';
    record.error = error instanceof Error ? error.message : 'Failed to start bot process';
    record.endedAt = new Date().toISOString();
    record.endedAtMs = Date.now();
    addLog(record, 'system', record.error);
    res.status(500).json({ error: record.error, botId: id, bot: serializeBot(record) });
  }
});

botRouter.post('/:id/stop', async (req, res) => {
  const record = botHistory.get(req.params.id);
  if (!record) {
    res.status(404).json({ error: 'Bot not found' });
    return;
  }

  if (isTerminal(record.status) && !record.child) {
    res.json({ success: true, message: `Bot is already ${record.status}`, bot: serializeBot(record) });
    return;
  }

  try {
    await stopRecord(record, 'Stop requested through API');
    res.json({ success: true, message: 'Bot stopped', bot: serializeBot(record) });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Failed to stop bot';
    res.status(500).json({ error: message, bot: serializeBot(record) });
  }
});

export async function shutdownBots(): Promise<void> {
  const runningRecords = Array.from(botHistory.values())
    .filter((record) => record.child && !childHasExited(record.child));
  const results = await Promise.allSettled(
    runningRecords.map((record) => stopRecord(record, 'Backend shutdown requested')),
  );
  const failures = results.filter((result) => result.status === 'rejected');
  if (failures.length > 0) {
    throw new Error(`Failed to stop ${failures.length} bot process tree(s)`);
  }
}
