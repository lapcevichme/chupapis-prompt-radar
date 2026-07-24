# Phase 4 completed

## Goal

Heavy recompute: UMAP + HDBSCAN per `task_type`, scheduler, small-group fallback, outliers, stable `scenario_id`, technical name fallback.

## Implemented

| Area | Location |
|------|----------|
| UMAP+HDBSCAN + small-group fallback | `pipeline/clustering_batch/umap_hdbscan.py` |
| Stable `scenario_id` (`{task_type}:cluster_{n}`) | same |
| Outliers (`is_outlier`, label `-1`) | same |
| Centroids in original embedding space | same |
| Technical name fallback (`Сценарий {task_type} {n}`) | same |
| Recompute job + in-memory store | `recompute/job.py` |
| Async scheduler | `recompute/scheduler.py` |
| FastAPI: `POST /api/v1/recompute` (202), `GET /api/v1/recompute/{job_id}`, put logs, assignments | `app/main.py` |
| Unit tests | `tests/test_clustering.py`, `test_recompute_job.py`, `test_scheduler.py` |

## How to verify

```bash
cd ml_service
python run_tests.py
# optional API:
# uvicorn app.main:app --app-dir . --port 8000
```

## Decisions

- Clustering **inside each `task_type`**.
- `n < min_cluster_size` → single fallback cluster, `statistical_reliability: low`.
- Fixed `random_state=42`; adaptive `n_neighbors` / `n_components` for small valid sets.
- LLM naming deferred (phase 5); technical names only.
- In-memory store until Qdrant/meta adapters land.

## Left for later

- Wire job to real Qdrant + meta DB
- LLM summarization (phase 5)
- Auth token enforcement, config.yaml load
- Integration/smoke with docker-compose

## Status

**Phase 4 completed** (MVP core).
