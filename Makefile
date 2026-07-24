.PHONY: up down down-clean logs ps build restart feed demo test lint

COMPOSE := docker compose
INGEST_TOKEN ?= dev-ingest-token
BACKEND_URL ?= http://localhost:8080

up:            ## build + start the whole stack (backend + ml + qdrant + db)
	$(COMPOSE) up -d --build

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

demo: up       ## bring the stack up and run the end-to-end demo (ingest -> dashboard -> ROI -> export)
	python tools/demo.py --url $(BACKEND_URL)

test:          ## run backend unit + API tests
	cd backend && poetry run pytest -q

lint:          ## ruff check backend
	cd backend && poetry run ruff check src tests
