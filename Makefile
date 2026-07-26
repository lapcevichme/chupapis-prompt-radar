.PHONY: up down down-clean logs ps build restart feed demo test lint ml-test ml-lint frontend-test frontend-check

COMPOSE := docker compose
INGEST_TOKEN ?= dev-ingest-token
BACKEND_URL ?= http://localhost:8080

up:            ## build + start the whole stack and wait for service healthchecks
	$(COMPOSE) up -d --build --wait --wait-timeout 240

down:          ## stop everything (keeps volumes)
	$(COMPOSE) down

down-clean:    ## stop everything and drop volumes (fresh state)
	$(COMPOSE) down -v

logs:          ## tail all logs
	$(COMPOSE) logs -f --tail=200

ps:            ## show service status
	$(COMPOSE) ps

build:         ## build images without starting
	$(COMPOSE) build

restart:       ## recreate backend only (after code change)
	$(COMPOSE) up -d --build backend

feed:          ## stream live demo requests to the running backend
	python tools/feed_live.py --url $(BACKEND_URL) --token $(INGEST_TOKEN) --count 30 --interval 0.5

demo: up       ## mutating API smoke: adds a demo source, recomputes, checks dashboard/ROI/export
	python tools/demo.py --url $(BACKEND_URL)

test:          ## run backend unit + API tests
	cd backend && poetry run pytest -q

lint:          ## ruff check backend
	cd backend && poetry run ruff check src tests

ml-test:       ## run ML unit tests (uv sync first; skips live provider tests)
	cd ml_service && uv sync --quiet && uv run pytest tests/ -q

ml-lint:       ## ruff check ml_service
	cd ml_service && uv sync --quiet && uv run ruff check app tests scripts

frontend-test: ## run frontend unit/integration tests
	cd frontend && npm test

frontend-check: ## run all frontend checks
	cd frontend && npm run lint && npm test && npm run build
