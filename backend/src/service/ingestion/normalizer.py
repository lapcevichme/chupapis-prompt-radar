import csv
import io
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from core.config import Settings
from core.errors import DatasetInvalidError

logger = logging.getLogger(__name__)

# Maps raw dataset status -> (response_status, error_code) per backend-ml.md §1.
_STATUS_MAP: dict[str, tuple[str, str | None]] = {
    "success": ("success", None),
    "error_tool": ("error", "tool_error"),
    "hallucination_loop": ("error", "hallucination_loop"),
}


@dataclass
class DatasetRow:
    """Raw ROI fields persisted per record (dataset_records)."""

    request_id: str
    query_text: str
    gold_category: str | None
    style: str | None
    tokens: int | None
    manual_time_minutes: float | None
    tools_used: list[Any] | None
    status: str | None
    timestamp: datetime


@dataclass
class NormalizationResult:
    log_records: list[dict[str, Any]] = field(default_factory=list)
    dataset_rows: list[DatasetRow] = field(default_factory=list)
    report: dict[str, Any] = field(default_factory=dict)


def parse_raw(raw_bytes: bytes, filename: str) -> list[dict[str, Any]]:
    """Parse json / jsonl / csv bytes into a list of raw record dicts."""
    name = (filename or "").lower()
    text = raw_bytes.decode("utf-8-sig", errors="replace").strip()

    try:
        if name.endswith(".jsonl"):
            return [json.loads(line) for line in text.splitlines() if line.strip()]
        if name.endswith(".csv"):
            return _parse_csv(text)
        # default: json
        data = json.loads(text) if text else []
    except (json.JSONDecodeError, csv.Error) as exc:
        raise DatasetInvalidError(f"Cannot parse dataset: {exc}") from exc

    if isinstance(data, dict):
        # tolerate {"records": [...]} / {"logs": [...]} wrappers
        for key in ("records", "logs", "data", "items"):
            if isinstance(data.get(key), list):
                return data[key]
        raise DatasetInvalidError("JSON object has no records list")
    if not isinstance(data, list):
        raise DatasetInvalidError("Dataset must be a JSON list")
    return data


def _parse_csv(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    reader = csv.DictReader(io.StringIO(text))
    for raw in reader:
        row = dict(raw)
        for int_key in ("simulated_context_tokens", "estimated_manual_time_minutes"):
            if row.get(int_key) not in (None, ""):
                try:
                    row[int_key] = int(float(row[int_key]))
                except (TypeError, ValueError):
                    row[int_key] = None
        tools = row.get("tools_used")
        if isinstance(tools, str) and tools:
            try:
                row["tools_used"] = json.loads(tools)
            except json.JSONDecodeError:
                row["tools_used"] = [t.strip() for t in tools.split(",") if t.strip()]
        rows.append(row)
    return rows


def _synthesize_timestamp(
    index: int, total: int, settings: Settings, now: datetime
) -> datetime:
    if not settings.NORMALIZE_SYNTHESIZE_TIMESTAMPS or total <= 0:
        return now
    span = timedelta(days=settings.NORMALIZE_TIMESTAMP_SPAN_DAYS)
    offset = span * (index / total)
    return now - span + offset


def normalize(
    raw_records: list[dict[str, Any]], settings: Settings
) -> NormalizationResult:
    """Turn raw records into (log_records, dataset_rows, report)."""
    result = NormalizationResult()
    now = datetime.now(UTC)
    total = len(raw_records)
    rejected_reasons: dict[str, int] = {}
    synthesize_ts = settings.NORMALIZE_SYNTHESIZE_TIMESTAMPS

    for index, raw in enumerate(raw_records):
        if not isinstance(raw, dict):
            rejected_reasons["not_an_object"] = (
                rejected_reasons.get("not_an_object", 0) + 1
            )
            continue

        query_text = str(raw.get("user_query") or "").strip()
        if not query_text:
            rejected_reasons["empty_query_text"] = (
                rejected_reasons.get("empty_query_text", 0) + 1
            )
            continue

        request_id = f"req_{index}"
        timestamp = _synthesize_timestamp(index, total, settings, now)
        raw_status = raw.get("status")
        response_status, error_code = _STATUS_MAP.get(
            str(raw_status), ("success", None)
        )
        tokens = _as_int(raw.get("simulated_context_tokens"))
        manual_time = _as_float(raw.get("estimated_manual_time_minutes"))
        tools_used = raw.get("tools_used") or []
        gold_category = raw.get("category")
        style = raw.get("style")

        result.log_records.append(
            {
                "request_id": request_id,
                "query_text": query_text,
                "timestamp": timestamp.isoformat(),
                "response_status": response_status,
                "error_code": error_code,
                "metadata": {
                    "gold_category": gold_category,
                    "style": style,
                    "tokens": tokens,
                    "tools_used": tools_used,
                    "manual_time_minutes": manual_time,
                    "agent_steps": _as_int(raw.get("agent_steps")),
                },
            }
        )
        result.dataset_rows.append(
            DatasetRow(
                request_id=request_id,
                query_text=query_text,
                gold_category=gold_category,
                style=style,
                tokens=tokens,
                manual_time_minutes=manual_time,
                tools_used=list(tools_used) if tools_used else [],
                status=str(raw_status) if raw_status is not None else None,
                timestamp=timestamp,
            )
        )

    valid = len(result.dataset_rows)
    rejected = sum(rejected_reasons.values())
    result.report = {
        "records_total": total,
        "records_valid": valid,
        "records_rejected": rejected,
        "synthesized_request_id": valid,
        "synthesized_timestamp": valid if synthesize_ts else 0,
        "synthetic_timestamps": synthesize_ts,
        "rejected_reasons": rejected_reasons,
    }
    return result


def _as_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
