#!/usr/bin/env python3
"""Complete safely derivable manufacturer metadata and synchronize prices."""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import math
import re
from collections import Counter
from pathlib import Path

try:
    import enrich_driver_prices as price_tools
except ModuleNotFoundError:  # Imported as tools.enrich_manufacturer_metadata.
    from tools import enrich_driver_prices as price_tools


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = ROOT / "data" / "manufacturer_drivers.json"
DEFAULT_PRICES = ROOT / "data" / "driver_prices.json"
DEFAULT_REPORT = ROOT / "data" / "manufacturer_metadata_enrichment_report.json"
RHO_AIR_KG_M3 = 1.18
SPEED_OF_SOUND_M_S = 344.0

# Nominal frame classes calibrated to conventional effective piston areas.
# The value is an estimate, not a substitute for a published frame diameter.
SIZE_SD_ANCHORS = (
    (1.0, 5.0), (1.5, 8.0), (2.0, 13.0), (2.5, 22.0),
    (3.0, 32.0), (3.5, 38.0), (4.0, 50.0), (4.5, 65.0),
    (5.0, 80.0), (5.25, 90.0), (5.5, 100.0), (6.0, 115.0),
    (6.5, 132.0), (7.0, 150.0), (7.5, 158.0), (8.0, 220.0),
    (8.5, 240.0), (9.0, 255.0), (9.5, 280.0), (10.0, 350.0),
    (11.0, 410.0), (12.0, 530.0), (13.0, 610.0), (13.5, 700.0),
    (14.0, 750.0), (15.0, 855.0), (16.0, 950.0), (18.0, 1210.0),
    (19.0, 1450.0), (21.0, 1680.0), (24.0, 2200.0),
)


def positive(value: object) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) and result > 0.0 else None


def nominal_size_from_sd(sd_cm2: float) -> tuple[float, float]:
    """Return nearest conventional nominal size and an estimation confidence."""
    sd = positive(sd_cm2)
    if sd is None:
        raise ValueError("Sd must be positive")
    size, anchor = min(SIZE_SD_ANCHORS, key=lambda item: abs(math.log(sd / item[1])))
    distance = abs(math.log(sd / anchor))
    confidence = max(0.50, min(0.95, 0.95 - distance / math.log(2.0) * 0.35))
    return size, round(confidence, 3)


def explicit_size_from_text(value: object) -> float | None:
    """Extract an explicitly labelled nominal inch size, including fractions."""
    text = str(value or "").replace("¼", " 1/4").replace("½", " 1/2").replace("¾", " 3/4")
    match = re.search(
        r"(?<![\d.])(\d+(?:[.,]\d+)?)"
        r"(?:\s*[- ]\s*(\d+)\s*/\s*(\d+))?\s*(?:inches?|in\b|[\"″])",
        text,
        re.I,
    )
    if not match:
        return None
    size = float(match.group(1).replace(",", "."))
    if match.group(2) and match.group(3):
        denominator = float(match.group(3))
        if denominator:
            size += float(match.group(2)) / denominator
    return round(size, 3) if 0.5 <= size <= 32.0 else None


def _mark_derivation(item: dict, field: str, formula: str, confidence: float = 1.0) -> None:
    website = item.setdefault("website_fields", {})
    derived_fields = list(website.get("derived_fields") or [])
    if field not in derived_fields:
        derived_fields.append(field)
    website["derived_fields"] = derived_fields
    derivations = dict(website.get("derivations") or {})
    derivations[field] = {
        "formula": formula,
        "confidence": round(float(confidence), 3),
    }
    website["derivations"] = derivations


def complete_physical_metadata(item: dict) -> Counter:
    """Fill only values determined by T/S identities; preserve published data."""
    counts: Counter = Counter()
    driver = item.setdefault("driver", {})
    fs = positive(driver.get("fs_hz"))
    vas = positive(driver.get("vas_l"))
    qts = positive(driver.get("qts"))
    qms = positive(driver.get("qms"))
    re_ohm = positive(driver.get("re_ohm"))
    sd = positive(driver.get("sd_cm2"))
    if None in (fs, vas, qts, qms, re_ohm, sd) or qms <= qts:
        return counts

    if positive(driver.get("qes")) is None:
        driver["qes"] = round(qts * qms / (qms - qts), 8)
        _mark_derivation(item, "qes", "Qes = Qts*Qms/(Qms-Qts)")
        counts["qes"] += 1

    if positive(driver.get("cms_mm_per_n")) is None:
        mms_g = positive(driver.get("mms_g"))
        if mms_g is not None:
            cms_mm_per_n = 1_000_000.0 / ((2.0 * math.pi * fs) ** 2 * mms_g)
            formula = "Cms = 1/((2*pi*Fs)^2*Mms)"
        else:
            sd_m2 = sd / 10_000.0
            cms_mm_per_n = (
                (vas / 1000.0)
                / (RHO_AIR_KG_M3 * SPEED_OF_SOUND_M_S**2 * sd_m2**2)
                * 1000.0
            )
            formula = "Cms = Vas/(rho*c^2*Sd^2)"
        if 0.000001 <= cms_mm_per_n <= 1000.0:
            driver["cms_mm_per_n"] = round(cms_mm_per_n, 8)
            _mark_derivation(item, "cms_mm_per_n", formula)
            counts["cms_mm_per_n"] += 1

    if positive(driver.get("mms_g")) is None and positive(driver.get("cms_mm_per_n")) is not None:
        cms_m_per_n = positive(driver.get("cms_mm_per_n")) / 1000.0
        mms_kg = 1.0 / ((2.0 * math.pi * fs) ** 2 * cms_m_per_n)
        mms_g = mms_kg * 1000.0
        if 0.001 <= mms_g <= 100_000.0:
            driver["mms_g"] = round(mms_g, 8)
            _mark_derivation(item, "mms_g", "Mms = 1/((2*pi*Fs)^2*Cms)")
            counts["mms_g"] += 1

    if positive(driver.get("bl_tm")) is None and positive(driver.get("mms_g")) is not None:
        mms_kg = positive(driver.get("mms_g")) / 1000.0
        qes = positive(driver.get("qes"))
        bl_tm = math.sqrt(2.0 * math.pi * fs * mms_kg * re_ohm / qes)
        if 0.0 < bl_tm <= 1000.0:
            driver["bl_tm"] = round(bl_tm, 8)
            _mark_derivation(item, "bl_tm", "BL = sqrt(2*pi*Fs*Mms*Re/Qes)")
            counts["bl_tm"] += 1

    if positive(item.get("size_in")) is None:
        explicit_size = explicit_size_from_text(f"{item.get('model', '')} {item.get('name', '')}")
        if explicit_size is not None:
            size, confidence = explicit_size, 1.0
            formula = "nominal size parsed from model/title"
        else:
            size, confidence = nominal_size_from_sd(sd)
            formula = "nominal frame class estimated from Sd"
        item["size_in"] = size
        _mark_derivation(item, "size_in", formula, confidence)
        counts["size_in"] += 1
    return counts


