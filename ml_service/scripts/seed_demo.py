#!/usr/bin/env python3
"""Convert demo dataset → log batches and stream to ML PUT /api/v1/logs.

Mapping follows docs/contracts/backend-ml.md:

  user_query  → query_text
  (index)     → request_id = req_{index}
  (synthetic) → timestamp
  source_id   → source_id (CLI / default demo)
  status      → response_status + error_code
  category    → metadata.gold_category
  style, agent_steps, tools_used, simulated_context_tokens,
  estimated_manual_time_minutes → metadata.*

If the dataset file is missing, a small built-in sample is used so
`make demo` / offline smoke still work without notebooks/.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, List, Optional

# Built-in fallback when notebooks/prompt_radar_dataset.json is absent
BUILTIN_DEMO: list[dict[str, Any]] = [
    {
        "user_query": "Выгрузи отчёт по продажам из CRM за прошлый квартал",
        "status": "success",
        "category": "data_analysis",
        "style": "formal",
        "agent_steps": 4,
        "tools_used": ["crm_export"],
        "simulated_context_tokens": 1200,
        "estimated_manual_time_minutes": 45,
    },
    {
        "user_query": "Напиши python function для парсинга JSON из API",
        "status": "success",
        "category": "code_help",
        "style": "concise",
        "agent_steps": 2,
        "tools_used": [],
        "simulated_context_tokens": 800,
        "estimated_manual_time_minutes": 25,
    },
    {
        "user_query": "Составь письмо клиенту о переносе сроков поставки",
        "status": "success",
        "category": "text_generation",
        "style": "formal",
        "agent_steps": 1,
        "tools_used": [],
        "simulated_context_tokens": 600,
        "estimated_manual_time_minutes": 15,
    },
    {
        "user_query": "Как настроить SSO для корпоративного портала?",
        "status": "success",
        "category": "information_search",
        "style": "neutral",
        "agent_steps": 3,
        "tools_used": ["web_search"],
        "simulated_context_tokens": 1500,
        "estimated_manual_time_minutes": 40,
    },
    {
        "user_query": "Разбей задачу внедрения BI на подзадачи и дедлайны",
        "status": "success",
        "category": "task_management",
        "style": "structured",
        "agent_steps": 2,
        "tools_used": [],
        "simulated_context_tokens": 900,
        "estimated_manual_time_minutes": 30,
    },
    {
        "user_query": "Объясни разницу между UMAP и t-SNE простыми словами",
        "status": "success",
        "category": "education",
        "style": "plain",
        "agent_steps": 1,
        "tools_used": [],
        "simulated_context_tokens": 700,
        "estimated_manual_time_minutes": 20,
    },
    {
        "user_query": "Собери SQL для сверки платежей и накладных",
        "status": "error_tool",
        "category": "data_analysis",
        "style": "formal",
        "agent_steps": 5,
        "tools_used": ["sql_runner"],
        "simulated_context_tokens": 1100,
        "estimated_manual_time_minutes": 50,
    },
    {
        "user_query": "Сгенерируй FAQ по внутреннему HR-боту",
        "status": "hallucination_loop",
        "category": "text_generation",
        "style": "friendly",
        "agent_steps": 6,
        "tools_used": [],
        "simulated_context_tokens": 2000,
        "estimated_manual_time_minutes": 35,
    },
    {
        "user_query": "Исправь баг в функции calculate_roi",
        "status": "success",
        "category": "code_help",
        "style": "concise",
        "agent_steps": 3,
        "tools_used": ["code_exec"],
        "simulated_context_tokens": 1000,
        "estimated_manual_time_minutes": 40,
    },
    {
        "user_query": "Найди регламент по обработке персональных данных",
        "status": "success",
        "category": "information_search",
        "style": "formal",
        "agent_steps": 2,
        "tools_used": ["kb_search"],
        "simulated_context_tokens": 950,
        "estimated_manual_time_minutes": 15,
    },
    {
        "user_query": "Построй сводную таблицу по отделам в Excel",
        "status": "success",
        "category": "data_analysis",
        "style": "formal",
        "agent_steps": 3,
        "tools_used": ["spreadsheet"],
        "simulated_context_tokens": 1300,
        "estimated_manual_time_minutes": 55,
    },
    {
        "user_query": "Напиши unit-тесты для API /statistics",
        "status": "success",
        "category": "code_help",
        "style": "concise",
        "agent_steps": 2,
        "tools_used": [],
        "simulated_context_tokens": 850,
        "estimated_manual_time_minutes": 30,
    },
]


def _map_status(status: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Dataset status → (response_status, error_code)."""
    if not status:
        return None, None
    s = str(status).strip().lower()
    if s in ("success", "ok"):
        return "success", None
    if s == "error_tool":
        return "error", "tool_error"
    if s == "hallucination_loop":
        return "error", "hallucination_loop"
    if s in ("error", "failed"):
        return "error", None
    return s, None


