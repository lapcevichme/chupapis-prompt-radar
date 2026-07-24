"""Unit tests for UMAP/HDBSCAN recompute core."""
from __future__ import annotations

from app.pipeline.clustering_batch.umap_hdbscan import (
    make_scenario_id,
    run_umap_hdbscan,
    technical_scenario_name,
)


def test_make_scenario_id():
    assert make_scenario_id("code_help", 2) == "code_help:cluster_2"


def test_small_group_fallback():
    emb = [[0.1] * 8] * 3
    out = run_umap_hdbscan(emb, task_type="code_help", min_cluster_size=5)
    assert out["fallback_used"] == "small_group_centroid"
    assert out["statistical_reliability"] == "low"
    assert len(out["labels"]) == 3
    assert all(s == "code_help:cluster_0" for s in out["scenario_ids"])


def test_technical_name():
    assert "code_help" in technical_scenario_name("code_help", 1)
