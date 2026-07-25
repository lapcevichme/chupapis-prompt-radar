import csv
import io
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from core.config import Settings
from core.errors import DatasetInvalidError

logger = logging.getLogger(__name__)

# Maps raw dataset status -> (response_status, error_code) per backend-ml.md §1.
_STATUS_MAP: dict[str, tuple[str, str | None]] = {
    "success": ("success", None),
    "error_tool": ("error", "tool_error"),
    "hallucination_loop": ("error", "hallucination_loop"),
}

# Generated datasets carry corrupted / compound style labels ("typoy", "typò",
# "voice_jargon"). Fold them onto the canonical modality so the ROI style
# breakdown is not diluted by single-record spelling variants. Unknown values are
# kept as-is (lowercased) rather than dropped — we normalize, we don't censor.
_STYLE_ALIASES: dict[str, str] = {
    "typoy": "typo",
    "typò": "typo",
    "typo_jargon": "typo",
    "voice_jargon": "voice",
    "corporate slang": "jargon",
    "corporate_slang": "jargon",
    "formnal": "formal",
}

# Status values that leaked into the `style` field of generated datasets. They are
# not speech styles, so the style is recorded as unknown rather than polluting the
# style breakdown with a bogus category.
_NON_STYLE_VALUES: frozenset[str] = frozenset(
    {"success", "error", "error_tool", "hallucination_loop"}
)


def _normalize_style(value: Any) -> str | None:
    if value in (None, ""):
        return None
    cleaned = str(value).strip().lower()
    if not cleaned or cleaned in _NON_STYLE_VALUES:
        return None
    return _STYLE_ALIASES.get(cleaned, cleaned)


@dataclass
class DatasetRow:
    """Raw ROI fields persisted per record (dataset_records)."""

    request_id: str
    query_text: str
    gold_category: str | None
    style: str | None
    user_id: str | None = None
    user_name: str | None = None
    department: str | None = None
    tokens: int | None = None
    manual_time_minutes: float | None = None
    tools_used: list[Any] | None = None
    status: str | None = None
    timestamp: datetime = None


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
        for int_key in (
            "simulated_context_tokens",
            "total_tokens",
            "estimated_manual_time_minutes",
            "manual_time_minutes",
            "manual_time",
        ):
            if row.get(int_key) not in (None, ""):
                try:
                    row[int_key] = float(row[int_key])
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
    raw_records: list[dict[str, Any]],
    settings: Settings,
    *,
    id_prefix: str = "req_",
    request_namespace: str | None = None,
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

        query_text = str(raw.get("user_query") or raw.get("query_text") or "").strip()
        if not query_text:
            rejected_reasons["empty_query_text"] = (
                rejected_reasons.get("empty_query_text", 0) + 1
            )
            continue

        external_request_id = str(raw.get("request_id") or f"{id_prefix}{index}")
        request_id = _canonical_request_id(request_namespace, external_request_id)
        
        raw_ts = raw.get("timestamp")
        if raw_ts:
            try:
                ts_clean = str(raw_ts).replace("Z", "+00:00")
                timestamp = datetime.fromisoformat(ts_clean)
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=UTC)
            except (ValueError, TypeError):
                timestamp = _synthesize_timestamp(index, total, settings, now)
        else:
            timestamp = _synthesize_timestamp(index, total, settings, now)

        raw_status = raw.get("status")
        if raw_status is None:
            raw_status = raw.get("response_status")
        raw_status_str = str(raw_status).lower() if raw_status is not None else "success"
        response_status, error_code = _STATUS_MAP.get(
            raw_status_str, ("success", None)
        )
        tokens = _as_int(raw.get("total_tokens"))
        if tokens is None:
            tokens = _as_int(raw.get("simulated_context_tokens"))
        if tokens is None and isinstance(raw.get("metadata"), dict):
            meta_usage = raw.get("metadata", {}).get("usage")
            if isinstance(meta_usage, dict):
                tokens = _as_int(meta_usage.get("total_tokens"))

        manual_time = _as_float(
            raw.get("estimated_manual_time_minutes")
            or raw.get("manual_time_minutes")
            or raw.get("manual_time")
            or raw.get("estimated_manual_time")
        )
        tools_used = list(raw.get("tools_used") or [])
        if not tools_used and isinstance(raw.get("metadata"), dict):
            tools_used = list(raw.get("metadata", {}).get("tools_used") or [])

        raw_model = str(raw.get("model") or raw.get("model_name") or raw.get("agent_id") or "").strip()
        if raw_model and not any(isinstance(t, str) and t.startswith("model:") for t in tools_used):
            tools_used.append(f"model:{raw_model}")

        gold_category = raw.get("category")
        style = _normalize_style(raw.get("style"))
        meta_dict = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
        user_id = raw.get("user_id") or meta_dict.get("user_email")
        user_name = raw.get("user_name")
        department = raw.get("department")


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
                    "user_id": user_id,
                    "user_name": user_name,
                    "department": department,
                    "tokens": tokens,
                    "tools_used": tools_used,
                    "manual_time_minutes": manual_time,
                    "agent_steps": _as_int(raw.get("agent_steps")),
                    "external_request_id": external_request_id,
                },
            }
        )
        result.dataset_rows.append(
            DatasetRow(
                request_id=request_id,
                query_text=query_text,
                gold_category=gold_category,
                style=style,
                user_id=user_id,
                user_name=user_name,
                department=department,
                tokens=tokens,
                manual_time_minutes=manual_time,
                tools_used=list(tools_used) if tools_used else [],
                status=str(raw_status) if raw_status is not None else "success",
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


def _canonical_request_id(namespace: str | None, external_request_id: str) -> str:
    """Make ML idempotency dataset-scoped while keeping a compact stable identifier."""
    if not namespace:
        return external_request_id
    return str(
        uuid5(
            NAMESPACE_URL,
            f"prompt-radar:{namespace}:{external_request_id}",
        )
    )


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
