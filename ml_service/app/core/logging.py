"""Structured logging helpers (ТЗ §11).

Never log full query_text. Prefer request_id / source_id / stage / duration.
"""
from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from typing import Any, Generator, Optional


_CONFIGURED = False


def setup_logging(level: Optional[str] = None) -> None:
    """Configure root logging once (idempotent)."""
    global _CONFIGURED
    log_level = (level or os.getenv("LOG_LEVEL") or "INFO").upper()
    if _CONFIGURED:
        logging.getLogger().setLevel(log_level)
        return
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)


def _fmt_extra(extra: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in (
        "stage",
        "request_id",
        "source_id",
        "duration_ms",
        "provider",
        "model",
        "error_code",
        "job_id",
        "status",
    ):
        if key in extra and extra[key] is not None:
            parts.append(f"{key}={extra[key]}")
    # any remaining keys (no query_text ever)
    for key, value in extra.items():
        if key in {
            "stage",
            "request_id",
            "source_id",
            "duration_ms",
            "provider",
            "model",
            "error_code",
            "job_id",
            "status",
            "query_text",
            "text",
        }:
            continue
        if value is not None:
            parts.append(f"{key}={value}")
    return " ".join(parts)


def log_event(
    logger: logging.Logger,
    message: str,
    *,
    level: int = logging.INFO,
    stage: Optional[str] = None,
    request_id: Optional[str] = None,
    source_id: Optional[str] = None,
    duration_ms: Optional[float] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    error_code: Optional[str] = None,
    **kwargs: Any,
) -> None:
    """Emit a structured one-line log. Strips query_text / text if passed by mistake."""
    kwargs.pop("query_text", None)
    kwargs.pop("text", None)
    extra = {
        "stage": stage,
        "request_id": request_id,
        "source_id": source_id,
        "duration_ms": round(duration_ms, 2) if duration_ms is not None else None,
        "provider": provider,
        "model": model,
        "error_code": error_code,
        **kwargs,
    }
    suffix = _fmt_extra(extra)
    line = f"{message} {suffix}".rstrip()
    logger.log(level, line)


@contextmanager
def log_stage(
    logger: logging.Logger,
    stage: str,
    *,
    request_id: Optional[str] = None,
    source_id: Optional[str] = None,
    **kwargs: Any,
) -> Generator[dict[str, Any], None, None]:
    """Context manager that logs stage start/end with duration_ms."""
    kwargs.pop("query_text", None)
    kwargs.pop("text", None)
    ctx: dict[str, Any] = {"stage": stage}
    t0 = time.perf_counter()
    log_event(
        logger,
        "stage_start",
        stage=stage,
        request_id=request_id,
        source_id=source_id,
        **kwargs,
    )
    try:
        yield ctx
    except Exception as exc:  # noqa: BLE001
        duration_ms = (time.perf_counter() - t0) * 1000
        log_event(
            logger,
            "stage_error",
            level=logging.ERROR,
            stage=stage,
            request_id=request_id,
            source_id=source_id,
            duration_ms=duration_ms,
            error_code=getattr(exc, "code", type(exc).__name__),
            **kwargs,
        )
        raise
    else:
        duration_ms = (time.perf_counter() - t0) * 1000
        log_event(
            logger,
            "stage_done",
            stage=stage,
            request_id=request_id,
            source_id=source_id,
            duration_ms=duration_ms,
            **{**kwargs, **{k: v for k, v in ctx.items() if k != "stage"}},
        )
