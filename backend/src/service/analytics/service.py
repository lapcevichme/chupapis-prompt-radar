import logging
from datetime import timedelta
from statistics import median
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings
from core.errors import SourceNotFoundError
from database.relational_db import DatasetRecord, LogAssignment
from domain.analytics import (
    DepartmentUserAnalytics,
    ModelAnalyticsSummary,
    ModelItemAnalytics,
    ModelsAnalyticsResponse,
    PersonaDistItem,
    UserAnalyticsSummary,
    UserItemAnalytics,
    UsersAnalyticsResponse,
)
from domain.taxonomy import label
from service.roi.calculator import (
    DEFAULT_CATEGORY_MANUAL_MINUTES,
    DEFAULT_FALLBACK_MANUAL_MINUTES,
    RoiConfig,
)

logger = logging.getLogger(__name__)

PERSONA_LABELS = {
    "code_craftsman": "Разработчик (Code)",
    "analyst": "Аналитик данных",
    "super_user": "AI Super-User",
    "generalist": "Универсал",
    "casual": "Эпизодический",
}

# Trailing window for the "active users" metric, in days.
ACTIVE_WINDOW_DAYS = 7

# Frustration index = weighted blend of failure-signal share and outlier share.
# Both come from ML assignments; the weights are a product judgement, not a
# measurement, and are surfaced as such in the docs/contract.
FRUSTRATION_FAILURE_WEIGHT = 0.6
FRUSTRATION_OUTLIER_WEIGHT = 0.4

# Persona thresholds. Volume rules are relative to the cohort median so the
# distribution cannot collapse into a single bucket on large datasets.
PERSONA_SPECIALIST_SHARE = 0.35
PERSONA_SUPER_USER_MIN_CATEGORIES = 5
PERSONA_CASUAL_MEDIAN_FRACTION = 0.5

SUCCESS_STATUSES = ("success", "ok", "completed")


