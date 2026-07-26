export const PLATFORMS = ['linkedin', 'naukri', 'indeed', 'glassdoor', 'foundit'] as const;

export type Platform = (typeof PLATFORMS)[number];
export type AppView = 'dashboard' | 'applications' | 'filters' | 'bots';
export type ApplicationStatus = 'applied' | 'pending' | 'failed' | 'skipped';
export type BotStatus = 'starting' | 'running' | 'completed' | 'error' | 'stopped';

export interface Application {
  id: string;
  timestamp: string;
  platform: Platform;
  jobTitle: string;
  company: string;
  location: string;
  jobUrl: string;
  status: ApplicationStatus;
  appliedAt: string;
  notes: string;
}

export interface BotConfig {
  platform: Platform;
  filters: string[];
  headless: boolean;
  slowMo: number;
  maxApplications: number;
  exportCsv: boolean;
}

export interface BotRecord {
  id: string;
  platform: Platform;
  status: BotStatus;
  startedAt: string;
  endedAt?: string;
  error?: string;
  exitCode?: number | null;
  signal?: string | null;
  config: BotConfig;
  recentLogs: string[];
}

/** Filter documents can include platform-specific values in addition to these shared fields. */
export interface FilterData {
  [key: string]: unknown;
  name?: string;
  platform?: Platform;
  keywords?: string[];
  locations?: string[];
  excludeKeywords?: string[];
  experienceMin?: number;
  experienceMax?: number;
  postedWithinDays?: number;
  easyApplyOnly?: boolean;
  remoteOnly?: boolean;
  strictKeywordMatch?: boolean;
}

export interface FilterProfile {
  name: string;
  data: FilterData;
}

export interface StartBotResponse {
  success: boolean;
  botId: string;
  message: string;
  bot: BotRecord;
}

export interface StopBotResponse {
  success: boolean;
  message: string;
  bot: BotRecord;
}

export interface SaveFilterResponse {
  success: boolean;
  name: string;
}

export interface SuccessResponse {
  success: boolean;
}
