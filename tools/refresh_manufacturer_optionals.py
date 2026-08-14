#!/usr/bin/env python3
"""Refetch known product pages and fill published driver specifications safely."""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import multiprocessing
import queue
import re
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
DEFAULT_CHECKPOINT = ROOT / "data" / "manufacturer_optional_refresh_checkpoint.json"
# Increment whenever extraction/validation changes should make completed URLs
# eligible for another pass.  The checkpoint is deliberately parser-versioned.
PARSER_REVISION = 4
MAX_FAILURE_ATTEMPTS = 3
DRIVER_TARGET_FIELDS = ("xmax_mm", "pe_w", "le_mh")
MECHANICAL_TARGET_FIELDS = crawler.MECHANICAL_FIELDS
PUBLISHED_TARGET_FIELDS = crawler.PUBLISHED_SPEC_FIELDS
TARGET_FIELDS = (
    *DRIVER_TARGET_FIELDS, *MECHANICAL_TARGET_FIELDS, *PUBLISHED_TARGET_FIELDS,
)


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()


def normalized_source_url(record: dict) -> str:
    return str(record.get("url") or "").strip()


def read_checkpoint(path: Path) -> dict:
    if not path.exists():
        return {"schema": 1, "attempts": {}}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema": 1, "attempts": {}}
    if not isinstance(value, dict) or not isinstance(value.get("attempts", {}), dict):
        return {"schema": 1, "attempts": {}}
    value.setdefault("schema", 1)
    value.setdefault("attempts", {})
    return value


def checkpoint_is_current(checkpoint: dict, url: str) -> bool:
    attempt = (checkpoint.get("attempts") or {}).get(url) or {}
    if attempt.get("parser_revision") != PARSER_REVISION:
        return False
    if attempt.get("status") in {"updated", "no_change"}:
        return True
    return int(attempt.get("attempt_count") or 0) >= MAX_FAILURE_ATTEMPTS


def clean_model(value: object) -> str:
    text = str(value or "").casefold()
    text = re.sub(r"\b(?:2|4|6|8|12|16|32)\s*(?:ohms?|ω|Ω)\b", "", text)
    return re.sub(r"[^a-z0-9]+", "", text)


def model_identity_matches(record: dict, preset: dict) -> bool:
    """Reject redirects/generic pages unless model or stable T/S identity agrees."""
    expected = clean_model(record.get("model"))
    observed = clean_model(preset.get("model"))
    if expected and observed and expected == observed:
        return True
    left = record.get("driver") or {}
    right = preset.get("driver") or {}
    rules = {
        "fs_hz": (0.015, 0.5),
        "qts": (0.025, 0.012),
        "re_ohm": (0.02, 0.12),
        "sd_cm2": (0.015, 1.0),
    }
    matches = 0
    for field, (relative, absolute) in rules.items():
        a = left.get(field)
        b = right.get(field)
        if not isinstance(a, (int, float)) or not isinstance(b, (int, float)) or a <= 0 or b <= 0:
            continue
        if abs(float(a) - float(b)) > max(absolute, relative * max(abs(float(a)), abs(float(b)))):
            return False
        matches += 1
    return matches >= 3


def seed_checkpoint_from_current_provenance(checkpoint: dict, records: list[dict]) -> int:
    """Adopt records fetched by this parser before checkpoint support existed."""
    attempts = checkpoint.setdefault("attempts", {})
    seeded = 0
    for record in records:
        url = str(record.get("url") or "")
        if not url or url in attempts:
            continue
        provenance = ((record.get("website_fields") or {}).get("field_provenance") or {})
        matching = [
            detail for detail in provenance.values()
            if isinstance(detail, dict)
            and detail.get("source_url") == url
            and str(detail.get("source") or "").startswith("Manufacturer published-spec refresh")
        ]
        if not matching:
            continue
        attempts[url] = {
            "parser_revision": PARSER_REVISION,
            "status": "updated",
            "attempted_at": max(str(item.get("fetched_at") or "") for item in matching),
            "seeded_from_provenance": True,
        }
        seeded += 1
    return seeded


def is_missing(value: object) -> bool:
    return not isinstance(value, (int, float)) or value <= 0


def missing_fields(record: dict) -> list[str]:
    driver = record.get("driver") or {}
    mechanical = record.get("mechanical") or {}
    published = record.get("published_specs") or {}
    return [
        field for field in TARGET_FIELDS
        if is_missing(
            driver.get(field) if field in DRIVER_TARGET_FIELDS
            else mechanical.get(field) if field in MECHANICAL_TARGET_FIELDS
            else published.get(field)
        )
    ]


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
    for field in DRIVER_TARGET_FIELDS:
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

    for section, fields in (
        ("mechanical", MECHANICAL_TARGET_FIELDS),
        ("published_specs", PUBLISHED_TARGET_FIELDS),
    ):
        stored = dict(record.get(section) or {})
        incoming_section = preset.get(section) or {}
        for field in fields:
            value = incoming_section.get(field)
            if not is_missing(stored.get(field)) or is_missing(value):
                continue
            stored[field] = value
            provenance[field] = {
                "source_url": preset.get("url") or incoming_website.get("url") or "",
                "fetched_at": incoming_website.get("fetched_at") or "",
                "source": preset.get("source") or "Manufacturer published-spec refresh",
                "measurement": raw_measurements.get(field) or {},
            }
            changed.append(field)
        if stored:
            record[section] = stored

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
            # Reserve a polite request start time, then release the host lock.
            # Slow responses may overlap, but request starts remain rate-limited.
            self._last_request[host] = time.monotonic()
        return function()


