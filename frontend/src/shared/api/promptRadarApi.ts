import type {DashboardApi, DashboardSummary} from '@/entities/dashboard/types';
import type {LogItem} from '@/entities/log/types';
import type {RoiData} from '@/entities/roi/types';
import type {Scenario} from '@/entities/scenario/types';
import type {RecomputeJob, RecomputeStatus, Source} from '@/entities/source/types';
import type {User} from '@/entities/user/types';
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

  getDashboard: async (query?: {source_id?: string; from?: string; to?: string}) => {
    const dashboard = await apiRequest<DashboardApi>('/dashboard', {query});
    return mapDashboard(dashboard);
  },
  getScenarios: (query?: {source_id?: string; task_type?: string}) =>
    apiRequest<Paginated<Scenario>>('/scenarios', {query}),
  getScenario: (scenarioId: string) =>
    apiRequest<Scenario>(`/scenarios/${encodeURIComponent(scenarioId)}`),
  getLogs: (query?: {
    source_id?: string;
    task_type?: string;
    scenario_id?: string;
    only_failures?: boolean;
    limit?: number;
    offset?: number;
  }) => apiRequest<Paginated<LogItem>>('/logs', {query}),
  getRoi: (query?: {
    source_id?: string;
    from?: string;
    to?: string;
    fte_hourly_rate_rub?: number;
    token_cost_per_1k_rub?: number;
  }) => apiRequest<RoiData>('/roi', {query}),
  exportResults: async (format: 'xlsx' | 'csv') => {
    const response = await fetch(`${API_BASE_URL}/export?format=${format}`, {
      credentials: 'include',
      headers: {Accept: 'application/octet-stream'},
    });
    if (!response.ok) {
      throw new Error(`Export failed with status ${response.status}`);
    }
    return response.blob();
  },
  getHealth: () => apiRequest<{status: string; dependencies?: Record<string, string>}>(API_HEALTH_URL),
};

export type {DashboardSummary};
