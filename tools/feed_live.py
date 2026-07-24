"""Feed live requests to the backend ingest webhook (demo simulator).

Sends batches to POST /api/v1/logs with the X-Ingest-Token header, so the
dashboard visibly reacts to a real incoming stream. Run against a running backend:

    python tools/feed_live.py --url http://localhost:8080 --token dev-ingest-token \
        --count 40 --interval 0.5
"""

from __future__ import annotations

import argparse
import time

import httpx

SAMPLES: list[dict] = [
    {
        "user_query": "Выгрузи отчёт по продажам за неделю из CRM в Excel",
        "status": "success",
        "simulated_context_tokens": 12000,
        "estimated_manual_time_minutes": 30,
        "tools_used": ["CRM", "Excel"],
        "category": "data_analysis",
    },
    {
        "user_query": "объясни ошибку в питон трейсбеке KeyError",
        "status": "success",
        "simulated_context_tokens": 3000,
        "estimated_manual_time_minutes": 15,
        "tools_used": [],
        "category": "code_help",
    },
    {
        "user_query": "сделай краткую сводку непрочитанных писем за сегодня",
        "status": "success",
        "simulated_context_tokens": 8000,
        "estimated_manual_time_minutes": 20,
        "tools_used": ["Mail"],
        "category": "information_search",
    },
    {
        "user_query": "создай задачу в Jira по итогам встречи и назначь на меня",
        "status": "error_tool",
        "simulated_context_tokens": 5000,
        "estimated_manual_time_minutes": 10,
        "tools_used": ["Jira"],
        "category": "task_management",
    },
    {
        "user_query": "напиши деловое письмо клиенту с извинениями за задержку",
        "status": "success",
        "simulated_context_tokens": 60000,
        "estimated_manual_time_minutes": 25,
        "tools_used": ["Mail"],
        "category": "text_generation",
    },
    {
        "user_query": "собери информацию по компании ООО Ромашка в открытых источниках",
        "status": "hallucination_loop",
        "simulated_context_tokens": 90000,
        "estimated_manual_time_minutes": 45,
        "tools_used": ["Web"],
        "category": "information_search",
    },
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8080")
    ap.add_argument("--token", default="dev-ingest-token")
    ap.add_argument("--count", type=int, default=30, help="total records to send")
    ap.add_argument("--batch", type=int, default=1, help="records per request")
    ap.add_argument(
        "--interval", type=float, default=1.0, help="seconds between requests"
    )
    args = ap.parse_args()

    headers = {"X-Ingest-Token": args.token}
    sent = 0
    i = 0
    while sent < args.count:
        batch = [dict(SAMPLES[(i + j) % len(SAMPLES)]) for j in range(args.batch)]
        try:
            resp = httpx.post(
                f"{args.url.rstrip('/')}/api/v1/logs",
                json={"logs": batch},
                headers=headers,
                timeout=30,
            )
            print(
                f"[{sent + len(batch)}/{args.count}] {resp.status_code} {resp.json()}"
            )
        except httpx.HTTPError as exc:
            print(f"request failed: {exc}")
        sent += len(batch)
        i += len(batch)
        if sent < args.count:
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
