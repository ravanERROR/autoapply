import { useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertCircle,
  Bot,
  CheckCircle2,
  ChevronRight,
  Clock3,
  FileDown,
  Loader2,
  MonitorOff,
  Play,
  RefreshCw,
  Settings2,
  SlidersHorizontal,
  Square,
  Terminal,
} from 'lucide-react';
import { PLATFORMS } from '../types';
import type { BotConfig, BotRecord, FilterProfile } from '../types';

interface BotControlCenterProps {
  bots: BotRecord[];
  filters: FilterProfile[];
  filtersLoading: boolean;
  loading: boolean;
  polling: boolean;
  onNavigateFilters: () => void;
  onRefresh: () => Promise<boolean>;
  onStart: (config: BotConfig) => Promise<BotRecord | null>;
  onStop: (id: string) => Promise<BotRecord | null>;
}

const INITIAL_CONFIG: BotConfig = {
  platform: 'linkedin',
  filters: [],
  headless: false,
  slowMo: 250,
  maxApplications: 25,
  exportCsv: true,
};

function formatDate(value?: string): string {
  if (!value) return 'Not ended';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Time unavailable';
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date);
}

function startedTimestamp(bot: BotRecord): number {
  const timestamp = new Date(bot.startedAt).getTime();
  return Number.isNaN(timestamp) ? 0 : timestamp;
}

function isActive(bot: BotRecord): boolean {
  return bot.status === 'starting' || bot.status === 'running';
}

function statusIcon(bot: BotRecord) {
  if (bot.status === 'completed') return <CheckCircle2 aria-hidden="true" className="size-4" />;
  if (bot.status === 'error') return <AlertCircle aria-hidden="true" className="size-4" />;
  if (bot.status === 'stopped') return <Square aria-hidden="true" className="size-3.5" />;
  return <Bot aria-hidden="true" className="size-4" />;
}

