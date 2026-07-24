from datetime import datetime

from pydantic import BaseModel


class Totals(BaseModel):
    records_processed: int
    scenarios_count: int
    outliers_percentage: float


class Freshness(BaseModel):
    last_recompute_at: datetime | None = None
    logs_since_last_recompute: int = 0
    recompute_pending: bool = False


class TaskDistItem(BaseModel):
    task_type: str
    label: str
    count: int
    percentage: float


class ScenarioOut(BaseModel):
    scenario_id: str
    task_type: str | None = None
    name: str | None = None
    summary: str | None = None
    user_goal: str | None = None
    representative_examples: list[str] = []
    pain_points: list[str] = []
    automation_potential: str | None = None
    count: int
    trend: str | None = None
    growth_rate_percent: float | None = None
    statistical_reliability: str | None = None


class DynamicsPoint(BaseModel):
    date: str
    count: int


class OutliersSummary(BaseModel):
    total_outliers_count: int
    outlier_percentage: float


class FailureSignal(BaseModel):
    signal: str
    count: int


class FailureAnalysis(BaseModel):
    status: str
    total_requests_with_failure_signals: int = 0
    failure_signal_percentage: float = 0.0
    top_failure_signals: list[FailureSignal] = []


class Dashboard(BaseModel):
    taxonomy_version: str
    freshness: Freshness
    totals: Totals
    tasks_distribution: list[TaskDistItem]
    top_scenarios: list[ScenarioOut]
    dynamics: list[DynamicsPoint]
    outliers_summary: OutliersSummary
    failure_analysis: FailureAnalysis


class LogItem(BaseModel):
    request_id: str
    query_text: str
    task_type: str | None = None
    label: str | None = None
    classification_confidence: float | None = None
    scenario_id: str | None = None
    scenario_name: str | None = None
    is_outlier: bool = False
    has_failure_signals: bool = False
    timestamp: datetime | None = None
