# Prompt Radar — шпаргалка для защиты (backend)

Составлено 2026-07-25 по коду в рабочем дереве (`main` + незакоммиченные правки ROI/normalizer).
Всё, что здесь написано, проверено по коду, а не по старым планам. Проверочный статус:
`65 passed` (pytest) и `ruff check src tests — All checks passed`.

> Осторожно с `docs/CODEBASE_MAP.md`: раздел про frontend там **устарел** (описывает структуру
> `features/entities/pages` и dataset-switcher, которых в коде нет). Реальный фронт — см. §11.

---

## 1. Продукт в 60 секунд

Проблема заказчика (КРОК): в компании сотрудники массово пользуются ИИ-агентами, но у CTO нет
ответа на «что вообще происходит с ИИ в компании и что делать дальше». Логи есть — смысла нет.

Prompt Radar превращает поток логов диалогов в управленческую аналитику:

1. **Классификация** запроса по таксономии (7 продуктовых классов).
2. **Кластеризация** в сценарии (use-cases) — «люди делают вот эти 20 вещей».
3. **Саммари** сценария LLM: имя, цель пользователя, боли, потенциал автоматизации.
4. **Живой дашборд** + **ROI/FTE** — оцифровка пользы ИИ в часах и рублях.

Киллер-фича — ROI/FTE, потому что это прямая боль заказчика (`docs/product_owners_pain.md`) и
именно её методику организаторы описали в `docs/QNA_ORGANIZERS.md` §1. Мы её воспроизводим
**один в один и усиливаем** — см. §7. По QNA методология важнее красоты дашборда.

---

## 2. Архитектура: три сервиса, одна команда запуска

```text
dataset / OWUI-фильтр / live feeder
              |
              v
   backend :8080  --HTTP-->  ml-service :8000  -->  Qdrant :6333  (векторы)
       |                     classify / embed             |
       |                     cluster / summarize      meta.db (sqlite)
       v                     aggregate
  Postgres :5433
  users, sources, dataset_records (сырые ROI-поля), log_assignments (зеркало)
       ^
       |
  frontend :3000 (nginx SPA) — ходит ТОЛЬКО в backend REST, cookie-auth, same-origin /api
```

Запуск: `cp .env.example .env && cp ml_service/.env.example ml_service/.env && make up`.
Демо-логин `test@gmail.com` / `test123`. Swagger: `http://localhost:8080/api/docs`.

### Почему так (главные ADR — `docs/decisions/DECISIONS.md`)

| # | Решение | Зачем именно так |
|---|---|---|
| **D1** | **Стриминговый CQRS** backend↔ML: write / recompute / read разведены | Дашборд «живой навигатор по потоку», а не «отчёт по файлу». Read-путь не вызывает модели → мгновенный. Тяжёлый пересчёт — по явному триггеру → главный де-риск демо |
| **D2** | Аналитическим стором владеет ML (Qdrant + мета-БД), бизнес-состоянием — backend | Чистая граница: ML-инженер владеет своим контуром целиком, backend не лезет в векторы. Backend не импортирует код ML и наоборот — только контракты |
| **D3** | Один глобальный дашборд + необязательные фильтры `source_id/from/to` | Нативно для стриминга, контракт проще, чем набор изолированных run'ов |
| **D4** | Плоская монорепа | Минимум трения, `ml_service/` уже существовал |
| **D5** | Полная auth из template (JWT access+refresh, cookie, argon2), но **без ролей** | Рабочая auth выглядит зрело, RBAC в кейсе избыточен (один тип пользователя) |
| **D6** | **ROI считает backend**, не ML | ROI — бизнес-логика поверх назначений ML. Контракт ML не раздувается ROI-полями. Ставки конфигурируемы и отдаются как `assumptions` |
| **D7** | Live-webhook `POST /api/v1/logs` с `X-Ingest-Token` (не cookie) | Это M2M-вход от системы-источника, логин там неуместен |

**Одной фразой, если спросят «почему не один сервис»:** потому что ML-контур (Qdrant, CatBoost,
UMAP/HDBSCAN, LLM-провайдеры) имеет свой цикл жизни и свои тяжёлые зависимости; разделив их по
HTTP-контракту, мы можем перезапускать/деградировать ML без падения дашборда, а два человека
могут работать параллельно, не блокируя друг друга.

---

## 3. Backend: стек и слои

**Стек:** Python 3.13, FastAPI, Pydantic v2, SQLAlchemy 2 async + asyncpg, Alembic, Poetry,
PyJWT, passlib/argon2, httpx. Тесты — pytest (65), линт — ruff.

**Модульный монолит**, поток строго в одну сторону:

```
api/v1/**        тонкие роутеры: валидация входа → вызов сервиса → response_model
   ↓
service/**       вся бизнес-логика
   ↓
domain/**        Pydantic-схемы и enum (контракт наружу)
   ↓
database/relational_db/**   SQLAlchemy 2 async + Alembic
```

