from pydantic import BaseModel


class PersonaDistItem(BaseModel):
    persona: str
    label: str
    count: int
    percentage: float


class UserAnalyticsSummary(BaseModel):
    total_users: int
    # Users seen at least once inside the trailing `active_window_days` window,
    # measured from the newest timestamp present in the filtered data.
    active_users_l7: int
    active_window_days: int = 7
    avg_frustration_index: float
    personas_distribution: list[PersonaDistItem]


class DepartmentUserAnalytics(BaseModel):
    department: str
    users_count: int
    total_queries: int
    avg_saved_hours: float
    frustration_index: float


class UserItemAnalytics(BaseModel):
    user_id: str
    user_name: str
    department: str
    persona: str
    persona_label: str
    total_queries: int
    active_days: int
    saved_hours: float
    frustration_index: float
    top_category: str
    needs_guidance: bool
    recommendation: str


class UsersAnalyticsResponse(BaseModel):
    summary: UserAnalyticsSummary
    by_department: list[DepartmentUserAnalytics]
    users: list[UserItemAnalytics]


class ModelItemAnalytics(BaseModel):
    """One model actually named by the data source.

    Only fields derivable from ingested records live here. Latency and user
    feedback are NOT part of `log.schema.json`, so they are not reported.
    """

    model_id: str
    model_name: str
    total_queries: int
    share_percentage: float
    total_tokens: int
    failure_rate_percent: float
    top_task_type: str


class ModelAnalyticsSummary(BaseModel):
    # "not_available" when no record carries model metadata — same convention as
    # statistics.failure_analysis.status. We never guess a model for a record.
    status: str
    total_models_detected: int
    total_queries_with_model: int
    total_tokens: int


class ModelsAnalyticsResponse(BaseModel):
    summary: ModelAnalyticsSummary
    models: list[ModelItemAnalytics]
