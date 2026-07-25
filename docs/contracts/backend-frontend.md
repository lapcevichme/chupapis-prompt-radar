# Контракт: Backend ↔ Frontend (REST для живого дашборда)

**Сервер:** backend. **Клиент:** frontend. Префикс: `/api/v1`. Формат — JSON.
Ломающее изменение → `/api/v2`. Владелец файла — backend.

Модель — **живой дашборд с workspace по датасетам**: данные можно смотреть по всему стору или
выбранному источнику через `?source_id=&from=&to=`. Дашборд читает ТОЛЬКО backend. ROI считает
backend.

## 0. Общие правила

- **Auth:** cookie-based JWT (access+refresh). При 401 фронт дёргает `POST /auth/refresh`,
  при неудаче → на логин.
- **CORS / credentials:** backend разрешает origins из `CORS_ORIGINS` (по умолчанию
  `http://localhost:3000,5173,8080`) с `allow_credentials=true`. Фронт **обязан** слать запросы с
  `credentials: 'include'` (fetch) / `withCredentials: true` (axios), иначе httpOnly-cookie не
  прикрепится. Заголовок `Content-Disposition` открыт для чтения (имя файла экспорта).
  Локально (`localhost:3000` → `:8080`) это один site → cookie `SameSite=lax` долетает. Для разных
  доменов в проде нужен `COOKIE_SAMESITE=none` + `COOKIE_SECURE=true` (HTTPS) **или** dev-proxy
  (Vite `server.proxy` / CRA `proxy`), который делает API same-origin — тогда CORS/cookie беспроблемны.
- **Формат ошибки** (единый): `{ "error_code": "not_found", "message": "...", "details": null }`.
- **Пагинация** (списки): `?limit=50&offset=0`, ответ `{ "items": [...], "total": 123 }`.
- **Фильтры дашборда** (везде опц.): `source_id` (заливка), `from`/`to` (ISO-даты).
- Выбор workspace на frontend — это фильтр `source_id`; смена дат не должна сбрасывать его.
- Даты — ISO 8601 UTC. Деньги — рубли (число). Проценты — число 0..100.

## 1. Auth

- `POST /api/v1/auth/login` — `{ "email", "password" }` → `200` (+ Set-Cookie) `{ "user": { "id", "email" } }`
- `POST /api/v1/auth/refresh` → `200` (+ new cookies)
- `POST /api/v1/auth/logout` → `204`
- `GET /api/v1/users/me` → `200` `{ "id", "email", "created_at" }`

> Регистрация не нужна — seed одна demo-учётка. Эндпоинт register может быть выключен.

## 2. Ingestion (загрузка датасета → стриминг в ML)

### `POST /api/v1/ingest`

Multipart `file` (`.json` | `.jsonl` | `.csv`) **или** JSON `{ "use_demo": true }`.
Backend нормализует и стримит батчами в ML. Ответ — сразу, обработка асинхронная.
`request_id` внутри аналитического контура детерминированно scoped по `source_id`, поэтому
одинаковые внешние ID из разных файлов не дедуплицируют друг друга.

Response `202`:

```json
{
  "source_id": "src_01",
  "name": "prompt_radar_dataset.json",
  "records_total": 350,
  "records_valid": 348,
  "records_rejected": 2,
  "normalization_report": { "synthesized_request_id": 350, "synthesized_timestamp": 350,
                            "rejected_reasons": { "empty_query_text": 2 } },
  "status": "ingesting"
}
```

### `GET /api/v1/sources` → `200`

`{ "items": [ { "source_id", "name", "origin", "records_total", "status", "created_at" } ], "total": n }`.
`status` ∈ `ingesting | classified | recomputed | failed`.
`origin` ∈ `preloaded | upload | demo | live`. Compose по умолчанию идемпотентно создаёт три
`preloaded` workspace; обычная файловая загрузка остаётся `upload`.

### `GET /api/v1/sources/{source_id}` → `200`

Детали + прогресс ingestion (`ingested`, `classified`, `assigned` счётчики). Фронт поллит.

## 2b. Live ingestion (webhook, machine-to-machine)

Для отправки логов в реальном времени (агентская платформа / OWUI-фильтр / demo-симулятор).
Авторизация — заголовок `X-Ingest-Token` (**не cookie**): это машинный вход, отдельный от пользовательского.

### `POST /api/v1/logs` → `202`

Header: `X-Ingest-Token: <INGEST_TOKEN>`. Body — сырые записи (тот же формат, что demo-датасет;
принимается и `query_text`, и `user_query`; можно передать свой `request_id`):

```json
{ "logs": [ { "user_query": "Выгрузи отчёт из CRM", "status": "success",
             "simulated_context_tokens": 12000, "estimated_manual_time_minutes": 30,
             "tools_used": ["CRM"], "category": "data_analysis" } ], "source_name": "live" }
```

