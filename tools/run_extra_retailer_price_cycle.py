#!/usr/bin/env python3
"""Refresh every extra retailer concurrently, then rematch the full library."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

import harvest_extra_retailers as harvester

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCES = tuple(sorted(harvester.HARVESTERS))


def log(message: str) -> None:
    print(message, flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sources",
        nargs="+",
        choices=DEFAULT_SOURCES,
        default=list(DEFAULT_SOURCES),
    )
    parser.add_argument("--sleep", type=float, default=0.4)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument(
        "--source-runtime",
        type=float,
        default=900.0,
        help="maximum wall time for each parallel source worker",
    )
    parser.add_argument(
        "--forever",
        action="store_true",
        help="repeat cycles indefinitely; failures are logged and retried",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=900.0,
        help="seconds between persistent cycles (default: 15 minutes)",
    )
    args = parser.parse_args()

    while True:
        cycle_code = _run_cycle(args, harvest_script=ROOT / "tools" / "harvest_extra_retailers.py")
        if not args.forever:
            return cycle_code
        log(f"persistent worker: cycle exit={cycle_code}; next cycle in {args.interval:g}s")
        time.sleep(max(1.0, args.interval))


def _run_cycle(args: argparse.Namespace, *, harvest_script: Path) -> int:

    workers: dict[str, subprocess.Popen] = {}
    started_at = time.monotonic()
    for source in args.sources:
        command = [
            sys.executable,
            str(harvest_script),
            "--source",
            source,
            "--sleep",
            str(args.sleep),
            "--timeout",
            str(args.timeout),
        ]
        workers[source] = subprocess.Popen(command)
        log(f"source {source}: worker pid={workers[source].pid}")

    failures = []
    for source, worker in workers.items():
        remaining = max(0.0, float(args.source_runtime) - (time.monotonic() - started_at))
        try:
            returncode = worker.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            log(f"source {source}: exceeded {args.source_runtime:g}s runtime; terminating")
            worker.terminate()
            try:
                returncode = worker.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                worker.kill()
                returncode = worker.wait()
        if returncode:
            failures.append(source)
            log(f"source {source}: failed with exit code {returncode}")
        else:
            log(f"source {source}: refresh complete")

    merge = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "merge_extra_retailers.py")],
        check=False,
    )
    if merge.returncode:
        log(f"extra-retailer merge failed with exit code {merge.returncode}")
        return merge.returncode
    if failures:
        log(f"cycle merged retained checkpoints; failed sources: {', '.join(failures)}")
        return 1
    log("extra-retailer cycle completed successfully")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
