from dataclasses import dataclass, field
from typing import Any

from domain.roi import (
    AnalysisCostModel,
    Assumptions,
    FteRateModel,
    PayoffVerdict,
    Roi,
    RoiByCategory,
    RoiByScenario,
    RoiSummary,
    SessionCoefficients,
    TokenCostModel,
    UserStats,
)
from domain.taxonomy import label


@dataclass
class RoiConfig:
    """ROI rates, session coefficients and token thresholds (from env / overrides)."""

    fte_hourly_rate_rub: float
    token_cost_per_1k_rub: float
    coeff_short: float
    coeff_medium: float
    coeff_long: float
    short_max_tokens: int
    long_min_tokens: int
    # Derivations behind the two rates above; carried through to `assumptions` so
    # the numbers can be audited rather than taken on trust.
    fte_rate_model: FteRateModel | None = None
    token_cost_model: TokenCostModel | None = None
    # Cost of running our own analysis over these records.
    analysis_chars_per_token: float = 3.0
    analysis_tokens_per_scenario: float = 1100.0

    def session_coeff(self, tokens: int) -> float:
        if tokens <= self.short_max_tokens:
            return self.coeff_short
        if tokens >= self.long_min_tokens:
            return self.coeff_long
        return self.coeff_medium


@dataclass
class RoiRecord:
    """One joined row: dataset_records × log_assignments."""

    status: str | None
    tokens: int
    manual_time_minutes: float
    tools_used: list[Any]
    task_type: str | None
    scenario_id: str | None
    scenario_name: str | None
    query_chars: int = 0
    user_id: str | None = "unknown_user"
    user_name: str | None = "Unknown"
    department: str | None = "Unknown"
    style: str | None = "formal"


@dataclass
class _Bucket:
    count: int = 0
    success_count: int = 0
    saved_minutes: float = 0.0
    tokens_used: int = 0
    name: str | None = None
    task_type: str | None = None
    tools: dict[str, int] = field(default_factory=dict)


# Manual handling time per task class, used when a record carries no measured
# `estimated_manual_time_minutes`. Keys are exactly taxonomy v1 (7 classes) —
# earlier revisions listed classes the classifier never emits (code_generation,
# debugging, data_transformation, document_analysis), which were dead entries,
# while `other` was missing and silently fell through to the 15-minute default.
#
# NOTE: the generated datasets no longer ship a measured manual time, so this
# table drives the whole FTE calculation. It is an explicit assumption, not a
# measurement, and is returned in `Roi.assumptions.manual_minutes_by_category`.
DEFAULT_CATEGORY_MANUAL_MINUTES: dict[str, float] = {
    "text_generation": 15.0,
    "code_help": 30.0,
    "data_analysis": 45.0,
    "education": 20.0,
    "information_search": 15.0,
    "task_management": 25.0,
    "other": 15.0,
}
DEFAULT_FALLBACK_MANUAL_MINUTES: float = 15.0