class AnalyticsService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    async def get_users_analytics(self, filters: dict[str, Any]) -> UsersAnalyticsResponse:
        rows = await self._fetch_joined_records(filters)
        if not rows:
            return UsersAnalyticsResponse(
                summary=UserAnalyticsSummary(
                    total_users=0,
                    active_users_l7=0,
                    active_window_days=ACTIVE_WINDOW_DAYS,
                    avg_frustration_index=0.0,
                    personas_distribution=[],
                ),
                by_department=[],
                users=[],
            )

        roi_config = self._roi_config()

        # Group records by user
        user_map: dict[str, list[Any]] = {}
        for r in rows:
            uid = r.user_id or r.user_name or "Anonymous"
            user_map.setdefault(uid, []).append(r)

        # "Active in the last N days" is measured against the newest timestamp in
        # the filtered data, not wall-clock now: demo datasets are historical and
        # a wall-clock window would report zero active users.
        all_timestamps = [r.timestamp for r in rows if r.timestamp]
        window_start = (
            max(all_timestamps) - timedelta(days=ACTIVE_WINDOW_DAYS)
            if all_timestamps
            else None
        )

        query_counts = [len(u_rows) for u_rows in user_map.values()]
        median_queries = median(query_counts) if query_counts else 0.0

        # First pass: per-user facts that persona assignment depends on.
        profiles: list[dict[str, Any]] = []
        for uid, u_rows in user_map.items():
            total_queries = len(u_rows)
            active_dates = {r.timestamp.date() for r in u_rows if r.timestamp}

            cat_counts: dict[str, int] = {}
            failure_count = 0
            outlier_count = 0
            saved_minutes = 0.0
            for r in u_rows:
                ttype = r.task_type or r.gold_category or "unknown"
                cat_counts[ttype] = cat_counts.get(ttype, 0) + 1
                if r.has_failure_signals or r.status in (
                    "error",
                    "error_tool",
                    "hallucination_loop",
                ):
                    failure_count += 1
                if r.is_outlier:
                    outlier_count += 1
                saved_minutes += _saved_minutes(r, roi_config)

            profiles.append(
                {
                    "user_id": uid,
                    "user_name": u_rows[0].user_name or uid,
                    "department": u_rows[0].department or "Общий",
                    "total_queries": total_queries,
                    "active_dates": active_dates,
                    "cat_counts": cat_counts,
                    "failure_count": failure_count,
                    "outlier_count": outlier_count,
                    "saved_minutes": saved_minutes,
                }
            )

        user_items: list[UserItemAnalytics] = []
        dept_map: dict[str, list[UserItemAnalytics]] = {}
        persona_counts: dict[str, int] = {}
        active_users = 0

        for p in profiles:
            total_queries = p["total_queries"]
            cat_counts = p["cat_counts"]
            active_dates = p["active_dates"]

            if window_start is not None and any(d >= window_start.date() for d in active_dates):
                active_users += 1

            top_cat = max(cat_counts, key=cat_counts.get) if cat_counts else "unknown"
            persona = _classify_persona(cat_counts, total_queries, median_queries)
            persona_counts[persona] = persona_counts.get(persona, 0) + 1

            fail_pct = (p["failure_count"] / total_queries) * 100
            outlier_pct = (p["outlier_count"] / total_queries) * 100
            frustration = round(
                fail_pct * FRUSTRATION_FAILURE_WEIGHT
                + outlier_pct * FRUSTRATION_OUTLIER_WEIGHT,
                1,
            )
            needs_guidance = frustration > 15.0 or (
                persona == "casual" and total_queries < 5
            )

            u_item = UserItemAnalytics(
                user_id=p["user_id"],
                user_name=p["user_name"],
                department=p["department"],
                persona=persona,
                persona_label=PERSONA_LABELS.get(persona, persona),
                total_queries=total_queries,
                active_days=len(active_dates),
                saved_hours=round(p["saved_minutes"] / 60.0, 1),
                frustration_index=frustration,
                top_category=label(top_cat),
                needs_guidance=needs_guidance,
                recommendation=_build_user_recommendation(
                    persona, frustration, top_cat, needs_guidance
                ),
            )
            user_items.append(u_item)
            dept_map.setdefault(p["department"], []).append(u_item)

        dept_items = [
            DepartmentUserAnalytics(
                department=d_name,
                users_count=len(d_users),
                total_queries=sum(u.total_queries for u in d_users),
                avg_saved_hours=round(sum(u.saved_hours for u in d_users), 1),
                frustration_index=round(
                    sum(u.frustration_index for u in d_users) / len(d_users), 1
                ),
            )
            for d_name, d_users in dept_map.items()
        ]

        total_u = len(user_items)
        avg_frust = round(sum(u.frustration_index for u in user_items) / total_u, 1)

        personas_dist = [
            PersonaDistItem(
                persona=p,
                label=PERSONA_LABELS.get(p, p),
                count=cnt,
                percentage=round((cnt / total_u) * 100, 1),
            )
            for p, cnt in sorted(
                persona_counts.items(), key=lambda kv: kv[1], reverse=True
            )
            if cnt > 0
        ]

        return UsersAnalyticsResponse(
            summary=UserAnalyticsSummary(
                total_users=total_u,
                active_users_l7=active_users,
                active_window_days=ACTIVE_WINDOW_DAYS,
                avg_frustration_index=avg_frust,
                personas_distribution=personas_dist,
            ),
            by_department=sorted(
                dept_items, key=lambda d: d.total_queries, reverse=True
            ),
            users=sorted(user_items, key=lambda x: x.total_queries, reverse=True),
        )

    async def get_models_analytics(self, filters: dict[str, Any]) -> ModelsAnalyticsResponse:
        """Report only models the data source actually named.

        Model identity comes from a `model:<id>` entry in `tools_used`, written by
        the normalizer from a raw `model` / `model_name` / `agent_id` field. Records
        without that metadata are excluded rather than attributed to a guess.
        """
        rows = await self._fetch_joined_records(filters)

        model_groups: dict[str, list[Any]] = {}
        for r in rows:
            m_id = _extract_model_name(r)
            if m_id is None:
                continue
            model_groups.setdefault(m_id, []).append(r)

        if not model_groups:
            return ModelsAnalyticsResponse(
                summary=ModelAnalyticsSummary(
                    status="not_available",
                    total_models_detected=0,
                    total_queries_with_model=0,
                    total_tokens=0,
                ),
                models=[],
            )

        total_with_model = sum(len(v) for v in model_groups.values())
        model_items: list[ModelItemAnalytics] = []
        total_tokens_all = 0

        for m_id, m_rows in model_groups.items():
            m_queries = len(m_rows)
            m_tokens = sum(r.tokens or 0 for r in m_rows)
            total_tokens_all += m_tokens

            failures = sum(
                1
                for r in m_rows
                if r.has_failure_signals or r.status in ("error", "error_tool")
            )

            ttype_cnt: dict[str, int] = {}
            for r in m_rows:
                tt = r.task_type or r.gold_category or "unknown"
                ttype_cnt[tt] = ttype_cnt.get(tt, 0) + 1
            top_ttype = max(ttype_cnt, key=ttype_cnt.get) if ttype_cnt else "unknown"

            model_items.append(
                ModelItemAnalytics(
                    model_id=m_id,
                    model_name=m_id,
                    total_queries=m_queries,
                    share_percentage=round((m_queries / total_with_model) * 100, 1),
                    total_tokens=m_tokens,
                    failure_rate_percent=round((failures / m_queries) * 100, 1),
                    top_task_type=label(top_ttype),
                )
            )

        return ModelsAnalyticsResponse(
            summary=ModelAnalyticsSummary(
                status="available",
                total_models_detected=len(model_items),
                total_queries_with_model=total_with_model,
                total_tokens=total_tokens_all,
            ),
            models=sorted(model_items, key=lambda x: x.total_queries, reverse=True),
        )

    def _roi_config(self) -> RoiConfig:
        s = self._settings
        return RoiConfig(
            fte_hourly_rate_rub=s.ROI_FTE_HOURLY_RATE_RUB,
            token_cost_per_1k_rub=s.ROI_TOKEN_COST_PER_1K_RUB,
            coeff_short=s.ROI_SESSION_COEFF_SHORT,
            coeff_medium=s.ROI_SESSION_COEFF_MEDIUM,
            coeff_long=s.ROI_SESSION_COEFF_LONG,
            short_max_tokens=s.ROI_SESSION_SHORT_MAX_TOKENS,
            long_min_tokens=s.ROI_SESSION_LONG_MIN_TOKENS,
        )

    async def _fetch_joined_records(self, filters: dict[str, Any]) -> list[Any]:
        query = (
            select(
                DatasetRecord.request_id,
                DatasetRecord.query_text,
                DatasetRecord.gold_category,
                DatasetRecord.user_id,
                DatasetRecord.user_name,
                DatasetRecord.department,
                DatasetRecord.tokens,
                DatasetRecord.manual_time_minutes,
                DatasetRecord.tools_used,
                DatasetRecord.status,
                DatasetRecord.timestamp,
                LogAssignment.task_type,
                LogAssignment.is_outlier,
                LogAssignment.has_failure_signals,
            )
            .select_from(
                DatasetRecord.__table__.outerjoin(
                    LogAssignment.__table__,
                    (LogAssignment.source_id == DatasetRecord.source_id)
                    & (LogAssignment.request_id == DatasetRecord.request_id),
                )
            )
        )

        source_id = filters.get("source_id")
        if source_id:
            query = query.where(DatasetRecord.source_id == _as_uuid(source_id))
        if filters.get("from"):
            query = query.where(DatasetRecord.timestamp >= filters["from"])
        if filters.get("to"):
            query = query.where(DatasetRecord.timestamp <= filters["to"])

        res = await self._session.execute(query)
        return list(res.all())


