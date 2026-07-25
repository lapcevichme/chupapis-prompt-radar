from pydantic import BaseModel


class PersonaDistItem(BaseModel):
    persona: str
    label: str
    count: int
    percentage: float


class UserAnalyticsSummary(BaseModel):
    total_users: int
    active_users_l7: int
    avg_adoption_score: float
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
    model_id: str
    model_name: str
    total_queries: int
    share_percentage: float
    avg_latency_ms: int
    total_tokens: int
    failure_rate_percent: float
    user_feedback_score: float
    top_task_type: str
    cost_tier: str


class TaskFitItem(BaseModel):
    task_type: str
    label: str
    recommended_model: str
    queries_count: int
    avg_latency_ms: int


class ModelAnalyticsSummary(BaseModel):
    total_models_detected: int
    avg_latency_ms: int
    total_tokens: int
    potential_cost_reduction_percent: float
    routing_recommendation: str


class ModelsAnalyticsResponse(BaseModel):
    summary: ModelAnalyticsSummary
    models: list[ModelItemAnalytics]
    task_fit: list[TaskFitItem]
