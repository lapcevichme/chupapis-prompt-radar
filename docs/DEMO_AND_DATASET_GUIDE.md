# Prompt Radar: запуск, свои датасеты и сценарий демонстрации

Этот runbook описывает текущий MVP: как поднять платформу локально или на одном demo-сервере,
как подготовить несколько собственных датасетов и как последовательно показать продукт.
Точные API-контракты остаются в `docs/contracts/`, архитектура — в `docs/CODEBASE_MAP.md`.

## 1. Что уже готово для показа

Проверенный baseline от 2026-07-25:

- frontend/nginx, backend, Postgres, Qdrant и ML поднимаются одним Compose;
- ML работает через OpenRouter embeddings + LLM, CatBoost-классификатор загружен;
- при чистом старте создаются три preloaded workspace: 170, 106 и 109 записей;
- глобально обработано 385 записей, в Qdrant лежит 385 векторов размерности 2560;
- heavy recompute создал и назвал 22 сценария;
- фильтр датасета применяется к Overview, Scenarios, Logs, ROI и экспортам;
- JSON/JSONL/CSV можно загрузить через экран **Ingestion & Sources**;
- XLSX и CSV экспортируются из **ROI Analytics**.

Demo credentials по умолчанию: `test@gmail.com` / `test123`. Для публичного стенда обязательно
замени их в корневом `.env`.

## 2. Быстрый локальный запуск

Требуются Docker Engine/Desktop с Compose v2 и доступ к выбранному model provider.

```bash
cp .env.example .env
cp ml_service/.env.example ml_service/.env
```

В `ml_service/.env` для OpenRouter должны быть настроены `ML_MODE=online`, модели и локальный
`OPENROUTER_API_KEY`. Не коммить этот файл и не вставляй ключ в логи или скриншоты.

```bash
make up
docker compose ps
curl -fsS http://localhost:8000/health/ready
```

`make up` пересобирает образы, запускает сервисы в фоне и ждёт healthchecks до 240 секунд.
Первичная классификация и recompute продолжаются после того, как контейнеры стали healthy.
Открой <http://localhost:3000> и на экране Sources дождись:

```text
ingesting → classified → recomputed
```

На online-конфигурации первый запуск обычно занимает несколько минут: embeddings считаются
батчами, а имена сценариев LLM создаёт последовательно.

Проверки перед показом:

```bash
docker compose ps
curl -fsS http://localhost:8080/api/ready
curl -fsS http://localhost:8000/health/ready
curl -fsS http://localhost:6333/collections/prompt_radar_vectors
```

В UI индикатор в верхней панели должен показывать **Healthy**, а все источники — `recomputed`.

## 3. Как готовить собственные датасеты

Один загруженный файл становится одним отдельным workspace. Поэтому разные подразделения,
компании или эксперименты лучше генерировать отдельными файлами, например:

```text
sales-crm.json
engineering-copilot.jsonl
support-knowledge.csv
```

Backend создаёт свой `source_id` и привязывает к нему канонические request IDs. Одинаковые
внешние `request_id` в разных файлах не конфликтуют.
Машинно-читаемая рекомендуемая схема JSON находится в
`docs/contracts/upload-dataset.schema.json`.

### Минимальный JSON

Достаточно массива объектов с непустым `user_query` или `query_text`:

```json
[
  {"request_id": "sales-0001", "user_query": "Собери краткий отчёт по воронке продаж"},
  {"request_id": "sales-0002", "user_query": "Подготовь письмо клиенту после встречи"}
]
```

Такой файл покажет классификацию и логи, но ROI будет нулевым или малоинформативным.

### Рекомендуемый JSON для полной демонстрации

