#!/usr/bin/env python3
"""Probe manufacturer domains and expand only sources with measured yield."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = ROOT / "data" / "manufacturer_drivers.json"
DEFAULT_CHECKPOINT = ROOT / "data" / "optional_source_yield_checkpoint.json"
DEFAULT_REPORT_DIR = ROOT / "io" / "optional_source_probes"
FIELDS = ("xmax_mm", "pe_w", "le_mh")
WEIGHTS = {"xmax_mm": 3.0, "pe_w": 2.0, "le_mh": 1.5}


def positive(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) > 0.0
    )


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()


def read_json(path: Path, default: dict | None = None) -> dict:
    if not path.exists():
        return dict(default or {})
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else dict(default or {})


def atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def rank_domains(rows: list[dict]) -> list[dict]:
    domains: dict[str, dict] = {}
    for row in rows:
        driver = row.get("driver") or {}
        missing = [field for field in FIELDS if not positive(driver.get(field))]
        source = str(row.get("source") or "").casefold()
        if any(token in source for token in (
            "retailer", "parts express", "madisound", "factory buyout", "coast buyout",
        )):
            continue
        parsed = urlparse(str(row.get("url") or ""))
        domain = (parsed.hostname or "").casefold().removeprefix("www.")
        if not missing or parsed.scheme not in {"http", "https"} or not domain:
            continue
        item = domains.setdefault(domain, {
            "domain": domain, "records": 0, "urls": set(),
            "missing": {field: 0 for field in FIELDS}, "score": 0.0,
        })
        item["records"] += 1
        item["urls"].add(str(row.get("url") or ""))
        for field in missing:
            item["missing"][field] += 1
            item["score"] += WEIGHTS[field]
    result = []
    for item in domains.values():
        unique_urls = len(item.pop("urls"))
        item["unique_urls"] = unique_urls
        item["url_diversity"] = round(unique_urls / item["records"], 3)
        # One shared archive/table URL needs a dedicated multi-record adapter;
        # probing it as if each row were an independent product is unsafe.
        item["eligible"] = item["url_diversity"] >= 0.5
        result.append(item)
    return sorted(result, key=lambda item: (-item["score"], item["domain"]))


def probe_passes(report: dict, min_yield: float, min_success: float) -> bool:
    processed = int(report.get("processed") or 0)
    if processed <= 0:
        return False
    updated = int(report.get("records_updated") or 0)
    failures = len(report.get("failures") or [])
    return updated / processed >= min_yield and (processed - failures) / processed >= min_success


def _fresh_attempt(record: dict, cooldown_hours: float) -> bool:
    try:
        attempted = dt.datetime.fromisoformat(str(record.get("attempted_at") or ""))
        if attempted.tzinfo is None:
            attempted = attempted.replace(tzinfo=dt.UTC)
    except ValueError:
        return False
    return attempted >= dt.datetime.now(dt.UTC) - dt.timedelta(hours=max(0.0, cooldown_hours))


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


def _run_refresh(args: argparse.Namespace, domain: str, report: Path, max_records: int) -> tuple[int, dict]:
    command = [
        sys.executable, str(ROOT / "tools" / "refresh_manufacturer_optionals.py"),
        "--database", str(args.database), "--report", str(report), "--domain", domain,
        "--apply", "--workers", str(args.workers), "--timeout", str(args.timeout),
        "--per-host-delay", str(args.per_host_delay),
    ]
    if max_records > 0:
        command.extend(["--max-records", str(max_records)])
    completed = subprocess.run(command, cwd=ROOT, check=False)
    return completed.returncode, read_json(report)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--max-domains", type=int, default=5)
    parser.add_argument("--probe-records", type=int, default=3)
    parser.add_argument("--min-probe-yield", type=float, default=0.5)
    parser.add_argument("--min-probe-success", type=float, default=0.5)
    parser.add_argument("--cooldown-hours", type=float, default=720.0)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--per-host-delay", type=float, default=0.75)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    rows = read_json(args.database).get("presets") or []
    checkpoint = read_json(args.checkpoint, {"schema": 1, "domains": {}})
    states = checkpoint.setdefault("domains", {})
    selected = []
    for candidate in rank_domains(rows):
        if not candidate["eligible"]:
            continue
        if not args.force and _fresh_attempt(states.get(candidate["domain"]) or {}, args.cooldown_hours):
            continue
        selected.append(candidate)
        if len(selected) >= max(0, args.max_domains):
            break

    results = []
    for candidate in selected:
        domain = candidate["domain"]
        report = args.report_dir / f"{_slug(domain)}.json"
        code, probe = _run_refresh(args, domain, report, max(1, args.probe_records))
        expanded = code == 0 and probe_passes(
            probe, args.min_probe_yield, args.min_probe_success,
        )
        full = None
        if expanded and candidate["records"] > args.probe_records:
            code, full = _run_refresh(args, domain, report, 0)
        outcome = {
            **candidate,
            "attempted_at": utc_now(),
            "probe": {key: probe.get(key) for key in (
                "processed", "records_updated", "fields_filled",
            )},
            "probe_failures": len(probe.get("failures") or []),
            "expanded": expanded,
            "full": ({key: full.get(key) for key in (
                "processed", "records_updated", "fields_filled",
            )} if full else None),
            "returncode": code,
        }
        states[domain] = outcome
        results.append(outcome)
        checkpoint["updated_at"] = utc_now()
        atomic_write(args.checkpoint, checkpoint)
        print(json.dumps(outcome, sort_keys=True), flush=True)
    print(json.dumps({"selected_domains": len(selected), "results": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
