# Prompt Radar ML service — local demo / test targets
# Run from ml_service/: make ml-up | ml-test | demo

COMPOSE ?= docker compose
COMPOSE_FILE ?= docker-compose.yml
ML_URL ?= http://localhost:8000
PYTHON ?= python
SEED_SCRIPT ?= scripts/seed_demo.py
# In-tree copy, byte-identical to backend/src/data/prompt_radar_dataset.json.
# (Was ../notebooks/…, a directory that no longer exists — seed/demo both died on it.)
DATASET ?= catboost/prompt_radar_dataset.json

.PHONY: help ml-up ml-down ml-logs ml-test ml-test-live demo seed smoke lint

help:
	@echo "Targets:"
	@echo "  ml-up    - build & start ml-service + qdrant"
	@echo "  ml-down  - stop stack"
	@echo "  ml-logs  - follow ml-service logs"
	@echo "  ml-test  - unit + smoke (mock embeddings; skips live)"
	@echo "  ml-test-live - real Ollama + CatBoost (no mocks)"
	@echo "  smoke    - pytest smoke only"
	@echo "  seed     - POST demo log batches to running ML"
	@echo "  demo     - ml-up, wait ready, seed, recompute, print statistics"
	@echo "  lint     - ruff check (if installed)"

ml-up:
	$(COMPOSE) -f $(COMPOSE_FILE) up -d --build

ml-down:
	$(COMPOSE) -f $(COMPOSE_FILE) down

ml-logs:
	$(COMPOSE) -f $(COMPOSE_FILE) logs -f ml-service

ml-test:
	$(PYTHON) -m pytest tests/ -q --tb=short

# Real Ollama embeddings + .cbm (requires ollama serve + qwen3-embedding:4b)
ml-test-live:
	$(PYTHON) -m pytest tests/live -m live -v --tb=short

# Real OpenRouter embeddings + LLM (requires OPENROUTER_API_KEY in env/.env)
ml-test-openrouter:
	LIVE_BACKEND=openrouter $(PYTHON) -m pytest tests/live/test_openrouter_real.py -m live -v --tb=short

smoke:
	$(PYTHON) -m pytest tests/test_smoke.py -q --tb=short

seed:
	$(PYTHON) $(SEED_SCRIPT) --url $(ML_URL) --dataset $(DATASET)

# Full local demo without requiring a real OPENROUTER_API_KEY
demo: ml-up
	@echo "Waiting for ML readiness..."
	@i=0; \
	until curl -fsS $(ML_URL)/health/ready >/dev/null 2>&1; do \
	  i=$$((i+1)); \
	  if [ $$i -gt 60 ]; then echo "ML not ready"; exit 1; fi; \
	  sleep 2; \
	done
	$(PYTHON) $(SEED_SCRIPT) --url $(ML_URL) --dataset $(DATASET) --recompute
	@echo "--- /api/v1/statistics ---"
	@curl -fsS $(ML_URL)/api/v1/statistics | $(PYTHON) -m json.tool | head -n 80

lint:
	@command -v ruff >/dev/null 2>&1 && ruff check app tests scripts || echo "ruff not installed; skip"