```json
[
  {
    "request_id": "sales-0001",
    "user_query": "Собери отчёт по конверсии лидов из CRM за неделю",
    "status": "success",
    "simulated_context_tokens": 12000,
    "estimated_manual_time_minutes": 45,
    "tools_used": ["CRM", "Excel"],
    "category": "data_analysis",
    "style": "formal",
    "agent_steps": 4
  },
  {
    "request_id": "sales-0002",
    "user_query": "Подготовь follow-up письмо клиенту после демо",
    "status": "success",
    "simulated_context_tokens": 3500,
    "estimated_manual_time_minutes": 20,
    "tools_used": ["Mail"],
    "category": "text_generation",
    "style": "brief",
    "agent_steps": 2
  },
  {
    "request_id": "sales-0003",
    "user_query": "Найди причины расхождения показателей в двух отчётах",
    "status": "error_tool",
    "simulated_context_tokens": 18000,
    "estimated_manual_time_minutes": 60,
    "tools_used": ["CRM", "BI"],
    "category": "data_analysis",
    "style": "formal",
    "agent_steps": 6
  }
]
```

Это только иллюстрация структуры. Для качественных кластеров нужны десятки или сотни записей.

### Поля входного файла

| Поле | Нужно | Как используется |
|---|---:|---|
| `user_query` или `query_text` | да | Текст для CatBoost, embeddings и кластеризации. |
| `request_id` | желательно | Уникальный ID внутри файла; при отсутствии backend синтезирует его. |
| `status` | желательно | `success`, `error_tool` или `hallucination_loop`; влияет на success rate и wasted tokens. |
| `simulated_context_tokens` | для ROI | Расход токенов; при отсутствии считается как 0. |
| `estimated_manual_time_minutes` | для ROI | Оценка ручного времени; база расчёта сохранённых FTE-часов. |
| `tools_used` | для ROI | JSON-массив инструментов, например `["CRM", "Mail"]`. |
| `category` | нет | Gold/контрольная метка из taxonomy v1; не принуждает модель выбрать этот класс. |
| `style` | нет | Метаданные стиля запроса. |
| `agent_steps` | нет | Число шагов агента, сохраняется в ML metadata. |

Допустимые значения `category`: `text_generation`, `code_help`, `data_analysis`, `education`,
`information_search`, `task_management`, `other`. `unknown` назначает только классификатор при
низкой уверенности.

Текущее ограничение: входной `timestamp` при файловой загрузке пока не читается. Backend
синтезирует временную шкалу за последние 14 дней, чтобы показать Dynamics. Для аналитики по
реальным датам normalizer нужно расширить отдельным изменением.

### JSONL и CSV

JSONL содержит один JSON-объект на строку и удобен для генерации больших файлов:

```jsonl
{"request_id":"eng-0001","user_query":"Объясни причину ошибки сборки","status":"success","simulated_context_tokens":5000,"estimated_manual_time_minutes":25,"tools_used":["GitLab"]}
{"request_id":"eng-0002","user_query":"Напиши SQL для агрегации метрик","status":"success","simulated_context_tokens":8000,"estimated_manual_time_minutes":40,"tools_used":["PostgreSQL"]}
```

CSV использует те же имена колонок. `tools_used` можно передать JSON-массивом или строкой через
запятую; для надёжности при генерации предпочтителен JSON:

```csv
request_id,user_query,status,simulated_context_tokens,estimated_manual_time_minutes,tools_used,category,style,agent_steps
support-0001,"Найди инструкцию по восстановлению доступа",success,4000,15,"[""Confluence"",""AD""]",information_search,formal,2
```

Frontend разрешает файлы до 50 MB. `.txt` тоже виден в file picker, но его содержимое парсится
как JSON; для ясности используй расширение `.json`.

### Как генерировать данные, чтобы аналитика выглядела убедительно

- Делай 100–500 записей на один workspace для быстрого demo-run.
- Закладывай хотя бы 15–30 семантически похожих формулировок на ожидаемый сценарий. Текущий
  HDBSCAN использует `min_cluster_size=10`.
- Смешивай 3–7 типов задач, но не делай каждую строку уникальной темой.
- Варьируй лексику, длину, формальность и наличие опечаток; не копируй один prompt дословно.
- Оставляй 10–20% `error_tool`/`hallucination_loop`, чтобы показать failure и wasted tokens.
- Используй реалистичные tokens и manual time: иначе ROI будет технически рассчитан, но неубедителен.
- Добавляй инструменты к автоматизированным успешным задачам — из них строятся automation rate и
  top tools.
