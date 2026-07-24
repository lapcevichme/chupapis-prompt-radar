"""Async ingest workers: pull batches from queue, process with concurrency limit."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional

from app.ingest.queue import IngestQueue

logger = logging.getLogger(__name__)

ProcessFn = Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]


class IngestWorker:
    """
    Spawns `concurrency` consumers that drain IngestQueue.
    process_fn(log_dict) -> assignment dict (or rejected marker).
    """

    def __init__(
        self,
        queue: IngestQueue,
        process_fn: ProcessFn,
        *,
        concurrency: int = 8,
    ):
        self.queue = queue
        self.process_fn = process_fn
        self.concurrency = max(1, int(concurrency))
        self._running = False
        self._tasks: List[asyncio.Task[Any]] = []
        self._sem = asyncio.Semaphore(self.concurrency)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        # one dispatcher loop + per-item concurrency via semaphore
        self._tasks = [asyncio.create_task(self._worker_loop(), name="ingest-worker")]
        logger.info("IngestWorker started concurrency=%s", self.concurrency)

    async def stop(self) -> None:
        self._running = False
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            try:
                await t
            except asyncio.CancelledError:
                pass
        self._tasks.clear()
        logger.info("IngestWorker stopped")

    async def _worker_loop(self) -> None:
        while self._running:
            try:
                logs = await asyncio.wait_for(self.queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            try:
                await self._process_batch(logs)
            except Exception:  # noqa: BLE001
                logger.exception("ingest batch failed size=%s", len(logs))
            finally:
                self.queue.task_done()

    async def _process_batch(self, logs: List[Dict[str, Any]]) -> None:
        async def _one(log: Dict[str, Any]) -> None:
            async with self._sem:
                try:
                    await self.process_fn(log)
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "Failed to process request_id=%s", log.get("request_id")
                    )

        await asyncio.gather(*[_one(log) for log in logs])
