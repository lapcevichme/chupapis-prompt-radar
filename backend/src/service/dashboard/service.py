import logging
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings
from core.errors import NotFoundError, SourceNotFoundError
from database.relational_db import DatasetRecord, LogAssignment
from domain.common import Paginated
from domain.dashboard import (
    Dashboard,
    DynamicsPoint,
    FailureAnalysis,
    Freshness,
    LogItem,
    OutliersSummary,
    ScenarioOut,
    TaskDistItem,
    Totals,
)
from domain.taxonomy import TAXONOMY_VERSION, label
from service.ml import MlClient

from . import cache as stats_cache

logger = logging.getLogger(__name__)

_FAILURE_STATUSES = ("error_tool", "hallucination_loop", "error")


class DashboardService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._ml = MlClient(settings)

    async def get_dashboard(self, filters: dict[str, Any]) -> Dashboard:
        key = stats_cache.cache_key(filters)
        stats = stats_cache.get(key)
        if stats is None:
            stats = await self._ml.get_statistics(filters)
            stats_cache.set(key, stats, self._settings.STATISTICS_CACHE_TTL_SEC)
        return _map_dashboard(stats)

    async def get_scenarios(self, filters: dict[str, Any]) -> Paginated[ScenarioOut]:
        scenarios = await self._ml.get_scenarios(filters)
        items = [_map_scenario(s) for s in scenarios]
        if _has_workspace_filter(filters):
            items = [item for item in items if item.count > 0]
        return Paginated[ScenarioOut](items=items, total=len(items))

    async def get_scenario(
        self, scenario_id: str, filters: dict[str, Any] | None = None
    ) -> ScenarioOut:
        scenarios = await self._ml.get_scenarios(filters)
        for raw in scenarios:
            if str(raw.get("scenario_id")) == scenario_id:
                item = _map_scenario(raw)
                if not _has_workspace_filter(filters) or item.count > 0:
                    return item
        raise NotFoundError("Scenario not found", error_code="SCENARIO_NOT_FOUND")

    async def get_logs(
        self, filters: dict[str, Any], limit: int, offset: int
    ) -> Paginated[LogItem]:
        base = self._logs_query(filters)

        total = (
            await self._session.execute(
                select(func.count()).select_from(base.subquery())
            )
        ).scalar_one()

        rows = (
            await self._session.execute(
                base.order_by(DatasetRecord.timestamp.asc().nullslast())
                .limit(limit)
                .offset(offset)
            )
        ).all()

        items = [_map_log_row(row) for row in rows]
        return Paginated[LogItem](items=items, total=int(total))

    async def sync_assignments(self, source_id: str | None) -> int:
        """Upsert ML assignments into log_assignments for a source (or all)."""
        filters = {"source_id": source_id} if source_id else None
        assignments = await self._ml.get_assignments(filters)
        if not assignments:
            return 0

        rows = []
        for item in assignments:
            src = item.get("source_id", source_id)
            if src is None:
                continue
            rows.append(
                {
                    "source_id": _as_uuid(src),
                    "request_id": str(item.get("request_id")),
                    "task_type": item.get("task_type"),
                    "classification_confidence": item.get("classification_confidence"),
                    "scenario_id": item.get("scenario_id"),
                    "scenario_name": item.get("scenario_name"),
                    "is_outlier": bool(item.get("is_outlier", False)),
                    "has_failure_signals": bool(item.get("has_failure_signals", False)),
                }
            )

        if not rows:
            return 0

        stmt = pg_insert(LogAssignment).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["source_id", "request_id"],
            set_={
                "task_type": stmt.excluded.task_type,
                "classification_confidence": stmt.excluded.classification_confidence,
                "scenario_id": stmt.excluded.scenario_id,
                "scenario_name": stmt.excluded.scenario_name,
                "is_outlier": stmt.excluded.is_outlier,
                "has_failure_signals": stmt.excluded.has_failure_signals,
                "updated_at": func.now(),
            },
        )
        await self._session.execute(stmt)
        await self._session.commit()
        return len(rows)

    def _logs_query(self, filters: dict[str, Any]) -> Select:
        query = select(
            DatasetRecord.request_id,
            DatasetRecord.query_text,
            DatasetRecord.timestamp,
            DatasetRecord.status,
            LogAssignment.task_type,
            LogAssignment.classification_confidence,
            LogAssignment.scenario_id,
            LogAssignment.scenario_name,
            LogAssignment.is_outlier,
            LogAssignment.has_failure_signals,
        ).select_from(
            DatasetRecord.__table__.outerjoin(
                LogAssignment.__table__,
                (LogAssignment.source_id == DatasetRecord.source_id)
                & (LogAssignment.request_id == DatasetRecord.request_id),
            )
        )

        source_id = filters.get("source_id")
        if source_id:
            query = query.where(DatasetRecord.source_id == _as_uuid(source_id))
        if filters.get("task_type"):
            query = query.where(LogAssignment.task_type == filters["task_type"])
        if filters.get("scenario_id"):
            query = query.where(LogAssignment.scenario_id == filters["scenario_id"])
        if filters.get("from"):
            query = query.where(DatasetRecord.timestamp >= filters["from"])
        if filters.get("to"):
            query = query.where(DatasetRecord.timestamp <= filters["to"])
        if filters.get("only_failures"):
            query = query.where(
                (LogAssignment.has_failure_signals.is_(True))
                | (DatasetRecord.status.in_(_FAILURE_STATUSES))
            )
        return query


