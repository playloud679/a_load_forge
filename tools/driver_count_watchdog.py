#!/usr/bin/env python3
"""Driver Count Watchdog — triggers ALARM if the catalog count is stale.

Keeps a tiny state file and compares the current manufacturer-catalog row
count against the last recorded value.  This is deliberately the same
population counted by ``run_catalog_completion_cycle.py``; importing
``src.presets`` would apply cross-catalog deduplication and produce a
different number from the crawler report.  Returns exit code:
  0  — count changed (healthy growth)
  1  — count unchanged (STALE ALARM)
  2  — first run (baseline recorded)

Prints a single-line JSON status to stdout for the orchestrating agent.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE_FILE = ROOT / "data" / ".driver_watchdog_state.json"
CATALOG_FILE = ROOT / "data" / "catalog_proprietario.json"
WATCHDOG_SOURCE = "application-manufacturer-tier"

STALE_THRESHOLD = 2  # consecutive stale cycles before ALARM


def _current_count() -> int:
    sys.path.insert(0, str(ROOT / "src"))
    import presets
    presets._load_manufacturer_presets.cache_clear()
    loaded, _info = presets._load_manufacturer_presets()
    return len(loaded)


def main() -> int:
    count = _current_count()
    now = time.time()

    # Load previous state
    if STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text("utf-8"))
    else:
        state = {"schema": 3, "source": WATCHDOG_SOURCE, "last_count": 0,
                 "last_change_ts": now, "stale_cycles": 0}

    # Do not compare a baseline produced by the old raw-row metric.
    if state.get("schema") != 3 or state.get("source") != WATCHDOG_SOURCE:
        state = {"schema": 3, "source": WATCHDOG_SOURCE, "last_count": count,
                 "last_change_ts": now, "stale_cycles": 0}
        STATE_FILE.write_text(json.dumps(state), encoding="utf-8")
        print(json.dumps({"status": "BASELINE_RESET", "count": count, "stale_cycles": 0}))
        return 2

    prev = state["last_count"]

    if prev == 0:
        # First run — record baseline
        state = {"schema": 3, "source": WATCHDOG_SOURCE, "last_count": count,
                 "last_change_ts": now, "stale_cycles": 0}
        STATE_FILE.write_text(json.dumps(state), "utf-8")
        print(json.dumps({"status": "BASELINE", "count": count, "stale_cycles": 0}))
        return 2

    if count > prev:
        # Growth detected — reset
        delta = count - prev
        state = {"schema": 3, "source": WATCHDOG_SOURCE, "last_count": count,
                 "last_change_ts": now, "stale_cycles": 0}
        STATE_FILE.write_text(json.dumps(state), "utf-8")
        print(json.dumps({"status": "GROWTH", "count": count, "delta": delta, "stale_cycles": 0}))
        return 0

    # Stale — count unchanged
    state["stale_cycles"] = state.get("stale_cycles", 0) + 1
    stale_min = round((now - state["last_change_ts"]) / 60, 1)
    STATE_FILE.write_text(json.dumps(state), "utf-8")

    if state["stale_cycles"] >= STALE_THRESHOLD:
        print(json.dumps({
            "status": "ALARM",
            "count": count,
            "stale_cycles": state["stale_cycles"],
            "stale_minutes": stale_min,
            "message": f"⚠️ STALE ALARM: driver count stuck at {count} for {state['stale_cycles']} cycles ({stale_min} min). Agent MUST react!"
        }))
        return 1

    print(json.dumps({
        "status": "WARNING",
        "count": count,
        "stale_cycles": state["stale_cycles"],
        "stale_minutes": stale_min,
        "message": f"⚡ Count unchanged at {count} for {state['stale_cycles']} cycle(s). Threshold: {STALE_THRESHOLD}."
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
