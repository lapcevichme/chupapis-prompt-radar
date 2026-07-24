"""Unit tests for the dashboard statistics TTL cache."""

import pytest

from service.dashboard import cache


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.invalidate()
    yield
    cache.invalidate()


def test_set_and_get() -> None:
    cache.set("k", {"records_total": 10}, ttl=60)
    assert cache.get("k") == {"records_total": 10}


def test_missing_key_returns_none() -> None:
    assert cache.get("absent") is None


def test_zero_ttl_disables_caching() -> None:
    cache.set("k", {"x": 1}, ttl=0)
    assert cache.get("k") is None


def test_expiry(monkeypatch) -> None:
    clock = {"t": 1000.0}
    monkeypatch.setattr(cache.time, "monotonic", lambda: clock["t"])
    cache.set("k", {"x": 1}, ttl=15)
    assert cache.get("k") == {"x": 1}
    clock["t"] += 14
    assert cache.get("k") == {"x": 1}  # still fresh
    clock["t"] += 2  # now 16s elapsed > 15 ttl
    assert cache.get("k") is None


def test_invalidate_clears_all() -> None:
    cache.set("a", 1, ttl=60)
    cache.set("b", 2, ttl=60)
    cache.invalidate()
    assert cache.get("a") is None
    assert cache.get("b") is None


def test_cache_key_stable_and_filter_sensitive() -> None:
    k1 = cache.cache_key({"source_id": "s1", "from": None, "to": None})
    k2 = cache.cache_key({"source_id": "s1"})
    assert k1 == k2  # None and missing are equivalent
    assert cache.cache_key({"source_id": "s2"}) != k1
    assert cache.cache_key(None) == cache.cache_key({})
