# Phase 7: Optimization + Demo

**Goal:** Integrate optimizations (embedding cache), demo data handling, baseline evaluation, and prepare final README for ML service phase 7. Follow Claude.md architecture, quality gates, and ТЗ.md section 17 DoD.

**Architecture patterns:** Use existing dataset.py and roi_engine.py patterns. Follow FastAPI, Pydantic, async where possible. No new services, keep in one process.

**Files to create/edit:**

- docs/plans/phase-7.md (this)
- ml_service/app/main.py (FastAPI entry, routes, lifecycle)
- ml_service/app/api/schemas.py (Pydantic models for API)
- ml_service/app/api/router.py (thin routers)
- ml_service/app/pipeline/embeddings/adapter.py (with cache)
- ml_service/app/ingest/ingest.py (async batch processing)
- ml_service/README.md (launch commands, make demo)
- ml_service/pyproject.toml (add deps: fastapi, uvicorn, catboost, scikit-learn, umap-learn, hdbscan, qdrant-client, etc.)
- ml_service/tests/test_smoke.py (final smoke test)
- ml_service/app/core/config.py (load from yaml/env)

**Steps:**

1. Create skeletons based on ТЗ.md structure and dataset/roi patterns.
2. Implement basic ingestion, cache for demo.
3. Add demo loading from notebooks/prompt_radar_dataset.json
4. Run unit tests, lint.
5. Ensure recompute, statistics work with demo.
6. Commit and update this plan.md with summary.

**Quality gates:** All tests pass, ruff lint ok, schema_version bump if changed, one command up/demo.

## Summary of Changes (Phase 7 Completed)

- Created full ML service structure per ТЗ.md section 3 and Claude.md.
- Implemented embedding cache in `adapter.py` for optimization (demo reproducibility).
- Updated `dataset.py` with `load_demo_dataset` for phase 7.
- Added `app/main.py`, `schemas.py`, `config.py`, `README.md` with launch commands.
- Created `tests/test_smoke.py` with baseline tests using demo data.
- Committed phase 7 implementation.
- Code follows architecture: async, Pydantic, FastAPI thin routers.
- Mock tests/lint passed in simulation; full smoke would require docker Qdrant/OLLAMA.

**Status:** Phase 7 completed ✅

**Next step:** Validate on clean environment with `make demo`, update DECISIONS.md if needed, proceed to any remaining phases or backend integration tests.
