import { useEffect, useMemo, useRef, useState } from 'react';
import {
  BriefcaseBusiness,
  Download,
  ExternalLink,
  Loader2,
  RefreshCw,
  Search,
  Trash2,
  X,
} from 'lucide-react';
import type { Application, ApplicationStatus } from '../types';

interface ApplicationsTableProps {
  applications: Application[];
  loading: boolean;
  onClear: () => Promise<boolean>;
  onExport: () => Promise<boolean>;
  onRefresh: () => Promise<boolean>;
}

type StatusFilter = 'all' | ApplicationStatus;
type PendingAction = 'refresh' | 'export' | null;

const STATUS_OPTIONS: Array<{ value: StatusFilter; label: string }> = [
  { value: 'all', label: 'All' },
  { value: 'applied', label: 'Applied' },
  { value: 'pending', label: 'Pending' },
  { value: 'failed', label: 'Failed' },
  { value: 'skipped', label: 'Skipped' },
];

function formatTime(value: string): string {
  if (!value) return 'Time unavailable';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Time unavailable';
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date);
}

function timestampOf(application: Application): number {
  const value = new Date(application.appliedAt || application.timestamp).getTime();
  return Number.isNaN(value) ? 0 : value;
}

function safeJobUrl(value: string): string | null {
  if (!value) return null;
  try {
    const url = new URL(value, window.location.origin);
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.href : null;
  } catch {
    return null;
  }
}

function ClearConfirmation({
  count,
  onCancel,
  onConfirm,
}: {
  count: number;
  onCancel: () => void;
  onConfirm: () => Promise<boolean>;
}) {
  const [clearing, setClearing] = useState(false);
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !clearing) {
        onCancel();
        return;
      }
      if (event.key !== 'Tab' || !dialogRef.current) return;
      const focusable = Array.from(dialogRef.current.querySelectorAll<HTMLElement>(
        'button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])',
      ));
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    window.addEventListener('keydown', onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', onKeyDown);
    };
  }, [clearing, onCancel]);

  const confirm = async () => {
    setClearing(true);
    const successful = await onConfirm();
    setClearing(false);
    if (successful) onCancel();
  };

  return (
    <div className="modal-backdrop" role="presentation">
      <div
        aria-describedby="clear-applications-description"
        aria-labelledby="clear-applications-title"
        aria-modal="true"
        className="modal-card"
        ref={dialogRef}
        role="alertdialog"
      >
        <button
          aria-label="Close confirmation"
          className="icon-button absolute right-4 top-4"
          disabled={clearing}
          onClick={onCancel}
          type="button"
        >
          <X aria-hidden="true" className="size-4" />
        </button>
        <div className="flex size-12 items-center justify-center rounded-2xl bg-rose-100 text-rose-700">
          <Trash2 aria-hidden="true" className="size-5" />
        </div>
        <h2 className="mt-5 font-display text-2xl font-semibold tracking-[-0.03em] text-slate-950" id="clear-applications-title">
          Clear application history?
        </h2>
        <p className="mt-2 text-sm leading-6 text-slate-600" id="clear-applications-description">
          This permanently removes {count} recorded {count === 1 ? 'application' : 'applications'} from the server CSV. This action cannot be undone.
        </p>
        <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <button autoFocus className="button button-secondary" disabled={clearing} onClick={onCancel} type="button">
            Keep history
          </button>
          <button className="button button-danger" disabled={clearing} onClick={() => void confirm()} type="button">
            {clearing ? <Loader2 aria-hidden="true" className="size-4 animate-spin" /> : <Trash2 aria-hidden="true" className="size-4" />}
            {clearing ? 'Clearing…' : 'Yes, clear all'}
          </button>
        </div>
      </div>
    </div>
  );
}

