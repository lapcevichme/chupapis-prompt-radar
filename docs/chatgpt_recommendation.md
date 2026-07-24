Да. Сейчас вам **не нужно сразу строить сложную систему с десятком subagents, hooks и MCP**. На старте это скорее замедлит команду.

Ваша задача на ближайшие 1–2 часа:

1. Зафиксировать границы backend, ML, frontend и infra.
2. Создать минимальный каркас репозитория.
3. Добавить постоянный контекст для Claude Code.
4. Сделать единые команды запуска и проверки.
5. Поднять пустой, но связанный vertical slice: frontend → backend → ML.
6. Зафиксировать контракт между backend и ML, чтобы вы могли работать параллельно.

Ниже конкретный порядок действий.

# 1. Сначала зафиксируйте архитектурное решение

Для вашего хакатона я рекомендую:

* **один monorepo**
* **основной backend как модульный монолит**
* **отдельный ML-сервис**
* **один frontend**
* **PostgreSQL**
* **Docker Compose**
* без Kafka, Kubernetes, service discovery и набора микросервисов

То есть фактически у вас три приложения:

```text
Frontend
   ↓
Backend API
   ↓
ML service
```

Backend отвечает за:

* загрузку датасета
* создание запуска анализа
* хранение статусов
* хранение результатов
* API для frontend
* оркестрацию ML-обработки
* историю запусков
* формирование данных для дашборда

ML-сервис отвечает за:

* предобработку запросов
* классификацию
* построение сценариев использования
* кластеризацию
* генерацию названий и саммари кластеров
* обнаружение проблемных запросов
* расчёт ML-метрик
* evaluation

Frontend отвечает только за продуктовый интерфейс и визуализацию.

Это решение надо сразу записать в репозиторий. Не держите его только в чате.

# 2. Создайте структуру репозитория

Я бы сделал так:

```text
prompt-radar/
├── apps/
│   ├── api/
│   │   ├── app/
│   │   ├── tests/
│   │   ├── pyproject.toml
│   │   ├── Dockerfile
│   │   └── README.md
│   │
│   └── web/
│       ├── src/
│       ├── public/
│       ├── package.json
│       ├── Dockerfile
│       └── README.md
│
├── services/
│   └── ml/
│       ├── app/
│       ├── tests/
│       ├── pyproject.toml
│       ├── Dockerfile
│       └── README.md
│
├── contracts/
│   ├── ml-analysis-request.schema.json
│   ├── ml-analysis-result.schema.json
│   ├── dashboard.schema.json
│   └── README.md
│
├── data/
│   ├── samples/
│   ├── generated/
│   └── README.md
│
├── eval/
│   ├── datasets/
│   ├── baselines/
│   ├── reports/
│   └── README.md
│
├── docs/
│   ├── architecture/
│   │   ├── overview.md
│   │   ├── data-flow.md
│   │   └── api-boundaries.md
│   ├── decisions/
│   │   └── 0001-system-architecture.md
│   ├── plans/
│   └── STATUS.md
│
├── infra/
│   ├── docker/
│   └── README.md
│
├── scripts/
│   ├── bootstrap.sh
│   ├── generate-demo-data.py
│   └── smoke-test.sh
│
├── .claude/
│   ├── rules/
│   │   ├── backend.md
│   │   ├── ml.md
│   │   ├── frontend.md
│   │   └── infra.md
│   └── settings.json
│
├── .github/
│   ├── workflows/
│   │   └── ci.yml
│   └── CODEOWNERS
│
├── CLAUDE.md
├── AGENTS.md
├── README.md
├── docker-compose.yml
├── Makefile
├── .env.example
├── .gitignore
└── .editorconfig
```

## Что пока не надо создавать

На первом этапе не создавайте:

* `.claude/agents/`
* `.claude/skills/`
* сложные hooks
* MCP-конфигурации
* Kubernetes
* Terraform
* очереди сообщений
* отдельный сервис авторизации
* отдельный reporting-service
* отдельный ingestion-service

Эти вещи стоит добавлять только тогда, когда появляется конкретная проблема.

