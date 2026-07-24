from fastapi import APIRouter, BackgroundTasks, status

from domain.recompute import RecomputeJob, RecomputeStatus
from service.recompute import finalize_recompute

from .deps import RecomputeServiceDep, SettingsDep

router = APIRouter(tags=["recompute"])


@router.post(
    "/recompute", response_model=RecomputeJob, status_code=status.HTTP_202_ACCEPTED
)
async def recompute(
    background: BackgroundTasks,
    service: RecomputeServiceDep,
    settings: SettingsDep,
) -> RecomputeJob:
    """Proxy recompute to ML; poll + sync assignments in background."""
    job = await service.trigger()
    background.add_task(finalize_recompute, settings, job.job_id)
    return job


@router.get("/recompute/status", response_model=RecomputeStatus)
async def recompute_status(service: RecomputeServiceDep) -> RecomputeStatus:
    return await service.status()
