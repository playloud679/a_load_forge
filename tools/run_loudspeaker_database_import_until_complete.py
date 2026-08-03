#!/usr/bin/env python3
"""Run the Loudspeaker Database importer in paced restart windows."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

INTERRUPTED_EXIT = 75


def log(message: str):
    print(message, flush=True)


def dataset_status(path: Path) -> tuple[bool, int]:
    if not path.exists():
        return False, 0
    payload = json.loads(path.read_text(encoding="utf-8"))
    return bool(payload.get("complete")), int(payload.get("usable_presets") or 0)


def run_attempt(args: argparse.Namespace) -> int:
    cmd = [
        sys.executable,
        "tools/import_loudspeaker_database.py",
        "--output",
        str(args.output),
        "--checkpoint",
        str(args.checkpoint),
        "--brand-cache",
        str(args.brand_cache),
        "--sleep",
        str(args.page_sleep),
        "--retry-delays",
        args.retry_delays,
        "--max-runtime",
        str(args.window_runtime),
    ]
    log(f"starting import window: {' '.join(cmd)}")
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    for line in process.stdout:
        print(line, end="", flush=True)
    return int(process.wait())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="data/loudspeaker_database_drivers.json", type=Path)
    parser.add_argument("--checkpoint", default="data/loudspeaker_database_checkpoint.json", type=Path)
    parser.add_argument("--brand-cache", default="data/loudspeaker_database_brands.json", type=Path)
    parser.add_argument("--max-attempts", default=12, type=int)
    parser.add_argument("--window-runtime", default=600.0, type=float)
    parser.add_argument("--page-sleep", default=15.0, type=float)
    parser.add_argument("--retry-delays", default="30,90,180")
    parser.add_argument("--initial-pause", default=900.0, type=float)
    parser.add_argument("--max-pause", default=7200.0, type=float)
    parser.add_argument("--pause-growth", default=1.75, type=float)
    args = parser.parse_args()

    complete, previous_count = dataset_status(args.output)
    if complete:
        log(f"dataset already complete with {previous_count} usable presets")
        return 0

    pause_s = args.initial_pause
    for attempt in range(1, args.max_attempts + 1):
        log(f"attempt {attempt}/{args.max_attempts}; current usable presets: {previous_count}")
        code = run_attempt(args)
        complete, count = dataset_status(args.output)
        log(f"attempt {attempt} exited {code}; usable presets: {count}; complete={complete}")

        if complete:
            return 0
        if code not in (0, INTERRUPTED_EXIT):
            return code

        if count > previous_count:
            previous_count = count
            pause_s = args.initial_pause
        else:
            pause_s = min(args.max_pause, pause_s * args.pause_growth)
        if attempt < args.max_attempts:
            log(f"sleeping {pause_s:.0f}s before next fresh session")
            time.sleep(pause_s)

    return INTERRUPTED_EXIT


if __name__ == "__main__":
    raise SystemExit(main())
