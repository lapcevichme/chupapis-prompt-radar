/** Global dashboard filters (D3): applied to every read screen and to exports. */
export interface DashboardFilters {
  /** Ingestion source to scope to; empty means the whole store. */
  source_id?: string;
  /** ISO date (YYYY-MM-DD). `to` is inclusive of the whole day, handled by backend. */
  from?: string;
  to?: string;
}

export interface DashboardSummary {
  period: { from: string; to: string };
  generated_at?: string;
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
    manual_minutes_by_category: Record<string, number>;
    manual_minutes_estimated_percent: number;
    fte_rate_model?: {
      monthly_rate_rub: number;
      work_hours_per_month: number;
      derived_hourly_rate_rub: number;
      is_overridden: boolean;
    } | null;
    token_cost_model?: {
      infra_capex_rub: number;
      amortization_years: number;
      electricity_rub_per_year: number;
      tokens_per_year: number;
      derived_cost_per_1k_rub: number;
      is_overridden: boolean;
    } | null;
  };
  /** Explicit B > A verdict (QNA §1): B = money freed, A = cost of running the agent. */
  verdict: {
    benefit_rub: number;
    cost_rub: number;
    net_rub: number;
    ratio: number;
    pays_off: boolean;
    headline: string;
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
    mau_count: number;
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
    /** null until heavy recompute names the cluster. */
    name: string | null;
    count: number;
    fte_hours_saved: number;
    net_savings_rub: number;
    automation_potential: string | null;
  }[];
}

export interface LogItem {
  request_id: string;
  query_text: string;
  task_type: string | null;
  label?: string | null;
  classification_confidence: number | null;
  scenario_id: string | null;
  scenario_name: string | null;
  is_outlier: boolean;
  has_failure_signals: boolean;
  timestamp: string;
}

export interface SourceProgress {
  classified: number;
  total: number;
  percent: number;
  done: boolean;
}

export interface Source {
  source_id: string;
  name: string;
  origin: string;
  records_total: number;
  records_valid: number;
  records_rejected: number;
  records_classified?: number;
  classification_percentage?: number;
  status: string;
  created_at: string;
  progress?: SourceProgress | null;
  normalization_report?: {
    synthesized_request_id?: number;
    synthesized_timestamp?: number;
    rejected_reasons?: Record<string, number>;
  };
}

export interface ProcessingSource {
  source_id: string;
  name: string;
  origin: string;
  status: string;
  records_total: number;
  records_valid: number;
  records_rejected: number;
  classified: number;
  percent: number;
  done: boolean;
}

export interface ProcessingStatus {
  indexing: boolean;
  total_valid: number;
  total_classified: number;
  percent: number;
  recompute_status: string;
  recompute_pending: boolean;
  logs_since_last_recompute: number;
  scenarios_named: number;
  sources: ProcessingSource[];
}

export interface UserAnalyticsData {
  summary: {
    total_users: number;
    active_users_l7: number;
    active_window_days: number;
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
    /** "available" | "not_available" — no model metadata in the ingested records. */
    status: string;
    total_models_detected: number;
    total_queries_with_model: number;
    total_tokens: number;
  };
  models: {
    model_id: string;
    model_name: string;
    total_queries: number;
    share_percentage: number;
    total_tokens: number;
    failure_rate_percent: number;
    top_task_type: string;
  }[];
}

