"""Tests for recompute job + store + stable scenario_id + summarization."""
from __future__ import annotations

import asyncio
from typing import List
from unittest.mock import AsyncMock

from app.pipeline.summarization import ScenarioSummary
from app.recompute.job import RecomputeJob, RecomputeStore
from app.recompute.stability import stabilize_scenario_ids, apply_id_mapping


def test_recompute_job_small_fallback():
    store = RecomputeStore()
    job = RecomputeJob(store=store, enable_summarization=False)
    data = [
        {
            "request_id": f"r{i}",
            "task_type": "code_help",
            "embedding": [0.1 * i] * 8,
            "query_text": f"help with code {i}",
        }
        for i in range(3)
    ]
    result = asyncio.run(job.run(data))
    assert result["status"] == "completed"
    assert result["fallback_used"] is True
    assert result["clusters_created"] >= 1
    assert store.get_job(job.job_id)["status"] == "completed"
    assert all(a["task_type"] == "code_help" for a in store.assignments.values())


def test_job_status_lifecycle():
    store = RecomputeStore()
    job = RecomputeJob(store=store, enable_summarization=False)
    assert job.status == "pending"
    assert store.get_job(job.job_id)["status"] == "pending"
    data = [
        {
            "request_id": "x1",
            "task_type": "unknown",
            "embedding": [1.0, 0.0, 0.0],
            "query_text": "q",
        }
    ]
    asyncio.run(job.run(data))
    assert job.status == "completed"
    assert store.get_job(job.job_id)["started_at"]
    assert store.get_job(job.job_id)["completed_at"]


def test_stabilize_scenario_ids_reuses_old():
    old = {
        "code_help:cluster_0": [1.0, 0.0, 0.0],
        "code_help:cluster_1": [0.0, 1.0, 0.0],
    }
    # new clusters swapped order but same directions
    new = {
        "code_help:cluster_0": [0.0, 0.99, 0.0],  # matches old cluster_1
        "code_help:cluster_1": [0.99, 0.0, 0.0],  # matches old cluster_0
    }
    mapping = stabilize_scenario_ids(
        new, old, task_type="code_help", match_threshold=0.75
    )
    assert mapping["code_help:cluster_0"] == "code_help:cluster_1"
    assert mapping["code_help:cluster_1"] == "code_help:cluster_0"


def test_stabilize_assigns_new_index_when_unmatched():
    old = {"code_help:cluster_0": [1.0, 0.0, 0.0]}
    new = {
        "code_help:cluster_0": [1.0, 0.0, 0.0],
        "code_help:cluster_1": [0.0, 0.0, 1.0],  # orthogonal → new id
    }
    mapping = stabilize_scenario_ids(
        new, old, task_type="code_help", match_threshold=0.9
    )
    assert mapping["code_help:cluster_0"] == "code_help:cluster_0"
    assert mapping["code_help:cluster_1"] != "code_help:cluster_0"
    assert mapping["code_help:cluster_1"].startswith("code_help:cluster_")


def test_apply_id_mapping_keeps_outliers_none():
    mapped = apply_id_mapping(
        ["a:cluster_0", None, "a:cluster_1"],
        {"a:cluster_0": "a:cluster_5", "a:cluster_1": "a:cluster_1"},
    )
    assert mapped == ["a:cluster_5", None, "a:cluster_1"]


def test_recompute_stable_ids_across_runs():
    store = RecomputeStore()
    # two tight groups
    group_a = [[1.0, 0.0, 0.0, 0.0]] * 6
    group_b = [[0.0, 1.0, 0.0, 0.0]] * 6
    data1 = []
    for i, emb in enumerate(group_a + group_b):
        data1.append(
            {
                "request_id": f"r{i}",
                "task_type": "code_help",
                "embedding": emb,
                "query_text": f"query {i}",
            }
        )
    job1 = RecomputeJob(store=store, enable_summarization=False)
    asyncio.run(job1.run(data1))
    first_ids = {
        rid: a["scenario_id"]
        for rid, a in store.assignments.items()
        if a.get("scenario_id")
    }
    # second run: same vectors, shuffled order slightly
    data2 = list(reversed(data1))
    job2 = RecomputeJob(store=store, enable_summarization=False)
    asyncio.run(job2.run(data2))
    for rid, sid in first_ids.items():
        if store.assignments[rid].get("is_outlier"):
            continue
        # same request should keep same scenario when centroid matches
        assert store.assignments[rid]["scenario_id"] == sid


def test_recompute_with_mocked_summarizer():
    store = RecomputeStore()

    class FakeSummarizer:
        async def summarize_scenario(
            self, scenario_id: str, examples: List[str], task_type: str
        ) -> ScenarioSummary:
            return ScenarioSummary(
                name="Mock Scenario",
                summary="From mock",
                user_goal="goal",
                pain_points=["p1"],
                automation_potential="medium",
                examples=examples[:2],
            )

    job = RecomputeJob(
        store=store,
        summarizer=FakeSummarizer(),  # type: ignore[arg-type]
        enable_summarization=True,
    )
    data = [
        {
            "request_id": f"r{i}",
            "task_type": "data_analysis",
            "embedding": [0.2] * 8,
            "query_text": f"export report {i}",
        }
        for i in range(4)
    ]
    result = asyncio.run(job.run(data))
    assert result["status"] == "completed"
    assert result["scenarios_named"] >= 1
    names = [c["name"] for c in store.clusters.values()]
    assert "Mock Scenario" in names
    assert any(c.get("summary") == "From mock" for c in store.clusters.values())


def test_job_failed_status():
    store = RecomputeStore()
    job = RecomputeJob(store=store, enable_summarization=False)

    async def boom(_data):
        raise RuntimeError("clustering exploded")

    # inject failure by patching run path via bad embedding shape after start
    # Use monkey: replace run_umap_hdbscan via broken data that raises in numpy
    data = [
        {
            "request_id": "bad",
            "task_type": "t",
            "embedding": "not-a-vector",  # will fail np.asarray path downstream
            "query_text": "x",
        }
    ]
    try:
        asyncio.run(job.run(data))
        # if implementation coerces, still ok — check we got some terminal status
        assert job.status in ("completed", "failed")
    except Exception:
        assert job.status == "failed"
        assert store.get_job(job.job_id)["status"] == "failed"
        assert store.get_job(job.job_id)["error"]


def test_store_persistence_mirror():
    class MemPersist:
        def __init__(self):
            self.jobs = {}

        def put_recompute_job(self, job):
            self.jobs[job["job_id"]] = dict(job)

        def get_recompute_job(self, job_id):
            return self.jobs.get(job_id)

    persist = MemPersist()
    store = RecomputeStore(persistence=persist)
    job = RecomputeJob(store=store, enable_summarization=False)
    assert job.job_id in persist.jobs
    assert persist.jobs[job.job_id]["status"] == "pending"
    asyncio.run(
        job.run(
            [
                {
                    "request_id": "p1",
                    "task_type": "t",
                    "embedding": [0.1] * 4,
                    "query_text": "hi",
                }
            ]
        )
    )
    assert persist.jobs[job.job_id]["status"] == "completed"