def _parse_pdf_worker(content: bytes, url: str, brand: str, output_queue) -> None:
    try:
        page = crawler.parse_pdf(content)
        preset, errors = crawler.build_preset(
            page, url, "Manufacturer published-spec refresh", brand, extraction_method="pdf",
        )
        if preset is None:
            preset = crawler.build_published_observation(
                page, url, "Manufacturer published-spec refresh", brand, extraction_method="pdf",
            )
        output_queue.put((preset, errors))
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
    url = normalized_source_url(record)

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
                page, result.url, "Manufacturer published-spec refresh",
                str(record.get("brand") or ""), extraction_method="html",
            )
            if preset is None:
                preset = crawler.build_published_observation(
                    page, result.url, "Manufacturer published-spec refresh",
                    str(record.get("brand") or ""), extraction_method="html",
                )
        if preset is None:
            return {"index": index, "url": url, "errors": errors or ["no valid driver extracted"]}
        if not model_identity_matches(record, preset):
            return {
                "index": index,
                "url": url,
                "errors": [
                    "model identity mismatch: "
                    f"expected {record.get('model')!r}, observed {preset.get('model')!r}"
                ],
            }
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
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--apply", action="store_true", help="Atomically update the database; default is dry-run.")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--parse-timeout", type=float, default=30.0, help="Maximum PDF parser CPU time per file.")
    parser.add_argument("--per-host-delay", type=float, default=0.15)
    parser.add_argument("--max-records", type=int, default=0)
    parser.add_argument("--local-only", action="store_true", help="Apply raw-value reparsing without network requests.")
    parser.add_argument("--domain", action="append", default=[], help="Restrict to a hostname; repeatable.")
    parser.add_argument("--force", action="store_true", help="Ignore URL attempts for the current parser revision.")
    args = parser.parse_args()

    payload = json.loads(args.database.read_text(encoding="utf-8"))
    presets = list(payload.get("presets") or [])
    checkpoint = read_checkpoint(args.checkpoint)
    checkpoint_seeded = seed_checkpoint_from_current_provenance(checkpoint, presets)
    unitless_power_invalidations = sum(invalidate_unitless_power(record) for record in presets)
    local_power_repairs = sum(repair_reparsable_power(record) for record in presets)
    allowed_domains = {item.casefold().removeprefix("www.") for item in args.domain}
    candidates: list[tuple[int, dict]] = []
    for index, record in enumerate(presets):
        url = normalized_source_url(record)
        parsed = urlparse(url)
        host = (parsed.hostname or "").casefold().removeprefix("www.")
        if (
            (not missing_fields(record) and not suspect_unitless_power(record))
            or parsed.scheme not in {"http", "https"}
            or not host
            or (not args.force and checkpoint_is_current(checkpoint, url))
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
    attempts: dict[str, dict] = {}
    stored_attempts = checkpoint.setdefault("attempts", {})
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
                attempts[outcome["url"]] = {
                    "parser_revision": PARSER_REVISION,
                    "status": "updated" if changed else "no_change",
                    "attempted_at": utc_now(),
                    "fields_filled": changed,
                }
            else:
                failures.append({"url": outcome["url"], "errors": outcome.get("errors") or []})
                previous = stored_attempts.get(outcome["url"]) or {}
                previous_count = (
                    int(previous.get("attempt_count") or 0)
                    if previous.get("parser_revision") == PARSER_REVISION else 0
                )
                attempts[outcome["url"]] = {
                    "parser_revision": PARSER_REVISION,
                    "status": "failure",
                    "attempted_at": utc_now(),
                    "attempt_count": previous_count + 1,
                    "errors": outcome.get("errors") or [],
                }
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
        "checkpoint_seeded": checkpoint_seeded,
        "parser_revision": PARSER_REVISION,
        "records_updated_by_host": dict(host_counts.most_common()),
        "failures": failures,
    }
    report["coverage_after"] = {
        field: {
            "present": sum(not is_missing(
                (record.get("driver") or {}).get(field) if field in DRIVER_TARGET_FIELDS
                else (record.get("mechanical") or {}).get(field) if field in MECHANICAL_TARGET_FIELDS
                else (record.get("published_specs") or {}).get(field)
            ) for record in presets),
            "missing": sum(is_missing(
                (record.get("driver") or {}).get(field) if field in DRIVER_TARGET_FIELDS
                else (record.get("mechanical") or {}).get(field) if field in MECHANICAL_TARGET_FIELDS
                else (record.get("published_specs") or {}).get(field)
            ) for record in presets),
            "percent": round(
                100.0 * sum(not is_missing(
                    (record.get("driver") or {}).get(field) if field in DRIVER_TARGET_FIELDS
                    else (record.get("mechanical") or {}).get(field) if field in MECHANICAL_TARGET_FIELDS
                    else (record.get("published_specs") or {}).get(field)
                ) for record in presets)
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
        checkpoint["attempts"].update(attempts)
        checkpoint["updated_at"] = utc_now()
        atomic_write(args.checkpoint, checkpoint)
    print(json.dumps({key: value for key, value in report.items() if key != "failures"}, indent=2))
    print(f"failures={len(failures)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
