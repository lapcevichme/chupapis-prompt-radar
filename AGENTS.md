# Prompt Radar: инструкции для агентов

Этот файл действует на весь репозиторий. Он хранит переносимый контекст для Codex и других
инженерных агентов. Подробная карта реализации находится в `docs/CODEBASE_MAP.md`.

## Что это за проект

Prompt Radar превращает поток запросов к корпоративным ИИ-агентам в аналитику для CTO:
классификация запросов, группировка в сценарии, саммари, поиск нетипичных запросов и расчёт
ROI/FTE. Главная продуктовая ценность — объяснить, как сотрудники используют ИИ и где он даёт
измеримую экономию.

## Что читать перед изменениями

1. Этот файл и `docs/CODEBASE_MAP.md`.
2. Релевантный контракт в `docs/contracts/`.
3. Для backend — `docs/backend/BACKEND_TASK.md`; для ML — `ml_service/ТЗ.md` и
   `docs/taxonomy/taxonomy_v1.md`.
4. Реальный код и тесты затронутого компонента.

При расхождении доверяй в таком порядке: исполняемый код и тесты → JSON Schema/OpenAPI и
контракты → актуальная карта `docs/CODEBASE_MAP.md` → README/исторические планы. `TASKS.md`,
`.claude/`, `docs/decisions/` и `template/` могут присутствовать локально, но исключены из Git;
не делай их единственным источником важного решения.

## Архитектурные инварианты

- Монорепозиторий состоит из `backend/`, `ml_service/` и `frontend/`; общие границы описаны в
  `docs/contracts/`.
- Backend — модульный монолит FastAPI: тонкие `api/v1` → `service` → `domain` → асинхронный
  SQLAlchemy/Alembic в `database`.
- Backend владеет пользователями, ingestion-источниками, сырыми ROI-полями и расчётом ROI.
- ML владеет аналитическим контуром: эмбеддингами, классификацией, кластерами, сценариями,
  Qdrant и лёгкой meta-БД.
- Backend и ML не импортируют код друг друга. Интеграция идёт только по HTTP-контракту.
- Frontend обращается только к backend REST и всегда использует cookie credentials; напрямую к
  ML он не ходит.
- Основной поток — streaming CQRS: `PUT /api/v1/logs` в ML для записи,
  `POST /api/v1/recompute` для тяжёлого пересчёта, быстрые `GET /statistics`, `/scenarios` и
  `/assignments` для чтения.
- `unknown` — низкая уверенность классификации, а `other` — только агрегированный хвост.
  HDBSCAN-outlier означает нетипичный запрос, а не ошибку агента.
- Изменение структуры `/statistics` требует обновления схемы и `schema_version`; изменение
  классов — `taxonomy_version`; ломающий backend↔frontend API должен перейти на новую API-версию.

## Правила изменения кода

- Сначала найди существующий паттерн рядом с изменяемым кодом. Не создавай новый слой или сервис
  без необходимости.
- При изменении endpoint обновляй соответствующий контракт, Pydantic/TypeScript-типы и тесты в
  том же изменении.
- Не переноси ML-логику в backend и не переноси ROI в ML.
- Не вызывай модели на read-path `/statistics`: он должен читать готовую read-модель.
- Не обрезай длинные запросы молча; сохраняй выбранную стратегию обработки в метаданных.
- Не обучай фиктивный CatBoost на маленьком синтетическом наборе в production-path.
- Не редактируй и не запускай `template/`: это локальный исторический референс, а не приложение.
- Не читай и не печатай `.env`, ключи или реальные пользовательские промпты. Не перезаписывай
  большие датасеты без явного запроса.
- Сохраняй чужие изменения в рабочем дереве. Коммиты, если они нужны, делай небольшими и в формате
  Conventional Commits, добавляя только относящиеся к задаче файлы.

## Команды

Из корня:

```bash
make up                 # frontend + backend + Postgres + Qdrant + ML
make demo               # полный demo-flow через backend
make feed               # поток live-логов
make test               # backend tests
make lint               # backend Ruff
make frontend-check     # frontend lint + tests + build
docker compose down     # остановка с сохранением volumes
```

По компонентам:

```bash
cd backend && poetry run pytest -q
cd backend && poetry run ruff check src tests

cd ml_service && uv sync
cd ml_service && uv run pytest -q

cd frontend && npm ci
cd frontend && npm run lint
cd frontend && npm test
cd frontend && npm run build
cd frontend && npm run dev
```

Не запускай `make down-clean` без явного намерения удалить локальные volumes. Корневой Compose
поднимает production-сборку frontend через nginx на порту 3000; `/api` проксируется в backend.
Для разработки Vite можно запускать отдельно той же командой `npm run dev`.

## Минимальная проверка

- Backend: релевантные тесты, затем Ruff; при изменении API также проверь OpenAPI/contract tests.
- ML: релевантные unit/contract/smoke-тесты с mock embeddings; сетевой LLM не нужен для тестов.
- Frontend: `npm run lint`, `npm test` и `npm run build`.
- Интеграция/infra: health endpoints и `tools/demo.py` либо `make demo`.
- Если зависимостей или сервисов нет, не выдавай проверку за успешную — явно зафиксируй предел.

## Осознанные ограничения MVP

- Фоновая обработка и статус последнего recompute живут в одном процессе; брокера задач нет.
- Качество mock embeddings ниже реального режима OpenRouter/Ollama.
- Онлайн-центроиды ML пока не восстанавливаются из meta-store после рестарта.
- Backend кэширует read-модель `/statistics` в памяти с TTL и инвалидирует её после ingestion и
  recompute.
- Lock-файлы и документация местами исторически рассинхронизированы; перед утверждением текущего
  статуса проверяй код, тесты и `git status`.