def _safe_price_record(item: dict, prices: dict, min_confidence: float) -> dict | None:
    record = prices.get(item.get("name")) or prices.get(item.get("model"))
    if not isinstance(record, dict):
        return None
    price = positive(record.get("price"))
    currency = str(record.get("currency") or "").upper()
    if price is None or not currency:
        return None
    candidate = price_tools.PresetCandidate(
        name=str(item.get("name") or ""),
        brand=str(item.get("brand") or ""),
        model=str(item.get("model") or ""),
        query=str(item.get("model") or ""),
        url=str(item.get("url") or ""),
    )
    product = {
        "name": record.get("matched_name", ""),
        "brand": record.get("matched_brand", ""),
        "mpn": record.get("matched_mpn", ""),
        "sku": record.get("matched_mpn", ""),
        "url": record.get("url", ""),
    }
    if price_tools.match_score(candidate, product) < min_confidence:
        return None
    return record


def synchronize_price(item: dict, prices: dict, min_confidence: float = 0.8) -> bool:
    record = _safe_price_record(item, prices, min_confidence)
    website = item.setdefault("website_fields", {})
    if record is None:
        website["price_status"] = "no_confident_retailer_match"
        return False
    item["price"] = round(float(record["price"]), 2)
    item["currency"] = str(record["currency"]).upper()
    item["price_url"] = str(record.get("url") or "")
    item["availability"] = str(record.get("availability") or "")
    website.pop("price_status", None)
    website["price_provenance"] = {
        "seller": record.get("seller"),
        "url": record.get("url"),
        "confidence": record.get("confidence"),
        "fetched_at": record.get("fetched_at"),
        "matched_name": record.get("matched_name"),
        "matched_brand": record.get("matched_brand"),
        "matched_mpn": record.get("matched_mpn"),
    }
    return True


def enrich_presets(
    presets: list[dict], prices: dict, min_price_confidence: float = 0.8,
) -> tuple[list[dict], dict]:
    result = copy.deepcopy(presets)
    derived: Counter = Counter()
    priced = 0
    for item in result:
        derived.update(complete_physical_metadata(item))
        priced += int(synchronize_price(item, prices, min_price_confidence))
    optional_fields = ("qes", "cms_mm_per_n", "mms_g", "bl_tm", "le_mh", "xmax_mm", "pe_w")
    coverage = {
        field: sum(positive(item.get("driver", {}).get(field)) is not None for item in result)
        for field in optional_fields
    }
    report = {
        "rows": len(result),
        "derived": dict(sorted(derived.items())),
        "priced": priced,
        "unpriced": len(result) - priced,
        "driver_field_coverage": coverage,
        "size_coverage": sum(positive(item.get("size_in")) is not None for item in result),
    }
    return result, report


def atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--prices", type=Path, default=DEFAULT_PRICES)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--min-price-confidence", type=float, default=0.8)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    database = json.loads(args.database.read_text(encoding="utf-8"))
    price_payload = json.loads(args.prices.read_text(encoding="utf-8"))
    presets, report = enrich_presets(
        list(database.get("presets") or []),
        dict(price_payload.get("prices") or {}),
        float(args.min_price_confidence),
    )
    timestamp = dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()
    report.update({"generated_at": timestamp, "applied": bool(args.apply)})
    atomic_write(args.report, report)
    if args.apply:
        database["presets"] = presets
        database["usable_presets"] = len(presets)
        database["downloaded_at"] = timestamp
        atomic_write(args.database, database)
    print(
        f"rows={report['rows']} priced={report['priced']} unpriced={report['unpriced']} "
        f"derived={report['derived']} applied={report['applied']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