# 3. Внутренняя структура backend

Для FastAPI я рекомендую не раскладывать проект по техническим папкам вроде одного общего `routers`, одного общего `services` и одного общего `repositories`.

Лучше организовать по бизнес-модулям:

```text
apps/api/app/
├── main.py
├── core/
│   ├── config.py
│   ├── logging.py
│   └── exceptions.py
│
├── db/
│   ├── base.py
│   ├── session.py
│   └── migrations/
│
├── modules/
│   ├── datasets/
│   │   ├── router.py
│   │   ├── schemas.py
│   │   ├── service.py
│   │   ├── repository.py
│   │   └── models.py
│   │
│   ├── analysis_runs/
│   │   ├── router.py
│   │   ├── schemas.py
│   │   ├── service.py
│   │   ├── repository.py
│   │   └── models.py
│   │
│   ├── reports/
│   │   ├── router.py
│   │   ├── schemas.py
│   │   └── service.py
│   │
│   └── health/
│       └── router.py
│
├── clients/
│   └── ml/
│       ├── client.py
│       ├── schemas.py
│       └── exceptions.py
│
└── tests/
```

Главное правило:

> Вызов ML-сервиса является внешней интеграцией и находится в `clients/ml`. ML-алгоритмы внутри backend не реализуются.

Контроллеры должны быть тонкими:

```text
HTTP request
    ↓
router
    ↓
service / use case
    ↓
repository или ML client
```

# 4. Внутренняя структура ML-сервиса

```text
services/ml/app/
├── main.py
├── api/
│   ├── router.py
│   └── schemas.py
│
├── pipeline/
│   ├── preprocessing/
│   ├── classification/
│   ├── clustering/
│   ├── summarization/
│   ├── failure_detection/
│   └── pipeline.py
│
├── domain/
│   ├── models.py
│   ├── taxonomy.py
│   └── results.py
│
├── adapters/
│   ├── embeddings/
│   ├── llm/
│   └── storage/
│
├── evaluation/
│   ├── metrics.py
│   ├── runner.py
│   └── reports.py
│
├── config.py
└── tests/
```

Здесь важно сразу разделить:

* production inference
* эксперименты
* evaluation
* ноутбуки

Ноутбуки не должны становиться единственным местом, где работает алгоритм.

Можно завести:

```text
services/ml/notebooks/
```

Но всё, что используется приложением, должно находиться в обычных Python-модулях.

# 5. Контракт между backend и ML надо создать до реализации

Это самое важное, чтобы ты и ML-инженер не блокировали друг друга.

Не договаривайтесь в формате:

> «Ну там backend как-нибудь вызовет ML».

Создайте конкретную схему.

Например, backend отправляет:

```json
{
  "analysis_run_id": "run_123",
  "input_uri": "file:///data/runs/run_123/input.jsonl",
  "pipeline_config": {
    "taxonomy_version": "v1",
    "generate_summaries": true,
    "detect_failures": true
  }
}
```

ML отвечает:

```json
{
  "analysis_run_id": "run_123",
  "status": "completed",
  "output_uri": "file:///data/runs/run_123/result.json",
  "metrics": {
    "records_processed": 1000,
    "clusters_created": 18,
    "unclassified_records": 24,
    "processing_time_seconds": 43.2
  }
}
```

## Почему `input_uri`, а не огромный массив в HTTP

В материалах кейса запросы потенциально могут быть очень длинными. Если backend начнёт передавать через HTTP огромные массивы логов, вы быстро получите:

* большие тела запросов
* таймауты
* повторную передачу данных
* сложности с восстановлением после ошибки

Для хакатона можно использовать общую Docker-volume:

```text
/data/runs/<analysis_run_id>/
```

Backend пишет туда:

```text
input.jsonl
```

ML пишет:

```text
result.json
metrics.json
```

В будущем `file://` можно заменить на:

```text
s3://bucket/runs/run_123/input.jsonl
```

При этом контракт почти не изменится.

# 6. Первым делом создайте `CLAUDE.md`

