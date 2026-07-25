from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings
from core.errors import SourceNotFoundError
from database.relational_db import DatasetRecord, LogAssignment
from domain.roi import Roi

from .calculator import RoiConfig, RoiRecord, compute_roi


class RoiService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    async def get_roi(
        self,
        filters: dict[str, Any],
        rate_overrides: dict[str, float] | None = None,
    ) -> Roi:
        records = await self._load_records(filters)
        config = self._build_config(rate_overrides or {})
        return compute_roi(records, config)

    async def _load_records(self, filters: dict[str, Any]) -> list[RoiRecord]:
        query = select(
            DatasetRecord.status,
            DatasetRecord.tokens,
            DatasetRecord.manual_time_minutes,
            DatasetRecord.tools_used,
            DatasetRecord.style,
            DatasetRecord.user_id,
            DatasetRecord.user_name,
            DatasetRecord.department,
            LogAssignment.task_type,
            LogAssignment.scenario_id,
            LogAssignment.scenario_name,
        ).select_from(
            DatasetRecord.__table__.outerjoin(
                LogAssignment.__table__,
                (LogAssignment.source_id == DatasetRecord.source_id)
                & (LogAssignment.request_id == DatasetRecord.request_id),
            )
        )

        if filters.get("source_id"):
            query = query.where(
                DatasetRecord.source_id == _as_uuid(filters["source_id"])
            )
        if filters.get("from"):
            query = query.where(DatasetRecord.timestamp >= filters["from"])
        if filters.get("to"):
            query = query.where(DatasetRecord.timestamp <= filters["to"])

        rows = (await self._session.execute(query)).all()
        return [
            RoiRecord(
                status=row.status,
                tokens=row.tokens or 0,
                manual_time_minutes=row.manual_time_minutes or 0.0,
                tools_used=list(row.tools_used or []),
                style=row.style or "formal",
                user_id=row.user_id or "unknown_user",
                user_name=row.user_name or "Unknown",
                department=row.department or "Unknown",
                task_type=row.task_type,
                scenario_id=row.scenario_id,
                scenario_name=row.scenario_name,
            )
            for row in rows
        ]

    def _build_config(self, overrides: dict[str, float]) -> RoiConfig:
        s = self._settings
        return RoiConfig(
            fte_hourly_rate_rub=overrides.get(
                "fte_hourly_rate_rub", s.ROI_FTE_HOURLY_RATE_RUB
            ),
            token_cost_per_1k_rub=overrides.get(
                "token_cost_per_1k_rub", s.ROI_TOKEN_COST_PER_1K_RUB
            ),
            coeff_short=s.ROI_SESSION_COEFF_SHORT,
            coeff_medium=s.ROI_SESSION_COEFF_MEDIUM,
            coeff_long=s.ROI_SESSION_COEFF_LONG,
            short_max_tokens=s.ROI_SESSION_SHORT_MAX_TOKENS,
            long_min_tokens=s.ROI_SESSION_LONG_MIN_TOKENS,
        )


def _as_uuid(value: Any) -> UUID:
    try:
        return UUID(str(value))
    except (ValueError, AttributeError) as exc:
        raise SourceNotFoundError() from exc
