# 📡 Prompt Radar — аналитика запросов к корпоративным ИИ-агентам

**Кейс КРОК.** Превращаем поток логов диалогов сотрудников с ИИ-агентами в понятную аналитику
для CTO: классификация запросов → сценарии (use-cases) → саммари → живой дашборд → **ROI в
FTE-часах и рублях**.

> Отвечаем руководителю на вопрос «что происходит с ИИ в компании и что делать дальше».

| | |
|---|---|
| **Запуск** | `make up` — весь стек одной командой (5 контейнеров) |
| **Приложение** | <http://localhost:3000> · demo-логин `test@gmail.com` / `test123` |
| **API + Swagger** | <http://localhost:8080/api/docs> |
| **Стек** | FastAPI · PostgreSQL · Qdrant · CatBoost · UMAP+HDBSCAN · React 19 + Vite |
| **Проверено** | backend `65 passed` + `ruff` clean · frontend typecheck + prod build clean |

**Материалы для защиты:** [`docs/backend/DEFENSE_BRIEF.md`](docs/backend/DEFENSE_BRIEF.md) —
разбор backend, методики ROI и всех связей с ML/frontend с формулами и ответами на вопросы.

---

## 1. Проблема и решение

**Боль заказчика** (`docs/product_owners_pain.md`, `docs/QNA_ORGANIZERS.md`): сотрудники массово
пользуются ИИ-агентами, логи копятся, но руководитель не может ответить ни на «зачем люди ходят
к ИИ», ни на «сколько это нам сэкономило». Ручная разметка не масштабируется.

**Что делает Prompt Radar:**

| Слой | Ответ на вопрос | Как |
|---|---|---|
| **Классификация** | «Какого рода задачи?» | CatBoost по эмбеддингам, таксономия v1 (7 классов) |
| **Сценарии** | «Какую работу люди реально делают?» | Онлайн-кластеризация (cosine) + heavy recompute UMAP + HDBSCAN |
| **Саммари** | «Что внутри сценария и где боль?» | LLM: имя, цель пользователя, pain points, потенциал автоматизации |
| **Дашборд** | «Что происходит прямо сейчас?» | Живая read-модель + динамика + выбросы + failure-анализ |
| **ROI / FTE** 🎯 | «Сколько это стоит и сколько экономит?» | Методика заказчика: минуты ручной работы × коэффициент сессии → часы → рубли |
| **Пользователи и модели** | «Кому помочь и что мы вообще используем?» | Персоны, frustration index, разрезы по департаментам, разбивка по моделям |

**Киллер-фича — ROI/FTE**, потому что это прямая боль заказчика и потому что мы воспроизводим
**его собственную методику** расчёта (см. §5), только классификацию делает модель, а не человек.

---

## 2. Запуск за 3 минуты

Нужен только Docker (+ `make`). Стек поднимается с нуля и **сам наполняет себя данными**.

```bash
git clone <repo> && cd chupapis-prompt-radar

cp .env.example .env                          # инфраструктура; работает и без правок
cp ml_service/.env.example ml_service/.env    # сюда OPENROUTER_API_KEY для реальных эмбеддингов

make up          # = docker compose up -d --build --wait  (ждёт healthcheck'и, ~2-4 мин)
```

Открыть <http://localhost:3000> — вход выполняется автоматически demo-учёткой.

| Сервис | URL | Назначение |
|---|---|---|
| Frontend (nginx SPA) | <http://localhost:3000> | дашборд |
| Backend API | <http://localhost:8080/api/docs> | Swagger, живой контракт |
| Backend health | <http://localhost:8080/api/health> | состояние `database` / `ml` |
| ML service | <http://localhost:8000/health/ready> | готовность пайплайна и провайдеров |
| Qdrant | <http://localhost:6333/dashboard> | векторный стор |
| PostgreSQL | `localhost:5433` | бизнес-состояние |

**Что происходит при первом старте:** backend применяет миграции Alembic, создаёт demo-пользователя
и идемпотентно заводит **три предзагруженных рабочих пространства** из встроенного датасета
(4860 записей), деля его по категориям без пересечений:

| Workspace | Категории | Валидных записей |
|---|---|---|
| Knowledge & Communications | text_generation, education, information_search | 2078 (2 отклонены: пустой запрос) |
| Engineering & Data | code_help, data_analysis | 1386 |
| Operations & Planning | task_management, other | 1394 |

Пространства проходят **тот же самый ingestion-путь**, что пользовательская загрузка, — в БД нет
захардкоженной аналитики. Создаются они **последовательно**: следующее начинается после того, как
ML классифицировал предыдущее, поэтому первые минуты после `make up` в баннере виден один источник
и растущий прогресс. Разбивка идёт по эталонной `category` из датасета, а дашборд показывает
**предсказанный** классификатором `task_type` — расхождение между ними ожидаемо и наблюдаемо.

Полезные команды:

```bash
make ps          # статус сервисов
make logs        # логи всего стека
make feed        # влить 30 live-запросов → баннер индексации оживает на всех экранах
make demo        # mutating smoke: login → ingest → recompute → dashboard → ROI → export
make down        # остановить (volumes сохраняются)
make down-clean  # остановить и удалить volumes (полностью чистый старт)
```

> **Про тяжёлый пересчёт.** `PRELOAD_DATASETS_RECOMPUTE` по умолчанию `false` в Compose: UMAP +
> HDBSCAN + LLM-нейминг тратят кредиты провайдера, поэтому первый recompute — осознанно ручной
> (кнопка в UI или `POST /api/v1/recompute`). До него дашборд показывает классификацию и
> онлайн-кластеры; после — стабилизированные сценарии с именами и саммари.

---

## 3. Сценарий демонстрации

Порядок, который показывает продукт, а не интерфейс:

1. **Overview** — сколько запросов обработано, распределение по классам, динамика, выбросы,
   failure-анализ. Тезис: «поток логов стал картиной».
2. **Ingestion & Sources** — три рабочих пространства + `normalization_report` по каждому
   (сколько записей принято, отклонено и почему). Тезис: «данные не из воздуха, весь путь виден».
   Здесь же — загрузка своего JSON/JSONL/CSV.
3. `make feed` в терминале → **баннер прогресса** индексации оживает на любом экране.
   Тезис: «это живой навигатор по потоку, а не отчёт по файлу».
4. **Scenarios** — сценарии с именами, целями пользователей, болями и потенциалом автоматизации.
   Тезис: «вот конкретные use-cases, которые можно автоматизировать».
5. **Logs & Outliers** — сырой запрос, класс, уверенность модели, сценарий, флаги провала.
   Тезис: «любую цифру можно раскрыть до конкретного запроса».
6. **Users & Models** — персоны, frustration index, кому нужна помощь, какие модели используются.
   Тезис: «понятно, кого учить и на чём мы тратим токены».
7. **ROI Analytics** — FTE-часы, рубли, ROI-множитель, потери на ошибках → **меняем ставку**
   → цифры пересчитываются → **экспорт XLSX**. Тезис: «мы отдаём не число, а число вместе с
   предпосылками, и вот ручка, которой вы их меняете».

---

## 4. Архитектура

```text
   dataset (JSON/JSONL/CSV)   Open WebUI filter   tools/feed_live.py
              │                      │                    │
              └──────────────┬───────┴────────────────────┘
                             ▼
                    ┌──────────────────┐        HTTP (X-Service-Token)
                    │  backend  :8080  │ ─────────────────────────────┐
                    │  FastAPI         │                             ▼
                    │  нормализация    │                  ┌────────────────────┐
                    │  оркестрация     │  PUT /logs       │ ml-service  :8000  │
                    │  ROI / auth      │  POST /recompute │ CatBoost + эмбеддинги
                    │  read-API        │  GET /statistics │ online + batch кластеры
                    └────────┬─────────┘  GET /assignments│ LLM-саммари, агрегаты
                             │                            └─────┬────────┬─────┘
                             ▼                                  ▼        ▼
                  ┌────────────────────┐              Qdrant :6333   meta.db
                  │ PostgreSQL :5433   │              (векторы)      (кластеры,
                  │ users, sources,    │                              сценарии,
                  │ dataset_records,   │                              назначения)
                  │ log_assignments    │
                  └────────────────────┘
                             ▲
                             │ cookie-auth, same-origin /api
                    ┌────────┴─────────┐
                    │ frontend  :3000  │  React 19 + Vite + Tailwind + Recharts
                    └──────────────────┘     ходит ТОЛЬКО в backend REST
```