Это основной постоянный контекст Claude Code.

Не делайте его огромным. На старте хватит примерно 100–150 строк.

Вот рабочая основа.

```md
# Prompt Radar

## Product

Prompt Radar is an analytics platform for user requests sent to enterprise AI agents.

The product must:

- classify requests by task type
- group requests into use-case scenarios
- generate clear names and summaries for scenarios
- show scenario frequency and growth
- identify requests where the AI agent has problems
- provide an understandable dashboard for managers and technical leaders

The hackathon priority is a reproducible end-to-end demo, not a production-scale distributed system.

## Architecture

The repository is a monorepo.

Main components:

- `apps/api` - FastAPI modular monolith
- `apps/web` - frontend dashboard
- `services/ml` - separate ML analysis service
- `contracts` - language-neutral API and data contracts
- `eval` - evaluation datasets, baselines and reports
- `infra` - Docker and deployment configuration

Architecture invariants:

- The main backend remains a modular monolith.
- ML algorithms must live in `services/ml`.
- Backend may orchestrate ML processing but must not implement ML algorithms.
- Frontend communicates only with the main backend.
- Frontend must not call the ML service directly.
- Shared integration contracts live in `contracts`.
- Do not introduce new services without a clear technical reason.
- Do not add Kafka, Kubernetes or other distributed infrastructure for the MVP.

## Backend rules

- Organize backend code by domain modules.
- Keep routers thin.
- Put business logic in services or use cases.
- External ML calls belong in `apps/api/app/clients/ml`.
- New endpoints must have explicit request and response schemas.
- Analysis run creation should be idempotent where practical.
- Persist analysis run status and errors.

## ML rules

- Keep preprocessing, classification, clustering, summarization and evaluation separated.
- Pipeline runs must be reproducible.
- Taxonomy versions must be explicit.
- Do not keep production logic only in notebooks.
- Do not overwrite evaluation baselines unless explicitly requested.
- Every pipeline result must include processing metrics and error information.

## Frontend rules

- Optimize the dashboard for managers and technical leaders.
- Every chart must answer a concrete business question.
- Prioritize:
  - most common task categories
  - most common use cases
  - growing scenarios
  - failure categories
  - representative request examples
- Avoid decorative complexity that does not improve the demo.

## Development workflow

Before changing code:

1. Read relevant project files.
2. Search for existing implementation patterns.
3. For non-trivial changes, propose a short plan.
4. Identify which components and contracts are affected.

During implementation:

- Keep changes small and reviewable.
- Do not refactor unrelated code.
- Prefer existing patterns over new abstractions.
- Do not change another team member's domain unless required.
- Update contracts before changing both sides of an integration.

After implementation:

1. Run the smallest relevant tests.
2. Run lint or type checking for the affected component.
3. Summarize modified files.
4. State what was tested.
5. State any remaining risks or unfinished work.

## Commands

Use repository commands from the root:

- `make dev`
- `make test`
- `make lint`
- `make test-api`
- `make test-ml`
- `make test-web`
- `make smoke`

Do not invent commands. If a command does not exist, inspect the Makefile or component README.

## Security

- Never read or print `.env` files.
- Never commit API keys or credentials.
- Never run `git push` unless explicitly requested.
- Never delete datasets or evaluation baselines without confirmation.
- Never run destructive database commands without confirmation.

## Compact instructions

When compacting the conversation, preserve:

- current task and acceptance criteria
- accepted architecture decisions
- modified files
- commands already run
- current errors
- remaining work
- the exact next step

Discard:

- long command output
- resolved errors
- duplicated explanations
- old alternatives that were rejected
```

После создания попросите всех участников команды прочитать файл и внести поправки.

Важно, чтобы это был не «промпт для магии», а реальная договорённость команды.

# 7. Добавьте scoped rules

Корневой `CLAUDE.md` содержит общие правила. Специализированные инструкции кладите в `.claude/rules`.

## `.claude/rules/backend.md`

