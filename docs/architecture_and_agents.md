# Оптимальная монорепа и рабочий процесс с Claude Code для кейса КРОК

## Что реально требует кейс

Кейс КРОК просит не “ещё одного чат-бота”, а рабочий прототип аналитики запросов к ИИ-агентам. Must-have часть очень конкретная: автоматическая классификация запросов, группировка в устойчивые use-case сценарии, саммари по группам и понятный отчёт или дашборд для руководителей. Организаторы отдельно подчеркивают интерпретируемость результата, качество группировки, воспроизводимость, скорость и полезность вывода для CTO. На сдачу нужны репозиторий с кодом и инструкцией запуска, входной датасет либо скрипт генерации или загрузки, а также итоговый отчёт либо дашборд. Технологии можно выбирать свободно, но есть ограничение по использованию GPU H100. fileciteturn0file0 fileciteturn0file1

Для архитектуры это означает очень важную вещь: у вас побеждает не самая “правильная” распределённая система, а решение, которое быстро собирается, легко демонстрируется и даёт объяснимый результат по сырым логам. Это особенно видно по формулировкам кейса: организаторам нужен навигатор по массиву логов, а не мобильное приложение, не тяжёлый набор микросервисов и не research-only ноутбук без продуктовой оболочки. fileciteturn0file0 fileciteturn0file1

Ещё один важный сигнал из материалов кейса: средний размер пользовательского запроса заявлен как 100k токенов, а сами темы покрывают почту, CRM, Jira, Confluence, календари, заметки, Excel-выгрузки, тикеты и другие корпоративные сценарии. Значит, ваша система должна изначально быть готова к большим текстам, долгим пайплайнам анализа и к многодоменной таксономии, где сценарии завязаны не на один источник данных, а на несколько рабочих систем сразу. fileciteturn0file0

## Какая архитектура для вас оптимальна

Если говорить честно и без красивых слов, для хакатона я бы рекомендовал **модульный монолит как основной backend плюс отдельный ML-сервис**. Это не формальное требование организаторов, а практический вывод из их критериев: вам нужна устойчивость, воспроизводимость, скорость сборки и понятность продукта для демо, а не цена за “микросервисность”. fileciteturn0file0

Почему именно так. Основной backend должен отвечать за ingestion логов, учёт analysis runs, хранение результатов, API для фронта, отчёты, авторизацию, историю запусков и оркестрацию процессов. Отдельный ML-сервис имеет смысл только там, где вам действительно выгодна Python-экосистема: эмбеддинги, тематическая классификация, кластеризация, саммаризация, evaluation и, возможно, обработка длинных промптов. Такой разрез даёт вам полезную изоляцию по ответственности, но не превращает MVP в клубок из пяти сервисов, очередей, сервис-дискавери и инфраструктурных сюрпризов. Это особенно разумно при ограниченном времени и при том, что сдача предполагает единый воспроизводимый репозиторий и простую инструкцию запуска. fileciteturn0file0

Я бы заложил следующую продуктовую схему. Сырые логи складываются в слой ingestion. Дальше идёт нормализация и выделение сущностей: пользователь, команда, источник, временной интервал, длина запроса, дополнительные метаданные. После этого ML-сервис строит первичную категоризацию, сценарии, краткие описания сценариев, а также диагностику “где ломается агент”. Backend записывает результаты анализа в основную БД и отдаёт во frontend как API для дашборда. Такой поток напрямую соответствует case flow “классификация → сценарии → саммари → отчёт”. fileciteturn0file0

Для вашей команды это хорошо ложится на роли. Ты ведёшь основной API и orchestration. ML-щик отвечает за пайплайн классификации, кластеризации, суммаризации и evaluation. Фронтендер собирает веб-дашборд. Четвёртого человека логично посадить не в мобильную разработку, а в инфраструктуру, генерацию датасета, подготовку демо-данных, CI и reproducibility. Это соответствует формату сдачи намного лучше, чем попытка тянуть ещё и мобильный контур, которого организаторы от вас не просят. fileciteturn0file0

