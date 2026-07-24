# Phase 3 completed

## Scope
Embeddings adapters + long-text chunking + online cosine clustering for ML service.

## Delivered
| Module | Path |
|--------|------|
| Settings | `app/core/config.py` |
| Embeddings interface + mock/Ollama/OpenRouter | `app/pipeline/embeddings/adapter.py` |
| Long-text chunking + strategy | `app/pipeline/long_text/chunking.py` |
| Online cosine clusterer | `app/pipeline/clustering_online/cosine_clusterer.py` |
| Pipeline glue | `app/pipeline/online_pipeline.py` |
| Unit tests | `tests/test_embeddings.py` |

## Behaviour
- **Embeddings:** `create_embedding_adapter(provider)` → `mock` (deterministic hash vectors for tests), `ollama`, `openrouter` (HTTP, batch, timeout, retry).
- **Long text:** if tokens ≤ `max_direct_tokens` → direct; else overlapping word chunks → head+tail extractive representation (`chunk_summary`). No silent full-doc drop without strategy flag.
- **Online clustering:** per `task_type`, assign by max cosine to centroids; ≥ threshold → assign + running-mean centroid; else `{task_type}:cluster_{n}`.

## Run tests
```bash
cd ml_service
pip install -e .  # or: pip install aiohttp pydantic numpy pytest pytest-asyncio
pytest tests/test_embeddings.py -q
```

## Defaults
`EMBEDDINGS_PROVIDER=mock` so unit tests and local smoke work offline.