### Кто чем владеет

| Сервис | Владеет | Никогда не делает |
|---|---|---|
| **backend** | пользователи, ingestion-источники, сырые ROI-поля, зеркало назначений, **расчёт ROI** | не считает эмбеддинги, не кластеризует, не вызывает LLM, не трогает Qdrant |
| **ml-service** | векторы (Qdrant), кластеры, сценарии, назначения, агрегаты | не знает про пользователей, ставки и ROI |
| **frontend** | представление | не обращается к ML напрямую, не хранит токен в JS |

Backend не импортирует код `ml_service` и наоборот — только контракты из `docs/contracts/`.

### Модель интеграции — стриминговый CQRS

Три независимых потока, поэтому чтение всегда мгновенное, а тяжёлое — управляемое:

| Поток | Вызов | Свойства |
|---|---|---|
| **write** | `PUT /api/v1/logs` | батчи ≤ 200, `202` сразу, обработка в фоне, идемпотентно по `request_id` |
| **recompute** | `POST /api/v1/recompute` + поллинг job'а | UMAP + HDBSCAN + LLM-нейминг, триггерится вручную |
| **read** | `GET /api/v1/statistics` · `/scenarios` · `/assignments` | из стора, **без вызова моделей**, кэш с TTL |

Ключевые решения зафиксированы как ADR (D1–D7): интеграция, владение стором, модель дашборда,
структура репозитория, auth без ролей, ROI на стороне backend, live-webhook. Разбор с
обоснованиями — в [`docs/backend/DEFENSE_BRIEF.md`](docs/backend/DEFENSE_BRIEF.md) §2.

---

## 5. ROI / FTE — методика

Мы воспроизводим методику заказчика из `docs/QNA_ORGANIZERS.md` §1: классификация запроса по теме
→ минуты ручной работы по теме → **× коэффициент за длину сессии** → часы → рубли.

```
для каждой записи:
    manual = измеренное estimated_manual_time_minutes
             иначе табличная оценка по классу задачи
             иначе 15 мин

    coeff  = 0.3   если tokens ≤ 4 000          (короткая сессия)
             2.0   если tokens ≥ 30 000         (очень длинная)
             1.0   иначе                        (средняя)

    saved  = manual × coeff        ← только для успешных запросов
                                     провал экономии не даёт, но токены сжигает

total_fte_hours_saved = Σ saved / 60
total_manual_cost_rub = fte_hours × ставка (по умолчанию 1200 ₽/ч)
total_agent_cost_rub  = tokens/1000 × цена (по умолчанию 0.1 ₽ за 1k)
net_savings_rub       = manual_cost − agent_cost
roi_multiplier        = manual_cost / agent_cost
```

Табличные минуты ручной работы по классам: генерация текста 15 · помощь с кодом 30 ·
анализ данных 45 · обучение 20 · поиск информации 15 · планирование 25 · другое 15.

Дополнительно считаются: `wasted_tokens_on_errors` и их стоимость, `cost_per_successful_action_rub`,
`token_value_index` (FTE-часы на 1k токенов), `process_automation_rate`, MAU, топ-3 «потребителя»
токенов, стоимость по департаментам, разбивка по стилям ввода (voice / typo / jargon / formal /
copypaste) с долей мобильного и голосового ввода.

### Почему это не «выдуманные цифры»

