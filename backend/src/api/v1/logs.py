from typing import Any

from fastapi import APIRouter, Query

from domain.common import Paginated
from domain.dashboard import LogItem

from .deps import DashboardServiceDep, FiltersDep

router = APIRouter(tags=["dashboard"])


@router.get("/logs", response_model=Paginated[LogItem])
async def list_logs(
    service: DashboardServiceDep,
    filters: FiltersDep,
    task_type: str | None = Query(None),
    scenario_id: str | None = Query(None),
    only_failures: bool = Query(False),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> Paginated[LogItem]:
    log_filters: dict[str, Any] = {
        **filters,
        "task_type": task_type,
        "scenario_id": scenario_id,
        "only_failures": only_failures,
    }
    return await service.get_logs(log_filters, limit, offset)
