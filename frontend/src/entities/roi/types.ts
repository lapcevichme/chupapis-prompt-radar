export interface RoiData {
  assumptions: {
    fte_hourly_rate_rub: number;
    token_cost_per_1k_rub: number;
    session_coefficients?: {
      short: number;
      medium: number;
      long: number;
    };
    session_short_max_tokens?: number;
    session_long_min_tokens?: number;
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
    name: string | null;
    count: number;
    fte_hours_saved: number;
    net_savings_rub: number;
    automation_potential: string | null;
  }[];
}
