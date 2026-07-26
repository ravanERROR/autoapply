import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  ArrowRight,
  Bot,
  BriefcaseBusiness,
  Check,
  CircleDashed,
  Loader2,
  Radar,
  Sparkles,
  Target,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import type { Application, AppView, BotRecord } from '../types';
import { PLATFORMS } from '../types';

interface DashboardProps {
  applications: Application[];
  bots: BotRecord[];
  loading: boolean;
  onNavigate: (view: AppView) => void;
}

const PLATFORM_COLORS: Record<string, string> = {
  linkedin: '#5b65f5',
  naukri: '#09a7a1',
  indeed: '#4865d9',
  glassdoor: '#2fb675',
  foundit: '#f27845',
};

const STATUS_COLORS = {
  Applied: '#18a873',
  Pending: '#e6a52c',
  Failed: '#e45e68',
  Skipped: '#98a2b3',
};

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Time unavailable';
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(date);
}

function MetricCard({
  icon: Icon,
  label,
  value,
  detail,
  tone,
}: {
  icon: LucideIcon;
  label: string;
  value: string | number;
  detail: string;
  tone: 'violet' | 'mint' | 'amber' | 'blue';
}) {
  const tones = {
    violet: 'bg-violet-100 text-violet-700',
    mint: 'bg-emerald-100 text-emerald-700',
    amber: 'bg-amber-100 text-amber-700',
    blue: 'bg-blue-100 text-blue-700',
  };

  return (
    <article className="surface-card metric-card min-w-0">
      <div className={`flex size-10 shrink-0 items-center justify-center rounded-2xl ${tones[tone]}`}>
        <Icon aria-hidden="true" className="size-5" />
      </div>
      <div className="min-w-0">
        <p className="text-xs font-bold uppercase tracking-[0.14em] text-slate-500">{label}</p>
        <p className="mt-1 font-display text-3xl font-semibold tracking-[-0.04em] text-slate-950">{value}</p>
        <p className="mt-1 truncate text-xs text-slate-500">{detail}</p>
      </div>
    </article>
  );
}

function EmptyChart({ label }: { label: string }) {
  return (
    <div className="flex h-[250px] flex-col items-center justify-center rounded-2xl border border-dashed border-slate-200 bg-slate-50/70 text-center">
      <div className="flex size-11 items-center justify-center rounded-2xl bg-white text-slate-400 shadow-sm">
        <CircleDashed aria-hidden="true" className="size-5" />
      </div>
      <p className="mt-3 text-sm font-semibold text-slate-700">No chart data yet</p>
      <p className="mt-1 max-w-52 text-xs leading-5 text-slate-500">{label}</p>
    </div>
  );
}

function LoadingBlock({ label, tall = false }: { label: string; tall?: boolean }) {
  return (
    <div className={`flex flex-col items-center justify-center text-center ${tall ? 'h-[250px]' : 'py-10'}`} role="status">
      <Loader2 aria-hidden="true" className="size-5 animate-spin text-violet-500" />
      <p className="mt-3 text-xs font-bold text-slate-500">{label}</p>
    </div>
  );
}