export function BotControlCenter({
  bots,
  filters,
  filtersLoading,
  loading,
  polling,
  onNavigateFilters,
  onRefresh,
  onStart,
  onStop,
}: BotControlCenterProps) {
  const [config, setConfig] = useState<BotConfig>(INITIAL_CONFIG);
  const [starting, setStarting] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [stoppingId, setStoppingId] = useState<string | null>(null);
  const [selectedBotId, setSelectedBotId] = useState<string | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const logsRef = useRef<HTMLDivElement>(null);

  const sortedBots = useMemo(() => (
    [...bots].sort((a, b) => startedTimestamp(b) - startedTimestamp(a))
  ), [bots]);
  const selectedBot = sortedBots.find((bot) => bot.id === selectedBotId) ?? null;
  const activeCount = sortedBots.filter(isActive).length;
  const unavailableFilters = config.filters.filter((name) => !filters.some((profile) => profile.name === name));

  useEffect(() => {
    if (sortedBots.length === 0) {
      setSelectedBotId(null);
      return;
    }
    if (selectedBotId && sortedBots.some((bot) => bot.id === selectedBotId)) return;
    setSelectedBotId(sortedBots.find(isActive)?.id ?? sortedBots[0].id);
  }, [selectedBotId, sortedBots]);

  const logCount = selectedBot?.recentLogs.length ?? 0;
  useEffect(() => {
    if (!logsRef.current) return;
    logsRef.current.scrollTop = logsRef.current.scrollHeight;
  }, [logCount, selectedBotId]);

  const updateNumber = (field: 'slowMo' | 'maxApplications', value: string) => {
    setConfig((current) => ({ ...current, [field]: value === '' ? Number.NaN : Number(value) }));
    setValidationError(null);
  };

  const toggleFilter = (name: string) => {
    setConfig((current) => ({
      ...current,
      filters: current.filters.includes(name)
        ? current.filters.filter((filter) => filter !== name)
        : [...current.filters, name],
    }));
    setValidationError(null);
  };

  const validate = (): string | null => {
    if (!Number.isInteger(config.maxApplications) || config.maxApplications < 1 || config.maxApplications > 200) {
      return 'Max applications must be a whole number between 1 and 200.';
    }
    if (!Number.isInteger(config.slowMo) || config.slowMo < 0 || config.slowMo > 60_000) {
      return 'Action delay must be a whole number between 0 and 60,000 milliseconds.';
    }
    if (config.filters.length > 50) return 'Choose no more than 50 filter profiles.';
    if (unavailableFilters.length > 0) {
      return `Remove unavailable ${unavailableFilters.length === 1 ? 'profile' : 'profiles'}: ${unavailableFilters.join(', ')}.`;
    }
    return null;
  };

  const start = async () => {
    const issue = validate();
    if (issue) {
      setValidationError(issue);
      return;
    }

    setStarting(true);
    setValidationError(null);
    const bot = await onStart({ ...config, filters: [...config.filters] });
    setStarting(false);
    if (bot) setSelectedBotId(bot.id);
  };

  const stop = async (id: string) => {
    setStoppingId(id);
    await onStop(id);
    setStoppingId(null);
  };

  const refresh = async () => {
    setRefreshing(true);
    await onRefresh();
    setRefreshing(false);
  };

  return (
    <div className="page-enter space-y-5">
      <header className="page-heading">
        <div>
          <div className="eyebrow text-violet-700">
            <Bot aria-hidden="true" className="size-3.5" />
            Automation control
          </div>
          <h1 className="mt-3 font-display text-3xl font-semibold tracking-[-0.04em] text-slate-950 sm:text-4xl">Launch with clarity.</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
            Send an exact run configuration, then follow the server-reported state and latest process output.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {polling && (
            <span className="live-pill" aria-label="Bot activity is refreshing automatically"><span />Live polling</span>
          )}
          <button className="button button-secondary" disabled={refreshing || loading} onClick={() => void refresh()} type="button">
            <RefreshCw aria-hidden="true" className={`size-4 ${refreshing ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </header>

      <div className="grid items-start gap-5 xl:grid-cols-[minmax(340px,0.78fr)_minmax(0,1.22fr)]">
        <section className="surface-card p-4 sm:p-5" aria-labelledby="bot-configuration-title">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="section-kicker">New run</p>
              <h2 className="section-title" id="bot-configuration-title">Bot configuration</h2>
            </div>
            <div className="flex size-10 items-center justify-center rounded-2xl bg-violet-100 text-violet-700">
              <Settings2 aria-hidden="true" className="size-5" />
            </div>
          </div>

          <fieldset className="mt-6">
            <legend className="field-label">Platform</legend>
            <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-2">
              {PLATFORMS.map((platform) => (
                <button
                  aria-pressed={config.platform === platform}
                  className={`platform-choice ${config.platform === platform ? 'platform-choice-active' : ''}`}
                  key={platform}
                  onClick={() => {
                    setConfig((current) => ({ ...current, platform }));
                    setValidationError(null);
                  }}
                  type="button"
                >
                  <span className="platform-mark size-7 text-[10px]" data-platform={platform}>
                    {platform.slice(0, 1).toUpperCase()}
                  </span>
                  <span className="capitalize">{platform}</span>
                </button>
              ))}
            </div>
          </fieldset>

          <div className="mt-5 grid gap-4 sm:grid-cols-2">
            <label>
              <span className="field-label">Max applications</span>
              <span className="field-hint">1–200 per run</span>
              <input
                className="field-input mt-2"
                inputMode="numeric"
                max={200}
                min={1}
                onChange={(event) => updateNumber('maxApplications', event.target.value)}
                type="number"
                value={Number.isNaN(config.maxApplications) ? '' : config.maxApplications}
              />
            </label>
            <label>
              <span className="field-label">Action delay</span>
              <span className="field-hint">Milliseconds</span>
              <input
                className="field-input mt-2"
                inputMode="numeric"
                max={60_000}
                min={0}
                onChange={(event) => updateNumber('slowMo', event.target.value)}
                step={50}
                type="number"
                value={Number.isNaN(config.slowMo) ? '' : config.slowMo}
              />
            </label>
          </div>

          <div className="mt-5 grid gap-2 sm:grid-cols-2">
            <label className="boolean-card">
              <span className="boolean-icon"><MonitorOff aria-hidden="true" className="size-4" /></span>
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-extrabold text-slate-800">Headless</span>
                <span className="mt-0.5 block text-[11px] leading-4 text-slate-500">Hide browser window</span>
              </span>
              <input
                checked={config.headless}
                className="switch-input"
                onChange={(event) => setConfig((current) => ({ ...current, headless: event.target.checked }))}
                type="checkbox"
              />
            </label>
            <label className="boolean-card">
              <span className="boolean-icon"><FileDown aria-hidden="true" className="size-4" /></span>
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-extrabold text-slate-800">Export CSV</span>
                <span className="mt-0.5 block text-[11px] leading-4 text-slate-500">Enable bot export</span>
              </span>
              <input
                checked={config.exportCsv}
                className="switch-input"
                onChange={(event) => setConfig((current) => ({ ...current, exportCsv: event.target.checked }))}
                type="checkbox"
              />
            </label>
          </div>

          <fieldset className="mt-6">
            <div className="flex items-center justify-between gap-3">
              <legend className="field-label">Filter profiles</legend>
              <span className="data-pill">{config.filters.length} selected</span>
            </div>
            {filtersLoading ? (
              <div className="mt-2 flex items-center gap-2 rounded-2xl border border-slate-200 bg-slate-50 px-3 py-4 text-xs text-slate-500">
                <Loader2 aria-hidden="true" className="size-4 animate-spin text-violet-500" /> Loading profiles…
              </div>
            ) : filters.length === 0 ? (
              <div className="mt-2 rounded-2xl border border-dashed border-slate-200 bg-slate-50/70 p-4 text-center">
                <SlidersHorizontal aria-hidden="true" className="mx-auto size-5 text-slate-300" />
                <p className="mt-2 text-xs font-bold text-slate-700">No filter profiles available</p>
                <button className="text-button mx-auto mt-2" onClick={onNavigateFilters} type="button">Create a profile</button>
              </div>
            ) : (
              <div className="mt-2 max-h-48 space-y-2 overflow-y-auto pr-1">
                {filters.map((profile) => (
                  <label className="profile-check" key={profile.name}>
                    <input
                      checked={config.filters.includes(profile.name)}
                      onChange={() => toggleFilter(profile.name)}
                      type="checkbox"
                    />
                    <span className="min-w-0 flex-1 truncate text-sm font-bold text-slate-700">{profile.name}</span>
                    <ChevronRight aria-hidden="true" className="size-3.5 text-slate-300" />
                  </label>
                ))}
              </div>
            )}
          </fieldset>

          {unavailableFilters.length > 0 && (
            <p className="form-error mt-4" role="alert">
              <AlertCircle aria-hidden="true" className="size-4 shrink-0" />
              Selected but unavailable: {unavailableFilters.join(', ')}
            </p>
          )}
          {validationError && (
            <p className="form-error mt-4" role="alert">
              <AlertCircle aria-hidden="true" className="size-4 shrink-0" />
              {validationError}
            </p>
          )}

          <button className="button button-primary mt-6 w-full justify-center py-3" disabled={starting} onClick={() => void start()} type="button">
            {starting
              ? <Loader2 aria-hidden="true" className="size-4 animate-spin" />
              : <Play aria-hidden="true" className="size-4 fill-current" />}
            {starting ? 'Starting bot…' : `Start ${config.platform} bot`}
          </button>
          <p className="mt-3 text-center text-[11px] leading-4 text-slate-400">The configuration is sent as one flat BotConfig object.</p>
        </section>

        <section className="surface-card min-w-0 overflow-hidden p-0" aria-labelledby="bot-activity-title">
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-4 sm:px-5">
            <div>
              <p className="section-kicker">Server records</p>
              <h2 className="section-title" id="bot-activity-title">Run activity</h2>
            </div>
            <span className="data-pill">{activeCount} active · {sortedBots.length} retained</span>
          </div>

          {loading && sortedBots.length === 0 ? (
            <div className="empty-state py-20">
              <Loader2 aria-hidden="true" className="size-6 animate-spin text-violet-500" />
              <p className="mt-3 text-sm font-bold text-slate-700">Loading bot activity…</p>
            </div>
          ) : sortedBots.length === 0 ? (
            <div className="empty-state py-20">
              <div className="empty-state-icon"><Bot aria-hidden="true" className="size-5" /></div>
              <p className="mt-4 text-sm font-extrabold text-slate-800">No bot records retained</p>
              <p className="mt-1 max-w-sm text-xs leading-5 text-slate-500">Configure a run to create the first server record.</p>
            </div>
          ) : (
            <div className="grid min-h-[560px] min-w-0 md:grid-cols-[210px_minmax(0,1fr)]">
              <div className="bot-record-list border-b border-slate-100 bg-slate-50/65 p-2 md:border-b-0 md:border-r">
                {sortedBots.map((bot) => (
                  <button
                    aria-current={bot.id === selectedBotId ? 'true' : undefined}
                    className={`bot-record-button ${bot.id === selectedBotId ? 'bot-record-button-active' : ''}`}
                    key={bot.id}
                    onClick={() => setSelectedBotId(bot.id)}
                    type="button"
                  >
                    <span className={`bot-state-icon bot-state-${bot.status}`}>{statusIcon(bot)}</span>
                    <span className="min-w-0 flex-1 text-left">
                      <span className="block truncate text-xs font-extrabold capitalize text-slate-800">{bot.platform}</span>
                      <span className="mt-1 block truncate text-[10px] text-slate-500">{formatDate(bot.startedAt)}</span>
                    </span>
                    {isActive(bot) && <span className="live-dot shrink-0" aria-label="Active" />}
                  </button>
                ))}
              </div>

              {selectedBot && (
                <div className="min-w-0 p-4 sm:p-5">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={`status-badge status-${selectedBot.status}`}>{selectedBot.status}</span>
                        <span className="text-xs font-bold capitalize text-slate-500">{selectedBot.platform}</span>
                      </div>
                      <p className="mt-3 break-all font-mono text-[11px] text-slate-400">{selectedBot.id}</p>
                    </div>
                    {isActive(selectedBot) && (
                      <button
                        className="button button-danger shrink-0"
                        disabled={stoppingId === selectedBot.id}
                        onClick={() => void stop(selectedBot.id)}
                        type="button"
                      >
                        {stoppingId === selectedBot.id
                          ? <Loader2 aria-hidden="true" className="size-4 animate-spin" />
                          : <Square aria-hidden="true" className="size-3.5 fill-current" />}
                        {stoppingId === selectedBot.id ? 'Stopping…' : 'Stop run'}
                      </button>
                    )}
                  </div>

                  <dl className="mt-5 grid grid-cols-2 gap-2 lg:grid-cols-3">
                    <div className="run-detail">
                      <dt><Clock3 aria-hidden="true" className="size-3.5" />Started</dt>
                      <dd>{formatDate(selectedBot.startedAt)}</dd>
                    </div>
                    <div className="run-detail">
                      <dt><Clock3 aria-hidden="true" className="size-3.5" />Ended</dt>
                      <dd>{formatDate(selectedBot.endedAt)}</dd>
                    </div>
                    <div className="run-detail col-span-2 lg:col-span-1">
                      <dt><Terminal aria-hidden="true" className="size-3.5" />Process result</dt>
                      <dd>
                        {selectedBot.exitCode === undefined
                          ? 'Not reported'
                          : `${selectedBot.exitCode === null ? 'No exit code' : `Exit ${selectedBot.exitCode}`}${selectedBot.signal ? ` · ${selectedBot.signal}` : ''}`}
                      </dd>
                    </div>
                  </dl>

                  {selectedBot.error && (
                    <div className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 px-3 py-3" role="alert">
                      <p className="flex items-center gap-2 text-xs font-extrabold text-rose-900">
                        <AlertCircle aria-hidden="true" className="size-4" />Server-reported error
                      </p>
                      <p className="mt-1 break-words text-xs leading-5 text-rose-800">{selectedBot.error}</p>
                    </div>
                  )}

                  <div className="mt-5">
                    <p className="section-kicker">Run configuration</p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      <span className="config-chip">Max {selectedBot.config.maxApplications}</span>
                      <span className="config-chip">Delay {selectedBot.config.slowMo} ms</span>
                      <span className="config-chip">{selectedBot.config.headless ? 'Headless' : 'Visible browser'}</span>
                      <span className="config-chip">CSV {selectedBot.config.exportCsv ? 'on' : 'off'}</span>
                      {selectedBot.config.filters.map((filter) => <span className="config-chip config-chip-accent" key={filter}>{filter}</span>)}
                    </div>
                  </div>

                  <div className="mt-5 overflow-hidden rounded-2xl border border-slate-800 bg-[#11121c] shadow-inner">
                    <div className="flex items-center justify-between border-b border-white/10 px-3 py-2.5">
                      <p className="flex items-center gap-2 text-[11px] font-extrabold uppercase tracking-[0.14em] text-slate-300">
                        <Terminal aria-hidden="true" className="size-3.5 text-violet-300" />Recent logs
                      </p>
                      <span className="text-[10px] text-slate-500">{selectedBot.recentLogs.length} lines</span>
                    </div>
                    <div
                      aria-label={`Recent logs for ${selectedBot.platform} bot`}
                      aria-live="off"
                      className="bot-log"
                      ref={logsRef}
                      role="log"
                    >
                      {selectedBot.recentLogs.length === 0 ? (
                        <p className="text-slate-500">No process output has been received by the server.</p>
                      ) : selectedBot.recentLogs.map((line, index) => (
                        <p className="break-words" key={`${index}-${line.slice(0, 32)}`}>{line}</p>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
