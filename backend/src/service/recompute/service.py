import asyncio
import logging

from sqlalchemy import update

from core.config import Settings, get_settings
from database.relational_db import IngestionSource, get_session_factory
from domain.ingestion import SourceStatus
from domain.recompute import RecomputeJob, RecomputeStatus
from service.ml import MlClient

logger = logging.getLogger(__name__)

# One-process MVP: remember the last triggered recompute job (D1, streaming CQRS).
_LAST_JOB_ID: str | None = None


class RecomputeService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._ml = MlClient(settings)

    async def trigger(self) -> RecomputeJob:
        global _LAST_JOB_ID
        result = await self._ml.recompute()
        _LAST_JOB_ID = str(result.get("job_id"))
        return RecomputeJob(
            job_id=_LAST_JOB_ID,
            status=str(result.get("status", "running")),
            started_at=result.get("started_at"),
        )

    async def status(self) -> RecomputeStatus:
        if not _LAST_JOB_ID:
            return RecomputeStatus(status="idle")
        result = await self._ml.get_recompute_status(_LAST_JOB_ID)
        return RecomputeStatus(
            job_id=str(result.get("job_id", _LAST_JOB_ID)),
            status=str(result.get("status", "running")),
            clusters_created=result.get("clusters_created"),
            scenarios_named=result.get("scenarios_named"),
            finished_at=result.get("finished_at") or result.get("completed_at"),
        )

    @property
    def last_job_id(self) -> str | None:
        return _LAST_JOB_ID


async def finalize_recompute(settings: Settings, job_id: str) -> None:
    """Background: poll ML until done, then sync assignments and mark recomputed."""
    client = MlClient(settings)
    completed = False
    deadline = asyncio.get_running_loop().time() + settings.ML_RECOMPUTE_TIMEOUT_SEC
    while asyncio.get_running_loop().time() < deadline:
        try:
            result = await client.get_recompute_status(job_id)
        except Exception as exc:
            logger.warning("recompute poll failed job_id=%s: %s", job_id, exc)
            return
        status = str(result.get("status"))
        if status == "completed":
            completed = True
            break
        if status == "failed":
            logger.warning("recompute job_id=%s failed", job_id)
            return
        await asyncio.sleep(1)

    if not completed:
        logger.warning("recompute job_id=%s did not complete in time", job_id)
        return

    from service.dashboard import DashboardService
    from service.dashboard.cache import invalidate as invalidate_stats

    factory = get_session_factory(settings or get_settings())
    async with factory() as session:
        synced = await DashboardService(session, settings).sync_assignments(None)
        await session.execute(
            update(IngestionSource)
            .where(IngestionSource.status != SourceStatus.failed.value)
            .values(status=SourceStatus.recomputed.value)
        )
        await session.commit()
        invalidate_stats()  # new clusters/scenarios -> drop stale dashboard cache
        logger.info("recompute finalized job_id=%s synced=%s", job_id, synced)
