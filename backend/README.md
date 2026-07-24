# Prompt Radar — Backend

Модульный монолит на FastAPI (`api/` → `service/` → `domain/` → `database/`) для аналитики
запросов к корпоративным ИИ-агентам. Модель интеграции с ML — стриминговый CQRS
(см. `docs/decisions/DECISIONS.md` → D1, `docs/contracts/backend-ml.md`).

> Статус: **Э1 — каркас (skeleton)**. Реализованы конфиг, слой БД + миграции, health/ready/ping,
> единый формат ошибок, примитивы безопасности. Доменные эндпоинты (ingestion, dashboard, ROI,
> auth) добавляются на следующих этапах — см. TODO ниже и `docs/backend/BACKEND_TASK.md` §15.

## Стек

Python 3.13 · FastAPI · SQLAlchemy 2.0 (async, asyncpg) · Alembic · Pydantic v2 ·
pydantic-settings · httpx · PyJWT[crypto] · passlib[argon2] · uvicorn. Менеджер — Poetry.

## Быстрый старт (локально)

```bash
cd backend
cp .env.example .env          # задайте DATABASE_URL, JWT_SECRET (>=32 симв.), ML_SERVICE_*
poetry install                # включая dev-группу

cd src
alembic upgrade head          # создать схему БД
uvicorn main:app --reload --host 0.0.0.0 --port 8080
```

Нужен запущенный PostgreSQL (`DATABASE_URL`). ML-сервис для `/api/ready` опционален:
если `ML_SERVICE_URL` недоступен, backend остаётся `ready` (ML-проверка отражается в `checks`).

## Docker

```bash
docker build -t prompt-radar-backend .
# entry.sh: alembic upgrade head -> seed-плейсхолдер -> uvicorn
docker run --env-file .env -p 8080:8080 prompt-radar-backend
```

В compose backend ходит в ML по DNS (`http://ml-service:8000`) — `localhost` в контейнер не зашивается.

## Health

- `GET /api/ping` — `{ "status": "ok" }`
- `GET /api/health` — статус зависимостей (`database`, `ml`)
- `GET /api/ready` — `200` (ready) / `503` (not_ready); БД обязательна, ML degraded не блокирует

## Проверки

```bash
poetry run ruff check src
poetry run ruff format src
poetry run pytest
```

## Ограничения MVP

Фоновая обработка — в одном процессе (без Celery/брокера); статистика дашборда кэшируется с TTL;
`timestamp` demo-датасета синтезируется; таксономия v1; ставки ROI — предпосылки, не факт.