def record_to_log(item: dict[str, Any], index: int, source_id: str, base_ts: datetime) -> dict[str, Any]:
    """Map one dataset row to log.schema.json fields."""
    query = (item.get("user_query") or item.get("query_text") or item.get("query") or "").strip()
    if not query:
        raise ValueError(f"row {index}: empty query")

    request_id = item.get("request_id") or f"req_{index}"
    ts = item.get("timestamp")
    if not ts:
        # Spread over ~30 days for demo dynamics
        ts = (base_ts + timedelta(hours=index * 5)).isoformat().replace("+00:00", "Z")

    response_status, error_code = _map_status(item.get("status") or item.get("response_status"))
    if "error_code" in item and item["error_code"] is not None:
        error_code = item["error_code"]
    if item.get("response_status"):
        response_status = item["response_status"]

    metadata: dict[str, Any] = {}
    if isinstance(item.get("metadata"), dict):
        metadata.update(item["metadata"])

    gold = item.get("category") or item.get("gold_category")
    if gold:
        metadata["gold_category"] = gold

    for key in (
        "style",
        "agent_steps",
        "tools_used",
        "simulated_context_tokens",
        "estimated_manual_time_minutes",
    ):
        if key in item and item[key] is not None:
            metadata[key] = item[key]

    log: dict[str, Any] = {
        "request_id": str(request_id),
        "query_text": query,
        "timestamp": ts,
        "source_id": item.get("source_id") or source_id,
        "response_status": response_status,
        "error_code": error_code,
        "metadata": metadata or None,
    }
    return log


def load_dataset(path: Optional[Path]) -> list[dict[str, Any]]:
    if path is None or not path.is_file():
        print(f"[seed] dataset not found ({path}); using built-in sample ({len(BUILTIN_DEMO)} rows)")
        return list(BUILTIN_DEMO)

    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        # common wrappers: { "items": [...] } / { "logs": [...] } / { "data": [...] }
        for key in ("items", "logs", "data", "records", "queries"):
            if isinstance(raw.get(key), list):
                raw = raw[key]
                break
        else:
            raise ValueError(f"Unsupported dataset object keys: {list(raw.keys())[:20]}")
    if not isinstance(raw, list):
        raise ValueError("Dataset must be a JSON array of records")
    print(f"[seed] loaded {len(raw)} rows from {path}")
    return raw


