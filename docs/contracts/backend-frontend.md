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

Детали + прогресс индексации: `records_classified`, `classification_percentage` (из локального
зеркала assignments) и объект `progress` `{ classified, total, percent, done }` (спрашивает ML,
fallback на зеркало). Фронт поллит.

### `GET /api/v1/ingest/status` → `200`

Агрегированный прогресс индексации по всем источникам + состояние recompute. Нужен для
глобального индикатора: пользователь видит стадию анализа на любом экране, не заходя в Sources.

```json
{
  "indexing": true,
  "total_valid": 2083, "total_classified": 667, "percent": 32.0,
  "recompute_status": "idle", "recompute_pending": false,
  "logs_since_last_recompute": 0, "scenarios_named": 0,
  "sources": [
    { "source_id": "...", "name": "prompt_radar_dataset.json", "origin": "upload",
      "status": "classified", "records_total": 2084, "records_valid": 2083,
      "records_rejected": 1, "classified": 667, "percent": 32.0, "done": false }
  ]
}
```

> Побочный эффект: запрос до-синхронизирует assignments для источников, которые ML успел
> классифицировать дальше нашего зеркала — поэтому `/logs` наполняется по мере индексации.
> `indexing == false && recompute_pending == false` → индикатор скрыт.

### `POST /api/v1/sources/{source_id}/resume` → `202`

Дослать в ML сохранённые записи источника. Нужен, когда индексация встала на половине: стриминг
живёт в `BackgroundTasks` и **не переживает рестарт backend**, а записи уже лежат в Postgres.
ML дедуплицирует по `request_id`, поэтому повторно обрабатывается только «хвост». Источник в
статусе `failed` переводится обратно в `ingesting`. Ответ — обновлённый `SourceOut`.

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

> **`task_type`/`classification_confidence` могут быть `null`** — запись загружена, но ML её ещё не
> классифицировал (индексация идёт). Это честное «пока нет данных»: **запрещено** подставлять
> placeholder-уверенность вместо реального выхода модели — дашборд защищает методику, и показанная
> цифра обязана быть настоящей. Фронт в этом случае рисует «awaiting classification».

## 5. ROI / FTE (киллер-фича, считает backend)

### `GET /api/v1/roi` → `200`

Фильтры те же (`source_id`, `from`, `to`) + переопределение ставок:
`?fte_hourly_rate_rub=&token_cost_per_1k_rub=` («что если»).

**Ставки выводятся, а не задаются константой (QNA §1).** `fte_hourly_rate_rub` = месячная
ставка FTE (400 000 ₽ — ориентир эксперта заказчика) ÷ рабочие часы в месяце.
`token_cost_per_1k_rub` = (капзатраты на GPU ÷ срок амортизации + электричество за год) ÷
токенов в год × 1000. Обе модели вывода возвращаются в `assumptions`, а `is_overridden`
показывает, что значение задано вручную через query-параметр — чтобы UI никогда не выдавал
ручную цифру за выведенную.

**`verdict` — явный ответ на вопрос «окупается ли ИИ»** (B > A), а не число, которое читатель
должен сравнить в уме. `B` = высвобожденные FTE-часы × ставка, `A` = токены × себестоимость.

```json
{
  "assumptions": {
    "fte_hourly_rate_rub": 2380.95, "token_cost_per_1k_rub": 1.03,
    "session_coefficients": { "short": 0.3, "medium": 1.0, "long": 2.0 },
    "session_short_max_tokens": 4000, "session_long_min_tokens": 30000,
    "manual_minutes_by_category": { "code_help": 30.0, "data_analysis": 45.0, "other": 15.0 },
    "manual_minutes_estimated_percent": 100.0,
    "fte_rate_model": {
      "monthly_rate_rub": 400000.0, "work_hours_per_month": 168.0,
      "derived_hourly_rate_rub": 2380.95, "is_overridden": false
    },
    "token_cost_model": {
      "infra_capex_rub": 100000000.0, "amortization_years": 5.0,
      "electricity_rub_per_year": 600000.0, "tokens_per_year": 20000000000.0,
      "derived_cost_per_1k_rub": 1.03, "is_overridden": false
    }
  },
  "verdict": {
    "benefit_rub": 2112817.46, "cost_rub": 245189.68, "net_rub": 1867627.78,
    "ratio": 8.62, "pays_off": true,
    "headline": "ИИ окупается: выгода 2.1 млн ₽ > затрат 245 тыс ₽ (×8.62, чистыми 1.9 млн ₽)"
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

Возвращает агрегаты по пользователям, распределение по архетипам (User Personas) и список
пользователей с Frustration Index для детекции барьеров.

**Предпосылки (не измерения):**

- `active_users_l7` — пользователи с активностью в последние `active_window_days` (7) дней,
  окно отсчитывается от **максимального timestamp в отфильтрованных данных**, а не от `now`:
  демо-датасеты историчны, и окно от wall-clock дало бы 0.
- `saved_hours` считается **той же методикой, что и `/roi`** (D6): только записи со
  `status=success`, `manual_time` × коэффициент сессии (0.3/1.0/2.0 по токенам). Сумма
  `saved_hours` по всем пользователям сходится с `summary.total_fte_hours_saved` из `/roi`.
- `frustration_index` = 0.6 × доля записей с failure-сигналами + 0.4 × доля выбросов.
  Веса — продуктовое суждение, не измерение.
- `persona` — эвристика по составу категорий и объёму **относительно медианы когорты**
  (абсолютные пороги вырождали распределение в один архетип на больших датасетах).

```json
{
  "summary": {
    "total_users": 15,
    "active_users_l7": 12,
    "active_window_days": 7,
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

Разрез по моделям/агентам: доля запросов, токены, уровень ошибок.

**Только реально переданные данные.** Модель определяется по записи `model:<id>` в `tools_used`,
которую нормализатор пишет из сырого поля `model` / `model_name` / `agent_id`. Записи без этих
метаданных **исключаются из разреза**, а не приписываются какой-либо модели по догадке.

Если ни одна запись не несёт метаданных модели — `summary.status = "not_available"`, `models: []`.
Соглашение то же, что у `statistics.failure_analysis.status`.

**Чего здесь намеренно нет:** задержки (`latency`), оценки пользователя (`feedback`) и ценового
класса модели. Этих полей нет в `log.schema.json`, вывести их не из чего, поэтому они не
возвращаются вообще — вместо правдоподобных, но выдуманных значений.

```json
{
  "summary": {
    "status": "available",
    "total_models_detected": 2,
    "total_queries_with_model": 348,
    "total_tokens": 1120000
  },
  "models": [
    {
      "model_id": "gpt-4o",
      "model_name": "gpt-4o",
      "total_queries": 180,
      "share_percentage": 51.7,
      "total_tokens": 750000,
      "failure_rate_percent": 3.2,
      "top_task_type": "Помощь с кодом"
    }
  ]
}
```

## 6. Health

- `GET /api/health` → `{ "status": "ok|degraded", "dependencies": { "database": "ok", "ml": "ok" } }`
- `GET /api/ready` → `200|503`
- `GET /api/ping` → `{ "status": "ok" }`
