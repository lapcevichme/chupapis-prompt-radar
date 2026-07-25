"""Live tests via OpenRouter API (real embeddings + optional LLM, no mocks).

Requires OPENROUTER_API_KEY (from env or ml_service/.env).

Run:
  cd ml_service
  $env:LIVE_BACKEND='openrouter'
  pytest tests/live/test_openrouter_real.py -m live -v
"""
from __future__ import annotations

import time

import numpy as np
import pytest

pytestmark = [pytest.mark.live, pytest.mark.openrouter]


def _cos(a, b) -> float:
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    return float(np.dot(a, b) / ((np.linalg.norm(a) * np.linalg.norm(b)) + 1e-12))


@pytest.fixture(autouse=True)
def _only_openrouter(live_backend):
    if live_backend != "openrouter":
        pytest.skip("Set LIVE_BACKEND=openrouter for these tests")


@pytest.mark.asyncio
async def test_openrouter_embedding_adapter(require_openrouter, live_settings):
    from app.pipeline.embeddings.adapter import create_embedding_adapter

    live_settings.embeddings.mode = "online"
    live_settings.embeddings.provider = "openrouter"
    live_settings.embeddings.openrouter_api_key = require_openrouter
    adapter = create_embedding_adapter(live_settings.embeddings)
    assert adapter.provider_name == "openrouter"

    texts = [
        "напиши python function для парсинга json",
        "сделай pivot table в excel по продажам",
        "напиши python function для парсинга json",
    ]
    t0 = time.perf_counter()
    vecs = await adapter.embed(texts)
    elapsed = time.perf_counter() - t0
    await adapter.close()

    assert len(vecs) == 3
    dim = len(vecs[0])
    assert dim >= 256, dim
    c_same = _cos(vecs[0], vecs[2])
    c_diff = _cos(vecs[0], vecs[1])
    assert c_same > 0.99
    assert c_diff < 0.98
    print(
        f"\n[openrouter] embed model={live_settings.embeddings.openrouter_model} "
        f"dim={dim} elapsed={elapsed:.2f}s cos_same={c_same:.4f} cos_diff={c_diff:.4f}"
    )


@pytest.mark.asyncio
async def test_openrouter_catboost_on_embeddings(
    require_openrouter, require_cbm, live_settings
):
    from app.domain.taxonomy import Taxonomy
    from app.pipeline.classification.catboost_classifier import CatBoostClassifier
    from app.pipeline.embeddings.adapter import create_embedding_adapter

    live_settings.embeddings.mode = "online"
    live_settings.embeddings.provider = "openrouter"
    live_settings.embeddings.openrouter_api_key = require_openrouter
    adapter = create_embedding_adapter(live_settings.embeddings)

    queries = [
        "напиши sql запрос для отчёта по продажам из excel",
        "debug python asyncio exception in worker",
        "создай письмо клиенту с извинениями за задержку",
    ]
    vecs = await adapter.embed(queries)
    await adapter.close()

    tax = Taxonomy()
    clf = CatBoostClassifier(
        model_path=str(require_cbm),
        taxonomy=tax.taxonomy if hasattr(tax, "taxonomy") else tax,
        config={"fallback_mode": "fail_fast", "confidence_threshold": 0.01},
    )
    assert clf.model_available
    preds = clf.predict(queries, np.asarray(vecs, dtype=np.float32))
    for q, p in zip(queries, preds):
        assert p.get("source") == "catboost", p
        conf = float(p["confidence"])
        assert 0 < conf <= 1
        print(f"[openrouter] catboost conf={conf:.3f} type={p['task_type']} :: {q[:48]}")


def test_openrouter_api_logs_and_recompute(
    live_client, require_openrouter, require_cbm, live_settings
):
    payload = {
        "logs": [
            {
                "request_id": "or-api-1",
                "query_text": "напиши sql запрос для сводного отчёта по продажам",
                "timestamp": "2026-07-25T12:00:00Z",
                "source_id": "or_live",
            },
            {
                "request_id": "or-api-2",
                "query_text": "исправь баг в python asyncio queue",
                "timestamp": "2026-07-25T12:01:00Z",
                "source_id": "or_live",
            },
            {
                "request_id": "or-api-3",
                "query_text": "объясни простыми словами что такое REST API",
                "timestamp": "2026-07-25T12:02:00Z",
                "source_id": "or_live",
            },
        ]
    }
    r = live_client.put("/api/v1/logs", json=payload)
    assert r.status_code == 202, r.text
    assert r.json()["accepted"] == 3

    total = 0
    stats = {}
    for _ in range(180):
        time.sleep(0.5)
        stats = live_client.get("/api/v1/statistics").json()
        total = (stats.get("totals") or {}).get("records_total") or stats.get(
            "total_logs"
        ) or 0
        if total >= 3:
            break
    assert total >= 3, stats

    meta = stats.get("pipeline_metadata") or {}
    emb_p = meta.get("embedding_provider") or meta.get("embeddings_provider")
    assert emb_p == "openrouter", meta
    print(f"[openrouter] api stats totals={stats.get('totals')} emb={emb_p}")

    assigns = live_client.get("/api/v1/assignments").json()
    for a in assigns.get("items", []):
        print(
            f"[openrouter] assign {a.get('request_id')} "
            f"type={a.get('task_type')} conf={a.get('classification_confidence')}"
        )

    r2 = live_client.post("/api/v1/recompute")
    assert r2.status_code == 202
    job_id = r2.json()["job_id"]
    job = {}
    for _ in range(120):
        time.sleep(1.0)
        job = live_client.get(f"/api/v1/recompute/{job_id}").json()
        if job.get("status") in ("completed", "failed"):
            break
    assert job.get("status") == "completed", job
    print(
        f"[openrouter] recompute clusters={job.get('clusters_created')} "
        f"named={job.get('scenarios_named')} fallback={job.get('fallback_used')}"
    )

    # After recompute, scenarios should have names (LLM or technical)
    sc = live_client.get("/api/v1/scenarios").json()
    items = sc.get("items") or []
    assert len(items) >= 1
    for it in items[:5]:
        print(f"[openrouter] scenario {it.get('scenario_id')} name={it.get('name')!r}")


@pytest.mark.asyncio
async def test_openrouter_llm_summarize(require_openrouter, live_settings):
    from app.pipeline.summarization import Summarizer

    live_settings.llm.mode = "online"
    live_settings.llm.provider = "openrouter"
    live_settings.llm.openrouter_api_key = require_openrouter
    summ = Summarizer.from_settings(live_settings)
    assert summ.backend == "openrouter"
    assert summ.api_key

    result = await summ.summarize_scenario(
        "code_help:cluster_0",
        [
            "как исправить asyncio Queue empty",
            "debug python worker concurrency",
            "почему падает task exception в asyncio",
        ],
        "code_help",
    )
    await summ.close()
    assert result.name
    assert len(result.name.split()) <= 4
    assert result.summary
    assert result.summary != "Summary unavailable" or result.name.startswith("Сценарий")
    print(
        f"[openrouter] llm name={result.name!r} "
        f"summary={result.summary[:100]!r} auto={result.automation_potential}"
    )
