import json

from fastapi import APIRouter, BackgroundTasks, Request, status

from core.errors import DatasetInvalidError
from domain.ingestion import ProcessingStatus, SourceOut
from service.ingestion.service import stream_source_logs

from .deps import IngestionServiceDep, SettingsDep

router = APIRouter(tags=["ingestion"])


@router.get("/ingest/status", response_model=ProcessingStatus)
async def ingest_status(service: IngestionServiceDep) -> ProcessingStatus:
    """Live indexing progress across all sources + recompute state (app-wide banner)."""
    return await service.processing_status()


@router.post("/ingest", response_model=SourceOut, status_code=status.HTTP_202_ACCEPTED)
async def ingest(
    request: Request,
    background: BackgroundTasks,
    service: IngestionServiceDep,
    settings: SettingsDep,
) -> SourceOut:
    """Accept a multipart file or JSON {use_demo:true}; stream to ML in background."""
    content_type = request.headers.get("content-type", "")

    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        upload = form.get("file")
        if upload is None or isinstance(upload, str):
            raise DatasetInvalidError("multipart field 'file' is required")
        raw_bytes = await upload.read()
        result = await service.ingest(raw_bytes=raw_bytes, filename=upload.filename)
    else:
        body_bytes = await request.body()
        body = json.loads(body_bytes) if body_bytes else {}
        if not bool(body.get("use_demo")):
            raise DatasetInvalidError('Provide a file or JSON {"use_demo": true}')
        result = await service.ingest(use_demo=True)

    background.add_task(
        stream_source_logs, settings, result.source_id, result.log_records
    )
    return result.source_out