```md
---
paths:
  - "apps/api/**"
  - "contracts/**"
---

# Backend rules

- Use FastAPI.
- Organize code by domain modules.
- Keep routers thin.
- Keep persistence behind repositories.
- Keep ML integration behind a dedicated client.
- Do not import code from `services/ml`.
- Do not expose database models directly through the API.
- Every endpoint must use explicit request and response schemas.
- Add tests for business logic and API behavior.
- Check existing migrations before changing database models.
```

## `.claude/rules/ml.md`

```md
---
paths:
  - "services/ml/**"
  - "eval/**"
  - "data/**"
  - "contracts/**"
---

# ML rules

- Keep the pipeline deterministic where possible.
- Separate inference code from experiments and notebooks.
- Keep taxonomy and label definitions versioned.
- Store run metrics with every analysis result.
- Do not modify baseline evaluation artifacts automatically.
- Changes affecting output labels require an evaluation run.
- Large requests must be handled explicitly through chunking, reduction or hierarchical analysis.
```

## `.claude/rules/frontend.md`

```md
---
paths:
  - "apps/web/**"
  - "contracts/**"
---

# Frontend rules

- Frontend communicates only with `apps/api`.
- Do not call the ML service directly.
- Prefer generated or typed API clients.
- Every dashboard element must answer a user question.
- Handle loading, empty and error states.
- Keep demo-critical paths simple.
- Do not add a state-management library unless existing state becomes difficult to manage.
```

## `.claude/rules/infra.md`

```md
---
paths:
  - "infra/**"
  - "docker-compose.yml"
  - ".github/**"
  - "scripts/**"
---

# Infrastructure rules

- The complete local system must start with one documented command.
- Prefer Docker Compose for the hackathon.
- Do not add Kubernetes.
- Do not store secrets in the repository.
- Pin important dependency and container versions.
- Health checks must exist for API, ML service and database.
- Do not change deployment configuration unless the task explicitly requires it.
```

Так Claude будет подгружать backend-инструкции при работе с backend, а ML-инструкции при работе с ML.

# 8. Добавьте `AGENTS.md`

Он нужен для совместимости с другими coding agents.

Не копируйте туда весь `CLAUDE.md`. Сделайте короткий переносимый вариант:

```md
# Agent instructions

The canonical project instructions are in `CLAUDE.md`.

## Repository

- `apps/api` - FastAPI modular monolith
- `apps/web` - frontend
- `services/ml` - ML analysis service
- `contracts` - shared language-neutral contracts
- `eval` - evaluation datasets and reports
- `infra` - local and deployment infrastructure

## Boundaries

- Frontend calls only the main API.
- Backend orchestrates ML through an explicit contract.
- ML algorithms stay in `services/ml`.
- Do not add new services without a clear reason.
- Do not read secrets.
- Do not modify unrelated components.
- Keep changes small and testable.

## Workflow

1. Inspect existing code.
2. Propose a plan for non-trivial changes.
3. Implement the minimum necessary change.
4. Run relevant tests and lint.
5. Report modified files and remaining risks.
```

# 9. Добавьте минимальные настройки Claude Code

Файл:

```text
.claude/settings.json
```

На старте я бы не давал Claude слишком широкие разрешения.

Пример:

```json
{
  "permissions": {
    "allow": [
      "Bash(git status)",
      "Bash(git diff *)",
      "Bash(make test-api)",
      "Bash(make test-ml)",
      "Bash(make test-web)",
      "Bash(make lint)",
      "Bash(make smoke)"
    ],
    "deny": [
      "Read(./.env)",
      "Read(./.env.*)",
      "Read(./secrets/**)",
      "Bash(git push *)",
      "Bash(rm -rf *)"
    ]
  }
}
```

Не копируйте это механически до появления команд в `Makefile`. Сначала создайте команды, затем разрешения.

Локальные настройки каждого разработчика:

```text
.claude/settings.local.json
```

Этот файл добавьте в `.gitignore`.

# 10. Создайте единые команды через Makefile

Claude работает заметно лучше, когда ему не нужно угадывать, как запускать каждый компонент.

Пример основы:

