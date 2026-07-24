# Техническое задание — Backend «Промпт-радар»

**Версия:** 2.0 (стриминговый CQRS) · **Контур:** hackathon MVP · **Роль автора:** backend + DevOps
**Расположение:** `backend/`

План и контекст для бэкендера. Согласован с `ml_service/ТЗ.md` (v2.0), `docs/contracts/` и
`docs/decisions/DECISIONS.md`. При расхождении — контракты приоритетнее.

---

## 1. Архитектура (со схемой)

```text
┌────────────────────┐   REST /api/v1 (JSON, cookie-auth)
│  Frontend (SPA)    │◀─ dashboard · scenarios · roi · logs ─┐
│  живой дашборд CTO  │                                        │
└────────────────────┘                                        │
                                                              ▼
                          ┌──────────────────────────────────────────────┐
                          │            Backend (FastAPI монолит)          │
                          │  api/ → service/ → domain/ → database/        │
                          │  • ingestion: нормализация → стрим батчей в ML │
                          │  • Postgres: users, ingestion_sources,         │
                          │    dataset_records (сырые ROI-поля)            │
                          │  • ROI-слой · read-API (проксирует+кэширует    │
                          │    статистику ML) · auth (JWT)                 │
                          └───┬───────────────┬───────────────┬───────────┘
              PUT /logs (батчи)│  POST /recompute│   GET /statistics,/assignments
                               ▼               ▼               ▲
                          ┌──────────────────────────────────────────────┐
                          │           ML service (ml_service)             │
                          │  write: classify+embed+онлайн-назначение      │
                          │  recompute: UMAP+HDBSCAN+LLM-нейминг           │
                          │  read: агрегаты из стора (Qdrant + мета-БД)    │
                          └──────────────────────────────────────────────┘
```

**Модель интеграции — стриминговый CQRS** (D1). **ML владеет аналитическим стором** (Qdrant +
мета-БД, D2). **Backend владеет бизнес-состоянием** и **считает ROI** (D6). Дашборд — глобальный
живой с фильтрами (D3).

---

## 2. Назначение и границы

**Backend отвечает за:**

- ingestion: приём/загрузку датасета (upload или demo), нормализацию в записи `log.schema.json`,
  **стриминг батчами** в ML (`PUT /logs`), отслеживание статуса источника;
- триггер пересчёта (`POST /recompute`, проксирует в ML) и слежение за статусом;
- хранение бизнес-состояния в Postgres: пользователи, ingestion-источники, **сырые ROI-поля**;
- расчёт ROI/FTE (джойн сырых полей с назначениями ML);
- read-API для дашборда: проксирование + кэш статистики ML, обогащение ROI и человекочитаемыми
  ярлыками, пагинация/фильтры;
- аутентификацию (JWT access+refresh, cookie), seed demo-учётки;
- health/readiness (включая проверку ML).

**Backend НЕ отвечает за:** эмбеддинги, кластеризацию, саммаризацию, векторный стор — это ML.
Backend не импортирует код ML.

---

## 3. Технологический стек

Python 3.13 · FastAPI · SQLAlchemy 2.0 (async, asyncpg) · Alembic · Pydantic v2 ·
pydantic-settings · httpx · PyJWT[crypto] · passlib[argon2] · uvicorn · (опц.) redis. Инструменты:
ruff, pytest, pytest-asyncio. Менеджер — poetry. Паттерны переносим из `template/backend/src`.

---

## 4. Структура каталога `backend/`

