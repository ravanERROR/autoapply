import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import {
  Bot,
  BriefcaseBusiness,
  LayoutDashboard,
  RefreshCw,
  SlidersHorizontal,
  Sparkles,
  X,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { ApplicationsTable } from './components/ApplicationsTable';
import { BotControlCenter } from './components/BotControlCenter';
import { FiltersView } from './components/FiltersView';
import { api, ApiError, errorMessage } from './lib/api';
import type {
  Application,
  AppView,
  BotConfig,
  BotRecord,
  FilterData,
  FilterProfile,
} from './types';

const Dashboard = lazy(async () => {
  const module = await import('./components/Dashboard');
  return { default: module.Dashboard };
});

interface NavigationItem {
  id: AppView;
  label: string;
  shortLabel: string;
  description: string;
  icon: LucideIcon;
}

interface Notice {
  id: number;
  kind: 'success' | 'error';
  message: string;
}

interface ResourceError {
  key: string;
  label: string;
  message: string;
  retry: () => Promise<boolean>;
}

const NAVIGATION: NavigationItem[] = [
  {
    id: 'dashboard',
    label: 'Dashboard',
    shortLabel: 'Home',
    description: 'Workspace overview',
    icon: LayoutDashboard,
  },
  {
    id: 'applications',
    label: 'Applications',
    shortLabel: 'Applications',
    description: 'Recorded opportunities',
    icon: BriefcaseBusiness,
  },
  {
    id: 'filters',
    label: 'Filter profiles',
    shortLabel: 'Filters',
    description: 'Search preferences',
    icon: SlidersHorizontal,
  },
  {
    id: 'bots',
    label: 'Bot runs',
    shortLabel: 'Bots',
    description: 'Configure and monitor',
    icon: Bot,
  },
];

function viewFromHash(): AppView {
  const value = window.location.hash.replace(/^#\/?/, '');
  return NAVIGATION.some((item) => item.id === value) ? value as AppView : 'dashboard';
}

function upsertBot(records: BotRecord[], bot: BotRecord): BotRecord[] {
  const withoutBot = records.filter((record) => record.id !== bot.id);
  return [bot, ...withoutBot];
}

function formatSyncTime(value: Date | null): string {
  if (!value) return 'Not synced yet';
  return `Updated ${new Intl.DateTimeFormat(undefined, {
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
  }).format(value)}`;
}

function BrandMark({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex items-center gap-3">
      <div className="brand-mark" aria-hidden="true">
        <Sparkles className="size-4" />
      </div>
      {!compact && (
        <div>
          <p className="font-display text-xl font-semibold leading-none tracking-[-0.03em]">JobApply</p>
          <p className="mt-1 text-[10px] font-bold uppercase tracking-[0.2em] text-violet-200/70">Search studio</p>
        </div>
      )}
    </div>
  );
}

export default function App() {
  const [view, setView] = useState<AppView>(viewFromHash);
  const [applications, setApplications] = useState<Application[]>([]);
  const [bots, setBots] = useState<BotRecord[]>([]);
  const [filters, setFilters] = useState<FilterProfile[]>([]);

  const [applicationsLoading, setApplicationsLoading] = useState(true);
  const [botsLoading, setBotsLoading] = useState(true);
  const [filtersLoading, setFiltersLoading] = useState(true);
  const [refreshingAll, setRefreshingAll] = useState(false);

  const [applicationsError, setApplicationsError] = useState<string | null>(null);
  const [botsError, setBotsError] = useState<string | null>(null);
  const [filtersError, setFiltersError] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);

  const [applicationsUpdatedAt, setApplicationsUpdatedAt] = useState<Date | null>(null);
  const [botsUpdatedAt, setBotsUpdatedAt] = useState<Date | null>(null);
  const [filtersUpdatedAt, setFiltersUpdatedAt] = useState<Date | null>(null);
  const pollInFlight = useRef(false);

  const notify = useCallback((kind: Notice['kind'], message: string) => {
    setNotice({ id: Date.now(), kind, message });
  }, []);

  const loadApplications = useCallback(async (background = false): Promise<boolean> => {
    if (!background) setApplicationsLoading(true);
    try {
      const records = await api.getApplications();
      setApplications(records);
      setApplicationsError(null);
      setApplicationsUpdatedAt(new Date());
      return true;
    } catch (error) {
      setApplicationsError(errorMessage(error));
      return false;
    } finally {
      if (!background) setApplicationsLoading(false);
    }
  }, []);

  const loadBots = useCallback(async (background = false): Promise<boolean> => {
    if (!background) setBotsLoading(true);
    try {
      const records = await api.getBots();
      setBots(records);
      setBotsError(null);
      setBotsUpdatedAt(new Date());
      return true;
    } catch (error) {
      setBotsError(errorMessage(error));
      return false;
    } finally {
      if (!background) setBotsLoading(false);
    }
  }, []);

  const loadFilters = useCallback(async (background = false): Promise<boolean> => {
    if (!background) setFiltersLoading(true);
    try {
      const profiles = await api.getFilters();
      setFilters(profiles);
      setFiltersError(null);
      setFiltersUpdatedAt(new Date());
      return true;
    } catch (error) {
      setFiltersError(errorMessage(error));
      return false;
    } finally {
      if (!background) setFiltersLoading(false);
    }
  }, []);

  useEffect(() => {
    void Promise.all([loadApplications(), loadBots(), loadFilters()]);
  }, [loadApplications, loadBots, loadFilters]);

  useEffect(() => {
    const syncView = () => setView(viewFromHash());
    window.addEventListener('popstate', syncView);
    window.addEventListener('hashchange', syncView);
    return () => {
      window.removeEventListener('popstate', syncView);
      window.removeEventListener('hashchange', syncView);
    };
  }, []);

  useEffect(() => {
    const label = NAVIGATION.find((item) => item.id === view)?.label ?? 'Dashboard';
    document.title = `${label} · JobApply`;
  }, [view]);

  useEffect(() => {
    if (!notice || notice.kind === 'error') return;
    const timer = window.setTimeout(() => setNotice((current) => (
      current?.id === notice.id ? null : current
    )), 4_500);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const hasActiveBots = bots.some((bot) => bot.status === 'starting' || bot.status === 'running');

  useEffect(() => {
    if (!hasActiveBots) return;

    const poll = async () => {
      if (pollInFlight.current) return;
      pollInFlight.current = true;
      try {
        await Promise.all([loadBots(true), loadApplications(true)]);
      } finally {
        pollInFlight.current = false;
      }
    };

    const interval = window.setInterval(() => void poll(), 2_500);
    return () => window.clearInterval(interval);
  }, [hasActiveBots, loadApplications, loadBots]);

  const navigate = useCallback((nextView: AppView) => {
    setView(nextView);
    if (viewFromHash() !== nextView) {
      window.history.pushState(null, '', `#${nextView}`);
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, []);

  const refreshAll = async () => {
    setRefreshingAll(true);
    const results = await Promise.all([
      loadApplications(),
      loadBots(),
      loadFilters(),
    ]);
    setRefreshingAll(false);
    if (results.every(Boolean)) {
      notify('success', 'Workspace data is up to date.');
    } else {
      const failedResources = ['applications', 'bot activity', 'filter profiles']
        .filter((_, index) => !results[index]);
      notify('error', `Workspace refresh incomplete: ${failedResources.join(', ')} could not be loaded.`);
    }
  };

  const refreshApplications = async (): Promise<boolean> => {
    const successful = await loadApplications();
    if (successful) notify('success', 'Applications refreshed.');
    return successful;
  };

  const refreshBots = async (): Promise<boolean> => {
    const successful = await loadBots();
    if (successful) notify('success', 'Bot activity refreshed.');
    return successful;
  };

  const refreshFilters = async (): Promise<boolean> => {
    const successful = await loadFilters();
    if (successful) notify('success', 'Filter profiles refreshed.');
    return successful;
  };

  const handleExport = async (): Promise<boolean> => {
    if (applications.length === 0) {
      notify('error', 'There are no applications to export.');
      return false;
    }

    try {
      const blob = await api.exportApplications();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `applications-${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
      notify('success', 'CSV export downloaded.');
      return true;
    } catch (error) {
      const message = errorMessage(error);
      setApplicationsError(message);
      notify('error', `Export failed: ${message}`);
      return false;
    }
  };

  const handleClear = async (): Promise<boolean> => {
    if (applications.length === 0) return false;
    try {
      await api.clearApplications();
      setApplications([]);
      setApplicationsError(null);
      setApplicationsUpdatedAt(new Date());
      notify('success', 'Application history cleared.');
      return true;
    } catch (error) {
      const message = errorMessage(error);
      setApplicationsError(message);
      notify('error', `Could not clear applications: ${message}`);
      return false;
    }
  };

  const handleStartBot = async (config: BotConfig): Promise<BotRecord | null> => {
    try {
      const response = await api.startBot(config);
      setBots((current) => upsertBot(current, response.bot));
      setBotsError(null);
      setBotsUpdatedAt(new Date());
      notify('success', response.message);
      return response.bot;
    } catch (error) {
      const message = errorMessage(error);
      const failedBot = error instanceof ApiError ? error.payload?.bot : undefined;
      if (failedBot) {
        setBots((current) => upsertBot(current, failedBot));
        setBotsUpdatedAt(new Date());
      }
      setBotsError(message);
      notify('error', `Bot could not start: ${message}`);
      return null;
    }
  };

  const handleStopBot = async (id: string): Promise<BotRecord | null> => {
    try {
      const response = await api.stopBot(id);
      setBots((current) => upsertBot(current, response.bot));
      setBotsError(null);
      setBotsUpdatedAt(new Date());
      notify('success', response.message);
      void loadApplications(true);
      return response.bot;
    } catch (error) {
      const message = errorMessage(error);
      const failedBot = error instanceof ApiError ? error.payload?.bot : undefined;
      if (failedBot) {
        setBots((current) => upsertBot(current, failedBot));
        setBotsUpdatedAt(new Date());
      }
      setBotsError(message);
      notify('error', `Bot could not be stopped: ${message}`);
      return null;
    }
  };

  const handleSaveFilter = async (name: string, data: FilterData): Promise<boolean> => {
    try {
      const response = await api.saveFilter(name, data);
      setFilters((current) => {
        const withoutProfile = current.filter((profile) => profile.name !== response.name);
        return [...withoutProfile, { name: response.name, data }]
          .sort((a, b) => a.name.localeCompare(b.name));
      });
      setFiltersError(null);
      setFiltersUpdatedAt(new Date());
      notify('success', `Saved “${response.name}”.`);
      void loadFilters(true);
      return true;
    } catch (error) {
      const message = errorMessage(error);
      setFiltersError(message);
      notify('error', `Filter profile could not be saved: ${message}`);
      return false;
    }
  };

  const currentNavigation = NAVIGATION.find((item) => item.id === view) ?? NAVIGATION[0];
  const activeBotCount = bots.filter((bot) => bot.status === 'starting' || bot.status === 'running').length;
  const automationSummary = botsError
    ? 'Status unavailable'
    : activeBotCount === 0
      ? 'No active runs'
      : `${activeBotCount} active ${activeBotCount === 1 ? 'run' : 'runs'}`;
  const latestUpdatedAt = [applicationsUpdatedAt, botsUpdatedAt, filtersUpdatedAt]
    .filter((date): date is Date => date !== null)
    .sort((a, b) => b.getTime() - a.getTime())[0] ?? null;

  const resourceErrors: ResourceError[] = [];
  if ((view === 'dashboard' || view === 'applications') && applicationsError) {
    resourceErrors.push({
      key: 'applications',
      label: 'Applications unavailable',
      message: applicationsError,
      retry: () => loadApplications(),
    });
  }
  if ((view === 'dashboard' || view === 'bots') && botsError) {
    resourceErrors.push({
      key: 'bots',
      label: 'Bot activity unavailable',
      message: botsError,
      retry: () => loadBots(),
    });
  }
  if ((view === 'filters' || view === 'bots') && filtersError) {
    resourceErrors.push({
      key: 'filters',
      label: 'Filter profiles unavailable',
      message: filtersError,
      retry: () => loadFilters(),
    });
  }

  return (
    <div className="app-shell min-h-dvh text-slate-900">
      <a className="skip-link" href="#main-content">Skip to content</a>

      <aside className="sidebar hidden lg:flex">
        <div className="px-3 pb-8 pt-2 text-white">
          <BrandMark />
        </div>
        <nav aria-label="Primary navigation" className="space-y-2">
          {NAVIGATION.map((item) => {
            const Icon = item.icon;
            const selected = item.id === view;
            return (
              <button
                aria-current={selected ? 'page' : undefined}
                className={`sidebar-link ${selected ? 'sidebar-link-active' : ''}`}
                key={item.id}
                onClick={() => navigate(item.id)}
                type="button"
              >
                <span className="sidebar-icon"><Icon aria-hidden="true" className="size-[18px]" /></span>
                <span>
                  <span className="block text-sm font-bold">{item.label}</span>
                  <span className="mt-0.5 block text-[11px] text-violet-100/55">{item.description}</span>
                </span>
              </button>
            );
          })}
        </nav>
        <div className="sidebar-status mt-auto">
          <div className="flex items-center justify-between gap-3">
            <span className="text-xs font-semibold text-violet-100/70">Automation</span>
            {activeBotCount > 0 && !botsError && <span className="live-dot" aria-hidden="true" />}
          </div>
          <p className="mt-2 text-sm font-bold text-white">{automationSummary}</p>
          <p className="mt-1 text-[11px] leading-4 text-violet-100/55">{formatSyncTime(latestUpdatedAt)}</p>
        </div>
      </aside>

      <header className="mobile-header lg:hidden">
        <BrandMark compact />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-extrabold text-slate-950">{currentNavigation.label}</p>
          <p className="truncate text-[11px] text-slate-500">{currentNavigation.description}</p>
        </div>
        <button
          aria-label="Refresh workspace"
          className="icon-button"
          disabled={refreshingAll}
          onClick={() => void refreshAll()}
          type="button"
        >
          <RefreshCw aria-hidden="true" className={`size-4 ${refreshingAll ? 'animate-spin' : ''}`} />
        </button>
      </header>

      <div className="lg:pl-[264px]">
        <div className="desktop-toolbar hidden lg:flex">
          <div>
            <p className="text-sm font-extrabold text-slate-950">{currentNavigation.label}</p>
            <p className="mt-0.5 text-xs text-slate-500">{currentNavigation.description}</p>
          </div>
          <div className="ml-auto flex items-center gap-3">
            <div className="sync-copy text-right">
              <p className="text-xs font-bold text-slate-700">
                {botsError
                  ? 'Bot status unavailable'
                  : activeBotCount > 0
                    ? `${activeBotCount} live ${activeBotCount === 1 ? 'run' : 'runs'}`
                    : 'No active runs'}
              </p>
              <p className="mt-0.5 text-[11px] text-slate-500">{formatSyncTime(latestUpdatedAt)}</p>
            </div>
            <button
              className="button button-secondary"
              disabled={refreshingAll}
              onClick={() => void refreshAll()}
              type="button"
            >
              <RefreshCw aria-hidden="true" className={`size-4 ${refreshingAll ? 'animate-spin' : ''}`} />
              Refresh all
            </button>
          </div>
        </div>

        <main className="main-canvas" id="main-content" tabIndex={-1}>
          {resourceErrors.length > 0 && (
            <div className="mb-5 space-y-2">
              {resourceErrors.map((error) => (
                <div className="error-banner" key={error.key} role="alert">
                  <div className="min-w-0">
                    <p className="text-sm font-extrabold text-rose-950">{error.label}</p>
                    <p className="mt-0.5 break-words text-xs leading-5 text-rose-800">{error.message}</p>
                  </div>
                  <button className="button button-error-ghost" onClick={() => void error.retry()} type="button">Retry</button>
                </div>
              ))}
            </div>
          )}

          {view === 'dashboard' && (
            <Suspense fallback={(
              <div className="hero-panel flex min-h-[300px] items-center justify-center" role="status">
                <div className="text-center">
                  <RefreshCw aria-hidden="true" className="mx-auto size-5 animate-spin text-violet-500" />
                  <p className="mt-3 text-xs font-bold text-slate-500">Loading dashboard…</p>
                </div>
              </div>
            )}>
              <Dashboard
                applications={applications}
                bots={bots}
                loading={applicationsLoading || botsLoading}
                onNavigate={navigate}
              />
            </Suspense>
          )}
          {view === 'applications' && (
            <ApplicationsTable
              applications={applications}
              loading={applicationsLoading}
              onClear={handleClear}
              onExport={handleExport}
              onRefresh={refreshApplications}
            />
          )}
          {view === 'filters' && (
            <FiltersView
              loading={filtersLoading}
              onRefresh={refreshFilters}
              onSave={handleSaveFilter}
              profiles={filters}
            />
          )}
          {view === 'bots' && (
            <BotControlCenter
              bots={bots}
              filters={filters}
              filtersLoading={filtersLoading}
              loading={botsLoading}
              onNavigateFilters={() => navigate('filters')}
              onRefresh={refreshBots}
              onStart={handleStartBot}
              onStop={handleStopBot}
              polling={hasActiveBots}
            />
          )}
        </main>
      </div>

      <nav aria-label="Mobile navigation" className="mobile-navigation lg:hidden">
        {NAVIGATION.map((item) => {
          const Icon = item.icon;
          const selected = item.id === view;
          return (
            <button
              aria-current={selected ? 'page' : undefined}
              className={`mobile-nav-link ${selected ? 'mobile-nav-link-active' : ''}`}
              key={item.id}
              onClick={() => navigate(item.id)}
              type="button"
            >
              <Icon aria-hidden="true" className="size-[19px]" />
              <span>{item.shortLabel}</span>
            </button>
          );
        })}
      </nav>

      {notice && (
        <div
          className={`notice notice-${notice.kind}`}
          key={notice.id}
          role={notice.kind === 'error' ? 'alert' : 'status'}
        >
          <span className="min-w-0 flex-1 text-sm font-bold leading-5">{notice.message}</span>
          <button aria-label="Dismiss message" className="notice-close" onClick={() => setNotice(null)} type="button">
            <X aria-hidden="true" className="size-4" />
          </button>
        </div>
      )}
    </div>
  );
}
