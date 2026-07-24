# PR G — Docker, demo, docs (ML)

## Goal

ТЗ §14 / §17 / §18: воспроизводимый Docker-контур ML, demo seed, README, smoke без live LLM.

## Delivered

| Item | Path |
|------|------|
| Dockerfile (`python:3.11-slim`, deps from pyproject, EXPOSE 8000, uvicorn) | `ml_service/Dockerfile` |
| Compose: `ml-service` + `qdrant` (+ optional `ollama` profile) | `ml_service/docker-compose.yml` |
| Env template (no real secrets) | `ml_service/.env.example` |
| Makefile: `ml-up`, `ml-test`, `demo`, `seed`, `smoke` | `ml_service/Makefile` |
| Demo seed (dataset → log batches per backend-ml.md) | `ml_service/scripts/seed_demo.py` |
| README (run, env, CQRS, classifier, MVP limits, keys) | `ml_service/README.md` |
| Smoke / mapping tests (mock embeddings) | `ml_service/tests/test_smoke.py` |
| setuptools packaging hooks for local `pip install` | `ml_service/pyproject.toml` |

## How to verify

```bash
cd ml_service
cp .env.example .env
# leave OPENROUTER_API_KEY empty; EMBEDDINGS_PROVIDER=mock
make ml-test
# full stack (needs Docker):
make demo
```

## Notes

- Root Makefile absent → targets live under `ml_service/Makefile`.
- `notebooks/prompt_radar_dataset.json` may be absent; seed falls back to built-in sample.
- Default embeddings provider is **mock** so CI/demo work without OpenRouter.
- `OPENROUTER_API_KEY` only via env / local `.env` (gitignored); never committed.
- Classifier artifact: `app/models/catboost_task_classifier.cbm` (Docker: `CLASSIFIER_MODEL_PATH`).

## Out of scope

- Full monorepo compose with backend/frontend/postgres (backend Э6).
- Real OpenRouter/Ollama smoke in CI.
- Production secrets management.
