"""Lightweight smoke without full demo dataset dependency."""
from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoints():
    with TestClient(app) as client:
        r = client.get("/health/live")
        assert r.status_code == 200
        assert r.json()["status"] == "live"
        r2 = client.get("/health/ready")
        assert r2.status_code == 200
        assert r2.json()["status"] == "ready"


def test_logs_and_statistics_flow():
    with TestClient(app) as client:
        payload = {
            "logs": [
                {
                    "request_id": "smoke-1",
                    "query_text": "напиши python function для парсинга json",
                    "timestamp": "2026-07-25T12:00:00Z",
                    "source_id": "demo",
                }
            ]
        }
        r = client.put("/api/v1/logs", json=payload)
        assert r.status_code == 202
        body = r.json()
        assert body["accepted"] == 1

        time.sleep(0.8)

        stats = client.get("/api/v1/statistics")
        assert stats.status_code == 200
        data = stats.json()
        assert "pipeline_metadata" in data
        assert data["pipeline_metadata"]["schema_version"] == "2.0.0"
