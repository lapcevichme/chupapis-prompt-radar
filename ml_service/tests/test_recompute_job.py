"""Tests for recompute job + store."""
from __future__ import annotations

import asyncio

from app.recompute.job import RecomputeJob, RecomputeStore


def test_recompute_job_small_fallback():
    store = RecomputeStore()
    job = RecomputeJob(store=store)
    data = [
        {
            "request_id": f"r{i}",
            "task_type": "code_help",
            "embedding": [0.1 * i] * 8,
        }
        for i in range(3)
    ]
    result = asyncio.run(job.run(data))
    assert result["status"] == "completed"
    assert result["fallback_used"] is True
    assert result["clusters_created"] >= 1
    assert store.get_job(job.job_id)["status"] == "completed"
