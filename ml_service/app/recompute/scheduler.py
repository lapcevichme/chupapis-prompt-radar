"""Optional periodic recompute trigger (asyncio, no Celery). Default: off."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any, Optional

logger = logging.getLogger(__name__)


class Scheduler:
    """Periodic async scheduler for recompute."""

    def __init__(self, interval_hours: float = 2.0) -> None:
        self.interval_seconds = max(0.0, float(interval_hours) * 3600.0)
        self.running = False
        self._task: asyncio.Task | None = None

    @classmethod
    def from_config(cls, config: Optional[dict[str, Any]] = None) -> Optional["Scheduler"]:
        """
        Build scheduler only when explicitly enabled.

        config.recompute.scheduler_enabled: false by default (opt-in).
        Env RECOMPUTE_SCHEDULER_ENABLED=true also enables.
        """
        import os

        cfg = (config or {}).get("recompute") or {}
        env_on = os.getenv("RECOMPUTE_SCHEDULER_ENABLED", "").lower() in (
            "1",
            "true",
            "yes",
        )
        enabled = bool(cfg.get("scheduler_enabled", False)) or env_on
        if not enabled:
            return None
        hours = float(cfg.get("interval_hours", 2))
        if hours <= 0:
            logger.warning("recompute.interval_hours <= 0 — scheduler not started")
            return None
        return cls(interval_hours=hours)

    async def start(
        self,
        task: Callable[[], Awaitable[None]],
        *,
        max_runs: int | None = None,
        run_forever: bool = True,
    ) -> None:
        """Run task every interval. For tests: max_runs=1, run_forever=False."""
        self.running = True
        runs = 0
        limit = max_runs if max_runs is not None else (None if run_forever else 1)
        while self.running:
            if limit is not None and runs >= limit:
                break
            try:
                t0 = time.time()
                await task()
                runs += 1
                elapsed = time.time() - t0
                sleep_for = max(0.0, self.interval_seconds - elapsed)
                if limit is not None and runs >= limit:
                    break
                if sleep_for > 0:
                    await asyncio.sleep(sleep_for)
            except asyncio.CancelledError:
                break
            except Exception as exc:  # noqa: BLE001
                logger.exception("Error in scheduler task: %s", exc)

    def stop(self) -> None:
        self.running = False
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None

    def start_background(
        self,
        loop: asyncio.AbstractEventLoop,
        task: Callable[[], Awaitable[None]],
    ) -> asyncio.Task:
        self._task = loop.create_task(self.start(task, run_forever=True))
        return self._task
