"""Restart recovery: centroids and recompute freshness come back from the meta store.

Both used to live only in process memory, so a restarted ML service reported
"never recomputed" and started assigning every incoming log to a brand-new
scenario even though recompute had already built the clusters.
"""
from __future__ import annotations

from app import main as main_mod
from app.database.meta_store import MetaStore
from app.pipeline.clustering_online.cosine_clusterer import CosineClusterer


class _OnlineStub:
    def __init__(self, clusterer: CosineClusterer) -> None:
        self.clusterer = clusterer


def _install(meta: MetaStore, clusterer: CosineClusterer | None) -> None:
    main_mod.app.state.meta = meta
    main_mod.app.state.online = _OnlineStub(clusterer) if clusterer else None


def test_centroids_reload_so_logs_rejoin_existing_clusters():
    meta = MetaStore("sqlite:///:memory:")
    try:
        meta.upsert_cluster(
            {
                "scenario_id": "code_help:cluster_0",
                "task_type": "code_help",
                "name": "Отладка кода",
                "records_count": 12,
                "centroid": [1.0, 0.0, 0.0],
            }
        )
        # No centroid stored -> nothing to hydrate from, must be skipped.
        meta.upsert_cluster(
            {
                "scenario_id": "code_help:cluster_1",
                "task_type": "code_help",
                "records_count": 3,
            }
        )
        clusterer = CosineClusterer(similarity_threshold=0.85)
        _install(meta, clusterer)

        assert main_mod._hydrate_online_clusterer() == 1

        result = clusterer.assign([0.99, 0.01, 0.0], "code_help")
        assert result.scenario_id == "code_help:cluster_0"
        assert result.is_new_cluster is False
    finally:
        meta.close()


def test_hydration_drops_clusters_recompute_dissolved():
    meta = MetaStore("sqlite:///:memory:")
    try:
        meta.upsert_cluster(
            {
                "scenario_id": "code_help:cluster_7",
                "task_type": "code_help",
                "records_count": 5,
                "centroid": [0.0, 1.0, 0.0],
            }
        )
        clusterer = CosineClusterer(similarity_threshold=0.85)
        clusterer.load_centroid("code_help:cluster_0", "code_help", [1.0, 0.0, 0.0])
        _install(meta, clusterer)

        main_mod._hydrate_online_clusterer()

        assert clusterer.get_all_scenarios() == ["code_help:cluster_7"]
        # ids keep climbing past the loaded ones instead of colliding with them
        assert clusterer.assign([0.0, 0.0, 1.0], "code_help").scenario_id == (
            "code_help:cluster_8"
        )
    finally:
        meta.close()


def test_freshness_restored_from_last_completed_job():
    meta = MetaStore("sqlite:///:memory:")
    try:
        meta.put_job(
            {
                "job_id": "j1",
                "status": "completed",
                "completed_at": "2026-07-20T10:00:00Z",
                "logs_at_completion": 100,
            }
        )
        meta.put_job(
            {
                "job_id": "j2",
                "status": "completed",
                "completed_at": "2026-07-24T10:00:00Z",
                "logs_at_completion": 4860,
            }
        )
        # A failed run must not be mistaken for the last good one.
        meta.put_job(
            {
                "job_id": "j3",
                "status": "failed",
                "completed_at": "2026-07-25T10:00:00Z",
                "error": "boom",
            }
        )
        _install(meta, None)
        main_mod._LAST_RECOMPUTE_AT = None
        main_mod._LOGS_AT_LAST_RECOMPUTE = 0

        main_mod._restore_recompute_state()

        assert main_mod._LAST_RECOMPUTE_AT == "2026-07-24T10:00:00Z"
        assert main_mod._LOGS_AT_LAST_RECOMPUTE == 4860
    finally:
        meta.close()
        main_mod._LAST_RECOMPUTE_AT = None
        main_mod._LOGS_AT_LAST_RECOMPUTE = 0


def test_restore_is_a_no_op_when_nothing_ever_completed():
    meta = MetaStore("sqlite:///:memory:")
    try:
        meta.put_job({"job_id": "j1", "status": "running"})
        _install(meta, None)
        main_mod._LAST_RECOMPUTE_AT = None
        main_mod._LOGS_AT_LAST_RECOMPUTE = 0

        main_mod._restore_recompute_state()

        assert main_mod._LAST_RECOMPUTE_AT is None
        assert main_mod._LOGS_AT_LAST_RECOMPUTE == 0
    finally:
        meta.close()
