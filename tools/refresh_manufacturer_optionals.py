#!/usr/bin/env python3
"""Refetch known product pages and fill missing Xmax, Pe and Le safely."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import multiprocessing
import queue
import sys
import threading
import time
from collections import Counter, deque
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import crawl_thiele_small as crawler  # noqa: E402

DEFAULT_DATABASE = ROOT / "data" / "manufacturer_drivers.json"
DEFAULT_REPORT = ROOT / "data" / "manufacturer_optional_refresh_report.json"
TARGET_FIELDS = ("xmax_mm", "pe_w", "le_mh")


def is_missing(value: object) -> bool:
    return not isinstance(value, (int, float)) or value <= 0


def missing_fields(record: dict) -> list[str]:
    driver = record.get("driver") or {}
    return [field for field in TARGET_FIELDS if is_missing(driver.get(field))]


def suspect_unitless_power(record: dict) -> bool:
    raw = ((record.get("website_fields") or {}).get("raw_measurements") or {}).get("pe_w") or {}
    if not isinstance(raw, dict):
        return False
    return bool(raw) and not crawler.normalize_unit(str(raw.get("unit") or ""))


def repair_reparsable_power(record: dict) -> bool:
    """Repair values such as ``2,000 W`` parsed by the old decimal-comma rule."""
    website = record.get("website_fields") or {}
    raw = (website.get("raw_measurements") or {}).get("pe_w") or {}
    if not isinstance(raw, dict):
        return False
    unit = str(raw.get("unit") or "")
    if crawler.normalize_unit(unit) not in {"w", "kw"}:
        return False
    corrected = crawler.convert_measurement("pe_w", raw.get("raw_value"), unit)
    current = (record.get("driver") or {}).get("pe_w")
    if corrected is None or not isinstance(current, (int, float)) or abs(corrected - current) < 1e-9:
        return False
    record["driver"]["pe_w"] = corrected
    provenance = dict(website.get("field_provenance") or {})
    provenance["pe_w"] = {
        "source_url": record.get("url") or website.get("url") or "",
        "source": "local raw-measurement correction",
        "measurement": raw,
        "correction": "reparsed thousands separator with explicit power unit",
    }
    website["field_provenance"] = provenance
    record["website_fields"] = website
    return True


def invalidate_unitless_power(record: dict) -> bool:
    """Remove legacy Pe values whose source measurement did not include W/kW."""
    if not suspect_unitless_power(record):
        return False
    driver = record.get("driver") or {}
    current = driver.get("pe_w")
    if is_missing(current):
        return False
    website = record.get("website_fields") or {}
    invalidated = dict(website.get("invalidated_fields") or {})
    invalidated["pe_w"] = {
        "previous_value": current,
        "reason": "legacy free-text extraction had no explicit W/kW unit",
    }
    website["invalidated_fields"] = invalidated
    driver["pe_w"] = 0.0
    record["driver"] = driver
    record["website_fields"] = website
    return True


def round_robin_by_host(candidates: list[tuple[int, dict]]) -> list[tuple[int, dict]]:
    """Interleave hosts so workers never all queue behind one host lock."""
    groups: dict[str, deque[tuple[int, dict]]] = {}
    for candidate in candidates:
        host = (urlparse(str(candidate[1].get("url") or "")).hostname or "").casefold()
        groups.setdefault(host, deque()).append(candidate)
    ordered: list[tuple[int, dict]] = []
    active = list(groups)
    while active:
        remaining: list[str] = []
        for host in active:
            ordered.append(groups[host].popleft())
            if groups[host]:
                remaining.append(host)
        active = remaining
    return ordered


def apply_preset_to_record(record: dict, preset: dict) -> list[str]:
    """Fill target fields only, retaining auditable source measurements."""
    driver = dict(record.get("driver") or {})
    incoming = preset.get("driver") or {}
    incoming_website = preset.get("website_fields") or {}
    raw_measurements = incoming_website.get("raw_measurements") or {}
    derivations = incoming_website.get("derivations") or {}
    changed: list[str] = []

    website = dict(record.get("website_fields") or {})
    provenance = dict(website.get("field_provenance") or {})
    for field in TARGET_FIELDS:
        value = incoming.get(field)
        replace_suspect_power = field == "pe_w" and suspect_unitless_power(record)
        incoming_raw = raw_measurements.get(field) or {}
        incoming_has_power_unit = crawler.normalize_unit(str(incoming_raw.get("unit") or "")) in {"w", "kw"}
        if (
            (not is_missing(driver.get(field)) and not (replace_suspect_power and incoming_has_power_unit))
            or is_missing(value)
        ):
            continue
        driver[field] = value
        detail = {
            "source_url": preset.get("url") or incoming_website.get("url") or "",
            "fetched_at": incoming_website.get("fetched_at") or "",
            "source": preset.get("source") or "Manufacturer optional refresh",
        }
        if field in raw_measurements:
            detail["measurement"] = raw_measurements[field]
        if field in derivations:
            detail["derivation"] = derivations[field]
            for source_field in derivations[field].get("source_fields", []):
                if source_field in raw_measurements:
                    detail.setdefault("source_measurements", {})[source_field] = raw_measurements[source_field]
        provenance[field] = detail
        changed.append(field)

    if changed:
        website["field_provenance"] = provenance
        stored_raw = dict(website.get("raw_measurements") or {})
        for field in changed:
            if field in raw_measurements:
                stored_raw[field] = raw_measurements[field]
        website["raw_measurements"] = stored_raw
        record["driver"] = driver
        record["website_fields"] = website
    return changed


class HostThrottle:
    def __init__(self, delay_s: float):
        self.delay_s = max(0.0, delay_s)
        self._locks: dict[str, threading.Lock] = {}
        self._last_request: dict[str, float] = {}
        self._guard = threading.Lock()

    def run(self, url: str, function):
        host = (urlparse(url).hostname or "").casefold()
        with self._guard:
            lock = self._locks.setdefault(host, threading.Lock())
        with lock:
            elapsed = time.monotonic() - self._last_request.get(host, 0.0)
            if elapsed < self.delay_s:
                time.sleep(self.delay_s - elapsed)
            try:
                return function()
            finally:
                self._last_request[host] = time.monotonic()


def _parse_pdf_worker(content: bytes, url: str, brand: str, output_queue) -> None:
    try:
        page = crawler.parse_pdf(content)
        output_queue.put(crawler.build_preset(
            page, url, "Manufacturer optional refresh", brand, extraction_method="pdf",
        ))
    except Exception as exc:
        output_queue.put((None, [f"{type(exc).__name__}: {exc}"]))


def parse_pdf_with_timeout(content: bytes, url: str, brand: str, timeout_s: float):
    context = multiprocessing.get_context("spawn")
    output_queue = context.Queue(maxsize=1)
    process = context.Process(target=_parse_pdf_worker, args=(content, url, brand, output_queue))
    process.start()
    process.join(max(1.0, timeout_s))
    if process.is_alive():
        process.terminate()
        process.join(5.0)
        return None, [f"PDF parse timeout after {timeout_s:g}s"]
    try:
        return output_queue.get(timeout=1.0)
    except queue.Empty:
        return None, [f"PDF parser exited with code {process.exitcode} without a result"]


def fetch_preset(
    index: int, record: dict, throttle: HostThrottle, timeout_s: float, parse_timeout_s: float,
) -> dict:
    url = str(record.get("url") or "")

    def fetch():
        return crawler.fetch_resource(url, timeout_s, crawler.DEFAULT_USER_AGENT)

    try:
        result = throttle.run(url, fetch)
        is_pdf = result.content_type == "application/pdf" or result.url.casefold().endswith(".pdf")
        if is_pdf:
            preset, errors = parse_pdf_with_timeout(
                result.content, result.url, str(record.get("brand") or ""), parse_timeout_s,
            )
        else:
            page = crawler.parse_html(result.content)
            preset, errors = crawler.build_preset(
                page, result.url, "Manufacturer optional refresh",
                str(record.get("brand") or ""), extraction_method="html",
            )
        if preset is None:
            return {"index": index, "url": url, "errors": errors or ["no valid driver extracted"]}
        return {"index": index, "url": url, "preset": preset}
    except Exception as exc:  # keep the bulk refresh resumable across hostile sites
        return {"index": index, "url": url, "errors": [f"{type(exc).__name__}: {exc}"]}


def atomic_write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--apply", action="store_true", help="Atomically update the database; default is dry-run.")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--parse-timeout", type=float, default=30.0, help="Maximum PDF parser CPU time per file.")
    parser.add_argument("--per-host-delay", type=float, default=0.15)
    parser.add_argument("--max-records", type=int, default=0)
    parser.add_argument("--local-only", action="store_true", help="Apply raw-value reparsing without network requests.")
    parser.add_argument("--domain", action="append", default=[], help="Restrict to a hostname; repeatable.")
    args = parser.parse_args()

    payload = json.loads(args.database.read_text(encoding="utf-8"))
    presets = list(payload.get("presets") or [])
    unitless_power_invalidations = sum(invalidate_unitless_power(record) for record in presets)
    local_power_repairs = sum(repair_reparsable_power(record) for record in presets)
    allowed_domains = {item.casefold().removeprefix("www.") for item in args.domain}
    candidates: list[tuple[int, dict]] = []
    for index, record in enumerate(presets):
        url = str(record.get("url") or "")
        parsed = urlparse(url)
        host = (parsed.hostname or "").casefold().removeprefix("www.")
        if (
            (not missing_fields(record) and not suspect_unitless_power(record))
            or parsed.scheme not in {"http", "https"}
            or not host
        ):
            continue
        if allowed_domains and host not in allowed_domains:
            continue
        candidates.append((index, record))
    if args.local_only:
        candidates = []
    if args.max_records > 0:
        candidates = candidates[:args.max_records]
    candidates = round_robin_by_host(candidates)

    throttle = HostThrottle(args.per_host_delay)
    field_counts: Counter[str] = Counter()
    host_counts: Counter[str] = Counter()
    failures: list[dict] = []
    processed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {
            executor.submit(
                fetch_preset, index, record, throttle, args.timeout, args.parse_timeout,
            ): index
            for index, record in candidates
        }
        for future in concurrent.futures.as_completed(futures):
            outcome = future.result()
            processed += 1
            if outcome.get("preset"):
                changed = apply_preset_to_record(presets[outcome["index"]], outcome["preset"])
                field_counts.update(changed)
                if changed:
                    host_counts[urlparse(outcome["url"]).hostname or ""] += 1
            else:
                failures.append({"url": outcome["url"], "errors": outcome.get("errors") or []})
            if processed % 100 == 0:
                print(f"processed={processed}/{len(candidates)} filled={sum(field_counts.values())}", flush=True)

    report = {
        "mode": "apply" if args.apply else "dry-run",
        "database": str(args.database),
        "candidates": len(candidates),
        "processed": processed,
        "records_updated": sum(host_counts.values()),
        "fields_filled": dict(sorted(field_counts.items())),
        "local_power_repairs": local_power_repairs,
        "unitless_power_invalidations": unitless_power_invalidations,
        "records_updated_by_host": dict(host_counts.most_common()),
        "failures": failures,
    }
    report["coverage_after"] = {
        field: {
            "present": sum(not is_missing((record.get("driver") or {}).get(field)) for record in presets),
            "missing": sum(is_missing((record.get("driver") or {}).get(field)) for record in presets),
            "percent": round(
                100.0 * sum(not is_missing((record.get("driver") or {}).get(field)) for record in presets)
                / len(presets),
                2,
            ) if presets else 0.0,
        }
        for field in TARGET_FIELDS
    }
    if args.apply:
        payload["presets"] = presets
        payload["downloaded_at"] = crawler.utc_now()
        payload["usable_presets"] = len(presets)
        atomic_write(args.database, payload)
        atomic_write(args.report, report)
    print(json.dumps({key: value for key, value in report.items() if key != "failures"}, indent=2))
    print(f"failures={len(failures)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
