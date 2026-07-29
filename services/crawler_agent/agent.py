"""Execute a policy-bounded crawler-agent plan as a Cloud Run Job."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .model import SOURCE_LABELS, AgentManifest, CrawlPlan, PlannedTarget, build_plan

ROOT = Path(__file__).resolve().parents[2]
CRAWLER = ROOT / "tools" / "crawl_thiele_small.py"


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _load_catalog(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {"presets": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {"presets": []}


def command_for_target(
    item: PlannedTarget,
    manifest: AgentManifest,
    target_dir: Path,
) -> list[str]:
    target = item.target
    command = [
        sys.executable,
        str(CRAWLER),
        "--output",
        str(target_dir / "candidate_catalog.json"),
        "--checkpoint",
        str(target_dir / "checkpoint.json"),
        "--source-name",
        SOURCE_LABELS[target.source_kind],
        "--max-pages",
        str(target.max_pages),
        "--max-depth",
        str(target.max_depth),
        "--sleep",
        str(target.sleep_seconds),
        "--min-confidence",
        str(target.min_confidence),
        "--user-agent",
        manifest.user_agent,
        "--fresh",
    ]
    if target.brand:
        command.extend(["--brand", target.brand])
    for domain in target.allowed_domains:
        command.extend(["--allow-domain", domain])
    for url in target.seeds:
        command.extend(["--seed", url])
    for url in target.sitemaps:
        command.extend(["--sitemap", url])
    for pattern in target.include:
        command.extend(["--include", pattern])
    for pattern in target.exclude:
        command.extend(["--exclude", pattern])
    return command


def _file_digest(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_plan(
    plan: CrawlPlan,
    manifest: AgentManifest,
    run_root: Path,
    *,
    run_id: str | None = None,
    target_timeout_seconds: int = 3_300,
) -> Path:
    """Run selected targets into staging; never update the production catalog."""
    run_id = run_id or f"crawl-{_utc_stamp()}"
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{2,127}", run_id):
        raise ValueError(f"unsafe run_id: {run_id!r}")
    run_dir = run_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "plan.json").write_text(
        json.dumps(plan.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    results: list[dict[str, Any]] = []
    for item in plan.selected:
        target_dir = run_dir / item.target.target_id
        target_dir.mkdir()
        command = command_for_target(item, manifest, target_dir)
        started = datetime.now(UTC)
        try:
            completed = subprocess.run(
                command,
                cwd=ROOT,
                text=True,
                capture_output=True,
                timeout=target_timeout_seconds,
                check=False,
            )
            status = "succeeded" if completed.returncode == 0 else "failed"
            returncode = completed.returncode
            stdout = completed.stdout
            stderr = completed.stderr
        except subprocess.TimeoutExpired as exc:
            status = "timed_out"
            returncode = 124
            stdout = str(exc.stdout or "")
            stderr = str(exc.stderr or "")
        (target_dir / "stdout.log").write_text(stdout, encoding="utf-8")
        (target_dir / "stderr.log").write_text(stderr, encoding="utf-8")
        candidate_path = target_dir / "candidate_catalog.json"
        results.append(
            {
                "target_id": item.target.target_id,
                "source_kind": item.target.source_kind,
                "status": status,
                "returncode": returncode,
                "started_at": started.isoformat(),
                "finished_at": datetime.now(UTC).isoformat(),
                "candidate_catalog": str(candidate_path.relative_to(run_dir)),
                "candidate_sha256": _file_digest(candidate_path),
            }
        )
    report = {
        "run_id": run_id,
        "objective": plan.objective,
        "publication_state": "staging_only",
        "results": results,
    }
    report_path = run_dir / "run_report.json"
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("plan", "run"))
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--run-root", type=Path, default=Path("/workspace/runs"))
    parser.add_argument("--run-id")
    parser.add_argument("--target-timeout", type=int, default=3_300)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    manifest = AgentManifest.from_path(args.manifest)
    plan = build_plan(manifest, _load_catalog(args.catalog))
    if args.mode == "plan":
        print(json.dumps(plan.to_dict(), indent=2, sort_keys=True))
        return 0
    report = run_plan(
        plan,
        manifest,
        args.run_root,
        run_id=args.run_id,
        target_timeout_seconds=args.target_timeout,
    )
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
