# PR E — Recompute + LLM scenario summarization

**Scope:** ТЗ §8.6–8.9  
**Commit:** `feat(ml): PR E recompute summarization`

## Goal

Harden heavy recompute (UMAP+HDBSCAN per `task_type`), stabilize `scenario_id` across runs,
wire LLM scenario naming/summaries with retries and technical fallback, optional scheduler
(default off), persistent-friendly job store. Keep existing `POST /recompute` (202) and
`GET /recompute/{job_id}`.

## Implemented

| Area | Location |
|------|----------|
| Job status `pending\|running\|completed\|failed` | `app/recompute/job.py` |
| UMAP+HDBSCAN per task_type, outliers, small-group fallback | `job.py` + `clustering_batch/umap_hdbscan.py` |
| **Stable `scenario_id`** via cosine match of centroids | `app/recompute/stability.py` |
| Representative examples (~10): KNN / samples | `app/recompute/representatives.py` |
| LLM summarization + Pydantic `name` ≤ 4 words + retries | `app/pipeline/summarization.py` |
| Technical name fallback (`Сценарий {task_type} {n}`) | same |
| Job store + optional MetaStore mirror (`recompute_jobs`) | `job.py` + `database/meta_store.py` |
| Scheduler opt-in (`scheduler_enabled: false` / env) | `recompute/scheduler.py` + `main.py` lifespan |
| Config: match threshold, summarization knobs | `config.yaml` |
| Unit tests (mocked LLM) | `tests/test_recompute_job.py`, `test_summarization.py`, `test_representatives.py`, `test_scheduler.py` |

## Behaviour notes

### Recompute job

1. Group records by `task_type`.
2. Run UMAP → HDBSCAN (or small-group / all-outliers fallback).
3. **Stabilize IDs:** greedy bipartite match of new centroids to previous ones
   (`centroid_match_threshold`, default `0.75`); unmatched clusters get free indices.
4. Update assignments (`scenario_id`, `is_outlier`, `scenario_name`).
5. For each cluster: pick representatives → `Summarizer.summarize_scenario` → store
   `name/summary/user_goal/pain_points/automation_potential`.
6. Persist job status snapshots (memory + optional SQLite).

### Summarization

- Structured JSON validated by `ScenarioSummary` (Pydantic v2).
- Long names soft-trimmed to ≤ 4 words.
- `max_llm_retries` (default 2) → then technical fallback.
- No `OPENROUTER_API_KEY` → technical fallback (no network).

### Scheduler

- **Default off.** Enable with `recompute.scheduler_enabled: true` or
  `RECOMPUTE_SCHEDULER_ENABLED=true`.
- Interval from `recompute.interval_hours` (default 2).

### API (unchanged contract)

- `POST /api/v1/recompute` → `202 { job_id, status: "pending" }` (background task).
- `GET /api/v1/recompute/{job_id}` → job record (status, counts, timestamps, error).
- Scenarios/assignments expose LLM or technical names after recompute.

## How to verify

```bash
cd ml_service
python -m pytest tests/ -q
# focused:
python -m pytest tests/test_recompute_job.py tests/test_summarization.py tests/test_representatives.py tests/test_scheduler.py -v
```

## Decisions

- Centroid cosine match preferred over label-order remapping so IDs survive HDBSCAN label shuffle.
- Summarization runs for every cluster after recompute (including fallback clusters); no LLM if no API key.
- Job store stays in-memory for speed; MetaStore mirrors jobs for restart-friendly status reads.
- Scheduler is opt-in so demo/local does not surprise-recompute.

## Left for later

- Full Qdrant KNN for representatives (adapter `search` currently stub when offline).
- Hydrate online `CosineClusterer` centroids after recompute.
- Richer `/statistics` aggregation (trends, failure) — later PR.

## Status

**PR E completed** — 47 unit tests green at merge time.
