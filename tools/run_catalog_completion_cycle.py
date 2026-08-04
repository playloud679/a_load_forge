#!/usr/bin/env python3
"""Plan or run restartable catalog-completion cycles.

The coordinator composes the existing conservative metadata and price tools.
It never estimates published-only specifications or commercial prices.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = ROOT / "data" / "manufacturer_drivers.json"
DEFAULT_PRICES = ROOT / "data" / "driver_prices.json"
DEFAULT_REPORT = ROOT / "data" / "catalog_completion_report.json"
DEFAULT_OPTIONAL_REPORT = ROOT / "data" / "manufacturer_optional_refresh_report.json"
DEFAULT_DATASHEET_CHECKPOINT = ROOT / "data" / "catalog_datasheet_completion_checkpoint.json"
DEFAULT_SOURCE_YIELD_CHECKPOINT = ROOT / "data" / "optional_source_yield_checkpoint.json"
OPTIONAL_FIELDS = ("xmax_mm", "pe_w", "le_mh")
TRACKED_FIELDS = (
    "fs_hz", "vas_l", "qts", "qms", "qes", "re_ohm", "sd_cm2",
    "mms_g", "cms_mm_per_n", "bl_tm", *OPTIONAL_FIELDS,
)
FIELD_WEIGHTS = {"xmax_mm": 3.0, "pe_w": 2.0, "le_mh": 1.5, "price": 1.0}


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()


def positive(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) > 0.0
    )


def read_json(path: Path, default: dict | None = None) -> dict:
    if not path.exists():
        return dict(default or {})
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def catalog_rows(database: dict) -> list[dict]:
    rows = database.get("presets") or []
    if not isinstance(rows, list):
        raise ValueError("manufacturer catalog 'presets' must be a list")
    return [row for row in rows if isinstance(row, dict)]


def coverage_snapshot(rows: list[dict]) -> dict:
    total = len(rows)
    fields = {}
    for field in TRACKED_FIELDS:
        present = sum(positive((row.get("driver") or {}).get(field)) for row in rows)
        fields[field] = {
            "present": present,
            "missing": total - present,
            "percent": round(100.0 * present / total, 2) if total else 0.0,
        }
    priced = sum(positive(row.get("price")) for row in rows)
    return {
        "rows": total,
        "fields": fields,
        "price": {
            "present": priced,
            "missing": total - priced,
            "percent": round(100.0 * priced / total, 2) if total else 0.0,
        },
    }


def completion_score(snapshot: dict) -> int:
    """Return a monotonic count used only to detect whether a cycle progressed."""
    fields = snapshot.get("fields") or {}
    return sum(int((fields.get(field) or {}).get("present", 0)) for field in TRACKED_FIELDS) + int(
        (snapshot.get("price") or {}).get("present", 0)
    )


def _source_action(row: dict, missing: list[str], unpriced: bool) -> list[str]:
    actions = []
    parsed = urlparse(str(row.get("url") or ""))
    if missing:
        actions.append(
            "refresh_known_source"
            if parsed.scheme in {"http", "https"} and parsed.hostname
            else "approved_source_discovery"
        )
    if unpriced:
        actions.append("retailer_price_match")
    return actions


def _official_datasheet_candidate(row: dict) -> bool:
    source = str(row.get("source") or "").casefold()
    url = str(row.get("url") or "")
    parsed = urlparse(url)
    excluded = ("retailer", "parts express", "factory buyout", "coast buyout")
    return bool(
        parsed.scheme in {"http", "https"}
        and parsed.hostname
        and not parsed.path.casefold().endswith(".pdf")
        and not any(token in source for token in excluded)
    )


def datasheet_seed_urls(
    rows: list[dict], checkpoint: dict, *, limit: int, cooldown_hours: float,
) -> list[str]:
    attempts = checkpoint.get("attempts") or {}
    cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(hours=max(0.0, cooldown_hours))
    candidates: dict[str, tuple[float, str]] = {}
    for row in rows:
        driver = row.get("driver") or {}
        missing = [field for field in OPTIONAL_FIELDS if not positive(driver.get(field))]
        if not missing or not _official_datasheet_candidate(row):
            continue
        url = str(row.get("url") or "")
        attempted_at = str((attempts.get(url) or {}).get("attempted_at") or "")
        try:
            attempted = dt.datetime.fromisoformat(attempted_at)
            if attempted.tzinfo is None:
                attempted = attempted.replace(tzinfo=dt.UTC)
        except ValueError:
            attempted = None
        if attempted is not None and attempted >= cutoff:
            continue
        score = sum(FIELD_WEIGHTS[field] for field in missing)
        rank = (-score, str(row.get("brand") or "").casefold())
        candidates[url] = min(candidates.get(url, rank), rank)
    ranked = sorted((score, brand, url) for url, (score, brand) in candidates.items())
    return [url for _score, _brand, url in ranked[:max(0, limit)]]


def known_refresh_decision(
    report_path: Path, *, cooldown_hours: float, force: bool,
) -> tuple[bool, str]:
    if force or not report_path.exists():
        return True, "forced" if force else "no previous refresh report"
    age_hours = (
        dt.datetime.now(dt.UTC).timestamp() - report_path.stat().st_mtime
    ) / 3600.0
    previous = read_json(report_path)
    candidates = int(previous.get("candidates") or 0)
    updated = int(previous.get("records_updated") or 0)
    yield_percent = 100.0 * updated / candidates if candidates else 0.0
    if age_hours < max(0.0, cooldown_hours):
        return False, (
            f"last full refresh is {age_hours:.1f}h old with {yield_percent:.2f}% record yield; "
            f"cooldown is {cooldown_hours:g}h"
        )
    return True, f"last refresh is older than the {cooldown_hours:g}h cooldown"


def prioritized_gaps(rows: list[dict], limit: int = 500) -> tuple[list[dict], list[dict]]:
    """Return brand summaries and the most valuable unresolved record tasks."""
    brands: dict[str, dict] = {}
    tasks = []
    for row in rows:
        brand = str(row.get("brand") or "Unknown").strip() or "Unknown"
        driver = row.get("driver") or {}
        missing = [field for field in OPTIONAL_FIELDS if not positive(driver.get(field))]
        unpriced = not positive(row.get("price"))
        if not missing and not unpriced:
            continue
        summary = brands.setdefault(
            brand,
            {
                "brand": brand,
                "records_with_gaps": 0,
                "missing": {field: 0 for field in OPTIONAL_FIELDS},
                "unpriced": 0,
                "known_source_urls": 0,
                "score": 0.0,
            },
        )
        summary["records_with_gaps"] += 1
        for field in missing:
            summary["missing"][field] += 1
            summary["score"] += FIELD_WEIGHTS[field]
        if unpriced:
            summary["unpriced"] += 1
            summary["score"] += FIELD_WEIGHTS["price"]
        parsed = urlparse(str(row.get("url") or ""))
        if missing and parsed.scheme in {"http", "https"} and parsed.hostname:
            summary["known_source_urls"] += 1
        task_score = sum(FIELD_WEIGHTS[field] for field in missing)
        task_score += FIELD_WEIGHTS["price"] if unpriced else 0.0
        tasks.append({
            "brand": brand,
            "model": str(row.get("model") or row.get("name") or ""),
            "missing_fields": missing,
            "missing_price": unpriced,
            "actions": _source_action(row, missing, unpriced),
            "source_url": str(row.get("url") or ""),
            "score": task_score,
        })
    brand_queue = sorted(brands.values(), key=lambda item: (-item["score"], item["brand"].casefold()))
    task_queue = sorted(
        tasks,
        key=lambda item: (-item["score"], item["brand"].casefold(), item["model"].casefold()),
    )
    return brand_queue, task_queue[: max(0, limit)]


def build_plan(database: dict, prices: dict, task_limit: int = 500) -> dict:
    rows = catalog_rows(database)
    brands, tasks = prioritized_gaps(rows, task_limit)
    snapshot = coverage_snapshot(rows)
    price_offers = prices.get("prices") or {}
    if not isinstance(price_offers, dict):
        price_offers = {}
    return {
        "schema": 1,
        "generated_at": utc_now(),
        "mode": "plan",
        "policy": {
            "published_only": list(OPTIONAL_FIELDS) + ["price"],
            "rule": "Never substitute estimates, averages, accessory prices or low-confidence matches.",
        },
        "coverage": snapshot,
        "price_index_offers": len(price_offers),
        "priority_brands": brands,
        "priority_tasks": tasks,
        "stages": [
            {
                "id": "cache_first_merge",
                "purpose": "Apply derivations and rematch the existing price index before network work.",
            },
            {
                "id": "official_datasheets",
                "purpose": "Follow high-value official product pages to durable PDF datasheets.",
            },
            {
                "id": "fresh_sources_only",
                "purpose": "Refresh pages and retailer checkpoints once per run, then enforce cooldown.",
            },
            {
                "id": "verified_merge",
                "purpose": "Derive only physical identities and accept only confident price matches.",
            },
            {
                "id": "publish_views",
                "purpose": "Rebuild source catalogs and regenerate the coverage report.",
            },
        ],
    }


def command_plan(args: argparse.Namespace, cycle_number: int = 1) -> list[tuple[str, list[str]]]:
    python = sys.executable
    commands: list[tuple[str, list[str]]] = []
    network_cycle = cycle_number == 1 or args.repeat_network
    if not args.skip_optionals:
        commands.append(("local_repairs", [
            python, str(ROOT / "tools" / "refresh_manufacturer_optionals.py"),
            "--database", str(args.database), "--report", str(args.optional_report),
            "--local-only", "--apply",
        ]))
    commands.append(("cache_first_merge", [
        python, str(ROOT / "tools" / "enrich_manufacturer_metadata.py"),
        "--database", str(args.database), "--prices", str(args.prices), "--apply",
    ]))
    if not args.skip_optionals and network_cycle:
        if args.max_source_domains > 0:
            source_gate = [
                python, str(ROOT / "tools" / "run_high_yield_optional_cycle.py"),
                "--database", str(args.database),
                "--checkpoint", str(args.source_yield_checkpoint),
                "--max-domains", str(args.max_source_domains),
                "--probe-records", str(args.probe_records),
                "--min-probe-yield", str(args.min_probe_yield),
                "--cooldown-hours", str(args.source_cooldown_hours),
                "--workers", str(args.workers), "--timeout", str(args.timeout),
                "--per-host-delay", str(args.per_host_delay),
            ]
            if args.force_optionals:
                source_gate.append("--force")
            commands.append(("high_yield_sources", source_gate))
        checkpoint = read_json(args.datasheet_checkpoint, {"attempts": {}})
        seeds = datasheet_seed_urls(
            catalog_rows(read_json(args.database)), checkpoint,
            limit=args.datasheet_limit, cooldown_hours=args.source_cooldown_hours,
        )
        if seeds and not args.skip_datasheets:
            datasheets = [
                python, str(ROOT / "tools" / "crawl_driver_datasheets.py"),
                "--catalog", str(args.database), "--max-pages", str(len(seeds)),
                "--max-pdfs", str(max(len(seeds) * 3, 1)),
                "--timeout", str(args.timeout), "--sleep", str(args.datasheet_sleep),
            ]
            for url in seeds:
                datasheets.extend(["--seed", url])
            commands.append(("official_datasheets", datasheets))
    if not args.skip_prices and network_cycle:
        commands.append(("primary_prices", [
            python, str(ROOT / "tools" / "run_price_enrichment_cycle.py"),
            "--output", str(args.prices), "--window-runtime", str(args.price_window_runtime),
            "--sleep", str(args.price_sleep), "--timeout", str(args.timeout),
        ]))
        if not args.skip_extra_retailers:
            commands.append(("regional_prices", [
                python, str(ROOT / "tools" / "run_extra_retailer_price_cycle.py"),
                "--sleep", str(args.extra_price_sleep), "--timeout", str(args.timeout),
                "--source-runtime", str(args.extra_source_runtime),
            ]))
    commands.append(("verified_merge", [
            python, str(ROOT / "tools" / "enrich_manufacturer_metadata.py"),
            "--database", str(args.database), "--prices", str(args.prices), "--apply",
        ]))
    if args.database.resolve() == DEFAULT_DATABASE.resolve() and args.prices.resolve() == DEFAULT_PRICES.resolve():
        commands.append((
            "publish_views", [python, str(ROOT / "tools" / "build_unified_catalogs.py")]
        ))
    commands.append(("status_report", [
            python, str(ROOT / "tools" / "generate_manufacturer_database_report.py"),
            "--database", str(args.database), "--prices", str(args.prices),
        ]))
    return commands


def run_completion(
    args: argparse.Namespace,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> tuple[int, dict]:
    if (
        not args.skip_prices
        and not args.skip_extra_retailers
        and args.prices.resolve() != DEFAULT_PRICES.resolve()
    ):
        raise ValueError(
            "regional retailer tools write data/driver_prices.json; use the default "
            "--prices path or add --skip-extra-retailers"
        )
    report = build_plan(read_json(args.database), read_json(args.prices), args.task_limit)
    report["mode"] = "run"
    report["started_at"] = utc_now()
    report["cycles"] = []
    atomic_write(args.report, report)
    exit_code = 0
    previous_score = completion_score(report["coverage"])
    stalled_cycles = 0
    for cycle_number in range(1, args.max_cycles + 1):
        cycle = {"cycle": cycle_number, "started_at": utc_now(), "steps": []}
        report["cycles"].append(cycle)
        for stage, command in command_plan(args, cycle_number):
            print(f"cycle {cycle_number}: starting {stage}", flush=True)
            started = utc_now()
            completed = runner(command, cwd=ROOT, text=True, capture_output=True, check=False)
            step = {
                "stage": stage,
                "command": command,
                "started_at": started,
                "finished_at": utc_now(),
                "returncode": int(completed.returncode),
                "stdout_tail": str(completed.stdout or "")[-4000:],
                "stderr_tail": str(completed.stderr or "")[-4000:],
            }
            cycle["steps"].append(step)
            if stage == "official_datasheets":
                checkpoint = read_json(args.datasheet_checkpoint, {"schema": 1, "attempts": {}})
                attempts = checkpoint.setdefault("attempts", {})
                for index, value in enumerate(command):
                    if value == "--seed" and index + 1 < len(command):
                        attempts[command[index + 1]] = {
                            "attempted_at": utc_now(),
                            "returncode": int(completed.returncode),
                        }
                checkpoint["updated_at"] = utc_now()
                atomic_write(args.datasheet_checkpoint, checkpoint)
            print(
                f"cycle {cycle_number}: {stage} exit={completed.returncode}",
                flush=True,
            )
            atomic_write(args.report, report)
            if completed.returncode:
                exit_code = 1
                if args.fail_fast:
                    report["finished_at"] = utc_now()
                    report["stop_reason"] = f"stage_failed:{stage}"
                    atomic_write(args.report, report)
                    return exit_code, report
        current_plan = build_plan(read_json(args.database), read_json(args.prices), args.task_limit)
        current_score = completion_score(current_plan["coverage"])
        cycle.update({
            "finished_at": utc_now(),
            "coverage_after": current_plan["coverage"],
            "progress_units": current_score - previous_score,
        })
        report.update({
            "coverage": current_plan["coverage"],
            "price_index_offers": current_plan["price_index_offers"],
            "priority_brands": current_plan["priority_brands"],
            "priority_tasks": current_plan["priority_tasks"],
        })
        stalled_cycles = stalled_cycles + 1 if current_score <= previous_score else 0
        previous_score = current_score
        atomic_write(args.report, report)
        if stalled_cycles >= args.stop_after_stalled:
            report["stop_reason"] = "coverage_stalled"
            break
    else:
        report["stop_reason"] = "max_cycles_reached"
    report["finished_at"] = utc_now()
    report["unresolved"] = {
        "optional_fields": {
            field: report["coverage"]["fields"][field]["missing"] for field in OPTIONAL_FIELDS
        },
        "prices": report["coverage"]["price"]["missing"],
        "note": "Remaining published-only values require an approved new source or do not appear to be published.",
    }
    atomic_write(args.report, report)
    return exit_code, report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("plan", "run"), nargs="?", default="plan")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--prices", type=Path, default=DEFAULT_PRICES)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--optional-report", type=Path, default=DEFAULT_OPTIONAL_REPORT)
    parser.add_argument("--datasheet-checkpoint", type=Path, default=DEFAULT_DATASHEET_CHECKPOINT)
    parser.add_argument("--source-yield-checkpoint", type=Path, default=DEFAULT_SOURCE_YIELD_CHECKPOINT)
    parser.add_argument("--task-limit", type=int, default=500)
    parser.add_argument("--max-cycles", type=int, default=2)
    parser.add_argument("--stop-after-stalled", type=int, default=1)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--max-records", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--per-host-delay", type=float, default=0.5)
    parser.add_argument("--price-window-runtime", type=float, default=900.0)
    parser.add_argument("--price-sleep", type=float, default=2.0)
    parser.add_argument("--extra-price-sleep", type=float, default=0.4)
    parser.add_argument("--extra-source-runtime", type=float, default=300.0)
    parser.add_argument("--datasheet-limit", type=int, default=0)
    parser.add_argument("--datasheet-sleep", type=float, default=0.5)
    parser.add_argument("--source-cooldown-hours", type=float, default=720.0)
    parser.add_argument("--max-source-domains", type=int, default=5)
    parser.add_argument("--probe-records", type=int, default=3)
    parser.add_argument("--min-probe-yield", type=float, default=0.5)
    parser.add_argument("--skip-optionals", action="store_true")
    parser.add_argument("--skip-datasheets", action="store_true")
    parser.add_argument("--skip-prices", action="store_true")
    parser.add_argument("--skip-extra-retailers", action="store_true")
    parser.add_argument("--force-optionals", action="store_true")
    parser.add_argument(
        "--repeat-network", action="store_true",
        help="repeat crawlers in later cycles; default reuses fresh checkpoints",
    )
    parser.add_argument("--fail-fast", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.max_cycles < 1 or args.stop_after_stalled < 1:
        raise SystemExit("--max-cycles and --stop-after-stalled must be positive")
    database = read_json(args.database)
    prices = read_json(args.prices)
    if args.mode == "plan":
        report = build_plan(database, prices, args.task_limit)
        refresh_allowed, refresh_reason = known_refresh_decision(
            args.optional_report,
            cooldown_hours=args.source_cooldown_hours,
            force=args.force_optionals,
        )
        seeds = datasheet_seed_urls(
            catalog_rows(database),
            read_json(args.datasheet_checkpoint, {"attempts": {}}),
            limit=args.datasheet_limit,
            cooldown_hours=args.source_cooldown_hours,
        )
        report["network_strategy"] = {
            "cache_first": True,
            "repeat_network": bool(args.repeat_network),
            "known_source_refresh": {
                "scheduled": False,
                "reason": f"blind full refresh suppressed: {refresh_reason}",
            },
            "source_probe_gate": {
                "scheduled": not args.skip_optionals and args.max_source_domains > 0,
                "max_domains": args.max_source_domains,
                "probe_records": args.probe_records,
                "min_yield": args.min_probe_yield,
            },
            "official_datasheet_seeds": seeds,
            "source_cooldown_hours": args.source_cooldown_hours,
        }
        atomic_write(args.report, report)
        print(json.dumps({
            "report": str(args.report),
            "coverage": report["coverage"],
            "priority_brands": report["priority_brands"][:10],
        }, indent=2, ensure_ascii=False))
        return 0
    code, report = run_completion(args)
    print(json.dumps({
        "report": str(args.report),
        "stop_reason": report.get("stop_reason"),
        "coverage": report["coverage"],
    }, indent=2, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
