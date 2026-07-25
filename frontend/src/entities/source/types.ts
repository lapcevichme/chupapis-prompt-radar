export interface Source {
  source_id: string;
  name: string;
  origin: 'upload' | 'demo' | string;
  records_total: number;
  records_valid: number;
  records_rejected: number;
  status: 'ingesting' | 'classified' | 'recomputed' | 'failed' | string;
  normalization_report?: Record<string, unknown> | null;
  created_at: string;
}

export interface RecomputeStatus {
  job_id: string;
  status: 'running' | 'completed' | 'failed' | string;
  clusters_created: number;
  scenarios_named: number;
  finished_at: string | null;
}
