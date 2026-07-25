"""Unit tests for Ollama auto-pull helpers (no real network pull)."""
from __future__ import annotations

import pytest

from app.core.ollama_bootstrap import _model_present, models_for_offline_settings


def test_model_present_exact_and_tag():
    installed = {"qwen3-embedding:4b", "gemma4:26b-a4b-it"}
    assert _model_present("qwen3-embedding:4b", installed)
    assert _model_present("gemma4:26b-a4b-it", installed)
    assert not _model_present("llama3:8b", installed)


def test_models_for_offline_settings():
    class Emb:
        mode = "offline"
        provider = "ollama"
        ollama_url = "http://127.0.0.1:11434"
        ollama_model = "qwen3-embedding:4b"

        def resolve_provider(self):
            return "ollama"

    class Llm:
        mode = "offline"
        provider = "ollama"
        ollama_url = "http://127.0.0.1:11434"
        ollama_model = "gemma4:26b-a4b-it"

        def resolve_provider(self):
            return "ollama"

    class S:
        embeddings = Emb()
        llm = Llm()

    base, models = models_for_offline_settings(S())
    assert "11434" in base
    assert "qwen3-embedding:4b" in models
    assert "gemma4:26b-a4b-it" in models


def test_models_online_skips_ollama():
    class Emb:
        ollama_url = "http://x"
        ollama_model = "qwen3-embedding:4b"

        def resolve_provider(self):
            return "openrouter"

    class Llm:
        ollama_url = "http://x"
        ollama_model = "gemma4:26b-a4b-it"

        def resolve_provider(self):
            return "openrouter"

    class S:
        embeddings = Emb()
        llm = Llm()

    base, models = models_for_offline_settings(S())
    assert models == []