export function Dashboard({ applications, bots, loading, onNavigate }: DashboardProps) {
  const applied = applications.filter((application) => application.status === 'applied').length;
  const pending = applications.filter((application) => application.status === 'pending').length;
  const failed = applications.filter((application) => application.status === 'failed').length;
  const skipped = applications.filter((application) => application.status === 'skipped').length;
  const liveBots = bots.filter((bot) => bot.status === 'starting' || bot.status === 'running');
  const successRate = applications.length === 0 ? 0 : Math.round((applied / applications.length) * 100);

  const platformData = PLATFORMS.map((platform) => ({
    platform: platform.charAt(0).toUpperCase() + platform.slice(1),
    count: applications.filter((application) => application.platform === platform).length,
    fill: PLATFORM_COLORS[platform],
  })).filter((item) => item.count > 0);

  const statusData = [
    { name: 'Applied', value: applied, color: STATUS_COLORS.Applied },
    { name: 'Pending', value: pending, color: STATUS_COLORS.Pending },
    { name: 'Failed', value: failed, color: STATUS_COLORS.Failed },
    { name: 'Skipped', value: skipped, color: STATUS_COLORS.Skipped },
  ].filter((item) => item.value > 0);

  const recentApplications = [...applications]
    .sort((a, b) => new Date(b.appliedAt || b.timestamp).getTime() - new Date(a.appliedAt || a.timestamp).getTime())
    .slice(0, 5);
  const recentBots = [...bots]
    .sort((a, b) => new Date(b.startedAt).getTime() - new Date(a.startedAt).getTime())
    .slice(0, 4);

  return (
    <div className="page-enter space-y-6">
      <header className="hero-panel overflow-hidden">
        <div className="relative z-10 max-w-2xl">
          <div className="eyebrow text-violet-700">
            <Sparkles aria-hidden="true" className="size-3.5" />
            Workspace overview
          </div>
          <h1 className="mt-4 font-display text-3xl font-semibold leading-tight tracking-[-0.04em] text-slate-950 sm:text-4xl">
            Your search, in motion.
          </h1>
          <p className="mt-3 max-w-xl text-sm leading-6 text-slate-600 sm:text-base">
            Track every application, watch live runs, and keep your next move focused.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <button className="button button-primary" onClick={() => onNavigate('bots')} type="button">
              <Bot aria-hidden="true" className="size-4" />
              Configure a run
            </button>
            <button className="button button-secondary" onClick={() => onNavigate('applications')} type="button">
              View applications
              <ArrowRight aria-hidden="true" className="size-4" />
            </button>
          </div>
        </div>
        <div aria-hidden="true" className="hero-orbit">
          <div className="hero-orbit-core"><Radar className="size-8" /></div>
        </div>
      </header>

      <section aria-label="Application summary" className="grid grid-cols-2 gap-3 lg:grid-cols-4 lg:gap-4">
        <MetricCard
          detail={applications.length === 1 ? '1 recorded opportunity' : `${applications.length} recorded opportunities`}
          icon={BriefcaseBusiness}
          label="Applications"
          tone="violet"
          value={loading ? '—' : applications.length}
        />
        <MetricCard
          detail={applied === 1 ? '1 submitted application' : `${applied} submitted applications`}
          icon={Check}
          label="Applied"
          tone="mint"
          value={loading ? '—' : applied}
        />
        <MetricCard
          detail={applications.length === 0 ? 'Waiting for your first result' : `${failed} failed · ${skipped} skipped`}
          icon={Target}
          label="Applied rate"
          tone="amber"
          value={loading ? '—' : `${successRate}%`}
        />
        <MetricCard
          detail={liveBots.length > 0 ? 'Records refresh automatically' : 'No run in progress'}
          icon={Bot}
          label="Live bots"
          tone="blue"
          value={loading ? '—' : liveBots.length}
        />
      </section>

      <section className="grid min-w-0 gap-4 xl:grid-cols-[1.25fr_0.75fr]">
        <article className="surface-card min-w-0 p-4 sm:p-5">
          <div className="mb-4 flex items-start justify-between gap-4">
            <div>
              <p className="section-kicker">Distribution</p>
              <h2 className="section-title">Applications by platform</h2>
            </div>
            <span className="data-pill">{applications.length} total</span>
          </div>
          {loading && applications.length === 0 ? (
            <LoadingBlock label="Loading application totals…" tall />
          ) : platformData.length === 0 ? (
            <EmptyChart label="Platform activity will appear after applications are recorded." />
          ) : (
            <div aria-label={`Bar chart of ${applications.length} applications by platform`} className="h-[250px] min-w-0" role="img">
              <ResponsiveContainer height="100%" width="100%">
                <BarChart data={platformData} margin={{ top: 8, right: 4, left: -24, bottom: 0 }}>
                  <CartesianGrid stroke="#e8eaf1" strokeDasharray="4 4" vertical={false} />
                  <XAxis axisLine={false} dataKey="platform" fontSize={11} tick={{ fill: '#667085' }} tickLine={false} />
                  <YAxis allowDecimals={false} axisLine={false} fontSize={11} tick={{ fill: '#98a2b3' }} tickLine={false} />
                  <Tooltip
                    contentStyle={{ border: '1px solid #e8eaf1', borderRadius: 14, boxShadow: '0 14px 34px rgba(25, 28, 49, .12)' }}
                    cursor={{ fill: '#f4f3ff' }}
                  />
                  <Bar dataKey="count" radius={[8, 8, 2, 2]}>
                    {platformData.map((entry) => <Cell fill={entry.fill} key={entry.platform} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </article>

        <article className="surface-card min-w-0 p-4 sm:p-5">
          <div className="mb-4">
            <p className="section-kicker">Outcome</p>
            <h2 className="section-title">Status mix</h2>
          </div>
          {loading && applications.length === 0 ? (
            <LoadingBlock label="Loading application outcomes…" tall />
          ) : statusData.length === 0 ? (
            <EmptyChart label="Application outcomes will be shown here without rendering an empty chart." />
          ) : (
            <div className="grid min-h-[250px] grid-cols-[minmax(0,1fr)_auto] items-center gap-2">
              <div aria-label={`Donut chart showing ${applications.length} application outcomes`} className="h-[220px] min-w-0" role="img">
                <ResponsiveContainer height="100%" width="100%">
                  <PieChart>
                    <Pie
                      cx="50%"
                      cy="50%"
                      data={statusData}
                      dataKey="value"
                      innerRadius={58}
                      nameKey="name"
                      outerRadius={86}
                      paddingAngle={3}
                      stroke="none"
                    >
                      {statusData.map((entry) => <Cell fill={entry.color} key={entry.name} />)}
                    </Pie>
                    <Tooltip
                      contentStyle={{ border: '1px solid #e8eaf1', borderRadius: 14, boxShadow: '0 14px 34px rgba(25, 28, 49, .12)' }}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <ul aria-label="Application status totals" className="space-y-3 pr-2 text-sm">
                {statusData.map((entry) => (
                  <li className="flex items-center gap-2" key={entry.name}>
                    <span className="size-2.5 rounded-full" style={{ backgroundColor: entry.color }} />
                    <span className="text-slate-600">{entry.name}</span>
                    <strong className="ml-auto text-slate-900">{entry.value}</strong>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </article>
      </section>

      <section className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
        <article className="surface-card overflow-hidden p-0">
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-4 sm:px-5">
            <div>
              <p className="section-kicker">Latest activity</p>
              <h2 className="section-title">Recent applications</h2>
            </div>
            <button className="text-button" onClick={() => onNavigate('applications')} type="button">
              View all <ArrowRight aria-hidden="true" className="size-3.5" />
            </button>
          </div>
          {loading && applications.length === 0 ? (
            <LoadingBlock label="Loading recent applications…" />
          ) : recentApplications.length === 0 ? (
            <div className="px-5 py-10 text-center">
              <BriefcaseBusiness aria-hidden="true" className="mx-auto size-6 text-slate-300" />
              <p className="mt-3 text-sm font-semibold text-slate-700">Nothing recorded yet</p>
              <p className="mt-1 text-xs text-slate-500">Start a bot when your filters are ready.</p>
            </div>
          ) : (
            <ul className="divide-y divide-slate-100">
              {recentApplications.map((application, index) => (
                <li className="flex min-w-0 items-center gap-3 px-4 py-3.5 sm:px-5" key={`${application.id || 'application'}-${application.timestamp}-${index}`}>
                  <div className="platform-mark" data-platform={application.platform}>
                    {application.platform.slice(0, 1).toUpperCase()}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold text-slate-900">{application.jobTitle || 'Untitled role'}</p>
                    <p className="mt-0.5 truncate text-xs text-slate-500">
                      {application.company || 'Company not listed'} · {formatDate(application.appliedAt || application.timestamp)}
                    </p>
                  </div>
                  <span className={`status-badge status-${application.status}`}>{application.status}</span>
                </li>
              ))}
            </ul>
          )}
        </article>

        <article className="surface-card overflow-hidden p-0">
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-4 sm:px-5">
            <div>
              <p className="section-kicker">Automation</p>
              <h2 className="section-title">Bot status</h2>
            </div>
            {liveBots.length > 0 && <span className="live-pill"><span />Live</span>}
          </div>
          {loading && bots.length === 0 ? (
            <LoadingBlock label="Loading bot activity…" />
          ) : recentBots.length === 0 ? (
            <div className="px-5 py-10 text-center">
              <Bot aria-hidden="true" className="mx-auto size-6 text-slate-300" />
              <p className="mt-3 text-sm font-semibold text-slate-700">No bot history</p>
              <button className="text-button mx-auto mt-2" onClick={() => onNavigate('bots')} type="button">Set up a run</button>
            </div>
          ) : (
            <ul className="divide-y divide-slate-100">
              {recentBots.map((bot) => (
                <li className="flex items-center gap-3 px-4 py-3.5 sm:px-5" key={bot.id}>
                  <div className={`bot-state-icon bot-state-${bot.status}`}>
                    <Bot aria-hidden="true" className="size-4" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold capitalize text-slate-900">{bot.platform}</p>
                    <p className="mt-0.5 truncate text-xs text-slate-500">Started {formatDate(bot.startedAt)}</p>
                  </div>
                  <span className={`status-badge status-${bot.status}`}>{bot.status}</span>
                </li>
              ))}
            </ul>
          )}
        </article>
      </section>
    </div>
  );
}
