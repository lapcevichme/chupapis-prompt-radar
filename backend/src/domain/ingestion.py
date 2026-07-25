from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SourceStatus(str, Enum):
    ingesting = "ingesting"
    classified = "classified"
    recomputed = "recomputed"
    failed = "failed"


class NormalizationReport(BaseModel):
    """Outcome of turning a raw dataset into log records."""

    records_total: int
    records_valid: int
    records_rejected: int
    synthesized_request_id: int = 0
    synthesized_timestamp: int = 0
    synthetic_timestamps: bool = False
    rejected_reasons: dict[str, int] = Field(default_factory=dict)


class SourceOut(BaseModel):
    source_id: str
    name: str
    origin: str
    records_total: int
    records_valid: int
    records_rejected: int
    records_classified: int = 0
    classification_percentage: float = 0.0
    status: SourceStatus
    created_at: datetime
    normalization_report: NormalizationReport | None = None



class LiveIngestRequest(BaseModel):
    """Live webhook payload: raw log records streamed in real time."""

    logs: list[dict[str, Any]] = Field(default_factory=list)
    source_name: str = "live"


class LiveIngestResponse(BaseModel):
    source_id: str
    accepted: int
    duplicates: int
    rejected: int
    records_valid: int
    records_rejected: int