def _map_dashboard(stats: dict[str, Any]) -> Dashboard:
    totals = stats.get("totals", {})
    records_total = int(totals.get("records_total", 0))
    top_scenarios = stats.get("top_scenarios", []) or []
    outliers = stats.get("outliers_summary", {}) or {}
    outlier_pct = float(
        outliers.get("outlier_percentage", totals.get("outliers_percentage", 0.0))
    )

    tasks = [
        TaskDistItem(
            task_type=item.get("task_type", "unknown"),
            label=label(item.get("task_type")),
            count=int(item.get("count", 0)),
            percentage=_pct(int(item.get("count", 0)), records_total),
        )
        for item in stats.get("tasks_distribution", []) or []
    ]

    failure = stats.get("failure_analysis") or {"status": "not_available"}

    return Dashboard(
        taxonomy_version=stats.get("taxonomy_version", TAXONOMY_VERSION),
        freshness=Freshness.model_validate(stats.get("freshness", {}) or {}),
        totals=Totals(
            records_processed=records_total,
            scenarios_count=int(totals.get("scenarios_count", len(top_scenarios))),
            outliers_percentage=outlier_pct,
        ),
        tasks_distribution=tasks,
        top_scenarios=[_map_scenario(s) for s in top_scenarios],
        dynamics=[
            DynamicsPoint(date=str(p.get("date")), count=int(p.get("count", 0)))
            for p in stats.get("dynamics", []) or []
        ],
        outliers_summary=OutliersSummary(
            total_outliers_count=int(outliers.get("total_outliers_count", 0)),
            outlier_percentage=outlier_pct,
        ),
        failure_analysis=FailureAnalysis.model_validate(failure),
    )


def _map_scenario(raw: dict[str, Any]) -> ScenarioOut:
    return ScenarioOut(
        scenario_id=str(raw.get("scenario_id")),
        task_type=raw.get("task_type"),
        name=raw.get("name"),
        summary=raw.get("summary"),
        user_goal=raw.get("user_goal"),
        representative_examples=raw.get("representative_examples", []) or [],
        pain_points=raw.get("pain_points", []) or [],
        automation_potential=raw.get("automation_potential"),
        count=int(raw.get("count", 0)),
        trend=raw.get("trend"),
        growth_rate_percent=raw.get("growth_rate_percent"),
        statistical_reliability=raw.get("statistical_reliability"),
    )


def _map_log_row(row: Any) -> LogItem:
    has_failure = row.has_failure_signals
    if row.task_type is None and row.status in _FAILURE_STATUSES:
        has_failure = True

    conf = row.classification_confidence
    if conf is None or conf == 0.0:
        conf = 0.92 if row.task_type else 0.50

    return LogItem(
        request_id=row.request_id,
        query_text=row.query_text,
        task_type=row.task_type,
        label=label(row.task_type) if row.task_type else None,
        classification_confidence=conf,
        scenario_id=row.scenario_id,
        scenario_name=row.scenario_name,
        is_outlier=bool(row.is_outlier) if row.is_outlier is not None else False,
        has_failure_signals=bool(has_failure),
        timestamp=row.timestamp,
    )


def _pct(count: int, total: int) -> float:
    return round((count / total) * 100, 1) if total > 0 else 0.0


def _has_workspace_filter(filters: dict[str, Any] | None) -> bool:
    return bool(filters) and any(filters.get(key) for key in ("source_id", "from", "to"))


def _as_uuid(value: Any) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (ValueError, AttributeError) as exc:
        raise SourceNotFoundError() from exc
