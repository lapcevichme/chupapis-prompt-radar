"""Fixtures for live (non-mock) integration tests.

Backends:
  LIVE_BACKEND=ollama (default) — local Ollama embeddings
  LIVE_BACKEND=openrouter — OpenRouter embeddings + LLM

Run:
  pytest tests/live -m live -v
  $env:LIVE_BACKEND='openrouter'; pytest tests/live -m live -k openrouter -v
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

_ML_ROOT = Path(__file__).resolve().parents[2]
_CBM = _ML_ROOT / "app" / "models" / "catboost_task_classifier.cbm"
_BACKEND = (os.environ.get("LIVE_BACKEND") or "ollama").strip().lower()

# Load .env for OPENROUTER_API_KEY without printing
_env_file = _ML_ROOT / ".env"
if _env_file.is_file():
    try:
        from dotenv import load_dotenv

        load_dotenv(_env_file, override=False)
    except ImportError:
        pass

os.environ["ALLOW_INMEMORY_STORE"] = "true"
os.environ["ML_META_DB_URL"] = "sqlite:///:memory:"
os.environ["ML_SERVICE_TOKEN"] = ""
os.environ["INGEST_WORKER_CONCURRENCY"] = "2"
os.environ.setdefault("OLLAMA_AUTO_PULL", "false")
os.environ["CLASSIFIER_FALLBACK_MODE"] = "fail_fast"
os.environ["CLASSIFIER_CONFIDENCE_THRESHOLD"] = os.environ.get(
    "CLASSIFIER_CONFIDENCE_THRESHOLD", "0.25"
)
if _CBM.is_file():
    os.environ["CLASSIFIER_MODEL_PATH"] = str(_CBM)

if _BACKEND in ("openrouter", "online", "cloud"):
    os.environ["LIVE_BACKEND"] = "openrouter"
    os.environ["ML_MODE"] = "online"
    os.environ["EMBEDDINGS_MODE"] = "online"
    os.environ["EMBEDDINGS_PROVIDER"] = "openrouter"
    os.environ["LLM_MODE"] = "online"
    os.environ["LLM_PROVIDER"] = "openrouter"
    os.environ["OPENROUTER_MODEL"] = os.environ.get(
        "OPENROUTER_MODEL", "qwen/qwen3-embedding-4b"
    )
    os.environ["OPENROUTER_CHAT_MODEL"] = os.environ.get(
        "OPENROUTER_CHAT_MODEL", "google/gemma-4-26b-a4b-it"
    )
    os.environ["OPENROUTER_EMBEDDINGS_URL"] = os.environ.get(
        "OPENROUTER_EMBEDDINGS_URL", "https://openrouter.ai/api/v1/embeddings"
    )
    os.environ["OPENROUTER_CHAT_URL"] = os.environ.get(
        "OPENROUTER_CHAT_URL", "https://openrouter.ai/api/v1/chat/completions"
    )
else:
    os.environ["LIVE_BACKEND"] = "ollama"
    os.environ["ML_MODE"] = "offline"
    os.environ["EMBEDDINGS_MODE"] = "offline"
    os.environ["EMBEDDINGS_PROVIDER"] = "ollama"
    os.environ["LLM_MODE"] = os.environ.get("LLM_MODE", "offline")
    os.environ["OLLAMA_URL"] = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
    os.environ["OLLAMA_MODEL"] = os.environ.get("OLLAMA_MODEL", "qwen3-embedding:4b")
    os.environ["OLLAMA_LLM_MODEL"] = os.environ.get(
        "OLLAMA_LLM_MODEL", "gemma4:26b-a4b-it"
    )


def _purge_app_modules() -> None:
    for k in list(sys.modules):
        if k == "app" or k.startswith("app."):
            del sys.modules[k]


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(scope="module")
def live_backend() -> str:
    return os.environ.get("LIVE_BACKEND", "ollama")


@pytest.fixture(scope="module")
def live_settings(live_backend):
    _purge_app_modules()
    from app.core import config as config_mod
    from app.core.config import load_settings

    config_mod.settings = load_settings()
    return config_mod.settings


@pytest.fixture(scope="module")
def ollama_base(live_settings) -> str:
    return (live_settings.embeddings.ollama_url or "http://127.0.0.1:11434").rstrip("/")


@pytest.fixture(scope="module")
def ollama_available(ollama_base, live_backend) -> bool:
    if live_backend == "openrouter":
        return False
    from app.core.ollama_bootstrap import list_local_models

    async def _check() -> bool:
        try:
            await list_local_models(ollama_base, timeout_sec=5.0)
            return True
        except Exception:
            return False

    return _run(_check())


@pytest.fixture(scope="module")
def require_ollama(ollama_available, live_backend):
    if live_backend == "openrouter":
        pytest.skip("Ollama not used for LIVE_BACKEND=openrouter")
    if not ollama_available:
        pytest.skip("Ollama not reachable at local URL")


@pytest.fixture(scope="module")
def require_openrouter(live_backend):
    if live_backend != "openrouter":
        pytest.skip("Set LIVE_BACKEND=openrouter")
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        pytest.skip("OPENROUTER_API_KEY not set")
    return key


@pytest.fixture(scope="module")
def require_embedding_model(live_backend, live_settings, ollama_base, request):
    if live_backend == "openrouter":
        request.getfixturevalue("require_openrouter")
        return live_settings.embeddings.openrouter_model

    request.getfixturevalue("require_ollama")
    from app.core.ollama_bootstrap import ensure_ollama_models

    model = live_settings.embeddings.ollama_model
    auto = os.environ.get("OLLAMA_AUTO_PULL", "false").lower() in ("1", "true", "yes")

    async def _ensure():
        return await ensure_ollama_models(
            ollama_base,
            [model],
            auto_pull=auto,
            pull_timeout_sec=600,
        )

    report = _run(_ensure())
    status = (report.get("models") or {}).get(model)
    if status not in ("present", "pulled"):
        pytest.skip(f"Embedding model not available: {model} ({status})")
    return model


@pytest.fixture(scope="module")
def require_cbm():
    if not _CBM.is_file():
        pytest.skip(f"CatBoost model missing: {_CBM}")
    return str(_CBM)


@pytest.fixture(scope="module")
def live_client(live_backend, require_embedding_model, live_settings):
    """FastAPI TestClient with real embeddings (Ollama or OpenRouter)."""
    _purge_app_modules()
    from app.core import config as config_mod
    from app.core.config import load_settings

    config_mod.settings = load_settings()
    from app.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        yield client