```makefile
.PHONY: dev down test lint test-api test-ml test-web smoke

dev:
	docker compose up --build

down:
	docker compose down

test: test-api test-ml test-web

test-api:
	cd apps/api && uv run pytest

test-ml:
	cd services/ml && uv run pytest

test-web:
	cd apps/web && npm run test

lint:
	cd apps/api && uv run ruff check .
	cd services/ml && uv run ruff check .
	cd apps/web && npm run lint

smoke:
	./scripts/smoke-test.sh
```

Команды можете поменять под `pnpm`, `poetry` или другой менеджер.

Ключевой принцип:

> Команда из `CLAUDE.md` должна реально работать из корня репозитория.

Не пишите в инструкциях выдуманные команды «на будущее».

# 11. Добавьте `.gitignore`

Минимально:

```gitignore
# Environment
.env
.env.*
!.env.example

# Claude local settings
.claude/settings.local.json

# Python
__pycache__/
*.py[cod]
.pytest_cache/
.ruff_cache/
.venv/

# Node
node_modules/
dist/
.next/

# IDE
.idea/
.vscode/
.DS_Store

# Local datasets and artifacts
data/generated/*
data/raw/*
artifacts/*
eval/reports/*

# Keep documentation and sample data
!data/samples/
!data/samples/**
!eval/reports/.gitkeep
```

Не кладите в Git огромные сырые датасеты.

В репозитории должны находиться:

* небольшой демонстрационный датасет
* генератор датасета
* схема данных
* golden set для evaluation
* инструкции получения полного датасета

# 12. Создайте архитектурный документ

Файл:

```text
docs/architecture/overview.md
```

Он должен отвечать всего на несколько вопросов:

```md
# System architecture

## Goal

Transform raw AI-agent request logs into structured and explainable use-case analytics.

## Components

### Web

Displays analysis runs, categories, use cases, trends and failures.

### API

Manages datasets, analysis runs, persisted results and dashboard API.

### ML service

Performs preprocessing, classification, clustering, summarization and failure analysis.

### PostgreSQL

Stores datasets metadata, analysis runs, scenarios and aggregated results.

### Shared run storage

Stores large normalized input and result artifacts.

## Data flow

1. User uploads a dataset.
2. API validates and normalizes the data.
3. API creates an analysis run.
4. API writes normalized input to run storage.
5. API calls ML service with the run identifier and input URI.
6. ML service executes the pipeline.
7. ML service writes output artifacts and returns metrics.
8. API persists normalized results.
9. Web displays the dashboard.

## Non-goals for the hackathon

- Kubernetes
- event-driven microservices
- enterprise authentication
- unlimited horizontal scaling
- real-time streaming
```

# 13. Создайте ADR с главным решением

Файл:

```text
docs/decisions/0001-system-architecture.md
```

Пример:

```md
# ADR 0001: Modular monolith with a separate ML service

## Status

Accepted.

## Context

The team must build an end-to-end analytics product during a hackathon. The system includes web UI, business orchestration and a specialized ML pipeline.

## Decision

Use:

- one monorepo
- one modular FastAPI backend
- one separate Python ML service
- one web frontend
- PostgreSQL
- Docker Compose
- file-compatible run storage abstraction

## Reasons

- fast implementation
- clear team ownership
- simple local startup
- isolated ML dependencies
- explicit backend-to-ML contract
- easy demonstration

## Rejected alternatives

### Multiple backend microservices

Rejected because deployment and integration complexity outweigh the benefits during the hackathon.

### ML logic inside the main backend

Rejected because ML dependencies, experiments and processing lifecycle require separate ownership.

### Frontend calling ML directly

Rejected because analysis orchestration, status and persistence belong to the backend.
```

Claude сможет прочитать этот документ в новом чате и не будет каждый раз предлагать другую архитектуру.

# 14. Используйте task-файлы для сложных задач

Не нужно хранить весь ход разработки в одном гигантском чате.

Для каждой крупной задачи создавайте файл:

```text
docs/plans/<task-name>.md
```

Например:

```text
docs/plans/analysis-run-api.md
```

Содержание:

```md
# Analysis run API

## Goal

Allow a user to start an analysis for an uploaded dataset and track its state.

## Scope

- create analysis run
- persist status
- call ML service
- expose status endpoint
- persist failure information

## Out of scope

- retries through a message queue
- distributed workers
- scheduling
- authentication

## Acceptance criteria

- POST `/api/v1/analysis-runs` creates a run
- run starts in `pending`
- backend calls ML service
- status becomes `running`, `completed` or `failed`
- GET endpoint returns status and error details
- relevant tests pass

## Decisions

- ML integration goes through `clients/ml`
- the initial implementation may call ML synchronously
- the public API must not expose ML implementation details

## Current status

Not started.
```

После реализации Claude обновляет только раздел:

```md
## Current status
```

Не просите его вести подробный дневник каждой команды. Такой журнал быстро превращается в мусор.

# 15. Первый запрос к Claude Code

Откройте Claude Code из корня репозитория.

Первую сессию посвятите только bootstrap репозитория.

Используйте примерно такой запрос:

```text
Мы только что создали пустой репозиторий Prompt Radar.

Сначала прочитай CLAUDE.md, AGENTS.md и содержимое docs.

Задача:
подготовить минимальный каркас monorepo для hackathon MVP.

Компоненты:
- apps/api: FastAPI modular monolith
- apps/web: React frontend
- services/ml: FastAPI ML service
- PostgreSQL
- Docker Compose
- shared contracts in contracts/

Ограничения:
- не реализуй продуктовую бизнес-логику
- не добавляй Kubernetes, Kafka, Redis или отдельные микросервисы
- не добавляй сложную авторизацию
- не создавай абстракции без текущего применения
- не меняй архитектурные границы из CLAUDE.md

Критерии готовности:
- все три приложения имеют health endpoint или health page
- docker compose поднимает web, api, ml и postgres
- backend может вызвать health endpoint ML-сервиса
- README содержит команды запуска
- Makefile содержит dev, test, lint и smoke
- есть .env.example
- есть минимальный smoke test

Сначала:
1. изучи структуру репозитория
2. предложи точное дерево файлов
3. перечисли зависимости
4. покажи план реализации
5. ничего не изменяй, пока я не подтвержу план
```

После проверки плана:

```text
План подтверждаю.

Реализуй его небольшими этапами.
После каждого этапа запускай минимально необходимые проверки.
Не добавляй продуктовую логику анализа запросов.
В конце покажи:
- созданные файлы
- команды запуска
- результаты проверок
- известные ограничения
```

# 16. Как использовать чаты Claude Code

Главное правило:

> Одна сессия Claude Code соответствует одной связной задаче.

Хорошие границы сессии:

* bootstrap monorepo
* загрузка датасета
* analysis run API
* интеграция backend с ML
* структура результата анализа
* dashboard API
* конкретный frontend-экран
* исправление определённого бага

Плохой вариант:

```text
Сделай весь backend, потом посмотри ML, потом поправь Docker, потом помоги с презентацией.
```

## Когда продолжать текущую сессию

Продолжайте её, когда:

* цель та же
* работаете с тем же модулем
* Claude помнит принятые решения
* контекст ещё не загрязнён большим количеством ошибок
* вы не переключились на другой компонент

## Когда делать `/compact`

Делайте compact, если:

* задача ещё та же
* сессия длинная
* было много вывода тестов
* Claude начинает забывать ранние решения
* `/context` показывает, что окно сильно заполнено

Не пишите просто:

```text
/compact
```

Лучше использовать направленный вариант:

```text
/compact Сохрани текущую цель, критерии готовности, принятые архитектурные решения, изменённые файлы, текущие ошибки, выполненные проверки и следующий шаг. Удали длинные выводы команд, решённые ошибки и отвергнутые варианты.
```

## Когда делать `/clear` или новый чат

Создавайте чистую сессию, когда:

* закончили feature
* переключились с backend на ML
* переключились с реализации на архитектурное исследование
* начали разбирать независимый баг
* текущий Claude зафиксировался на ошибочном решении
* прошли несколько compact, и качество стало заметно хуже
* изменения уже закоммичены и начинается новый workstream

