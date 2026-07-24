# PR A — config, health, auth, errors

**Commit message:** `feat(ml): PR A config health auth errors`  
**Scope:** `ml_service/` (ТЗ §4, §7, §10, §11)

## What landed

### 1. Full config (`app/core/config.py`)
- Loads `config.yaml` via `ML_CONFIG_PATH` or default search (`ml_service/config.yaml`, CWD).
- Nested dataclasses: server, store, embeddings, llm, classifier, ingest, online_clustering, recompute (umap/hdbscan), summarization, aggregation_defaults, long_text.
- Env overrides: `QDRANT_URL`, `ML_META_DB_URL`, `OLLAMA_URL`, `OPENROUTER_API_KEY`, `OPENROUTER_EMBEDDINGS_URL`, `OPENROUTER_CHAT_URL`, `CLASSIFIER_MODEL_PATH`, `CLASSIFIER_FALLBACK_MODE`, `ML_SERVICE_TOKEN`, `LOG_LEVEL`, `EMBEDDINGS_PROVIDER`, online thresholds, umap/hdbscan knobs, summarization limits.
- Startup validation collects `config_errors` (invalid provider/fallback/thresholds).
- Backward-compatible with existing `Settings` / `EmbeddingsSettings` / `OnlineClusteringSettings` / `LongTextSettings` constructors used in tests.
- `pipeline_metadata_params()` for `/statistics` reproducibility fields.

### 2. Errors (`app/core/exceptions.py`)
- Codes: `INVALID_REQUEST`, `INGEST_VALIDATION_FAILED`, `CLASSIFIER_NOT_AVAILABLE`, `EMBEDDING_*`, `LLM_*`, `CLUSTERING_FAILED`, `STORE_UNAVAILABLE`, `RECOMPUTE_FAILED`, `INTERNAL_ERROR`, `UNAUTHORIZED`.
- Wire format: `{ code, message, retryable, details? }`.
- `MLServiceError` + FastAPI handler in `main.py`.

### 3. Logging (`app/core/logging.py`)
- Structured one-line events with `stage` / `duration_ms` / `request_id` / `source_id` / `provider` / `error_code`.
- Strips `query_text` / `text` if passed accidentally.
- `log_stage` context manager for timed stages.

### 4. Auth (`app/api/dependencies.py`)
- `require_service_token`: when `ML_SERVICE_TOKEN` / `settings.service_token` is set, all `/api/v1/*` require matching `X-Service-Token`.
- Missing/invalid → **401** with standard body.
- Health endpoints remain open (no dependency).

### 5. Health
- `GET /health/live` → `{ "status": "ok" }` always.
- `GET /health/ready` → `{ status: ready|degraded|not_ready, checks: { config, qdrant, classifier, embeddings_provider, llm_provider }, clusters_loaded }`.
- Degraded when Qdrant is mock, classifier uses heuristic fallback, LLM key missing, etc.
- `not_ready` when config invalid or critical checks fail.

### 6. `main.py` (minimal wiring)
- Uses settings for classifier path/fallback, store URLs, meta DB.
- Exception handlers for `MLServiceError` (+ generic safety net).
- API routes use `Depends(require_service_token)`; pipeline logic unchanged.

### 7. Tests
- `tests/test_config_auth_health.py` — yaml load, env overrides, 401 auth, live/ready degraded/not_ready, error body.
- `tests/test_smoke.py` — live status `ok`; ready accepts ready|degraded|not_ready.
- `tests/conftest.py` — offline defaults (`EMBEDDINGS_PROVIDER=mock`, open auth).
- Dependency: `pyyaml>=6.0.0` in `pyproject.toml`.

## Verification

```text
pytest tests/test_config_auth_health.py tests/test_smoke.py tests/test_embeddings.py -q
# 18 passed
```

## Out of scope (later PRs)
- Full ingestion queue/worker rewrite
- Real Qdrant readiness probe
- LLM/embeddings connectivity ping on ready
- Changing pipeline stages beyond config wiring
