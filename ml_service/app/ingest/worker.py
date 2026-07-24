import asyncio
from typing import List, Dict
from app.ingest.queue import IngestQueue
from app.core.config import settings

class IngestWorker:
    def __init__(self):
        self.queue = IngestQueue()
        self._running = False

    async def start(self):
        self._running = True
        asyncio.create_task(self._worker_loop())

    async def _worker_loop(self):
        while self._running:
            logs = await self.queue.queue.get()
            # Process in background
            asyncio.create_task(self._process_batch(logs))
            self.queue.queue.task_done()

    async def _process_batch(self, logs: List[Dict]):
        # Mock classification, embedding, clustering
        # For phase 1
        for log in logs:
            log["task_type"] = "mock_task"
            log["scenario_id"] = f"mock:{hash(str(log.get('request_id', ''))) % 1000}"
            log["is_outlier"] = False
            log["has_failure_signals"] = False
            # Store
            pass

    async def stop(self):
        self._running = False