```text
backend/
├── pyproject.toml, poetry.lock, Dockerfile, entry.sh, .env.example, pytest.ini
├── src/
│   ├── main.py                       # create_app, lifespan, health/ready/ping
│   ├── core/                         # config, error_handling, errors, security, http/cookies, middlewares
│   │   # rbac.py — переносим закомментированным (роли не нужны, D5)
│   ├── database/relational_db/       # session, unit_of_work, tables/ (см. §6)
│   ├── domain/                       # Pydantic-схемы, enum: auth, ingestion, dashboard, roi, common
│   ├── service/
│   │   ├── auth/                     # credentials_auth + token_service (порт)
│   │   ├── ingestion/                # приём + нормализация + стриминг батчей в ML
│   │   ├── ml/                       # HTTP-клиент ML (PUT /logs, /recompute, /statistics, /assignments)
│   │   ├── dashboard/                # проксирование+кэш статистики, обогащение ярлыками
│   │   ├── roi/                      # порт roi_engine.py + разрезы
│   │   └── seeding/                  # seed demo-учётки
│   ├── api/v1/                       # тонкие роутеры: auth, ingest, sources, recompute, dashboard, scenarios, logs, roi
│   ├── migrations/                   # alembic
│   └── scripts/                      # seed, утилиты
└── tests/ (unit, integration, contract)
```

---

## 5. Конфигурация (env)

```text
# App
APP_STAGE=dev
LOG_LEVEL=INFO
API_HOST=0.0.0.0
API_PORT=8080

# DB / cache
DATABASE_URL=postgresql+asyncpg://postgres:...@db:5432/prompt_radar
REDIS_URL=redis://redis:6379/0          # опционально (кэш статистики/ROI)

# Auth
JWT_SECRET=<>=32 символов>
ACCESS_TTL=900
REFRESH_TTL=604800
COOKIE_SECURE=false
COOKIE_SAMESITE=lax
DEMO_USER_EMAIL=demo@prompt-radar.local
DEMO_USER_PASSWORD=DemoPass123!

# ML integration
ML_SERVICE_URL=http://ml-service:8000
ML_SERVICE_TOKEN=change-me-ml-token
ML_INGEST_BATCH_SIZE=200
ML_HTTP_TIMEOUT_SEC=30

# ROI defaults (предпосылки расчёта)
ROI_FTE_HOURLY_RATE_RUB=1200.0
ROI_TOKEN_COST_PER_1K_RUB=0.015

# Normalization
NORMALIZE_SYNTHESIZE_TIMESTAMPS=true
NORMALIZE_TIMESTAMP_SPAN_DAYS=14
```

Секреты только через env; конфиг валидируется при старте; `localhost` не зашивать в контейнер.

---

## 6. Модель данных (Postgres)

Backend хранит только бизнес-состояние. Векторы/кластеры/сценарии — в сторе ML.

- **`users`** — `id`, `email` (unique), `password_hash`, `created_at`. (порт из template, урезанный)
- **`ingestion_sources`** — `id` (=`source_id`), `name`, `origin` (`upload|demo`), `records_total`,
  `records_valid`, `records_rejected`, `normalization_report` JSONB, `status`
  (`ingesting|classified|recomputed|failed`), `created_by`, `created_at`.
- **`dataset_records`** — сырые поля для ROI-джойна и таблицы логов:
  `source_id` FK, `request_id`, `query_text`, `gold_category`(nullable), `style`,
  `tokens` (=`simulated_context_tokens`), `manual_time_minutes`, `tools_used` JSONB, `status`,
  `timestamp`. Индекс `(source_id, request_id)`.
- **`log_assignments`** (кэш назначений от ML для ROI и `/logs`) — `source_id` FK, `request_id`,
  `task_type`, `classification_confidence`, `scenario_id`, `scenario_name`, `is_outlier`,
  `has_failure_signals`, `updated_at`. Периодически синхронизируется из ML `GET /assignments`.
- **`roi_cache`** (опц.) — `key` (source_id/фильтры/ставки), `summary`/`by_category`/`by_scenario`
  JSONB, `computed_at`. Либо кэш в Redis.

> `dashboard` (статистику ML) кэшируем в Redis/JSONB с коротким TTL — это read-модель, источник в ML.

Миграции — Alembic (`entry.sh`: `alembic upgrade head` при старте).

---

## 7. Нормализация датасета

Backend превращает сырой датасет в записи `log.schema.json`. Правила маппинга — в
`docs/contracts/backend-ml.md` §1. Ключевое:

