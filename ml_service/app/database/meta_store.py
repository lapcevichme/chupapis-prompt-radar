"""Lightweight meta store (SQLite mock for MVP aggregates)."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional


def _sqlite_path(db_url: str) -> str:
    # sqlite:///./ml_meta.db or sqlite:////data/ml/meta.db
    if db_url.startswith("sqlite:////"):
        return "/" + db_url[len("sqlite:////") :]
    if db_url.startswith("sqlite:///"):
        return db_url[len("sqlite:///") :]
    return db_url


class MetaStore:
    def __init__(self, db_url: str):
        self.db_url = db_url
        self.path = _sqlite_path(db_url)
        if self.path not in (":memory:",):
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS clusters (
                    scenario_id TEXT PRIMARY KEY,
                    task_type TEXT,
                    name TEXT,
                    summary TEXT,
                    records_count INTEGER,
                    updated_at TEXT
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS ingest_log (
                    source_id TEXT,
                    accepted INTEGER DEFAULT 0,
                    classified INTEGER DEFAULT 0,
                    updated_at TEXT
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def get_statistics(
        self,
        source_id: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "total_logs": 0,
            "by_task_type": [],
            "by_scenario": [],
            "outliers": 0,
            "failure_rate": 0.0,
            "pipeline_metadata": {
                "schema_version": "2.0.0",
                "taxonomy_version": "v1",
            },
        }

    def get_assignments(self, source_id: Optional[str] = None, limit: int = 10) -> Dict[str, Any]:
        return {"items": [], "total": 0}
