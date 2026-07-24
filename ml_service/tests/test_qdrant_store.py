"""QdrantStore mock mode tests."""
from __future__ import annotations

import os

import pytest

# force mock before import of store usage
os.environ["ALLOW_INMEMORY_STORE"] = "true"

from app.store.qdrant import QdrantStore  # noqa: E402


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
