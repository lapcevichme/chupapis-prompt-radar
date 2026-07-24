"""Minimal mock ML service for backend E1 dev/testing.

Implements the streaming-CQRS contract (docs/contracts/backend-ml.md) with
deterministic keyword classification and in-memory storage. Not for production.
"""

import hashlib
import os
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, Request

SERVICE_TOKEN = os.getenv(
    "MOCK_ML_SERVICE_TOKEN", os.getenv("ML_SERVICE_TOKEN", "dev-ml-token")
)
RECOMPUTE_SECONDS = float(os.getenv("MOCK_ML_RECOMPUTE_SECONDS", "1"))
CLUSTERS_PER_TYPE = 3

CLASSES = [
    "text_generation",
    "code_help",
    "data_analysis",
    "education",
    "information_search",
    "task_management",
    "other",
]

KEYWORDS: dict[str, list[str]] = {
    "code_help": [
        "код",
        "функци",
        "sql",
        "скрипт",
        "python",
        "javascript",
        "debug",
        "баг",
        "регуляр",
        "запрос к бд",
        "напиши класс",
        "рефактор",
    ],
    "data_analysis": [
        "excel",
        "таблиц",
        "отчёт",
        "отчет",
        "выгруз",
        "аналитик",
        "данны",
        "дашборд",
        "диаграмм",
        "статистик",
        "метрик",
        "график",
    ],
    "information_search": [
        "найди",
        "поиск",
        "собери информац",
        "письм",
        "почт",
        "crm",
        "confluence",
        "ресёрч",
        "ресерч",
        "узнай",
        "сводк",
        "непрочитан",
    ],
    "task_management": [
        "задач",
        "jira",
        "тикет",
        "встреч",
        "календар",
        "напомни",
        "план",
        "дедлайн",
        "совещани",
        "митинг",
        "поручени",
    ],
    "education": [
        "объясни",
        "что значит",
        "что такое",
        "как работает",
        "обучени",
        "расскажи про",
        "в чём разница",
        "в чем разница",
        "почему",
    ],
    "text_generation": [
        "напиши письмо",
        "напиши пост",
        "сгенерируй",
        "составь",
        "сформулируй",
        "инструкци",
        "ответ клиент",
        "поздравл",
        "текст для",
    ],
}

app = FastAPI(title="Mock ML Service", version="0.1.0")

# (source_id, request_id) -> stored log + derived assignment.
_LOGS: dict[tuple[str, str], dict[str, Any]] = {}
_JOBS: dict[str, dict[str, Any]] = {}
_LAST_RECOMPUTE_AT: str | None = None
_LOGS_SINCE_RECOMPUTE = 0
_SCENARIO_NAMES: dict[str, dict[str, Any]] = {}
_JOB_SEQ = 0


def _require_token(token: str | None) -> None:
    if token != SERVICE_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid X-Service-Token")


def _stable_hash(text: str) -> int:
    return int(hashlib.md5(text.encode("utf-8")).hexdigest(), 16)


def _classify(query_text: str) -> tuple[str, float]:
    low = query_text.lower()
    best_class, best_count = None, 0
    for cls, words in KEYWORDS.items():
        count = sum(1 for w in words if w in low)
        if count > best_count:
            best_class, best_count = cls, count

    if best_count > 0:
        return best_class, round(min(0.95, 0.7 + 0.08 * best_count), 2)

    h = _stable_hash(query_text)
    if h % 6 == 0:
        return "unknown", 0.4
    return CLASSES[h % len(CLASSES)], 0.5


def _assign(
    source_id: str, request_id: str, query_text: str, task_type: str
) -> dict[str, Any]:
    h = _stable_hash(query_text)
    bucket = h % CLUSTERS_PER_TYPE
    base = task_type if task_type != "unknown" else "other"
    scenario_id = f"{base}:cluster_{bucket:02d}"
    is_outlier = _stable_hash(f"{source_id}:{request_id}") % 20 == 0
    return {"scenario_id": scenario_id, "is_outlier": is_outlier}


@app.get("/health/live")
async def health_live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
async def health_ready() -> dict[str, Any]:
    return {
        "status": "ready",
        "checks": {
            "config": "ok",
            "qdrant": "ok",
            "classifier": "ok",
            "embeddings_provider": "ok",
            "llm_provider": "ok",
        },
    }


