#!/usr/bin/env python3
"""Run restartable published-spec refreshes as small atomic URL batches."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = ROOT / "data" / "manufacturer_drivers.json"
DEFAULT_CHECKPOINT = ROOT / "data" / "manufacturer_optional_refresh_checkpoint.json"
DEFAULT_REPORT = ROOT / "data" / "manufacturer_optional_refresh_report.json"


def read_report(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def should_continue(report: dict, max_failure_rate: float) -> bool:
    processed = int(report.get("processed") or 0)
    if processed <= 0:
        return False
    failures = len(report.get("failures") or [])
    return failures / processed <= max(0.0, min(1.0, max_failure_rate))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", required=True)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--max-batches", type=int, default=0)
    parser.add_argument("--max-failure-rate", type=float, default=0.5)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--per-host-delay", type=float, default=0.5)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    batch = 0
    totals = {"processed": 0, "records_updated": 0, "failures": 0}
    while args.max_batches <= 0 or batch < args.max_batches:
        batch += 1
        command = [
            sys.executable,
            str(ROOT / "tools" / "refresh_manufacturer_optionals.py"),
            "--database", str(args.database),
            "--checkpoint", str(args.checkpoint),
            "--report", str(args.report),
            "--domain", args.domain,
            "--apply",
            "--max-records", str(max(1, args.batch_size)),
            "--workers", str(max(1, args.workers)),
            "--timeout", str(args.timeout),
            "--per-host-delay", str(args.per_host_delay),
        ]
        completed = subprocess.run(command, cwd=ROOT, check=False)
        report = read_report(args.report)
        processed = int(report.get("processed") or 0)
        updated = int(report.get("records_updated") or 0)
        failures = len(report.get("failures") or [])
        totals["processed"] += processed
        totals["records_updated"] += updated
        totals["failures"] += failures
        print(json.dumps({
            "batch": batch,
            "returncode": completed.returncode,
            "processed": processed,
            "records_updated": updated,
            "failures": failures,
            "fields_filled": report.get("fields_filled") or {},
        }, sort_keys=True), flush=True)
        if completed.returncode != 0:
            print(json.dumps({"stop_reason": "child_failed", "totals": totals}, sort_keys=True))
            return completed.returncode
        if processed == 0:
            print(json.dumps({"stop_reason": "domain_exhausted", "totals": totals}, sort_keys=True))
            return 0
        if not should_continue(report, args.max_failure_rate):
            print(json.dumps({"stop_reason": "failure_rate", "totals": totals}, sort_keys=True))
            return 2
    print(json.dumps({"stop_reason": "batch_limit", "totals": totals}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