Response:

```json
{ "source_id": "...", "accepted": 1, "duplicates": 0, "rejected": 0,
  "records_valid": 1, "records_rejected": 0 }
```

Backend нормализует, копит в rolling-источник `live` (`origin: "live"`) и стримит в ML. Записи видны
на дашборде (глобально или с фильтром `source_id`). Симулятор потока: `tools/feed_live.py` / `make feed`.

## 3. Recompute (пересчёт кластеров + имена сценариев)

### `POST /api/v1/recompute` → `202`

Backend проксирует в ML. `{ "job_id": "rc_01", "status": "running" }`.

### `GET /api/v1/recompute/status` → `200`

`{ "job_id", "status": "running|completed|failed", "clusters_created", "scenarios_named",
"finished_at" }`. Фронт поллит и потом обновляет дашборд.

## 4. Дашборд (главный экран)

### `GET /api/v1/dashboard` → `200`

Фильтры: `?source_id=&from=&to=`.

```json
{
  "taxonomy_version": "v1",
  "freshness": { "last_recompute_at": "...", "logs_since_last_recompute": 0, "recompute_pending": false },
  "totals": { "records_processed": 348, "scenarios_count": 18, "outliers_percentage": 4.5 },
  "tasks_distribution": [
    { "task_type": "data_analysis", "label": "Анализ данных", "count": 120, "percentage": 34.5 },
    { "task_type": "unknown", "label": "Не уверены", "count": 10, "percentage": 2.9 },
    { "task_type": "other", "label": "Другое", "count": 8, "percentage": 2.3 }
  ],
  "top_scenarios": [
    {
      "scenario_id": "data_analysis:cluster_01",
      "task_type": "data_analysis",
      "name": "Экспорт отчётов CRM",
      "summary": "Пользователи выгружают данные из CRM и формируют таблицы для анализа.",
      "user_goal": "Сократить ручную подготовку отчётности.",
      "representative_examples": ["Выгрузи список выигранных тендеров", "Собери отчёт по продажам"],
      "pain_points": ["Ручная выгрузка данных", "Повторяющиеся операции"],
      "automation_potential": "high",
      "count": 45, "trend": "up", "growth_rate_percent": 15.4
    }
  ],
  "dynamics": [ { "date": "2026-07-23", "count": 800 }, { "date": "2026-07-24", "count": 1000 } ],
  "outliers_summary": { "total_outliers_count": 16, "outlier_percentage": 4.5 },
  "failure_analysis": {
    "status": "available",
    "total_requests_with_failure_signals": 30,
    "failure_signal_percentage": 8.6,
    "top_failure_signals": [ { "signal": "tool_error", "count": 22 },
                             { "signal": "hallucination_loop", "count": 8 } ]
  }
}
```

> `failure_analysis.status == "not_available"` → фронт показывает «данных о качестве нет».
> Выбросы называем «Нетипичные или редкие запросы», НЕ «Ошибки агента».
> `freshness.recompute_pending == true` → показать плашку «есть новые логи, пересчитать сценарии».

### `GET /api/v1/scenarios` → `200`

Полный список сценариев (не только top). Фильтры те же. При фильтре workspace сценарии с нулевым
числом запросов не возвращаются. `{ "items": [ <scenario> ], "total": n }`.

### `GET /api/v1/scenarios/{scenario_id}` → `200`

Детали + `representative_request_ids`, `records_count`, `statistical_reliability`. Принимает те же
`source_id`/`from`/`to`, чтобы count и примеры не выходили за выбранный workspace.

### `GET /api/v1/logs` → `200`

Обработанные логи. Пагинация + фильтры `?source_id=&task_type=&scenario_id=&only_failures=true`.

```json
{ "items": [
  { "request_id": "req_101", "query_text": "Выгрузи отчёт из CRM",
    "task_type": "data_analysis", "classification_confidence": 0.91,
    "scenario_id": "data_analysis:cluster_01", "scenario_name": "Экспорт отчётов CRM",
    "is_outlier": false, "has_failure_signals": false, "timestamp": "..." }
], "total": 348 }
```

## 5. ROI / FTE (киллер-фича, считает backend)

### `GET /api/v1/roi` → `200`

Фильтры те же (`source_id`, `from`, `to`) + переопределение ставок:
`?fte_hourly_rate_rub=&token_cost_per_1k_rub=` («что если»).

