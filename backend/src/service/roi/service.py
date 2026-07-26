from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings
from core.errors import SourceNotFoundError
from database.relational_db import DatasetRecord, LogAssignment
from domain.roi import FteRateModel, Roi, TokenCostModel

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
            func.length(DatasetRecord.query_text).label("query_chars"),
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
                query_chars=row.query_chars or 0,
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
        # Rates come from a stated derivation (monthly salary / infra economics).
        # A what-if query parameter beats the derivation, and says so via
        # `is_overridden` so the UI never presents a manual figure as derived.
        fte_rate = overrides.get("fte_hourly_rate_rub", s.roi_fte_hourly_rate)
        token_cost = overrides.get("token_cost_per_1k_rub", s.roi_token_cost_per_1k)

        return RoiConfig(
            fte_hourly_rate_rub=fte_rate,
            token_cost_per_1k_rub=token_cost,
            coeff_short=s.ROI_SESSION_COEFF_SHORT,
            coeff_medium=s.ROI_SESSION_COEFF_MEDIUM,
            coeff_long=s.ROI_SESSION_COEFF_LONG,
            short_max_tokens=s.ROI_SESSION_SHORT_MAX_TOKENS,
            long_min_tokens=s.ROI_SESSION_LONG_MIN_TOKENS,
            fte_rate_model=FteRateModel(
                monthly_rate_rub=s.ROI_FTE_MONTHLY_RATE_RUB,
                work_hours_per_month=s.ROI_WORK_HOURS_PER_MONTH,
                derived_hourly_rate_rub=round(s.roi_fte_hourly_rate, 2),
                is_overridden="fte_hourly_rate_rub" in overrides,
            ),
            token_cost_model=TokenCostModel(
                mandated_per_mln_rub=s.ROI_TOKEN_COST_PER_MLN_RUB,
                infra_capex_rub=s.ROI_INFRA_CAPEX_RUB,
                amortization_years=s.ROI_INFRA_AMORTIZATION_YEARS,
                electricity_rub_per_year=s.ROI_INFRA_ELECTRICITY_RUB_PER_YEAR,
                tokens_per_year=s.ROI_INFRA_TOKENS_PER_YEAR,
                infra_derived_per_1k_rub=round(s.roi_infra_token_cost_per_1k, 4),
                derived_cost_per_1k_rub=round(s.roi_token_cost_per_1k, 4),
                is_overridden="token_cost_per_1k_rub" in overrides,
            ),
            analysis_chars_per_token=s.ROI_ANALYSIS_CHARS_PER_TOKEN,
            analysis_tokens_per_scenario=s.ROI_ANALYSIS_TOKENS_PER_SCENARIO,
        )


def _as_uuid(value: Any) -> UUID:
    try:
        return UUID(str(value))
    except (ValueError, AttributeError) as exc:
        raise SourceNotFoundError() from exc