Правило, которое стоит произнести вслух: **каждый endpoint объявляет `response_model`** —
контракт с фронтом не «как получится», а типизирован и виден в OpenAPI.

### Карта файлов, которые нужно знать наизусть

| Файл | Роль |
|---|---|
| `backend/src/main.py` | app factory, lifespan (wait_for_db → seed demo user → preload workspaces), CORS, `/api/ping|health|ready` |
| `backend/src/api/v1/__init__.py` | сборка роутеров и **где навешивается auth** |
| `backend/src/api/v1/deps.py` | DI: сессия, сервисы, `get_current_user`, `require_ingest_token`, общие фильтры |
| `backend/src/service/ingestion/normalizer.py` | сырой датасет → `log.schema.json` (§6) |
| `backend/src/service/ingestion/service.py` | персист, стриминг в ML, live-ingest, прогресс, resume |
| `backend/src/service/ml/client.py` | **единственная** HTTP-граница backend → ML |
| `backend/src/service/roi/calculator.py` | ROI/FTE — чистая функция, ядро защиты (§7) |
| `backend/src/service/dashboard/service.py` | read-модель, зеркалирование assignments, `/logs` |
| `backend/src/service/analytics/service.py` | персоны пользователей, frustration index, модели (§8) |
| `backend/src/core/error_handling.py` | единый формат ошибок, stack trace наружу не уходит |
| `backend/src/migrations/versions/0001_initial_schema.py` | вся схема БД одной ревизией |

---

## 4. Полный список эндпоинтов backend

Все под `/api/v1`, кроме health. Контракт — `docs/contracts/backend-frontend.md` +
`openapi-backend-frontend.yaml`.

### Auth (cookie JWT)
| Метод | Путь | Что делает |
|---|---|---|
| POST | `/auth/login` | `{email,password}` → 200 + httpOnly cookies `access_token`/`refresh_token` |
| POST | `/auth/refresh` | по refresh-cookie выдаёт новую пару |
| POST | `/auth/logout` | 204, чистит cookies |
| GET | `/users/me` | текущий пользователь |

### Ingestion
| Метод | Путь | Что делает |
|---|---|---|
| POST | `/ingest` | multipart `file` (JSON/JSONL/CSV) **или** `{"use_demo":true}` → **202** + `SourceOut`; стриминг в ML уходит в `BackgroundTasks` |
| GET | `/ingest/status` | глобальный прогресс индексации + состояние recompute (баннер на всех экранах) |
| GET | `/sources` | список источников (`Paginated[SourceOut]`) |
| GET | `/sources/{id}` | источник + `normalization_report` + `progress` |
| POST | `/sources/{id}/resume` | 202 — **пере-стримит сохранённые записи** в ML, чтобы добить залипший прогон |
| POST | `/logs` | **live-webhook, M2M**, guard `X-Ingest-Token`, не cookie → 202 |

### Recompute
| Метод | Путь | Что делает |
|---|---|---|
| POST | `/recompute` | проксирует в ML, 202 + `job_id`; фоновая задача поллит до конца и синхронизирует assignments |
| GET | `/recompute/status` | статус последнего job'а |

### Чтение / дашборд
| Метод | Путь | Что делает |
|---|---|---|
| GET | `/dashboard` | read-модель из ML + TTL-кэш + русские ярлыки |
| GET | `/scenarios`, `/scenarios/{id}` | сценарии из ML |
| GET | `/logs` | таблица логов **из Postgres** (join `dataset_records` × `log_assignments`); фильтры `task_type`, `scenario_id`, `only_failures`, `limit/offset` |
| GET | `/analytics/users` | персоны, frustration index, разрезы по департаментам |
| GET | `/analytics/models` | какие модели реально используются |
| GET | `/roi` | ROI/FTE + what-if через `fte_hourly_rate_rub`, `token_cost_per_1k_rub` |
| GET | `/export?format=xlsx\|csv` | тот же ROI файлом, `Content-Disposition: attachment` |

Общие фильтры на `/dashboard`, `/scenarios`, `/logs`, `/analytics/*`, `/roi`, `/export`:
`source_id`, `from`, `to` (алиас `from_` в Python из-за ключевого слова).

### Health
`GET /api/ping` → `{status:ok}` · `GET /api/health` → агрегат зависимостей (`database`, `ml`) ·
`GET /api/ready` → 200/503.

**Важная деталь readiness, её любят спрашивать:** БД обязательна, а ML в `degraded`/
`not_configured` **не блокирует** readiness (`main.py:150`). То есть если у ML отвалился
провайдер эмбеддингов, приложение продолжает отдавать последний снапшот, а не падает целиком.

---

## 5. Данные: что живёт в Postgres

5 таблиц, одна Alembic-ревизия `0001_initial_schema`, миграции применяются в `entry.sh` при
старте контейнера (`alembic upgrade head`).

