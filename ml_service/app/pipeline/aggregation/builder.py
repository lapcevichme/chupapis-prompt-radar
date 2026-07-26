"""Statistics builder: totals, Top-N+other, dynamics, trends, failure, freshness.

Contract: docs/contracts/statistics.schema.json (ТЗ §8.8–8.11).
Rules:
  - unknown is never merged into other (tasks_distribution)
  - top_scenarios other has no fake summary
  - trends: half-period up/down/stable/new/insufficient_data
  - failure_analysis available only when quality signals exist
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Optional


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class AggregationConfig:
    top_tasks_limit: int = 7
    top_scenarios_limit: int = 9
    trend_threshold_percent: float = 15.0
    trend_min_total: int = 20
    trend_min_previous: int = 5
    schema_version: str = "2.0.0"
    taxonomy_version: str = "v1"
    pipeline_version: str = "0.1.0-mvp"


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested)
# ---------------------------------------------------------------------------


def top_n_distribution(
    counts: dict[str, int],
    limit: int,
    *,
    protected_keys: frozenset[str] = frozenset({"unknown"}),
    other_key: str = "other",
    key_field: str = "task_type",
) -> list[dict[str, Any]]:
    """Top-N by count + other for the tail. Protected keys never merge into other."""
    if limit < 0:
        raise ValueError("limit must be >= 0")

    protected = {
        k: v for k, v in counts.items() if k in protected_keys and v > 0
    }
    rest = {k: v for k, v in counts.items() if k not in protected_keys and v > 0}
    ordered = sorted(rest.items(), key=lambda x: (-x[1], x[0]))

    head = ordered[:limit]
    tail = ordered[limit:]
    result: list[dict[str, Any]] = [{key_field: k, "count": v} for k, v in head]

    tail_sum = sum(v for _, v in tail)
    if tail_sum > 0:
        merged = False
        for item in result:
            if item[key_field] == other_key:
                item["count"] += tail_sum
                merged = True
                break
        if not merged:
            result.append({key_field: other_key, "count": tail_sum})

    for k, v in sorted(protected.items(), key=lambda x: (-x[1], x[0])):
        result.append({key_field: k, "count": v})

    return result


def top_n_scenarios(
    scenario_counts: dict[str, int],
    limit: int,
    *,
    clusters: Optional[dict[str, dict[str, Any]]] = None,
    trends: Optional[dict[str, dict[str, Any]]] = None,
    other_id: str = "other",
) -> list[dict[str, Any]]:
    """Top-N scenarios + other bucket without a fake summary."""
    clusters = clusters or {}
    trends = trends or {}

    ordered = sorted(
        ((k, v) for k, v in scenario_counts.items() if v > 0 and k != other_id),
        key=lambda x: (-x[1], x[0]),
    )
    head = ordered[:limit]
    tail = ordered[limit:]
    other_count = sum(v for _, v in tail)
    # If caller already had an "other" count, include it
    other_count += int(scenario_counts.get(other_id, 0) or 0)

    result: list[dict[str, Any]] = []
    for sid, count in head:
        meta = clusters.get(sid, {})
        trend_info = trends.get(sid, {})
        result.append(
            {
                "scenario_id": sid,
                "task_type": meta.get("task_type"),
                "name": meta.get("name"),
                "summary": meta.get("summary"),
                "user_goal": meta.get("user_goal"),
                "representative_examples": list(meta.get("representative_examples") or []),
                "pain_points": list(meta.get("pain_points") or []),
                "automation_potential": meta.get("automation_potential"),
                "count": count,
                "trend": trend_info.get("trend"),
                "growth_rate_percent": trend_info.get("growth_rate_percent"),
                "statistical_reliability": meta.get("statistical_reliability"),
            }
        )

    if other_count > 0:
        result.append(
            {
                "scenario_id": other_id,
                "task_type": None,
                "name": "Other",
                "summary": None,  # no fake summary for other
                "user_goal": None,
                "representative_examples": [],
                "pain_points": [],
                "automation_potential": None,
                "count": other_count,
                "trend": None,
                "growth_rate_percent": None,
                "statistical_reliability": None,
            }
        )

    return result


def compute_trend(
    previous_count: int,
    current_count: int,
    *,
    threshold_percent: float = 15.0,
    min_total_for_trend: int = 20,
    min_previous_for_rate: int = 5,
) -> tuple[str, Optional[float]]:
    """
    Half-period trend (ТЗ §8.10).

    Returns (trend, growth_rate_percent).
      - previous_count == 0 and current_count > 0 → new (no % rate)
      - total < min_total_for_trend → insufficient_data
      - previous too small for a stable % → insufficient_data
      - growth > +threshold → up
      - growth < -threshold → down
      - else stable
    """
    total = previous_count + current_count
    # "new" is qualitative — allow on cold-start without crazy rates
    if previous_count == 0:
        if current_count > 0:
            return "new", None
        return "insufficient_data", None
    if total < min_total_for_trend:
        return "insufficient_data", None
    if previous_count < min_previous_for_rate:
        return "insufficient_data", None

    growth = ((current_count - previous_count) / previous_count) * 100.0
    if growth > threshold_percent:
        return "up", round(growth, 2)
    if growth < -threshold_percent:
        return "down", round(growth, 2)
    return "stable", round(growth, 2)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_ts(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    s = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        # date-only
        try:
            dt = datetime.fromisoformat(s[:10])
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _date_key(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return dt.date().isoformat()


def _in_range(
    ts: Optional[datetime],
    from_dt: Optional[datetime],
    to_dt: Optional[datetime],
) -> bool:
    if from_dt is not None and (ts is None or ts < from_dt):
        return False
    if to_dt is not None and (ts is None or ts > to_dt):
        return False
    return True


def _filter_assignments(
    assignments: Iterable[dict[str, Any]],
    *,
    source_id: Optional[str],
    from_date: Optional[str],
    to_date: Optional[str],
) -> list[dict[str, Any]]:
    from_dt = _parse_ts(from_date) if from_date else None
    to_dt = _parse_ts(to_date) if to_date else None
    # Inclusive end-of-day if date-only string
    if to_date and len(to_date.strip()) == 10 and to_dt is not None:
        to_dt = to_dt.replace(hour=23, minute=59, second=59, microsecond=999999)

    out: list[dict[str, Any]] = []
    for a in assignments:
        if source_id is not None and a.get("source_id") != source_id:
            continue
        ts = _parse_ts(a.get("timestamp"))
        if not _in_range(ts, from_dt, to_dt):
            continue
        out.append(a)
    return out


def _half_period_bounds(
    items: list[dict[str, Any]],
) -> tuple[Optional[datetime], Optional[datetime], Optional[datetime]]:
    """Return (start, mid, end) from timestamps; None if not enough data."""
    stamps = sorted(t for t in (_parse_ts(a.get("timestamp")) for a in items) if t is not None)
    if len(stamps) < 2:
        return None, None, None
    start, end = stamps[0], stamps[-1]
    mid = start + (end - start) / 2
    return start, mid, end


def _scenario_trends(
    items: list[dict[str, Any]],
    *,
    threshold_percent: float,
    min_total: int = 20,
    min_previous: int = 5,
) -> dict[str, dict[str, Any]]:
    _, mid, _ = _half_period_bounds(items)
    if mid is None:
        # not enough temporal span
        by_sid = Counter(
            (a.get("scenario_id") or "unknown") for a in items if not a.get("is_outlier")
        )
        return {
            sid: {"trend": "insufficient_data", "growth_rate_percent": None}
            for sid in by_sid
        }

    first: Counter[str] = Counter()
    second: Counter[str] = Counter()
    for a in items:
        if a.get("is_outlier"):
            continue
        sid = a.get("scenario_id") or "unknown"
        ts = _parse_ts(a.get("timestamp"))
        if ts is None:
            continue
        if ts <= mid:
            first[sid] += 1
        else:
            second[sid] += 1

    all_sids = set(first) | set(second)
    out: dict[str, dict[str, Any]] = {}
    for sid in all_sids:
        trend, growth = compute_trend(
            first.get(sid, 0),
            second.get(sid, 0),
            threshold_percent=threshold_percent,
            min_total_for_trend=min_total,
            min_previous_for_rate=min_previous,
        )
        out[sid] = {"trend": trend, "growth_rate_percent": growth}
    return out


def _failure_analysis(items: list[dict[str, Any]]) -> dict[str, Any]:
    """ТЗ §8.8: available only when quality signals are present on any record."""
    signal_counter: Counter[str] = Counter()
    requests_with_signals = 0
    any_signal_field_present = False

    for a in items:
        signals: list[str] = []

        # Presence of fields (even success) means we *have* failure channel data
        if a.get("response_status") is not None:
            any_signal_field_present = True
            status = str(a["response_status"]).lower()
            if status in ("error", "failed", "failure", "timeout"):
                signals.append(f"response_status:{status}")

        if a.get("error_code") is not None:
            any_signal_field_present = True
            code = str(a["error_code"]).strip()
            if code:
                signals.append(code)

        if a.get("user_feedback") is not None:
            any_signal_field_present = True
            fb = a["user_feedback"]
            try:
                if int(fb) < 0:
                    signals.append("user_feedback:negative")
            except (TypeError, ValueError):
                pass

        if a.get("retry_count") is not None:
            any_signal_field_present = True
            try:
                if int(a["retry_count"]) > 0:
                    signals.append("retry")
            except (TypeError, ValueError):
                pass

        # Structured signals from the ingest path come before the generic flag:
        # checking `has_failure_signals` first counted the same record twice —
        # once as "failure" and again as "response_status:error" — because the
        # structured list had not been read yet when the emptiness check ran.
        if a.get("failure_signals"):
            any_signal_field_present = True
            for s in a["failure_signals"]:
                if s and str(s) not in signals:
                    signals.append(str(s))

        # Explicit flag with no structured detail anywhere: count it generically.
        if a.get("has_failure_signals"):
            any_signal_field_present = True
            if not signals:
                signals.append("failure")

        if signals:
            requests_with_signals += 1
            for s in signals:
                signal_counter[s] += 1

    if not any_signal_field_present:
        return {"status": "not_available"}

    total = len(items)
    pct = (requests_with_signals / total * 100.0) if total else 0.0
    top = [
        {"signal": sig, "count": cnt}
        for sig, cnt in signal_counter.most_common(10)
    ]
    return {
        "status": "available",
        "total_requests_with_failure_signals": requests_with_signals,
        "failure_signal_percentage": round(pct, 2),
        "top_failure_signals": top,
    }


def _dynamics(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_date: Counter[str] = Counter()
    for a in items:
        key = _date_key(_parse_ts(a.get("timestamp")))
        if key:
            by_date[key] += 1
    return [{"date": d, "count": c} for d, c in sorted(by_date.items())]


def _default_pipeline_metadata(config: AggregationConfig) -> dict[str, Any]:
    return {
        "schema_version": config.schema_version,
        "pipeline_version": config.pipeline_version,
        "taxonomy_version": config.taxonomy_version,
        "classifier_mode": "catboost",
        "classifier_model_version": "v1",
        "embedding_provider": "mock",
        "embedding_model": "mock",
        "llm_provider": "openrouter",
        "llm_model": "unknown",
        "online_similarity_threshold": 0.85,
        "umap_params": {},
        "hdbscan_params": {},
    }


# ---------------------------------------------------------------------------
# Public builders
# ---------------------------------------------------------------------------


def build_statistics(
    assignments: Iterable[dict[str, Any]],
    *,
    clusters: Optional[dict[str, dict[str, Any]]] = None,
    source_id: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    config: Optional[AggregationConfig] = None,
    freshness: Optional[dict[str, Any]] = None,
    pipeline_metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Build full GET /statistics payload per statistics.schema.json."""
    cfg = config or AggregationConfig()
    clusters = clusters or {}
    items = _filter_assignments(
        assignments,
        source_id=source_id,
        from_date=from_date,
        to_date=to_date,
    )

    records_total = len(items)
    task_counts: Counter[str] = Counter()
    scenario_counts: Counter[str] = Counter()
    unknown_count = 0
    outliers = 0

    for a in items:
        tt = a.get("task_type") or "unknown"
        task_counts[tt] += 1
        if tt == "unknown":
            unknown_count += 1
        if a.get("is_outlier"):
            outliers += 1
        else:
            sid = a.get("scenario_id")
            if sid and sid in clusters:
                scenario_counts[sid] += 1

    scenarios_count = len(scenario_counts)
    outliers_pct = (outliers / records_total * 100.0) if records_total else 0.0

    trends = _scenario_trends(
        items,
        threshold_percent=cfg.trend_threshold_percent,
        min_total=int(getattr(cfg, "trend_min_total", 20)),
        min_previous=int(getattr(cfg, "trend_min_previous", 5)),
    )

    tasks_distribution = top_n_distribution(
        dict(task_counts),
        cfg.top_tasks_limit,
        protected_keys=frozenset({"unknown"}),
        other_key="other",
        key_field="task_type",
    )
    top_scenarios = top_n_scenarios(
        dict(scenario_counts),
        cfg.top_scenarios_limit,
        clusters=clusters,
        trends=trends,
    )

    meta = _default_pipeline_metadata(cfg)
    if pipeline_metadata:
        meta.update(pipeline_metadata)

    freshness_out = {
        "last_recompute_at": None,
        "logs_since_last_recompute": 0,
        "recompute_pending": False,
        "recompute_running": False,
    }
    if freshness:
        freshness_out.update(freshness)

    return {
        "schema_version": cfg.schema_version,
        "taxonomy_version": cfg.taxonomy_version,
        "pipeline_version": cfg.pipeline_version,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "filters_applied": {
            "source_id": source_id,
            "from": from_date,
            "to": to_date,
        },
        "freshness": freshness_out,
        "totals": {
            "records_total": records_total,
            "scenarios_count": scenarios_count,
            "unknown_count": unknown_count,
            "outliers_percentage": round(outliers_pct, 4),
        },
        "tasks_distribution": tasks_distribution,
        "top_scenarios": top_scenarios,
        "dynamics": _dynamics(items),
        "outliers_summary": {
            "total_outliers_count": outliers,
            "outlier_percentage": round(outliers_pct, 4),
        },
        "failure_analysis": _failure_analysis(items),
        "pipeline_metadata": meta,
    }


