import { useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertCircle,
  Braces,
  ChevronRight,
  FileSliders,
  Loader2,
  MapPin,
  Plus,
  RefreshCw,
  Save,
  Search,
  Tags,
} from 'lucide-react';
import { PLATFORMS } from '../types';
import type { FilterData, FilterProfile, Platform } from '../types';

interface FiltersViewProps {
  profiles: FilterProfile[];
  loading: boolean;
  onRefresh: () => Promise<boolean>;
  onSave: (name: string, data: FilterData) => Promise<boolean>;
}

const PROFILE_NAME_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/;
const COMMON_FIELDS = new Set([
  'platform',
  'keywords',
  'locations',
  'excludeKeywords',
  'experienceMin',
  'experienceMax',
  'postedWithinDays',
  'easyApplyOnly',
  'remoteOnly',
  'strictKeywordMatch',
]);

function cloneData(data: FilterData): FilterData {
  return JSON.parse(JSON.stringify(data)) as FilterData;
}

function formatJson(data: FilterData): string {
  return JSON.stringify(data, null, 2);
}

function listText(value: unknown): string {
  if (!Array.isArray(value)) return '';
  return value.filter((item): item is string => typeof item === 'string').join(', ');
}

function parseList(value: string): string[] | undefined {
  const items = value
    .split(/[,\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
  return items.length > 0 ? Array.from(new Set(items)) : undefined;
}

function numberValue(value: unknown): number | '' {
  return typeof value === 'number' && Number.isFinite(value) ? value : '';
}

function parseJsonObject(value: string): { data?: FilterData; error?: string } {
  try {
    const parsed = JSON.parse(value) as unknown;
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return { error: 'Filter JSON must be an object, not an array or primitive value.' };
    }
    return { data: parsed as FilterData };
  } catch (error) {
    return { error: error instanceof Error ? error.message : 'Invalid JSON.' };
  }
}

function profileSummary(profile: FilterProfile): string {
  const keywordCount = Array.isArray(profile.data.keywords)
    ? profile.data.keywords.filter((item) => typeof item === 'string').length
    : 0;
  const locationCount = Array.isArray(profile.data.locations)
    ? profile.data.locations.filter((item) => typeof item === 'string').length
    : 0;
  const parts = [];
  if (typeof profile.data.platform === 'string') parts.push(profile.data.platform);
  if (keywordCount > 0) parts.push(`${keywordCount} ${keywordCount === 1 ? 'keyword' : 'keywords'}`);
  if (locationCount > 0) parts.push(`${locationCount} ${locationCount === 1 ? 'location' : 'locations'}`);
  return parts.join(' · ') || `${Object.keys(profile.data).length} saved fields`;
}

export function FiltersView({ profiles, loading, onRefresh, onSave }: FiltersViewProps) {
  const [selectedName, setSelectedName] = useState<string | null>(null);
  const [creating, setCreating] = useState(true);
  const [name, setName] = useState('');
  const [draft, setDraft] = useState<FilterData>({});
  const [rawText, setRawText] = useState('{}');
  const [keywordsText, setKeywordsText] = useState('');
  const [locationsText, setLocationsText] = useState('');
  const [excludeText, setExcludeText] = useState('');
  const [advanced, setAdvanced] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [profileQuery, setProfileQuery] = useState('');
  const initialized = useRef(false);

  const visibleProfiles = useMemo(() => {
    const query = profileQuery.trim().toLocaleLowerCase();
    if (!query) return profiles;
    return profiles.filter((profile) => profile.name.toLocaleLowerCase().includes(query));
  }, [profileQuery, profiles]);

  const extraFieldCount = Object.keys(draft).filter((key) => !COMMON_FIELDS.has(key)).length;

  const syncListFields = (data: FilterData) => {
    setKeywordsText(listText(data.keywords));
    setLocationsText(listText(data.locations));
    setExcludeText(listText(data.excludeKeywords));
  };

  useEffect(() => {
    if (loading || initialized.current) return;
    initialized.current = true;
    if (profiles.length === 0) return;
    const firstProfile = profiles[0];
    const data = cloneData(firstProfile.data);
    setSelectedName(firstProfile.name);
    setCreating(false);
    setName(firstProfile.name);
    setDraft(data);
    setRawText(formatJson(data));
    syncListFields(data);
  }, [loading, profiles]);

  useEffect(() => {
    if (creating || dirty || !selectedName) return;
    const profile = profiles.find((item) => item.name === selectedName);
    if (!profile) return;
    const data = cloneData(profile.data);
    setName(profile.name);
    setDraft(data);
    setRawText(formatJson(data));
    syncListFields(data);
  }, [creating, dirty, profiles, selectedName]);

  useEffect(() => {
    if (!dirty) return;
    const warnBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', warnBeforeUnload);
    return () => window.removeEventListener('beforeunload', warnBeforeUnload);
  }, [dirty]);

  const canDiscard = () => !dirty || window.confirm('Discard your unsaved filter changes?');

  const selectProfile = (profile: FilterProfile) => {
    if (!canDiscard()) return;
    const data = cloneData(profile.data);
    setSelectedName(profile.name);
    setCreating(false);
    setName(profile.name);
    setDraft(data);
    setRawText(formatJson(data));
    syncListFields(data);
    setAdvanced(false);
    setDirty(false);
    setFormError(null);
  };

  const createProfile = () => {
    if (!canDiscard()) return;
    setSelectedName(null);
    setCreating(true);
    setName('');
    setDraft({});
    setRawText('{}');
    syncListFields({});
    setAdvanced(false);
    setDirty(false);
    setFormError(null);
  };

  const updateField = (field: string, value: unknown) => {
    const next = { ...draft };
    if (value === undefined || value === '') delete next[field];
    else next[field] = value;
    setDraft(next);
    setRawText(formatJson(next));
    setDirty(true);
    setFormError(null);
  };

  const updateNumberField = (field: string, value: string) => {
    updateField(field, value === '' ? undefined : Number(value));
  };

  const toggleAdvanced = () => {
    if (!advanced) {
      setRawText(formatJson(draft));
      setAdvanced(true);
      setFormError(null);
      return;
    }

    const parsed = parseJsonObject(rawText);
    if (!parsed.data) {
      setFormError(parsed.error ?? 'Invalid JSON.');
      return;
    }
    setDraft(parsed.data);
    setRawText(formatJson(parsed.data));
    syncListFields(parsed.data);
    setAdvanced(false);
    setFormError(null);
  };

  const save = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const normalizedName = name.trim();
    if (!PROFILE_NAME_PATTERN.test(normalizedName)) {
      setFormError('Use 1–64 letters, numbers, underscores, or hyphens; begin with a letter or number.');
      return;
    }

    let data = draft;
    if (advanced) {
      const parsed = parseJsonObject(rawText);
      if (!parsed.data) {
        setFormError(parsed.error ?? 'Invalid JSON.');
        return;
      }
      data = parsed.data;
    }

    setSaving(true);
    setFormError(null);
    const successful = await onSave(normalizedName, data);
    setSaving(false);
    if (!successful) return;

    setSelectedName(normalizedName);
    setCreating(false);
    setName(normalizedName);
    setDraft(cloneData(data));
    setRawText(formatJson(data));
    syncListFields(data);
    setDirty(false);
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
            <FileSliders aria-hidden="true" className="size-3.5" />
            Search preferences
          </div>
          <h1 className="mt-3 font-display text-3xl font-semibold tracking-[-0.04em] text-slate-950 sm:text-4xl">Shape the search once.</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
            Build reusable profiles with clear common fields, while retaining every platform-specific JSON value.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button className="button button-secondary" disabled={refreshing || loading} onClick={() => void refresh()} type="button">
            <RefreshCw aria-hidden="true" className={`size-4 ${refreshing ? 'animate-spin' : ''}`} />
            Refresh
          </button>
          <button className="button button-primary" onClick={createProfile} type="button">
            <Plus aria-hidden="true" className="size-4" />
            New profile
          </button>
        </div>
      </header>

      <section className="surface-card grid min-h-[650px] overflow-hidden p-0 lg:grid-cols-[280px_minmax(0,1fr)]">
        <aside className="border-b border-slate-100 bg-slate-50/65 p-3 lg:border-b-0 lg:border-r" aria-label="Filter profiles">
          <label className="search-field bg-white">
            <Search aria-hidden="true" className="size-4 shrink-0 text-slate-400" />
            <span className="sr-only">Search filter profiles</span>
            <input
              onChange={(event) => setProfileQuery(event.target.value)}
              placeholder="Find a profile…"
              type="search"
              value={profileQuery}
            />
          </label>

          <button className={`new-profile-row ${creating ? 'new-profile-row-active' : ''}`} onClick={createProfile} type="button">
            <span className="flex size-8 items-center justify-center rounded-xl bg-violet-100 text-violet-700">
              <Plus aria-hidden="true" className="size-4" />
            </span>
            <span className="text-sm font-extrabold">Create new</span>
          </button>

          <div className="mt-2 max-h-64 space-y-1 overflow-y-auto lg:max-h-[530px]">
            {loading && profiles.length === 0 ? (
              <div className="flex items-center justify-center gap-2 px-3 py-10 text-xs text-slate-500">
                <Loader2 aria-hidden="true" className="size-4 animate-spin text-violet-500" />Loading profiles…
              </div>
            ) : visibleProfiles.length === 0 ? (
              <div className="px-3 py-10 text-center">
                <FileSliders aria-hidden="true" className="mx-auto size-5 text-slate-300" />
                <p className="mt-2 text-xs font-bold text-slate-600">
                  {profiles.length === 0 ? 'No saved profiles' : 'No profile matches'}
                </p>
              </div>
            ) : visibleProfiles.map((profile) => {
              const active = !creating && selectedName === profile.name;
              return (
                <button
                  aria-current={active ? 'true' : undefined}
                  className={`profile-row ${active ? 'profile-row-active' : ''}`}
                  key={profile.name}
                  onClick={() => selectProfile(profile)}
                  type="button"
                >
                  <span className="min-w-0 flex-1 text-left">
                    <span className="block truncate text-sm font-extrabold text-slate-800">{profile.name}</span>
                    <span className="mt-1 block truncate text-[10px] capitalize text-slate-500">{profileSummary(profile)}</span>
                  </span>
                  <ChevronRight aria-hidden="true" className="size-4 shrink-0 text-slate-300" />
                </button>
              );
            })}
          </div>
        </aside>

        <form className="min-w-0" onSubmit={(event) => void save(event)}>
          <div className="border-b border-slate-100 px-4 py-4 sm:px-6 sm:py-5">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <p className="section-kicker">{creating ? 'New profile' : 'Editing profile'}</p>
                  {dirty && <span className="unsaved-pill">Unsaved changes</span>}
                </div>
                <h2 className="section-title mt-1">{creating ? 'Define a reusable search' : selectedName}</h2>
              </div>
              <button className="button button-secondary" onClick={toggleAdvanced} type="button">
                <Braces aria-hidden="true" className="size-4" />
                {advanced ? 'Use form' : 'Edit raw JSON'}
              </button>
            </div>
          </div>

          <div className="p-4 sm:p-6">
            <label className="block max-w-xl">
              <span className="field-label">Profile name</span>
              <span className="field-hint">Letters, numbers, underscores, and hyphens only</span>
              <input
                aria-describedby="profile-name-help"
                className="field-input mt-2"
                maxLength={64}
                onChange={(event) => {
                  setName(event.target.value);
                  setDirty(true);
                  setFormError(null);
                }}
                placeholder="senior_frontend_remote"
                required
                spellCheck={false}
                type="text"
                value={name}
              />
              <span className="mt-1.5 block text-[11px] leading-4 text-slate-400" id="profile-name-help">
                Changing an existing name saves a new profile; the API has no delete endpoint.
              </span>
            </label>

            {advanced ? (
              <div className="mt-6">
                <div className="mb-2 flex items-end justify-between gap-3">
                  <div>
                    <p className="field-label">Raw filter object</p>
                    <p className="field-hint">Sent directly as the POST request body</p>
                  </div>
                  <span className="data-pill">JSON</span>
                </div>
                <textarea
                  aria-label="Raw filter JSON"
                  className="json-editor"
                  onChange={(event) => {
                    setRawText(event.target.value);
                    setDirty(true);
                    setFormError(null);
                  }}
                  spellCheck={false}
                  value={rawText}
                />
              </div>
            ) : (
              <div className="mt-7 space-y-7">
                <fieldset>
                  <legend className="section-kicker">Search foundation</legend>
                  <div className="mt-3 grid gap-4 md:grid-cols-2">
                    <label>
                      <span className="field-label"><Tags aria-hidden="true" className="mr-1.5 inline size-3.5" />Keywords</span>
                      <span className="field-hint">Comma or line separated</span>
                      <textarea
                        className="field-textarea mt-2 min-h-24"
                        onChange={(event) => {
                          setKeywordsText(event.target.value);
                          updateField('keywords', parseList(event.target.value));
                        }}
                        placeholder="frontend engineer, react, typescript"
                        value={keywordsText}
                      />
                    </label>
                    <label>
                      <span className="field-label"><MapPin aria-hidden="true" className="mr-1.5 inline size-3.5" />Locations</span>
                      <span className="field-hint">Comma or line separated</span>
                      <textarea
                        className="field-textarea mt-2 min-h-24"
                        onChange={(event) => {
                          setLocationsText(event.target.value);
                          updateField('locations', parseList(event.target.value));
                        }}
                        placeholder="Bengaluru, Remote"
                        value={locationsText}
                      />
                    </label>
                    <label>
                      <span className="field-label">Exclude keywords</span>
                      <span className="field-hint">Roles or terms to skip</span>
                      <input
                        className="field-input mt-2"
                        onChange={(event) => {
                          setExcludeText(event.target.value);
                          updateField('excludeKeywords', parseList(event.target.value));
                        }}
                        placeholder="intern, contract"
                        type="text"
                        value={excludeText}
                      />
                    </label>
                    <label>
                      <span className="field-label">Platform</span>
                      <span className="field-hint">Optional profile scope</span>
                      <select
                        className="field-select mt-2 capitalize"
                        onChange={(event) => updateField('platform', event.target.value ? event.target.value as Platform : undefined)}
                        value={typeof draft.platform === 'string' ? draft.platform : ''}
                      >
                        <option value="">Any platform</option>
                        {PLATFORMS.map((platform) => <option key={platform} value={platform}>{platform}</option>)}
                      </select>
                    </label>
                  </div>
                </fieldset>

                <fieldset>
                  <legend className="section-kicker">Range and recency</legend>
                  <div className="mt-3 grid gap-4 sm:grid-cols-3">
                    <label>
                      <span className="field-label">Min experience</span>
                      <span className="field-hint">Years</span>
                      <input
                        className="field-input mt-2"
                        min={0}
                        onChange={(event) => updateNumberField('experienceMin', event.target.value)}
                        type="number"
                        value={numberValue(draft.experienceMin)}
                      />
                    </label>
                    <label>
                      <span className="field-label">Max experience</span>
                      <span className="field-hint">Years</span>
                      <input
                        className="field-input mt-2"
                        min={0}
                        onChange={(event) => updateNumberField('experienceMax', event.target.value)}
                        type="number"
                        value={numberValue(draft.experienceMax)}
                      />
                    </label>
                    <label>
                      <span className="field-label">Posted within</span>
                      <span className="field-hint">Days</span>
                      <input
                        className="field-input mt-2"
                        min={0}
                        onChange={(event) => updateNumberField('postedWithinDays', event.target.value)}
                        type="number"
                        value={numberValue(draft.postedWithinDays)}
                      />
                    </label>
                  </div>
                </fieldset>

                <fieldset>
                  <legend className="section-kicker">Application preferences</legend>
                  <div className="mt-3 grid gap-2 sm:grid-cols-3">
                    {([
                      ['easyApplyOnly', 'Easy apply only', 'Prioritize short application flows'],
                      ['remoteOnly', 'Remote only', 'Limit results to remote roles'],
                      ['strictKeywordMatch', 'Strict matching', 'Require close keyword matches'],
                    ] as const).map(([field, label, description]) => (
                      <label className="filter-toggle" key={field}>
                        <span className="min-w-0 flex-1">
                          <span className="block text-sm font-extrabold text-slate-800">{label}</span>
                          <span className="mt-1 block text-[11px] leading-4 text-slate-500">{description}</span>
                        </span>
                        <input
                          checked={draft[field] === true}
                          className="switch-input"
                          onChange={(event) => updateField(field, event.target.checked)}
                          type="checkbox"
                        />
                      </label>
                    ))}
                  </div>
                </fieldset>

                <div className="rounded-2xl border border-violet-100 bg-violet-50/60 px-4 py-3">
                  <p className="text-xs font-extrabold text-violet-900">Platform-specific data is preserved</p>
                  <p className="mt-1 text-[11px] leading-5 text-violet-700">
                    {extraFieldCount > 0
                      ? `${extraFieldCount} additional ${extraFieldCount === 1 ? 'field remains' : 'fields remain'} in this profile. Use raw JSON to inspect or edit them.`
                      : 'Use raw JSON when a bot needs fields beyond this common form.'}
                  </p>
                </div>
              </div>
            )}

            {formError && (
              <p className="form-error mt-5" role="alert">
                <AlertCircle aria-hidden="true" className="size-4 shrink-0" />
                {formError}
              </p>
            )}
          </div>

          <div className="sticky bottom-0 flex flex-col gap-3 border-t border-slate-100 bg-white/95 px-4 py-4 backdrop-blur sm:flex-row sm:items-center sm:justify-between sm:px-6">
            <p className="text-[11px] leading-4 text-slate-400">
              Saves to <span className="font-mono text-slate-600">POST /api/filters/{name.trim() || ':name'}</span>
            </p>
            <button className="button button-primary justify-center" disabled={saving || !dirty} type="submit">
              {saving
                ? <Loader2 aria-hidden="true" className="size-4 animate-spin" />
                : <Save aria-hidden="true" className="size-4" />}
              {saving ? 'Saving profile…' : 'Save profile'}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
