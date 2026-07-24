from fastapi import APIRouter, Query

from domain.roi import Roi

from .deps import FiltersDep, RoiServiceDep

router = APIRouter(tags=["roi"])


@router.get("/roi", response_model=Roi)
async def get_roi(
    service: RoiServiceDep,
    filters: FiltersDep,
    fte_hourly_rate_rub: float | None = Query(None, gt=0),
    token_cost_per_1k_rub: float | None = Query(None, gt=0),
) -> Roi:
    overrides = {
        k: v
        for k, v in {
            "fte_hourly_rate_rub": fte_hourly_rate_rub,
            "token_cost_per_1k_rub": token_cost_per_1k_rub,
        }.items()
        if v is not None
    }
    return await service.get_roi(filters, overrides)
