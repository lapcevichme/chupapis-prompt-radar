import type { DashboardSummary, Scenario, LogItem, RoiData, Source, UserAnalyticsData, ModelAnalyticsData, ProcessingStatus, DashboardFilters } from './types';

const BASE = '/api/v1';

/** Serialize the global filters into the query string every read endpoint accepts. */
export function buildFilterQuery(filters?: DashboardFilters, extra?: Record<string, string | number | boolean>): string {
  const params = new URLSearchParams();
  if (filters?.source_id) params.set('source_id', filters.source_id);
  if (filters?.from) params.set('from', filters.from);
  if (filters?.to) params.set('to', filters.to);
  for (const [k, v] of Object.entries(extra ?? {})) params.set(k, String(v));
  const s = params.toString();
  return s ? `?${s}` : '';
}

/** Thrown on 401 after a refresh attempt failed, so the shell can show the login form. */
export class UnauthorizedError extends Error {
  constructor() {
    super('Session expired');
    this.name = 'UnauthorizedError';
  }
}

/**
 * Screens poll on their own timers and swallow their errors, so a session that
 * dies mid-use would otherwise show stale data forever. Announce it once and let
 * the shell decide, instead of threading a callback through every screen.
 */
export const SESSION_EXPIRED_EVENT = 'prompt-radar:session-expired';

function announceSessionExpired(): never {
  window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
  throw new UnauthorizedError();
}

async function send(path: string, init?: RequestInit): Promise<Response> {
  const url = path.startsWith('/api') ? path : `${BASE}${path}`;
  const isFormData = init?.body instanceof FormData;
  return fetch(url, {
    ...init,
    credentials: 'include',
    headers: {
      ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
      ...(init?.headers ?? {}),
    },
  });
}

// The access cookie lives ~15 minutes, so a long-open dashboard will hit 401 on
// its own polling. Refresh once and replay, per contract §0; a second failure is
// a real logout, not a hiccup.
let refreshing: Promise<boolean> | null = null;

function refreshSession(): Promise<boolean> {
  refreshing ??= send('/auth/refresh', { method: 'POST' })
    .then((r) => r.ok)
    .catch(() => false)
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}