Практически я бы предложил такой каркас монорепы:

```text
repo/
  CLAUDE.md
  AGENTS.md
  README.md
  .claude/
    settings.json
    settings.local.example.json
    rules/
      core.md
      backend-api.md
      ml-pipeline.md
      frontend-dashboard.md
      infra-ci.md
      security.md
    agents/
      backend-implementer.md
      ml-researcher.md
      frontend-builder.md
      repo-reviewer.md
      dataset-curator.md
    skills/
      new-feature/
        SKILL.md
      run-eval/
        SKILL.md
      generate-dataset/
        SKILL.md
      demo-report/
        SKILL.md
  apps/
    api/
    web/
  services/
    ml/
  packages/
    contracts/
    shared-domain/
    shared-config/
  data/
    raw/
    processed/
    samples/
  eval/
    gold/
    prompts/
    reports/
  docs/
    architecture/
    decisions/
    taxonomy/
  infra/
    docker/
    compose/
    ci/
  scripts/
```

Если нужен совсем приземлённый выбор стека, то для hackathon-скорости обычно выигрывает либо `NestJS + Python FastAPI ML service`, либо `FastAPI + FastAPI`, если вся команда спокойно живёт в Python. Но архитектурно важнее не язык, а то, чтобы **основной backend оставался единым и модульным**, а ML-контур был вынесен только из-за вычислительной и библиотечной специфики.

## Как оформить репозиторий так, чтобы Claude Code работал на вас

У Claude Code есть несколько официальных механизмов “памяти”. Базовый и самый важный — `CLAUDE.md`: это постоянный контекст, который вы пишете сами. Есть и auto memory, где Claude сохраняет полезные заметки для себя автоматически. Оба механизма подгружаются в начале каждой сессии, но Anthropic отдельно подчёркивает, что это именно контекст, а не жёстко гарантированная конфигурация, поэтому инструкции должны быть конкретными, короткими и хорошо структурированными. Для `CLAUDE.md` они прямо рекомендуют держать файл примерно до 200 строк; если он разрастается, инструкции лучше раскладывать на path-scoped rules в `.claude/rules/`, потому что импортированные через `@path` файлы всё равно попадают в контекст и стоят токены. citeturn13search3turn16search0

Отсюда главный вывод для монорепы: **не пытайтесь запихнуть всё в один гигантский root `CLAUDE.md`**. Для вашей команды оптимальна трёхслойная схема.

Первый слой — корневой `CLAUDE.md`. В нём должны жить только глобальные инварианты проекта: цель продукта, границы MVP, архитектурные принципы, правила naming, обязательные команды проверки, правила по безопасности и формат работы агента. Это тот контекст, который реально должен существовать в каждой сессии. Claude Code каждый раз читает его на старте, и именно он лучше всего переживает длинные сессии и compaction. citeturn13search0turn16search0

Второй слой — `.claude/rules/` с rules по доменам. Официальные docs рекомендуют именно этот каталог для больших проектов: правила можно разбить на отдельные markdown-файлы, а через YAML frontmatter `paths` привязать их к нужным каталогам и типам файлов. Такие path-scoped rules загружаются только когда Claude работает с совпадающими файлами, что сильно экономит контекст и уменьшает шум — ровно то, что нужно для монорепы с backend, ML, frontend и infra в одном дереве. citeturn16search0turn13search2

Третий слой — личные или машинно-специфичные настройки в `.claude/settings.local.json` и пользовательских файлах `~/.claude/...`. Официальная иерархия такая: managed settings выше всего, затем аргументы CLI, потом локальные project settings, затем shared project settings и только потом user settings. При этом массивы, например `permissions.allow` и `permissions.deny`, не заменяются, а объединяются и дедуплицируются. Это удобно: в репозиторий можно коммитить безопасную командную базу, а каждый разработчик локально добавит свои разрешённые команды, MCP или любимые режимы, не ломая командную конфигурацию. citeturn14search0turn14search1