- Не клади в demo-файлы персональные данные, секреты и реальные конфиденциальные prompts.

## 4. Загрузка нескольких своих датасетов

### Через интерфейс

1. Открой **Ingestion & Sources**.
2. Перетащи JSON/JSONL/CSV в **Upload New Source**.
3. Проверь `records valid / records total` и `records rejected`.
4. Дождись статуса `classified`.
5. Повтори для остальных файлов.
6. Когда все файлы стали `classified`, один раз нажми **Recompute Scenarios**.
7. Дождись `completed` в recompute pill и `recomputed` у источников.
8. Через Dataset Switcher сравни каждый файл с **All datasets**.

Не запускай recompute после каждого файла: он глобальный и должен видеть сразу весь актуальный
набор. Online-classification, Logs и базовый Dashboard появляются до heavy recompute, но
стабильные HDBSCAN-сценарии и LLM-названия — после него.

Если нужно показать только свои датасеты без трёх встроенных workspace, до первого запуска задай
в корневом `.env`:

```dotenv
PRELOAD_DATASETS_ENABLED=false
PRELOAD_DATASETS_RECOMPUTE=false
```

Переключение флага не удаляет уже созданные источники. Для полностью чистого стенда нужно сначала
сделать осознанный `make down-clean`, затем поднять Compose и загрузить свои файлы. Если встроенные
данные нужны как baseline для сравнения, оставь оба флага `true`.

### Через API

UI предпочтительнее для показа, но тот же поток можно автоматизировать:

```bash
BASE_URL=http://localhost:3000
DATASET_PATH=./sales-crm.json
COOKIE_JAR=$(mktemp)

curl -fsS -c "$COOKIE_JAR" \
  -H 'Content-Type: application/json' \
  -d '{"email":"test@gmail.com","password":"test123"}' \
  "$BASE_URL/api/v1/auth/login"

curl -fsS -b "$COOKIE_JAR" \
  -F "file=@$DATASET_PATH" \
  "$BASE_URL/api/v1/ingest"

curl -fsS -b "$COOKIE_JAR" "$BASE_URL/api/v1/sources"
curl -fsS -b "$COOKIE_JAR" -X POST "$BASE_URL/api/v1/recompute"
curl -fsS -b "$COOKIE_JAR" "$BASE_URL/api/v1/recompute/status"

unlink "$COOKIE_JAR"
```

На публичном стенде замени URL и credentials. Не храни пароль в shell history реального
production-аккаунта; используй secret manager или короткоживущую demo-учётку.

## 5. Стабильный сценарий презентации на 7–10 минут

### До встречи

1. Подними стенд и дождись `recomputed` заранее.
2. Открой UI в отдельном browser profile и проверь login.
3. Проверь **Healthy**, 385 записей и 22 сценария для встроенного baseline либо свои ожидаемые
   totals для сгенерированных файлов.
4. Скачай XLSX один раз, чтобы убедиться, что browser не блокирует загрузку.
5. Не запускай `make demo` непосредственно перед показом: этот legacy smoke добавляет ещё один
   demo source и меняет глобальные totals.

### Во время показа

1. **Overview / All datasets.** Объясни distribution задач, top scenarios, dynamics и outliers.
2. **Dataset Switcher.** Переключи 2–3 workspace и покажи, что counts, категории и ROI меняются.
3. **Scenarios.** Открой LLM-name, summary, user goal, pain points и automation potential.
4. **Logs & Outliers.** Покажи исходные запросы и фильтры. Outlier — редкий запрос, а не ошибка
   агента; failures показываются отдельно.
5. **ROI Analytics.** Покажи FTE hours, net savings, success rate, tools и what-if ставки, затем
   скачай XLSX/CSV.
6. **Ingestion & Sources.** Покажи provenance источников и normalization report. Если нужен live
   wow-effect, загрузи небольшой заранее подготовленный файл и покажи переход в `classified`.

Heavy recompute лучше не ждать внутри короткой презентации: запусти его заранее либо нажми в
конце и объясни, что online analytics доступны сразу, а batch-clusters обновляются асинхронно.

Дополнительный live-сценарий:

```bash
make feed
```

