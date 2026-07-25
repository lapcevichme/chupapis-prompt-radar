from fastapi import APIRouter, BackgroundTasks, status

from domain.common import Paginated
from domain.ingestion import SourceOut
from service.ingestion.service import stream_source_logs

from .deps import IngestionServiceDep, SettingsDep

router = APIRouter(tags=["ingestion"])


@router.get("/sources", response_model=Paginated[SourceOut])
async def list_sources(service: IngestionServiceDep) -> Paginated[SourceOut]:
    return await service.list_sources()


@router.get("/sources/{source_id}", response_model=SourceOut)
async def get_source(source_id: str, service: IngestionServiceDep) -> SourceOut:
    return await service.get_source(source_id)


@router.post(
    "/sources/{source_id}/resume",
    response_model=SourceOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def resume_source(
    source_id: str,
    background: BackgroundTasks,
    service: IngestionServiceDep,
    settings: SettingsDep,
) -> SourceOut:
    """Re-stream a source's stored records to ML to finish a stalled indexing run.

    ML deduplicates by request_id, so this only processes the records that never
    made it (e.g. the backend restarted mid-ingest).
    """
    records = await service.rebuild_log_records(source_id)
    background.add_task(stream_source_logs, settings, source_id, records)
    return await service.get_source(source_id)
