import type {DashboardApi, DashboardSummary} from '@/entities/dashboard/types';
import type {LogItem} from '@/entities/log/types';
import type {RoiData} from '@/entities/roi/types';
import type {Scenario} from '@/entities/scenario/types';
import type {RecomputeJob, RecomputeStatus, Source} from '@/entities/source/types';
import type {User} from '@/entities/user/types';
import type {WorkspaceFilters} from '@/entities/workspace/types';
import {API_BASE_URL, API_HEALTH_URL} from '@/shared/config/env';
import {apiRequest} from './http';
import {mapDashboard} from './mappers';

export interface Paginated<T> {
  items: T[];
  total: number;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface LoginResponse {
  user: User;
}

export type RoiQuery = WorkspaceFilters & {
  fte_hourly_rate_rub?: number;
  token_cost_per_1k_rub?: number;
};

export const promptRadarApi = {
  login: (payload: LoginPayload) =>
    apiRequest<LoginResponse>('/auth/login', {method: 'POST', body: payload}),
  refresh: () => apiRequest<{status: string}>('/auth/refresh', {method: 'POST'}),
  logout: () => apiRequest<void>('/auth/logout', {method: 'POST'}),
  getMe: () => apiRequest<User>('/users/me'),

  ingestDemo: () => apiRequest<Source>('/ingest', {method: 'POST', body: {use_demo: true}}),
  uploadDataset: (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return apiRequest<Source>('/ingest', {method: 'POST', body: form});
  },
  getSources: () => apiRequest<Paginated<Source>>('/sources'),
  getSource: (sourceId: string) => apiRequest<Source>(`/sources/${encodeURIComponent(sourceId)}`),

  startRecompute: () => apiRequest<RecomputeJob>('/recompute', {method: 'POST'}),
  getRecomputeStatus: () => apiRequest<RecomputeStatus>('/recompute/status'),

  getDashboard: async (query?: WorkspaceFilters) => {
    const dashboard = await apiRequest<DashboardApi>('/dashboard', {query: query ? {...query} : undefined});
    return mapDashboard(dashboard);
  },
  getScenarios: (query?: WorkspaceFilters & {task_type?: string}) =>
    apiRequest<Paginated<Scenario>>('/scenarios', {query: query ? {...query} : undefined}),
  getScenario: (scenarioId: string, query?: WorkspaceFilters) =>
    apiRequest<Scenario>(`/scenarios/${encodeURIComponent(scenarioId)}`, {
      query: query ? {...query} : undefined,
    }),
  getLogs: (query?: {
    source_id?: string;
    from?: string;
    to?: string;
    task_type?: string;
    scenario_id?: string;
    only_failures?: boolean;
    limit?: number;
    offset?: number;
  }) => apiRequest<Paginated<LogItem>>('/logs', {query}),
  getRoi: (query?: RoiQuery) => apiRequest<RoiData>('/roi', {query: query ? {...query} : undefined}),
  exportResults: async (format: 'xlsx' | 'csv', query?: RoiQuery) => {
    const url = new URL(`${API_BASE_URL}/export`, window.location.origin);
    url.searchParams.set('format', format);
    Object.entries(query ?? {}).forEach(([key, value]) => {
      if (value !== null && value !== undefined && value !== '') {
        url.searchParams.set(key, String(value));
      }
    });
    const response = await fetch(url, {
      credentials: 'include',
      headers: {Accept: 'application/octet-stream'},
    });
    if (!response.ok) {
      throw new Error(`Export failed with status ${response.status}`);
    }
    const disposition = response.headers.get('Content-Disposition') ?? '';
    const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1] ?? `prompt_radar_roi.${format}`;
    return {blob: await response.blob(), filename};
  },
  getHealth: () => apiRequest<{status: string; dependencies?: Record<string, string>}>(API_HEALTH_URL),
};

export type {DashboardSummary};
