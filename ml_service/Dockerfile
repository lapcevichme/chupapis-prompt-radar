# Prompt Radar ML service (ТЗ §14)
FROM python:3.11-slim

WORKDIR /app

# Native build deps for hdbscan / umap-learn wheels fallback
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps from pyproject (reproducible pins via package metadata)
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
        "qdrant-client>=1.9.0"

COPY config.yaml ./
COPY app ./app
COPY scripts ./scripts

# Paths used by classifier + meta store inside the container
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    CLASSIFIER_MODEL_PATH=/app/app/models/catboost_task_classifier.cbm \
    CLASSIFIER_CONFIDENCE_THRESHOLD=0.30 \
    ML_CONFIG_PATH=/app/config.yaml \
    EMBEDDINGS_PROVIDER=mock \
    EMBEDDINGS_DIM=2560 \
    ALLOW_INMEMORY_STORE=false \
    QDRANT_REQUIRED=true \
    QDRANT_URL=http://qdrant:6333 \
    QDRANT_COLLECTION=prompt_radar_vectors \
    ML_META_DB_URL=sqlite:////data/ml/meta.db \
    LOG_LEVEL=INFO

RUN mkdir -p /data/ml

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health/live || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
