"""MetaStore unit tests (SQLite in-memory)."""
from __future__ import annotations

from app.database.meta_store import MetaStore


def test_assignments_crud_and_filters():
    store = MetaStore("sqlite:///:memory:")
    try:
        store.upsert_assignment(
            {
                "request_id": "r1",
                "task_type": "code_help",
                "classification_confidence": 0.9,
                "scenario_id": "code_help:cluster_0",
                "is_outlier": False,
                "has_failure_signals": True,
                "failure_signals": ["error_code:tool_error"],
                "source_id": "src_a",
                "timestamp": "2026-07-20T10:00:00Z",
                "query_text": "fix a bug",
            }
        )
        store.upsert_assignment(
            {
                "request_id": "r2",
                "task_type": "data_analysis",
                "classification_confidence": 0.7,
                "scenario_id": "data_analysis:cluster_0",
                "source_id": "src_b",
                "timestamp": "2026-07-22T10:00:00Z",
                "query_text": "export crm",
            }
        )
        assert store.has_assignment("r1")
        assert not store.has_assignment("missing")
        got = store.get_assignment("r1")
        assert got is not None
        assert got["task_type"] == "code_help"
        assert got["failure_signals"] == ["error_code:tool_error"]

        page = store.list_assignments(source_id="src_a", limit=10, offset=0)
        assert page["total"] == 1
        assert page["items"][0]["request_id"] == "r1"

        filtered = store.list_assignments(
            from_date="2026-07-21T00:00:00Z",
            to_date="2026-07-23T00:00:00Z",
        )
        assert filtered["total"] == 1
        assert filtered["items"][0]["request_id"] == "r2"

        # idempotent upsert updates fields
        store.upsert_assignment(
            {
                "request_id": "r1",
                "task_type": "code_help",
                "classification_confidence": 0.95,
                "scenario_id": "code_help:cluster_1",
                "source_id": "src_a",
                "timestamp": "2026-07-20T10:00:00Z",
            }
        )
        assert store.get_assignment("r1")["scenario_id"] == "code_help:cluster_1"
        assert store.count_assignments() == 2
    finally:
        store.close()


def test_clusters_and_jobs_and_ingest_log():
    store = MetaStore("sqlite:///:memory:")
    try:
        store.upsert_cluster(
            {
                "scenario_id": "code_help:cluster_0",
                "task_type": "code_help",
                "name": "Bugfix helpers",
                "summary": "Fix bugs",
                "user_goal": "Ship fix",
                "pain_points": ["unclear stacktraces"],
                "automation_potential": "medium",
                "records_count": 3,
                "statistical_reliability": "low",
                "centroid": [0.1, 0.2],
            }
        )
        c = store.get_cluster("code_help:cluster_0")
        assert c is not None
        assert c["name"] == "Bugfix helpers"
        assert c["pain_points"] == ["unclear stacktraces"]
        assert c["centroid"] == [0.1, 0.2]
        assert len(store.list_clusters()) == 1

        store.put_job(
            {
                "job_id": "rc_1",
                "status": "running",
                "clusters_created": 0,
                "scenarios_named": 0,
                "created_at": "2026-07-25T00:00:00Z",
            }
        )
        store.put_job(
            {
                "job_id": "rc_1",
                "status": "completed",
                "clusters_created": 2,
                "scenarios_named": 2,
                "completed_at": "2026-07-25T00:01:00Z",
                "fallback_used": False,
            }
        )
        job = store.get_job("rc_1")
        assert job is not None
        assert job["status"] == "completed"
        assert job["clusters_created"] == 2
        assert job.get("fallback_used") is False

        store.bump_ingest_log("src_a", accepted=2, rejected=1)
        store.bump_ingest_log("src_a", accepted=1, classified=2, assigned=2)
        # no public getter — statistics still works
        store.upsert_assignment(
            {
                "request_id": "x1",
                "task_type": "code_help",
                "scenario_id": "code_help:cluster_0",
                "source_id": "src_a",
                "timestamp": "2026-07-25T12:00:00Z",
                "is_outlier": True,
                "has_failure_signals": True,
            }
        )
        stats = store.get_statistics(source_id="src_a")
        assert stats["total_logs"] == 1
        assert stats["outliers"] == 1
        assert stats["failure_rate"] == 1.0
    finally:
        store.close()


def test_pagination():
    store = MetaStore(":memory:")
    try:
        for i in range(5):
            store.upsert_assignment(
                {
                    "request_id": f"p{i}",
                    "task_type": "other",
                    "source_id": "s",
                    "timestamp": f"2026-07-0{i + 1}T00:00:00Z",
                }
            )
        page1 = store.list_assignments(limit=2, offset=0)
        page2 = store.list_assignments(limit=2, offset=2)
        assert page1["total"] == 5
        assert len(page1["items"]) == 2
        assert len(page2["items"]) == 2
        ids = {x["request_id"] for x in page1["items"] + page2["items"]}
        assert len(ids) == 4
    finally:
        store.close()
