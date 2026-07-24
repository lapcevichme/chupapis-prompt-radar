"""Async ingest queue for log batches."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional


class IngestQueue:
    """Thin asyncio.Queue wrapper for batches of log dicts."""

    def __init__(self, maxsize: int = 0):
        self._queue: asyncio.Queue[List[Dict[str, Any]]] = asyncio.Queue(maxsize=maxsize)

    async def enqueue(self, logs: List[Dict[str, Any]]) -> None:
        if not logs:
            return
        await self._queue.put(logs)

    async def get(self) -> List[Dict[str, Any]]:
        return await self._queue.get()

    def task_done(self) -> None:
        self._queue.task_done()

    def qsize(self) -> int:
        return self._queue.qsize()

    def empty(self) -> bool:
        return self._queue.empty()

    async def join(self) -> None:
        await self._queue.join()