| Таблица | Смысл |
|---|---|
| `users` | id, email (unique), password_hash (argon2), created_at |
| `ingestion_sources` | заливка: name, `origin` ∈ {upload, demo, preloaded, live}, счётчики total/valid/rejected, `normalization_report` (JSONB), `status` ∈ {ingesting, classified, recomputed, failed} |
| `dataset_records` | **сырые поля по каждой записи**: query_text, gold_category, style, user_id/user_name/department, tokens, manual_time_minutes, tools_used (JSONB), status, timestamp |
| `log_assignments` | **зеркало назначений ML**: task_type, classification_confidence, scenario_id/name, is_outlier, has_failure_signals |
| `roi_cache` | задел под кэш ROI (в текущем пути не используется — ROI считается на лету) |

### Идемпотентность — то, что стоит подчеркнуть

- Уникальный индекс `(source_id, request_id)` и в `dataset_records`, и в `log_assignments`.
- `request_id` канонизируется как **UUIDv5 от `prompt-radar:{source_id}:{внешний request_id}`**
  (`normalizer.py:_canonical_request_id`). Следствие: один и тот же внешний `req_17` в двух
  разных заливках — **две разные записи**, датасеты не дедуплицируют друг друга. А повторная
  отправка той же записи того же источника — гарантированный дубль, который ML отбросит.
- Зеркалирование assignments — `INSERT ... ON CONFLICT DO UPDATE` (`pg_insert` + `on_conflict_do_update`),
  то есть синхронизацию можно запускать сколько угодно раз.

### Зачем зеркалить assignments у себя, если ими владеет ML

Два ответа, оба честные:
1. **ROI-джойн** должен быть SQL-джойном по `(source_id, request_id)`, а не N HTTP-запросами.
2. `/logs` — это таблица с фильтрами/пагинацией по сырому тексту, который живёт у нас;
   тянуть её через ML означало бы дублировать в ML хранение query_text и пагинацию.

Зеркало обновляется в трёх местах: после стриминга источника, после `recompute`, и инкрементально
на каждом poll'е `/ingest/status` (side effect в `processing_status`).

---

## 6. Нормализация — ответственность backend

`service/ingestion/normalizer.py`. Вход: JSON / JSONL / CSV (терпит обёртки
`{"records": [...]}`, `logs`, `data`, `items`). Выход: `log_records` (для ML по
`docs/contracts/log.schema.json`) + `dataset_rows` (для Postgres) + `report`.

Маппинг, который надо знать:

| Сырое поле | Куда | Правило |
|---|---|---|
| `user_query` / `query_text` | `query_text` | trim; пустой → **reject** (`empty_query_text`) |
| — | `request_id` | UUIDv5(source_id + внешний id или `req_{index}`) |
| `timestamp` | `timestamp` | ISO parse (`Z` → `+00:00`, naive → UTC); при отсутствии/ошибке — **синтез** по шкале `NORMALIZE_TIMESTAMP_SPAN_DAYS` (14 дней) |
| `status` / `response_status` | `response_status` + `error_code` | `success`→`success/null`; `error_tool`→`error/tool_error`; `hallucination_loop`→`error/hallucination_loop` |
| `total_tokens` → `simulated_context_tokens` → `metadata.usage.total_tokens` | `tokens` | первый непустой |
| `estimated_manual_time_minutes` / `manual_time_minutes` / `manual_time` | `manual_time_minutes` | первый непустой |
| `model` / `model_name` / `agent_id` | `tools_used += "model:<id>"` | так модель попадает в `/analytics/models` |
| `style` | `style` | нормализация алиасов: `typoy`/`typò`→`typo`, `voice_jargon`→`voice`, `corporate slang`→`jargon` |
| `category` | `metadata.gold_category` | эталон для eval классификатора, **в расчётах не используется** как истина |
| `user_id`/`user_name`/`department` | как есть | питают MAU и разрезы по департаментам |

**Честная формулировка про синтез времени:** «если в источнике нет времени, мы не выдумываем
факт — мы явно помечаем это в `normalization_report.synthetic_timestamps: true`, и это видно
в API источника». Не говорите «у нас есть таймстемпы» — говорите «реальные читаются, отсутствие
компенсируется явно помеченным допущением».

`normalization_report` = `records_total`, `records_valid`, `records_rejected`,
`synthesized_request_id`, `synthesized_timestamp`, `synthetic_timestamps`,
`rejected_reasons: {причина: count}`. Отдаётся в `GET /sources/{id}`.

---

## 7. ROI / FTE — ядро защиты, знать формулы наизусть

`service/roi/calculator.py` — чистая функция `compute_roi(records, config)`, без БД и без HTTP.
Поэтому она полностью покрыта unit-тестами и её легко защищать.

### Методика заказчика (QNA §1) и как мы её воспроизводим

Заказчик считает так: классификация запроса по теме → минуты ручной работы по теме →
**× коэффициент за длину сессии** (короткая 0.3, средняя 1, очень длинная 2) → часы → дни → FTE.

