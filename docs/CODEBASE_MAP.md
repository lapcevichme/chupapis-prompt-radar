# Prompt Radar — карта кодовой базы

Актуализировано 2026-07-25 по коду в ветке `main`. Это навигационный документ: продуктовые
требования остаются в материалах кейса, точные формы данных — в `docs/contracts/`, а обязательные
правила для агентов — в корневом `AGENTS.md`.

## Система в одном абзаце

Prompt Radar принимает датасеты и live-логи корпоративных ИИ-агентов. Backend нормализует их,
сохраняет бизнес-поля в Postgres и отправляет записи в ML. ML классифицирует запросы, строит
эмбеддинги и сценарии, сохраняет аналитическое состояние в Qdrant/meta-store и отдаёт готовую
read-модель. Backend объединяет назначения ML со своими данными для ROI, а React-фронтенд
показывает обзор, источники, сценарии, логи/выбросы и ROI.

```text
dataset / OWUI / live feeder
            |
            v
  backend :8080  ------>  ml-service :8000  ------> Qdrant :6333
      |          HTTP       classify/cluster          vectors
      |                     summarize/aggregate
      v
 Postgres :5433
 users, sources, raw ROI, assignment mirror
      ^
      |
 frontend :3000  (только backend REST, cookie auth)
```

## Основные потоки

### Загрузка датасета

1. `POST /api/v1/ingest` принимает JSON demo-флаг или multipart JSON/CSV.
2. `backend/src/service/ingestion/normalizer.py` приводит строки к
   `docs/contracts/log.schema.json`, синтезируя недостающие ID/timestamp и сохраняя отчёт.
3. `IngestionService` пишет источник и ROI-поля в Postgres.
4. FastAPI `BackgroundTasks` отправляет батчи в ML через `MlClient.stream_logs()` и обновляет статус
   источника после появления фактических assignments в асинхронном ML worker.
5. Backend подтягивает `/assignments` ML в таблицу `log_assignments` для `/logs` и ROI.

Одинаковый внешний `request_id` получает разные канонические UUID в разных `source_id`, поэтому
несколько датасетов не дедуплицируют записи друг друга. При старте Compose backend идемпотентно
создаёт три непересекающихся preloaded workspace из demo fixture, дожидается классификации и
запускает один общий recompute. Файловая загрузка JSON/JSONL/CSV остаётся доступной.

### Live ingestion

`POST /api/v1/logs` backend защищён `X-Ingest-Token`, пишет записи в rolling source с
`origin=live` и синхронно передаёт нормализованный батч в ML. Этот вход используют
`tools/feed_live.py` и OWUI-фильтр `ml_service/filter.py`.

### ML write/read/recompute

- `PUT /api/v1/logs`: идемпотентный приём по `request_id`, затем фоновые classification,
  embeddings и online cosine assignment внутри `task_type`.
- `GET /api/v1/statistics`, `/scenarios`, `/assignments`: чтение готового состояния без вызова
  LLM/embedding provider.
- `POST /api/v1/recompute`: UMAP + HDBSCAN по каждому `task_type`, стабилизация `scenario_id`,
  выбор репрезентативных запросов и опциональное LLM-саммари.
- Backend после завершения recompute повторно синхронизирует assignments и инвалидирует кэш.

### Dashboard и ROI

`DashboardService` валидирует/маппит статистику ML и держит in-memory TTL-кэш. `RoiService`
соединяет `dataset_records` и локальное зеркало `log_assignments` по source/request ID.
Ставки и session-коэффициенты приходят из backend settings и возвращаются в `assumptions`, чтобы
не выдавать оценку за измеренный факт.

## Компоненты

### `backend/`

Стек: Python 3.13, FastAPI, Pydantic v2, SQLAlchemy 2 async, asyncpg, Alembic, Poetry.

- `src/main.py` — app factory, lifespan, CORS, `/api/ping|health|ready`.
- `src/api/v1/` — auth, ingest/live, sources, recompute, dashboard, scenarios, logs, ROI/export.
- `src/service/ingestion/` — JSON/CSV parsing, нормализация, Postgres, preloaded workspaces и
  streaming в ML.
