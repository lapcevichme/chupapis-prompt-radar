# Prompt Radar ML service (ТЗ §14)
FROM python:3.11-slim

WORKDIR /app

# Native build deps for hdbscan / umap-learn wheels fallback
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Runtime deps, mirroring pyproject minus the test-only ones. Keep the two lists
# in sync. The numba floor is redundant for pip today (it backtracks numpy on its
# own) but states the constraint outright: numba caps the numpy it supports, and
# uv's resolver answered the same unbounded spec with numba 0.53.1 (2021), which
# does not build. Pinned so the answer no longer depends on which resolver runs.
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir \
        "aiohttp>=3.9.0" \
        "python-dotenv>=1.0.0" \
        "pydantic>=2.0.0" \
        "fastapi>=0.110.0" \
        "uvicorn[standard]>=0.27.0" \
        "httpx>=0.27.0" \
        "numpy>=1.26.0" \
        "scikit-learn>=1.5.0" \
        "catboost>=1.2.0" \
        "umap-learn>=0.5.6" \
        "hdbscan>=0.8.40" \
        "numba>=0.60" \
        "qdrant-client>=1.9.0" \
        "pyyaml>=6.0.0" \
        "jsonschema>=4.22.0" \
        "langchain-openrouter>=0.2.0" \
        "langchain-ollama>=0.3.0" \
        "langchain-core>=0.3.0"

COPY config.yaml ./
COPY app ./app
COPY scripts ./scripts

# Paths used by classifier + meta store inside the container
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    CLASSIFIER_MODEL_PATH=/app/app/models/catboost_task_classifier.cbm \
    CLASSIFIER_CONFIDENCE_THRESHOLD=0.30 \
    ML_CONFIG_PATH=/app/config.yaml \
    ML_MODE=mock \
    EMBEDDINGS_DIM=2560 \
    ALLOW_INMEMORY_STORE=false \
    QDRANT_REQUIRED=true \
    QDRANT_URL=http://qdrant:6333 \
    ML_META_DB_URL=sqlite:////data/ml/meta.db \
    LOG_LEVEL=INFO

RUN mkdir -p /data/ml

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health/live || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
