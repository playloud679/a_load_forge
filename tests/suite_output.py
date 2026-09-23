"""Keep complete suite output on disk and return a bounded terminal report."""

from collections import deque
import os
from pathlib import Path
import subprocess
import tempfile
import time


def run_logged(command: list[str], log_dir: Path | None = None) -> int:
    log_dir = log_dir or Path(__file__).resolve().parents[1] / ".local/test-logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    with tempfile.NamedTemporaryFile(
        mode="w", prefix="suite-", suffix=".log", dir=log_dir, delete=False
    ) as log:
        path = Path(log.name)
        print(f"Running tests; full output: {path}", flush=True)
        result = subprocess.run(
            command, stdout=log, stderr=subprocess.STDOUT,
            env={**os.environ, "LOAD_FORGE_TEST_LOG_CHILD": "1"},
        )
    tail: deque[str] = deque(maxlen=40)
    failures = []
    failure_context = []
    in_failure = False
    summary = None
    with path.open(errors="replace") as log:
        for line in log:
            tail.append(line.rstrip())
            if line.startswith("  FAIL "):
                failures.append(line.strip())
                in_failure = True
            elif line.startswith(("  OK ", "  PASS:")):
                in_failure = False
            if in_failure and len(failure_context) < 30:
                failure_context.append(line.rstrip())
            if line.startswith("  PASS:"):
                summary = line.strip()
            if "--time" in command and line.startswith("  OK "):
                print(line.rstrip())
    if summary:
        print(summary)
    if result.returncode:
        for failure in failures[:10]:
            print(failure)
        if len(failures) > 10:
            print(f"... and {len(failures) - 10} more failures; see the log.")
        print("Failure excerpt (complete output in the log):")
        print("\n".join(failure_context or tail))
    print(f"Elapsed: {time.perf_counter() - started:.2f}s; exit: {result.returncode}")
    return result.returncode