async function request<T>(path: string, init?: RequestInit, retry = true): Promise<T> {
  let res = await send(path, init);

  if (res.status === 401 && retry && !path.startsWith('/auth/')) {
    if (await refreshSession()) {
      res = await send(path, init);
    } else {
      announceSessionExpired();
    }
  }

  if (res.status === 204) return undefined as T;
  if (!res.ok) {
    if (res.status === 401) announceSessionExpired();
    const text = await res.text().catch(() => '');
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json();
}

/* ── Auth ── */

export interface CurrentUser {
  id: string;
  email: string;
}

/** Is there a valid cookie session right now? */
export async function checkSession(): Promise<CurrentUser | null> {
  try {
    return await request<CurrentUser>('/users/me');
  } catch {
    return null;
  }
}

export async function login(email: string, password: string): Promise<CurrentUser> {
  await request('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
  return request<CurrentUser>('/users/me');
}

export async function logout(): Promise<void> {
  try {
    await request('/auth/logout', { method: 'POST' });
  } catch {
    /* already gone — the shell drops the session either way */
  }
}

/**
 * Opt-in convenience for the bundled demo: `make up` should land on a populated
 * dashboard without anyone hunting for a password. Credentials come from
 * build-time env, never from literals in the source, and the flag is off unless
 * a build explicitly sets it.
 */
export function demoLoginEnabled(): boolean {
  return import.meta.env.VITE_AUTO_DEMO_LOGIN === 'true';
}

export async function demoLogin(): Promise<CurrentUser | null> {
  const email = import.meta.env.VITE_DEMO_EMAIL;
  const password = import.meta.env.VITE_DEMO_PASSWORD;
  if (!demoLoginEnabled() || !email || !password) return null;
  try {
    return await login(email, password);
  } catch {
    return null;
  }
}

/* ── Dashboard ── */

export async function fetchDashboard(filters?: DashboardFilters): Promise<DashboardSummary> {
  const raw = await request<any>(`/dashboard${buildFilterQuery(filters)}`);
  const failureRate = raw.failure_analysis?.failure_signal_percentage ?? 0;
  return {
    period: { from: '', to: '' },
    generated_at: raw.generated_at,
    total_logs: raw.totals?.records_processed ?? 0,
    success_rate_percent: Math.max(0, 100 - failureRate),
    by_category: raw.tasks_distribution ?? [],
    top_scenarios: raw.top_scenarios ?? [],
    dynamics: raw.dynamics ?? [],
    outliers_summary: raw.outliers_summary ?? { total_outliers_count: 0, outlier_percentage: 0 },
    failure_analysis: raw.failure_analysis ?? {
      status: 'not_available',
      total_requests_with_failure_signals: 0,
      failure_signal_percentage: 0,
      top_failure_signals: [],
    },
  };
}

/* ── Sources ── */

export async function fetchSources(): Promise<Source[]> {
  const raw = await request<{ items: Source[]; total: number }>('/sources');
  return raw.items ?? [];
}

export async function fetchSource(id: string): Promise<Source> {
  return request<Source>(`/sources/${encodeURIComponent(id)}`);
}

export async function uploadFile(file: File): Promise<Source> {
  const form = new FormData();
  form.append('file', file);
  return request<Source>('/ingest', { method: 'POST', body: form });
}

/** Re-stream a source's stored records to finish a stalled indexing run. */
export async function resumeSource(id: string): Promise<Source> {
  return request<Source>(`/sources/${encodeURIComponent(id)}/resume`, { method: 'POST' });
}

/* ── Recompute ── */

export async function triggerRecompute(): Promise<{ job_id?: string; status: string }> {
  return request('/recompute', { method: 'POST' });
}

export async function fetchRecomputeStatus(): Promise<{ status: string; job_id?: string; scenarios_named?: number }> {
  return request('/recompute/status');
}

/* ── Processing (global indexing progress) ── */

export async function fetchProcessingStatus(): Promise<ProcessingStatus> {
  return request<ProcessingStatus>('/ingest/status');
}

/* ── Scenarios ── */

export async function fetchScenarios(filters?: DashboardFilters): Promise<Scenario[]> {
  const raw = await request<{ items: Scenario[]; total: number }>(`/scenarios${buildFilterQuery(filters)}`);
  return raw.items ?? [];
}

export async function fetchScenarioDetail(id: string): Promise<Scenario> {
  return request<Scenario>(`/scenarios/${encodeURIComponent(id)}`);
}

/* ── Logs ── */

export async function fetchLogs(filters?: DashboardFilters, limit = 100): Promise<LogItem[]> {
  const raw = await request<{ items: LogItem[]; total: number }>(`/logs${buildFilterQuery(filters, { limit })}`);
  return raw.items ?? [];
}

/* ── ROI ── */

export async function fetchRoi(filters?: DashboardFilters): Promise<RoiData> {
  return request<RoiData>(`/roi${buildFilterQuery(filters)}`);
}

/** Export honours the same filters as the screen it was triggered from. */
export function exportUrl(format: 'xlsx' | 'csv', filters?: DashboardFilters): string {
  return `${BASE}/export${buildFilterQuery(filters, { format })}`;
}

/* ── Analytics ── */

export async function fetchUserAnalytics(filters?: DashboardFilters): Promise<UserAnalyticsData> {
  return request<UserAnalyticsData>(`/analytics/users${buildFilterQuery(filters)}`);
}

export async function fetchModelAnalytics(filters?: DashboardFilters): Promise<ModelAnalyticsData> {
  return request<ModelAnalyticsData>(`/analytics/models${buildFilterQuery(filters)}`);
}