На твой прямой вопрос “корень или подпапки” отвечу так. **Да, Claude Code умеет работать с вложенными `CLAUDE.md`, но в монорепе лучше сделать корневой `CLAUDE.md` основным источником истины, а package-specific контекст переносить в `.claude/rules/` с `paths`.** На это есть практическая причина: официальный memory guide прямо говорит, что root `CLAUDE.md` после `/compact` перечитывается и заново инжектится в сессию, а вложенные `CLAUDE.md` в поддиректориях автоматически не переинжектятся, пока Claude снова не прочитает файл из этой зоны. Значит, критичные правила должны быть в корне, а узкоспециализированные — в scoped rules. citeturn16search0turn13search0

Если вы хотите, чтобы репозиторий одинаково хорошо работал не только с Claude Code, но и с другими агентами, добавьте ещё и `AGENTS.md` в корень. Индустрия реально движется к этому формату: `AGENTS.md` продвигается как открытый общий стандарт, Cursor умеет читать и `AGENTS.md`, и `CLAUDE.md`, а GitHub Copilot coding agent тоже добавил поддержку `AGENTS.md` наряду с `CLAUDE.md`. Но внутри Claude Code всё равно делайте **первичным `CLAUDE.md`**, а `AGENTS.md` держите как совместимый “портируемый слой” для других инструментов. citeturn9search0turn10search1turn9search1

## Как работать с чатами, контекстом и compact без деградации качества

Вот здесь очень многие портят себе жизнь. Claude Code сам умеет компактить контекст, но официальные документы прямо предупреждают: по мере заполнения окна контекста ранние инструкции из диалога могут теряться, а детальные инструкции, которые вы дали только в чате, хуже переживают compaction, чем то, что записано в `CLAUDE.md`. Внутри окна контекста у Claude находятся история разговора, содержимое файлов, вывод команд, `CLAUDE.md`, auto memory, skills и system instructions; когда места становится мало, Claude сначала чистит старый tool output, а потом суммаризирует разговор. Для контроля есть `/context`, а для ручного прицельного сжатия — `/compact` с фокусом, например на изменениях API. citeturn13search0turn13search2

Поэтому рабочее правило простое. **Одна сессия — один workstream**. Не “одна сессия на весь хакатон” и не “новая сессия каждые 10 минут”. Если ты делаешь ingestion API, живи в одной сессии, пока не дошёл до понятной границы: модуль готов, API стабилизирован, тесты зелёные. Если переключаешься с backend на исследование ML-кластеризации или на совершенно другой баг, лучше делать новую сессию или хотя бы `/clear`. Официальный help center прямо пишет, что `/clear` — самый сильный рычаг для качества и стоимости, когда вы переключаетесь на другую задачу, а `/compact` нужен когда вы остаетесь внутри той же задачи и хотите сохранить суть, но освободить место. citeturn12search9turn12search3

Если сессию пришлось оборвать, не нужно “пересказывать всё заново”. Для этого у Claude Code есть `--continue` и `--resume`, которые позволяют продолжать последнюю или конкретную сессию. Это полезно и для обычной работы в терминале, и особенно для автоматизации через SDK или CI-скрипты. citeturn2search3turn2search1

На практике я бы установил такой режим работы для вашей команды. Глобальные правила всегда живут в файлах. В чат передаются только “плавающие” цели конкретной подзадачи. Когда работаешь над одной фичей долго и видишь, что контекст разросся, запускаешь не просто `/compact`, а **осмысленный `/compact` с фокусом**, например: сохранить текущую цель, изменённые файлы, принятые архитектурные решения и открытые вопросы. Anthropic официально поддерживает такой режим: и через `Compact Instructions` в `CLAUDE.md`, и через аргумент самого `/compact`. citeturn13search0turn16search0