@app.put("/api/v1/logs")
async def put_logs(
    request: Request, x_service_token: str | None = Header(None)
) -> dict[str, Any]:
    _require_token(x_service_token)
    global _LOGS_SINCE_RECOMPUTE
    body = await request.json()
    source_id = str(body.get("source_id"))
    logs = body.get("logs", [])

    accepted, duplicates, rejected = 0, 0, 0
    for log in logs:
        request_id = log.get("request_id")
        query_text = (log.get("query_text") or "").strip()
        if not request_id or not query_text:
            rejected += 1
            continue
        key = (source_id, request_id)
        if key in _LOGS:
            duplicates += 1
        task_type, confidence = _classify(query_text)
        assignment = _assign(source_id, request_id, query_text, task_type)
        error_code = log.get("error_code")
        response_status = log.get("response_status")
        has_failure = bool(error_code) or response_status == "error"
        _LOGS[key] = {
            "source_id": source_id,
            "request_id": request_id,
            "query_text": query_text,
            "timestamp": log.get("timestamp"),
            "response_status": response_status,
            "error_code": error_code,
            "task_type": task_type,
            "classification_confidence": confidence,
            "scenario_id": assignment["scenario_id"],
            "is_outlier": assignment["is_outlier"],
            "has_failure_signals": has_failure,
        }
        accepted += 1
        _LOGS_SINCE_RECOMPUTE += 1

    return {
        "accepted": accepted,
        "duplicates": duplicates,
        "rejected": rejected,
        "source_id": source_id,
    }


@app.post("/api/v1/recompute", status_code=202)
async def recompute(
    request: Request, x_service_token: str | None = Header(None)
) -> dict[str, Any]:
    _require_token(x_service_token)
    global _JOB_SEQ
    _JOB_SEQ += 1
    job_id = f"rc_{_JOB_SEQ:02d}"
    _JOBS[job_id] = {
        "job_id": job_id,
        "status": "running",
        "started_at": datetime.now(UTC).isoformat(),
        "started_ts": datetime.now(UTC).timestamp(),
    }
    return {
        "job_id": job_id,
        "status": "running",
        "started_at": _JOBS[job_id]["started_at"],
    }


@app.get("/api/v1/recompute/{job_id}")
async def recompute_status(
    job_id: str, x_service_token: str | None = Header(None)
) -> dict[str, Any]:
    _require_token(x_service_token)
    job = _JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    elapsed = datetime.now(UTC).timestamp() - job["started_ts"]
    if job["status"] == "running" and elapsed >= RECOMPUTE_SECONDS:
        _finish_recompute(job)

    return {
        "job_id": job_id,
        "status": job["status"],
        "clusters_created": job.get("clusters_created"),
        "scenarios_named": job.get("scenarios_named"),
        "finished_at": job.get("finished_at"),
    }


def _finish_recompute(job: dict[str, Any]) -> None:
    global _LAST_RECOMPUTE_AT, _LOGS_SINCE_RECOMPUTE
    scenario_ids = sorted({log["scenario_id"] for log in _LOGS.values()})
    for index, scenario_id in enumerate(scenario_ids, start=1):
        task_type = scenario_id.split(":", 1)[0]
        _SCENARIO_NAMES[scenario_id] = {
            "name": f"Сценарий {task_type} #{index}",
            "summary": f"Кластер запросов категории {task_type}.",
            "user_goal": "Ускорить рутинные операции.",
            "automation_potential": ["low", "medium", "high"][index % 3],
        }
    _LAST_RECOMPUTE_AT = datetime.now(UTC).isoformat()
    _LOGS_SINCE_RECOMPUTE = 0
    job["status"] = "completed"
    job["clusters_created"] = len(scenario_ids)
    job["scenarios_named"] = len(scenario_ids)
    job["finished_at"] = _LAST_RECOMPUTE_AT


def _filtered_logs(source_id: str | None) -> list[dict[str, Any]]:
    if not source_id:
        return list(_LOGS.values())
    return [log for log in _LOGS.values() if log["source_id"] == source_id]


