# ML Service - Prompt Radar Phase 7

## Overview

ML-сервис for corporate AI agent analytics. Implements CQRS: write (logs), recompute (clusters), read (statistics).

Phase 7: Optimization (embedding cache), demo dataset integration, baseline, final smoke.

## Architecture

- app/: FastAPI main, API routers, core config, domain models, pipeline (classification, embeddings, clustering, summarization, aggregation)
- adapters/: LLM, embeddings, Qdrant, meta store
- ingest/: async worker for batches
- recompute/: heavy jobs
- evaluation/: metrics and baseline
- models/: CatBoost artifacts
- tests/: unit, integration, smoke

## Quick Start (Demo)

1. Install deps: uv pip install -e . or pip install -r requirements.txt (generate from pyproject)
2. Start services: docker-compose up -d (includes Qdrant)
3. Run ML: uvicorn app.main:app --host 0.0.0.0 --port 8000
4. Health: curl http://localhost:8000/health/ready
5. Demo: use notebooks/prompt_radar_dataset.json via PUT /logs with token.
6. Recompute: POST /api/v1/recompute
7. Statistics: GET /api/v1/statistics

## Environment

- ML_SERVICE_TOKEN
- OPENROUTER_API_KEY
- QDRANT_URL
- OLLAMA_URL (optional)
- ML_CONFIG_PATH

## Makefile targets (from root)

make up
make demo  # seeds demo, recompute, shows stats
make ml-test
make lint

## Quality Gates

- Unit tests pass
- Ruff lint
- Contract schemas valid
- Smoke on clean env

## Limitations (MVP)

- Single process, no Kafka
- Local Qdrant/meta
- Manual CatBoost prep
- Online clustering sensitive, recompute stabilizes
