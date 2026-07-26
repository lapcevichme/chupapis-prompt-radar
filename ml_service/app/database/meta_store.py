"""Analytical meta store (SQLite default): assignments, clusters, jobs, ingest_log."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


def _sqlite_path(db_url: str) -> str:
    # sqlite:///:memory: | sqlite:///./ml_meta.db | sqlite:////data/ml/meta.db
    if db_url in (":memory:", "sqlite:///:memory:", "sqlite://"):
        return ":memory:"
    if db_url.startswith("sqlite:////"):
        return "/" + db_url[len("sqlite:////") :]
    if db_url.startswith("sqlite:///"):
        return db_url[len("sqlite:///") :]
    return db_url


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_dumps(value: Any) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _json_loads(raw: Optional[str]) -> Any:
    if raw is None or raw == "":
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


class MetaStore:
    """Thread-safe SQLite meta store. Keeps a single connection (needed for :memory:)."""

    def __init__(self, db_url: str = "sqlite:///./ml_meta.db"):
        self.db_url = db_url
        self.path = _sqlite_path(db_url)
        if self.path not in (":memory:",):
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        # check_same_thread=False: FastAPI/worker threads share one connection
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def _cursor(self) -> sqlite3.Cursor:
        assert self._conn is not None
        return self._conn.cursor()

    def _commit(self) -> None:
        assert self._conn is not None
        self._conn.commit()

    def _init_db(self) -> None:
        with self._lock:
            cur = self._cursor()
            cur.executescript(
                """
                CREATE TABLE IF NOT EXISTS assignments (
                    request_id TEXT PRIMARY KEY,
                    task_type TEXT,
                    classification_confidence REAL,
                    scenario_id TEXT,
                    is_outlier INTEGER DEFAULT 0,
                    has_failure_signals INTEGER DEFAULT 0,
                    failure_signals TEXT,
                    source_id TEXT,
                    timestamp TEXT,
                    query_text TEXT,
                    created_at TEXT,
                    updated_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_assignments_source
                    ON assignments(source_id);
                CREATE INDEX IF NOT EXISTS idx_assignments_ts
                    ON assignments(timestamp);
                CREATE INDEX IF NOT EXISTS idx_assignments_scenario
                    ON assignments(scenario_id);

                CREATE TABLE IF NOT EXISTS clusters (
                    scenario_id TEXT PRIMARY KEY,
                    task_type TEXT,
                    name TEXT,
                    summary TEXT,
                    user_goal TEXT,
                    pain_points TEXT,
                    automation_potential TEXT,
                    records_count INTEGER DEFAULT 0,
                    statistical_reliability TEXT,
                    centroid TEXT,
                    updated_at TEXT
                );

                CREATE TABLE IF NOT EXISTS recompute_jobs (
                    job_id TEXT PRIMARY KEY,
                    status TEXT,
                    clusters_created INTEGER DEFAULT 0,
                    scenarios_named INTEGER DEFAULT 0,
                    created_at TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    error TEXT,
                    extra TEXT
                );

                CREATE TABLE IF NOT EXISTS ingest_log (
                    source_id TEXT PRIMARY KEY,
                    accepted INTEGER DEFAULT 0,
                    classified INTEGER DEFAULT 0,
                    assigned INTEGER DEFAULT 0,
                    rejected INTEGER DEFAULT 0,
                    duplicates INTEGER DEFAULT 0,
                    updated_at TEXT
                );
                """
            )
            self._commit()

    # ── assignments ──────────────────────────────────────────────────────────

    def has_assignment(self, request_id: str) -> bool:
        with self._lock:
            cur = self._cursor()
            cur.execute(
                "SELECT 1 FROM assignments WHERE request_id = ? LIMIT 1",
                (request_id,),
            )
            return cur.fetchone() is not None

    def get_assignment(self, request_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            cur = self._cursor()
            cur.execute(
                "SELECT * FROM assignments WHERE request_id = ?",
                (request_id,),
            )
            row = cur.fetchone()
            return self._row_to_assignment(row) if row else None

    def upsert_assignment(self, data: Dict[str, Any]) -> None:
        now = _utcnow()
        request_id = data["request_id"]
        with self._lock:
            cur = self._cursor()
            cur.execute(
                "SELECT created_at FROM assignments WHERE request_id = ?",
                (request_id,),
            )
            existing = cur.fetchone()
            created_at = existing["created_at"] if existing else now
            failure_signals = data.get("failure_signals")
            if failure_signals is None and data.get("has_failure_signals"):
                failure_signals = []
            cur.execute(
                """
                INSERT INTO assignments (
                    request_id, task_type, classification_confidence, scenario_id,
                    is_outlier, has_failure_signals, failure_signals, source_id,
                    timestamp, query_text, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(request_id) DO UPDATE SET
                    task_type = excluded.task_type,
                    classification_confidence = excluded.classification_confidence,
                    scenario_id = excluded.scenario_id,
                    is_outlier = excluded.is_outlier,
                    has_failure_signals = excluded.has_failure_signals,
                    failure_signals = excluded.failure_signals,
                    source_id = excluded.source_id,
                    timestamp = excluded.timestamp,
                    query_text = excluded.query_text,
                    updated_at = excluded.updated_at
                """,
                (
                    request_id,
                    data.get("task_type"),
                    data.get("classification_confidence"),
                    data.get("scenario_id"),
                    1 if data.get("is_outlier") else 0,
                    1 if data.get("has_failure_signals") else 0,
                    _json_dumps(failure_signals),
                    data.get("source_id"),
                    _ts_str(data.get("timestamp")),
                    data.get("query_text"),
                    created_at,
                    now,
                ),
            )
            self._commit()

    def list_assignments(
        self,
        *,
        source_id: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        where, params = self._filter_clause(source_id, from_date, to_date)
        with self._lock:
            cur = self._cursor()
            cur.execute(
                f"SELECT COUNT(*) AS cnt FROM assignments {where}",
                params,
            )
            total = int(cur.fetchone()["cnt"])
            cur.execute(
                f"""
                SELECT * FROM assignments {where}
                ORDER BY timestamp DESC, request_id
                LIMIT ? OFFSET ?
                """,
                [*params, limit, offset],
            )
            items = [self._row_to_assignment(r) for r in cur.fetchall()]
        return {"items": items, "total": total}

    def all_assignments(
        self,
        *,
        source_id: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        where, params = self._filter_clause(source_id, from_date, to_date)
        with self._lock:
            cur = self._cursor()
            cur.execute(
                f"SELECT * FROM assignments {where} ORDER BY timestamp, request_id",
                params,
            )
            return [self._row_to_assignment(r) for r in cur.fetchall()]

    def count_assignments(
        self,
        *,
        source_id: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> int:
        where, params = self._filter_clause(source_id, from_date, to_date)
        with self._lock:
            cur = self._cursor()
            cur.execute(f"SELECT COUNT(*) AS cnt FROM assignments {where}", params)
            return int(cur.fetchone()["cnt"])

    def update_assignment_scenario(
        self,
        request_id: str,
        *,
        scenario_id: Optional[str],
        is_outlier: bool = False,
    ) -> None:
        with self._lock:
            cur = self._cursor()
            cur.execute(
                """
                UPDATE assignments
                SET scenario_id = ?, is_outlier = ?, updated_at = ?
                WHERE request_id = ?
                """,
                (scenario_id, 1 if is_outlier else 0, _utcnow(), request_id),
            )
            self._commit()

    def update_assignment_scenarios_batch(
        self,
        rows: Sequence[Dict[str, Any]],
    ) -> int:
        """Bulk-update scenario_id / is_outlier in one transaction."""
        if not rows:
            return 0
        now = _utcnow()
        with self._lock:
            cur = self._cursor()
            cur.executemany(
                """
                UPDATE assignments
                SET scenario_id = ?, is_outlier = ?, updated_at = ?
                WHERE request_id = ?
                """,
                [
                    (
                        r.get("scenario_id"),
                        1 if r.get("is_outlier") else 0,
                        now,
                        r["request_id"],
                    )
                    for r in rows
                    if r.get("request_id")
                ],
            )
            self._commit()
            return len(rows)

    # ── clusters ─────────────────────────────────────────────────────────────

    def upsert_cluster(self, data: Dict[str, Any]) -> None:
        with self._lock:
            cur = self._cursor()
            cur.execute(
                """
                INSERT INTO clusters (
                    scenario_id, task_type, name, summary, user_goal, pain_points,
                    automation_potential, records_count, statistical_reliability,
                    centroid, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scenario_id) DO UPDATE SET
                    task_type = excluded.task_type,
                    name = excluded.name,
                    summary = excluded.summary,
                    user_goal = excluded.user_goal,
                    pain_points = excluded.pain_points,
                    automation_potential = excluded.automation_potential,
                    records_count = excluded.records_count,
                    statistical_reliability = excluded.statistical_reliability,
                    centroid = excluded.centroid,
                    updated_at = excluded.updated_at
                """,
                (
                    data["scenario_id"],
                    data.get("task_type"),
                    data.get("name"),
                    data.get("summary"),
                    data.get("user_goal"),
                    _json_dumps(data.get("pain_points")),
                    data.get("automation_potential"),
                    int(data.get("records_count") or 0),
                    data.get("statistical_reliability"),
                    _json_dumps(data.get("centroid")),
                    data.get("updated_at") or _utcnow(),
                ),
            )
            self._commit()

    def get_cluster(self, scenario_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            cur = self._cursor()
            cur.execute(
                "SELECT * FROM clusters WHERE scenario_id = ?",
                (scenario_id,),
            )
            row = cur.fetchone()
            return self._row_to_cluster(row) if row else None

    def list_clusters(self) -> List[Dict[str, Any]]:
        with self._lock:
            cur = self._cursor()
            cur.execute("SELECT * FROM clusters ORDER BY records_count DESC, scenario_id")
            return [self._row_to_cluster(r) for r in cur.fetchall()]

    # ── recompute_jobs ───────────────────────────────────────────────────────

    def put_recompute_job(self, job: Dict[str, Any]) -> None:
        """Alias for RecomputeStore.persistence protocol (PR E)."""
        self.put_job(job)

    def get_recompute_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Alias for RecomputeStore.persistence protocol (PR E)."""
        return self.get_job(job_id)

    def put_job(self, job: Dict[str, Any]) -> None:
        with self._lock:
            cur = self._cursor()
            known = {
                "job_id",
                "status",
                "clusters_created",
                "scenarios_named",
                "created_at",
                "started_at",
                "completed_at",
                "error",
            }
            extra = {k: v for k, v in job.items() if k not in known}
            cur.execute(
                """
                INSERT INTO recompute_jobs (
                    job_id, status, clusters_created, scenarios_named,
                    created_at, started_at, completed_at, error, extra
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    status = excluded.status,
                    clusters_created = excluded.clusters_created,
                    scenarios_named = excluded.scenarios_named,
                    created_at = COALESCE(excluded.created_at, recompute_jobs.created_at),
                    started_at = COALESCE(excluded.started_at, recompute_jobs.started_at),
                    completed_at = excluded.completed_at,
                    error = excluded.error,
                    extra = excluded.extra
                """,
                (
                    job["job_id"],
                    job.get("status", "pending"),
                    int(job.get("clusters_created") or 0),
                    int(job.get("scenarios_named") or 0),
                    job.get("created_at") or _utcnow(),
                    job.get("started_at"),
                    job.get("completed_at") or job.get("finished_at"),
                    job.get("error"),
                    _json_dumps(extra) if extra else None,
                ),
            )
            self._commit()

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            cur = self._cursor()
            cur.execute("SELECT * FROM recompute_jobs WHERE job_id = ?", (job_id,))
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_job(row)

    def get_last_completed_job(self) -> Optional[Dict[str, Any]]:
        """Most recent successful recompute, so freshness survives a restart."""
        with self._lock:
            cur = self._cursor()
            cur.execute(
                "SELECT * FROM recompute_jobs "
                "WHERE status = 'completed' AND completed_at IS NOT NULL "
                "ORDER BY completed_at DESC LIMIT 1"
            )
            row = cur.fetchone()
            return self._row_to_job(row) if row else None

    # ── ingest_log ───────────────────────────────────────────────────────────

    def bump_ingest_log(
        self,
        source_id: str,
        *,
        accepted: int = 0,
        classified: int = 0,
        assigned: int = 0,
        rejected: int = 0,
        duplicates: int = 0,
    ) -> None:
        if not source_id:
            source_id = "_unknown"
        with self._lock:
            cur = self._cursor()
            cur.execute(
                """
                INSERT INTO ingest_log (
                    source_id, accepted, classified, assigned, rejected, duplicates, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    accepted = ingest_log.accepted + excluded.accepted,
                    classified = ingest_log.classified + excluded.classified,
                    assigned = ingest_log.assigned + excluded.assigned,
                    rejected = ingest_log.rejected + excluded.rejected,
                    duplicates = ingest_log.duplicates + excluded.duplicates,
                    updated_at = excluded.updated_at
                """,
                (
                    source_id,
                    accepted,
                    classified,
                    assigned,
                    rejected,
                    duplicates,
                    _utcnow(),
                ),
            )
            self._commit()

    # ── statistics (aggregates from assignments) ─────────────────────────────

    def get_statistics(
        self,
        source_id: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        items = self.all_assignments(
            source_id=source_id, from_date=from_date, to_date=to_date
        )
        by_task: Dict[str, int] = {}
        by_scenario: Dict[str, int] = {}
        outliers = 0
        failures = 0
        for a in items:
            tt = a.get("task_type") or "unknown"
            by_task[tt] = by_task.get(tt, 0) + 1
            sid = a.get("scenario_id") or "unknown"
            by_scenario[sid] = by_scenario.get(sid, 0) + 1
            if a.get("is_outlier"):
                outliers += 1
            if a.get("has_failure_signals"):
                failures += 1

        clusters_by_id = {c["scenario_id"]: c for c in self.list_clusters()}
        total = len(items)
        return {
            "total_logs": total,
            "by_task_type": [
                {"task_type": k, "count": v}
                for k, v in sorted(by_task.items(), key=lambda x: -x[1])
            ],
            "by_scenario": [
                {
                    "scenario_id": k,
                    "count": v,
                    "name": (clusters_by_id.get(k) or {}).get("name"),
                }
                for k, v in sorted(by_scenario.items(), key=lambda x: -x[1])
            ],
            "outliers": outliers,
            "failure_rate": (failures / total) if total else 0.0,
            "pipeline_metadata": {
                "schema_version": "2.0.0",
                "taxonomy_version": "v1",
            },
        }

    def get_assignments(
        self,
        source_id: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self.list_assignments(
            source_id=source_id,
            from_date=from_date,
            to_date=to_date,
            limit=limit,
            offset=offset,
        )

    # ── helpers ──────────────────────────────────────────────────────────────

    def _filter_clause(
        self,
        source_id: Optional[str],
        from_date: Optional[str],
        to_date: Optional[str],
    ) -> tuple[str, List[Any]]:
        clauses: List[str] = []
        params: List[Any] = []
        if source_id:
            clauses.append("source_id = ?")
            params.append(source_id)
        if from_date:
            clauses.append("timestamp >= ?")
            params.append(from_date)
        if to_date:
            clauses.append("timestamp <= ?")
            params.append(to_date)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        return where, params

    @staticmethod
    def _row_to_assignment(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "request_id": row["request_id"],
            "task_type": row["task_type"],
            "classification_confidence": row["classification_confidence"],
            "scenario_id": row["scenario_id"],
            "is_outlier": bool(row["is_outlier"]),
            "has_failure_signals": bool(row["has_failure_signals"]),
            "failure_signals": _json_loads(row["failure_signals"]) or [],
            "source_id": row["source_id"],
            "timestamp": row["timestamp"],
            "query_text": row["query_text"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _row_to_cluster(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "scenario_id": row["scenario_id"],
            "task_type": row["task_type"],
            "name": row["name"],
            "summary": row["summary"],
            "user_goal": row["user_goal"],
            "pain_points": _json_loads(row["pain_points"]) or [],
            "automation_potential": row["automation_potential"],
            "records_count": row["records_count"],
            "statistical_reliability": row["statistical_reliability"],
            "centroid": _json_loads(row["centroid"]),
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> Dict[str, Any]:
        extra = _json_loads(row["extra"]) or {}
        out: Dict[str, Any] = {
            "job_id": row["job_id"],
            "status": row["status"],
            "clusters_created": row["clusters_created"],
            "scenarios_named": row["scenarios_named"],
            "created_at": row["created_at"],
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
            "error": row["error"],
        }
        out.update(extra)
        return out


def _ts_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)
