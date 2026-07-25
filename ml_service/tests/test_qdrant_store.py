"""QdrantStore mock mode tests."""
from __future__ import annotations

import pytest

from app.store import qdrant as qdrant_module
from app.store.qdrant import QdrantStore


def test_mock_upsert_search_count():
    store = QdrantStore({"qdrant_url": "http://127.0.0.1:9"}, vector_size=4)
    assert store.is_mock is True
    store.upsert(
        "req_a",
        [1.0, 0.0, 0.0, 0.0],
        payload={
            "request_id": "req_a",
            "task_type": "code_help",
            "scenario_id": "code_help:cluster_0",
            "source_id": "demo",
            "is_outlier": False,
            "has_failure_signals": False,
            "failure_signals": [],
        },
    )
    store.upsert(
        "req_b",
        [0.9, 0.1, 0.0, 0.0],
        payload={"request_id": "req_b", "task_type": "code_help"},
    )
    store.upsert(
        "req_c",
        [0.0, 1.0, 0.0, 0.0],
        payload={"request_id": "req_c", "task_type": "data_analysis"},
    )
    assert store.get_count() == 3
    hits = store.search([1.0, 0.0, 0.0, 0.0], limit=2, task_type="code_help")
    assert len(hits) == 2
    assert hits[0]["request_id"] == "req_a"
    assert hits[0]["score"] == pytest.approx(1.0, abs=1e-6)

    all_pts = store.get_all()
    assert len(all_pts) == 3
    got = store.get("req_a")
    assert got is not None
    assert got["payload"]["scenario_id"] == "code_help:cluster_0"

    store.upsert_batch(
        [
            {
                "request_id": "req_d",
                "vector": [0.0, 0.0, 1.0, 0.0],
                "payload": {"request_id": "req_d", "task_type": "other"},
            }
        ]
    )
    assert store.get_count() == 4


def test_real_client_creates_collection_during_initialization(monkeypatch):
    calls: dict[str, object] = {}

    class FakeClient:
        def __init__(self, *, url: str, timeout: float):
            calls["init"] = (url, timeout)

        def collection_exists(self, collection_name: str) -> bool:
            calls["checked"] = collection_name
            return False

        def create_collection(self, *, collection_name: str, vectors_config: object):
            calls["created"] = (collection_name, vectors_config)

    monkeypatch.delenv("ALLOW_INMEMORY_STORE", raising=False)
    monkeypatch.delenv("QDRANT_URL", raising=False)
    monkeypatch.setattr(qdrant_module, "_HAS_QDRANT", True)
    monkeypatch.setattr(qdrant_module, "QdrantClient", FakeClient)

    store = QdrantStore(
        {
            "qdrant_url": "http://qdrant.test:6333",
            "qdrant_collection": "test_vectors",
        },
        vector_size=4,
    )

    assert store.is_mock is False
    assert calls["init"] == ("http://qdrant.test:6333", 2.0)
    assert calls["checked"] == "test_vectors"
    collection_name, vector_config = calls["created"]
    assert collection_name == "test_vectors"
    assert vector_config.size == 4