Перед очисткой попросите Claude:

```text
Перед завершением сессии обнови docs/plans/<task>.md.

Зафиксируй:
- что реализовано
- какие решения приняты
- какие файлы изменены
- какие проверки прошли
- что осталось
- какой должен быть первый шаг следующей сессии

Не добавляй подробный журнал команд.
```

После этого новая сессия начинается так:

```text
Прочитай CLAUDE.md и docs/plans/analysis-run-api.md.

Продолжи задачу с раздела Current status.
Сначала проверь фактическое состояние кода и git diff.
Не считай документ безусловно актуальным, если код ему противоречит.
```

Последняя фраза важна. Claude должен проверять реальный код, а не слепо доверять статусному файлу.

# 17. Как писать задачи Claude

Используйте постоянный шаблон.

```text
Задача:
[Что конкретно должно появиться.]

Контекст:
[Где это находится и зачем нужно.]

Границы:
- работаем только с [...]
- не меняем [...]
- интеграция должна использовать [...]

Критерии готовности:
- [...]
- [...]
- [...]

Перед реализацией:
1. прочитай релевантные файлы
2. найди существующие паттерны
3. перечисли затрагиваемые контракты
4. предложи короткий план

После реализации:
1. запусти релевантные тесты
2. запусти lint/typecheck
3. покажи изменённые файлы
4. укажи риски и оставшуюся работу
```

## Плохой запрос

```text
Сделай нормальный анализ датасета.
```

## Нормальный запрос

```text
Задача:
реализовать создание analysis run в backend.

Контекст:
dataset уже загружен и имеет идентификатор. Backend должен создать запуск анализа и вызвать существующий ML client.

Границы:
- изменяем apps/api
- при необходимости обновляем contracts
- не меняем реализацию ML pipeline
- не добавляем очередь
- не добавляем новые сервисы

Критерии готовности:
- POST /api/v1/analysis-runs принимает dataset_id
- создаётся запись со статусом pending
- ML client получает analysis_run_id и input_uri
- ошибки ML сохраняются в analysis run
- есть тест успешного и ошибочного сценария
- существующие тесты проходят

Сначала изучи существующие модули datasets и clients/ml.
Предложи план, но пока не изменяй файлы.
```

# 18. Как разделить работу команды

Предлагаю такое владение.

| Участник           | Зона                                                       |
| ------------------ | ---------------------------------------------------------- |
| Ты, backend        | `apps/api`, backend-to-ML orchestration, DB, API contracts |
| ML-инженер         | `services/ml`, `eval`, taxonomy, pipeline                  |
| Frontend           | `apps/web`, dashboard                                      |
| Четвёртый участник | `infra`, Docker Compose, CI, датасет, demo scripts         |

Создайте `.github/CODEOWNERS`:

```text
/apps/api/          @backend-owner
/services/ml/       @ml-owner
/apps/web/          @frontend-owner
/infra/             @infra-owner
/docker-compose.yml @infra-owner
/contracts/         @backend-owner @ml-owner @frontend-owner
```

Особенно важно совместное владение `contracts`.

Изменение контракта должно быть видно всем трём направлениям.

# 19. Git-процесс

Для хакатона не усложняйте Git Flow.

Используйте:

```text
main
feature/backend-analysis-runs
feature/ml-pipeline
feature/frontend-dashboard
chore/docker-compose
```

Правила:

* одна feature, одна ветка
* небольшие коммиты
* не держать незакоммиченные изменения часами
* перед началом задачи подтягивать `main`
* не запускать двух Claude-сессий, редактирующих одну рабочую директорию

Если один разработчик хочет параллельно запустить несколько Claude Code, используйте `git worktree`.

Пример:

```bash
git worktree add ../prompt-radar-analysis-runs -b feature/analysis-runs
git worktree add ../prompt-radar-reports -b feature/reporting-api
```

Тогда каждая Claude-сессия работает в своей директории и не перетирает файлы другой.

