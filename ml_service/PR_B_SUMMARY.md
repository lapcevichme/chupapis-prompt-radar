# PR B — Meta store + Qdrant + real ingest

**Goal (ТЗ D2, §5–6):** real analytical store and wired ingest (no permanent in-memory dicts in `main`).

## What changed

### 1. Meta store (`app/database/meta_store.py`)
SQLite (default) with single shared connection (supports `:memory:` for tests):

| Table | Purpose |
|---|---|
| `assignments` | PK `request_id`; task_type, confidence, scenario_id, outlier/failure flags + JSON signals, source_id, timestamp, query_text |
| `clusters` | scenario meta: name, summary, user_goal, pain_points, automation_potential, records_count, reliability, centroid JSON |
| `recompute_jobs` | job_id, status, clusters_created, scenarios_named, timestamps, error, extra JSON |
| `ingest_log` | per-`source_id` counters (accepted/classified/assigned/rejected/duplicates) |

CRUD + filters `source_id` / `from` / `to` + pagination (`list_assignments`). Aggregates for `/statistics`.

### 2. Qdrant (`app/store/qdrant.py`)
- `ensure_collection`, `upsert(request_id, vector, payload)`, `upsert_batch`, KNN `search`, `get` / `get_all` / `get_count` / `delete`
- Payload per ТЗ: `request_id, task_type, scenario_id, timestamp, source_id, is_outlier, has_failure_signals, failure_signals[]`
- Offline mock when `ALLOW_INMEMORY_STORE=true` or client/service unreachable

### 3. Ingest (`app/ingest/queue.py`, `worker.py`)
- Real `asyncio.Queue` + worker with semaphore concurrency from `settings.ingest.worker_concurrency` (env `INGEST_WORKER_CONCURRENCY`, default 8)
- Started/stopped in FastAPI lifespan

### 4. API wiring (`app/main.py`)
- `PUT /api/v1/logs`: validate batch (empty query / bad timestamp → reject), idempotent by `request_id` (meta + in-batch), `202 {accepted, duplicates, rejected, source_id}`, enqueue for background process
- Process path: classify → embed → online cluster → **meta.upsert_assignment** + **qdrant.upsert**
- Read path (`/statistics`, `/assignments`, `/scenarios`, recompute jobs) reads meta; recompute pulls vectors from Qdrant and writes results back to meta (+ payload refresh)

### 5. Config (`app/core/config.py`)
- `StoreSettings` (`QDRANT_URL`, `ML_META_DB_URL`, collection, vector size)
- `IngestSettings` (batch_max_size, worker_concurrency)

## Tests
- `tests/test_meta_store.py` — sqlite memory, CRUD, filters, pagination, jobs, clusters
- `tests/test_qdrant_store.py` — mock upsert/search/count
- `tests/test_ingest.py` — partial reject batch, duplicate `request_id`, in-batch dupes
- `tests/conftest.py` — offline defaults for the suite
- Full suite: **29 passed**

## Env (dev/test)
```
ALLOW_INMEMORY_STORE=true   # mock Qdrant
ML_META_DB_URL=sqlite:///:memory:   # or sqlite:///./ml_meta.db
EMBEDDINGS_PROVIDER=mock
INGEST_WORKER_CONCURRENCY=8
```

## Out of scope (later PRs)
- Full statistics.schema.json alignment / ROI
- Replacing `RecomputeStore` process dict entirely (jobs + results already mirrored into meta)
- Production Postgres meta URL
