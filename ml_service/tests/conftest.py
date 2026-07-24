"""Shared test env: offline vector store + in-memory meta DB."""
from __future__ import annotations

import os

# Must run before app.main / QdrantStore imports in other test modules.
os.environ.setdefault("ALLOW_INMEMORY_STORE", "true")
os.environ.setdefault("EMBEDDINGS_PROVIDER", "mock")
os.environ.setdefault("ML_META_DB_URL", "sqlite:///:memory:")
os.environ.setdefault("ML_SERVICE_TOKEN", "")
os.environ.setdefault("INGEST_WORKER_CONCURRENCY", "4")
