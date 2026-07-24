"""In-process TTL cache for the dashboard read-model (ML statistics).

MVP-lean: statistics is a read-model owned by ML; caching it briefly avoids a
round-trip to ML on every dashboard request. Single-process only (no Redis).
Invalidated explicitly on recompute / new ingestion, and expires by TTL.
"""

import time
from typing import Any

_store: dict[str, tuple[float, Any]] = {}


def get(key: str) -> Any | None:
    entry = _store.get(key)
    if entry is None:
        return None
    expires_at, value = entry
    if time.monotonic() >= expires_at:
        _store.pop(key, None)
        return None
    return value


def set(key: str, value: Any, ttl: float) -> None:
    if ttl <= 0:
        return
    _store[key] = (time.monotonic() + ttl, value)


def invalidate() -> None:
    """Drop all cached statistics (call after recompute / new logs)."""
    _store.clear()


def cache_key(filters: dict[str, Any] | None) -> str:
    filters = filters or {}
    return "|".join(
        f"{name}={filters.get(name) or ''}" for name in ("source_id", "from", "to")
    )