def compute_roi(records: list[RoiRecord], config: RoiConfig) -> Roi:
    """Merged ROI calculator: session coefficients, MAU/Depts, and style analytics (D6)."""
    assumptions = Assumptions(
        fte_hourly_rate_rub=config.fte_hourly_rate_rub,
        token_cost_per_1k_rub=config.token_cost_per_1k_rub,
        session_coefficients=SessionCoefficients(
            short=config.coeff_short,
            medium=config.coeff_medium,
            long=config.coeff_long,
        ),
        session_short_max_tokens=config.short_max_tokens,
        session_long_min_tokens=config.long_min_tokens,
        manual_minutes_by_category=dict(DEFAULT_CATEGORY_MANUAL_MINUTES),
        fte_rate_model=config.fte_rate_model,
        token_cost_model=config.token_cost_model,
    )

    if not records:
        return Roi(
            assumptions=assumptions,
            verdict=_build_verdict(0.0, 0.0),
            summary=_empty_summary(),
            by_category=[],
            by_scenario=[],
        )

    total_logs = len(records)
    success_count = 0
    total_tokens = 0
    wasted_tokens = 0
    total_saved_minutes = 0.0
    automation_count = 0
    tools_frequency: dict[str, int] = {}
    style_stats: dict[str, int] = {}

    users_analytics: dict[str, UserStats] = {}
    department_costs: dict[str, float] = {}

    by_category: dict[str, _Bucket] = {}
    by_scenario: dict[str, _Bucket] = {}

    estimated_manual_count = 0
    query_chars_total = 0

    for rec in records:
        tokens = rec.tokens or 0
        cat_key = rec.task_type or "unknown"
        manual = rec.manual_time_minutes
        if not manual or manual <= 0.0:
            manual = DEFAULT_CATEGORY_MANUAL_MINUTES.get(
                cat_key, DEFAULT_FALLBACK_MANUAL_MINUTES
            )
            estimated_manual_count += 1

        total_tokens += tokens
        query_chars_total += rec.query_chars or 0
        cost_for_log = (tokens / 1000.0) * config.token_cost_per_1k_rub

        uid = rec.user_id or "unknown_user"
        uname = rec.user_name or "Unknown"
        dept = rec.department or "Unknown"

        if uid not in users_analytics:
            users_analytics[uid] = UserStats(user_id=uid, name=uname, department=dept)
        u_stat = users_analytics[uid]
        u_stat.requests_count += 1
        u_stat.tokens_consumed += tokens
        u_stat.cost_rub += cost_for_log

        department_costs[dept] = department_costs.get(dept, 0.0) + cost_for_log

        log_style = rec.style or "formal"
        style_stats[log_style] = style_stats.get(log_style, 0) + 1

        cat = by_category.setdefault(cat_key, _Bucket(task_type=cat_key))
        cat.count += 1
        cat.tokens_used += tokens

        scenario = None
        if rec.scenario_id:
            scenario = by_scenario.setdefault(
                rec.scenario_id, _Bucket(name=rec.scenario_name)
            )
            scenario.count += 1
            scenario.tokens_used += tokens

        rec_status = (rec.status or "").strip().lower()
        if rec_status in ("success", "ok", "completed"):
            saved = manual * config.session_coeff(tokens)
            success_count += 1
            total_saved_minutes += saved
            cat.success_count += 1
            cat.saved_minutes += saved
            if scenario is not None:
                scenario.success_count += 1
                scenario.saved_minutes += saved
            if rec.tools_used:
                automation_count += 1
                for tool in rec.tools_used:
                    tools_frequency[tool] = tools_frequency.get(tool, 0) + 1
        else:
            wasted_tokens += tokens
            u_stat.wasted_tokens += tokens

    assumptions.manual_minutes_estimated_percent = round(
        (estimated_manual_count / total_logs) * 100, 1
    )
    assumptions.analysis_cost_model = _build_analysis_cost(
        query_chars_total, len(by_scenario), total_logs, config
    )

    total_fte_hours = total_saved_minutes / 60.0
    manual_cost = total_fte_hours * config.fte_hourly_rate_rub
    agent_cost = (total_tokens / 1000.0) * config.token_cost_per_1k_rub
    wasted_cost = (wasted_tokens / 1000.0) * config.token_cost_per_1k_rub
    net_savings = manual_cost - agent_cost
    roi_mult = round(manual_cost / agent_cost, 2) if agent_cost > 0 else 0.0
    cost_per_action = round(agent_cost / success_count, 2) if success_count > 0 else 0.0
    tvi = round(total_fte_hours / (total_tokens / 1000.0), 4) if total_tokens else 0.0

    sorted_users = sorted(users_analytics.values(), key=lambda x: x.tokens_consumed, reverse=True)
    top_spenders = sorted_users[:3]

    sorted_departments = {
        k: round(v, 2)
        for k, v in sorted(department_costs.items(), key=lambda kv: kv[1], reverse=True)
    }

    style_percentages = {
        st: round((cnt / total_logs) * 100, 1) for st, cnt in style_stats.items()
    }
    mobile_voice_count = style_stats.get("voice", 0) + style_stats.get("typo", 0)
    mobile_voice_rate = round((mobile_voice_count / total_logs) * 100, 1)
    insight = (
        f"📱 {mobile_voice_rate}% запросов поступают в неформальном/мобильном стиле (голос или опечатки с телефона). "
        f"Рекомендуется поддерживать и развивать Voice-to-Text интерфейс."
    )

    summary = RoiSummary(
        total_logs=total_logs,
        success_rate_percent=round((success_count / total_logs) * 100, 1),
        total_fte_hours_saved=round(total_fte_hours, 2),
        total_manual_cost_rub=round(manual_cost, 2),
        total_agent_cost_rub=round(agent_cost, 2),
        net_savings_rub=round(net_savings, 2),
        roi_multiplier=roi_mult,
        total_tokens_consumed=total_tokens,
        wasted_tokens_on_errors=wasted_tokens,
        wasted_cost_rub=round(wasted_cost, 2),
        cost_per_successful_action_rub=cost_per_action,
        mau_count=len(users_analytics),
        top_spenders=top_spenders,
        department_costs=sorted_departments,
        style_breakdown=style_stats,
        style_percentages=style_percentages,
        mobile_voice_adoption_rate=mobile_voice_rate,
        style_insight=insight,
        token_value_index=tvi,
        process_automation_rate=round((automation_count / total_logs) * 100, 1),
        top_tools_used=dict(
            sorted(tools_frequency.items(), key=lambda kv: kv[1], reverse=True)
        ),
    )

    category_rows = [
        RoiByCategory(
            task_type=key,
            label=label(key),
            count=bucket.count,
            success_rate_percent=round((bucket.success_count / bucket.count) * 100, 1)
            if bucket.count
            else 0.0,
            fte_hours_saved=round(bucket.saved_minutes / 60.0, 2),
            net_savings_rub=_bucket_net(bucket, config),
        )
        for key, bucket in sorted(
            by_category.items(), key=lambda kv: kv[1].count, reverse=True
        )
    ]

    scenario_rows = [
        RoiByScenario(
            scenario_id=key,
            name=bucket.name,
            count=bucket.count,
            fte_hours_saved=round(bucket.saved_minutes / 60.0, 2),
            net_savings_rub=_bucket_net(bucket, config),
        )
        for key, bucket in sorted(
            by_scenario.items(), key=lambda kv: kv[1].count, reverse=True
        )
    ]

    return Roi(
        assumptions=assumptions,
        verdict=_build_verdict(manual_cost, agent_cost),
        summary=summary,
        by_category=category_rows,
        by_scenario=scenario_rows,
    )


