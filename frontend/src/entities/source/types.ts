export interface Source {
  source_id: string;
  name: string;
  origin: 'upload' | 'demo' | string;
  records_total: number;
  records_valid: number;
  records_rejected: number;
  status: 'ingesting' | 'classified' | 'recomputed' | 'failed' | string;
  ingested?: number | null;
  classified?: number | null;
  assigned?: number | null;
  normalization_report?: Record<string, unknown> | null;
  created_at: string;
}

export interface RecomputeJob {
  job_id: string;
  status: 'running' | 'completed' | 'failed' | string;
  started_at?: string | null;
}

export interface RecomputeStatus {
  job_id: string | null;
  status: 'running' | 'completed' | 'failed' | string;
  clusters_created: number | null;
  scenarios_named: number | null;
  finished_at: string | null;
}
