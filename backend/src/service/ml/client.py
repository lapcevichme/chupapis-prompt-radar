import logging
import asyncio
from typing import Any

import httpx

from core.config import Settings
from core.errors import MLUnavailableError

from .statistics_validation import validate_statistics

logger = logging.getLogger(__name__)


class MlClient:
    """HTTP facade over the ML service (streaming CQRS contract, backend-ml.md)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base = (settings.ML_SERVICE_URL or "").rstrip("/")
        self._headers = {"X-Service-Token": settings.ML_SERVICE_TOKEN}
        self._timeout = settings.ML_HTTP_TIMEOUT_SEC

    def _client(self) -> httpx.AsyncClient:
        if not self._base:
            raise MLUnavailableError("ML_SERVICE_URL is not configured")
        return httpx.AsyncClient(
            base_url=self._base, headers=self._headers, timeout=self._timeout
        )

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            async with self._client() as client:
                response = await client.request(method, path, **kwargs)
                response.raise_for_status()
                return response.json()
        except MLUnavailableError:
            raise
        except httpx.HTTPStatusError as exc:
            logger.warning("ML %s %s -> %s", method, path, exc.response.status_code)
            raise MLUnavailableError(
                f"ML returned {exc.response.status_code} for {path}"
            ) from exc
        except httpx.HTTPError as exc:
            logger.warning("ML %s %s failed: %s", method, path, exc)
            raise MLUnavailableError(f"ML request to {path} failed") from exc

    async def stream_logs(
        self, source_id: str, records: list[dict[str, Any]]
    ) -> dict[str, int]:
        """Stream normalized logs to PUT /logs in batches; aggregate counters."""
        batch_size = max(1, self._settings.ML_INGEST_BATCH_SIZE)
        totals = {"accepted": 0, "duplicates": 0, "rejected": 0}

        for start in range(0, len(records), batch_size):
            batch = [
                {**rec, "source_id": source_id}
                for rec in records[start : start + batch_size]
            ]
            payload = {"source_id": source_id, "logs": batch}
            result = await self._request("PUT", "/api/v1/logs", json=payload)
            for key in totals:
                totals[key] += int(result.get(key, 0))

        return totals

    async def recompute(self, scope: str = "all") -> dict[str, Any]:
        return await self._request("POST", "/api/v1/recompute", json={"scope": scope})

    async def get_recompute_status(self, job_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/api/v1/recompute/{job_id}")

    async def get_statistics(
        self, filters: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        payload = await self._request(
            "GET", "/api/v1/statistics", params=_clean(filters)
        )
        return validate_statistics(payload)

    async def get_assignments(
        self, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Fetch all assignment pages for the given filters."""
        params = _clean(filters)
        limit = int(params.get("limit", 500) or 500)
        offset = int(params.get("offset", 0) or 0)
        items: list[dict[str, Any]] = []

        while True:
            page = await self._request(
                "GET",
                "/api/v1/assignments",
                params={**params, "limit": limit, "offset": offset},
            )
            page_items = page.get("items", [])
            items.extend(page_items)
            total = int(page.get("total", len(items)))
            offset += len(page_items)
            if not page_items or offset >= total:
                break

        return items

    async def get_assignment_count(self, source_id: str) -> int:
        page = await self._request(
            "GET",
            "/api/v1/assignments",
            params={"source_id": source_id, "limit": 1, "offset": 0},
        )
        return int(page.get("total", 0))

    async def wait_for_assignment_count(self, source_id: str, expected: int) -> int:
        """Wait until the asynchronous ML worker persisted this source's assignments."""
        if expected <= 0:
            return 0

        timeout = float(self._settings.ML_PROCESSING_TIMEOUT_SEC)
        interval = max(0.1, float(self._settings.ML_PROCESSING_POLL_INTERVAL_SEC))
        deadline = asyncio.get_running_loop().time() + timeout
        observed = 0
        while True:
            observed = await self.get_assignment_count(source_id)
            if observed >= expected:
                return observed
            if asyncio.get_running_loop().time() >= deadline:
                raise MLUnavailableError(
                    f"ML processing timed out for source {source_id}: "
                    f"expected {expected}, observed {observed}"
                )
            await asyncio.sleep(interval)

    async def get_scenarios(
        self, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        payload = await self._request(
            "GET", "/api/v1/scenarios", params=_clean(filters)
        )
        return payload.get("items", [])


def _clean(filters: dict[str, Any] | None) -> dict[str, Any]:
    """Drop None-valued query params."""
    if not filters:
        return {}
    return {k: v for k, v in filters.items() if v is not None}