Для сложных задач лучше не бросать агента сразу в код. В гайде по common workflows Anthropic рекомендует сначала дать задачу, позволить Claude собрать контекст проекта, а потом явно попросить “think” глубже уже на основе найденного контекста. В вашем случае это очень хорошо работает для дизайна пайплайна классификации, ревью схемы БД, декомпозиции по модулям и крупных рефакторингов. Если хочешь ещё жёстче дисциплинировать сессию, запускай её в permission mode `plan`, где Claude может анализировать, но не писать файлы и не гонять команды. citeturn11search9turn5search3turn4search4

## Subagents, skills, hooks и MCP для вашей команды

Самое сильное в современном Claude Code — не один большой чат, а то, что вы можете вынести разные типы работы в разные механизмы.

**Subagents** полезны тогда, когда хочется изолировать контекст. Официальные docs прямо говорят: subagent получает собственное свежее окно контекста, его промежуточная работа не раздувает main conversation, а назад он возвращает только summary. Это идеальный инструмент для длинных исследовательских задач, codebase exploration, ML-поиска по ноутбукам, ревью фронта или механического поиска регрессий. Для вашего репозитория я бы завёл как минимум пять custom subagents: `backend-implementer`, `ml-researcher`, `frontend-builder`, `repo-reviewer`, `dataset-curator`. citeturn15search0turn15search1

**Skills** нужны не для постоянных правил, а для on-demand знаний и повторяемых workflows. Anthropic описывает их как reusable knowledge и invocable workflows: skill можно вызывать вручную через slash-команду, а Claude может подгружать её автоматически, если она релевантна. Важно другое: для навыков с побочными эффектами вроде deploy, массового сидирования, очистки данных или отправки уведомлений надо ставить `disable-model-invocation: true`, чтобы skill запускалась только по вашему явному вызову, а не потому, что агент “решил, что так уже пора”. Для сложных skills рекомендуют держать `SKILL.md` коротким, а детальные reference-файлы выносить рядом, чтобы не тащить лишний токенный хвост в каждую загрузку. citeturn17search1turn17search4turn15search1

**Hooks** — это способ автоматизировать дисциплину разработки. Официально это shell-команды, HTTP-endpoints, LLM-prompts, subagents или MCP tool hooks, которые срабатывают в lifecycle Claude Code на событиях вроде `SessionStart`, `PreToolUse`, `PostToolUse`, `PermissionRequest` и так далее. Но тут есть серьёзное предупреждение из docs: command hooks запускаются с полными правами текущего системного пользователя. Поэтому hooks у вас должны быть не “магией”, а маленькими прозрачными скриптами, которые легко аудировать. Для хакатона уместны такие hooks: на `SessionStart` подгружать статус проекта и TODO; на `PostToolUse` после записи в backend гонять быстрый lint или unit subset; через `InstructionsLoaded` логировать, какие rules реально подгрузились; через `PreToolUse` блочить чтение секретов или опасные операции. citeturn13search1turn14search0

**MCP** я бы сразу закладывал как расширяемый слой, даже если на MVP вы его почти не используете. Anthropic описывает MCP как открытый протокол для подключения внешних инструментов и источников данных. Важный для контекста нюанс: полные схемы MCP tools откладываются и подгружаются по требованию, так что простаивающие MCP-серверы почти не засоряют контекст, пока агент не начнёт реально использовать конкретный инструмент. Для вас это означает, что можно спокойно проектировать будущие интеграции с GitHub, Jira, Postgres, Sentry или аналитикой, не боясь, что весь список инструментов съест половину окна контекста ещё до старта. citeturn3search5turn13search0

