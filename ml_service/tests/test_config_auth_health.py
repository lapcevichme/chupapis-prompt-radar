"""PR A: config load, auth, readiness (ТЗ §4, §7, §10)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app.core.config import load_settings, resolve_config_path
from app.core.exceptions import (
    EMBEDDING_PROVIDER_UNAVAILABLE,
    INVALID_REQUEST,
    MLServiceError,
    error_response,
)


def test_resolve_config_path_finds_repo_yaml():
    path = resolve_config_path()
    assert path is not None
    assert path.name == "config.yaml"
    assert path.is_file()


def test_load_settings_from_yaml(tmp_path: Path):
    cfg = {
        "server": {"host": "127.0.0.1", "port": 9001},
        "store": {
            "qdrant_url": "http://qdrant-test:6333",
            "qdrant_collection": "test_vectors",
            "meta_db_url": "sqlite:////tmp/test.db",
        },
        "models": {
            "embeddings": {
                "provider": "mock",
                "ollama": {"model_name": "test-emb", "url": "http://ollama:11434/api/embed"},
            },
            "classifier": {
                "provider": "catboost",
                "model_path": "/models/test.cbm",
                "confidence_threshold": 0.55,
                "fallback_mode": "llm",
                "taxonomy_version": "v1",
            },
        },
        "online_clustering": {"similarity_threshold": 0.77, "recompute_centroid": False},
        "recompute": {
            "umap": {"n_neighbors": 12, "n_components": 8, "random_state": 7},
            "hdbscan": {"min_cluster_size": 4, "min_samples": 2},
        },
        "summarization": {
            "representative_examples_count": 5,
            "scenario_name_max_words": 3,
            "max_llm_retries": 1,
        },
    }
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(yaml.dump(cfg), encoding="utf-8")

    s = load_settings(config_path=str(yaml_path), env={})
    assert s.config_loaded is True
    assert s.is_valid()
    assert s.server.port == 9001
    assert s.store.qdrant_url == "http://qdrant-test:6333"
    assert s.embeddings.provider == "mock"
    assert s.embeddings.ollama_model == "test-emb"
    assert s.classifier.model_path == "/models/test.cbm"
    assert s.classifier.confidence_threshold == pytest.approx(0.55)
    assert s.online_clustering.similarity_threshold == pytest.approx(0.77)
    assert s.online_clustering.recompute_centroid is False
    assert s.recompute.umap.n_neighbors == 12
    assert s.recompute.hdbscan.min_cluster_size == 4
    assert s.summarization.representative_examples_count == 5


def test_env_overrides_yaml(tmp_path: Path):
    cfg = {
        "store": {"qdrant_url": "http://from-yaml:6333", "meta_db_url": "sqlite:////from-yaml.db"},
        "models": {"embeddings": {"provider": "ollama"}},
        "classifier": {"fallback_mode": "llm", "model_path": "/from-yaml.cbm"},
        "online_clustering": {"similarity_threshold": 0.5},
    }
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(yaml.dump(cfg), encoding="utf-8")

    s = load_settings(
        config_path=str(yaml_path),
        env={
            "QDRANT_URL": "http://from-env:6333",
            "ML_META_DB_URL": "sqlite:////from-env.db",
            "EMBEDDINGS_PROVIDER": "mock",
            "CLASSIFIER_MODEL_PATH": "/from-env.cbm",
            "CLASSIFIER_FALLBACK_MODE": "fail_fast",
            "ONLINE_SIMILARITY_THRESHOLD": "0.91",
            "OPENROUTER_API_KEY": "sk-test-not-for-git",
            "ML_SERVICE_TOKEN": "secret-token",
            "LOG_LEVEL": "DEBUG",
            "OLLAMA_URL": "http://ollama-env:11434",
            "OPENROUTER_EMBEDDINGS_URL": "https://example.com/emb",
            "OPENROUTER_CHAT_URL": "https://example.com/chat",
        },
    )
    assert s.store.qdrant_url == "http://from-env:6333"
    assert s.store.meta_db_url == "sqlite:////from-env.db"
    assert s.embeddings.provider == "mock"
    assert s.embeddings.ollama_url == "http://ollama-env:11434"
    assert s.embeddings.openrouter_url == "https://example.com/emb"
    assert s.embeddings.openrouter_api_key == "sk-test-not-for-git"
    assert s.llm.openrouter_url == "https://example.com/chat"
    assert s.llm.openrouter_api_key == "sk-test-not-for-git"
    assert s.classifier.model_path == "/from-env.cbm"
    assert s.classifier.fallback_mode == "fail_fast"
    assert s.online_clustering.similarity_threshold == pytest.approx(0.91)
    assert s.service_token == "secret-token"
    assert s.log_level == "DEBUG"


def test_invalid_fallback_mode_collected():
    s = load_settings(
        config_path=None,
        env={
            "EMBEDDINGS_PROVIDER": "mock",
            "CLASSIFIER_FALLBACK_MODE": "not_a_mode",
        },
    )
    # no yaml path: still builds defaults then validates
    assert not s.is_valid()
    assert any("fallback_mode" in e for e in s.config_errors)


def test_error_body_format():
    body = error_response(INVALID_REQUEST, "bad payload", details={"field": "query_text"})
    assert body == {
        "code": "INVALID_REQUEST",
        "message": "bad payload",
        "retryable": False,
        "details": {"field": "query_text"},
    }
    exc = MLServiceError(code=EMBEDDING_PROVIDER_UNAVAILABLE, message="down")
    assert exc.to_dict()["retryable"] is True
    assert exc.status_code == 503


def test_auth_401_when_token_required(monkeypatch: pytest.MonkeyPatch):
    # Import after patching settings.service_token used by dependency
    from app.core import config as config_mod
    from app.main import app

    monkeypatch.setattr(config_mod.settings, "service_token", "expected-token")

    with TestClient(app) as client:
        r = client.get("/api/v1/statistics")
        assert r.status_code == 401
        body = r.json()
        assert body["code"] == "UNAUTHORIZED"
        assert body["retryable"] is False
        assert "message" in body

        r_ok = client.get(
            "/api/v1/statistics",
            headers={"X-Service-Token": "expected-token"},
        )
        assert r_ok.status_code == 200

        # health stays open
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 200


def test_health_live_always_ok():
    from app.main import app

    with TestClient(app) as client:
        r = client.get("/health/live")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


def test_health_ready_degraded_when_store_mock(monkeypatch: pytest.MonkeyPatch):
    from app.core import config as config_mod
    from app.main import app

    # Force known-good config; missing openrouter key → llm degraded; mock qdrant → degraded
    monkeypatch.setattr(config_mod.settings, "config_errors", [])
    monkeypatch.setattr(config_mod.settings.embeddings, "provider", "mock")
    monkeypatch.setattr(config_mod.settings.llm, "provider", "openrouter")
    monkeypatch.setattr(config_mod.settings.llm, "openrouter_api_key", "")
    monkeypatch.setattr(config_mod.settings.classifier, "fallback_mode", "llm")

    with TestClient(app) as client:
        r = client.get("/health/ready")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] in {"ready", "degraded", "not_ready"}
        assert "checks" in body
        for key in ("config", "qdrant", "classifier", "embeddings_provider", "llm_provider"):
            assert key in body["checks"]
        # Without live Qdrant and without LLM key we expect degradation, not full ready
        assert body["status"] in {"degraded", "not_ready"}
        assert body["checks"]["llm_provider"] == "degraded"


def test_health_ready_not_ready_on_bad_config(monkeypatch: pytest.MonkeyPatch):
    from app.core import config as config_mod
    from app.main import app

    monkeypatch.setattr(config_mod.settings, "config_errors", ["broken"])
    with TestClient(app) as client:
        body = client.get("/health/ready").json()
        assert body["status"] == "not_ready"
        assert body["checks"]["config"] == "fail"
