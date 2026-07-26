import type {
  Application,
  BotConfig,
  BotRecord,
  FilterData,
  FilterProfile,
  SaveFilterResponse,
  StartBotResponse,
  StopBotResponse,
  SuccessResponse,
} from '../types';

const API_ROOT = '/api';

interface ApiErrorPayload {
  error?: string;
  message?: string;
  details?: unknown;
  bot?: BotRecord;
}

export class ApiError extends Error {
  readonly status: number;
  readonly payload?: ApiErrorPayload;

  constructor(message: string, status: number, payload?: ApiErrorPayload) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.payload = payload;
  }
}

function detailsText(details: unknown): string {
  if (Array.isArray(details)) {
    return details.filter((item): item is string => typeof item === 'string').join(' · ');
  }
  return typeof details === 'string' ? details : '';
}

async function readError(response: Response): Promise<ApiError> {
  let payload: ApiErrorPayload | undefined;

  try {
    payload = await response.json() as ApiErrorPayload;
  } catch {
    payload = undefined;
  }

  const baseMessage = payload?.error || payload?.message || `Request failed (${response.status})`;
  const detail = detailsText(payload?.details);
  return new ApiError(detail ? `${baseMessage}: ${detail}` : baseMessage, response.status, payload);
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;

  try {
    response = await fetch(`${API_ROOT}${path}`, {
      ...init,
      headers: {
        Accept: 'application/json',
        ...init?.headers,
      },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'The server could not be reached';
    throw new ApiError(message, 0);
  }

  if (!response.ok) throw await readError(response);

  try {
    return await response.json() as T;
  } catch {
    throw new ApiError('The server returned an invalid response', response.status);
  }
}

async function requestBlob(path: string): Promise<Blob> {
  let response: Response;

  try {
    response = await fetch(`${API_ROOT}${path}`, {
      headers: { Accept: 'text/csv' },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'The server could not be reached';
    throw new ApiError(message, 0);
  }

  if (!response.ok) throw await readError(response);
  return response.blob();
}

function jsonBody(value: unknown): Pick<RequestInit, 'headers' | 'body'> {
  return {
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(value),
  };
}

export const api = {
  getApplications: () => requestJson<Application[]>('/applications'),
  clearApplications: () => requestJson<SuccessResponse>('/applications/clear', { method: 'DELETE' }),
  exportApplications: () => requestBlob('/applications/export'),

  getBots: () => requestJson<BotRecord[]>('/bot/active'),
  startBot: (config: BotConfig) => requestJson<StartBotResponse>('/bot/start', {
    method: 'POST',
    ...jsonBody(config),
  }),
  stopBot: (id: string) => requestJson<StopBotResponse>(`/bot/${encodeURIComponent(id)}/stop`, {
    method: 'POST',
  }),

  getFilters: () => requestJson<FilterProfile[]>('/filters'),
  saveFilter: (name: string, data: FilterData) => requestJson<SaveFilterResponse>(
    `/filters/${encodeURIComponent(name)}`,
    { method: 'POST', ...jsonBody(data) },
  ),
};

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Something went wrong';
}