Для автоматизации вне интерактива Claude Code поддерживает SDK и неинтерактивный режим `-p`. Там критично использовать `--output-format json`, `--max-turns`, таймауты и обработку ошибок, а также хранить секреты как env или GitHub Secrets, а не в репозитории. Это вам пригодится, если захотите сделать автоматический nightly summary, batch evaluation или pre-demo генерацию отчёта. citeturn2search1turn6search4

## Какие файлы я бы создал в первый же вечер

Ниже не “единственно правильная истина”, а шаблон, который хорошо согласуется с тем, как Claude Code официально работает с памятью, scoped rules, settings, skills и subagents. citeturn16search0turn14search0turn15search0turn15search1

### Корневой CLAUDE.md

```md
# Prompt Radar

## Product goal
- Build an analytics tool for prompts to AI agents.
- Output must explain what users ask, what scenarios exist, what grows, and where the agent fails.
- MVP priority: reproducible pipeline + understandable dashboard + demo data.

## Architecture invariants
- Main backend is a modular monolith.
- ML logic lives in a separate ML service.
- Do not introduce more services unless there is a hard technical reason.
- Shared contracts live in packages/contracts.
- Shared domain vocabulary lives in packages/shared-domain.

## Working rules
- Before writing new code, search for existing implementation patterns.
- For complex changes, first propose a plan, then implement.
- Keep patches small and reviewable.
- Prefer changing existing files over creating new abstractions.
- After meaningful edits, run the smallest relevant verification command first.

## Quality gates
- Backend changes must pass unit tests and lint.
- Frontend changes must pass build or typecheck.
- ML pipeline changes must produce a reproducible analysis run.

## Safety
- Never read or print secrets from .env or secrets directories.
- Never edit deployment or infra files unless explicitly asked.
- Never rewrite large generated datasets in place without confirmation.

## Compact Instructions
- When compacting, preserve: current goal, modified files, accepted architecture decisions, open issues, and next step.
- Drop: verbose command output, already resolved errors, and long file dumps.
```

Корневой файл должен быть коротким и действительно глобальным. Это именно тот тип инструкций, который Anthropic рекомендует хранить в `CLAUDE.md`: вещи, которые вы иначе повторяли бы из сессии в сессию. citeturn16search0

### Scoped rules для монорепы

`/.claude/rules/backend-api.md`

```md
---
paths:
  - "apps/api/**"
  - "packages/contracts/**"
  - "packages/shared-domain/**"
---

# Backend API rules

- Use existing domain modules before creating new top-level folders.
- Keep controllers thin, business logic in services/use-cases.
- Do not put ML-specific logic in the main API unless it is orchestration only.
- Any new endpoint must declare response DTO / schema.
- Prefer idempotent analysis-run endpoints.
```

`/.claude/rules/ml-pipeline.md`

```md
---
paths:
  - "services/ml/**"
  - "eval/**"
  - "data/**"
---

# ML pipeline rules

- Keep training, offline evaluation, and inference code separated.
- Every experiment that affects output labels must write a run artifact.
- Prefer deterministic preprocessing for demo reproducibility.
- Long prompts should be chunked or summarized before expensive downstream steps.
- Store taxonomy and label definitions as versioned assets.
```

`/.claude/rules/frontend-dashboard.md`

```md
---
paths:
  - "apps/web/**"
---

# Frontend dashboard rules

- Optimize for readability for a CTO audience.
- Every chart should answer a decision question, not just show a metric.
- Prefer top categories, top scenarios, trends, failures, and examples.
- Avoid over-designed interactions that slow down demo readiness.
```

Scoped rules — это лучший ответ на ваш вопрос “как сделать, чтобы Claude читал нужный контекст тогда, когда ему это нужно”. Именно для этого они и созданы: загружаться только при работе с совпадающими файлами и не раздувать каждый сеанс лишними инструкциями. citeturn16search0turn13search2

### Shared settings

`/.claude/settings.json`

