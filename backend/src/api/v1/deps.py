from typing import Annotated, Any, AsyncGenerator

from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings, get_settings
from database.relational_db import get_session_factory
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
RecomputeServiceDep = Annotated[RecomputeService, Depends(get_recompute_service)]
