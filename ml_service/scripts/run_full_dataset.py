#!/usr/bin/env python3
"""Run full ml_service pipeline on a dataset JSON and print evaluation report.

Example:
  cd ml_service
  python scripts/run_full_dataset.py --dataset catboost/prompt_radar_dataset.json

Uses in-process FastAPI TestClient (no external uvicorn required).
Embeddings/LLM modes come from env / .env (ML_MODE, EMBEDDINGS_MODE, LLM_MODE).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    load_dotenv()
except ImportError:
    pass

# Store / worker defaults (overridden by --real-qdrant / env)
os.environ.setdefault("ML_META_DB_URL", "sqlite:///./ml_meta_full_run.db")
os.environ.setdefault("ML_SERVICE_TOKEN", "")
# Start parallel; AdaptiveConcurrency scales down on OpenRouter "model busy"
os.environ.setdefault("INGEST_WORKER_CONCURRENCY", "4")
os.environ.setdefault("EMBEDDINGS_BATCH_SIZE", "1")
os.environ.setdefault("EMBEDDINGS_MAX_CONCURRENCY", "4")
os.environ.setdefault("EMBEDDINGS_MAX_RETRIES", "8")
os.environ.setdefault("EMBEDDINGS_DIM", "2560")

from scripts.seed_demo import batches, load_dataset, record_to_log  # noqa: E402


def _purge_app() -> None:
    for k in list(sys.modules):
        if k == "app" or k.startswith("app."):
            del sys.modules[k]


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Full dataset pipeline run + report")
    p.add_argument(
        "--dataset",
        default=str(ROOT / "catboost" / "prompt_radar_dataset.json"),
    )
    p.add_argument("--source-id", default="full_dataset_run")
    p.add_argument("--batch-size", type=int, default=25)
    p.add_argument("--limit", type=int, default=0, help="0 = all")
    p.add_argument(
        "--mode",
        choices=("offline", "online", "hybrid"),
        default=os.getenv("DATASET_RUN_MODE", "offline"),
        help="offline=Ollama emb+llm, online=OpenRouter both, hybrid=Ollama emb + OpenRouter llm",
    )
    p.add_argument("--no-recompute", action="store_true")
    p.add_argument("--no-llm-names", action="store_true", help="Skip LLM naming (technical names only)")
    p.add_argument("--process-timeout", type=float, default=3600.0)
    p.add_argument(
        "--real-qdrant",
        action="store_true",
        default=os.getenv("DATASET_RUN_REAL_QDRANT", "").lower() in ("1", "true", "yes"),
        help="Use real Qdrant (no in-memory mock). Requires Qdrant at QDRANT_URL.",
    )
    p.add_argument(
        "--qdrant-url",
        default=os.getenv("QDRANT_URL", "http://127.0.0.1:6333"),
        help="Qdrant URL when --real-qdrant (default http://127.0.0.1:6333)",
    )
    p.add_argument(
        "--qdrant-collection",
        default=os.getenv("QDRANT_COLLECTION", "prompt_radar_full_run"),
        help="Qdrant collection name for this run",
    )
    args = p.parse_args(argv)

    # Mode wiring
    if args.mode == "offline":
        os.environ["ML_MODE"] = "offline"
        os.environ["EMBEDDINGS_MODE"] = "offline"
        os.environ["EMBEDDINGS_PROVIDER"] = "ollama"
        os.environ["LLM_MODE"] = "offline"
        os.environ.setdefault("OLLAMA_AUTO_PULL", "false")
    elif args.mode == "online":
        os.environ["ML_MODE"] = "online"
        os.environ["EMBEDDINGS_MODE"] = "online"
        os.environ["EMBEDDINGS_PROVIDER"] = "openrouter"
        os.environ["LLM_MODE"] = "online"
        os.environ["LLM_PROVIDER"] = "openrouter"
    else:  # hybrid
        os.environ["EMBEDDINGS_MODE"] = "offline"
        os.environ["EMBEDDINGS_PROVIDER"] = "ollama"
        os.environ["LLM_MODE"] = "online"
        os.environ["LLM_PROVIDER"] = "openrouter"
        os.environ.setdefault("OLLAMA_AUTO_PULL", "false")

    # Vector store: real Qdrant or in-memory mock
    if args.real_qdrant:
        os.environ["ALLOW_INMEMORY_STORE"] = "false"
        os.environ["QDRANT_REQUIRED"] = "true"
        os.environ["QDRANT_URL"] = args.qdrant_url
        os.environ["QDRANT_COLLECTION"] = args.qdrant_collection
        os.environ.setdefault("QDRANT_CONNECT_RETRIES", "20")
        os.environ.setdefault("QDRANT_TIMEOUT_SEC", "5")
        os.environ.setdefault("EMBEDDINGS_DIM", "2560")
        print(
            f"[run] REAL Qdrant url={args.qdrant_url} collection={args.qdrant_collection}"
        )
    else:
        os.environ.setdefault("ALLOW_INMEMORY_STORE", "true")
        os.environ.setdefault("QDRANT_REQUIRED", "false")
        print("[run] Qdrant=mock (pass --real-qdrant for real store)")

    if args.no_llm_names:
        # force technical names by clearing online key temporarily only if offline
        if args.mode == "offline":
            os.environ["LLM_MODE"] = "online"  # openrouter without key → technical
            os.environ["OPENROUTER_API_KEY"] = ""

    dataset_path = Path(args.dataset)
    rows = load_dataset(dataset_path)
    if args.limit and args.limit > 0:
        rows = rows[: args.limit]

    base_ts = datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
    logs: list[dict[str, Any]] = []
    gold: dict[str, str] = {}
    for i, row in enumerate(rows):
        try:
            log = record_to_log(row, i, args.source_id, base_ts)
        except ValueError as exc:
            print(f"[run] skip: {exc}")
            continue
        logs.append(log)
        g = (row.get("category") or row.get("gold_category") or "").strip()
        if g:
            gold[str(log["request_id"])] = g

    print(f"[run] mode={args.mode} records={len(logs)} gold_labels={len(gold)}")
    print(
        f"[run] emb={os.environ.get('EMBEDDINGS_MODE')} "
        f"llm={os.environ.get('LLM_MODE')} "
        f"cbm={os.environ.get('CLASSIFIER_MODEL_PATH', 'default')}"
    )

    # Fresh sqlite file for this run
    db_path = ROOT / "ml_meta_full_run.db"
    if db_path.is_file():
        db_path.unlink()
    os.environ["ML_META_DB_URL"] = f"sqlite:///{db_path.as_posix()}"

    _purge_app()
    from app.core import config as config_mod
    from app.core.config import load_settings

    config_mod.settings = load_settings()
    from app.main import app
    from fastapi.testclient import TestClient

    t_start = time.perf_counter()
    with TestClient(app) as client:
        live = client.get("/health/live").json()
        ready = client.get("/health/ready").json()
        checks = ready.get("checks") or {}
        print(f"[run] health live={live} ready={ready.get('status')} checks={checks}")
        if args.real_qdrant and checks.get("qdrant") != "ok":
            print(
                f"[run] FATAL: expected real Qdrant, got checks.qdrant={checks.get('qdrant')!r}. "
                f"Is Qdrant up at {args.qdrant_url}?"
            )
            return 2
        emb_p = checks.get("embeddings_provider") or ""
        if args.mode == "online" and "mock" in str(emb_p).lower():
            print(f"[run] FATAL: mode=online but embeddings_provider={emb_p!r} (mock)")
            return 2

        accepted = duplicates = rejected = 0
        for bi, batch in enumerate(batches(logs, max(1, args.batch_size))):
            r = client.put("/api/v1/logs", json={"logs": batch})
            if r.status_code not in (200, 202):
                print(f"[run] batch {bi} FAILED {r.status_code} {r.text[:300]}")
                return 1
            body = r.json()
            accepted += int(body.get("accepted") or 0)
            duplicates += int(body.get("duplicates") or 0)
            rejected += int(body.get("rejected") or 0)
            if bi % 5 == 0 or bi == 0:
                print(
                    f"[run] batch {bi}/{((len(logs)-1)//args.batch_size)} "
                    f"acc={body.get('accepted')} dup={body.get('duplicates')} rej={body.get('rejected')}"
                )

        print(
            f"[run] seed done accepted={accepted} duplicates={duplicates} "
            f"rejected={rejected} expected={len(logs)}"
        )

        # Wait until processed
        deadline = time.time() + args.process_timeout
        total = 0
        while time.time() < deadline:
            stats = client.get("/api/v1/statistics").json()
            total = int(
                (stats.get("totals") or {}).get("records_total")
                or stats.get("total_logs")
                or 0
            )
            if total >= len(logs) - rejected:
                break
            print(f"[run] processing... {total}/{len(logs)}", flush=True)
            time.sleep(3.0)
        else:
            print(f"[run] TIMEOUT processed only {total}/{len(logs)}")

        t_ingest = time.perf_counter() - t_start
        print(f"[run] ingest complete total={total} elapsed={t_ingest:.1f}s")

        # Assignments + accuracy
        all_items: list[dict[str, Any]] = []
        offset = 0
        page = 500
        while True:
            page_body = client.get(
                f"/api/v1/assignments?limit={page}&offset={offset}&source_id={args.source_id}"
            ).json()
            items = page_body.get("items") or []
            all_items.extend(items)
            if offset + len(items) >= int(page_body.get("total") or 0) or not items:
                break
            offset += len(items)

        pred_counts = Counter(a.get("task_type") for a in all_items)
        confs = [float(a.get("classification_confidence") or 0) for a in all_items]
        unknown_n = sum(1 for a in all_items if a.get("task_type") == "unknown")

        correct = 0
        labeled = 0
        conf_mat: dict[str, Counter] = defaultdict(Counter)
        for a in all_items:
            rid = str(a.get("request_id"))
            if rid not in gold:
                continue
            labeled += 1
            g = gold[rid]
            pr = a.get("task_type") or "unknown"
            conf_mat[g][pr] += 1
            if pr == g:
                correct += 1

        acc = (correct / labeled) if labeled else None
        print("\n========== CLASSIFICATION REPORT ==========")
        print(f"assignments: {len(all_items)}")
        print(f"pred distribution: {dict(pred_counts)}")
        print(f"unknown: {unknown_n} ({100*unknown_n/max(1,len(all_items)):.1f}%)")
        if confs:
            print(
                f"confidence: min={min(confs):.3f} mean={sum(confs)/len(confs):.3f} max={max(confs):.3f}"
            )
        if acc is not None:
            print(f"accuracy vs gold_category (excl. empty gold): {acc:.3f} ({correct}/{labeled})")
            print("confusion gold→pred (top):")
            for g, ctr in sorted(conf_mat.items()):
                top = ctr.most_common(4)
                print(f"  {g}: {top}")
        else:
            print("accuracy: n/a (no gold labels)")

        # Recompute
        if not args.no_recompute:
            print("\n========== RECOMPUTE ==========")
            t0 = time.perf_counter()
            r2 = client.post("/api/v1/recompute")
            print(f"POST /recompute → {r2.status_code} {r2.json()}")
            job_id = r2.json().get("job_id")
            job = {}
            for i in range(int(args.process_timeout // 2)):
                time.sleep(2.0)
                job = client.get(f"/api/v1/recompute/{job_id}").json()
                st = job.get("status")
                if i % 5 == 0:
                    print(f"[run] job {job_id}: {st} clusters={job.get('clusters_created')} named={job.get('scenarios_named')}")
                if st in ("completed", "failed"):
                    break
            print(f"[run] recompute done in {time.perf_counter()-t0:.1f}s → {job}")

        stats = client.get(f"/api/v1/statistics?source_id={args.source_id}").json()
        scenarios = client.get("/api/v1/scenarios").json()

        print("\n========== STATISTICS ==========")
        print(f"totals: {stats.get('totals')}")
        print(f"tasks_distribution: {stats.get('tasks_distribution')}")
        print(f"failure_analysis: {stats.get('failure_analysis')}")
        print(f"outliers_summary: {stats.get('outliers_summary')}")
        print(f"freshness: {stats.get('freshness')}")
        meta = stats.get("pipeline_metadata") or {}
        print(
            f"pipeline: emb={meta.get('embedding_provider') or meta.get('embeddings_provider')} "
            f"model={meta.get('embedding_model')} llm={meta.get('llm_provider')} "
            f"llm_model={meta.get('llm_model')}"
        )

        print("\n========== TOP SCENARIOS ==========")
        top = stats.get("top_scenarios") or []
        for s in top[:15]:
            print(
                f"  {s.get('scenario_id') or s.get('task_type')}: "
                f"count={s.get('count') or s.get('records_count')} "
                f"name={s.get('name')!r} trend={s.get('trend')}"
            )

        sc_items = scenarios.get("items") or []
        print(f"\nscenarios total listed: {scenarios.get('total') or len(sc_items)}")
        named = [s for s in sc_items if s.get("name") and not str(s.get("name")).startswith("Сценарий")]
        print(f"scenarios with non-technical LLM names: {len(named)}")
        for s in named[:12]:
            print(f"  {s.get('scenario_id')}: {s.get('name')!r}")

        out_path = ROOT / "full_dataset_run_report.json"
        report = {
            "dataset": str(dataset_path),
            "mode": args.mode,
            "real_qdrant": bool(args.real_qdrant),
            "qdrant_url": args.qdrant_url if args.real_qdrant else "mock",
            "qdrant_collection": args.qdrant_collection if args.real_qdrant else None,
            "health_checks": checks,
            "records": len(logs),
            "processed": total,
            "accepted": accepted,
            "duplicates": duplicates,
            "rejected": rejected,
            "pred_distribution": dict(pred_counts),
            "unknown_count": unknown_n,
            "accuracy": acc,
            "correct": correct,
            "labeled": labeled,
            "confidence": {
                "min": min(confs) if confs else None,
                "mean": (sum(confs) / len(confs)) if confs else None,
                "max": max(confs) if confs else None,
            },
            "totals": stats.get("totals"),
            "tasks_distribution": stats.get("tasks_distribution"),
            "top_scenarios": top[:20],
            "pipeline_metadata": meta,
            "recompute": job if not args.no_recompute else None,
            "elapsed_sec": time.perf_counter() - t_start,
        }
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n[run] report written → {out_path}")
        print(f"[run] total elapsed {report['elapsed_sec']:.1f}s")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