Мы делаем ровно это, только классификацию даёт модель, а не человек:

```
для каждой записи:
    manual = измеренный estimated_manual_time_minutes
             else DEFAULT_CATEGORY_MANUAL_MINUTES[task_type]      # табличное допущение
             else 15.0

    coeff  = 0.3   если tokens ≤ 4000        (ROI_SESSION_SHORT_MAX_TOKENS)
             2.0   если tokens ≥ 30000       (ROI_SESSION_LONG_MIN_TOKENS)
             1.0   иначе

    saved  = manual × coeff        ← ТОЛЬКО если status ∈ {success, ok, completed}
                                     провал экономии не даёт, но токены сжигает
```

Табличные минуты ручной работы (`DEFAULT_CATEGORY_MANUAL_MINUTES`, ровно 7 классов таксономии):

| Класс | мин | Класс | мин |
|---|---|---|---|
| `text_generation` | 15 | `information_search` | 15 |
| `code_help` | 30 | `task_management` | 25 |
| `data_analysis` | 45 | `other` | 15 |
| `education` | 20 | fallback | 15 |

Итоговые метрики:

```
total_fte_hours_saved   = Σ saved / 60
total_manual_cost_rub   = fte_hours × 2380.95 ₽/ч     ← 400 000 ₽/мес ÷ 168 ч (QNA §1.1)
total_agent_cost_rub    = total_tokens/1000 × 1.03 ₽  ← вывод из инфраструктуры (ниже)
net_savings_rub         = manual_cost − agent_cost
roi_multiplier          = manual_cost / agent_cost
wasted_tokens_on_errors = Σ tokens по НЕ-success  →  wasted_cost_rub
cost_per_successful_action_rub = agent_cost / success_count
token_value_index       = fte_hours / (tokens/1000)     «сколько часов даёт 1k токенов»
process_automation_rate = доля успешных записей с tools_used
mau_count               = число уникальных user_id
```

### Вердикт B > A — главный ответ эксперту (QNA §1)

`/roi` возвращает отдельный блок `verdict`, а не оставляет сравнение читателю:

```
B (benefit_rub) = высвобожденные FTE-часы × ставка   → 2 112 817 ₽
A (cost_rub)    = токены × себестоимость             →   245 190 ₽
net_rub = B − A                                      → 1 867 628 ₽
ratio   = B / A                                      → ×8.62      pays_off = true
headline: «ИИ окупается: выгода 2.1 млн ₽ > затрат 245 тыс ₽ (×8.62, чистыми 1.9 млн ₽)»
```

### Откуда взялись ставки — ни одна не «магическое число»

```
ставка FTE      = 400 000 ₽/мес ÷ 168 ч = 2380.95 ₽/ч
                  (400к — ориентир эксперта заказчика, QNA §1.1)

себестоимость   = (100 000 000 ₽ капзатрат ÷ 5 лет + 600 000 ₽/год электричество)
токена            ÷ 20 млрд токенов/год × 1000 = 1.03 ₽ / 1k токенов
                  (амортизация GPU-сервера — прямая отсылка к вопросу эксперта)
```

Обе модели вывода отдаются в `assumptions.fte_rate_model` / `assumptions.token_cost_model`
вместе с флагом `is_overridden`. Если оценщик спорит с цифрой — он спорит с **месячной
зарплатой** и **стоимостью сервера**, а не с непрозрачным коэффициентом. Все параметры
меняются через env (`ROI_FTE_MONTHLY_RATE_RUB`, `ROI_INFRA_CAPEX_RUB`, …) или query-параметром.

> Раньше здесь стояли 1200 ₽/ч и 0.1 ₽/1k, и ROI получался ×44.73 — цифра, которая
> разваливается от первого вопроса. С выведенными ставками ROI ×8.62: меньше, но защитимо.

Плюс разрезы: `by_category` (по `task_type`), `by_scenario` (по `scenario_id` от ML),
`department_costs`, `top_spenders` (топ-3 по токенам), `style_breakdown` /
`mobile_voice_adoption_rate` (voice + typo — аргумент за Voice-to-Text интерфейс).

### Почему это выдерживает удар «вы просто выдумали цифры»

Ответ в одном слове: **`assumptions`**. Каждый ответ `/roi` возвращает блок предпосылок:
ставка, цена токенов, session-коэффициенты и их пороги, **вся таблица табличных минут** и
`manual_minutes_estimated_percent` — какая доля записей посчитана по допущению, а не по
измерению. Мы не выдаём оценку за факт: мы отдаём оценку **вместе с её предпосылками**, и
ставки можно поменять прямо в запросе (`?fte_hourly_rate_rub=...`) — what-if на живом дашборде.

Формулировка на стену: «Мы не утверждаем, что сэкономлено ровно N рублей. Мы утверждаем, что
при явно названных предпосылках это N, и вот ручка, которой вы меняете предпосылки.»

### Два неудобных вопроса — отвечаем сами, не ждём удара

