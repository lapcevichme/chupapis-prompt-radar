import type { DashboardSummary, Scenario, LogItem, RoiData, Source, UserAnalyticsData, ModelAnalyticsData, ProcessingStatus, DashboardFilters } from './types';

const BASE = '/api/v1';

/** Serialize the global filters into the query string every read endpoint accepts. */
function qs(filters?: DashboardFilters, extra?: Record<string, string | number | boolean>): string {
  const params = new URLSearchParams();
  if (filters?.source_id) params.set('source_id', filters.source_id);
  if (filters?.from) params.set('from', filters.from);
  if (filters?.to) params.set('to', filters.to);
  for (const [k, v] of Object.entries(extra ?? {})) params.set(k, String(v));
  const s = params.toString();
  return s ? `?${s}` : '';
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = path.startsWith('/api') ? path : `${BASE}${path}`;
  const isFormData = init?.body instanceof FormData;
  const res = await fetch(url, {
    ...init,
    credentials: 'include',
    headers: {
      ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
      ...(init?.headers ?? {}),
    },
  });
  if (res.status === 204) return undefined as T;
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json();
}

/* ── Auth ── */

export async function ensureAuth(): Promise<boolean> {
  try {
    await request('/users/me');
    return true;
  } catch {
    const credentials = [
      { email: 'demo@prompt-radar.local', password: 'DemoPass123!' },
      { email: 'test@gmail.com', password: 'test123' },
    ];
    for (const cred of credentials) {
      try {
        await request('/auth/login', {
          method: 'POST',
          body: JSON.stringify(cred),
        });
        return true;
      } catch { /* try next */ }
    }
    return false;
  }
}

/* ── Dashboard ── */

export async function fetchDashboard(filters?: DashboardFilters): Promise<DashboardSummary> {
  const raw = await request<any>(`/dashboard${qs(filters)}`);
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
  const raw = await request<{ items: Scenario[]; total: number }>(`/scenarios${qs(filters)}`);
  return raw.items ?? [];
}

export async function fetchScenarioDetail(id: string): Promise<Scenario> {
  return request<Scenario>(`/scenarios/${encodeURIComponent(id)}`);
}

/* ── Logs ── */

export async function fetchLogs(filters?: DashboardFilters, limit = 100): Promise<LogItem[]> {
  const raw = await request<{ items: LogItem[]; total: number }>(`/logs${qs(filters, { limit })}`);
  return raw.items ?? [];
}

/* ── ROI ── */

export async function fetchRoi(filters?: DashboardFilters): Promise<RoiData> {
  return request<RoiData>(`/roi${qs(filters)}`);
}

/** Export honours the same filters as the screen it was triggered from. */
export function exportUrl(format: 'xlsx' | 'csv', filters?: DashboardFilters): string {
  return `${BASE}/export${qs(filters, { format })}`;
}

/* ── Analytics ── */

export async function fetchUserAnalytics(filters?: DashboardFilters): Promise<UserAnalyticsData> {
  return request<UserAnalyticsData>(`/analytics/users${qs(filters)}`);
}

export async function fetchModelAnalytics(filters?: DashboardFilters): Promise<ModelAnalyticsData> {
  return request<ModelAnalyticsData>(`/analytics/models${qs(filters)}`);
}

