from fastapi import APIRouter, status

from core.errors import DatasetInvalidError
from domain.ingestion import LiveIngestRequest, LiveIngestResponse

from .deps import IngestionServiceDep

router = APIRouter(tags=["live"])


@router.post(
    "/logs",
    response_model=LiveIngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_live(
    payload: LiveIngestRequest,
    service: IngestionServiceDep,
) -> LiveIngestResponse:
    """Live webhook: accept raw log records, normalize, persist, stream to ML."""
    if not payload.logs:
        raise DatasetInvalidError("Provide a non-empty 'logs' list")
    result = await service.ingest_live(payload.logs, source_name=payload.source_name)
    return LiveIngestResponse(**result)