def batches(items: List[dict[str, Any]], size: int) -> Iterator[List[dict[str, Any]]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def http_json(
    method: str,
    url: str,
    body: Optional[dict[str, Any]] = None,
    token: str = "",
    timeout: float = 60.0,
) -> tuple[int, Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["X-Service-Token"] = token
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = resp.read().decode("utf-8")
            return resp.status, json.loads(payload) if payload else None
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(err_body)
        except json.JSONDecodeError:
            parsed = {"raw": err_body}
        return e.code, parsed


def wait_ready(base_url: str, timeout_sec: float = 120.0) -> None:
    deadline = time.time() + timeout_sec
    url = base_url.rstrip("/") + "/health/ready"
    while time.time() < deadline:
        try:
            code, body = http_json("GET", url)
            if code == 200 and isinstance(body, dict) and body.get("status") in ("ready", "degraded", "live"):
                print(f"[seed] ready: {body.get('status')}")
                return
        except Exception as exc:  # noqa: BLE001
            print(f"[seed] waiting for {url}: {exc}")
        time.sleep(2)
    raise SystemExit(f"ML not ready at {url} within {timeout_sec}s")


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Seed Prompt Radar ML with demo log batches")
    parser.add_argument("--url", default=os.getenv("ML_URL", "http://localhost:8000"))
    parser.add_argument(
        "--dataset",
        default=os.getenv("DEMO_DATASET", ""),
        help="Path to prompt_radar_dataset.json (optional)",
    )
    parser.add_argument("--source-id", default=os.getenv("DEMO_SOURCE_ID", "demo"))
    parser.add_argument("--batch-size", type=int, default=int(os.getenv("DEMO_BATCH_SIZE", "50")))
    parser.add_argument("--token", default=os.getenv("ML_SERVICE_TOKEN", ""))
    parser.add_argument("--limit", type=int, default=0, help="Max records (0 = all)")
    parser.add_argument("--recompute", action="store_true", help="Trigger POST /api/v1/recompute after seed")
    parser.add_argument("--skip-ready", action="store_true")
    parser.add_argument("--process-wait", type=float, default=1.5, help="Seconds to wait after last batch")
    args = parser.parse_args(list(argv) if argv is not None else None)

    dataset_path: Optional[Path] = None
    if args.dataset:
        dataset_path = Path(args.dataset)
    else:
        # Prefer notebooks path from monorepo root, then local fixtures
        candidates = [
            Path(__file__).resolve().parents[2] / "notebooks" / "prompt_radar_dataset.json",
            Path(__file__).resolve().parents[1] / "fixtures" / "prompt_radar_dataset.json",
            Path("notebooks/prompt_radar_dataset.json"),
            Path("prompt_radar_dataset.json"),
        ]
        for c in candidates:
            if c.is_file():
                dataset_path = c
                break

    rows = load_dataset(dataset_path)
    if args.limit and args.limit > 0:
        rows = rows[: args.limit]

    base_ts = datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
    logs: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        try:
            logs.append(record_to_log(row, i, args.source_id, base_ts))
        except ValueError as exc:
            print(f"[seed] skip: {exc}")

    if not logs:
        print("[seed] nothing to send", file=sys.stderr)
        return 1

    base = args.url.rstrip("/")
    if not args.skip_ready:
        wait_ready(base)

    accepted = duplicates = rejected = 0
    for bi, batch in enumerate(batches(logs, max(1, args.batch_size))):
        code, body = http_json(
            "PUT",
            f"{base}/api/v1/logs",
            {"logs": batch},
            token=args.token,
        )
        if code not in (200, 202):
            print(f"[seed] batch {bi} failed HTTP {code}: {body}", file=sys.stderr)
            return 1
        accepted += int(body.get("accepted", 0)) if isinstance(body, dict) else 0
        duplicates += int(body.get("duplicates", 0)) if isinstance(body, dict) else 0
        rejected += int(body.get("rejected", 0)) if isinstance(body, dict) else 0
        print(f"[seed] batch {bi}: accepted={body.get('accepted')} duplicates={body.get('duplicates')}")

    print(f"[seed] done: accepted={accepted} duplicates={duplicates} rejected={rejected} total={len(logs)}")
    time.sleep(max(0.0, args.process_wait))

    if args.recompute:
        code, body = http_json("POST", f"{base}/api/v1/recompute", {}, token=args.token)
        print(f"[seed] recompute → HTTP {code}: {body}")
        if isinstance(body, dict) and body.get("job_id"):
            job_id = body["job_id"]
            for _ in range(30):
                time.sleep(1.0)
                jcode, jbody = http_json("GET", f"{base}/api/v1/recompute/{job_id}", token=args.token)
                status = jbody.get("status") if isinstance(jbody, dict) else None
                print(f"[seed] job {job_id}: {status}")
                if status in ("completed", "failed", "pending") and status != "running":
                    # pending may flip quickly; break on terminal-ish states
                    if status in ("completed", "failed"):
                        break
            # short grace for in-process jobs that stay "pending" briefly
            time.sleep(1.0)

        scode, stats = http_json("GET", f"{base}/api/v1/statistics", token=args.token)
        print(f"[seed] statistics HTTP {scode}: total_logs={stats.get('total_logs') if isinstance(stats, dict) else stats}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