- `src/service/ml/client.py` — единственная HTTP-граница backend → ML.
- `src/service/dashboard/` — статистика, assignments mirror и TTL-кэш.
- `src/service/roi/` — FTE/стоимость/экономия и разрезы по категориям/сценариям.
- `src/service/export/` — XLSX/CSV без тяжёлой табличной зависимости.
- `src/database/relational_db/tables/` — users, ingestion_sources, dataset_records,
  log_assignments, roi_cache.
- `src/migrations/versions/0001_initial_schema.py` — текущая схема БД.
- `tests/` — unit и ASGI API tests; внешние сервисы подменяются.

Auth — JWT access/refresh в httpOnly cookies. Пользовательские `/api/v1/*` защищены cookie;
live webhook использует отдельный ingest token. ML failure должен превращаться в контролируемую
ошибку/degraded state, а не в необработанный 500.

### `ml_service/`

Стек: Python 3.11+, FastAPI, CatBoost, NumPy/scikit-learn, UMAP, HDBSCAN, qdrant-client, uv.

- `app/main.py` — runtime state и весь HTTP API ML.
- `app/ingest/` — in-process очередь и worker.
- `app/pipeline/classification/` — загрузка CatBoost и явный fallback.
- `app/pipeline/embeddings/` — mock/Ollama/OpenRouter adapters.
- `app/pipeline/long_text/` — chunking вместо молчаливого truncate.
- `app/pipeline/clustering_online/` — online cosine clusters.
- `app/pipeline/clustering_batch/`, `app/recompute/` — UMAP/HDBSCAN, stability, representatives,
  scheduler/job.
- `app/pipeline/summarization.py` — структурированное имя/summary сценария и fallback.
- `app/pipeline/aggregation/` — read-модель статистики.
- `app/store/qdrant.py` — Qdrant с in-memory fallback; коллекция создаётся при старте сервиса.
- `app/database/meta_store.py` — лёгкая мета-БД.
- `config.yaml` и `.env.example` — параметры провайдеров и пайплайна.
- `tests/` и `eval/` — pipeline/contract/smoke и оценка классификации.

В offline-режиме сервис работоспособен с mock embeddings, но это не показатель качества. Для
осмысленного демо нужны совместимые реальные embeddings через OpenRouter/Ollama. Артефакт
CatBoost лежит в `app/models/`; при несовместимом или отсутствующем артефакте используется явно
описанный fallback.

### `frontend/`

Стек: React 19, TypeScript, Vite 6, Tailwind 4, Recharts, npm.

- `src/app/App.tsx` — bootstrap cookie-auth, глобальные фильтры, polling и переключение пяти
  лениво загружаемых экранов без роутера.
- `src/features/dataset-switcher/` — выбор общего представления или конкретного `source_id`;
  один фильтр применяется к Dashboard, Scenarios, Logs, ROI и экспортам.
- `src/shared/api/promptRadarApi.ts` — единый типизированный клиент backend.
- `src/shared/api/http.ts` — query/body handling, `credentials: include`, refresh после 401.
- `src/entities/` — локальные типы API; при контрактных изменениях синхронизировать вручную.
- `src/pages/` — Login, Dashboard, Sources, Scenarios, Logs, ROI; ROI поддерживает what-if и
  XLSX/CSV-экспорт с теми же фильтрами.
- `src/features/workspace-actions/` — ingestion/recompute actions.
- `src/widgets/` и `src/shared/ui/` — shell и общие состояния/примитивы.
- `vite.config.ts` — alias `@`, Vitest/jsdom и dev proxy `/api` → backend `:8080`.
- `Dockerfile` и `nginx.conf` — production-сборка SPA, history fallback и same-origin `/api`.

Frontend пытается восстановить cookie-сессию и показывает обычную форму входа. Demo-autologin
включается только build-time флагом `VITE_AUTO_DEMO_LOGIN`; корневой Compose включает его по
умолчанию для локального демо, а standalone Vite — нет. Выход из аккаунта отключает повторный
autologin в текущей вкладке.

## Контракты и версии

