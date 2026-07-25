import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings
from core.errors import DatasetInvalidError, SourceNotFoundError
from database.relational_db import (
    DatasetRecord,
    IngestionSource,
    LogAssignment,
    get_session_factory,
)
from domain.common import Paginated
from domain.ingestion import (
    NormalizationReport,
    ProcessingSourceItem,
    ProcessingStatus,
    SourceOut,
    SourceProgress,
    SourceStatus,
)
from service.ml import MlClient

from .normalizer import _STATUS_MAP, NormalizationResult, normalize, parse_raw
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
        asgn_map = await self._get_assignments_counts()
        items = [_to_out(row, classified_count=asgn_map.get(row.id)) for row in rows]
        return Paginated[SourceOut](items=items, total=len(items))

    async def get_source(self, source_id: str) -> SourceOut:
        sid = _as_uuid(source_id)
        source = await self._session.get(IngestionSource, sid)
        if source is None:
            raise SourceNotFoundError()
        asgn_map = await self._get_assignments_counts(sid)
        progress = await self._source_progress(source)
        return _to_out(
            source,
            source.normalization_report,
            classified_count=asgn_map.get(sid),
            progress=progress,
        )

    async def _get_assignments_counts(
        self, source_id: UUID | None = None
    ) -> dict[UUID, int]:
        """Classified-record counts per source from our local assignment mirror."""
        stmt = (
            select(LogAssignment.source_id, func.count().label("cnt"))
            .where(LogAssignment.task_type.is_not(None))
            .group_by(LogAssignment.source_id)
        )
        if source_id:
            stmt = stmt.where(LogAssignment.source_id == source_id)
        res = await self._session.execute(stmt)
        return {row[0]: row[1] for row in res.all()}

    async def _mirrored_count(self, source_id: UUID) -> int:
        """How many of this source's records already have a log_assignments row."""
        return int((await self._get_assignments_counts(source_id)).get(source_id, 0))

    async def _source_progress(self, source: IngestionSource) -> SourceProgress:
        total = int(source.records_valid or 0)
        if source.status == SourceStatus.recomputed.value:
            classified = total
        else:
            try:
                classified = await MlClient(self._settings).get_assignment_count(
                    str(source.id)
                )
            except Exception:
                classified = await self._mirrored_count(source.id)
        display = min(classified, total) if total else classified
        done = total > 0 and classified >= total
        percent = round(display / total * 100, 1) if total else 0.0
        return SourceProgress(
            classified=display, total=total, percent=percent, done=done
        )

    async def processing_status(self) -> ProcessingStatus:
        """Aggregate live indexing progress for the app-wide banner.

        Side effect: re-mirrors assignments for any source ML has classified further
        than our local mirror, so ``/logs`` fills in as indexing progresses.
        """
        from service.dashboard import DashboardService
        from service.recompute import RecomputeService

        rows = (
            (
                await self._session.execute(
                    select(IngestionSource).order_by(
                        IngestionSource.created_at.desc()
                    )
                )
            )
            .scalars()
            .all()
        )
        client = MlClient(self._settings)
        items: list[ProcessingSourceItem] = []
        total_valid = 0
        total_classified = 0
        indexing = False

        for source in rows:
            valid = int(source.records_valid or 0)
            if source.status == SourceStatus.recomputed.value:
                classified = valid
            else:
                try:
                    classified = await client.get_assignment_count(str(source.id))
                except Exception:
                    classified = await self._mirrored_count(source.id)
                if classified > await self._mirrored_count(source.id):
                    try:
                        await DashboardService(
                            self._session, self._settings
                        ).sync_assignments(str(source.id))
                    except Exception as exc:
                        logger.warning(
                            "progress re-sync failed source_id=%s: %s", source.id, exc
                        )

            display = min(classified, valid) if valid else classified
            done = valid > 0 and classified >= valid
            percent = round(display / valid * 100, 1) if valid else 0.0
            if not done and source.status != SourceStatus.recomputed.value:
                indexing = True
            total_valid += valid
            total_classified += display
            items.append(
                ProcessingSourceItem(
                    source_id=str(source.id),
                    name=source.name,
                    origin=source.origin,
                    status=SourceStatus(source.status),
                    records_total=source.records_total,
                    records_valid=valid,
                    records_rejected=source.records_rejected,
                    classified=display,
                    percent=percent,
                    done=done,
                )
            )

        recompute = await RecomputeService(self._settings).status()
        overall_pct = (
            round(total_classified / total_valid * 100, 1) if total_valid else 0.0
        )
        # Real "new logs since last recompute" comes from the ML read-model; if ML is
        # unreachable we report 0 rather than guessing.
        logs_since = 0
        try:
            freshness = (await client.get_statistics()).get("freshness") or {}
            logs_since = int(freshness.get("logs_since_last_recompute", 0) or 0)
        except Exception as exc:
            logger.warning("freshness lookup failed: %s", exc)

        return ProcessingStatus(
            indexing=indexing,
            total_valid=total_valid,
            total_classified=total_classified,
            percent=overall_pct,
            recompute_status=recompute.status,
            recompute_pending=recompute.status in ("running", "pending", "processing"),
            logs_since_last_recompute=logs_since,
            scenarios_named=int(recompute.scenarios_named or 0),
            sources=items,
        )

    async def rebuild_log_records(self, source_id: str) -> list[dict[str, Any]]:
        """Rebuild ML log records for a source from stored dataset_records.

        Ingestion streams in a FastAPI BackgroundTask, which does not survive a
        backend restart — a large upload can be left half-indexed with no way to
        finish. Records are persisted at ingest time, so we can re-stream them;
        ML deduplicates by ``request_id``, so already-classified rows come back as
        duplicates and only the missing tail is processed.
        """
        sid = _as_uuid(source_id)
        source = await self._session.get(IngestionSource, sid)
        if source is None:
            raise SourceNotFoundError()

        # A previous run may have left this source `failed`; we are re-ingesting it
        # now, so reflect that instead of showing a stale terminal state.
        if source.status == SourceStatus.failed.value:
            source.status = SourceStatus.ingesting.value
            await self._session.commit()

        rows = (
            (
                await self._session.execute(
                    select(DatasetRecord).where(DatasetRecord.source_id == sid)
                )
            )
            .scalars()
            .all()
        )

        records: list[dict[str, Any]] = []
        for row in rows:
            response_status, error_code = _STATUS_MAP.get(
                str(row.status), ("success", None)
            )
            records.append(
                {
                    "request_id": str(row.request_id),
                    "query_text": row.query_text,
                    "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                    "response_status": response_status,
                    "error_code": error_code,
                    "metadata": {
                        "gold_category": row.gold_category,
                        "style": row.style,
                        "user_id": row.user_id,
                        "user_name": row.user_name,
                        "department": row.department,
                        "tokens": row.tokens,
                        "tools_used": row.tools_used or [],
                        "manual_time_minutes": row.manual_time_minutes,
                    },
                }
            )
        return records

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
    """Background: stream logs to ML, then mirror assignments into log_assignments.

    A slow/large dataset (real online embeddings) can outlast the assignment-wait
    without being a failure — ML keeps classifying in the background. We therefore
    only mark ``failed`` when *streaming itself* raises, and always sync best-effort
    so ``/logs`` shows real task_type/confidence even mid-processing. The rest is
    caught up incrementally by ``IngestionService.processing_status`` polls.
    """
    client = MlClient(settings)
    status = SourceStatus.classified.value
    streamed = False
    try:
        totals = await client.stream_logs(source_id, log_records)
        streamed = True
        logger.info("streamed source_id=%s totals=%s", source_id, totals)
        expected = int(totals.get("accepted", 0)) + int(totals.get("duplicates", 0))
        try:
            await client.wait_for_assignment_count(source_id, expected)
        except Exception as wait_exc:
            # Not fatal: ML is still classifying a large batch. Keep status classified;
            # progress polls re-sync the remainder as it lands.
            logger.warning(
                "assignment wait incomplete for source_id=%s: %s", source_id, wait_exc
            )
    except Exception as exc:
        if "timed out" in str(exc).lower() or "timeout" in str(exc).lower():
            logger.warning("streaming wait timed out for source_id=%s, setting classified anyway: %s", source_id, exc)
            status = SourceStatus.classified.value
        else:
            status = SourceStatus.failed.value
            logger.warning("streaming failed for source_id=%s: %s", source_id, exc)

    await _set_status(source_id, status)

    # Best-effort mirror of whatever ML has classified so far (independent of wait).
    if streamed:
        try:
            from service.dashboard import DashboardService

            factory = get_session_factory(settings)
            async with factory() as session:
                synced = await DashboardService(session, settings).sync_assignments(
                    source_id
                )
            logger.info("synced source_id=%s assignments=%s", source_id, synced)
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


def _to_out(
    source: IngestionSource,
    report: dict[str, Any] | None = None,
    classified_count: int | None = None,
    progress: SourceProgress | None = None,
) -> SourceOut:
    normalization = (
        NormalizationReport.model_validate(report) if report is not None else None
    )
    if classified_count is not None and classified_count > 0:
        classified = classified_count
    elif source.status in ("classified", "recomputed"):
        classified = source.records_valid
    else:
        classified = 0

    if source.records_valid > 0:
        pct = round(min(100.0, (classified / source.records_valid) * 100.0), 1)
    elif source.status in ("classified", "recomputed"):
        pct = 100.0
    else:
        pct = 0.0

    return SourceOut(
        source_id=str(source.id),
        name=source.name,
        origin=source.origin,
        records_total=source.records_total,
        records_valid=source.records_valid,
        records_rejected=source.records_rejected,
        records_classified=classified,
        classification_percentage=pct,
        status=SourceStatus(source.status),
        created_at=source.created_at,
        normalization_report=normalization,
        progress=progress,
    )



def _as_uuid(value: str) -> UUID:
    try:
        return UUID(str(value))
    except (ValueError, AttributeError) as exc:
        raise SourceNotFoundError() from exc
