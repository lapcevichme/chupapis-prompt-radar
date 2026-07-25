import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings
from core.errors import DatasetInvalidError, SourceNotFoundError
from database.relational_db import DatasetRecord, IngestionSource, get_session_factory
from domain.common import Paginated
from domain.ingestion import NormalizationReport, SourceOut, SourceStatus
from service.ml import MlClient

from .normalizer import NormalizationResult, normalize, parse_raw
from .preloaded import PreloadedDatasetSpec, load_preloaded_records

logger = logging.getLogger(__name__)


@dataclass
class IngestResult:
    source_out: SourceOut
    source_id: str
    log_records: list[dict[str, Any]]


class IngestionService:
    """Ingest a dataset, persist raw ROI fields, hand off to background streaming."""

    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    async def ingest(
        self,
        *,
        raw_bytes: bytes | None = None,
        use_demo: bool = False,
        filename: str | None = None,
    ) -> IngestResult:
        if use_demo:
            raw_bytes, filename = self._load_demo()
        if raw_bytes is None:
            raise DatasetInvalidError("No dataset provided")

        name = filename or "dataset.json"
        raw_records = parse_raw(raw_bytes, name)
        source_id = uuid4()
        result = normalize(
            raw_records,
            self._settings,
            request_namespace=str(source_id),
        )

        return await self._persist_dataset(
            source_id=source_id,
            name=name,
            origin="demo" if use_demo else "upload",
            result=result,
        )

    async def ensure_preloaded(
        self, spec: PreloadedDatasetSpec
    ) -> tuple[IngestResult, bool]:
        """Create a deterministic preloaded source or return it for reconciliation."""
        raw_records = load_preloaded_records(self._settings, spec)
        result = normalize(
            raw_records,
            self._settings,
            request_namespace=str(spec.source_id),
        )
        existing = await self._session.get(IngestionSource, spec.source_id)
        if existing is not None:
            return (
                IngestResult(
                    source_out=_to_out(existing, existing.normalization_report),
                    source_id=str(existing.id),
                    log_records=result.log_records,
                ),
                False,
            )

        persisted = await self._persist_dataset(
            source_id=spec.source_id,
            name=spec.name,
            origin="preloaded",
            result=result,
        )
        return persisted, True

    async def _persist_dataset(
        self,
        *,
        source_id: UUID,
        name: str,
        origin: str,
        result: NormalizationResult,
    ) -> IngestResult:

        source = IngestionSource(
            id=source_id,
            name=name,
            origin=origin,
            records_total=result.report["records_total"],
            records_valid=result.report["records_valid"],
            records_rejected=result.report["records_rejected"],
            normalization_report=result.report,
            status=SourceStatus.ingesting.value,
        )
        self._session.add(source)
        await self._session.flush()

        self._session.add_all(
            [
                DatasetRecord(
                    source_id=source.id,
                    request_id=row.request_id,
                    query_text=row.query_text,
                    gold_category=row.gold_category,
                    style=row.style,
                    user_id=row.user_id,
                    user_name=row.user_name,
                    department=row.department,
                    tokens=row.tokens,
                    manual_time_minutes=row.manual_time_minutes,
                    tools_used=row.tools_used,
                    status=row.status,
                    timestamp=row.timestamp,
                )
                for row in result.dataset_rows
            ]
        )
        await self._session.commit()

        return IngestResult(
            source_out=_to_out(source, result.report),
            source_id=str(source.id),
            log_records=result.log_records,
        )

    async def list_sources(self) -> Paginated[SourceOut]:
        rows = (
            (
                await self._session.execute(
                    select(IngestionSource).order_by(IngestionSource.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
        items = [_to_out(row) for row in rows]
        return Paginated[SourceOut](items=items, total=len(items))

    async def get_source(self, source_id: str) -> SourceOut:
        source = await self._session.get(IngestionSource, _as_uuid(source_id))
        if source is None:
            raise SourceNotFoundError()
        return _to_out(source, source.normalization_report)

    def _load_demo(self) -> tuple[bytes, str]:
        path = Path(self._settings.DEMO_DATASET_PATH)
        if not path.exists():
            raise DatasetInvalidError(f"Demo dataset not found at {path}")
        return path.read_bytes(), path.name

    async def ingest_live(
        self, raw_records: list[dict[str, Any]], source_name: str = "live"
    ) -> dict[str, Any]:
        """Append live records to a rolling source and stream them to ML now."""
        source = await self._get_or_create_live_source(source_name)
        result = normalize(
            raw_records,
            self._settings,
            id_prefix=f"live_{uuid4().hex[:8]}_",
            request_namespace=str(source.id),
        )
        self._session.add_all(
            [
                DatasetRecord(
                    source_id=source.id,
                    request_id=row.request_id,
                    query_text=row.query_text,
                    gold_category=row.gold_category,
                    style=row.style,
                    user_id=row.user_id,
                    user_name=row.user_name,
                    department=row.department,
                    tokens=row.tokens,
                    manual_time_minutes=row.manual_time_minutes,
                    tools_used=row.tools_used,
                    status=row.status,
                    timestamp=row.timestamp,
                )
                for row in result.dataset_rows
            ]
        )
        source.records_total += result.report["records_total"]
        source.records_valid += result.report["records_valid"]
        source.records_rejected += result.report["records_rejected"]
        await self._session.commit()

        totals = await MlClient(self._settings).stream_logs(
            str(source.id), result.log_records
        )

        from service.dashboard.cache import invalidate as invalidate_stats

        invalidate_stats()  # new live logs -> dashboard totals changed
        return {
            "source_id": str(source.id),
            "accepted": int(totals.get("accepted", result.report["records_valid"])),
            "duplicates": int(totals.get("duplicates", 0)),
            "rejected": int(totals.get("rejected", 0)),
            "records_valid": result.report["records_valid"],
            "records_rejected": result.report["records_rejected"],
        }

    async def _get_or_create_live_source(self, name: str) -> IngestionSource:
        existing = await self._session.scalar(
            select(IngestionSource).where(
                IngestionSource.name == name,
                IngestionSource.origin == "live",
            )
        )
        if existing is not None:
            return existing
        source = IngestionSource(
            name=name,
            origin="live",
            records_total=0,
            records_valid=0,
            records_rejected=0,
            status=SourceStatus.classified.value,
        )
        self._session.add(source)
        await self._session.flush()
        return source


async def stream_source_logs(
    settings: Settings, source_id: str, log_records: list[dict[str, Any]]
) -> None:
    """Background: stream logs to ML, then set source status classified | failed."""
    client = MlClient(settings)
    status = SourceStatus.classified.value
    try:
        totals = await client.stream_logs(source_id, log_records)
        logger.info("streamed source_id=%s totals=%s", source_id, totals)
        expected = int(totals.get("accepted", 0)) + int(totals.get("duplicates", 0))
        await client.wait_for_assignment_count(source_id, expected)
    except Exception as exc:
        status = SourceStatus.failed.value
        logger.warning("streaming failed for source_id=%s: %s", source_id, exc)

    await _set_status(source_id, status)

    if status == SourceStatus.classified.value:
        # Online assignments exist right after streaming; pull them for /logs and ROI.
        try:
            from service.dashboard import DashboardService

            factory = get_session_factory(settings)
            async with factory() as session:
                await DashboardService(session, settings).sync_assignments(source_id)
        except Exception as exc:
            logger.warning(
                "assignment sync failed for source_id=%s: %s", source_id, exc
            )

        from service.dashboard.cache import invalidate as invalidate_stats

        invalidate_stats()  # fresh classified logs -> refresh dashboard read-model


async def _set_status(source_id: str, status: str) -> None:
    from core.config import get_settings

    factory = get_session_factory(get_settings())
    async with factory() as session:
        source = await session.get(IngestionSource, _as_uuid(source_id))
        if source is not None:
            source.status = status
            await session.commit()


def _to_out(source: IngestionSource, report: dict[str, Any] | None = None) -> SourceOut:
    normalization = (
        NormalizationReport.model_validate(report) if report is not None else None
    )
    return SourceOut(
        source_id=str(source.id),
        name=source.name,
        origin=source.origin,
        records_total=source.records_total,
        records_valid=source.records_valid,
        records_rejected=source.records_rejected,
        status=SourceStatus(source.status),
        created_at=source.created_at,
        normalization_report=normalization,
    )


def _as_uuid(value: str) -> UUID:
    try:
        return UUID(str(value))
    except (ValueError, AttributeError) as exc:
        raise SourceNotFoundError() from exc