- `docs/contracts/log.schema.json` — backend → ML, одна нормализованная запись.
- `docs/contracts/upload-dataset.schema.json` — рекомендуемый сырой JSON для пользовательской
  загрузки и генераторов датасетов.
- `docs/contracts/statistics.schema.json` — ML → backend, готовая аналитическая read-модель.
- `docs/contracts/backend-ml.md` — HTTP и деградация между backend/ML.
- `docs/contracts/backend-frontend.md` и `openapi-backend-frontend.yaml` — публичный REST.
- `docs/taxonomy/taxonomy_v1.md` — семь продуктовых классов плюс служебные значения.

Проверяй и меняй обе стороны контракта атомарно. Backend не должен доверять произвольной
статистике ML: валидация находится в `backend/src/service/ml/statistics_validation.py`.

## Runtime и локальный запуск

Корневой `docker-compose.yml` поднимает frontend/nginx, backend, Postgres, Qdrant и ML. Persistent
volumes: `postgres_data`, `qdrant_data`, `ml_meta_data`; Ollama доступна отдельным profile. Порты
по умолчанию: frontend `3000`, backend `8080`, ML `8000`, Qdrant `6333`, host Postgres `5433`.

```bash
cp .env.example .env
cp ml_service/.env.example ml_service/.env
make up
make demo
```

Приложение: `http://localhost:3000`; Swagger backend: `http://localhost:8080/api/docs`.
Для hot reload можно отдельно запустить `cd frontend && npm ci && npm run dev`. Demo credentials:
`test@gmail.com` / `test123`. Provider/model config и секреты ML хранятся только в локальном
`ml_service/.env`; Compose загружает его напрямую, но переопределяет контейнерные URL/пути.
Практический runbook для local/remote demo и формат генерируемых датасетов находится в
`docs/DEMO_AND_DATASET_GUIDE.md`.

## Состояние и границы проверки

На момент актуализации:

- backend: `57 passed`; `ruff check src tests` проходит;
- ML: `95 passed, 8 deselected` в runtime-образе с mock providers; отдельный online smoke через
  OpenRouter создал реальные embeddings/assignments в Qdrant;
- frontend: lint, пять Vitest-тестов и production build проходят; npm audit не находит уязвимостей;
- основной Compose на чистых volumes поднял три preloaded источника (170 + 106 + 109 = 385),
  создал 385 OpenRouter-векторов размерности 2560, завершил heavy recompute с 22 сценариями и
  проверен по dashboard, scenarios, logs, ROI и XLSX/CSV через frontend/nginx.

Исторические `TASKS.md` и локальные планы могут содержать уже неверные статусы. Они полезны для
причин решений, но не для ответа «что работает сейчас» без повторной проверки кода и тестов.

## Известные ограничения и точки внимания

- FastAPI `BackgroundTasks`, очередь ML и `_LAST_JOB_ID` рассчитаны на один процесс. Несколько
  worker/replika без внешней очереди и общего job-store нарушат ожидания.
- Online cosine centroids пока не восстанавливаются из meta-store после рестарта (TODO в
  `cosine_clusterer.py`). Heavy recompute — путь стабилизации сценариев.
- Read-кэш backend — память процесса, не Redis; фильтры входят в cache key.
- `.gitignore` исторически исключает локальные `.claude/`, `TASKS.md`, `docs/decisions/` и
  `template/`. Важные долговечные правила нужно переносить в tracked `AGENTS.md` или docs.
- Dependency lock policy неоднородна: frontend lock tracked, Python lock-файлы отсутствуют.
- Полный end-to-end зависит от Postgres/Qdrant и выбранного embeddings provider; unit-тесты не
  заменяют smoke на чистых volumes перед демонстрацией.
- Входной timestamp файлов сейчас не читается normalizer: для Dynamics синтезируется шкала за
  `NORMALIZE_TIMESTAMP_SPAN_DAYS` (по умолчанию 14). Реальные даты требуют контрактного изменения.
- Корневой Compose — single-host demo/staging. Для production нужны TLS/firewall/secrets/backups,
  task broker + общий job state, IAM/RBAC, monitoring и migration policy embeddings.
