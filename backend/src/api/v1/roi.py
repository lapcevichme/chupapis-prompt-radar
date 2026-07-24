from typing import Literal

from fastapi import APIRouter, Query, Response

from domain.roi import Roi
from service.export import roi_to_csv, roi_to_xlsx
from service.export.roi_export import CSV_CONTENT_TYPE, XLSX_CONTENT_TYPE

from .deps import FiltersDep, RoiServiceDep

router = APIRouter(tags=["roi"])


def _rate_overrides(
    fte_hourly_rate_rub: float | None,
    token_cost_per_1k_rub: float | None,
) -> dict[str, float]:
    return {
        k: v
        for k, v in {
            "fte_hourly_rate_rub": fte_hourly_rate_rub,
            "token_cost_per_1k_rub": token_cost_per_1k_rub,
        }.items()
        if v is not None
    }


@router.get("/roi", response_model=Roi)
async def get_roi(
    service: RoiServiceDep,
    filters: FiltersDep,
    fte_hourly_rate_rub: float | None = Query(None, gt=0),
    token_cost_per_1k_rub: float | None = Query(None, gt=0),
) -> Roi:
    overrides = _rate_overrides(fte_hourly_rate_rub, token_cost_per_1k_rub)
    return await service.get_roi(filters, overrides)


@router.get("/export")
async def export_roi(
    service: RoiServiceDep,
    filters: FiltersDep,
    format: Literal["csv", "xlsx"] = Query("xlsx"),
    fte_hourly_rate_rub: float | None = Query(None, gt=0),
    token_cost_per_1k_rub: float | None = Query(None, gt=0),
) -> Response:
    overrides = _rate_overrides(fte_hourly_rate_rub, token_cost_per_1k_rub)
    roi = await service.get_roi(filters, overrides)

    if format == "csv":
        body = roi_to_csv(roi)
        media_type = CSV_CONTENT_TYPE
        filename = "prompt_radar_roi.csv"
    else:
        body = roi_to_xlsx(roi)
        media_type = XLSX_CONTENT_TYPE
        filename = "prompt_radar_roi.xlsx"

    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