def build_scenarios_list(
    assignments: Iterable[dict[str, Any]],
    *,
    clusters: Optional[dict[str, dict[str, Any]]] = None,
    source_id: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    config: Optional[AggregationConfig] = None,
    scenario_id: Optional[str] = None,
) -> dict[str, Any]:
    """Full scenarios list (or single) with counts and trends."""
    cfg = config or AggregationConfig()
    clusters = dict(clusters or {})
    items = _filter_assignments(
        assignments,
        source_id=source_id,
        from_date=from_date,
        to_date=to_date,
    )

    scenario_counts: Counter[str] = Counter()
    examples: dict[str, list[str]] = defaultdict(list)
    for a in items:
        if a.get("is_outlier"):
            continue
        sid = a.get("scenario_id")
        if not sid:
            continue
        if scenario_id is not None and sid != scenario_id:
            continue
        scenario_counts[sid] += 1
        qt = a.get("query_text")
        if qt and len(examples[sid]) < 5:
            examples[sid].append(str(qt))

    trends = _scenario_trends(
        items,
        threshold_percent=cfg.trend_threshold_percent,
        min_total=int(getattr(cfg, "trend_min_total", 20)),
        min_previous=int(getattr(cfg, "trend_min_previous", 5)),
    )

    # Ensure cluster meta appears even with zero filtered counts
    sids = set(scenario_counts)
    if scenario_id is not None:
        sids.add(scenario_id)
    else:
        sids |= set(clusters.keys())

    items_out: list[dict[str, Any]] = []
    for sid in sorted(sids):
        if scenario_id is not None and sid != scenario_id:
            continue
        meta = clusters.get(sid, {})
        if not meta and scenario_id is None:
            continue
        trend_info = trends.get(sid, {})
        rep = list(meta.get("representative_examples") or []) or examples.get(sid, [])
        items_out.append(
            {
                "scenario_id": sid,
                "task_type": meta.get("task_type"),
                "name": meta.get("name"),
                "summary": meta.get("summary"),
                "user_goal": meta.get("user_goal"),
                "representative_examples": rep,
                "pain_points": list(meta.get("pain_points") or []),
                "automation_potential": meta.get("automation_potential"),
                "count": int(scenario_counts.get(sid, 0)),
                "records_count": int(
                    scenario_counts.get(sid, 0) or meta.get("records_count") or 0
                ),
                "trend": trend_info.get("trend"),
                "growth_rate_percent": trend_info.get("growth_rate_percent"),
                "statistical_reliability": meta.get("statistical_reliability"),
            }
        )

    return {"items": items_out, "total": len(items_out)}
