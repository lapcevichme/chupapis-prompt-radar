import {render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {expect, test, vi} from 'vitest';
import DashboardPage from './DashboardPage';

vi.mock('recharts', () => ({
  Area: () => null,
  AreaChart: () => null,
  CartesianGrid: () => null,
  Cell: () => null,
  Pie: () => null,
  PieChart: () => null,
  ResponsiveContainer: () => null,
  Tooltip: () => null,
  XAxis: () => null,
  YAxis: () => null,
}));

vi.mock('@/shared/api/promptRadarApi', () => ({
  promptRadarApi: {
    getDashboard: vi.fn().mockResolvedValue({
      taxonomy_version: 'v1',
      freshness: {last_recompute_at: null, logs_since_last_recompute: 12, recompute_pending: false},
      total_logs: 12,
      success_rate_percent: 100,
      by_category: [],
      top_scenarios: [],
      dynamics: [],
      outliers_summary: {total_outliers_count: 0, outlier_percentage: 0},
      failure_analysis: {
        status: 'not_available',
        total_requests_with_failure_signals: 0,
        failure_signal_percentage: 0,
        top_failure_signals: [],
      },
    }),
  },
}));

test('shows freshness warning and opens sources', async () => {
  const user = userEvent.setup();
  const onOpenSources = vi.fn();
  render(<DashboardPage filters={{}} onOpenSources={onOpenSources} refreshKey={0} />);

  expect(await screen.findByText('Scenario recompute recommended')).toBeInTheDocument();
  await user.click(screen.getByRole('button', {name: 'Open sources'}));
  expect(onOpenSources).toHaveBeenCalledOnce();
});
