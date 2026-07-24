# Phase 3: Embeddings Adapters + Chunking + Cosine Clustering

**Status:** In Progress (restarted)
**Goal:** Implement embeddings adapters (Ollama/OpenRouter), long-text chunking, online cosine clustering.

## Tasks
- [x] Create directory structure for ml_service/app/pipeline/{embeddings,long_text,clustering_online}
- [x] Implement EmbeddingAdapter with provider support (Ollama, OpenRouter)
- [x] Implement long text chunking with overlap
- [x] Implement CosineClusterer for online assignment based on similarity threshold
- [x] Add unit tests for the components
- [x] Update pyproject.toml with dependencies (numpy, scikit-learn, umap, hdbscan, pytest)
- [ ] Integrate with full pipeline and Qdrant/meta (next phase)
- [ ] Ensure contract compliance for embeddings dimension
- [ ] Add config.yaml for phase 3 params

## Changes
- ml_service/app/pipeline/embeddings/adapter.py: new
- ml_service/app/pipeline/long_text/chunking.py: new
- ml_service/app/pipeline/clustering_online/cosine_clusterer.py: new
- ml_service/app/core/config.py: new
- ml_service/app/main.py: basic FastAPI
- ml_service/app/domain/models.py: LogEntry schema
- ml_service/tests/test_embeddings.py: tests
- ml_service/pyproject.toml: deps

## Next
- Phase 4: Recompute with UMAP+HDBSCAN
- Wire into ingest worker
- Add readiness checks for embeddings provider
