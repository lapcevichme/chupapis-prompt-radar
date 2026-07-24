# Phase 4: UMAP/HDBSCAN Recomputation, Scheduler and Fallback

## Goal

Heavy recompute: UMAP + HDBSCAN per task_type, scheduler, small-group fallback, outliers, stable scenario_id, technical naming fallback.

## Acceptance criteria

- [x] UMAP+HDBSCAN with fixed random_state
- [x] Small-group fallback (`statistical_reliability: low`)
- [x] Stable `scenario_id` = `{task_type}:cluster_{n}`
- [x] Outliers marked `is_outlier`
- [x] Recompute job with status tracking
- [x] Optional asyncio scheduler
- [x] Technical name fallback (LLM in phase 5)
- [x] Unit tests (10/10 pass via `python run_tests.py`)

## Current status

**Phase 4 completed.**

### Changed / added

- `ml_service/pipeline/clustering_batch/umap_hdbscan.py`
- `ml_service/recompute/job.py`, `scheduler.py`
- `ml_service/app/main.py` — POST/GET recompute
- `ml_service/tests/*`
- `ml_service/PHASE4_SUMMARY.md`

### Next session

Phase 5: LLM summarization for scenario names/summaries; wire store to Qdrant/meta.
