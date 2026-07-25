from pydantic import BaseModel


class SessionCoefficients(BaseModel):
    short: float
    medium: float
    long: float


class FteRateModel(BaseModel):
    """How the hourly FTE cost was obtained (QNA §1.1: ~400 000 ₽/month)."""

    monthly_rate_rub: float
    work_hours_per_month: float
    derived_hourly_rate_rub: float
    is_overridden: bool = False


class TokenCostModel(BaseModel):
    """How the token price was obtained (QNA §1.2), instead of a magic constant.

    (capex / amortization_years + electricity_per_year) / tokens_per_year × 1000
    """

    infra_capex_rub: float
    amortization_years: float
    electricity_rub_per_year: float
    tokens_per_year: float
    derived_cost_per_1k_rub: float
    is_overridden: bool = False


class PayoffVerdict(BaseModel):
    """Explicit B > A verdict the customer's expert asked for.

    B — money freed by saving FTE time. A — cost of running the agent.
    """

    benefit_rub: float
    cost_rub: float
    net_rub: float
    ratio: float
    pays_off: bool
    headline: str


class Assumptions(BaseModel):
    fte_hourly_rate_rub: float
    token_cost_per_1k_rub: float
    fte_rate_model: FteRateModel | None = None
    token_cost_model: TokenCostModel | None = None
    session_coefficients: SessionCoefficients
    session_short_max_tokens: int
    session_long_min_tokens: int
    # Fallback manual handling time per task class, applied when a record has no
    # measured `estimated_manual_time_minutes`. Surfaced so the FTE figure can be
    # audited: it is a stated assumption, not a measurement.
    manual_minutes_by_category: dict[str, float] = {}
    # Share of records (0-100) whose manual time came from the table above rather
    # than from the data.
    manual_minutes_estimated_percent: float = 0.0


class UserStats(BaseModel):
    user_id: str
    name: str
    department: str
    requests_count: int = 0
    tokens_consumed: int = 0
    wasted_tokens: int = 0
    cost_rub: float = 0.0


class RoiSummary(BaseModel):
    total_logs: int
    success_rate_percent: float
    total_fte_hours_saved: float
    total_manual_cost_rub: float
    total_agent_cost_rub: float
    net_savings_rub: float
    roi_multiplier: float
    total_tokens_consumed: int
    wasted_tokens_on_errors: int
    wasted_cost_rub: float = 0.0
    cost_per_successful_action_rub: float = 0.0

    # MAU и разрезы по сотрудникам / департаментам
    mau_count: int = 0
    top_spenders: list[UserStats] = []
    department_costs: dict[str, float] = {}

    # Аналитика стилей речи (Voice / Mobile / Jargon / Formal)
    style_breakdown: dict[str, int] = {}
    style_percentages: dict[str, float] = {}
    mobile_voice_adoption_rate: float = 0.0
    style_insight: str = ""

    token_value_index: float
    process_automation_rate: float
    top_tools_used: dict[str, int]


class RoiByCategory(BaseModel):
    task_type: str
    label: str
    count: int
    success_rate_percent: float
    fte_hours_saved: float
    net_savings_rub: float


class RoiByScenario(BaseModel):
    scenario_id: str
    name: str | None = None
    count: int
    fte_hours_saved: float
    net_savings_rub: float
    automation_potential: str | None = None


class Roi(BaseModel):
    assumptions: Assumptions
    verdict: PayoffVerdict
    summary: RoiSummary
    by_category: list[RoiByCategory]
    by_scenario: list[RoiByScenario]
