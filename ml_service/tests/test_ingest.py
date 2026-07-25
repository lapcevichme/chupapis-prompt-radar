"""Ingest API: validation, duplicates, partial reject, meta persistence."""
from __future__ import annotations

import os
import time

# Ensure offline store before app import
os.environ.setdefault("ALLOW_INMEMORY_STORE", "true")
os.environ.setdefault("EMBEDDINGS_PROVIDER", "mock")
os.environ.setdefault("ML_META_DB_URL", "sqlite:///:memory:")
os.environ.setdefault("ML_SERVICE_TOKEN", "")

from fastapi.testclient import TestClient

from app.main import app


def _wait_processed(client: TestClient, expected_min: int = 1, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        r = client.get("/api/v1/statistics")
        assert r.status_code == 200
        last = r.json()
        if last.get("total_logs", 0) >= expected_min:
            return last
        time.sleep(0.1)
    return last


def test_put_logs_partial_reject_and_duplicate():
    with TestClient(app) as client:
        payload = {
            "logs": [
                {
                    "request_id": "ing-1",
                    "query_text": "напиши python function для парсинга json",
                    "timestamp": "2026-07-25T12:00:00Z",
                    "source_id": "demo",
                },
                {
                    "request_id": "ing-empty",
                    "query_text": "   ",
                    "timestamp": "2026-07-25T12:00:00Z",
                    "source_id": "demo",
                },
                {
                    "request_id": "ing-bad-ts",
                    "query_text": "valid text",
                    "timestamp": "not-a-date",
                    "source_id": "demo",
                },
                {
                    "request_id": "ing-2",
                    "query_text": "как сделать pivot table в excel",
                    "timestamp": "2026-07-25T13:00:00Z",
                    "source_id": "demo",
                },
            ]
        }
        r = client.put("/api/v1/logs", json=payload)
        assert r.status_code == 202
        body = r.json()
        assert body["accepted"] == 2
        assert body["rejected"] == 2
        assert body["duplicates"] == 0
        assert body["source_id"] == "demo"

        stats = _wait_processed(client, expected_min=2)
        assert stats["total_logs"] >= 2

        # duplicate request_id → counted as duplicates, not re-accepted
        r2 = client.put(
            "/api/v1/logs",
            json={
                "logs": [
                    {
                        "request_id": "ing-1",
                        "query_text": "another text same id",
                        "timestamp": "2026-07-25T14:00:00Z",
                        "source_id": "demo",
                    }
                ]
            },
        )
        assert r2.status_code == 202
        assert r2.json()["accepted"] == 0
        assert r2.json()["duplicates"] == 1

        # total should not grow from the duplicate
        time.sleep(0.3)
        stats2 = client.get("/api/v1/statistics").json()
        assert stats2["total_logs"] == stats["total_logs"]

        assigns = client.get("/api/v1/assignments?source_id=demo&limit=10")
        assert assigns.status_code == 200
        data = assigns.json()
        assert data["total"] >= 2
        ids = {x["request_id"] for x in data["items"]}
        assert "ing-1" in ids
        assert {x["source_id"] for x in data["items"]} == {"demo"}


def test_duplicate_within_same_batch():
    with TestClient(app) as client:
        payload = {
            "logs": [
                {
                    "request_id": "dup-batch",
                    "query_text": "first occurrence",
                    "timestamp": "2026-07-25T12:00:00Z",
                    "source_id": "batch",
                },
                {
                    "request_id": "dup-batch",
                    "query_text": "second occurrence",
                    "timestamp": "2026-07-25T12:01:00Z",
                    "source_id": "batch",
                },
            ]
        }
        r = client.put("/api/v1/logs", json=payload)
        assert r.status_code == 202
        body = r.json()
        assert body["accepted"] == 1
        assert body["duplicates"] == 1
