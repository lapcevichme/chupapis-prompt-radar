from fastapi import APIRouter

from domain.common import Paginated
from domain.dashboard import ScenarioOut

from .deps import DashboardServiceDep, FiltersDep

router = APIRouter(tags=["dashboard"])


@router.get("/scenarios", response_model=Paginated[ScenarioOut])
async def list_scenarios(
    service: DashboardServiceDep, filters: FiltersDep
) -> Paginated[ScenarioOut]:
    return await service.get_scenarios(filters)


@router.get("/scenarios/{scenario_id}", response_model=ScenarioOut)
async def get_scenario(scenario_id: str, service: DashboardServiceDep) -> ScenarioOut:
    return await service.get_scenario(scenario_id)
