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
  normalization_report?: {
    synthesized_request_id?: number;
    synthesized_timestamp?: number;
    rejected_reasons?: Record<string, number>;
  };
}

export interface UserAnalyticsData {
  summary: {
    total_users: number;
    active_users_l7: number;
    avg_adoption_score: number;
    avg_frustration_index: number;
    personas_distribution: {
      persona: string;
      label: string;
      count: number;
      percentage: number;
    }[];
  };
  by_department: {
    department: string;
    users_count: number;
    total_queries: number;
    avg_saved_hours: number;
    frustration_index: number;
  }[];
  users: {
    user_id: string;
    user_name: string;
    department: string;
    persona: string;
    persona_label: string;
    total_queries: number;
    active_days: number;
    saved_hours: number;
    frustration_index: number;
    top_category: string;
    needs_guidance: boolean;
    recommendation: string;
  }[];
}

export interface ModelAnalyticsData {
  summary: {
    total_models_detected: number;
    avg_latency_ms: number;
    total_tokens: number;
    potential_cost_reduction_percent: number;
    routing_recommendation: string;
  };
  models: {
    model_id: string;
    model_name: string;
    total_queries: number;
    share_percentage: number;
    avg_latency_ms: number;
    total_tokens: number;
    failure_rate_percent: number;
    user_feedback_score: number;
    top_task_type: string;
    cost_tier: string;
  }[];
  task_fit: {
    task_type: string;
    label: string;
    recommended_model: string;
    queries_count: number;
    avg_latency_ms: number;
  }[];
}

