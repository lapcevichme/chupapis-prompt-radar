"""Prompt Radar ML service — CQRS: write / recompute / read (merged PR A–G)."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np

try:
    from dotenv import load_dotenv

    # Load ml_service/.env before settings/config import side effects
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    load_dotenv()  # also CWD .env if present
except ImportError:  # pragma: no cover
    pass

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.dependencies import require_service_token
from app.api.schemas import LogBatch
from app.core.config import settings
from app.core.exceptions import (
    INVALID_REQUEST,
    MLServiceError,
    error_response,
)
from app.core.logging import get_logger, log_event, setup_logging
from app.database.meta_store import MetaStore
from app.domain.taxonomy import Taxonomy
from app.ingest.queue import IngestQueue
from app.ingest.worker import IngestWorker
from app.pipeline.aggregation import AggregationConfig, build_scenarios_list, build_statistics
from app.pipeline.classification.catboost_classifier import CatBoostClassifier
from app.pipeline.online_pipeline import OnlinePipeline
from app.pipeline.summarization import Summarizer
from app.recompute import job as job_mod
from app.recompute.job import RecomputeJob, RecomputeStore
from app.recompute.scheduler import Scheduler
from app.store.qdrant import QdrantStore

setup_logging(settings.log_level)
logger = get_logger(__name__)

SCHEMA_VERSION = "2.0.0"
PIPELINE_VERSION = "0.3.0-mvp"
TAXONOMY_VERSION = "v1"

_LAST_RECOMPUTE_AT: Optional[str] = None
_LOGS_AT_LAST_RECOMPUTE: int = 0


def _store_dict() -> dict[str, Any]:
    return {
        "qdrant_url": settings.store.qdrant_url,
        "qdrant_collection": settings.store.qdrant_collection,
        "meta_db_url": settings.store.meta_db_url,
    }


def _failure_signals(log: dict[str, Any]) -> list[str]:
    signals: list[str] = []
    status = log.get("response_status")
    if status is not None and str(status).lower() in (
        "error",
        "failed",
        "failure",
        "timeout",
    ):
        signals.append(f"response_status:{str(status).lower()}")
    if log.get("error_code"):
        signals.append(f"error_code:{log['error_code']}")
    fb = log.get("user_feedback")
    if fb is not None:
        try:
            if int(fb) < 0:
                signals.append("user_feedback:negative")
        except (TypeError, ValueError):
            pass
    retry = log.get("retry_count")
    if retry is not None:
        try:
            if int(retry) > 0:
                signals.append(f"retry_count:{retry}")
        except (TypeError, ValueError):
            pass
    return signals


async def _process_one(log: dict[str, Any]) -> dict[str, Any]:
    """Embed → classify (CatBoost on vectors) → online cluster → persist meta + qdrant."""
    request_id = log["request_id"]
    query_text = (log.get("query_text") or "").strip()
    if not query_text:
        return {"request_id": request_id, "rejected": True, "reason": "empty_query"}

    meta: MetaStore = app.state.meta
    if meta.has_assignment(request_id):
        return {"request_id": request_id, "duplicate": True}

    # One embedding for both classification and online clustering / Qdrant.
    _original, _normalized, _lt, emb_list = await app.state.online.embed_query(query_text)
    emb = np.asarray(emb_list, dtype=np.float32)
    clf = app.state.classifier.predict_with_confidence(query_text, embedding=emb)
    task_type = clf["task_type"]
    online = await app.state.online.process(
        request_id=request_id,
        query_text=query_text,
        task_type=task_type,
        embedding=emb_list,
    )

    signals = _failure_signals(log)
    assignment = {
        "request_id": request_id,
        "task_type": task_type,
        "classification_confidence": clf.get("classification_confidence", 0.0),
        "scenario_id": online.scenario_id,
        "is_outlier": False,
        "has_failure_signals": bool(signals),
        "failure_signals": signals,
        "source_id": log.get("source_id"),
        "timestamp": log.get("timestamp"),
        "query_text": query_text,
        "response_status": log.get("response_status"),
        "error_code": log.get("error_code"),
        "user_feedback": log.get("user_feedback"),
        "retry_count": log.get("retry_count"),
        "long_text_strategy": getattr(online, "long_text_strategy", None),
    }
    meta.upsert_assignment(assignment)

    qdrant: Optional[QdrantStore] = getattr(app.state, "qdrant", None)
    if qdrant is not None:
        qdrant.upsert(
            request_id,
            online.embedding,
            payload={
                "request_id": request_id,
                "task_type": task_type,
                "scenario_id": online.scenario_id,
                "timestamp": str(log.get("timestamp") or ""),
                "source_id": log.get("source_id"),
                "is_outlier": False,
                "has_failure_signals": bool(signals),
                "failure_signals": signals,
            },
        )

    source_id = log.get("source_id") or "_unknown"
    meta.bump_ingest_log(source_id, classified=1, assigned=1)
    return assignment


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.taxonomy = Taxonomy()
    fb = settings.classifier.fallback_mode
    model_path = os.getenv("CLASSIFIER_MODEL_PATH") or settings.classifier.model_path
    # Resolve relative path against ml_service root
    from pathlib import Path

    mp = Path(model_path)
    if not mp.is_file():
        candidates = [
            Path.cwd() / model_path,
            Path(__file__).resolve().parents[1] / "app" / "models" / "catboost_task_classifier.cbm",
            Path(__file__).resolve().parents[1] / "models" / "catboost_task_classifier.cbm",
            Path(model_path.lstrip("/")),
        ]
        for c in candidates:
            if c.is_file():
                mp = c
                break
    model_path = str(mp) if mp.is_file() else model_path

    # Only force keyword when: no .cbm AND no OpenRouter AND offline mock embeddings
    if not Path(model_path).is_file() and fb == "llm":
        if not (os.getenv("OPENROUTER_API_KEY") or settings.llm.openrouter_api_key):
            if os.getenv("EMBEDDINGS_PROVIDER", settings.embeddings.provider) == "mock":
                fb = "keyword"

    app.state.classifier = CatBoostClassifier(
        model_path=model_path,
        taxonomy=app.state.taxonomy.taxonomy
        if hasattr(app.state.taxonomy, "taxonomy")
        else app.state.taxonomy,
        config={
            "fallback_mode": fb,
            "confidence_threshold": settings.classifier.confidence_threshold,
        },
    )
    log_event(
        logger,
        "classifier ready",
        stage="startup",
        model_path=model_path,
        model_loaded=getattr(app.state.classifier, "model_available", False),
        fallback_mode=fb,
    )

    # Offline (Ollama): auto-pull missing models if OLLAMA_AUTO_PULL (default on)
    try:
        from app.core.ollama_bootstrap import ensure_ollama_models, models_for_offline_settings

        ollama_base, ollama_models = models_for_offline_settings(settings)
        if ollama_models:
            log_event(
                logger,
                "ollama bootstrap start",
                stage="startup",
                base=ollama_base,
                models=",".join(ollama_models),
            )
            pull_report = await ensure_ollama_models(ollama_base, ollama_models)
            app.state.ollama_bootstrap = pull_report
            log_event(
                logger,
                "ollama bootstrap done",
                stage="startup",
                models=str(pull_report.get("models")),
                errors=str(pull_report.get("errors") or []),
            )
        else:
            app.state.ollama_bootstrap = {"models": {}, "errors": []}
    except Exception as exc:  # noqa: BLE001
        logger.warning("ollama bootstrap skipped: %s", exc)
        app.state.ollama_bootstrap = {"models": {}, "errors": [str(exc)]}

    try:
        from app.pipeline.clustering_batch.umap_hdbscan import _HAS_UMAP_HDBSCAN

        if not _HAS_UMAP_HDBSCAN:
            logger.error(
                "UMAP/HDBSCAN not installed — recompute will NOT form real clusters. "
                "pip install 'umap-learn>=0.5.6' 'hdbscan>=0.8.40'"
            )
        else:
            logger.info("UMAP+HDBSCAN libraries available for recompute")
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not probe UMAP/HDBSCAN: %s", exc)

    app.state.online = OnlinePipeline(settings=settings)
    app.state.qdrant = QdrantStore(
        _store_dict(),
        vector_size=settings.embeddings.dim,
    )
    meta_url = os.getenv("ML_META_DB_URL") or settings.store.meta_db_url
    if meta_url.startswith("sqlite:////data/") and os.name == "nt":
        meta_url = os.getenv("ML_META_DB_URL", "sqlite:///./ml_meta.db")
    app.state.meta = MetaStore(meta_url)

    job_mod.STORE = RecomputeStore(persistence=app.state.meta)

    _restore_recompute_state()
    n_hydrated = _hydrate_online_clusterer()
    logger.info(
        "restored from meta: centroids=%s last_recompute_at=%s logs_at_last_recompute=%s",
        n_hydrated,
        _LAST_RECOMPUTE_AT,
        _LOGS_AT_LAST_RECOMPUTE,
    )

    app.state.ingest_queue = IngestQueue()
    app.state.ingest_worker = IngestWorker(
        app.state.ingest_queue,
        _process_one,
        concurrency=settings.ingest.worker_concurrency,
    )
    await app.state.ingest_worker.start()

    app.state.scheduler = None
    sched_enabled = os.getenv("RECOMPUTE_SCHEDULER_ENABLED", "").lower() in (
        "1",
        "true",
        "yes",
    )
    if sched_enabled and hasattr(Scheduler, "from_config"):
        try:
            app.state.scheduler = Scheduler.from_config({"recompute": {"interval_hours": settings.recompute.interval_hours if hasattr(settings.recompute, "interval_hours") else 2}})
        except Exception:  # noqa: BLE001
            app.state.scheduler = None

    log_event(
        logger,
        "ML service started",
        stage="startup",
        embeddings_provider=settings.embeddings.provider,
        meta=meta_url,
        qdrant_mock=getattr(app.state.qdrant, "is_mock", True),
    )
    yield
    await app.state.ingest_worker.stop()
    await app.state.online.close()
    if hasattr(app.state.meta, "close"):
        app.state.meta.close()
    log_event(logger, "ML service stopped", stage="shutdown")


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


@app.exception_handler(MLServiceError)
async def ml_service_error_handler(_request: Request, exc: MLServiceError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code or 500, content=exc.to_dict())


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=error_response(
            INVALID_REQUEST,
            "Request validation failed",
            retryable=False,
            details={"errors": exc.errors()},
        ),
    )


def _pipeline_metadata() -> dict[str, Any]:
    meta = {
        "schema_version": SCHEMA_VERSION,
        "pipeline_version": PIPELINE_VERSION,
        "taxonomy_version": TAXONOMY_VERSION,
        "classifier_mode": settings.classifier.provider,
        "classifier_fallback_mode": settings.classifier.fallback_mode,
        "online_similarity_threshold": settings.online_clustering.similarity_threshold,
    }
    if hasattr(settings, "pipeline_metadata_params"):
        meta.update(settings.pipeline_metadata_params())
    return meta


def _agg_config() -> AggregationConfig:
    ad = getattr(settings, "aggregation_defaults", None)
    return AggregationConfig(
        top_tasks_limit=int(getattr(ad, "top_tasks_limit", 7) if ad else 7),
        top_scenarios_limit=int(getattr(ad, "top_scenarios_limit", 9) if ad else 9),
        trend_threshold_percent=float(
            getattr(ad, "trend_threshold_percent", 15.0) if ad else 15.0
        ),
        trend_min_total=int(getattr(ad, "trend_min_total", 20) if ad else 20),
        trend_min_previous=int(getattr(ad, "trend_min_previous", 5) if ad else 5),
        schema_version=SCHEMA_VERSION,
        taxonomy_version=TAXONOMY_VERSION,
        pipeline_version=PIPELINE_VERSION,
    )


def _restore_recompute_state() -> None:
    """Recover freshness bookkeeping from the meta store on startup.

    `last_recompute_at` and the log count it was taken at lived only in module
    globals, so a restart reported "never recomputed" and the dashboard demanded
    a fresh (expensive) run over data that was already clustered. Jobs written
    before `logs_at_completion` existed leave the count at 0, which reads as
    stale — the conservative direction.
    """
    global _LAST_RECOMPUTE_AT, _LOGS_AT_LAST_RECOMPUTE
    try:
        job = app.state.meta.get_last_completed_job()
    except Exception:
        logger.exception("could not restore recompute state")
        return
    if not job:
        return
    _LAST_RECOMPUTE_AT = job.get("completed_at")
    _LOGS_AT_LAST_RECOMPUTE = int(job.get("logs_at_completion") or 0)


def _hydrate_online_clusterer() -> int:
    """Reload cosine centroids from the clusters table.

    Without this the online path starts every boot with no centroids, so the
    first logs after a restart each open a brand-new scenario instead of joining
    the clusters recompute already built.
    """
    clusterer = getattr(getattr(app.state, "online", None), "clusterer", None)
    if clusterer is None:
        return 0
    try:
        rows = [
            {
                "scenario_id": c["scenario_id"],
                "task_type": c.get("task_type") or "unknown",
                "centroid": c["centroid"],
                "count": int(c.get("records_count") or 1),
            }
            for c in app.state.meta.list_clusters()
            if c.get("centroid")
        ]
    except Exception:
        logger.exception("could not load centroids from meta store")
        return 0
    clusterer.clear()
    return clusterer.load_centroids(rows)


def _freshness() -> dict[str, Any]:
    """Is the read model stale, and is anything being done about it?

    `recompute_pending` answers "does the stored analysis lag behind the logs",
    which is what the dashboard banner asks. It used to report "is a job running
    right now", so a store with thousands of unclustered logs and no job reported
    `false` — the one state the banner exists to catch.
    """
    meta: MetaStore = app.state.meta
    total = meta.count_assignments()
    logs_since = max(0, total - _LOGS_AT_LAST_RECOMPUTE)

    running = any(
        job.get("status") in ("pending", "running")
        for job in job_mod.STORE.jobs.values()
    )
    # Never recomputed but logs exist -> stale. Recomputed earlier but new logs
    # arrived since -> stale. A job already in flight is not "pending work".
    never_recomputed = _LAST_RECOMPUTE_AT is None
    stale = (never_recomputed and total > 0) or logs_since > 0

    return {
        "last_recompute_at": _LAST_RECOMPUTE_AT,
        "logs_since_last_recompute": logs_since,
        "recompute_pending": stale and not running,
        "recompute_running": running,
    }


@app.get("/health/live")
async def health_live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
async def health_ready() -> dict[str, Any]:
    qdrant = getattr(app.state, "qdrant", None)
    classifier = getattr(app.state, "classifier", None)
    clf_status = "ok"
    if classifier is not None and hasattr(classifier, "readiness_status"):
        rs = classifier.readiness_status()
        if isinstance(rs, dict):
            clf_status = str(rs.get("status") or "ok")
        else:
            clf_status = str(rs)
    elif classifier is not None and hasattr(classifier, "is_ready"):
        ready = classifier.is_ready
        if callable(ready):
            ready = ready()
        clf_status = "ok" if ready else "degraded"

    qdrant_mock = True
    if qdrant is not None:
        qdrant_mock = bool(getattr(qdrant, "is_mock", getattr(qdrant, "_mock", True)))

    emb_provider = settings.embeddings.resolve_provider()
    llm_provider = settings.llm.resolve_provider()
    if llm_provider == "openrouter":
        llm_status = (
            "ok"
            if (settings.llm.openrouter_api_key or os.getenv("OPENROUTER_API_KEY", ""))
            else "degraded"
        )
    else:
        llm_status = "ok"  # ollama offline — assume local; failure surfaces at recompute

    checks = {
        "config": "ok" if settings.is_valid() else "fail",
        "embeddings_mode": settings.embeddings.mode,
        "embeddings_provider": emb_provider,
        "llm_mode": settings.llm.mode,
        "llm_provider": f"{llm_provider}:{llm_status}",
        "classifier": clf_status,
        "qdrant": "mock" if (qdrant is None or qdrant_mock) else "ok",
        "meta_store": "ok" if getattr(app.state, "meta", None) else "missing",
        "clusters_loaded": app.state.online.clusterer.cluster_count()
        if getattr(app.state, "online", None)
        else 0,
    }
    status = "ready"
    if not settings.is_valid():
        status = "not_ready"
    elif clf_status in ("degraded", "not_ready") or qdrant_mock or llm_status == "degraded":
        status = "degraded"
    if checks["meta_store"] == "missing":
        status = "not_ready"
    return {"status": status, "checks": checks}


def _validate_timestamp(ts: Any) -> bool:
    if ts is None:
        return False
    if isinstance(ts, datetime):
        return True
    s = str(ts).strip()
    if not s:
        return False
    try:
        datetime.fromisoformat(s.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


@app.put("/api/v1/logs", status_code=202, dependencies=[Depends(require_service_token)])
async def put_logs(batch: LogBatch) -> dict[str, Any]:
    accepted = 0
    duplicates = 0
    rejected = 0
    source_id: Optional[str] = None
    to_process: list[dict[str, Any]] = []
    meta: MetaStore = app.state.meta
    seen_in_batch: set[str] = set()

    max_size = settings.ingest.batch_max_size
    logs = batch.logs[:max_size] if max_size > 0 else batch.logs

    for item in logs:
        source_id = source_id or item.source_id
        query = (item.query_text or "").strip()
        if not query:
            rejected += 1
            continue
        if not _validate_timestamp(item.timestamp):
            rejected += 1
            continue
        rid = item.request_id
        if not rid or rid in seen_in_batch:
            duplicates += 1
            continue
        seen_in_batch.add(rid)
        if meta.has_assignment(rid):
            duplicates += 1
            continue
        to_process.append(item.model_dump(mode="json"))
        accepted += 1

    if source_id:
        meta.bump_ingest_log(
            source_id, accepted=accepted, rejected=rejected, duplicates=duplicates
        )

    if to_process:
        await app.state.ingest_queue.enqueue(to_process)

    return {
        "accepted": accepted,
        "duplicates": duplicates,
        "rejected": rejected,
        "source_id": source_id,
    }


def _pending_for_recompute() -> list[dict[str, Any]]:
    meta: MetaStore = app.state.meta
    qdrant: Optional[QdrantStore] = getattr(app.state, "qdrant", None)
    vectors_by_id: dict[str, list[float]] = {}
    if qdrant is not None:
        for p in qdrant.get_all():
            vectors_by_id[p["request_id"]] = p.get("vector") or []

    out: list[dict[str, Any]] = []
    for a in meta.all_assignments():
        rid = a["request_id"]
        out.append(
            {
                "request_id": rid,
                "task_type": a.get("task_type"),
                "embedding": vectors_by_id.get(rid) or [0.0] * settings.embeddings.dim,
                "query_text": a.get("query_text"),
                "source_id": a.get("source_id"),
                "timestamp": a.get("timestamp"),
            }
        )
    return out


@app.post("/api/v1/recompute", status_code=202, dependencies=[Depends(require_service_token)])
async def post_recompute(background: BackgroundTasks) -> dict[str, str]:
    summarizer = Summarizer.from_settings(settings)
    store = job_mod.STORE
    job = RecomputeJob(
        store=store,
        summarizer=summarizer,
        qdrant=getattr(app.state, "qdrant", None),
        enable_summarization=True,
        config={
            "recompute": {
                "umap": settings.pipeline_metadata_params().get("umap", {}),
                "hdbscan": settings.pipeline_metadata_params().get("hdbscan", {}),
                "max_clusters_per_task_type": getattr(
                    settings.recompute, "max_clusters_per_task_type", 5
                ),
            },
            "llm": {
                "mode": settings.llm.mode,
                "provider": settings.llm.resolve_provider(),
            },
        },
    )
    app.state.meta.put_job(job.result)
    data = _pending_for_recompute()

    async def _run() -> None:
        global _LAST_RECOMPUTE_AT, _LOGS_AT_LAST_RECOMPUTE
        try:
            logger.info(
                "recompute start job_id=%s records=%s", job.job_id, len(data)
            )
            result = await job.run(data)
            app.state.meta.put_job(result)

            # Batch meta updates (was N× commit)
            assign_rows = [
                {
                    "request_id": rid,
                    "scenario_id": a.get("scenario_id"),
                    "is_outlier": bool(a.get("is_outlier", False)),
                }
                for rid, a in store.assignments.items()
            ]
            if hasattr(app.state.meta, "update_assignment_scenarios_batch"):
                n_meta = app.state.meta.update_assignment_scenarios_batch(assign_rows)
            else:
                n_meta = 0
                for row in assign_rows:
                    app.state.meta.update_assignment_scenario(
                        row["request_id"],
                        scenario_id=row.get("scenario_id"),
                        is_outlier=bool(row.get("is_outlier", False)),
                    )
                    n_meta += 1
            logger.info("recompute meta assignments updated n=%s", n_meta)

            for sid, cluster in store.clusters.items():
                payload = dict(cluster)
                if sid in store.centroids:
                    payload["centroid"] = store.centroids[sid]
                app.state.meta.upsert_cluster(payload)
            logger.info("recompute clusters upserted n=%s", len(store.clusters))

            # Batch Qdrant rewrite (was N× get + N× upsert hang)
            qdrant: Optional[QdrantStore] = getattr(app.state, "qdrant", None)
            if qdrant is not None and store.assignments:
                by_data = {str(d.get("request_id")): d for d in data}
                points: list[dict[str, Any]] = []
                for rid, a in store.assignments.items():
                    d = by_data.get(str(rid)) or {}
                    vec = d.get("embedding") or []
                    if not vec:
                        existing = qdrant.get(rid) if hasattr(qdrant, "get") else None
                        if not existing:
                            continue
                        vec = existing.get("vector") or []
                        base_payload = dict(existing.get("payload") or {})
                    else:
                        base_payload = {
                            "request_id": rid,
                            "task_type": a.get("task_type") or d.get("task_type"),
                            "source_id": d.get("source_id"),
                            "timestamp": str(d.get("timestamp") or ""),
                            "query_text": d.get("query_text"),
                        }
                    base_payload["request_id"] = rid
                    base_payload["task_type"] = a.get("task_type") or base_payload.get(
                        "task_type"
                    )
                    base_payload["scenario_id"] = a.get("scenario_id")
                    base_payload["is_outlier"] = bool(a.get("is_outlier", False))
                    points.append(
                        {"request_id": rid, "vector": vec, "payload": base_payload}
                    )
                n_qd = qdrant.upsert_batch(points, batch_size=64, wait=False)
                logger.info("recompute qdrant batch upsert n=%s", n_qd)

            _LAST_RECOMPUTE_AT = result.get("completed_at")
            _LOGS_AT_LAST_RECOMPUTE = app.state.meta.count_assignments()
            # Ride along on the job row so a restart can restore both.
            result["logs_at_completion"] = _LOGS_AT_LAST_RECOMPUTE
            app.state.meta.put_job(result)

            # Recompute replaced the cluster set; move the online path onto the
            # new centroids so streaming assignments agree with what was stored.
            n_hydrated = _hydrate_online_clusterer()
            logger.info(
                "recompute fully done job_id=%s status=%s clusters=%s centroids=%s",
                job.job_id,
                result.get("status"),
                result.get("clusters_created"),
                n_hydrated,
            )
        except Exception:  # noqa: BLE001
            logger.exception("recompute failed job_id=%s", job.job_id)
            app.state.meta.put_job(job.result)

    background.add_task(_run)
    return {"job_id": job.job_id, "status": "pending"}


@app.get("/api/v1/recompute/{job_id}", dependencies=[Depends(require_service_token)])
async def get_recompute(job_id: str) -> dict[str, Any]:
    job = app.state.meta.get_job(job_id) or job_mod.STORE.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=404, detail={"code": "NOT_FOUND", "message": "job not found"}
        )
    return job


@app.get("/api/v1/statistics", dependencies=[Depends(require_service_token)])
async def get_statistics(
    source_id: Optional[str] = Query(default=None),
    from_date: Optional[str] = Query(default=None, alias="from"),
    to_date: Optional[str] = Query(default=None, alias="to"),
) -> dict[str, Any]:
    assignments = app.state.meta.all_assignments(
        source_id=source_id, from_date=from_date, to_date=to_date
    )
    clusters = {c["scenario_id"]: c for c in app.state.meta.list_clusters()}
    if not clusters and job_mod.STORE.clusters:
        clusters = dict(job_mod.STORE.clusters)
    payload = build_statistics(
        assignments,
        clusters=clusters,
        source_id=source_id,
        from_date=from_date,
        to_date=to_date,
        config=_agg_config(),
        freshness=_freshness(),
        pipeline_metadata=_pipeline_metadata(),
    )
    # backward-compat aliases used by early ingest tests
    totals = payload.get("totals") or {}
    payload.setdefault("total_logs", totals.get("records_total", len(assignments)))
    return payload


@app.get("/api/v1/assignments", dependencies=[Depends(require_service_token)])
async def get_assignments(
    source_id: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    from_date: Optional[str] = Query(default=None, alias="from"),
    to_date: Optional[str] = Query(default=None, alias="to"),
) -> dict[str, Any]:
    page = app.state.meta.list_assignments(
        source_id=source_id,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
        offset=offset,
    )
    cleaned = []
    for a in page["items"]:
        cluster = app.state.meta.get_cluster(a.get("scenario_id") or "")
        cleaned.append(
            {
                "request_id": a.get("request_id"),
                "task_type": a.get("task_type"),
                "classification_confidence": a.get("classification_confidence"),
                "scenario_id": a.get("scenario_id"),
                "scenario_name": (cluster or {}).get("name")
                or job_mod.STORE.clusters.get(a.get("scenario_id") or "", {}).get("name"),
                "is_outlier": bool(a.get("is_outlier")),
                "has_failure_signals": bool(a.get("has_failure_signals")),
                "source_id": a.get("source_id"),
                "timestamp": a.get("timestamp"),
            }
        )
    return {
        "items": cleaned,
        "total": page["total"],
        "pipeline_metadata": _pipeline_metadata(),
    }


@app.get("/api/v1/scenarios", dependencies=[Depends(require_service_token)])
async def get_scenarios(
    source_id: Optional[str] = Query(default=None),
    from_date: Optional[str] = Query(default=None, alias="from"),
    to_date: Optional[str] = Query(default=None, alias="to"),
) -> dict[str, Any]:
    assignments = app.state.meta.all_assignments(
        source_id=source_id, from_date=from_date, to_date=to_date
    )
    clusters = {c["scenario_id"]: c for c in app.state.meta.list_clusters()}
    if not clusters and job_mod.STORE.clusters:
        clusters = dict(job_mod.STORE.clusters)
    return build_scenarios_list(
        assignments,
        clusters=clusters,
        source_id=source_id,
        from_date=from_date,
        to_date=to_date,
        config=_agg_config(),
    )


@app.get("/api/v1/scenarios/{scenario_id}", dependencies=[Depends(require_service_token)])
async def get_scenario(
    scenario_id: str,
    source_id: Optional[str] = Query(default=None),
    from_date: Optional[str] = Query(default=None, alias="from"),
    to_date: Optional[str] = Query(default=None, alias="to"),
) -> dict[str, Any]:
    assignments = app.state.meta.all_assignments(
        source_id=source_id, from_date=from_date, to_date=to_date
    )
    clusters = {c["scenario_id"]: c for c in app.state.meta.list_clusters()}
    if not clusters and job_mod.STORE.clusters:
        clusters = dict(job_mod.STORE.clusters)
    result = build_scenarios_list(
        assignments,
        clusters=clusters,
        source_id=source_id,
        from_date=from_date,
        to_date=to_date,
        config=_agg_config(),
        scenario_id=scenario_id,
    )
    if result.get("items"):
        return result["items"][0]
    if scenario_id not in clusters:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": f"scenario {scenario_id} not found"},
        )
    meta = clusters[scenario_id]
    return {
        "scenario_id": scenario_id,
        "task_type": meta.get("task_type"),
        "name": meta.get("name"),
        "summary": meta.get("summary"),
        "count": 0,
        "trend": "insufficient_data",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
