# ML Service — Prompt Radar

Аналитика запросов к корпоративным ИИ-агентам: классификация → сценарии → саммари → агрегаты для дашборда.

Реализует **стриминговый CQRS** (см. `docs/contracts/backend-ml.md`, `docs/decisions/DECISIONS.md` → D1):

| Поток | Endpoint | Поведение |
|--------|----------|-----------|
| **write** | `PUT /api/v1/logs` | 202 + фон: классификация → эмбеддинг → онлайн-кластер |
| **recompute** | `POST /api/v1/recompute` | Тяжёлый UMAP+HDBSCAN + LLM-нейминг (вручную/крон) |
| **read** | `GET /api/v1/statistics` | Мгновенно из стора, без вызова моделей |

Health (без префикса API): `GET /health/live`, `GET /health/ready`.

---

## Quick start (Docker)

```bash
cd ml_service
cp .env.example .env
# optional: set OPENROUTER_API_KEY for real embeddings/summarization
# default EMBEDDINGS_PROVIDER=mock works offline

make ml-up          # qdrant + ml-service on :8000 / :6333
curl http://localhost:8000/health/ready
make seed           # demo batches (builtin sample if no dataset file)
# or full path:
# make demo          # up → ready → seed → recompute → print statistics
```

Without Make:

```bash
docker compose up -d --build
python scripts/seed_demo.py --url http://localhost:8000 --recompute
```

Optional local Ollama embeddings:

```bash
docker compose --profile ollama up -d
# then set EMBEDDINGS_PROVIDER=ollama in .env and recreate ml-service
```

---

## Local run (no Docker for app)

```bash
cd ml_service
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -e .   # or: pip install the deps from pyproject.toml
cp .env.example .env

# Qdrant still recommended:
docker compose up -d qdrant

export EMBEDDINGS_PROVIDER=mock
export CLASSIFIER_MODEL_PATH=./app/models/catboost_task_classifier.cbm
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

## Environment

See [`.env.example`](./.env.example). Important variables:

| Variable | Default | Notes |
|----------|---------|--------|
| `ML_SERVICE_TOKEN` | empty | Empty = open local/dev; set in shared env. Header: `X-Service-Token` |
| `EMBEDDINGS_PROVIDER` | `mock` | `mock` \| `ollama` \| `openrouter` |
| `OPENROUTER_API_KEY` | empty | **Never commit.** Needed for openrouter embeddings + LLM names |
| `QDRANT_URL` | `http://localhost:6333` | In compose: `http://qdrant:6333` |
| `ML_META_DB_URL` | sqlite local | Meta store path |
| `CLASSIFIER_MODEL_PATH` | `./app/models/...` | CatBoost `.cbm` artifact |
| `CLASSIFIER_CONFIDENCE_THRESHOLD` | `0.60` | Below → `unknown` |
| `ONLINE_SIMILARITY_THRESHOLD` | `0.85` | Online cluster assignment |
| `OLLAMA_URL` / `OLLAMA_MODEL` | localhost / qwen3-embedding:4b | Local embeddings |
| `LOG_LEVEL` | `INFO` | |

Secrets (`OPENROUTER_API_KEY`, real `ML_SERVICE_TOKEN`) only via env / local `.env` (gitignored).

---

## Classifier artifact

- Path: `app/models/catboost_task_classifier.cbm` (also expected as `/app/app/models/...` in Docker).
- If the file is missing, MVP falls back to a **keyword heuristic** (not fictitious CatBoost training at runtime).
- Retrain offline via `catboost/train_catboost.py` when you have labeled data; do not invent labels in production paths.
- Taxonomy: `app/domain/taxonomy.py` + `docs/taxonomy/taxonomy_v1.md` (`taxonomy_version` in `/statistics`).

---

## Demo dataset → logs

Backend (or this seed script) normalizes raw rows to [`log.schema.json`](../docs/contracts/log.schema.json).

| Dataset field | Log field |
|---------------|-----------|
| `user_query` | `query_text` |
| index | `request_id` = `req_{index}` |
| synthetic / now | `timestamp` |
| upload id | `source_id` |
| `status` | `response_status` + `error_code` |
| `category` | `metadata.gold_category` |
| style, agent_steps, tools, tokens, manual time | `metadata.*` |

Default dataset path: `notebooks/prompt_radar_dataset.json` (not always in git).  
If missing, `scripts/seed_demo.py` uses a small built-in sample so demos still work.

```bash
python scripts/seed_demo.py \
  --url http://localhost:8000 \
  --dataset ../notebooks/prompt_radar_dataset.json \
  --source-id demo \
  --recompute
```

---

## Makefile targets

From `ml_service/`:

| Target | Action |
|--------|--------|
| `make ml-up` | `docker compose up -d --build` |
| `make ml-down` | stop stack |
| `make ml-test` | pytest (unit + smoke, mock embeddings) |
| `make smoke` | smoke only |
| `make seed` | stream demo batches |
| `make demo` | up → ready → seed+recompute → print stats |
| `make lint` | ruff if installed |

---

## Tests / smoke (no live LLM)

```bash
export EMBEDDINGS_PROVIDER=mock   # default in config loader
pytest tests/ -q
# or
make ml-test
```

Smoke (`tests/test_smoke.py`) covers:

- `/health/live` + `/health/ready`
- `PUT /api/v1/logs` → process → `GET /api/v1/statistics`
- `POST /api/v1/recompute` path with mock embeddings
- dataset→log mapping helpers (no network)

---

## CQRS notes

- **Write** is async: client gets 202 before classification finishes; poll `/assignments` or wait briefly before stats.
- **Recompute** is the de-risk path for demos: stabilizes clusters and optional LLM names; online threshold alone is sensitive.
- **Read** must stay fast: no model calls on `GET /statistics`.
- ML owns analytical store (Qdrant + meta). Backend owns users, sources, ROI (D6).

---

## MVP limits (ТЗ §18)

- Single process background worker (no Kafka / multi-replica queue).
- Online cosine threshold is sensitive; recompute stabilizes scenarios.
- Local Qdrant + SQLite meta (not managed cloud).
- CatBoost artifact prepared offline; keyword fallback if missing.
- LLM scenario names need `OPENROUTER_API_KEY`; without it, fallback names / mock embeddings still produce clusters for demo.
- Failure analysis may return `not_available` when signals are sparse.
- No horizontal scaling of the ingest worker in MVP.

---

## Layout

```
ml_service/
  app/                 # FastAPI, pipeline, store adapters
  scripts/seed_demo.py # demo seed
  models via app/models/*.cbm
  tests/
  Dockerfile
  docker-compose.yml   # ml-service + qdrant (+ optional ollama profile)
  config.yaml
  pyproject.toml
  .env.example
  Makefile
```

Контракты: `docs/contracts/backend-ml.md`, `log.schema.json`, `statistics.schema.json`.  
ТЗ: `ml_service/ТЗ.md`.
