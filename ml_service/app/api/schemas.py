from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional, Dict, Any, Union
from datetime import datetime

class Log(BaseModel):
    model_config = ConfigDict(extra="ignore")

    request_id: str
    query_text: str
    timestamp: Union[datetime, str]
    source_id: Optional[str] = None
    response_status: Optional[str] = None
    error_code: Optional[str] = None
    response_latency_ms: Optional[int] = None
    user_feedback: Optional[int] = None
    retry_count: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None

class LogBatch(BaseModel):
    logs: List[Log] = Field(default_factory=list)

class Statistics(BaseModel):
    total_logs: int
    by_task_type: List[Dict]
    by_scenario: List[Dict]
    outliers: int
    failure_rate: float
    pipeline_metadata: Dict

class Assignment(BaseModel):
    request_id: str
    source_id: Optional[str] = None
    task_type: str
    classification_confidence: float
    scenario_id: str
    scenario_name: Optional[str] = None
    is_outlier: bool
    has_failure_signals: bool
    timestamp: Optional[Union[datetime, str]] = None

class AssignmentsResponse(BaseModel):
    items: List[Assignment]
    total: int
    pipeline_metadata: Dict

class ErrorResponse(BaseModel):
    code: str
    message: str
    retryable: bool
