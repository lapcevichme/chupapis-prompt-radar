"""Prompt Radar ML service — CQRS: write / recompute / read."""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.api.schemas import Assignment, AssignmentsResponse, LogBatch
from app.core.config import settings
from app.database.meta_store import MetaStore
from app.domain.taxonomy import Taxonomy
from app.pipeline.classification.catboost_classifier import CatBoostClassifier
from app.pipeline.online_pipeline import OnlinePipeline
from app.recompute.job import STORE, RecomputeJob
from app.store.qdrant import QdrantStore

logger = logging.getLogger(__name__)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

SERVICE_TOKEN = os.getenv("ML_SERVICE_TOKEN", "")
SCHEMA_VERSION = "2.0.0"
PIPELINE_VERSION = "0.1.0-mvp"
TAXONOMY_VERSION = "v1"

# In-memory buffers until full Qdrant/meta wiring
_PENDING_FOR_RECOMPUTE: list[dict[str, Any]] = []
_ASSIGNMENTS: dict[str, dict[str, Any]] = {}


def _check_token(x_service_token: Optional[str]) -> None:
    if not SERVICE_TOKEN:
        return  # local/dev open
    if x_service_token != SERVICE_TOKEN:
        raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "Invalid token"})


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.taxonomy = Taxonomy()
    app.state.classifier = CatBoostClassifier(
        taxonomy=app.state.taxonomy.taxonomy,
        config={
            "fallback_mode": os.getenv("CLASSIFIER_FALLBACK_MODE", "llm"),
            "confidence_threshold": float(os.getenv("CLASSIFIER_CONFIDENCE_THRESHOLD", "0.60")),
        },
    )
    app.state.online = OnlinePipeline(settings=settings)
    try:
        app.state.qdrant = QdrantStore(getattr(settings, "store", {}) if hasattr(settings, "store") else {})
    except Exception:  # noqa: BLE001
        app.state.qdrant = None
    meta_url = os.getenv("ML_META_DB_URL", "sqlite:///./ml_meta.db")
    app.state.meta = MetaStore(meta_url)
    logger.info("ML service started")
    yield
    await app.state.online.close()
    logger.info("ML service stopped")


app = FastAPI(
    title="Prompt Radar ML Service",
    version=PIPELINE_VERSION,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _pipeline_metadata() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "pipeline_version": PIPELINE_VERSION,
        "taxonomy_version": TAXONOMY_VERSION,
        "embeddings_provider": settings.embeddings.provider,
        "online_similarity_threshold": settings.online_clustering.similarity_threshold,
    }


@app.get("/health/live")
async def health_live() -> dict[str, str]:
    return {"status": "live"}


@app.get("/health/ready")
async def health_ready() -> dict[str, Any]:
    return {
        "status": "ready",
        "checks": {
            "embeddings_provider": settings.embeddings.provider,
            "classifier": "ok",
            "clusters_loaded": app.state.online.clusterer.cluster_count(),
        },
    }


async def _process_one(log: dict[str, Any]) -> dict[str, Any]:
    request_id = log["request_id"]
    query_text = (log.get("query_text") or "").strip()
    if not query_text:
        return {"request_id": request_id, "rejected": True, "reason": "empty_query"}

    clf = app.state.classifier.predict_with_confidence(query_text)
    task_type = clf["task_type"]
    online = await app.state.online.process(
        request_id=request_id,
        query_text=query_text,
        task_type=task_type,
    )
    assignment = {
        "request_id": request_id,
        "task_type": task_type,
        "classification_confidence": clf["classification_confidence"],
        "scenario_id": online.scenario_id,
        "scenario_name": None,
        "is_outlier": False,
        "has_failure_signals": bool(
            log.get("error_code") or log.get("response_status") in ("error", "failed")
        ),
        "embedding": online.embedding,
        "timestamp": log.get("timestamp"),
        "source_id": log.get("source_id"),
    }
    _ASSIGNMENTS[request_id] = assignment
    _PENDING_FOR_RECOMPUTE.append(
        {
            "request_id": request_id,
            "task_type": task_type,
            "embedding": online.embedding,
            "query_text": query_text,
            "source_id": log.get("source_id"),
            "timestamp": log.get("timestamp"),
        }
    )
    return assignment


async def process_batch(logs: list[dict[str, Any]]) -> None:
    for log in logs:
        try:
            await _process_one(log)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to process request_id=%s", log.get("request_id"))


