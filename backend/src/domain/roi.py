from pydantic import BaseModel


class SessionCoefficients(BaseModel):
    short: float
    medium: float
    long: float


class Assumptions(BaseModel):
    fte_hourly_rate_rub: float
    token_cost_per_1k_rub: float
    session_coefficients: SessionCoefficients
    session_short_max_tokens: int
    session_long_min_tokens: int


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
    summary: RoiSummary
    by_category: list[RoiByCategory]
    by_scenario: list[RoiByScenario]
