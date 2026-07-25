export interface DashboardSummary {
  period: { from: string; to: string };
  total_logs: number;
  success_rate_percent: number;
  by_category: {
    task_type: string;
    label: string;
    count: number;
    percentage: number;
  }[];
  top_scenarios: Scenario[];
  dynamics: { date: string; count: number }[];
  outliers_summary: {
    total_outliers_count: number;
    outlier_percentage: number;
  };
  failure_analysis: {
    status: string;
    total_requests_with_failure_signals: number;
    failure_signal_percentage: number;
    top_failure_signals: { signal: string; count: number }[];
  };
}

export interface Scenario {
  scenario_id: string;
  task_type: string;
  name: string;
  summary: string;
  user_goal: string;
  representative_examples: string[];
  pain_points: string[];
  automation_potential: 'high' | 'medium' | 'low';
  count: number;
  trend: 'up' | 'down' | 'stable';
  growth_rate_percent: number;
  statistical_reliability?: 'high' | 'medium' | 'low';
}

export interface RoiData {
  assumptions: {
    fte_hourly_rate_rub: number;
    token_cost_per_1k_rub: number;
  };
  summary: {
    total_logs: number;
    success_rate_percent: number;
    total_fte_hours_saved: number;
    total_manual_cost_rub: number;
    total_agent_cost_rub: number;
    net_savings_rub: number;
    roi_multiplier: number;
    total_tokens_consumed: number;
    wasted_tokens_on_errors: number;
    token_value_index: number;
    process_automation_rate: number;
    top_tools_used: Record<string, number>;
  };
  by_category: {
    task_type: string;
    label: string;
    count: number;
    success_rate_percent: number;
    fte_hours_saved: number;
    net_savings_rub: number;
  }[];
  by_scenario: {
    scenario_id: string;
    name: string;
    count: number;
    fte_hours_saved: number;
    net_savings_rub: number;
    automation_potential: string;
  }[];
}

export interface LogItem {
  request_id: string;
  query_text: string;
  task_type: string;
  classification_confidence: number;
  scenario_id: string | null;
  scenario_name: string | null;
  is_outlier: boolean;
  has_failure_signals: boolean;
  timestamp: string;
}

export interface Source {
  source_id: string;
  name: string;
  origin: string;
  records_total: number;
  records_valid: number;
  records_rejected: number;
  status: string;
  created_at: string;
}
