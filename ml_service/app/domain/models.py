from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class LogEntry(BaseModel):
    """Subset of log.schema.json used by phase-3 pipeline."""

    request_id: str
    query_text: str
    timestamp: Optional[str] = None
    source_id: Optional[str] = None
    response_status: Optional[str] = None
    error_code: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AssignmentItem(BaseModel):
    request_id: str
    task_type: str
    scenario_id: str
    similarity: float = 0.0
    is_outlier: bool = False
    has_failure_signals: bool = False