Каждый ответ `GET /api/v1/roi` возвращает блок **`assumptions`**: ставка, цена токенов,
session-коэффициенты и их пороги, **вся таблица табличных минут** и
`manual_minutes_estimated_percent` — какая доля записей посчитана по допущению, а не по измерению.
Мы не выдаём оценку за факт — мы отдаём оценку вместе с её предпосылками.

Ставки переопределяются прямо в запросе (what-if):

```bash
curl -b cookies.txt "http://localhost:8080/api/v1/roi?fte_hourly_rate_rub=2500&token_cost_per_1k_rub=0.3"
```

Экспорт для финансистов: `GET /api/v1/export?format=xlsx|csv` — саммари + разрезы по категориям
и сценариям. XLSX собирается на stdlib без тяжёлых зависимостей; CSV — с BOM, чтобы Excel
корректно открывал кириллицу.

---

## 6. Публичный API

Все пути под `/api/v1`, кроме health. Полный контракт с примерами —
[`docs/contracts/backend-frontend.md`](docs/contracts/backend-frontend.md) и
[`openapi-backend-frontend.yaml`](docs/contracts/openapi-backend-frontend.yaml).

| Группа | Endpoints |
|---|---|
| **Auth** | `POST /auth/login` · `POST /auth/refresh` · `POST /auth/logout` · `GET /users/me` |
| **Ingestion** | `POST /ingest` (multipart или `{"use_demo":true}`) · `GET /ingest/status` · `GET /sources` · `GET /sources/{id}` · `POST /sources/{id}/resume` |
| **Live (M2M)** | `POST /logs` — заголовок `X-Ingest-Token`, не cookie |
| **Recompute** | `POST /recompute` · `GET /recompute/status` |
| **Аналитика** | `GET /dashboard` · `GET /scenarios` · `GET /scenarios/{id}` · `GET /logs` · `GET /analytics/users` · `GET /analytics/models` |
| **ROI** | `GET /roi` · `GET /export?format=xlsx\|csv` |
| **Health** | `GET /api/ping` · `GET /api/health` · `GET /api/ready` |

Общие фильтры read-эндпоинтов: `source_id`, `from`, `to`. У `/logs` дополнительно `task_type`,
`scenario_id`, `only_failures`, `limit`, `offset`. Списки всегда в конверте `{items, total}`.
Каждый endpoint объявляет Pydantic `response_model` — контракт типизирован и виден в OpenAPI.

**Формат ошибок единый:** `{error_code, message, details, title, status, instance, timestamp,
request_id}`. Stack trace наружу не отдаётся никогда.

**Устойчивость к сбоям ML** (реализовано, а не декларировано): ошибка ML → `502 ML_UNAVAILABLE`
вместо необработанного 500 · ответ `/statistics` семантически валидируется перед употреблением
(`502 STATISTICS_SCHEMA_INVALID`) · незавершённая заливка добивается через `POST /sources/{id}/resume`
(ML дедуплицирует, доезжает только хвост) · ML в состоянии `degraded` **не блокирует**
`/api/ready` — дашборд продолжает отдавать последний валидный снапшот.

---

## 7. Данные

### Встроенный демо-датасет

`backend/src/data/prompt_radar_dataset.json` — **4860 записей**: реальные ISO-таймстемпы за 7 дней,
10 сотрудников, 8 департаментов (IT, Analytics, Finance, HR, Management, Marketing, Sales,
Security), 4 модели (gpt-4o, claude-3-5-sonnet, llama-3-8b-ollama, deepseek-r1), токены, стили
ввода, статусы (`success` / `error_tool` / `hallucination_loop`) и `category` как эталон для
оценки классификатора.

Генератор и формат своих датасетов: [`docs/DEMO_AND_DATASET_GUIDE.md`](docs/DEMO_AND_DATASET_GUIDE.md),
схема сырой загрузки: [`docs/contracts/upload-dataset.schema.json`](docs/contracts/upload-dataset.schema.json).

### Своя загрузка

Экран **Ingestion & Sources** или напрямую:

```bash
curl -b cookies.txt -F "file=@my_logs.json" http://localhost:8080/api/v1/ingest
```

