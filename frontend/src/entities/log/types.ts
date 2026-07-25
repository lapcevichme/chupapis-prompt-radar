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
  timestamp: string | null;
}