# 20. Первые четыре коммита

Я бы двигался так.

## Коммит 1

```text
chore: bootstrap monorepo structure
```

Содержит:

* каталоги
* `.gitignore`
* `.editorconfig`
* пустые component README

## Коммит 2

```text
docs: add architecture and agent instructions
```

Содержит:

* `CLAUDE.md`
* `AGENTS.md`
* `.claude/rules`
* архитектурный документ
* ADR

## Коммит 3

```text
chore: add local development environment
```

Содержит:

* Dockerfile
* Docker Compose
* PostgreSQL
* health checks
* Makefile
* `.env.example`

## Коммит 4

```text
feat: add backend to ml service contract
```

Содержит:

* JSON Schema или OpenAPI-контракт
* backend ML client
* заглушку ML endpoint
* contract tests или smoke test

После этих четырёх коммитов команда уже может работать параллельно.

# 21. Первый end-to-end сценарий

До того как делать красивый дашборд и сложный ML, реализуйте одну вертикаль:

```text
1. Пользователь загружает небольшой JSONL или CSV.
2. Backend создаёт dataset.
3. Пользователь запускает анализ.
4. Backend создаёт analysis_run.
5. Backend вызывает ML.
6. ML пока возвращает фиктивные категории и сценарии.
7. Backend сохраняет результат.
8. Frontend показывает результат.
```

Даже если ML пока возвращает:

```json
{
  "scenarios": [
    {
      "name": "Работа с документами",
      "count": 120,
      "summary": "Пользователи просят анализировать и создавать документы."
    }
  ]
}
```

Это уже доказывает, что архитектура работает.

После этого ML-инженер заменяет stub реальным pipeline, не ломая backend и frontend.

# 22. Что поручить четвёртому участнику

Раз мобильное приложение не требуется, четвертому участнику можно дать очень полезный контур:

* Docker Compose
* CI
* генератор synthetic dataset
* преобразование исходного датасета в нормализованный JSONL
* smoke tests
* demo script
* подготовка evaluation set
* фиксация baseline-метрик
* проверка запуска на чистой машине

Его Definition of Done:

```text
git clone
cp .env.example .env
make dev
make smoke
```

И система работает.

Это для хакатона зачастую ценнее, чем ещё один человек, который пишет бизнес-логику.

# 23. Что не надо автоматизировать через Claude прямо сейчас

Пока не заставляйте Claude автоматически:

* обновлять `CLAUDE.md` после каждого изменения
* менять архитектурные документы без запроса
* перезаписывать baseline evaluation
* генерировать и коммитить огромные датасеты
* автоматически деплоить
* автоматически пушить ветки
* самостоятельно изменять API-контракты
* вести огромный журнал истории проекта

`CLAUDE.md` должен меняться редко, когда команда действительно принимает новое постоянное правило.

Task-файл меняется в рамках конкретной задачи.

Код и тесты остаются главным источником истины.

# Что сделать прямо сейчас

Ваш ближайший порядок:

1. Создать каталоги `apps/api`, `apps/web`, `services/ml`, `contracts`, `docs`, `eval`, `infra`.
2. Добавить `CLAUDE.md` из примера выше.
3. Добавить четыре scoped rules.
4. Добавить короткий `AGENTS.md`.
5. Записать архитектуру в ADR.
6. Создать Makefile с едиными командами.
7. Создать `.env.example` и `.gitignore`.
8. Открыть Claude Code в корне.
9. Запустить bootstrap-промпт в plan mode.
10. Проверить предложенное Claude дерево.
11. Попросить его создать только каркас и health checks.
12. Закоммитить bootstrap.
13. Создать контракт backend ↔ ML.
14. Реализовать первый сквозной сценарий на stub-данных.
15. Только после этого параллельно развивать backend, ML и frontend.

Самое важное: **сейчас вложитесь не в сложность AI-настроек, а в чёткие границы, контракты, команды запуска и маленький работающий end-to-end сценарий**. Тогда Claude Code станет ускорителем вашей архитектуры, а не генератором случайных файлов.
