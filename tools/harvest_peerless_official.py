#!/usr/bin/env python3
"""Harvest complete T/S records from Peerless/Tymphany's public official API."""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = "https://www.products-peerless.com/api"
DEFAULT_OUTPUT = ROOT / "data" / "peerless_official_checkpoint.json"
USER_AGENT = "LoadForgeCrawler/1.0 (official catalog research)"
REQUIRED = ("Fs", "Vas", "Qts", "Qms", "Re", "Sd")
LF_TYPES = {"fullrange", "subwoofer", "woofer"}


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def fetch_json(url: str, timeout_s: float = 30.0) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(request, timeout=timeout_s) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"official API returned {type(payload).__name__}, expected object")
    return payload


def _positive_number(row: dict[str, Any], key: str) -> float | None:
    try:
        value = float(row.get(key))
    except (TypeError, ValueError):
        return None
    return value if value > 0.0 else None


def preset_from_detail(row: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize one first-party API detail response without inferred core data."""
    driver_type = str(row.get("Type") or "").strip()
    if driver_type.casefold() not in LF_TYPES:
        return None
    values = {key: _positive_number(row, key) for key in REQUIRED}
    if any(values[key] is None for key in REQUIRED):
        return None
    assert all(value is not None for value in values.values())
    if values["Qms"] <= values["Qts"]:
        return None
    model = str(row.get("MarketingNo") or "").strip()
    driver_id = row.get("id")
    if not model or not isinstance(driver_id, int):
        return None
    detail_url = f"https://www.products-peerless.com/en/transducer/{driver_id}"
    driver = {
        "fs_hz": values["Fs"],
        "vas_l": values["Vas"],
        "qts": values["Qts"],
        "qms": values["Qms"],
        "re_ohm": values["Re"],
        "sd_cm2": values["Sd"],
        "qes": _positive_number(row, "Qes") or 0.0,
        "le_mh": _positive_number(row, "Le") or 0.0,
        "le10k_mh": None,
        "xmax_mm": _positive_number(row, "Xmax") or 0.0,
        "pe_w": _positive_number(row, "Power") or 0.0,
        "mms_g": _positive_number(row, "Mms"),
        # The official product client labels Cms in micrometres/newton.
        "cms_mm_per_n": (
            _positive_number(row, "Cms") / 1000.0
            if _positive_number(row, "Cms") is not None
            else None
        ),
        "bl_tm": _positive_number(row, "BL"),
    }
    size = _positive_number(row, "Size")
    size_unit = str(row.get("SizeMeasurementType") or "").casefold()
    size_in = size / 25.4 if size is not None and size_unit == "mm" else size
    raw_measurements = {
        "fs_hz": {"value": values["Fs"], "unit": "Hz", "source_url": detail_url},
        "vas_l": {"value": values["Vas"], "unit": "L", "source_url": detail_url},
        "qts": {"value": values["Qts"], "unit": "", "source_url": detail_url},
        "qms": {"value": values["Qms"], "unit": "", "source_url": detail_url},
        "re_ohm": {"value": values["Re"], "unit": "ohm", "source_url": detail_url},
        "sd_cm2": {"value": values["Sd"], "unit": "cm2", "source_url": detail_url},
    }
    preset: dict[str, Any] = {
        "name": f"WEB: Peerless {model}",
        "brand": "Peerless",
        "model": model,
        "size_in": round(size_in, 3) if size_in else None,
        "kind": "Loudspeaker driver",
        "url": detail_url,
        "source": "Official manufacturer site",
        "driver": driver,
        "raw": {key: value for key, value in row.items() if key in {
            "Fs", "Vas", "Qts", "Qms", "Qes", "Re", "Sd", "Le", "Xmax",
            "Power", "Mms", "Cms", "BL", "Impedance", "SensZ", "Type",
        }},
        "website_fields": {
            "title": model,
            "brand": "Peerless",
            "model": model,
            "url": detail_url,
            "source": "Official manufacturer site",
            "fetched_at": utc_now(),
            "extraction_method": "official.api",
            "confidence": 1.0,
            "api_id": driver_id,
            "official_pdf": row.get("pdf"),
            "raw_measurements": raw_measurements,
        },
    }
    mechanical_weight = _positive_number(row, "NetWeight")
    if mechanical_weight is not None and str(row.get("WeightMeasurementType") or "").casefold() == "kg":
        preset["mechanical"] = {"weight_kg": mechanical_weight}
    published_specs = {
        "nominal_impedance_ohm": _positive_number(row, "Impedance"),
        "sensitivity_db": _positive_number(row, "SensZ"),
        "voice_coil_diameter_mm": _positive_number(row, "VoiceCoilInnerDiameter"),
        "xmech_mm": _positive_number(row, "Xmech"),
    }
    published_specs = {key: value for key, value in published_specs.items() if value is not None}
    if published_specs:
        preset["published_specs"] = published_specs
    return preset


def harvest(
    *,
    fetcher: Callable[[str, float], dict[str, Any]] = fetch_json,
    timeout_s: float = 30.0,
    sleep_s: float = 0.15,
    workers: int = 4,
    retries: int = 2,
) -> dict[str, Any]:
    listings: list[dict[str, Any]] = []
    first = fetcher(f"{API_ROOT}/drivers?page=1", timeout_s)
    last_page = int(first.get("last_page") or 1)
    for page in range(1, last_page + 1):
        payload = first if page == 1 else fetcher(
            f"{API_ROOT}/drivers?{urlencode({'page': page})}", timeout_s
        )
        listings.extend(item for item in payload.get("data", []) if isinstance(item, dict))
        if sleep_s and page < last_page:
            time.sleep(sleep_s)

    presets: list[dict[str, Any]] = []
    rejected = 0
    failures: list[dict[str, Any]] = []
    seen_models: set[str] = set()

    def fetch_detail(listing: dict[str, Any]) -> tuple[int | None, dict[str, Any] | None, str | None]:
        driver_id = listing.get("id")
        if not isinstance(driver_id, int):
            return None, None, "missing integer API id"
        for attempt in range(retries + 1):
            try:
                return driver_id, fetcher(f"{API_ROOT}/driver/{driver_id}", timeout_s), None
            except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
                if attempt >= retries:
                    return driver_id, None, f"{type(exc).__name__}: {exc}"
                time.sleep(0.25 * (attempt + 1))
        return driver_id, None, "retry loop exhausted"

    details: list[tuple[int, dict[str, Any]]] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        pending = [pool.submit(fetch_detail, listing) for listing in listings]
        for completed, future in enumerate(as_completed(pending), start=1):
            driver_id, detail, error = future.result()
            if detail is None:
                failures.append({"id": driver_id, "error": error})
            else:
                assert driver_id is not None
                details.append((driver_id, detail))
            if completed % 10 == 0 or completed == len(pending):
                print(
                    f"PEERLESS PROGRESS: {completed}/{len(pending)} "
                    f"detail_failures={len(failures)}",
                    flush=True,
                )
            if sleep_s:
                time.sleep(sleep_s)

    for _driver_id, detail in sorted(details):
        preset = preset_from_detail(detail)
        if preset is None or preset["model"].casefold() in seen_models:
            rejected += 1
            continue
        presets.append(preset)
        seen_models.add(preset["model"].casefold())
    return {
        "schema_version": 1,
        "generated_at": utc_now(),
        "source": "Peerless/Tymphany public official API",
        "api_root": API_ROOT,
        "publication_state": "staging_only",
        "listed": len(listings),
        "accepted": len(presets),
        "rejected_incomplete": rejected,
        "detail_failures": failures,
        "presets": presets,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--sleep", type=float, default=0.15)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--retries", type=int, default=2)
    args = parser.parse_args()
    payload = harvest(
        timeout_s=args.timeout,
        sleep_s=max(0.0, args.sleep),
        workers=max(1, args.workers),
        retries=max(0, args.retries),
    )
    write_json(args.output, payload)
    print(
        f"PEERLESS OFFICIAL: listed={payload['listed']} "
        f"accepted={payload['accepted']} rejected={payload['rejected_incomplete']} "
        f"detail_failures={len(payload['detail_failures'])} "
        f"output={args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
