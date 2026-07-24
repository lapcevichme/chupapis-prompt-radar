# Контракт: Backend ↔ ML-сервис (стриминговый CQRS)

**Статус:** актуальный (см. `docs/decisions/DECISIONS.md` → D1, D2).
**Источник со стороны ML:** `ml_service/ТЗ.md`. Здесь — согласованный срез со стороны backend.

Backend — **клиент**, ML — **сервер**. ML владеет аналитическим стором (Qdrant + мета-БД).
Разделение потоков: запись (async ingestion) · тяжёлый пересчёт (recompute) · чтение (fast).

## 0. Транспорт и аутентификация

- ML доступен по `ML_SERVICE_URL` (в compose: `http://ml-service:8000`).
- Все вызовы ML несут заголовок `X-Service-Token: <ML_SERVICE_TOKEN>`.
  ⚠ COORDINATE: подтвердить с ML (в `ТЗ.md` изначально не описано).
- Префикс API: `/api/v1`. Health — без префикса: `/health/live`, `/health/ready`.
- Большие тексты передаются в теле `PUT /logs` батчами (по умолчанию ≤ 200 записей/батч),
  а не одним гигантским запросом.

## 1. Нормализация (ответственность backend, ДО стриминга)

Backend превращает сырой датасет (наш `prompt_radar_dataset.json`, CSV, JSONL) в записи
[`log.schema.json`](./log.schema.json) и шлёт их батчами. Маппинг нашего demo-датасета:

| Поле датасета | Поле лога | Правило |
|---|---|---|
| `user_query` | `query_text` | как есть (trim) |
| — | `request_id` | синтез: `req_{index}` (стабильно, ключ идемпотентности) |
| — | `timestamp` | синтез: раскидать по диапазону дат (демо-допущение) или `now` |
| — | `source_id` | id заливки (для фильтров дашборда) |
| `status` | `response_status` | `success`→`success`; `error_tool`/`hallucination_loop`→`error` |
| `status` | `error_code` | `error_tool`→`tool_error`; `hallucination_loop`→`hallucination_loop`; иначе `null` |
| `category` | `metadata.gold_category` | опционально, как эталон для eval |
| `style`, `agent_steps`, `tools_used`, `simulated_context_tokens`, `estimated_manual_time_minutes` | `metadata.*` | пробрасываем; backend их же хранит отдельно для ROI |

> Сырые ROI-поля backend **хранит у себя** (по `request_id`). ML их считать не обязан —
> для кластеризации они не нужны. Failure-сигналы (`response_status`, `error_code`,
> `user_feedback`, `retry_count`) ML использует для `failure_analysis`.

## 2. Поток ЗАПИСИ — `PUT /api/v1/logs`

Приём батча логов. Отвечает мгновенно, обработка — в фоне.

Request:

```json
{
  "source_id": "src_01",
  "logs": [
    { "request_id": "req_1", "query_text": "Выгрузи отчёт из CRM", "timestamp": "2026-07-24T10:00:00Z",
      "response_status": "success", "error_code": null, "metadata": { "gold_category": "data_analysis" } }
  ]
}
```

Response `202 Accepted`:

```json
{ "accepted": 1, "duplicates": 0, "rejected": 0, "source_id": "src_01" }
```

Правила:

- Идемпотентность по `request_id`: повторная присылка того же id не создаёт дубль (обновление/skip).
- В фоне для каждой записи: CatBoost-классификация → эмбеддинг (async, Ollama/OpenRouter) →
  онлайн-назначение в кластер по cosine-сходству к центроидам (≥ порога → в существующий и
  пересчёт центроида; иначе новый кластер без имени).
- Невалидные записи не роняют батч; счётчик `rejected` в ответе, причины — в метриках/логах ML.

## 3. Поток ПЕРЕСЧЁТА — `POST /api/v1/recompute`

Тяжёлый пересчёт: UMAP + HDBSCAN полная перекластеризация + LLM-нейминг новых ядер сценариев.
Триггерится **вручную** (главный де-риск демо) и опционально по крону.

Request (опц.): `{ "scope": "all" }`
Response `202`:

```json
{ "job_id": "rc_01", "status": "running", "started_at": "2026-07-24T10:05:00Z" }
```

### `GET /api/v1/recompute/{job_id}` → 200

```json
{ "job_id": "rc_01", "status": "completed", "clusters_created": 18,
  "scenarios_named": 15, "finished_at": "2026-07-24T10:05:40Z" }
```

`status` ∈ `running | completed | failed`. Backend поллит до завершения (или показывает прогресс).

## 4. Поток ЧТЕНИЯ (fast, из стора, без ML-моделей)

### `GET /api/v1/statistics` → 200

Готовые агрегаты для дашборда. Фильтры (опц.): `?source_id=&from=&to=`.
Структура — [`statistics.schema.json`](./statistics.schema.json): `totals`, `tasks_distribution`,
`top_scenarios`, `dynamics`, `outliers_summary`, `failure_analysis`, `freshness`, `pipeline_metadata`.
Backend валидирует ответ по схеме, кэширует и обогащает (ROI + человекочитаемые ярлыки).

### `GET /api/v1/scenarios` (+ `/{scenario_id}`) → 200

Полный список сценариев / детали (name, summary, user_goal, examples, pain_points,
automation_potential, records_count, trend, statistical_reliability).

### `GET /api/v1/assignments` → 200

Назначения по записям — для ROI-джойна backend и таблицы логов. Фильтры:
`?source_id=&limit=&offset=&updated_since=`.

```json
{ "items": [
  { "request_id": "req_1", "task_type": "data_analysis", "classification_confidence": 0.91,
    "scenario_id": "data_analysis:cluster_01", "scenario_name": "Экспорт отчётов CRM",
    "is_outlier": false, "has_failure_signals": false }
], "total": 348 }
```

## 5. Health

- `GET /health/live` → `{ "status": "ok" }`
- `GET /health/ready` → `{ "status": "ready|degraded|not_ready", "checks": { "config", "qdrant",
  "classifier", "embeddings_provider", "llm_provider" } }`. Backend отражает это в своём `/api/ready`.

## 6. Коды ошибок ML

`INVALID_REQUEST · INGEST_VALIDATION_FAILED · CLASSIFIER_NOT_AVAILABLE ·
EMBEDDING_PROVIDER_UNAVAILABLE · EMBEDDING_REQUEST_FAILED · LLM_PROVIDER_UNAVAILABLE ·
LLM_RESPONSE_INVALID · CLUSTERING_FAILED · STORE_UNAVAILABLE · RECOMPUTE_FAILED · INTERNAL_ERROR`

Формат: `{ "code", "message", "retryable", "details"? }`. Секреты/stack trace наружу не отдаются.

## 7. Поведение backend при сбоях ML

- ML недоступен на `PUT /logs` → ingestion-источник помечается `failed`, UI показывает retry.
- `POST /recompute` упал/таймаут → показываем `failed`, дашборд остаётся на прошлом снапшоте.
- `GET /statistics` не проходит схему → backend отдаёт последний валидный кэш + помечает деградацию.
- Эмбеддинги/LLM недоступны → ML работает в degraded (классификация без сценариев / fallback-имена),
  что видно в `pipeline_metadata`/`freshness`.

## 8. Reproducibility

- UMAP с фиксированным `random_state`; онлайн-порог и параметры UMAP/HDBSCAN — в `pipeline_metadata`.
- Детерминированная загрузка сид-датасета + снапшот после `recompute` дают воспроизводимую картину.
