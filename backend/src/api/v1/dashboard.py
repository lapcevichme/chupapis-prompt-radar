from fastapi import APIRouter

from domain.dashboard import Dashboard

from .deps import DashboardServiceDep, FiltersDep

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", response_model=Dashboard)
async def get_dashboard(service: DashboardServiceDep, filters: FiltersDep) -> Dashboard:
    return await service.get_dashboard(filters)