- синтез `request_id` (`req_{index}`), стабильно; синтез `timestamp` (демо-допущение, если включено);
- маппинг `status` → `response_status` + `error_code`;
- сохранить сырые ROI-поля в `dataset_records` для ROI;
- невалидные строки не роняют импорт; для каждой отклонённой — причина; порог настраиваемый;
- итог — `normalization_report`. Синтетические timestamp'ы помечаем честно (в отчёте и на дашборде).

---

## 8. Оркестрация (стриминг)

**Ingestion (`POST /ingest`):**

1. создать `ingestion_sources(status=ingesting)`, сохранить `dataset_records`;
2. нормализовать → нарезать на батчи `ML_INGEST_BATCH_SIZE`;
3. стримить батчи в ML `PUT /api/v1/logs` (async, заголовок `X-Service-Token`), считать accepted/rejected;
4. по завершении → `status=classified` (онлайн-назначения готовы, имена — после recompute).

**Recompute (`POST /recompute`):** проксировать в ML, отслеживать `GET /recompute/{job_id}`,
по завершении обновить статус источников → `recomputed`, инвалидировать кэш дашборда,
подтянуть свежие назначения (`GET /assignments`) в `log_assignments`.

**Read (дашборд):** `GET /dashboard` → проксирует `GET /statistics` (с фильтрами), кэширует,
добавляет человекочитаемые ярлыки таксономии. `GET /roi` → считает из `dataset_records` ×
`log_assignments`.

**Идемпотентность/устойчивость:** повторная заливка того же источника не плодит дубли; ML
недоступен → `status=failed` + человекочитаемая причина, backend не отдаёт 500 наружу.
Фон — asyncio-задача/`BackgroundTasks` в одном процессе (без Celery, вне объёма MVP; ограничение в README).

---

## 9. API (backend ↔ frontend)

Полный контракт с примерами — `docs/contracts/backend-frontend.md`. Группы:

- **auth:** `POST /auth/login`, `/auth/refresh`, `/auth/logout`, `GET /users/me`;
- **ingestion:** `POST /ingest`, `GET /sources`, `GET /sources/{id}`;
- **recompute:** `POST /recompute`, `GET /recompute/status`;
- **dashboard:** `GET /dashboard`, `/scenarios`, `/scenarios/{id}`, `/logs` (все с фильтрами
  `source_id/from/to`, пагинацией);
- **roi:** `GET /roi` (+ переопределение ставок), `GET /export?format=xlsx|csv` (опц.);
- **health:** `/api/health`, `/api/ready`, `/api/ping`.

Каждый endpoint — тонкий роутер + `response_model`. Единый формат ошибки. Пагинация для списков.

---

## 10. ROI-слой

Порт `ml_service/roi_engine.py` → `service/roi`. Вход — джойн `log_assignments`
(`request_id → task_type, scenario_id`) × `dataset_records` (`tokens, manual_time_minutes,
tools_used, status`). Выход — `summary` + `by_category` + `by_scenario` + `assumptions`
(контракт §5). Ставки из env, опц. переопределение query-параметрами. Кэш в `roi_cache`/Redis.

---

## 11. Auth

Порт из `template/backend/src/service/auth` (credentials_auth + token_service): логин
email+пароль, access+refresh в httpOnly-cookie, ротация refresh, argon2. RBAC/роли — не
подключаем (закомментированы, D5). Seed demo-учётки при старте. Между backend и ML — `X-Service-Token`.

---

## 12. Ошибки и логирование

Единый формат (`{error_code, message, details}`, порт `core/error_handling`), без stack trace
наружу. Коды backend: `SOURCE_NOT_FOUND`, `DATASET_INVALID`, `ML_UNAVAILABLE`,
`STATISTICS_SCHEMA_INVALID` + проксирование `error.code` от ML. Структурные логи с
`source_id`/стадией. Не логировать полные тексты запросов.

---

## 13. Тестирование

