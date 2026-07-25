import type {DashboardApi, DashboardSummary} from '@/entities/dashboard/types';

export function mapDashboard(apiDashboard: DashboardApi): DashboardSummary {
  const failureRate = apiDashboard.failure_analysis.failure_signal_percentage ?? 0;

  return {
    taxonomy_version: apiDashboard.taxonomy_version,
    freshness: apiDashboard.freshness,
    total_logs: apiDashboard.totals.records_processed,
    success_rate_percent: Math.max(0, 100 - failureRate),
    by_category: apiDashboard.tasks_distribution,
    top_scenarios: apiDashboard.top_scenarios,
    dynamics: apiDashboard.dynamics,
    outliers_summary: apiDashboard.outliers_summary,
    failure_analysis: apiDashboard.failure_analysis,
  };
}
