"""End-to-end demo driver for Prompt Radar (`make demo`).

Runs the full happy path against a running stack and prints a readable summary:

    ready -> login -> ingest demo dataset -> recompute (best-effort)
          -> dashboard -> ROI -> export xlsx

Recompute may be unavailable while the ML store is still warming up; the driver
reports it and keeps going, because ingestion / dashboard / ROI / export do not
depend on it. Run against a running backend:

    python tools/demo.py --url http://localhost:8080
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import httpx

EMAIL = "test@gmail.com"
PASSWORD = "test123"


def _wait_ready(client: httpx.Client, attempts: int = 60) -> bool:
    for _ in range(attempts):
        try:
            resp = client.get("/api/ready")
            if resp.status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(1)
    return False


def _login(client: httpx.Client) -> None:
    resp = client.post(
        "/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}
    )
    resp.raise_for_status()
    print(f"  logged in as {EMAIL}")


def _ingest_demo(client: httpx.Client) -> None:
    resp = client.post("/api/v1/ingest", json={"use_demo": True})
    resp.raise_for_status()
    body = resp.json()
    print(
        f"  source_id={body.get('source_id')} "
        f"valid={body.get('records_valid')} rejected={body.get('records_rejected')} "
        f"status={body.get('status')}"
    )


def _recompute(client: httpx.Client) -> None:
    try:
        resp = client.post("/api/v1/recompute")
        if resp.status_code >= 400:
            print(f"  recompute unavailable (HTTP {resp.status_code}) — skipping, "
                  "dashboard/ROI still work on online assignments")
            return
        print(f"  recompute triggered: {resp.json()}")
        for _ in range(30):
            time.sleep(1)
            status = client.get("/api/v1/recompute/status").json()
            if status.get("status") in ("completed", "failed", "idle"):
                print(f"  recompute status: {status.get('status')}")
                return
    except httpx.HTTPError as exc:
        print(f"  recompute error: {exc} — skipping")


def _dashboard(client: httpx.Client) -> None:
    body = client.get("/api/v1/dashboard").json()
    totals = body.get("totals", {})
    print(
        f"  records_processed={totals.get('records_processed')} "
        f"scenarios={totals.get('scenarios_count')} "
        f"outliers%={totals.get('outliers_percentage')}"
    )
    for item in body.get("tasks_distribution", [])[:5]:
        print(f"    - {item.get('label')}: {item.get('count')} ({item.get('percentage')}%)")


def _roi(client: httpx.Client) -> None:
    body = client.get("/api/v1/roi").json()
    s = body.get("summary", {})
    print(
        f"  FTE hours saved={s.get('total_fte_hours_saved')} "
        f"net savings={s.get('net_savings_rub')}₽ "
        f"ROI x{s.get('roi_multiplier')} "
        f"success%={s.get('success_rate_percent')}"
    )


def _export(client: httpx.Client, out_dir: Path) -> None:
    resp = client.get("/api/v1/export", params={"format": "xlsx"})
    resp.raise_for_status()
    out = out_dir / "prompt_radar_roi.xlsx"
    out.write_bytes(resp.content)
    print(f"  exported ROI workbook -> {out} ({len(resp.content)} bytes)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prompt Radar end-to-end demo")
    parser.add_argument("--url", default="http://localhost:8080")
    parser.add_argument("--out", default=".", help="dir to save the export file")
    args = parser.parse_args()

    with httpx.Client(base_url=args.url, timeout=30) as client:
        print("[1/6] waiting for /api/ready ...")
        if not _wait_ready(client):
            print("  backend not ready — is the stack up? (make up)")
            return 1
        print("[2/6] login")
        _login(client)
        print("[3/6] ingest demo dataset")
        _ingest_demo(client)
        print("[4/6] recompute (best-effort)")
        _recompute(client)
        print("[5/6] dashboard")
        _dashboard(client)
        print("[5/6] ROI")
        _roi(client)
        print("[6/6] export")
        _export(client, Path(args.out))

    print("\nDone. Open the dashboard API docs at "
          f"{args.url}/api/docs — login {EMAIL} / {PASSWORD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
