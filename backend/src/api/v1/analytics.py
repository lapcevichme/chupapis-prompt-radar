from fastapi import APIRouter

from domain.analytics import ModelsAnalyticsResponse, UsersAnalyticsResponse

from .deps import AnalyticsServiceDep, FiltersDep

router = APIRouter(tags=["analytics"])


@router.get("/analytics/users", response_model=UsersAnalyticsResponse)
async def get_users_analytics(
    service: AnalyticsServiceDep, filters: FiltersDep
) -> UsersAnalyticsResponse:
    return await service.get_users_analytics(filters)


@router.get("/analytics/models", response_model=ModelsAnalyticsResponse)
async def get_models_analytics(
    service: AnalyticsServiceDep, filters: FiltersDep
) -> ModelsAnalyticsResponse:
    return await service.get_models_analytics(filters)
