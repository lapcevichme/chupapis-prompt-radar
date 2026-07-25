"""Ensure Ollama models are present for offline mode (auto-pull if missing)."""
from __future__ import annotations

import logging
import os
from typing import Any, Iterable, Optional, Sequence

import aiohttp

logger = logging.getLogger(__name__)


def _auto_pull_enabled() -> bool:
    """Default ON for offline; OFF if explicitly disabled or pure unit-test mock."""
    raw = (os.getenv("OLLAMA_AUTO_PULL") or "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    # auto: skip when embeddings forced mock (pytest)
    emb_mode = (os.getenv("EMBEDDINGS_MODE") or os.getenv("EMBEDDINGS_PROVIDER") or "").lower()
    if emb_mode == "mock":
        return False
    return True


async def list_local_models(base_url: str, *, timeout_sec: float = 10.0) -> set[str]:
    """Return set of model names from Ollama /api/tags."""
    url = base_url.rstrip("/") + "/api/tags"
    timeout = aiohttp.ClientTimeout(total=timeout_sec)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(f"Ollama /api/tags HTTP {resp.status}: {body[:200]}")
            data = await resp.json(content_type=None)
    names: set[str] = set()
    for m in data.get("models") or []:
        name = m.get("name") or m.get("model")
        if name:
            names.add(str(name))
            # also bare name without :tag for matching
            if ":" in name:
                names.add(name.split(":", 1)[0])
    return names


def _model_present(needed: str, installed: set[str]) -> bool:
    if not needed:
        return False
    if needed in installed:
        return True
    base = needed.split(":", 1)[0]
    # exact tag or any installed tag of same base (e.g. needed foo:bar, have foo:bar)
    for name in installed:
        if name == needed:
            return True
        if name.split(":", 1)[0] == base and ":" in needed and name == needed:
            return True
    # if only base name requested
    if ":" not in needed and any(n == needed or n.startswith(needed + ":") for n in installed):
        return True
    return False


async def pull_model(
    base_url: str,
    model: str,
    *,
    timeout_sec: float = 3600.0,
) -> None:
    """Pull model via Ollama /api/pull (stream=false, can take a long time)."""
    url = base_url.rstrip("/") + "/api/pull"
    payload = {"name": model, "stream": False}
    timeout = aiohttp.ClientTimeout(total=timeout_sec)
    logger.info("Ollama pull started model=%s (may take several minutes)", model)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, json=payload) as resp:
            body = await resp.text()
            if resp.status != 200:
                raise RuntimeError(f"Ollama pull {model} HTTP {resp.status}: {body[:300]}")
            # stream=false still may return JSON status
            logger.info("Ollama pull finished model=%s status=%s", model, resp.status)


async def ensure_ollama_models(
    base_url: str,
    models: Sequence[str],
    *,
    auto_pull: Optional[bool] = None,
    pull_timeout_sec: float = 3600.0,
) -> dict[str, Any]:
    """
    Check that each model is available locally; pull missing ones if auto_pull.

    Returns report: {model: "present"|"pulled"|"failed"|"skipped", ... , "errors": [...]}
    """
    report: dict[str, Any] = {"base_url": base_url, "models": {}, "errors": []}
    models = [m for m in models if m and str(m).strip()]
    if not models:
        return report

    if auto_pull is None:
        auto_pull = _auto_pull_enabled()

    try:
        installed = await list_local_models(base_url)
    except Exception as exc:  # noqa: BLE001
        msg = f"Ollama not reachable at {base_url}: {exc}"
        logger.warning(msg)
        report["errors"].append(msg)
        for m in models:
            report["models"][m] = "unreachable"
        return report

    logger.info("Ollama local models: %s", sorted(installed)[:30])

    for model in models:
        if _model_present(model, installed):
            report["models"][model] = "present"
            logger.info("Ollama model already present: %s", model)
            continue
        if not auto_pull:
            report["models"][model] = "missing"
            report["errors"].append(f"missing model {model} (OLLAMA_AUTO_PULL=false)")
            logger.warning(
                "Ollama model missing: %s — set OLLAMA_AUTO_PULL=true or: ollama pull %s",
                model,
                model,
            )
            continue
        try:
            await pull_model(base_url, model, timeout_sec=pull_timeout_sec)
            report["models"][model] = "pulled"
            # refresh installed set
            try:
                installed = await list_local_models(base_url)
            except Exception:  # noqa: BLE001
                pass
        except Exception as exc:  # noqa: BLE001
            report["models"][model] = "failed"
            report["errors"].append(f"pull {model}: {exc}")
            logger.error("Ollama pull failed model=%s: %s", model, exc)

    return report


def models_for_offline_settings(settings: Any) -> tuple[str, list[str]]:
    """Collect Ollama base URL + model names needed for current offline modes."""
    models: list[str] = []
    base = "http://127.0.0.1:11434"

    emb_p = settings.embeddings.resolve_provider() if hasattr(settings.embeddings, "resolve_provider") else settings.embeddings.provider
    if emb_p == "ollama":
        base = (settings.embeddings.ollama_url or base).rstrip("/")
        if settings.embeddings.ollama_model:
            models.append(settings.embeddings.ollama_model)

    llm_p = settings.llm.resolve_provider() if hasattr(settings.llm, "resolve_provider") else settings.llm.provider
    if llm_p == "ollama":
        base = (settings.llm.ollama_url or base).rstrip("/")
        if settings.llm.ollama_model:
            models.append(settings.llm.ollama_model)

    # dedupe preserve order
    seen: set[str] = set()
    uniq: list[str] = []
    for m in models:
        if m not in seen:
            seen.add(m)
            uniq.append(m)
    return base, uniq
