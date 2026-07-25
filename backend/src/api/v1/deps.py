from typing import Annotated, Any, AsyncGenerator

from fastapi import Depends, Header, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings, get_settings
from core.errors import UnauthorizedError
from database.relational_db import User, get_session_factory
from service.analytics import AnalyticsService
from service.auth import AuthService
from service.dashboard import DashboardService
from service.ingestion import IngestionService
from service.recompute import RecomputeService
from service.roi import RoiService


SettingsDep = Annotated[Settings, Depends(get_settings)]


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_db_session)]


def get_ingestion_service(
    session: SessionDep, settings: SettingsDep
) -> IngestionService:
    return IngestionService(session, settings)


def get_dashboard_service(
    session: SessionDep, settings: SettingsDep
) -> DashboardService:
    return DashboardService(session, settings)


def get_roi_service(session: SessionDep, settings: SettingsDep) -> RoiService:
    return RoiService(session, settings)


def get_analytics_service(
    session: SessionDep, settings: SettingsDep
) -> AnalyticsService:
    return AnalyticsService(session, settings)


def get_recompute_service(settings: SettingsDep) -> RecomputeService:
    return RecomputeService(settings)


def dashboard_filters(
    source_id: str | None = Query(None),
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
) -> dict[str, Any]:
    """Common dashboard filters: source_id / from / to."""
    return {"source_id": source_id, "from": from_, "to": to}


FiltersDep = Annotated[dict[str, Any], Depends(dashboard_filters)]
IngestionServiceDep = Annotated[IngestionService, Depends(get_ingestion_service)]
DashboardServiceDep = Annotated[DashboardService, Depends(get_dashboard_service)]
RoiServiceDep = Annotated[RoiService, Depends(get_roi_service)]
AnalyticsServiceDep = Annotated[AnalyticsService, Depends(get_analytics_service)]
RecomputeServiceDep = Annotated[RecomputeService, Depends(get_recompute_service)]



def get_auth_service(session: SessionDep, settings: SettingsDep) -> AuthService:
    return AuthService(session, settings)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


async def get_current_user(request: Request, service: AuthServiceDep) -> User:
    return await service.user_from_access(request.cookies.get("access_token"))


CurrentUserDep = Annotated[User, Depends(get_current_user)]


async def require_ingest_token(
    settings: SettingsDep,
    x_ingest_token: Annotated[str | None, Header(alias="X-Ingest-Token")] = None,
) -> None:
    expected = settings.INGEST_TOKEN
    if expected and x_ingest_token != expected:
        raise UnauthorizedError("Invalid or missing X-Ingest-Token")