**«Вы показываете классификацию на данных, на которых учились?»** Да, и мы это говорим первыми.
Весь демо-датасет (4860 записей) — это `DEFAULT_DATA` из `catboost/train_catboost.py`. Поэтому
качество модели мы заявляем **не по демо**, а по honest holdout: `holdout_accuracy = 0.8097`
на стратифицированном 20% сплите (`app/models/*.meta.json`, `n_samples = 4858`). Формулировка:
«демо показывает работу пайплайна на сквозном потоке; качество классификатора — 81% на
отложенной выборке, цифра лежит в артефакте модели».

**«114 тысяч токенов на один запрос — серьёзно?»** Нет, и это ограничение данных, а не расчёта.
Генератор положил в `total_tokens` объём контекста сессии, а не одного запроса (медиана ~89k,
максимум 349k). Важно, в какую сторону это врёт: раздутые токены увеличивают **A** (затраты),
то есть делают наш ROI **консервативным** — реальная выгода выше заявленной ×8.62, а не ниже.
Мы предпочли занизить свою же метрику, чем чинить данные под красивую цифру.

### Нюанс, к которому надо быть готовым

Записи без назначения ML (ещё не классифицированы) попадают в бакет `task_type = "unknown"`
и берут fallback 15 минут. Если в `by_category` видно большое «Другое/Не уверены» — это
незавершённая индексация, а не ошибка расчёта. Проверяется по `/ingest/status`.

---

## 8. Analytics: пользователи и модели (backend-only, без ML)

`service/analytics/service.py` — считается на нашем джойне, ML не участвует.

**Персоны** (`_classify_persona`), пороги относительны медиане когорты, чтобы распределение не
схлопывалось в один бакет на больших датасетах:
`code_craftsman` (≥35% code_help) · `analyst` (≥35% data_analysis+information_search) ·
`super_user` (≥5 категорий и объём ≥ медианы) · `casual` (< max(5, 0.5×медианы)) · `generalist`.

**Frustration index** = `0.6 × доля_записей_с_failure_signals + 0.4 × доля_выбросов`.
Веса — продуктовое суждение, и это прямо написано в комментарии кода. Если спросят «откуда
0.6/0.4» — правильный ответ: «это заявленная эвристика, а не измерение; она нужна, чтобы
отранжировать, кому дать шаблоны промптов, и порог `needs_guidance > 15` калибруется».

**Active users L7** считается от **максимального timestamp в отфильтрованных данных**, а не от
wall-clock now — иначе на историческом демо-датасете было бы 0 активных. Это осознанное решение,
задокументированное в коде.

**Модели** берутся только из `tools_used: "model:<id>"`. Если ни одна запись не несёт модель —
`summary.status = "not_available"`, и мы **не угадываем**. Та же конвенция, что у
`failure_analysis.status` в ML. Latency и user feedback мы не показываем, потому что их нет в
`log.schema.json` — не показываем то, чего не измеряли.

---

## 9. Auth и безопасность

- **JWT access + refresh в httpOnly cookies** (`core/http/cookies.py`), пароли — **argon2id**
  (memory_cost 64 MiB, time_cost 3, parallelism 2), хеширование/проверка вынесены в
  `asyncio.to_thread`, чтобы не блокировать event loop.
- TTL: access 900 с, refresh 604800 с. В токене `sub`, `jti`, `typ`, `iat`, `exp`; тип токена
  **проверяется** (`typ != "access"` → 401) — refresh-токеном нельзя ходить в API.
- `JWT_SECRET` валидируется на старте: **минимум 32 символа**, иначе приложение не поднимется.
- Все пользовательские `/api/v1/*` защищены cookie-зависимостью на уровне сборки роутеров
  (`api/v1/__init__.py`) — нельзя случайно забыть guard на новом endpoint'е. `/auth/*` и
  live-webhook подключены отдельно.
- Live-webhook — `X-Ingest-Token` (M2M). Backend↔ML — `X-Service-Token`. Разные секреты,
  разные назначения.
- CORS: `allow_credentials=True` требует явных origins (не `*`), список из `CORS_ORIGINS`.
  Middleware добавлен последним, чтобы оборачивать всё снаружи и ставить заголовки даже на ошибках.
- **Единый формат ошибок** (`core/error_handling.py`): `error_code`, `message`, `details`,
  `title`, `status`, `instance`, `timestamp`, `request_id`. Stack trace наружу не уходит никогда
  — текст исключения подставляется только при `DEBUG`.
- Секреты только через env. `OPENROUTER_API_KEY` живёт в `ml_service/.env`, в Git его нет.
- RBAC — сознательно нет (D5): в кейсе один тип пользователя.

---

## 10. Связь с ML — самое частое место вопросов

### Контракт (`docs/contracts/backend-ml.md`)

Backend — **клиент**, ML — **сервер**. Единственная точка выхода — `service/ml/client.py`
(`MlClient`). Все вызовы несут `X-Service-Token`, таймаут `ML_HTTP_TIMEOUT_SEC`.

