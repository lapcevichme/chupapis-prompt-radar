from fastapi import APIRouter

from domain.common import Paginated
from domain.ingestion import SourceOut

from .deps import IngestionServiceDep

router = APIRouter(tags=["ingestion"])


@router.get("/sources", response_model=Paginated[SourceOut])
async def list_sources(service: IngestionServiceDep) -> Paginated[SourceOut]:
    return await service.list_sources()


@router.get("/sources/{source_id}", response_model=SourceOut)
async def get_source(source_id: str, service: IngestionServiceDep) -> SourceOut:
    return await service.get_source(source_id)