Backend нормализует запись в [`log.schema.json`](docs/contracts/log.schema.json): вытягивает текст
запроса, статус → `response_status` + `error_code`, токены, стиль (со сведением алиасов), модель
(в `tools_used` как `model:<id>`), пользователя/департамент. Отсутствующий `timestamp`
**синтезируется по шкале и явно помечается** `synthetic_timestamps: true` в `normalization_report`
— мы не выдаём допущение за факт. Пустой текст запроса отклоняется с причиной в отчёте.

**Идемпотентность на трёх уровнях:** `request_id` канонизируется как UUIDv5 от
`source_id + внешний id` · уникальные индексы `(source_id, request_id)` в Postgres · идемпотентный
приём по `request_id` на стороне ML. Повторная заливка того же файла не создаёт дублей, а разные
заливки не «съедают» записи друг друга.

### Live-поток: симулятор

```bash
make feed
# или: python tools/feed_live.py --url http://localhost:8080 --token dev-ingest-token --count 30 --interval 0.5
```

### Live-поток: Open WebUI

Перехват реальных диалогов фильтром [`ml_service/filter.py`](ml_service/filter.py)
(OWUI Pipelines Filter).

```bash
docker compose -f docker-compose-owui.yml up -d      # Open WebUI на :3001
```

1. Open WebUI → **Admin Panel** → **Functions / Filters** → **Add Filter**.
2. Вставить содержимое `ml_service/filter.py`, активировать для нужных моделей.
3. В **Valves** указать:
   - `BACKEND_URL`: `http://host.docker.internal:8080/api/v1/logs`
   - `BACKEND_SERVICE_TOKEN`: значение `INGEST_TOKEN` из корневого `.env`

> ⚠️ **Важно про авторизацию.** Live-webhook backend проверяет заголовок **`X-Ingest-Token`**.
> Текущая версия фильтра отправляет токен как `Authorization: Bearer` и `X-Service-Token`,
> поэтому для работы связки нужно либо добавить в `_send_log_to_backend` строку
> `headers["X-Ingest-Token"] = self.valves.BACKEND_SERVICE_TOKEN`, либо запустить backend с пустым
> `INGEST_TOKEN=` (пустое значение отключает проверку — только для локального демо).
> Симулятор `tools/feed_live.py` отправляет правильный заголовок и работает без правок.

Диагностика:

```bash
docker logs --tail 100 open-webui                                  # что делает фильтр
docker exec -it open-webui cat /app/backend/data/input.jsonl        # локальная копия логов
curl http://localhost:8080/api/v1/ingest/status -b cookies.txt      # дошло ли до backend
```

---

## 8. Структура репозитория

```text
backend/           FastAPI: API + оркестрация + Postgres + ROI + auth
  src/api/v1/         тонкие роутеры (валидация → сервис → response_model)
  src/service/        бизнес-логика: ingestion, ml-клиент, dashboard, roi, analytics, export
  src/domain/         Pydantic-схемы и таксономия
  src/database/       SQLAlchemy 2 async + Alembic
  src/data/           встроенный демо-датасет
  tests/              65 unit + ASGI API тестов
ml_service/        ML-пайплайн: классификация, эмбеддинги, кластеризация, саммари, агрегаты
  app/pipeline/       classification · embeddings · clustering_online · clustering_batch · summarization · aggregation
  app/store/          Qdrant · meta_store
  filter.py           коннектор Open WebUI
  eval/               оценка качества классификации
frontend/          React 19 + Vite + Tailwind + Recharts (SPA, 6 экранов)
docs/
  backend/DEFENSE_BRIEF.md   ← шпаргалка для защиты (backend + связи)
  contracts/                 контракты backend↔ML и backend↔frontend, JSON-схемы
  CODEBASE_MAP.md            карта реализации
  taxonomy/, plans/, decisions/
tools/             feed_live.py (live-симулятор), demo.py (e2e smoke)
docker-compose.yml · Makefile · .env.example
```

---

## 9. Конфигурация

