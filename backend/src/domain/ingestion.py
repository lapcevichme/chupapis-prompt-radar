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


class SourceProgress(BaseModel):
    """How far ML has classified this source's valid records (live progress)."""

    classified: int = 0
    total: int = 0
    percent: float = 0.0
    done: bool = False


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
    progress: SourceProgress | None = None


class ProcessingSourceItem(BaseModel):
    """Per-source indexing progress used by the global processing banner."""

    source_id: str
    name: str
    origin: str
    status: SourceStatus
    records_total: int
    records_valid: int
    records_rejected: int
    classified: int
    percent: float
    done: bool


class ProcessingStatus(BaseModel):
    """Aggregate indexing/recompute state for a live, app-wide progress banner."""

    indexing: bool
    total_valid: int
    total_classified: int
    percent: float
    recompute_status: str
    recompute_pending: bool
    logs_since_last_recompute: int
    scenarios_named: int
    sources: list[ProcessingSourceItem] = Field(default_factory=list)



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
