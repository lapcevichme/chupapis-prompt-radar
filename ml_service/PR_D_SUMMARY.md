# PR D — Production embeddings + online clustering

## Goal (ТЗ §8.2, §8.4, §8.5)

Hardened embedding adapters, long-text metrics, and online cosine clustering for the
ML online path: **preprocess → long_text → embed → assign**.

## Delivered

| Module | Path | Notes |
|--------|------|--------|
| Settings | `app/core/config.py` | provider, batch, timeout, retries, **max_concurrency**, cache |
| Embeddings | `app/pipeline/embeddings/adapter.py` | mock / Ollama / OpenRouter; retryable errors; batch; concurrency; dim from response; LRU cache |
| Long-text | `app/pipeline/long_text/chunking.py` | (existing) `strategy` + `chunks_processed`; no silent full-doc drop |
| Online clusterer | `app/pipeline/clustering_online/cosine_clusterer.py` | per-`task_type` centroids; cosine threshold; `{task_type}:cluster_{n}`; optional centroid update; **dump/load** + TODO(PR B) |
| Pipeline glue | `app/pipeline/online_pipeline.py` | preprocess → long_text → embed → assign; full storage result + metrics |
| API wiring | `app/main.py` | assignments carry `long_text_strategy`, `chunks_processed`, `metrics` |
| Config sample | `config.yaml` | concurrency + cache knobs |
| Unit tests | `tests/test_embeddings.py` | mock, cache, HTTP retry/batch/dim, clusterer dump/load, e2e pipeline |

## Behaviour

### Embeddings (§8.4)

- Factory: `create_embedding_adapter(cfg)` → `mock` | `ollama` | `openrouter`.
- **Mock only** when `EMBEDDINGS_PROVIDER=mock` (code default for offline tests/demo).
  Production: set env/`config.yaml` to `ollama` or `openrouter`.
- HTTP path: batch (`batch_size`), timeout, exponential backoff retries, **semaphore
  concurrency** (`max_concurrency`), 429/5xx → retryable `EMBEDDING_PROVIDER_UNAVAILABLE`.
- Dimension taken from first successful provider response (`adapter.dimension`).
- Optional **hash→vector LRU cache** (`cache_enabled`, `cache_max_size`) for demo re-ingest.

### Long text (§8.2)

- Short (`≤ max_direct_tokens`) → `strategy=direct`, `chunks_processed=0`.
- Long → overlapping chunks → head+tail extractive summary → `strategy=chunk_summary`,
  `chunks_processed=N`. Metrics exposed on `OnlinePipelineResult` and assignment payload.

### Online clustering (§8.5)

1. Compare embedding to centroids of the **same** `task_type` (cosine).
2. If max ≥ `similarity_threshold` → assign; optionally running-mean centroid update.
3. Else → new `scenario_id = {task_type}:cluster_{n}`.
4. State is in-memory; `dump_centroids()` / `load_centroids()` for hydration.
   **TODO(PR B):** persist via meta store `clusters` table on restart / after recompute.

### Online pipeline

```
preprocess (whitespace normalize) → prepare_for_embedding → embed → CosineClusterer.assign
```

`OnlinePipelineResult.to_storage_dict()` is the fragment for Qdrant + meta.

## Env knobs

| Env | Default | Meaning |
|-----|---------|---------|
| `EMBEDDINGS_PROVIDER` | `mock` | `mock` \| `ollama` \| `openrouter` |
| `OLLAMA_URL` / `OLLAMA_MODEL` | ollama defaults | Ollama endpoint + model |
| `OPENROUTER_API_KEY` / `OPENROUTER_MODEL` | — | OpenRouter |
| `EMBEDDINGS_BATCH_SIZE` | 32 | batch size |
| `EMBEDDINGS_TIMEOUT_SEC` | 30 | HTTP timeout |
| `EMBEDDINGS_MAX_RETRIES` | 2 | retries after first attempt |
| `EMBEDDINGS_MAX_CONCURRENCY` | 4 | in-flight HTTP embed requests |
| `EMBEDDINGS_CACHE_ENABLED` | true | hash→vector cache |
| `ONLINE_SIMILARITY_THRESHOLD` | 0.85 | cosine assign threshold |
| `RECOMPUTE_CENTROID` | true | running-mean update online |

## Tests

```bash
cd ml_service
pytest tests/test_embeddings.py -q
```

## Out of scope / next

- Wire `load_centroids` from real meta store after recompute (PR B).
- Full Qdrant point upsert of online assignments (store PR).
- Production readiness probe against live Ollama/OpenRouter.
