"""Unit tests for statistics aggregation: Top-N/other/unknown/trends (PR F)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from app.pipeline.aggregation import (
    AggregationConfig,
    build_statistics,
    compute_trend,
    top_n_distribution,
    top_n_scenarios,
)


# ---------------------------------------------------------------------------
# Top-N + other + unknown
# ---------------------------------------------------------------------------


def test_top_n_merges_tail_into_other():
    counts = {
        "a": 100,
        "b": 50,
        "c": 40,
        "d": 30,
        "e": 5,
        "f": 3,
    }
    result = top_n_distribution(counts, limit=3)
    assert [r["task_type"] for r in result] == ["a", "b", "c", "other"]
    assert result[-1]["count"] == 30 + 5 + 3


def test_unknown_never_merged_into_other():
    counts = {
        "data_analysis": 100,
        "code_generation": 50,
        "docs": 20,
        "chat": 10,
        "unknown": 25,  # large but protected
        "tiny": 1,
    }
    result = top_n_distribution(counts, limit=2)
    types = [r["task_type"] for r in result]
    assert "unknown" in types
    assert "other" in types
    unknown_row = next(r for r in result if r["task_type"] == "unknown")
    other_row = next(r for r in result if r["task_type"] == "other")
    assert unknown_row["count"] == 25
    # other must not include unknown
    assert other_row["count"] == 20 + 10 + 1  # docs + chat + tiny
    assert sum(r["count"] for r in result) == sum(counts.values())


def test_unknown_alone_still_shown():
    counts = {"unknown": 7}
    result = top_n_distribution(counts, limit=5)
    assert result == [{"task_type": "unknown", "count": 7}]


def test_top_n_merges_into_existing_other_class():
    counts = {"a": 10, "b": 9, "c": 1, "other": 2}
    result = top_n_distribution(counts, limit=2)
    # head: a, b; tail c merges into existing other → other = 2+1
    types = [r["task_type"] for r in result]
    assert types[:2] == ["a", "b"]
    assert "other" in types
    other = next(r for r in result if r["task_type"] == "other")
    assert other["count"] == 3


def test_top_scenarios_other_has_no_fake_summary():
    counts = {f"s{i}": 100 - i for i in range(12)}
    clusters = {
        f"s{i}": {
            "task_type": "data_analysis",
            "name": f"Scenario {i}",
            "summary": f"Summary {i}",
        }
        for i in range(12)
    }
    result = top_n_scenarios(counts, limit=3, clusters=clusters)
    assert len(result) == 4  # 3 + other
    other = result[-1]
    assert other["scenario_id"] == "other"
    assert other["summary"] is None
    assert other["name"] == "Other"
    assert other["count"] == sum(counts[f"s{i}"] for i in range(3, 12))


# ---------------------------------------------------------------------------
# Trends (§8.10)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "prev,cur,expected_trend",
    [
        (10, 15, "up"),  # +50%
        (10, 8, "down"),  # -20%
        (10, 10, "stable"),
        (10, 11, "stable"),  # +10% not > threshold 15
        (0, 25, "new"),
        (0, 0, "insufficient_data"),
        (1, 0, "insufficient_data"),
        (3, 30, "insufficient_data"),  # prev < min_previous_for_rate
    ],
)
def test_compute_trend_cases(prev, cur, expected_trend):
    kwargs = dict(threshold_percent=15.0, min_total_for_trend=20, min_previous_for_rate=5)
    if prev == 10 and cur == 8:
        kwargs["min_total_for_trend"] = 15
    if prev == 10 and cur in (10, 11, 15):
        kwargs["min_total_for_trend"] = 15
    trend, growth = compute_trend(prev, cur, **kwargs)
    assert trend == expected_trend
    if expected_trend in ("new", "insufficient_data"):
        assert growth is None
    else:
        assert growth is not None


def test_compute_trend_threshold_boundary():
    trend, growth = compute_trend(
        100, 111, threshold_percent=10.0, min_total_for_trend=20, min_previous_for_rate=5
    )
    assert trend == "up"
    assert growth == 11.0
    trend2, _ = compute_trend(
        100, 110, threshold_percent=10.0, min_total_for_trend=20, min_previous_for_rate=5
    )
    assert trend2 == "stable"  # exactly 10% is not > 10


def test_build_statistics_trends_half_period():
    assignments = []
    for i in range(15):
        assignments.append(
            {
                "request_id": f"a{i}",
                "task_type": "data_analysis",
                "scenario_id": "data_analysis:cluster_0",
                "timestamp": f"2026-01-0{(i % 5) + 1}T12:00:00Z",
                "is_outlier": False,
            }
        )
    for i in range(30):
        assignments.append(
            {
                "request_id": f"b{i}",
                "task_type": "data_analysis",
                "scenario_id": "data_analysis:cluster_0",
                "timestamp": f"2026-01-2{(i % 5)}T12:00:00Z",
                "is_outlier": False,
            }
        )
    for i in range(12):
        assignments.append(
            {
                "request_id": f"c{i}",
                "task_type": "code_generation",
                "scenario_id": "code_generation:cluster_0",
                "timestamp": "2026-01-25T12:00:00Z",
                "is_outlier": False,
            }
        )

    clusters = {
        "data_analysis:cluster_0": {
            "task_type": "data_analysis",
            "name": "CRM export",
            "summary": "Export CRM reports",
        },
        "code_generation:cluster_0": {
            "task_type": "code_generation",
            "name": "Python helpers",
            "summary": None,
        },
    }
    stats = build_statistics(
        assignments,
        clusters=clusters,
        config=AggregationConfig(
            trend_threshold_percent=15.0,
            trend_min_total=20,
            trend_min_previous=5,
        ),
    )
    by_id = {s["scenario_id"]: s for s in stats["top_scenarios"]}
    assert by_id["data_analysis:cluster_0"]["trend"] in ("up", "stable")
    assert by_id["code_generation:cluster_0"]["trend"] == "new"


# ---------------------------------------------------------------------------
# Failure analysis + totals + contract
# ---------------------------------------------------------------------------


def test_failure_not_available_without_signals():
    items = [
        {
            "request_id": "1",
            "task_type": "data_analysis",
            "scenario_id": "s1",
            "timestamp": "2026-07-01T00:00:00Z",
        }
    ]
    stats = build_statistics(items)
    assert stats["failure_analysis"]["status"] == "not_available"


def test_failure_available_with_error_code():
    items = [
        {
            "request_id": "1",
            "task_type": "data_analysis",
            "scenario_id": "s1",
            "timestamp": "2026-07-01T00:00:00Z",
            "response_status": "error",
            "error_code": "tool_error",
        },
        {
            "request_id": "2",
            "task_type": "data_analysis",
            "scenario_id": "s1",
            "timestamp": "2026-07-02T00:00:00Z",
            "response_status": "success",
            "error_code": None,
        },
    ]
    stats = build_statistics(items)
    fa = stats["failure_analysis"]
    assert fa["status"] == "available"
    assert fa["total_requests_with_failure_signals"] == 1
    assert any(s["signal"] == "tool_error" for s in fa["top_failure_signals"])


def test_totals_and_dynamics():
    items = [
        {
            "request_id": "1",
            "task_type": "unknown",
            "scenario_id": None,
            "timestamp": "2026-07-01T10:00:00Z",
            "is_outlier": True,
        },
        {
            "request_id": "2",
            "task_type": "data_analysis",
            "scenario_id": "data_analysis:cluster_0",
            "timestamp": "2026-07-01T11:00:00Z",
            "is_outlier": False,
        },
        {
            "request_id": "3",
            "task_type": "data_analysis",
            "scenario_id": "data_analysis:cluster_0",
            "timestamp": "2026-07-02T11:00:00Z",
            "is_outlier": False,
        },
    ]
    clusters = {"data_analysis:cluster_0": {"scenario_id": "data_analysis:cluster_0"}}
    stats = build_statistics(items, clusters=clusters)
    assert stats["totals"]["records_total"] == 3
    assert stats["totals"]["unknown_count"] == 1
    assert stats["totals"]["scenarios_count"] == 1
    assert stats["outliers_summary"]["total_outliers_count"] == 1
    assert {d["date"] for d in stats["dynamics"]} == {"2026-07-01", "2026-07-02"}


def test_scenarios_without_cluster_metadata_are_not_counted():
    """Online clustering hands out scenario_ids before recompute names them.

    Those provisional ids have no cluster row, so they carry no name or summary.
    Counting them would put nameless entries in `top_scenarios`; the dashboard
    shows 0 scenarios plus the "recompute needed" banner instead.
    """
    items = [
        {
            "request_id": "1",
            "task_type": "data_analysis",
            "scenario_id": "data_analysis:cluster_0",
            "timestamp": "2026-07-01T11:00:00Z",
            "is_outlier": False,
        },
    ]
    stats = build_statistics(items)
    assert stats["totals"]["records_total"] == 1
    assert stats["totals"]["scenarios_count"] == 0
    assert stats["top_scenarios"] == []


def test_source_and_date_filters():
    items = [
        {
            "request_id": "1",
            "task_type": "a",
            "scenario_id": "s1",
            "source_id": "src_a",
            "timestamp": "2026-07-01T00:00:00Z",
        },
        {
            "request_id": "2",
            "task_type": "b",
            "scenario_id": "s2",
            "source_id": "src_b",
            "timestamp": "2026-07-10T00:00:00Z",
        },
    ]
    stats = build_statistics(items, source_id="src_a")
    assert stats["totals"]["records_total"] == 1
    assert stats["filters_applied"]["source_id"] == "src_a"

    stats2 = build_statistics(items, from_date="2026-07-05", to_date="2026-07-31")
    assert stats2["totals"]["records_total"] == 1
    assert stats2["tasks_distribution"][0]["task_type"] == "b"


def test_statistics_matches_contract_schema():
    schema_path = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "contracts"
        / "statistics.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)

    items = [
        {
            "request_id": f"r{i}",
            "task_type": "data_analysis" if i % 3 else "unknown",
            "scenario_id": "data_analysis:cluster_0" if i % 3 else None,
            "timestamp": f"2026-07-{(i % 28) + 1:02d}T12:00:00Z",
            "is_outlier": i % 7 == 0,
            "response_status": "error" if i % 5 == 0 else "success",
            "error_code": "tool_error" if i % 5 == 0 else None,
            "source_id": "demo",
        }
        for i in range(30)
    ]
    clusters = {
        "data_analysis:cluster_0": {
            "task_type": "data_analysis",
            "name": "CRM",
            "summary": "Export",
            "automation_potential": "high",
            "statistical_reliability": "medium",
        }
    }
    stats = build_statistics(
        items,
        clusters=clusters,
        source_id="demo",
        config=AggregationConfig(top_tasks_limit=5, top_scenarios_limit=5),
        freshness={
            "last_recompute_at": "2026-07-20T10:00:00Z",
            "logs_since_last_recompute": 3,
            "recompute_pending": True,
        },
        pipeline_metadata={
            "embedding_provider": "mock",
            "online_similarity_threshold": 0.85,
        },
    )
    errors = sorted(validator.iter_errors(stats), key=lambda e: list(e.path))
    assert not errors, "; ".join(
        f"{'/'.join(str(p) for p in e.path)}: {e.message}" for e in errors
    )

    # Required top-level keys
    for key in (
        "schema_version",
        "generated_at",
        "totals",
        "tasks_distribution",
        "top_scenarios",
        "dynamics",
        "outliers_summary",
        "failure_analysis",
        "freshness",
        "pipeline_metadata",
        "filters_applied",
    ):
        assert key in stats

    # unknown not collapsed into other
    task_types = [t["task_type"] for t in stats["tasks_distribution"]]
    if "unknown" in task_types:
        assert task_types.count("unknown") == 1