def _saved_minutes(record: Any, config: RoiConfig) -> float:
    """Saved minutes for one record, using the same rule as the ROI calculator.

    Only successful records save time, and manual time is scaled by the session
    coefficient (D6). Keeping this identical to `compute_roi` means the Users
    screen and the ROI screen cannot disagree about hours saved.
    """
    status = (record.status or "").strip().lower()
    if status not in SUCCESS_STATUSES:
        return 0.0

    manual = record.manual_time_minutes
    if not manual or manual <= 0.0:
        cat_key = record.task_type or record.gold_category or "unknown"
        manual = DEFAULT_CATEGORY_MANUAL_MINUTES.get(
            cat_key, DEFAULT_FALLBACK_MANUAL_MINUTES
        )
    return manual * config.session_coeff(record.tokens or 0)


def _classify_persona(
    cat_counts: dict[str, int], total_queries: int, median_queries: float
) -> str:
    """Assign a usage archetype from category mix and cohort-relative volume."""
    code_share = cat_counts.get("code_help", 0) / total_queries
    data_share = (
        cat_counts.get("data_analysis", 0) + cat_counts.get("information_search", 0)
    ) / total_queries

    if code_share >= PERSONA_SPECIALIST_SHARE:
        return "code_craftsman"
    if data_share >= PERSONA_SPECIALIST_SHARE:
        return "analyst"
    if (
        len(cat_counts) >= PERSONA_SUPER_USER_MIN_CATEGORIES
        and total_queries >= median_queries
    ):
        return "super_user"
    if total_queries < max(5.0, median_queries * PERSONA_CASUAL_MEDIAN_FRACTION):
        return "casual"
    return "generalist"


def _build_user_recommendation(
    persona: str, frustration: float, top_cat: str, needs_guidance: bool
) -> str:
    if frustration > 20.0:
        return f"Высокий процент повторов в «{label(top_cat)}». Рекомендуется предоставить готовый шаблон промпта."
    if persona == "code_craftsman":
        return "Пользователь активно генерирует и отлаживает код. Рекомендуется интегрировать IDE-агента."
    if persona == "analyst":
        return "Основная ценность — разбор документов и поиск данных. Эффективно использует автоматизацию."
    if persona == "super_user":
        return "Лидер внедрения ИИ. Использует широкий спектр сценариев с высокой эффективностью."
    if persona == "generalist":
        return "Ровное использование по нескольким категориям. Рекомендуется показать продвинутые сценарии."
    return "Эпизодическое использование. Рекомендуется вводный вебинар по возможностям ИИ-агентов."


def _extract_model_name(record: Any) -> str | None:
    """Return the model named by the record, or None when it carries no model metadata."""
    for tool in record.tools_used or []:
        if isinstance(tool, str) and tool.startswith("model:"):
            model_id = tool.removeprefix("model:").strip()
            if model_id:
                return model_id
    return None


def _as_uuid(val: Any) -> UUID:
    try:
        return val if isinstance(val, UUID) else UUID(str(val))
    except Exception as exc:
        raise SourceNotFoundError() from exc