Он отправляет поток в rolling source `live`; Dashboard обновляется, а freshness показывает, что
для новых записей стоит пересчитать сценарии.

## 6. Публичный demo/staging на одном сервере

Текущий Compose подходит для демонстрационного single-host стенда. Практический минимум — 4 CPU,
8 GB RAM, 20 GB свободного диска и стабильный исходящий HTTPS-доступ к OpenRouter. Это ориентир,
а не формальный capacity guarantee.

В корневом `.env` для публичного стенда задай сильные уникальные значения:

```dotenv
APP_STAGE=prod
POSTGRES_PASSWORD=<strong-random-password>
JWT_SECRET=<random-string-at-least-32-characters>
ML_SERVICE_TOKEN=<strong-random-token>
INGEST_TOKEN=<strong-random-token>
DEMO_USER_EMAIL=<demo-login>
DEMO_USER_PASSWORD=<strong-demo-password>
FRONTEND_AUTO_DEMO_LOGIN=false
COOKIE_SECURE=true
COOKIE_SAMESITE=lax
CORS_ORIGINS=https://radar.example.com
PRELOAD_DATASETS_ENABLED=true
PRELOAD_DATASETS_RECOMPUTE=true
```

Для стенда только на собственных данных поставь оба preload-флага в `false` и загрузи файлы через
Sources после старта.

В `ml_service/.env` оставь `ML_MODE=online` и provider credentials. Compose специально задаёт
поверх него только внутренние URL/пути и service token.

Не публикуй инфраструктурные порты наружу. Если TLS reverse proxy работает на том же host,
ограничь bindings loopback-интерфейсом:

```dotenv
FRONTEND_HOST_PORT=127.0.0.1:3000
BACKEND_HOST_PORT=127.0.0.1:8080
ML_HOST_PORT=127.0.0.1:8000
QDRANT_HOST_PORT=127.0.0.1:6333
QDRANT_GRPC_HOST_PORT=127.0.0.1:6334
DB_HOST_PORT=127.0.0.1:5433
```

Reverse proxy должен терминировать HTTPS и проксировать весь домен на
`http://127.0.0.1:3000`. Frontend nginx сам отправит `/api/*` во внутренний backend, поэтому
browser cookies остаются same-origin.

```bash
docker compose up -d --build --wait --wait-timeout 240
docker compose ps
docker compose logs --tail=100 backend ml-service
```

Остановить с сохранением данных:

```bash
docker compose down
```

Полностью очистить Postgres, Qdrant и ML meta-store:

```bash
make down-clean
```

Последняя команда необратима без backup.

### Где заканчивается demo/staging и начинается production

Перед настоящей эксплуатацией с SLA нужны отдельные работы:

- TLS/reverse proxy, firewall и secret manager;
- регулярные backups Postgres, Qdrant и ML meta volume;
- внешний task broker/job store вместо in-process background tasks;
- несколько workers только после выноса process-local state;
- нормальная IAM/RBAC-модель вместо одной seeded demo-учётки;
- мониторинг, алерты, rate limits, audit log и политика хранения prompts;
- миграционный план при смене embedding model/dimension.

Сейчас продукт корректно позиционировать как функциональный MVP и single-host demo/staging, а не
как отказоустойчивую multi-tenant production-платформу.

## 7. Быстрая диагностика

- **UI Degraded:** проверь `/api/ready` backend и `/health/ready` ML.
- **Источник `failed`:** `docker compose logs --tail=200 backend ml-service`.
- **Долго `ingesting`:** проверь provider quota/network и число assignments в ML.
- **Много `unknown`:** это confidence ниже порога CatBoost, а не mock; проверь домен датасета.
- **Слишком много/мало сценариев:** проверь повторяемость тем и размер групп; recompute требует
  минимум 10 близких записей на устойчивый cluster.
- **Смена embedding model/dimension:** старую Qdrant collection нельзя смешивать с новыми
  vectors; нужен новый store/collection или осознанный `make down-clean`.
- **После рестарта recompute status `idle`:** это известное ограничение process-local job status;
  сохранённые sources/scenarios при этом остаются доступны.