Инфраструктура — корневой `.env` (см. `.env.example`); стек работает и на дефолтах Compose.
Провайдеры и секреты ML — только в `ml_service/.env`, в Git их нет.

| Переменная | По умолчанию | Смысл |
|---|---|---|
| `JWT_SECRET` | dev-значение | подпись токенов, **минимум 32 символа** (валидируется на старте) |
| `ML_SERVICE_TOKEN` | `dev-ml-token` | общий секрет backend ↔ ML (`X-Service-Token`) |
| `INGEST_TOKEN` | `dev-ingest-token` | авторизация live-webhook (`X-Ingest-Token`); пустое значение отключает проверку |
| `ROI_FTE_HOURLY_RATE_RUB` | `1200` | ставка часа сотрудника |
| `ROI_TOKEN_COST_PER_1K_RUB` | `0.1` | стоимость 1k токенов |
| `ROI_SESSION_COEFF_SHORT/MEDIUM/LONG` | `0.3 / 1.0 / 2.0` | коэффициенты длины сессии |
| `ROI_SESSION_SHORT_MAX_TOKENS` / `LONG_MIN_TOKENS` | `4000` / `30000` | пороги длины сессии |
| `PRELOAD_DATASETS_ENABLED` | `true` | создавать три рабочих пространства при старте |
| `PRELOAD_DATASETS_RECOMPUTE` | `false` (Compose) | запускать тяжёлый recompute автоматически |
| `STATISTICS_CACHE_TTL_SEC` | `15` | TTL кэша read-модели дашборда |
| `NORMALIZE_TIMESTAMP_SPAN_DAYS` | `14` | шкала синтеза времени при его отсутствии в источнике |
| `CORS_ORIGINS` | localhost:3000,5173,8080 | явные origins (cookie-auth несовместим с `*`) |

Со стороны ML (`ml_service/config.yaml` + `ml_service/.env`): `mode` эмбеддингов и LLM
(`offline` Ollama / `online` OpenRouter / `mock`), порог классификатора `0.30`, порог
онлайн-кластеризации `0.85`, параметры UMAP (`random_state=42`) и HDBSCAN
(`min_cluster_size=10`), лимит сценариев на класс.

> `mock`-режим эмбеддингов существует для тестов и **не показывает качество аналитики** —
> для осмысленного демо нужен реальный провайдер (OpenRouter или локальная Ollama:
> `docker compose --profile ollama up -d`).

---

## 10. Безопасность

- **JWT access + refresh в httpOnly cookies**, пароли — **argon2id** (64 MiB / time_cost 3),
  хеширование вынесено в поток, чтобы не блокировать event loop.
- Тип токена проверяется: refresh-токеном нельзя ходить в API. `JWT_SECRET` < 32 символов →
  приложение не стартует.
- Guard навешивается **на уровне сборки роутеров**, а не на каждой функции — нельзя случайно
  забыть авторизацию на новом endpoint'е.
- Разные секреты для разных границ: `X-Service-Token` (backend ↔ ML) и `X-Ingest-Token`
  (внешний M2M-вход). Роли/RBAC сознательно не вводились — в кейсе один тип пользователя.
- CORS с явным списком origins, секреты только через env, stack trace не покидает сервис.

---

## 11. Проверка качества

```bash
make test            # backend: pytest  → 65 passed
make lint            # backend: ruff check src tests → All checks passed
npm --prefix frontend run lint     # tsc --noEmit → без ошибок
npm --prefix frontend run build    # production-сборка Vite → успешно
cd ml_service && uv sync && uv run pytest -q    # тесты ML-пайплайна
make demo            # e2e smoke по живому стеку: login → ingest → recompute → dashboard → ROI → export
```

Покрыто тестами на стороне backend: ROI-калькулятор (включая коэффициенты сессий и предпосылки),
нормализация всех входных форматов, стриминг и деградация ML-клиента, валидация `/statistics`,
кэш read-модели, экспорт XLSX/CSV, preloaded-workspaces, контракт роутов через ASGI.

