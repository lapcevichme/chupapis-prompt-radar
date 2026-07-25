import type {Scenario} from '@/entities/scenario/types';

export interface TaskDistributionItem {
  task_type: string;
  label: string;
  count: number;
  percentage: number;
}

export interface DashboardApi {
  taxonomy_version: string;
  freshness: {
    last_recompute_at: string | null;
    logs_since_last_recompute: number;
    recompute_pending: boolean;
  };
  totals: {
    records_processed: number;
    scenarios_count: number;
    outliers_percentage: number;
  };
  tasks_distribution: TaskDistributionItem[];
  top_scenarios: Scenario[];
  dynamics: {date: string; count: number}[];
  outliers_summary: {
    total_outliers_count: number;
    outlier_percentage: number;
  };
  failure_analysis: {
    status: 'available' | 'not_available' | string;
    total_requests_with_failure_signals: number;
    failure_signal_percentage: number;
    top_failure_signals: {signal: string; count: number}[];
  };
}

export interface DashboardSummary {
  taxonomy_version: string;
  freshness: DashboardApi['freshness'];
  total_logs: number;
  success_rate_percent: number;
  by_category: TaskDistributionItem[];
  top_scenarios: Scenario[];
  dynamics: {date: string; count: number}[];
  outliers_summary: DashboardApi['outliers_summary'];
  failure_analysis: DashboardApi['failure_analysis'];
}