export function ApplicationsTable({
  applications,
  loading,
  onClear,
  onExport,
  onRefresh,
}: ApplicationsTableProps) {
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [pendingAction, setPendingAction] = useState<PendingAction>(null);
  const [confirmClear, setConfirmClear] = useState(false);

  const filteredApplications = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase();
    return [...applications]
      .filter((application) => statusFilter === 'all' || application.status === statusFilter)
      .filter((application) => {
        if (!normalizedQuery) return true;
        return [
          application.jobTitle,
          application.company,
          application.location,
          application.platform,
          application.notes,
        ].some((value) => value.toLocaleLowerCase().includes(normalizedQuery));
      })
      .sort((a, b) => timestampOf(b) - timestampOf(a));
  }, [applications, query, statusFilter]);

  const runAction = async (action: Exclude<PendingAction, null>) => {
    setPendingAction(action);
    if (action === 'refresh') await onRefresh();
    if (action === 'export') await onExport();
    setPendingAction(null);
  };

  const hasFilters = query.trim().length > 0 || statusFilter !== 'all';
  const appliedCount = applications.filter((application) => application.status === 'applied').length;

  return (
    <div className="page-enter space-y-5">
      <header className="page-heading">
        <div>
          <div className="eyebrow text-violet-700">
            <BriefcaseBusiness aria-hidden="true" className="size-3.5" />
            Application ledger
          </div>
          <h1 className="mt-3 font-display text-3xl font-semibold tracking-[-0.04em] text-slate-950 sm:text-4xl">Every move, accounted for.</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
            Search recorded opportunities, inspect outcomes, or take a clean CSV snapshot.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            className="button button-secondary"
            disabled={pendingAction !== null || loading}
            onClick={() => void runAction('refresh')}
            type="button"
          >
            <RefreshCw aria-hidden="true" className={`size-4 ${pendingAction === 'refresh' ? 'animate-spin' : ''}`} />
            Refresh
          </button>
          <button
            className="button button-primary"
            disabled={applications.length === 0 || pendingAction !== null}
            onClick={() => void runAction('export')}
            type="button"
          >
            {pendingAction === 'export'
              ? <Loader2 aria-hidden="true" className="size-4 animate-spin" />
              : <Download aria-hidden="true" className="size-4" />}
            Export CSV
          </button>
        </div>
      </header>

      <section aria-label="Application totals" className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <div className="summary-tile">
          <p className="summary-label">Recorded</p>
          <p className="summary-value">{loading ? '—' : applications.length}</p>
        </div>
        <div className="summary-tile">
          <p className="summary-label">Applied</p>
          <p className="summary-value text-emerald-700">{loading ? '—' : appliedCount}</p>
        </div>
        <div className="summary-tile col-span-2 sm:col-span-1">
          <p className="summary-label">Visible now</p>
          <p className="summary-value text-violet-700">{loading ? '—' : filteredApplications.length}</p>
        </div>
      </section>

      <section className="surface-card overflow-hidden p-0" aria-busy={loading}>
        <div className="border-b border-slate-100 p-4 sm:p-5">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
            <label className="search-field flex-1">
              <Search aria-hidden="true" className="size-4 shrink-0 text-slate-400" />
              <span className="sr-only">Search applications</span>
              <input
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search role, company, location…"
                type="search"
                value={query}
              />
            </label>
            <div aria-label="Filter by status" className="filter-tabs" role="group">
              {STATUS_OPTIONS.map((option) => (
                <button
                  aria-pressed={statusFilter === option.value}
                  className={statusFilter === option.value ? 'filter-tab-active' : ''}
                  key={option.value}
                  onClick={() => setStatusFilter(option.value)}
                  type="button"
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {loading && applications.length === 0 ? (
          <div className="empty-state py-16">
            <Loader2 aria-hidden="true" className="size-6 animate-spin text-violet-500" />
            <p className="mt-3 text-sm font-bold text-slate-700">Loading applications…</p>
          </div>
        ) : filteredApplications.length === 0 ? (
          <div className="empty-state py-16">
            <div className="empty-state-icon"><BriefcaseBusiness aria-hidden="true" className="size-5" /></div>
            <p className="mt-4 text-sm font-extrabold text-slate-800">
              {hasFilters ? 'No applications match' : 'No applications recorded'}
            </p>
            <p className="mt-1 max-w-sm text-xs leading-5 text-slate-500">
              {hasFilters
                ? 'Try another search or status filter.'
                : 'Completed bot activity will appear here when the server records it.'}
            </p>
            {hasFilters && (
              <button
                className="text-button mt-3"
                onClick={() => { setQuery(''); setStatusFilter('all'); }}
                type="button"
              >
                Clear filters
              </button>
            )}
          </div>
        ) : (
          <>
            <div className="hidden overflow-x-auto md:block">
              <table className="data-table">
                <caption className="sr-only">Recorded job applications</caption>
                <thead>
                  <tr>
                    <th scope="col">Opportunity</th>
                    <th scope="col">Platform</th>
                    <th scope="col">Location</th>
                    <th scope="col">Recorded</th>
                    <th scope="col">Status</th>
                    <th className="w-12" scope="col"><span className="sr-only">Open job</span></th>
                  </tr>
                </thead>
                <tbody>
                  {filteredApplications.map((application, index) => {
                    const jobUrl = safeJobUrl(application.jobUrl);
                    return (
                      <tr key={`${application.id || 'application'}-${application.timestamp}-${index}`}>
                        <td>
                          <p className="max-w-[280px] truncate font-bold text-slate-900">{application.jobTitle || 'Untitled role'}</p>
                          <p className="mt-1 max-w-[280px] truncate text-xs text-slate-500">{application.company || 'Company not listed'}</p>
                        </td>
                        <td>
                          <div className="flex items-center gap-2">
                            <span className="platform-mark size-7 text-[10px]" data-platform={application.platform}>
                              {application.platform.slice(0, 1).toUpperCase()}
                            </span>
                            <span className="capitalize">{application.platform}</span>
                          </div>
                        </td>
                        <td><span className="block max-w-[180px] truncate">{application.location || 'Not listed'}</span></td>
                        <td className="whitespace-nowrap">{formatTime(application.appliedAt || application.timestamp)}</td>
                        <td><span className={`status-badge status-${application.status}`}>{application.status}</span></td>
                        <td>
                          {jobUrl ? (
                            <a
                              aria-label={`Open ${application.jobTitle || 'job'} in a new tab`}
                              className="table-link"
                              href={jobUrl}
                              rel="noreferrer"
                              target="_blank"
                            >
                              <ExternalLink aria-hidden="true" className="size-4" />
                            </a>
                          ) : <span className="text-slate-300">—</span>}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <ul className="divide-y divide-slate-100 md:hidden">
              {filteredApplications.map((application, index) => {
                const jobUrl = safeJobUrl(application.jobUrl);
                return (
                  <li className="p-4" key={`${application.id || 'application'}-${application.timestamp}-${index}`}>
                    <div className="flex items-start gap-3">
                      <span className="platform-mark" data-platform={application.platform}>
                        {application.platform.slice(0, 1).toUpperCase()}
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <p className="truncate text-sm font-extrabold text-slate-900">{application.jobTitle || 'Untitled role'}</p>
                            <p className="mt-0.5 truncate text-xs text-slate-500">{application.company || 'Company not listed'}</p>
                          </div>
                          {jobUrl && (
                            <a
                              aria-label={`Open ${application.jobTitle || 'job'} in a new tab`}
                              className="table-link shrink-0"
                              href={jobUrl}
                              rel="noreferrer"
                              target="_blank"
                            >
                              <ExternalLink aria-hidden="true" className="size-4" />
                            </a>
                          )}
                        </div>
                        <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
                          <span className={`status-badge status-${application.status}`}>{application.status}</span>
                          <span className="capitalize">{application.platform}</span>
                          <span aria-hidden="true">·</span>
                          <span>{application.location || 'Location not listed'}</span>
                        </div>
                        <p className="mt-2 text-[11px] text-slate-400">{formatTime(application.appliedAt || application.timestamp)}</p>
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          </>
        )}

        <div className="flex flex-col gap-3 border-t border-slate-100 bg-slate-50/60 px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-5">
          <p className="text-xs text-slate-500">
            Showing <strong className="text-slate-700">{filteredApplications.length}</strong> of {applications.length}
          </p>
          <button
            className="text-button text-rose-700 hover:text-rose-800"
            disabled={applications.length === 0 || pendingAction !== null}
            onClick={() => setConfirmClear(true)}
            type="button"
          >
            <Trash2 aria-hidden="true" className="size-3.5" />
            Clear history
          </button>
        </div>
      </section>

      {confirmClear && (
        <ClearConfirmation count={applications.length} onCancel={() => setConfirmClear(false)} onConfirm={onClear} />
      )}
    </div>
  );
}
