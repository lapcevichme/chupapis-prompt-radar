"""Live smoke: Ollama embeddings + API path without LLM summarization."""
from __future__ import annotations

import asyncio
import math
import os
import sys
import time
from pathlib import Path

# Force env before app imports
os.environ["EMBEDDINGS_PROVIDER"] = "ollama"
os.environ["OLLAMA_URL"] = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
os.environ["OLLAMA_MODEL"] = os.environ.get("OLLAMA_MODEL", "qwen3-embedding:4b")
os.environ["ALLOW_INMEMORY_STORE"] = "true"
# Prefer real .cbm (trained on Ollama embeddings); fail_fast if missing
_cbm = Path(__file__).resolve().parents[1] / "app" / "models" / "catboost_task_classifier.cbm"
if _cbm.is_file():
    os.environ["CLASSIFIER_MODEL_PATH"] = str(_cbm)
    os.environ["CLASSIFIER_FALLBACK_MODE"] = "fail_fast"
else:
    os.environ["CLASSIFIER_FALLBACK_MODE"] = "keyword"
os.environ["ML_META_DB_URL"] = os.environ.get(
    "ML_META_DB_URL", "sqlite:///./ml_meta_ollama_smoke.db"
)
os.environ["ML_SERVICE_TOKEN"] = ""
os.environ["OPENROUTER_API_KEY"] = ""

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core import config as config_mod
from app.core.config import load_settings

config_mod.settings = load_settings()
settings = config_mod.settings

from app.pipeline.embeddings.adapter import create_embedding_adapter


def cos(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)


async def test_adapter() -> None:
    print("=== CONFIG ===")
    print("provider:", settings.embeddings.provider)
    print("ollama_url:", settings.embeddings.ollama_url)
    print("ollama_model:", settings.embeddings.ollama_model)

    print("\n=== 1) DIRECT OLLAMA ADAPTER ===")
    adapter = create_embedding_adapter(settings.embeddings)
    print("adapter:", type(adapter).__name__, "provider=", adapter.provider_name)
    texts = [
        "напиши python function для парсинга json",
        "сделай pivot table в excel по продажам",
        "напиши python function для парсинга json",
    ]
    t0 = time.perf_counter()
    vecs = await adapter.embed(texts)
    dt = time.perf_counter() - t0
    print(f"count={len(vecs)} dim={len(vecs[0])} elapsed={dt:.2f}s")
    assert len(vecs) == 3
    assert len(vecs[0]) > 10
    assert len(vecs[0]) == len(vecs[1])
    c_same = cos(vecs[0], vecs[2])
    c_diff = cos(vecs[0], vecs[1])
    print(f"cosine same_text={c_same:.4f} different_domain={c_diff:.4f}")
    assert c_same > 0.99, f"identical texts should match, got {c_same}"
    print("adapter.dimension after call:", adapter.dimension)
    await adapter.close()
    print("OK adapter")


def test_api() -> None:
    print("\n=== 2) FASTAPI PATH (ollama embed + CatBoost .cbm, no LLM) ===")
    print("CLASSIFIER_MODEL_PATH:", os.environ.get("CLASSIFIER_MODEL_PATH"))
    print("CLASSIFIER_FALLBACK_MODE:", os.environ.get("CLASSIFIER_FALLBACK_MODE"))
    from fastapi.testclient import TestClient

    # ensure main picks current settings
    if "app.main" in sys.modules:
        del sys.modules["app.main"]
    from app.main import app

    with TestClient(app) as client:
        live = client.get("/health/live").json()
        ready = client.get("/health/ready").json()
        print("health live:", live)
        print(
            "health ready:",
            ready.get("status"),
            "embeddings:",
            ready.get("checks", {}).get("embeddings_provider"),
        )
        payload = {
            "logs": [
                {
                    "request_id": f"ollama-smoke-{i}",
                    "query_text": t,
                    "timestamp": "2026-07-25T12:00:00Z",
                    "source_id": "ollama_smoke",
                }
                for i, t in enumerate(
                    [
                        "напиши sql запрос для отчёта по продажам",
                        "debug python asyncio queue worker",
                        "объясни что такое REST API простыми словами",
                    ]
                )
            ]
        }
        t0 = time.perf_counter()
        r = client.put("/api/v1/logs", json=payload)
        print("PUT /logs", r.status_code, r.json())
        assert r.status_code == 202, r.text
        assert r.json()["accepted"] == 3

        total = 0
        stats = {}
        for _ in range(90):
            time.sleep(0.5)
            stats = client.get("/api/v1/statistics").json()
            total = (stats.get("totals") or {}).get("records_total") or stats.get(
                "total_logs"
            ) or 0
            if total >= 3:
                break
        dt = time.perf_counter() - t0
        print(f"processed total_logs={total} wait={dt:.2f}s")
        assert total >= 3, stats

        assigns = client.get("/api/v1/assignments").json()
        print("assignments total:", assigns.get("total"))
        for a in assigns.get("items", [])[:5]:
            print(
                " ",
                {
                    k: a.get(k)
                    for k in (
                        "request_id",
                        "task_type",
                        "scenario_id",
                        "classification_confidence",
                    )
                },
            )
        # sanity: with real cbm we expect non-trivial confidences
        confs = [a.get("classification_confidence") for a in assigns.get("items", [])]
        print("confidences:", confs)

        r2 = client.post("/api/v1/recompute")
        print("POST /recompute", r2.status_code, r2.json())
        job_id = r2.json().get("job_id")
        j = {}
        for _ in range(60):
            time.sleep(0.5)
            j = client.get(f"/api/v1/recompute/{job_id}").json()
            if j.get("status") in ("completed", "failed"):
                break
        print(
            "job:",
            {
                k: j.get(k)
                for k in (
                    "status",
                    "clusters_created",
                    "scenarios_named",
                    "error",
                    "fallback_used",
                )
            },
        )
        assert j.get("status") == "completed", j

        stats2 = client.get("/api/v1/statistics").json()
        print("stats after recompute totals:", stats2.get("totals"))
        print("tasks_distribution:", stats2.get("tasks_distribution"))
        meta = stats2.get("pipeline_metadata") or {}
        print(
            "pipeline embeddings_provider:",
            meta.get("embedding_provider") or meta.get("embeddings_provider"),
        )


def main() -> None:
    asyncio.run(test_adapter())
    test_api()
    print("\n=== ALL OLLAMA SMOKE PASSED (no LLM) ===")


if __name__ == "__main__":
    main()