```json
{
  "assumptions": {
    "fte_hourly_rate_rub": 1200.0, "token_cost_per_1k_rub": 0.015,
    "session_coefficients": { "short": 0.3, "medium": 1.0, "long": 2.0 }
  },
  "summary": {
    "total_logs": 348, "success_rate_percent": 82.5,
    "total_fte_hours_saved": 210.5, "total_manual_cost_rub": 252600.0,
    "total_agent_cost_rub": 16800.0, "net_savings_rub": 235800.0, "roi_multiplier": 15.0,
    "total_tokens_consumed": 1120000, "wasted_tokens_on_errors": 96000,
    "token_value_index": 0.188, "process_automation_rate": 61.0,
    "top_tools_used": { "CRM": 90, "Mail": 70, "Jira": 40 }
  },
  "by_category": [
    { "task_type": "data_analysis", "label": "Анализ данных", "count": 120,
      "success_rate_percent": 88.0, "fte_hours_saved": 95.0, "net_savings_rub": 110000.0 }
  ],
  "by_scenario": [
    { "scenario_id": "data_analysis:cluster_01", "name": "Экспорт отчётов CRM",
      "count": 45, "fte_hours_saved": 40.0, "net_savings_rub": 47000.0, "automation_potential": "high" }
  ]
}
```

### `GET /api/v1/export?format=xlsx|csv` → `200` (файл)

Выгрузка ROI в Excel/CSV (кейсовая тема «экспорт в Excel»). Те же фильтры + переопределение ставок,
что и `GET /roi`. `format` по умолчанию `xlsx`. Ответ — `Content-Disposition: attachment` с именем
`prompt_radar_roi.xlsx|csv`.

- `xlsx`: три листа — `Summary`, `ByCategory`, `ByScenario` (собирается нативно, без доп. зависимостей).
- `csv`: один файл с секциями `# Summary` / `# ByCategory` / `# ByScenario`, UTF-8 с BOM (кириллица
  в Excel). Неверный `format` → `422`.

## 5b. Аналитика пользователей и моделей (Users & Models Analytics)

### `GET /api/v1/analytics/users` → `200`

Фильтры: `?source_id=&from=&to=`.

Возвращает агрегированный вектор пользователей, метрики вовлечения (DAU/MAU, Adoption Score), распределение по архетипам (User Personas) и список пользователей с Frustration Index для детекции барьеров.

```json
{
  "summary": {
    "total_users": 15,
    "active_users_l7": 12,
    "avg_adoption_score": 78.4,
    "avg_frustration_index": 12.1,
    "personas_distribution": [
      { "persona": "code_craftsman", "label": "Разработчик (Code)", "count": 6, "percentage": 40.0 },
      { "persona": "analyst", "label": "Аналитик данных", "count": 4, "percentage": 26.7 },
      { "persona": "super_user", "label": "AI Super-User", "count": 3, "percentage": 20.0 },
      { "persona": "casual", "label": "Эпизодический", "count": 2, "percentage": 13.3 }
    ]
  },
  "by_department": [
    { "department": "IT / Dev", "users_count": 8, "total_queries": 220, "avg_saved_hours": 18.5, "frustration_index": 8.2 }
  ],
  "users": [
    {
      "user_id": "user_01",
      "user_name": "Алексей Смирнов",
      "department": "IT / Dev",
      "persona": "code_craftsman",
      "persona_label": "Разработчик (Code)",
      "total_queries": 45,
      "active_days": 12,
      "saved_hours": 14.2,
      "frustration_index": 6.5,
      "top_category": "code_generation",
      "needs_guidance": false,
      "recommendation": "Пользователь эффективно использует сценарии отладки и генерации кода."
    }
  ]
}
```

### `GET /api/v1/analytics/models` → `200`

Фильтры: `?source_id=&from=&to=`.

Сравнение производительности и стоимости моделей/агентов (Model-to-Task Fit, задержка, токены, уровень ошибок, потенциал оптимизации маршрутизации).

```json
{
  "summary": {
    "total_models_detected": 4,
    "avg_latency_ms": 1420,
    "total_tokens": 1120000,
    "potential_cost_reduction_percent": 24.5,
    "routing_recommendation": "Перенаправление 25% тривиальных запросов General QA с GPT-4o на GPT-4o-mini позволит сэкономить 24.5% токенового бюджета."
  },
  "models": [
    {
      "model_id": "gpt-4o",
      "model_name": "GPT-4o (OpenAI)",
      "total_queries": 180,
      "share_percentage": 51.7,
      "avg_latency_ms": 1650,
      "total_tokens": 750000,
      "failure_rate_percent": 3.2,
      "user_feedback_score": 0.85,
      "top_task_type": "code_generation",
      "cost_tier": "premium"
    }
  ],
  "task_fit": [
    {
      "task_type": "code_generation",
      "label": "Генерация кода",
      "recommended_model": "GPT-4o",
      "queries_count": 120,
      "avg_latency_ms": 1500
    }
  ]
}
```

## 6. Health

- `GET /api/health` → `{ "status": "ok|degraded", "dependencies": { "database": "ok", "ml": "ok" } }`
- `GET /api/ready` → `200|503`
- `GET /api/ping` → `{ "status": "ok" }`

