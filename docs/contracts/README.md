# Контракты интеграции — Prompt Radar

Здесь зафиксированы границы между сервисами. **Контракт — источник истины.** Любое изменение
поля/эндпоинта сначала правится здесь, потом в коде, и синхронизируется с владельцем другой стороны.

Модель интеграции — **стриминговый CQRS** (см. `docs/decisions/DECISIONS.md` → D1).

## Файлы
- [`backend-ml.md`](./backend-ml.md) — backend ↔ ML (стриминг: PUT /logs, POST /recompute, GET /statistics).
- [`log.schema.json`](./log.schema.json) — JSON Schema одной записи лога (backend → ML в `PUT /logs`).
- [`statistics.schema.json`](./statistics.schema.json) — JSON Schema ответа `GET /statistics` (ML → backend).
- [`backend-frontend.md`](./backend-frontend.md) — backend ↔ frontend (REST для живого дашборда).

## Владельцы
| Контракт | Сторона A | Сторона B | Кто ведёт файл |
|---|---|---|---|
| backend ↔ ML | backend (клиент) | ml_service (сервер) | backend + ML вместе |
| backend ↔ frontend | backend (сервер) | frontend (клиент) | backend |

## Владение данными
- **ML** владеет аналитическим стором: Qdrant (векторы) + лёгкая мета-БД (кластеры, имена
  сценариев, назначения, агрегаты). См. D2.
- **Backend** владеет бизнес-состоянием: пользователи, история ingestion-источников, **сырые
  ROI-поля** (tokens/manual_time/tools/status по `request_id`) для расчёта ROI.

## Версионирование
- `schema_version` — структура ответа `GET /statistics`.
- `taxonomy_version` — набор классов задач (`docs/taxonomy/`). Bump при изменении списка.
- `pipeline_version` — версия ML-пайплайна (информационно).
- Backend-frontend API — под префиксом `/api/v1`. Ломающее изменение → `/api/v2`.

## Открытые вопросы для согласования (⚠ COORDINATE)
1. **Таксономия**: фиксируем 7-классовый v1 (`docs/taxonomy/taxonomy_v1.md`). Подтвердить с ML.
2. **`X-Service-Token`** на эндпоинтах ML — согласовать с ML (мы вводим как в `template`).
3. **Онлайн-порог** cosine-сходства для назначения в кластер (старт `0.85`) и параметры
   UMAP/HDBSCAN — ведёт ML в своём `config.yaml`, но значения фиксируем в метаданных ответа.
4. **Нормализация**: сырой датасет (`user_query/category/style/...`) не совпадает с `log.schema`.
   Маппинг и синтез `request_id`/`timestamp` делает backend перед стримингом (см. `backend-ml.md`).
