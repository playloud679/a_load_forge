#!/usr/bin/env python3
"""Manufacturer-first catalog crawler daemon with staging-only publication.

Each cycle inventories every catalog brand, verifies unresolved official sites,
builds a bounded crawler-agent plan, and writes candidate artifacts under
``io/crawler_agent_runs``. It never edits the proprietary catalog and never
invokes git.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import build_official_source_registry as registry_builder
import discover_official_manufacturer_sites as site_discovery
from services.crawler_agent.agent import run_plan
from services.crawler_agent.model import AgentManifest, build_plan

CATALOG = ROOT / "data" / "catalog_proprietario.json"
REGISTRY = ROOT / "data" / "official_source_registry.json"
DISCOVERY_CACHE = ROOT / "data" / "official_source_discovery_cache.json"
MANIFEST = ROOT / "services" / "crawler_agent" / "manifest.loadforge.json"
REPORT = ROOT / "data" / "autonomous_crawler_latest_report.json"
PROGRESS_REPORT = ROOT / "data" / "autonomous_crawler_progress.json"
RUN_ROOT = ROOT / "io" / "crawler_agent_runs"
LOG_FILE = ROOT / "data" / "crawler_daemon.log"


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def log(message: str) -> None:
    line = f"[{datetime.now().astimezone().isoformat(timespec='seconds')}] {message}"
    print(line, flush=True)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        pass


class Progress:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: dict[str, Any] = {"phase": "starting"}
        self._stop = threading.Event()

    def update(self, **values: Any) -> None:
        with self._lock:
            self._state.update(values)
            self._state["updated_at"] = utc_now()
            write_json(PROGRESS_REPORT, self._state)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def heartbeat(self, every_seconds: float) -> None:
        while not self._stop.wait(every_seconds):
            state = self.snapshot()
            write_json(PROGRESS_REPORT, state)
            details = " ".join(f"{key}={value}" for key, value in state.items() if key != "updated_at")
            log(f"PROGRESS {details}")

    def stop(self) -> None:
        self._stop.set()


def load_json(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return fallback
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else fallback


def build_sources(catalog: dict[str, Any], *, max_targets: int) -> tuple[dict[str, Any], dict[str, Any]]:
    discoveries = load_json(DISCOVERY_CACHE, {"discoveries": []})
    registry = registry_builder.build_registry(catalog, discoveries)
    manifest = registry_builder.build_manifest(registry, max_targets=max_targets)
    registry_builder.write_json(REGISTRY, registry)
    registry_builder.write_json(MANIFEST, manifest)
    return registry, manifest


def run_cycle(args: argparse.Namespace, progress: Progress) -> dict[str, Any]:
    started_at = utc_now()
    started_clock = time.monotonic()
    catalog_digest_before = CATALOG.read_bytes()
    catalog = json.loads(catalog_digest_before.decode("utf-8"))

    progress.update(phase="source_registry", brands="loading")
    registry, manifest_payload = build_sources(catalog, max_targets=args.max_targets)
    summary = registry["summary"]
    progress.update(
        phase="source_registry",
        brands=summary["catalog_brands"],
        covered=summary["covered_brand_labels"],
        unresolved=summary["needs_discovery"],
    )
    log(
        "REGISTRY "
        f"brands={summary['catalog_brands']} covered={summary['covered_brand_labels']} "
        f"official_targets={summary['ready_official_targets']} "
        f"unresolved={summary['needs_discovery']} cleanup={summary['needs_brand_cleanup']}"
    )

    discovery_report: dict[str, Any] | None = None
    if not args.skip_discovery and summary["needs_discovery"]:
        progress.update(
            phase="official_site_discovery",
            brands=summary["needs_discovery"],
            verified=0,
        )
        discovery_report = site_discovery.discover(
            registry,
            workers=args.discovery_workers,
            timeout=args.discovery_timeout,
            candidates_per_brand=args.discovery_candidates,
        )
        site_discovery.write_json(DISCOVERY_CACHE, discovery_report)
        registry, manifest_payload = build_sources(catalog, max_targets=args.max_targets)
        summary = registry["summary"]
        progress.update(
            phase="official_site_discovery",
            brands=discovery_report["summary"]["brands_considered"],
            verified=discovery_report["summary"]["verified"],
            unresolved=summary["needs_discovery"],
        )
        log(
            "DISCOVERY "
            f"verified={discovery_report['summary']['verified']} "
            f"remaining={summary['needs_discovery']}"
        )

    manifest = AgentManifest.from_mapping(manifest_payload)
    plan = build_plan(manifest, catalog)
    progress.update(
        phase="official_crawl",
        targets_complete=0,
        targets_total=len(plan.selected),
        publication="staging_only",
    )
    crawl_report_path: Path | None = None
    crawl_report: dict[str, Any] | None = None
    if plan.selected and not args.registry_only:
        run_id = datetime.now(UTC).strftime("crawl-%Y%m%dT%H%M%SZ")
        crawl_report_path = run_plan(
            plan,
            manifest,
            RUN_ROOT,
            run_id=run_id,
            target_timeout_seconds=args.target_timeout,
        )
        crawl_report = json.loads(crawl_report_path.read_text(encoding="utf-8"))
        completed = sum(
            result["status"] in {"succeeded", "observed_only", "no_pages"}
            for result in crawl_report["results"]
        )
        progress.update(
            phase="official_crawl",
            targets_complete=completed,
            targets_total=len(plan.selected),
            publication="staging_only",
        )

    if CATALOG.read_bytes() != catalog_digest_before:
        raise RuntimeError("catalog changed during staging-only crawler cycle")

    result_counts: dict[str, int] = {}
    if crawl_report:
        for result in crawl_report["results"]:
            status = str(result["status"])
            result_counts[status] = result_counts.get(status, 0) + 1
    report = {
        "schema_version": 2,
        "started_at": started_at,
        "finished_at": utc_now(),
        "elapsed_seconds": round(time.monotonic() - started_clock, 3),
        "publication_state": "staging_only",
        "catalog_write": False,
        "catalog_path": str(CATALOG.relative_to(ROOT)),
        "catalog_unchanged": True,
        "registry_summary": summary,
        "discovery_summary": discovery_report["summary"] if discovery_report else None,
        "plan": plan.to_dict(),
        "crawl_report": str(crawl_report_path.relative_to(ROOT)) if crawl_report_path else None,
        "crawl_result_counts": result_counts,
        "retailer_sources": {
            "role": "gap_and_price_discovery_only",
            "configured": ["Finizio Power Team", "Masori", "RG Sound"],
        },
    }
    write_json(REPORT, report)
    progress.update(phase="complete", elapsed_seconds=report["elapsed_seconds"])
    log(
        "CYCLE COMPLETE "
        f"elapsed_s={report['elapsed_seconds']} catalog_unchanged=true "
        f"report={REPORT.relative_to(ROOT)}"
    )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--registry-only", action="store_true")
    parser.add_argument("--skip-discovery", action="store_true")
    parser.add_argument("--interval", type=float, default=3_600.0)
    parser.add_argument("--progress-interval", type=float, default=60.0)
    parser.add_argument("--max-targets", type=int, default=5)
    parser.add_argument("--target-timeout", type=int, default=900)
    parser.add_argument("--discovery-workers", type=int, default=8)
    parser.add_argument("--discovery-timeout", type=float, default=7.0)
    parser.add_argument("--discovery-candidates", type=int, default=8)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    progress = Progress()
    heartbeat = threading.Thread(
        target=progress.heartbeat,
        args=(max(args.progress_interval, 5.0),),
        daemon=True,
    )
    heartbeat.start()
    try:
        while True:
            try:
                run_cycle(args, progress)
            except Exception as exc:
                progress.update(phase="failed", error=type(exc).__name__)
                log(f"CYCLE FAILED {type(exc).__name__}: {exc}")
                if args.once:
                    return 1
            if args.once:
                return 0
            progress.update(phase="sleeping", next_cycle_seconds=args.interval)
            time.sleep(max(args.interval, 60.0))
    finally:
        progress.stop()
        heartbeat.join(timeout=1.0)


if __name__ == "__main__":
    raise SystemExit(main())