def _build_verdict(benefit_rub: float, cost_rub: float) -> PayoffVerdict:
    """State the B > A comparison outright instead of leaving it to be inferred."""
    net = benefit_rub - cost_rub
    ratio = round(benefit_rub / cost_rub, 2) if cost_rub > 0 else 0.0
    pays_off = benefit_rub > cost_rub

    if cost_rub <= 0 and benefit_rub <= 0:
        headline = "Недостаточно данных для вердикта"
    elif pays_off:
        headline = (
            f"ИИ окупается: выгода {_money(benefit_rub)} > затрат {_money(cost_rub)} "
            f"(×{ratio}, чистыми {_money(net)})"
        )
    else:
        headline = (
            f"ИИ пока не окупается: выгода {_money(benefit_rub)} "
            f"< затрат {_money(cost_rub)} (минус {_money(abs(net))})"
        )

    return PayoffVerdict(
        benefit_rub=round(benefit_rub, 2),
        cost_rub=round(cost_rub, 2),
        net_rub=round(net, 2),
        ratio=ratio,
        pays_off=pays_off,
        headline=headline,
    )


def _money(value: float) -> str:
    """Compact rouble figure for the headline (2.1 млн ₽ reads better than 2112800)."""
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.1f} млн ₽"
    if abs(value) >= 1_000:
        return f"{value / 1_000:.0f} тыс ₽"
    return f"{value:.0f} ₽"


def _bucket_net(bucket: _Bucket, config: RoiConfig) -> float:
    manual = (bucket.saved_minutes / 60.0) * config.fte_hourly_rate_rub
    agent = (bucket.tokens_used / 1000.0) * config.token_cost_per_1k_rub
    return round(manual - agent, 2)


def _empty_summary() -> RoiSummary:
    return RoiSummary(
        total_logs=0,
        success_rate_percent=0.0,
        total_fte_hours_saved=0.0,
        total_manual_cost_rub=0.0,
        total_agent_cost_rub=0.0,
        net_savings_rub=0.0,
        roi_multiplier=0.0,
        total_tokens_consumed=0,
        wasted_tokens_on_errors=0,
        wasted_cost_rub=0.0,
        cost_per_successful_action_rub=0.0,
        mau_count=0,
        top_spenders=[],
        department_costs={},
        style_breakdown={},
        style_percentages={},
        mobile_voice_adoption_rate=0.0,
        style_insight="",
        token_value_index=0.0,
        process_automation_rate=0.0,
        top_tools_used={},
    )


def _build_analysis_cost(
    query_chars: int, scenario_count: int, total_logs: int, config: RoiConfig
) -> AnalysisCostModel:
    """Cost of running Prompt Radar over these records, at the same token price.

    Embeddings are charged on the query text (characters converted at a stated
    ratio, since there is no tokeniser at this layer); summarisation is a one-off
    per scenario on each recompute. CatBoost inference is CPU-only and free.
    """
    chars_per_token = config.analysis_chars_per_token or 3.0
    embedding_tokens = int(query_chars / chars_per_token)
    summarization_tokens = int(scenario_count * config.analysis_tokens_per_scenario)
    total = embedding_tokens + summarization_tokens
    cost = (total / 1000.0) * config.token_cost_per_1k_rub

    return AnalysisCostModel(
        embedding_tokens=embedding_tokens,
        summarization_tokens=summarization_tokens,
        chars_per_token=chars_per_token,
        tokens_per_scenario=config.analysis_tokens_per_scenario,
        cost_rub=round(cost, 2),
        cost_per_request_rub=round(cost / total_logs, 4) if total_logs else 0.0,
    )
