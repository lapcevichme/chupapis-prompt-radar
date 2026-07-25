"""Chat models per provider — simple LangChain clients.

Usage:
    chat = chat_openrouter(model="google/gemma-4-26b-a4b-it")
    structured = chat.with_structured_output(MySchema)
    result = await structured.ainvoke(prompt)
"""
from __future__ import annotations

import os
from typing import Any, Optional


def chat_openrouter(
    model: str = "google/gemma-4-26b-a4b-it",
    *,
    api_key: Optional[str] = None,
    temperature: float = 0.3,
    **kwargs: Any,
):
    """OpenRouter chat (online)."""
    from langchain_openrouter import ChatOpenRouter

    key = api_key if api_key is not None else os.getenv("OPENROUTER_API_KEY", "")
    return ChatOpenRouter(
        model=model,
        temperature=temperature,
        api_key=key or None,
        **kwargs,
    )


def chat_ollama(
    model: str = "gemma4:26b-a4b-it",
    *,
    base_url: str = "http://127.0.0.1:11434",
    temperature: float = 0.3,
    **kwargs: Any,
):
    """Ollama chat (offline)."""
    from langchain_ollama import ChatOllama

    root = (base_url or "http://127.0.0.1:11434").rstrip("/")
    for suffix in ("/api/chat", "/api/generate", "/api/embed"):
        if root.endswith(suffix):
            root = root[: -len(suffix)]
    return ChatOllama(
        model=model,
        base_url=root,
        temperature=temperature,
        **kwargs,
    )


def chat_from_settings(settings: Any = None, **kwargs: Any):
    """Pick OpenRouter or Ollama from settings.llm.mode / resolve_provider()."""
    if settings is None:
        from app.core.config import settings as default_settings

        settings = default_settings
    llm = settings.llm
    backend = llm.resolve_provider() if hasattr(llm, "resolve_provider") else llm.provider
    if backend == "ollama":
        return chat_ollama(
            model=kwargs.pop("model", None) or llm.ollama_model,
            base_url=kwargs.pop("base_url", None) or llm.ollama_url,
            temperature=kwargs.pop("temperature", 0.3),
            **kwargs,
        )
    return chat_openrouter(
        model=kwargs.pop("model", None) or llm.openrouter_model,
        api_key=kwargs.pop("api_key", None) or llm.openrouter_api_key,
        temperature=kwargs.pop("temperature", 0.3),
        **kwargs,
    )
