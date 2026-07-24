"""Scheduler smoke + opt-in from_config."""
from __future__ import annotations

import asyncio
import os

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


def test_from_config_default_off():
    assert Scheduler.from_config({}) is None
    assert Scheduler.from_config({"recompute": {"interval_hours": 2}}) is None
    assert (
        Scheduler.from_config(
            {"recompute": {"scheduler_enabled": False, "interval_hours": 1}}
        )
        is None
    )


def test_from_config_enabled():
    sched = Scheduler.from_config(
        {"recompute": {"scheduler_enabled": True, "interval_hours": 1.5}}
    )
    assert sched is not None
    assert abs(sched.interval_seconds - 1.5 * 3600) < 1e-6


def test_from_config_env_enable(monkeypatch):
    monkeypatch.setenv("RECOMPUTE_SCHEDULER_ENABLED", "true")
    sched = Scheduler.from_config({"recompute": {"interval_hours": 0.5}})
    assert sched is not None
    monkeypatch.delenv("RECOMPUTE_SCHEDULER_ENABLED", raising=False)
