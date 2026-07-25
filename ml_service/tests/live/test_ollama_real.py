"""Live integration tests: real Ollama embeddings + CatBoost (no mocks).

Requires:
  - Ollama running
  - qwen3-embedding:4b (or OLLAMA_MODEL)
  - app/models/catboost_task_classifier.cbm for classification tests

Run:
  cd ml_service
  pytest tests/live -m live -v

  $env:OLLAMA_AUTO_PULL='true'; pytest tests/live -m live -v
"""
from __future__ import annotations

import os
import time

import numpy as np
import pytest

pytestmark = pytest.mark.live


def _cos(a, b) -> float:
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    return float(np.dot(a, b) / ((np.linalg.norm(a) * np.linalg.norm(b)) + 1e-12))


@pytest.mark.asyncio
async def test_live_ollama_embedding_adapter(require_embedding_model, live_settings):
    """Real Ollama embed: dim>0, same text ~identical, different text less similar."""
    from app.pipeline.embeddings.adapter import create_embedding_adapter

    live_settings.embeddings.mode = "offline"
    live_settings.embeddings.provider = "ollama"
    adapter = create_embedding_adapter(live_settings.embeddings)
    assert adapter.provider_name == "ollama"

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
    assert dim >= 256, f"unexpected embedding dim {dim}"
    assert len(vecs[1]) == dim
    assert adapter.dimension == dim

    c_same = _cos(vecs[0], vecs[2])
    c_diff = _cos(vecs[0], vecs[1])
    assert c_same > 0.99, f"same text cosine={c_same}"
    assert c_diff < 0.95, f"different text cosine unexpectedly high={c_diff}"
    print(
        f"\n[live] embed dim={dim} elapsed={elapsed:.2f}s "
        f"cos_same={c_same:.4f} cos_diff={c_diff:.4f}"
    )


@pytest.mark.asyncio
async def test_live_catboost_on_ollama_embeddings(
    require_embedding_model, require_cbm, live_settings
):
    """CatBoost .cbm predicts using real Ollama vectors (source=catboost)."""
    from app.domain.taxonomy import Taxonomy
    from app.pipeline.classification.catboost_classifier import CatBoostClassifier
    from app.pipeline.embeddings.adapter import create_embedding_adapter

    live_settings.embeddings.mode = "offline"
    live_settings.embeddings.provider = "ollama"
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
        config={
            "fallback_mode": "fail_fast",
            "confidence_threshold": 0.01,
        },
    )
    assert clf.model_available is True
    assert clf.is_ready is True

    X = np.asarray(vecs, dtype=np.float32)
    preds = clf.predict(queries, X)
    assert len(preds) == 3
    for q, p in zip(queries, preds):
        assert p.get("source") == "catboost", p
        conf = float(p.get("confidence") or 0)
        assert 0.0 < conf <= 1.0
        print(
            f"[live] catboost: conf={conf:.3f} type={p.get('task_type')} :: {q[:50]}"
        )


def test_live_api_logs_with_ollama_and_cbm(
    live_client, require_embedding_model, require_cbm
):
    """Full PUT /logs → assignments using real Ollama + CatBoost."""
    payload = {
        "logs": [
            {
                "request_id": "live-api-1",
                "query_text": "напиши sql запрос для сводного отчёта по продажам",
                "timestamp": "2026-07-25T12:00:00Z",
                "source_id": "live_test",
            },
            {
                "request_id": "live-api-2",
                "query_text": "исправь баг в python asyncio queue",
                "timestamp": "2026-07-25T12:01:00Z",
                "source_id": "live_test",
            },
            {
                "request_id": "live-api-3",
                "query_text": "объясни простыми словами что такое REST API",
                "timestamp": "2026-07-25T12:02:00Z",
                "source_id": "live_test",
            },
        ]
    }
    r = live_client.put("/api/v1/logs", json=payload)
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["accepted"] == 3
    assert body["rejected"] == 0

    total = 0
    stats = {}
    for _ in range(120):
        time.sleep(0.5)
        stats = live_client.get("/api/v1/statistics").json()
        total = (stats.get("totals") or {}).get("records_total") or stats.get(
            "total_logs"
        ) or 0
        if total >= 3:
            break
    assert total >= 3, f"timeout waiting for ingest, stats={stats}"

    assigns = live_client.get("/api/v1/assignments").json()
    assert assigns["total"] >= 3
    for a in assigns["items"]:
        assert a.get("request_id")
        assert a.get("scenario_id")
        conf = a.get("classification_confidence")
        assert conf is not None
        print(
            f"[live] api assign {a.get('request_id')} "
            f"type={a.get('task_type')} conf={conf} scenario={a.get('scenario_id')}"
        )

    meta = stats.get("pipeline_metadata") or {}
    emb_p = meta.get("embedding_provider") or meta.get("embeddings_provider")
    assert emb_p == "ollama", meta

    r2 = live_client.post("/api/v1/recompute")
    assert r2.status_code == 202
    job_id = r2.json()["job_id"]
    job = {}
    for _ in range(90):
        time.sleep(0.5)
        job = live_client.get(f"/api/v1/recompute/{job_id}").json()
        if job.get("status") in ("completed", "failed"):
            break
    assert job.get("status") == "completed", job
    assert int(job.get("clusters_created") or 0) >= 1
    print(f"[live] recompute job={job_id} clusters={job.get('clusters_created')}")


@pytest.mark.asyncio
async def test_live_llm_summarize_if_model_present(
    require_ollama, live_settings, ollama_base
):
    """Optional: real Ollama chat summarization if Gemma model is installed."""
    from app.core.ollama_bootstrap import ensure_ollama_models
    from app.pipeline.summarization import Summarizer

    model = live_settings.llm.ollama_model
    auto = os.environ.get("OLLAMA_AUTO_PULL", "false").lower() in ("1", "true", "yes")
    report = await ensure_ollama_models(
        ollama_base,
        [model],
        auto_pull=auto,
        pull_timeout_sec=120,
    )
    st = (report.get("models") or {}).get(model)
    if st not in ("present", "pulled"):
        pytest.skip(f"LLM model not installed: {model} (status={st})")

    live_settings.llm.mode = "offline"
    live_settings.llm.provider = "ollama"
    summ = Summarizer.from_settings(live_settings)
    assert summ.backend == "ollama"
    assert summ.model == model

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
    assert result.automation_potential in ("low", "medium", "high")
    print(f"[live] llm summary name={result.name!r} summary={result.summary[:80]!r}")
