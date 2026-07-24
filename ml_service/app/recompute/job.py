"""Heavy recompute job: UMAP+HDBSCAN per task_type, outliers, stable scenario_ids."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from app.pipeline.clustering_batch.umap_hdbscan import (
    make_scenario_id,
    run_umap_hdbscan,
    technical_scenario_name,
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class RecomputeStore:
    """In-memory store for jobs + cluster assignments (swap for Qdrant/meta later)."""

    def __init__(self) -> None:
        self.jobs: dict[str, dict[str, Any]] = {}
        self.assignments: dict[str, dict[str, Any]] = {}  # request_id → assignment
        self.clusters: dict[str, dict[str, Any]] = {}  # scenario_id → meta
        self.centroids: dict[str, list[float]] = {}

    def put_job(self, job: dict[str, Any]) -> None:
        self.jobs[job["job_id"]] = job

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        return self.jobs.get(job_id)


# Process-wide store for API
STORE = RecomputeStore()


class RecomputeJob:
    """Run UMAP+HDBSCAN recompute; track status for GET /recompute/{job_id}."""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        store: RecomputeStore | None = None,
    ) -> None:
        self.config = config or {}
        self.store = store or STORE
        self.job_id = f"recompute_{uuid.uuid4().hex[:12]}"
        self.status = "pending"
        self.result: dict[str, Any] = {
            "job_id": self.job_id,
            "status": self.status,
            "created_at": _utcnow(),
            "clusters_created": 0,
            "scenarios_named": 0,
            "fallback_used": False,
            "task_types": [],
            "error": None,
        }
        self.store.put_job(self.result)

    def _set_status(self, status: str, **extra: Any) -> None:
        self.status = status
        self.result["status"] = status
        self.result.update(extra)
        self.store.put_job(self.result)

    async def run(self, data: list[dict[str, Any]]) -> dict[str, Any]:
        """
        data items: request_id, task_type, embedding (list[float]), optional query_text.
        """
        self._set_status("running", started_at=_utcnow())
        try:
            by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for rec in data:
                tt = rec.get("task_type") or "unknown"
                by_type[tt].append(rec)

            recompute_cfg = self.config.get("recompute", {})
            umap_cfg = recompute_cfg.get("umap", {})
            hdb_cfg = recompute_cfg.get("hdbscan", {})

            total_clusters = 0
            named = 0
            any_fallback = False
            task_types: list[str] = []

            for task_type, records in by_type.items():
                task_types.append(task_type)
                embeddings = [
                    r.get("embedding") or [0.0] * 10 for r in records
                ]
                out = run_umap_hdbscan(
                    embeddings,
                    task_type=task_type,
                    random_state=int(umap_cfg.get("random_state", 42)),
                    min_cluster_size=int(hdb_cfg.get("min_cluster_size", 5)),
                    min_samples=int(hdb_cfg.get("min_samples", 3)),
                    n_neighbors=int(umap_cfg.get("n_neighbors", 15)),
                    n_components=int(umap_cfg.get("n_components", 10)),
                )
                if out["fallback_used"] != "none":
                    any_fallback = True

                for sid, centroid in out["centroids"].items():
                    n = int(sid.rsplit("_", 1)[-1])
                    name = technical_scenario_name(task_type, n)
                    self.store.clusters[sid] = {
                        "scenario_id": sid,
                        "task_type": task_type,
                        "name": name,
                        "summary": None,
                        "records_count": sum(
                            1 for s in out["scenario_ids"] if s == sid
                        ),
                        "statistical_reliability": out["statistical_reliability"],
                        "updated_at": _utcnow(),
                    }
                    self.store.centroids[sid] = centroid
                    total_clusters += 1
                    named += 1

                for i, rec in enumerate(records):
                    rid = rec.get("request_id") or f"anon_{i}"
                    self.store.assignments[rid] = {
                        "request_id": rid,
                        "task_type": task_type,
                        "scenario_id": out["scenario_ids"][i],
                        "is_outlier": out["is_outlier"][i],
                        "label": out["labels"][i],
                        "pipeline_metadata": out["metadata"],
                    }

            self._set_status(
                "completed",
                completed_at=_utcnow(),
                clusters_created=total_clusters,
                scenarios_named=named,
                fallback_used=any_fallback,
                task_types=task_types,
            )
            return self.result
        except Exception as exc:  # noqa: BLE001
            self._set_status(
                "failed",
                completed_at=_utcnow(),
                error=str(exc),
            )
            raise


async def run_recompute_background(
    data: list[dict[str, Any]],
    config: dict[str, Any] | None = None,
    store: RecomputeStore | None = None,
) -> str:
    """Start job, return job_id (caller may schedule as background task)."""
    job = RecomputeJob(config=config, store=store)
    await job.run(data)
    return job.job_id