| Поток | Вызов | Семантика |
|---|---|---|
| write | `PUT /api/v1/logs` | батчи ≤ 200 записей, 202, идемпотентно по `request_id`; ML обрабатывает в фоне |
| recompute | `POST /api/v1/recompute` → `GET /api/v1/recompute/{job_id}` | UMAP + HDBSCAN + LLM-нейминг; поллинг до `completed`/`failed` |
| read | `GET /api/v1/statistics` | готовая read-модель, без вызова моделей |
| read | `GET /api/v1/scenarios` | сценарии с саммари |
| read | `GET /api/v1/assignments` | `request_id → task_type, scenario_id, ...`, пагинация, для нашего зеркала |
| health | `GET /health/ready` | отражаем в своём `/api/ready` |

**Подводный камень, который мы уже обошли:** у ML `LogBatch` **нет** верхнеуровневого `source_id`
— он читается из каждой записи. Поэтому `MlClient.stream_logs` инжектит `source_id` в **каждый**
лог батча (`client.py:57`). Без этого сломалась бы атрибуция источника и фильтры дашборда.

### Что backend НЕ делает (граница ответственности)

Не считает эмбеддинги, не кластеризует, не вызывает LLM, не трогает Qdrant, не импортирует код
`ml_service`. Всё это — контур ML. Backend оркестрирует и владеет бизнес-состоянием.

### Что делает ML (нужно знать на уровне «могу объяснить»)

CatBoost по эмбеддингам запроса (порог уверенности 0.30 — 0.45 отправлял половину живого трафика
в `unknown`) → эмбеддинги (Ollama offline / OpenRouter online / mock) → онлайн-назначение в
кластер по cosine ≥ 0.85 внутри `task_type` → тяжёлый recompute: UMAP (`random_state=42`,
n_neighbors 15, n_components 10, cosine) + HDBSCAN (min_cluster_size 10, min_samples 4),
стабилизация `scenario_id` по центроидам (порог 0.75), не более 5 сценариев на `task_type`,
затем LLM-саммари (имя ≤ 4 слов, 10 репрезентативных примеров).

### Деградация — что мы отвечаем на «а если ML упал?»

Реализовано в коде, не на словах:

- Любая HTTP-ошибка ML → `MLUnavailableError` → **502 с `error_code: ML_UNAVAILABLE`**, а не
  необработанный 500 (`client.py:_request`).
- Ответ `/statistics` **валидируется семантически** перед употреблением
  (`service/ml/statistics_validation.py`): нет `schema_version`/`totals.records_total`/
  корректного `tasks_distribution` → `502 STATISTICS_SCHEMA_INVALID`. Мы не доверяем произвольному
  ответу ML.
- Стриминг упал → источник помечается `failed`, в UI есть кнопка **resume**, которая
  пере-стримит сохранённые записи (ML отбросит уже обработанные как duplicates → доедет только хвост).
- Ожидание классификации **истекло по таймауту, но стриминг прошёл** → это НЕ ошибка: ML всё ещё
  классифицирует большой батч. Статус остаётся `classified`, остаток догоняется инкрементально
  на poll'ах `/ingest/status`. Это осознанно (`stream_source_logs`, комментарий в коде).
- `/api/ready`: ML `degraded` не блокирует готовность приложения.
- Подсчёт классифицированных: сначала спрашиваем ML, при недоступности — падаем на локальное
  зеркало (`_mirrored_count`), то есть прогресс не обнуляется при недоступном ML.

### Кэш read-модели

`service/dashboard/cache.py` — in-process TTL-кэш (`STATISTICS_CACHE_TTL_SEC`, по умолчанию 15 с),
ключ включает фильтры (`source_id|from|to`). Инвалидируется явно: после recompute и после
поступления новых логов. Не Redis — и это осознанный MVP-выбор, см. §13.

---

## 11. Связь с frontend

**Реальная структура (проверено по коду):** плоский SPA, React + TypeScript + Vite + Tailwind +
Recharts + lucide, файлы `frontend/src/api.ts`, `App.tsx`, `components/*`, `types.ts`.
Роутера нет — 6 табов в состоянии: Overview, Ingestion & Sources, Scenarios, Logs & Outliers,
Users & Models, ROI Analytics. Плюс `ProcessingBanner` — глобальный прогресс индексации,
видимый на всех экранах.

**Как связаны:**

- Фронт ходит **только** в backend REST, `same-origin /api` через nginx (в dev — Vite proxy на
  `:8080`). ML для фронта не существует — это и есть ценность стабильного read-контракта:
  форма API не зависит от того, как ML наполняет данные.
- Все запросы с `credentials: 'include'` → httpOnly cookies. Токен в JS не попадает.
- `ensureAuth()` при старте: пробует `GET /users/me`, при неудаче логинится demo-креденшелами.
  То есть на демо логин-формы не видно — приложение сразу показывает данные.