```json
{
  "$schema": "https://json.schemastore.org/claude-code-settings.json",
  "permissions": {
    "allow": [
      "Bash(pnpm test *)",
      "Bash(pnpm lint *)",
      "Bash(pnpm build *)",
      "Bash(pytest *)",
      "Bash(ruff check *)",
      "Bash(uv run *)"
    ],
    "deny": [
      "Read(./.env)",
      "Read(./.env.*)",
      "Read(./secrets/**)",
      "Bash(rm -rf *)",
      "Bash(git push *)"
    ],
    "defaultMode": "default"
  }
}
```

Командная мысль здесь такая: в общий репозиторный settings кладёте только безопасное и воспроизводимое. Всё персонально спорное, например более агрессивные режимы, личные MCP и экспериментальные hooks, держите в `.claude/settings.local.json`. Это полностью соответствует официальной модели user/project/local settings и правилам слияния permission arrays. citeturn14search0turn14search1

### Subagent под backend

`/.claude/agents/backend-implementer.md`

```md
---
name: backend-implementer
description: Use proactively for backend API, orchestration, contracts, and modular-monolith changes
tools:
  - Read
  - Edit
  - Write
  - Bash
  - Grep
  - Glob
  - LS
model: sonnet
permissionMode: default
skills:
  - new-feature
  - run-eval
---

You are a senior backend engineer for the Prompt Radar project.

Focus on:
- modular monolith boundaries
- API contracts
- analysis run orchestration
- testability
- minimal surface area changes

Do not:
- move ML logic into the main API
- invent new infra for small problems
- bypass shared contracts
```

### Skill под повторяемую команду

`/.claude/skills/run-eval/SKILL.md`

```md
---
name: run-eval
description: Run offline evaluation for the current analysis pipeline and summarize regressions
disable-model-invocation: true
---

Run the evaluation workflow for the current branch.

Steps:
1. Find the evaluation entry point in eval/ or services/ml/.
2. Run the smallest reproducible evaluation command.
3. Compare current metrics with the latest baseline artifact.
4. Summarize what improved, what regressed, and what looks suspicious.
5. Do not modify baseline artifacts unless explicitly requested.
```

Здесь важно именно `disable-model-invocation: true`. Для evaluation, deploy, data regeneration и любых side-effect действий я бы делал только ручной запуск. Anthropic это отдельно рекомендуют для skills, которые вы не хотите отдавать на автоматическое усмотрение модели. citeturn17search1turn17search2

### Совместимость с другими агентами

`/AGENTS.md`

```md
# Agent instructions

## Project
Prompt Radar for analytics of prompts to enterprise AI agents.

## Architecture
- Main backend: modular monolith
- Separate ML service for embeddings, clustering, summarization, evaluation
- Frontend dashboard for managers and analysts

## Commands
- Web: pnpm --filter web dev
- API: pnpm --filter api dev
- ML: uv run python -m services.ml.main
- Tests: pnpm test / pytest
- Lint: pnpm lint / ruff check

## Boundaries
- Do not read secrets
- Prefer existing patterns before adding new abstractions
- Keep changes small and testable
```

Это пригодится, если кто-то из команды параллельно начнёт работать из Cursor или через другой агентный инструмент. citeturn9search0turn10search1turn10search4

## Как именно формулировать запросы Claude Code

Самая полезная практика здесь не “магический суперпромпт”, а хороший **task envelope**. Для Claude 4 Anthropic рекомендует быть максимально явным: чётко описывать ожидаемое поведение, давать контекст, объяснять, почему это важно, и приводить примеры нужного результата. Они отдельно отмечают, что модели лучше реагируют на формулировки “что нужно сделать”, чем на длинные списки “чего нельзя делать”, и что формат вашего запроса влияет на формат ответа. citeturn8search3turn8search5

Для ваших задач я бы использовал такой шаблон запроса почти всегда:

```text
Задача:
Нужно реализовать [конкретная цель].

Контекст:
Работаем в Prompt Radar.
Трогаем только [папки/модули].
Не меняем [что нельзя трогать].

Критерии готовности:
- ...
- ...
- ...

Сначала:
1. Найди существующие паттерны в коде.
2. Коротко предложи план.
3. Реализуй минимальными изменениями.
4. Запусти только релевантные проверки.
5. Покажи итог: какие файлы изменены, что сделано, что осталось.
```

Такой шаблон хорош по двум причинам. Во-первых, он совпадает с рекомендацией Anthropic сначала давать задачу и контекст, а затем просить модель углубиться в планирование. Во-вторых, он резко снижает склонность агента “сразу писать что-нибудь”, не посмотрев на существующие паттерны проекта. citeturn11search9turn8search3

Для сложных кусков, например проектирования анализа сценариев или выбора схемы хранения, лучше делать двухходовку. Сначала: “исследуй и предложи 2–3 варианта без изменения файлов”. Потом, после выбора: “реализуй вариант B”. Это держит сессию чище и экономит токены на ненужных переписываниях.

А вот чего бы я не делал: не строил бы гигантский “скрытый system prompt”. Claude Code официально пишет, что внутренний system prompt не публикуется, а поддерживаемые способы кастомизации — это `CLAUDE.md` и флаг `--append-system-prompt`. Причём `--append-system-prompt` разумнее применять в скриптах и automation, а не в повседневной интерактивной работе. Для команды вашими главными рычагами должны быть `CLAUDE.md`, scoped rules, skills и subagents. citeturn14search0turn2search1turn16search4

## Что я бы считал хорошим процессом команды на хакатоне

Нормальная схема на ваш состав такая.

Ты работаешь в ветке backend и держишь одну основную сессию Claude Code на один bounded workstream: ingestion API, analysis-run orchestration или reporting API. Когда задача меняется радикально, делаешь новую сессию. Когда сессия длинная, но цель та же — `/compact` с фокусом. Когда нужен чистый лист — `/clear`. Всё постоянное выносишь из чата в `CLAUDE.md` и rules сразу после того, как заметил повторяющуюся коррекцию. citeturn12search9turn12search3turn16search0

ML-инженер ведёт свою часть либо в отдельной директории `services/ml`, либо в subagent-oriented workflow. Для него важно, чтобы taxonomy, эвалы и артефакты анализов были versioned и не жили только внутри чата. С точки зрения Claude Code это ровно тот случай, где отдельный subagent или хотя бы отдельная сессия спасают основной контекст от бесконечного research trail. citeturn15search0turn15search1

Фронтендеру даёте свой scoped rule на `apps/web/**`, где акцент на менеджерский UX: какие сценарии чаще, какие растут, что ломается, какие примеры и решения видны руководителю. Это полностью соответствует критерию кейса “понятность результата для CTO” и не даёт агенту уходить в декоративный frontend ради самого frontend-а. fileciteturn0file0

Четвёртого человека лучше сразу сделать владельцем reproducibility. Его зона — `docker compose`, фиксированные команды запуска, demo dataset, baseline eval, one-click demo script и CI. Anthropic SDK и GitHub Actions позволяют запускать Claude Code в неинтерактивном режиме с `--max-turns`, JSON output и ограничениями по tools, если вы захотите автоматизировать часть рутины. Но даже без этого сам репозиторий должен быть собран так, чтобы его можно было поднять одной понятной командой. citeturn2search1turn6search4 fileciteturn0file0

Мой финальный совет совсем короткий. **Не стройте “большой общий чат про всё”. Стройте репозиторий, в котором знание разложено по слоям: глобальные правила в root `CLAUDE.md`, scoped-правила в `.claude/rules/`, повторяемые действия в skills, длинные исследовательские работы в subagents, безопасность и checked automation в settings и hooks.** Именно такая структура лучше всего совпадает и с официальной моделью Claude Code, и с вашей реальной задачей на хакатоне. citeturn16search0turn13search0turn15search1turn13search1