@app.put("/api/v1/logs", status_code=202)
async def put_logs(
    batch: LogBatch,
    background: BackgroundTasks,
    x_service_token: Optional[str] = Header(default=None, alias="X-Service-Token"),
) -> dict[str, Any]:
    _check_token(x_service_token)
    accepted = 0
    duplicates = 0
    rejected = 0
    source_id = None
    to_process: list[dict[str, Any]] = []
    for item in batch.logs:
        source_id = source_id or item.source_id
        if not (item.query_text or "").strip():
            rejected += 1
            continue
        if item.request_id in _ASSIGNMENTS:
            duplicates += 1
            continue
        to_process.append(item.model_dump(mode="json"))
        accepted += 1
    if to_process:
        background.add_task(process_batch, to_process)
    return {
        "accepted": accepted,
        "duplicates": duplicates,
        "rejected": rejected,
        "source_id": source_id,
    }


@app.post("/api/v1/recompute", status_code=202)
async def post_recompute(
    background: BackgroundTasks,
    x_service_token: Optional[str] = Header(default=None, alias="X-Service-Token"),
) -> dict[str, str]:
    _check_token(x_service_token)
    job = RecomputeJob(store=STORE)
    data = list(_PENDING_FOR_RECOMPUTE)

    async def _run() -> None:
        try:
            await job.run(data)
            for rid, a in STORE.assignments.items():
                if rid in _ASSIGNMENTS:
                    _ASSIGNMENTS[rid].update(
                        {
                            "scenario_id": a.get("scenario_id"),
                            "is_outlier": a.get("is_outlier", False),
                        }
                    )
                else:
                    _ASSIGNMENTS[rid] = a
        except Exception:  # noqa: BLE001
            logger.exception("recompute failed job_id=%s", job.job_id)

    background.add_task(_run)
    return {"job_id": job.job_id, "status": "pending"}


@app.get("/api/v1/recompute/{job_id}")
async def get_recompute(
    job_id: str,
    x_service_token: Optional[str] = Header(default=None, alias="X-Service-Token"),
) -> dict[str, Any]:
    _check_token(x_service_token)
    job = STORE.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "job not found"})
    return job


@app.get("/api/v1/statistics")
async def get_statistics(
    source_id: Optional[str] = Query(default=None),
    from_date: Optional[str] = Query(default=None, alias="from"),
    to_date: Optional[str] = Query(default=None, alias="to"),
    x_service_token: Optional[str] = Header(default=None, alias="X-Service-Token"),
) -> dict[str, Any]:
    _check_token(x_service_token)
    items = list(_ASSIGNMENTS.values())
    if source_id:
        items = [a for a in items if a.get("source_id") == source_id]

    by_task: dict[str, int] = {}
    by_scenario: dict[str, int] = {}
    outliers = 0
    for a in items:
        tt = a.get("task_type") or "unknown"
        by_task[tt] = by_task.get(tt, 0) + 1
        sid = a.get("scenario_id") or "unknown"
        by_scenario[sid] = by_scenario.get(sid, 0) + 1
        if a.get("is_outlier"):
            outliers += 1

    return {
        "total_logs": len(items),
        "by_task_type": [{"task_type": k, "count": v} for k, v in sorted(by_task.items(), key=lambda x: -x[1])],
        "by_scenario": [
            {
                "scenario_id": k,
                "count": v,
                "name": STORE.clusters.get(k, {}).get("name"),
            }
            for k, v in sorted(by_scenario.items(), key=lambda x: -x[1])
        ],
        "outliers": outliers,
        "failure_analysis": {"status": "not_available"},
        "pipeline_metadata": _pipeline_metadata(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "filters": {"source_id": source_id, "from": from_date, "to": to_date},
    }


@app.get("/api/v1/assignments")
async def get_assignments(
    source_id: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    x_service_token: Optional[str] = Header(default=None, alias="X-Service-Token"),
) -> dict[str, Any]:
    _check_token(x_service_token)
    items = list(_ASSIGNMENTS.values())
    if source_id:
        items = [a for a in items if a.get("source_id") == source_id]
    total = len(items)
    page = items[offset : offset + limit]
    # drop heavy embedding from response
    cleaned = []
    for a in page:
        cleaned.append(
            {
                "request_id": a.get("request_id"),
                "task_type": a.get("task_type"),
                "classification_confidence": a.get("classification_confidence"),
                "scenario_id": a.get("scenario_id"),
                "scenario_name": a.get("scenario_name")
                or STORE.clusters.get(a.get("scenario_id") or "", {}).get("name"),
                "is_outlier": bool(a.get("is_outlier")),
                "has_failure_signals": bool(a.get("has_failure_signals")),
            }
        )
    return {"items": cleaned, "total": total, "pipeline_metadata": _pipeline_metadata()}


@app.get("/api/v1/scenarios")
async def get_scenarios(
    x_service_token: Optional[str] = Header(default=None, alias="X-Service-Token"),
) -> dict[str, Any]:
    _check_token(x_service_token)
    return {"items": list(STORE.clusters.values()), "total": len(STORE.clusters)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