- **unit:** нормализация (маппинг, синтез id/timestamp, отбраковка), нарезка на батчи, расчёт ROI
  (FTE/₽/множитель, пустой вход, деление на ноль), валидация `/statistics` по схеме, ярлыки таксономии.
- **contract:** запрос/ответ `POST /ingest`, `/dashboard`, `/roi`; соответствие
  `statistics.schema.json` при чтении ML.
- **integration:** happy path (маленький датасет → ingest → recompute → dashboard), ML недоступен,
  невалидная статистика ML, повторная заливка, пустой/битый датасет.
- **smoke:** поднять backend+ML+db+qdrant → readiness → залить demo → recompute → проверить dashboard/roi.

---

## 14. Docker / infra (роль DevOps)

- `docker-compose.yml`: `backend`, `ml-service`, `qdrant`, `db` (postgres), `frontend`/caddy,
  опц. `redis`, опц. `ollama`. Healthcheck'и + `depends_on: healthy`.
- Backend `Dockerfile` + `entry.sh` (migrations → seed → uvicorn) — порт из template.
- `Makefile`: `up/down/logs`, `demo`, `backend-test`, `ml-test`, `lint`.
- `make demo`: seed + залить demo-датасет + `POST /recompute` + показать дашборд/ROI end-to-end.
- `.env.example` актуален; реальный `.env` в `.gitignore`. (опц.) CI: lint + быстрые unit.

---

## 15. Этапы реализации (синхронно с ML-этапами `ml_service/ТЗ.md` §16)

**Э1 — Каркас + ingestion контур (против mock ML).** Перенос каркаса из template (config,
session, error-handling, main, health). Модель данных + alembic. Приём demo-датасета +
нормализация. Стриминг батчей в ML `PUT /logs`. Чтение `GET /statistics` → `GET /dashboard`.
Против mock-ML (отдаёт валидную статистику). Результат: `Backend → PUT /logs → ML mock →
GET /statistics → dashboard`.

**Э2 — Auth.** Порт auth из template, seed demo-учётки, защита эндпоинтов, cookie.

**Э3 — Дашборд-API.** `dashboard/scenarios/logs` с фильтрами, проксирование+кэш статистики,
синхронизация `log_assignments`, human-labels таксономии.

**Э4 — ROI.** Порт roi_engine, джойн, разрезы, `GET /roi`, кэш, ставки из env.

**Э5 — Recompute + реальный ML.** `POST /recompute` проксирование + статус; интеграция с
настоящим ML (эмбеддинги/кластеры/саммари); обработка degraded/ошибок.

**Э6 — Infra + demo.** docker-compose (backend+ml+qdrant+db+frontend), Makefile, `make demo`,
экспорт в Excel/CSV (опц.), README с запуском и ограничениями MVP.

**Э7 — Полировка.** Профилирование горячих GET, устойчивость к сбоям ML, опц. авто-recompute-
плашка на дашборде, финальный smoke на чистом окружении.

---

## 16. Definition of Done (backend MVP)

- Поднимается через docker-compose; `/api/ready` честно отражает готовность (включая ML).
- Логин demo-учёткой; защищённые эндпоинты требуют auth.
- Можно загрузить датасет (или выбрать demo) → `normalization_report` → стрим в ML.
- `POST /recompute` проксируется, статус отслеживается, дашборд обновляется.
- Дашборд-эндпоинты отдают tasks/scenarios/dynamics/outliers/failure с фильтрами.
- `/roi` считает FTE/₽/ROI по компании, категориям и сценариям.
- Повторная заливка не плодит дублей; недоступность ML не роняет backend 500-й.
- Есть unit + contract + integration + smoke; `make demo` проходит на чистом окружении.
- README: запуск, ограничения MVP (синтетические timestamp'ы, один процесс, онлайн-порог).

---

## 17. Ограничения MVP (в README)

Фоновая обработка в одном процессе (без Celery/брокера); дашборд-статистика кэшируется с TTL;
`timestamp` в demo-датасете синтезируется; таксономия v1 (7 классов); ставки ROI — предпосылки,
не факт. Всё указываем явно.
