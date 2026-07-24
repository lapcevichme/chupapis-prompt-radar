"""Statistics aggregation for GET /api/v1/statistics (ТЗ §8.8–8.11)."""

from app.pipeline.aggregation.builder import (
    AggregationConfig,
    build_scenarios_list,
    build_statistics,
    compute_trend,
    top_n_distribution,
    top_n_scenarios,
)

__all__ = [
    "AggregationConfig",
    "build_scenarios_list",
    "build_statistics",
    "compute_trend",
    "top_n_distribution",
    "top_n_scenarios",
]