- 204 обрабатывается отдельно, не-ok → `Error(текст)`; тело нашей ошибки унифицировано (§9),
  так что фронт может показать `error_code`/`message`.
- Обёртка списков везде одна: `{items, total}` (`Paginated[T]`) — единая форма для sources,
  scenarios, logs.
- `ProcessingBanner` поллит `GET /ingest/status`. Этот endpoint не только читает — он **на каждом
  вызове до-зеркалирует assignments** тех источников, которые ML успел классифицировать дальше
  нашего зеркала. Так `/logs` заполняется живьём, без ручного recompute.
- Загрузка файла — `FormData` в `POST /ingest`; экспорт ROI — `GET /export`,
  `Content-Disposition` проброшен через CORS `expose_headers`.

**Честно про текущее состояние фронта** (если спросят или заметят): в `api.ts` сейчас **не
передаются** фильтры `source_id/from/to` — backend их поддерживает во всех read-эндпоинтах, а UI
пока показывает глобальную картину. Это разрыв на стороне фронта, не на стороне контракта;
если спросят про сравнение источников — говорите «API уже параметризован, переключатель
рабочих пространств — следующий шаг фронта», и не обещайте, что это работает в UI сейчас.

---

## 12. Живые потоки данных end-to-end

### A. Загрузка датасета
`POST /ingest` → parse (JSON/JSONL/CSV) → `normalize()` → создать `ingestion_sources`
(`status=ingesting`) + `dataset_records` (одна транзакция) → **202 сразу** →
`BackgroundTasks: stream_source_logs` → `MlClient.stream_logs` батчами по 200 →
дождаться появления assignments → `sync_assignments` (upsert в зеркало) → `status=classified` →
инвалидация кэша дашборда.

### B. Live ingestion
`POST /api/v1/logs` + `X-Ingest-Token` → rolling-источник с `origin=live` (создаётся по имени) →
normalize → persist → **синхронный** `stream_logs` в ML → инвалидация кэша → ответ со счётчиками
`accepted/duplicates/rejected`. Источники: `tools/feed_live.py` (`make feed`) и OWUI-фильтр
`ml_service/filter.py`.

### C. Recompute
`POST /recompute` → ML отдаёт `job_id`, 202 → `finalize_recompute` в фоне поллит
`GET /recompute/{job_id}` раз в секунду до `completed` (дедлайн `ML_RECOMPUTE_TIMEOUT_SEC`) →
`sync_assignments(None)` по всем источникам → все не-`failed` источники → `recomputed` →
инвалидация кэша.

### D. Preloaded workspaces (что видит жюри на чистом старте)
При старте, если `PRELOAD_DATASETS_ENABLED=true`, backend идемпотентно создаёт **три
непересекающихся рабочих пространства** из demo-фикстуры, поделённые по категориям:
Knowledge & Communications (text_generation, education, information_search) ·
Engineering & Data (code_help, data_analysis) · Operations & Planning (task_management, other).
`source_id` детерминированный (UUIDv5 от ключа) → повторный старт не плодит дубли, а
реконсилится: сравнивает ожидаемое число записей с числом assignments в ML и додаёт недостающее.
Тяжёлый recompute при этом **opt-in** (`PRELOAD_DATASETS_RECOMPUTE`), потому что он тратит
кредиты провайдера. В `docker-compose.yml` по умолчанию `false`, в `.env.example` — `true`.

Смысл фразы для защиты: «на чистом клоне `make up` показывает наполненный дашборд, а не пустое
приложение — и это не хардкод в БД, а тот же самый ingestion-путь».

---

## 13. Известные ограничения — говорить о них первым

Лучше назвать самому, чем услышать в вопросе. Каждое — с обоснованием, почему это ОК для MVP.

| Ограничение | Почему так и что было бы в prod |
|---|---|
| `BackgroundTasks` + `_LAST_JOB_ID` в модуле — **один процесс** | Несколько воркеров/реплик без брокера и общего job-store сломают ожидания. В prod — Celery/ARQ + Redis. Для демо это лишняя сложность (и прямо запрещено правилами MVP) |
| Кэш read-модели — память процесса, не Redis | TTL 15 с, ключ по фильтрам, явная инвалидация. `REDIS_URL` уже в настройках как задел |
| Фоновая задача не выживает рестарт backend | Ровно поэтому есть `POST /sources/{id}/resume` — записи персистятся до стриминга, ML дедуплицирует, доезжает только хвост. Это не дырка, это спроектированное восстановление |
| ROI считается на лету, `roi_cache` не используется | На демо-объёмах (единицы тысяч записей) один SQL-джойн быстрее, чем инвалидация кэша по 4 измерениям. Таблица оставлена как задел |
| `roi_multiplier` при `agent_cost = 0` даёт 0.0 | Защита от делёния на ноль; 0 читается как «нет данных о токенах», а не «ROI нулевой» |
| Онлайн-центроиды ML не восстанавливаются из мета-стора после рестарта | TODO на стороне ML; путь стабилизации — heavy recompute |
| Python lock-файлы: `poetry.lock` есть, но `Dockerfile` делает `poetry lock` заново | Сборка не полностью детерминирована. Один из первых пунктов после хакатона |
| Compose — single-host demo/staging | Для prod нужны TLS, secrets manager, бэкапы, брокер задач, IAM/RBAC, мониторинг, политика миграции эмбеддингов |