Нагрузочная проверка write-пути: `cd ml_service && uv run python load_tester.py --batch-size 20
--concurrency 10 --repeat 5`.

---

## 12. Осознанные ограничения MVP

Названы честно — каждое с обоснованием и понятным следующим шагом.

| Ограничение | Почему так и что дальше |
|---|---|
| Фоновая обработка — `BackgroundTasks` в одном процессе | Брокер (Celery/ARQ + Redis) для MVP запрещён объёмом и добавил бы отказов больше, чем убрал. Контракт уже асинхронный (`202` + поллинг), поэтому вынос в брокер не меняет API |
| Фоновая задача не выживает рестарт backend | Ровно поэтому есть `POST /sources/{id}/resume`: записи персистятся до стриминга, ML дедуплицирует, доезжает только незавершённый хвост |
| Кэш read-модели — память процесса, не Redis | TTL 15 с, ключ включает фильтры, инвалидация по recompute и новым логам. `REDIS_URL` заведён как задел |
| ROI считается на лету (таблица `roi_cache` не задействована) | На демо-объёмах один SQL-джойн быстрее, чем инвалидация кэша по четырём измерениям |
| Онлайн-центроиды ML не восстанавливаются из мета-стора после рестарта | Путь стабилизации сценариев — heavy recompute; TODO на стороне ML |
| Фронтенд пока не передаёт фильтры `source_id/from/to` | Backend параметризован во всех read-эндпоинтах; переключатель рабочих пространств — следующий шаг UI |
| Python lock-файлы: сборка backend делает `poetry lock` заново | Полная детерминированность сборки — первый пункт после хакатона |
| Compose — single-host demo/staging | Для production нужны TLS, secrets manager, бэкапы, брокер задач с общим job-store, IAM/RBAC, мониторинг и политика миграции эмбеддингов |

`ml_service/roi_engine.py` и `ml_service/dataset.py` — **прототипы** ранней итерации (генератор
датасета и первая версия ROI). Продуктовый ROI живёт в `backend/src/service/roi/` (решение D6);
прототипы оставлены как референс происхождения методики.

---

## 13. Документация

| Документ | О чём |
|---|---|
| [`docs/backend/DEFENSE_BRIEF.md`](docs/backend/DEFENSE_BRIEF.md) | **шпаргалка для защиты**: backend, формулы ROI, связи с ML и frontend, ответы на вопросы |
| [`docs/CODEBASE_MAP.md`](docs/CODEBASE_MAP.md) | карта реализации по компонентам |
| [`docs/contracts/backend-ml.md`](docs/contracts/backend-ml.md) | контракт backend ↔ ML, поведение при сбоях |
| [`docs/contracts/backend-frontend.md`](docs/contracts/backend-frontend.md) | публичный REST с примерами |
| [`docs/contracts/*.schema.json`](docs/contracts/) | схемы лога, статистики и сырой загрузки |
| [`docs/DEMO_AND_DATASET_GUIDE.md`](docs/DEMO_AND_DATASET_GUIDE.md) | runbook демо и формат датасетов |
| [`docs/taxonomy/taxonomy_v1.md`](docs/taxonomy/taxonomy_v1.md) | таксономия: 7 классов |
| [`docs/КРОК_case.md`](docs/КРОК_case.md), [`docs/QNA_ORGANIZERS.md`](docs/QNA_ORGANIZERS.md), [`docs/product_owners_pain.md`](docs/product_owners_pain.md) | материалы кейса и боль заказчика |
| [`ml_service/ТЗ.md`](ml_service/ТЗ.md), [`docs/backend/BACKEND_TASK.md`](docs/backend/BACKEND_TASK.md) | ТЗ обеих частей |

Версионирование контрактов: изменение `/statistics` → меняется `schema_version`; изменение
таксономии → `taxonomy_version` (сейчас `v1`).

---

## 14. Команда

| | |
|---|---|
| **@laughin_me** | backend, инфраструктура, интеграция, ROI |
| **@lapcevichme** | ML-пайплайн, датасеты, Open WebUI |
| **@oatis123** | frontend, визуализация |
