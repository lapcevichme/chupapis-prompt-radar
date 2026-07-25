export type AutomationPotential = 'high' | 'medium' | 'low' | string | null;
export type ScenarioTrend = 'up' | 'down' | 'stable' | 'new' | 'insufficient_data' | string | null;

export interface Scenario {
  scenario_id: string;
  task_type: string | null;
  name: string | null;
  summary: string | null;
  user_goal: string | null;
  representative_examples: string[];
  pain_points: string[];
  automation_potential: AutomationPotential;
  count: number;
  trend: ScenarioTrend;
  growth_rate_percent: number | null;
  statistical_reliability?: 'high' | 'medium' | 'low' | string | null;
}