---

## 14. Ожидаемые вопросы и короткие ответы

**«Почему ROI — это не фантазия?»**
Потому что мы отдаём не только число, но и все предпосылки: ставку, цену токенов,
session-коэффициенты, таблицу минут и **процент записей, посчитанных по допущению**. Ставки
меняются в запросе — жюри может пересчитать на своих цифрах прямо на демо.

**«Почему backend, а не ML считает ROI?»**
ROI — бизнес-логика, зависящая от корпоративных ставок, а не от векторов. Держать её в ML
означало бы раздуть ML-контракт бизнес-полями и связать две команды. ML отдаёт
`request_id → task_type, scenario_id`, остальное — наш джойн (D6).

**«Что будет, если ML недоступен?»** — см. §10 «Деградация». Ключевое: 502 с кодом вместо 500,
последний валидный снапшот на дашборде, resume для незавершённых заливок, ML не блокирует readiness.

**«Как избегаете дублей при повторной заливке?»**
Уникальный индекс `(source_id, request_id)` у нас + UUIDv5-канонизация + идемпотентный приём по
`request_id` в ML + upsert зеркала. Три уровня.

**«Почему не микросервисы / почему не монолит?»**
Ровно два деплой-юнита по границе владения данными (D1/D2). Меньше — и ML-зависимости тянут
дашборд за собой; больше — оверинжиниринг на хакатоне.

**«Масштабирование?»**
Честный ответ: read-путь масштабируется горизонтально (stateless + кэш), write-путь сейчас
однопроцессный из-за `BackgroundTasks`; первый шаг — вынести стриминг и recompute в брокер
задач с общим job-store. Endpoint'ы менять не придётся — контракт уже асинхронный (202 + poll).

**«Безопасность?»** — argon2id, httpOnly cookies, проверка типа токена, JWT_SECRET ≥ 32,
CORS с явными origins, разделённые секреты для M2M-входа и ML, единый формат ошибок без
stack trace, секреты только в env.

**«Чем ваш дашборд отличается от подсчёта категорий?»**
Три слоя: категория (что за задача) → сценарий (какую работу человек реально делает) → ROI
(сколько это стоит и сколько экономит). Первый слой — статистика, третий — управленческое решение.

---

## 15. Демо-runbook и две вещи, которые стоит починить до защиты

```bash
cp .env.example .env
cp ml_service/.env.example ml_service/.env    # сюда OPENROUTER_API_KEY
make up                                        # ждёт healthcheck'и
open http://localhost:3000                     # авто-логин demo
make feed                                      # live-поток 30 запросов → баннер оживает
# ROI → меняем ставку → экспорт XLSX
```

Полезно иметь под рукой: `http://localhost:8080/api/docs` (Swagger — показывает, что контракт
типизирован) и `GET /api/health` (показывает состояние зависимостей).

### Найдено при подготовке — оба факта надо знать до сцены

1. **OWUI-фильтр не пройдёт auth live-webhook'а.** `ml_service/filter.py:56-57` отправляет
   `Authorization: Bearer <token>` и `X-Service-Token`, а backend требует **`X-Ingest-Token`**
   (`backend/src/api/v1/deps.py:89`). При дефолтном `INGEST_TOKEN=dev-ingest-token` логи из
   Open WebUI получат 401. Починка — одна строка в filter (`headers["X-Ingest-Token"] = ...`),
   либо на демо поднять backend с пустым `INGEST_TOKEN` (пустое значение отключает проверку).
   `make feed` работает — `tools/feed_live.py` шлёт правильный заголовок.
2. **`docs/CODEBASE_MAP.md` устарел про frontend** (описывает `features/entities/pages`,
   dataset-switcher, форму логина и `promptRadarApi.ts` — ничего этого в коде нет). Если жюри
   читает docs, лучше поправить раздел или не ссылаться на него.

---

## Приложение: таксономия v1 и ярлыки

`backend/src/domain/taxonomy.py`, `TAXONOMY_VERSION = "v1"`. 7 классов + служебные:

`text_generation` Генерация текста · `code_help` Помощь с кодом · `data_analysis` Анализ данных ·
`education` Объяснение / обучение · `information_search` Поиск информации ·
`task_management` Планирование / задачи · `other` Другое · `unknown` **Не уверены**.

`label(None)` → «Не уверены», неизвестный ключ → «Другое». Правило версионирования из
quality gates: меняется `/statistics` → меняется `schema_version`; меняется таксономия →
`taxonomy_version`.
