"""Scheduler smoke test."""
from __future__ import annotations

import asyncio

from app.recompute.scheduler import Scheduler


def test_scheduler_max_runs():
    calls = {"n": 0}

    async def tick():
        calls["n"] += 1

    async def run():
        sched = Scheduler(interval_hours=0)
        await sched.start(tick, max_runs=2, run_forever=False)

    asyncio.run(run())
    assert calls["n"] == 2
