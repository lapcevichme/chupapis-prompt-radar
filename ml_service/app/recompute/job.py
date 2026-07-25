"""Heavy recompute job: UMAP+HDBSCAN per task_type, stable scenario_ids, LLM summarization."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Optional, Protocol

from app.pipeline.clustering_batch.umap_hdbscan import (
    run_umap_hdbscan,
    technical_scenario_name,
)
from app.pipeline.summarization import ScenarioSummary, Summarizer, technical_summary
from app.recompute.representatives import (
    select_representatives,
    select_representatives_via_qdrant,
)
from app.recompute.stability import (
    apply_id_mapping,
    remap_centroids,
    stabilize_scenario_ids,
)

logger = logging.getLogger(__name__)

# Allowed job statuses (ТЗ recompute_jobs)
JOB_STATUSES = frozenset({"pending", "running", "completed", "failed"})


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobPersistence(Protocol):
    """Optional durable sink for job records (MetaStore implements this)."""

    def put_recompute_job(self, job: dict[str, Any]) -> None: ...
    def get_recompute_job(self, job_id: str) -> dict[str, Any] | None: ...


class RecomputeStore:
    """
    In-memory store for jobs + cluster assignments.

    Persistent-friendly: optional `persistence` backend mirrors job dicts
    (and can be swapped for SQLite meta later without changing job logic).
    """

    def __init__(self, persistence: Any | None = None) -> None:
        self.jobs: dict[str, dict[str, Any]] = {}
        self.assignments: dict[str, dict[str, Any]] = {}  # request_id → assignment
        self.clusters: dict[str, dict[str, Any]] = {}  # scenario_id → meta
        self.centroids: dict[str, list[float]] = {}
        self._persistence = persistence

    def put_job(self, job: dict[str, Any]) -> None:
        # snapshot so callers cannot mutate store silently
        snap = dict(job)
        self.jobs[snap["job_id"]] = snap
        if self._persistence is not None:
            try:
                self._persistence.put_recompute_job(snap)
            except Exception:  # noqa: BLE001
                logger.exception("failed to persist job %s", snap.get("job_id"))

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        job = self.jobs.get(job_id)
        if job is not None:
            return job
        if self._persistence is not None:
            try:
                loaded = self._persistence.get_recompute_job(job_id)
                if loaded:
                    self.jobs[job_id] = loaded
                    return loaded
            except Exception:  # noqa: BLE001
                logger.exception("failed to load job %s", job_id)
        return None

    def snapshot_centroids(self) -> dict[str, list[float]]:
        return {k: list(v) for k, v in self.centroids.items()}


# Process-wide store for API
STORE = RecomputeStore()


class RecomputeJob:
    """
    Run UMAP+HDBSCAN recompute; track status for GET /recompute/{job_id}.

    Status lifecycle: pending → running → completed | failed
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        store: RecomputeStore | None = None,
        *,
        summarizer: Summarizer | None = None,
        qdrant: Any | None = None,
        enable_summarization: bool = True,
        match_threshold: float = 0.75,
    ) -> None:
        self.config = config or {}
        self.store = store or STORE
        self.qdrant = qdrant
        self.enable_summarization = enable_summarization
        self.match_threshold = float(match_threshold)
        self._summarizer = summarizer
        self.job_id = f"recompute_{uuid.uuid4().hex[:12]}"
        self.status = "pending"
        self.result: dict[str, Any] = {
            "job_id": self.job_id,
            "status": self.status,
            "created_at": _utcnow(),
            "started_at": None,
            "completed_at": None,
            "clusters_created": 0,
            "scenarios_named": 0,
            "fallback_used": False,
            "task_types": [],
            "error": None,
        }
        self.store.put_job(self.result)

    def _get_summarizer(self) -> Summarizer:
        if self._summarizer is not None:
            return self._summarizer
        self._summarizer = Summarizer.from_config(self.config)
        return self._summarizer

    def _set_status(self, status: str, **extra: Any) -> None:
        if status not in JOB_STATUSES:
            raise ValueError(f"invalid job status: {status}")
        self.status = status
        self.result["status"] = status
        self.result.update(extra)
        self.store.put_job(self.result)

    def _sum_cfg(self) -> dict[str, Any]:
        return self.config.get("summarization") or {}

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
            match_threshold = float(
                recompute_cfg.get("centroid_match_threshold", self.match_threshold)
            )

            total_clusters = 0
            named = 0
            any_fallback = False
            task_types: list[str] = []
            old_centroids = self.store.snapshot_centroids()

            # Clear previous cluster metas for types we recompute (keep others)
            for task_type in list(by_type.keys()):
                for sid in list(self.store.clusters.keys()):
                    if sid.startswith(f"{task_type}:"):
                        self.store.clusters.pop(sid, None)
                        self.store.centroids.pop(sid, None)

            for task_type, records in by_type.items():
                task_types.append(task_type)
                embeddings = [r.get("embedding") or [0.0] * 10 for r in records]
                max_clusters = int(
                    recompute_cfg.get("max_clusters_per_task_type")
                    or hdb_cfg.get("max_clusters")
                    or 5
                )
                logger.info(
                    "recompute UMAP+HDBSCAN task_type=%s n=%s dim=%s",
                    task_type,
                    len(embeddings),
                    len(embeddings[0]) if embeddings else 0,
                )
                # CPU-heavy: keep event loop free for API poll / TestClient
                out = await asyncio.to_thread(
                    run_umap_hdbscan,
                    embeddings,
                    task_type=task_type,
                    random_state=int(umap_cfg.get("random_state", 42)),
                    min_cluster_size=int(hdb_cfg.get("min_cluster_size", 10)),
                    min_samples=int(hdb_cfg.get("min_samples", 4)),
                    n_neighbors=int(umap_cfg.get("n_neighbors", 15)),
                    n_components=int(umap_cfg.get("n_components", 10)),
                    max_clusters=max_clusters,
                )
                logger.info(
                    "recompute clustered task_type=%s clusters=%s fallback=%s",
                    task_type,
                    len(out.get("centroids") or {}),
                    out.get("fallback_used"),
                )
                if out["fallback_used"] != "none":
                    any_fallback = True

                # Stabilize scenario_id against previous centroids
                mapping = stabilize_scenario_ids(
                    out["centroids"],
                    old_centroids,
                    task_type=task_type,
                    match_threshold=match_threshold,
                )
                scenario_ids = apply_id_mapping(out["scenario_ids"], mapping)
                centroids = remap_centroids(out["centroids"], mapping)

                # Group records by stable scenario_id for summarization
                members: dict[str, list[dict[str, Any]]] = defaultdict(list)
                for i, rec in enumerate(records):
                    sid = scenario_ids[i]
                    if sid is not None:
                        members[sid].append(rec)

                sum_cfg = self._sum_cfg()
                examples_count = int(sum_cfg.get("representative_examples_count", 10))

                for sid, centroid in centroids.items():
                    try:
                        n = int(sid.rsplit("_", 1)[-1])
                    except (ValueError, IndexError):
                        n = 0
                    tech_name = technical_scenario_name(task_type, n)
                    cluster_meta: dict[str, Any] = {
                        "scenario_id": sid,
                        "task_type": task_type,
                        "name": tech_name,
                        "summary": None,
                        "user_goal": None,
                        "pain_points": [],
                        "automation_potential": None,
                        "records_count": sum(1 for s in scenario_ids if s == sid),
                        "statistical_reliability": out["statistical_reliability"],
                        "updated_at": _utcnow(),
                    }

                    summary_obj: Optional[ScenarioSummary] = None
                    if self.enable_summarization:
                        examples = select_representatives_via_qdrant(
                            self.qdrant,
                            centroid,
                            scenario_id=sid,
                            count=examples_count,
                        )
                        if not examples:
                            examples = select_representatives(
                                members.get(sid, []),
                                centroid=centroid,
                                count=examples_count,
                            )
                        try:
                            summarizer = self._get_summarizer()
                            summary_obj = await summarizer.summarize_scenario(
                                sid, examples, task_type
                            )
                        except Exception:  # noqa: BLE001
                            logger.exception("summarization error for %s", sid)
                            summary_obj = technical_summary(sid, task_type, examples)

                        if summary_obj is not None:
                            cluster_meta["name"] = summary_obj.name
                            cluster_meta["summary"] = summary_obj.summary
                            cluster_meta["user_goal"] = summary_obj.user_goal
                            cluster_meta["pain_points"] = list(summary_obj.pain_points)
                            cluster_meta["automation_potential"] = (
                                summary_obj.automation_potential
                            )

                    self.store.clusters[sid] = cluster_meta
                    self.store.centroids[sid] = centroid
                    total_clusters += 1
                    if cluster_meta.get("name"):
                        named += 1

                for i, rec in enumerate(records):
                    rid = rec.get("request_id") or f"anon_{i}"
                    sid = scenario_ids[i]
                    self.store.assignments[rid] = {
                        "request_id": rid,
                        "task_type": task_type,
                        "scenario_id": sid,
                        "scenario_name": (
                            self.store.clusters.get(sid or "", {}).get("name")
                            if sid
                            else None
                        ),
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
    **kwargs: Any,
) -> str:
    """Start job, return job_id (caller may schedule as background task)."""
    job = RecomputeJob(config=config, store=store, **kwargs)
    await job.run(data)
    return job.job_id