def _build_scenarios(logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for log in logs:
        grouped.setdefault(log["scenario_id"], []).append(log)

    scenarios = []
    for scenario_id, members in grouped.items():
        meta = _SCENARIO_NAMES.get(scenario_id, {})
        task_type = scenario_id.split(":", 1)[0]
        scenarios.append(
            {
                "scenario_id": scenario_id,
                "task_type": task_type,
                "name": meta.get("name"),
                "summary": meta.get("summary"),
                "user_goal": meta.get("user_goal"),
                "representative_examples": [m["query_text"] for m in members[:2]],
                "pain_points": ["Ручные повторяющиеся операции"],
                "automation_potential": meta.get("automation_potential"),
                "count": len(members),
                "trend": "stable" if meta else "new",
                "growth_rate_percent": 0.0,
                "statistical_reliability": "high" if len(members) >= 20 else "low",
            }
        )
    scenarios.sort(key=lambda s: s["count"], reverse=True)
    return scenarios


@app.get("/api/v1/statistics")
async def statistics(
    source_id: str | None = Query(None),
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    x_service_token: str | None = Header(None),
) -> dict[str, Any]:
    _require_token(x_service_token)
    logs = _filtered_logs(source_id)
    total = len(logs)

    task_counter = Counter(log["task_type"] for log in logs)
    scenarios = _build_scenarios(logs)
    outliers = [log for log in logs if log["is_outlier"]]
    outlier_pct = round(len(outliers) / total * 100, 1) if total else 0.0

    failures = [log for log in logs if log["has_failure_signals"]]
    signal_counter = Counter(log["error_code"] for log in failures if log["error_code"])
    failure_analysis = (
        {
            "status": "available",
            "total_requests_with_failure_signals": len(failures),
            "failure_signal_percentage": round(len(failures) / total * 100, 1)
            if total
            else 0.0,
            "top_failure_signals": [
                {"signal": s, "count": c} for s, c in signal_counter.most_common()
            ],
        }
        if failures
        else {"status": "not_available"}
    )

    dynamics_counter: Counter[str] = Counter()
    for log in logs:
        ts = log.get("timestamp") or ""
        dynamics_counter[ts[:10]] += 1
    dynamics = [
        {"date": date, "count": count}
        for date, count in sorted(dynamics_counter.items())
        if date
    ]

    return {
        "schema_version": "1.0",
        "taxonomy_version": "v1",
        "pipeline_version": "mock-0.1",
        "generated_at": datetime.now(UTC).isoformat(),
        "filters_applied": {"source_id": source_id, "from": from_, "to": to},
        "freshness": {
            "last_recompute_at": _LAST_RECOMPUTE_AT,
            "logs_since_last_recompute": _LOGS_SINCE_RECOMPUTE,
            "recompute_pending": _LOGS_SINCE_RECOMPUTE > 0,
        },
        "totals": {
            "records_total": total,
            "scenarios_count": len(scenarios),
            "unknown_count": task_counter.get("unknown", 0),
            "outliers_percentage": outlier_pct,
        },
        "tasks_distribution": [
            {"task_type": task_type, "count": count}
            for task_type, count in task_counter.most_common()
        ],
        "top_scenarios": scenarios[:10],
        "dynamics": dynamics,
        "outliers_summary": {
            "total_outliers_count": len(outliers),
            "outlier_percentage": outlier_pct,
        },
        "failure_analysis": failure_analysis,
        "pipeline_metadata": {
            "classifier_mode": "mock_keyword",
            "classifier_model_version": "mock-0.1",
            "online_similarity_threshold": 0.75,
        },
    }


@app.get("/api/v1/assignments")
async def assignments(
    source_id: str | None = Query(None),
    limit: int = Query(500, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    updated_since: str | None = Query(None),
    x_service_token: str | None = Header(None),
) -> dict[str, Any]:
    _require_token(x_service_token)
    logs = _filtered_logs(source_id)
    logs.sort(key=lambda log: (log["source_id"], log["request_id"]))
    page = logs[offset : offset + limit]
    items = [
        {
            "source_id": log["source_id"],
            "request_id": log["request_id"],
            "task_type": log["task_type"],
            "classification_confidence": log["classification_confidence"],
            "scenario_id": log["scenario_id"],
            "scenario_name": _SCENARIO_NAMES.get(log["scenario_id"], {}).get("name"),
            "is_outlier": log["is_outlier"],
            "has_failure_signals": log["has_failure_signals"],
        }
        for log in page
    ]
    return {"items": items, "total": len(logs)}


@app.get("/api/v1/scenarios")
async def list_scenarios(
    source_id: str | None = Query(None),
    x_service_token: str | None = Header(None),
) -> dict[str, Any]:
    _require_token(x_service_token)
    scenarios = _build_scenarios(_filtered_logs(source_id))
    return {"items": scenarios, "total": len(scenarios)}
