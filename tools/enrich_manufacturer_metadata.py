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
    import crawl_thiele_small as crawl_tools
    import enrich_driver_prices as price_tools
except ModuleNotFoundError:  # Imported as tools.enrich_manufacturer_metadata.
    from tools import crawl_thiele_small as crawl_tools
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
    (0.75, 2.5), (1.0, 5.0), (1.5, 8.0), (2.0, 13.0), (2.5, 22.0),
    (3.0, 32.0), (3.5, 38.0), (4.0, 50.0), (4.5, 65.0),
    (5.0, 80.0), (5.25, 90.0), (5.5, 100.0), (6.0, 115.0),
    (6.5, 132.0), (7.0, 150.0), (7.5, 158.0), (8.0, 220.0),
    (8.5, 240.0), (9.0, 255.0), (9.5, 280.0), (10.0, 350.0),
    (11.0, 410.0), (12.0, 530.0), (13.0, 610.0), (13.5, 700.0),
    (14.0, 750.0), (15.0, 855.0), (16.0, 950.0), (18.0, 1210.0),
    (19.0, 1450.0), (21.0, 1680.0), (24.0, 2200.0),
)

# Values rechecked against manufacturer product pages/datasheets during the
# nominal-size/Sd audit.  These override damaged text extraction, while the
# original raw value remains attached to each record for traceability.
VERIFIED_DRIVER_CORRECTIONS = (
    {
        "brand": "SB Acoustics",
        "model_prefix": "SB17NRXC35-4",
        "fields": {"sd_cm2": 118.0, "cms_mm_per_n": 1.78, "size_in": 6.0},
        "source_url": "https://sbacoustics.com/product/6in-sb17nrxc35-4/",
    },
    {
        "brand": "SB Acoustics",
        "model_prefix": "SB34NRX75-6",
        "fields": {"sd_cm2": 508.0, "cms_mm_per_n": 0.71, "size_in": 12.0},
        "source_url": "https://sbacoustics.com/product/12-sb34nrx75-6-norex/",
    },
    {
        "brand": "SB Acoustics",
        "model_prefix": "SB34SWNRX-S75-6",
        "fields": {"sd_cm2": 508.0, "size_in": 12.0},
        "source_url": "https://sbacoustics.com/product/12in-sb34swnrx-s75-6-norex/",
    },
    {
        "brand": "Dayton Audio",
        "model_prefix": "PA460-8",
        "fields": {"sd_cm2": 1241.1, "cms_mm_per_n": 0.19, "size_in": 18.0},
        "source_url": "https://www.daytonaudio.com/product/78/pa460-8-18-pro-woofer-8-ohm",
    },
    {
        "brand": "Tang Band",
        "model_prefix": "W8-1772",
        "fields": {"sd_cm2": 220.0, "size_in": 8.0},
        "source_url": "https://tb-speaker.com/zh-tw/products/w8-1772",
    },
    {
        "brand": "Markaudio",
        "model_prefix": "Alpair 10P",
        "fields": {"size_in": 5.0},
        "source_url": "https://www.markaudio.com/online_shop/archive/alpair-10p/",
    },
    {
        "brand": "Beyma",
        "model_prefix": "4FR40",
        "fields": {"sd_cm2": 55.0, "cms_mm_per_n": 0.668, "size_in": 4.0},
        "source_url": "https://www.beyma.com/en/products/c/full-range/104FR408/loudspeaker-4fr40-8-oh/",
    },
    {
        "brand": "Eminence",
        "model_prefix": "Eminence Alpha-6CBMRA",
        "fields": {"sd_cm2": 126.7, "cms_mm_per_n": 0.02},
        "source_url": "https://eminence.com/products/alpha_6cbmra",
    },
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
    return crawl_tools.first_inch_size(value)


def effective_diameter_in(sd_cm2: float) -> float:
    """Return the circular effective-piston diameter represented by Sd."""
    sd = positive(sd_cm2)
    if sd is None:
        raise ValueError("Sd must be positive")
    return math.sqrt(4.0 * sd / math.pi) / 2.54


def _metadata_texts(item: dict) -> list[str]:
    website = item.get("website_fields") or {}
    values = [
        website.get("catalog_name"),
        website.get("product_title"),
        website.get("title"),
        website.get("raw_model_title"),
        item.get("name"),
        item.get("model"),
    ]
    return [str(value) for value in values if str(value or "").strip()]


def _explicit_size_metadata(item: dict) -> tuple[float | None, str]:
    for text in _metadata_texts(item):
        size = explicit_size_from_text(text)
        if size is not None:
            return size, text
    return None, ""


def _has_compound_dimensions(item: dict) -> bool:
    patterns = (
        re.compile(
            r"(?:inch(?:es)?|in\.?|[\"″])\s*[x×]\s*"
            r"\d+(?:[.,]\d+)?(?:\s*[- ]\s*\d+\s*/\s*\d+)?\s*"
            r"(?:inch(?:es)?|in\.?|[\"″])?",
            re.I,
        ),
        re.compile(
            r"\d+(?:[.,]\d+)?\s*[x×]\s*\d+(?:[.,]\d+)?\s*"
            r"(?:inch(?:es)?|in\.?|[\"″])",
            re.I,
        ),
    )
    return any(
        pattern.search(text)
        for text in _metadata_texts(item)
        for pattern in patterns
    )


def _diameter_is_plausible(sd_cm2: float, size_in: float) -> bool:
    ratio = effective_diameter_in(sd_cm2) / float(size_in)
    return 0.70 <= ratio <= 1.15


def _record_correction(
    item: dict,
    field: str,
    old_value: object,
    new_value: object,
    reason: str,
    source_url: str = "",
) -> None:
    website = item.setdefault("website_fields", {})
    corrections = dict(website.get("field_corrections") or {})
    corrections[field] = {
        "old_value": old_value,
        "new_value": new_value,
        "reason": reason,
        **({"source_url": source_url} if source_url else {}),
    }
    website["field_corrections"] = corrections


def _set_verified_field(
    item: dict,
    field: str,
    value: float,
    source_url: str,
) -> bool:
    target = item if field == "size_in" else item.setdefault("driver", {})
    old = target.get(field)
    if positive(old) is not None and math.isclose(float(old), value, rel_tol=0.0, abs_tol=1e-9):
        return False
    target[field] = value
    _record_correction(
        item, field, old, value, "manufacturer value rechecked during Sd/nominal-size audit",
        source_url,
    )
    website = item.setdefault("website_fields", {})
    provenance = dict(website.get("field_provenance") or {})
    provenance[field] = {
        "source": "Manufacturer Sd/nominal-size audit",
        "source_url": source_url,
        "value": value,
    }
    website["field_provenance"] = provenance
    derived_fields = list(website.get("derived_fields") or [])
    if field in derived_fields:
        derived_fields.remove(field)
        website["derived_fields"] = derived_fields
    derivations = dict(website.get("derivations") or {})
    derivations.pop(field, None)
    website["derivations"] = derivations
    return True


def apply_verified_driver_corrections(item: dict) -> Counter:
    counts: Counter = Counter()
    brand = str(item.get("brand") or "").casefold()
    model = str(item.get("model") or "").casefold()
    for correction in VERIFIED_DRIVER_CORRECTIONS:
        if brand != str(correction["brand"]).casefold():
            continue
        if not model.startswith(str(correction["model_prefix"]).casefold()):
            continue
        source_url = str(correction["source_url"])
        for field, value in dict(correction["fields"]).items():
            if _set_verified_field(item, field, float(value), source_url):
                counts[field] += 1
        break
    return counts


def _mechanical_sd_cm2(item: dict) -> float | None:
    """Derive Sd from independent published Vas and mechanical compliance."""
    driver = item.get("driver") or {}
    website = item.get("website_fields") or {}
    derived = set(website.get("derived_fields") or [])
    vas = positive(driver.get("vas_l"))
    if vas is None or "vas_l" in derived:
        return None
    cms = None
    fs = positive(driver.get("fs_hz"))
    mms = positive(driver.get("mms_g"))
    if fs is not None and mms is not None and "mms_g" not in derived:
        cms = 1_000_000.0 / ((2.0 * math.pi * fs) ** 2 * mms)
    elif "cms_mm_per_n" not in derived:
        cms = positive(driver.get("cms_mm_per_n"))
    if cms is None:
        return None
    vas_m3 = vas / 1000.0
    cms_m_per_n = cms / 1000.0
    return math.sqrt(
        vas_m3 / (cms_m_per_n * RHO_AIR_KG_M3 * SPEED_OF_SOUND_M_S**2)
    ) * 10_000.0


def _nominal_size_hint(item: dict) -> tuple[float | None, bool]:
    explicit, _ = _explicit_size_metadata(item)
    if explicit is not None:
        return explicit, True
    current = positive(item.get("size_in"))
    if current is not None:
        return current, False
    for text in _metadata_texts(item):
        inferred = crawl_tools.infer_size_in(text)
        if inferred is not None:
            return inferred, False
    return None, False


def _refresh_sd_dependents(item: dict) -> None:
    """Recompute only fields whose recorded derivation depends on corrected Sd."""
    driver = item.get("driver") or {}
    derivations = (item.get("website_fields") or {}).get("derivations") or {}
    cms_formula = str((derivations.get("cms_mm_per_n") or {}).get("formula") or "")
    if "Vas" in cms_formula and all(
        positive(driver.get(field)) is not None for field in ("vas_l", "sd_cm2")
    ):
        sd_m2 = float(driver["sd_cm2"]) / 10_000.0
        driver["cms_mm_per_n"] = (
            (float(driver["vas_l"]) / 1000.0)
            / (RHO_AIR_KG_M3 * SPEED_OF_SOUND_M_S**2 * sd_m2**2)
            * 1000.0
        )
    mms_formula = str((derivations.get("mms_g") or {}).get("formula") or "")
    if "Cms" in mms_formula and all(
        positive(driver.get(field)) is not None
        for field in ("fs_hz", "cms_mm_per_n")
    ):
        cms_m_per_n = float(driver["cms_mm_per_n"]) / 1000.0
        driver["mms_g"] = (
            1.0 / ((2.0 * math.pi * float(driver["fs_hz"])) ** 2 * cms_m_per_n)
            * 1000.0
        )


def reconcile_sd_and_nominal_size(item: dict) -> Counter:
    """Repair safe unit/parse errors and flag unresolved size/Sd conflicts."""
    counts: Counter = Counter()
    counts.update(apply_verified_driver_corrections(item))
    driver = item.setdefault("driver", {})
    current_sd = positive(driver.get("sd_cm2"))
    size_hint, _ = _nominal_size_hint(item)
    mechanical_sd = _mechanical_sd_cm2(item)

    if current_sd is not None:
        raw_sd = ((item.get("website_fields") or {}).get("raw_measurements") or {}).get("sd_cm2")
        reparsed = None
        if isinstance(raw_sd, dict):
            reparsed = crawl_tools.convert_measurement(
                "sd_cm2", raw_sd.get("raw_value"), str(raw_sd.get("unit") or "")
            )
        raw_matches_physics = (
            mechanical_sd is not None
            and abs(reparsed / mechanical_sd - 1.0) <= 0.12
            if reparsed is not None
            else False
        )
        raw_is_better = (
            reparsed is not None
            and not math.isclose(reparsed, current_sd, rel_tol=1e-6)
            and (
                (
                    size_hint is not None
                    and
                    _diameter_is_plausible(reparsed, size_hint)
                    and not _diameter_is_plausible(current_sd, size_hint)
                )
                or (size_hint is None and raw_matches_physics)
            )
        )
        if raw_is_better:
            old = current_sd
            driver["sd_cm2"] = round(float(reparsed), 8)
            current_sd = float(driver["sd_cm2"])
            _record_correction(
                item, "sd_cm2", old, current_sd,
                "raw Sd reparsed with decimal/thousands separator and unit",
            )
            counts["sd_cm2"] += 1

    if current_sd is not None and mechanical_sd is not None:
        if size_hint is None or not _diameter_is_plausible(current_sd, size_hint):
            decade_candidates = [current_sd * 10.0**power for power in range(-3, 4) if power]
            scaled = min(
                decade_candidates,
                key=lambda candidate: abs(math.log(candidate / mechanical_sd)),
            )
            close_to_physics = abs(scaled / mechanical_sd - 1.0) <= 0.12
            fits_size = size_hint is None or _diameter_is_plausible(scaled, size_hint)
            if close_to_physics and fits_size:
                old = current_sd
                driver["sd_cm2"] = round(scaled, 8)
                current_sd = float(driver["sd_cm2"])
                _record_correction(
                    item, "sd_cm2", old, current_sd,
                    "restored missing decimal decade; corroborated by Fs/Vas/Mms",
                )
                counts["sd_cm2"] += 1

    if counts["sd_cm2"]:
        _refresh_sd_dependents(item)

    website = item.setdefault("website_fields", {})
    explicit_size, explicit_text = _explicit_size_metadata(item)
    current_size = positive(item.get("size_in"))
    if explicit_size is not None and (
        current_size is None
        or not math.isclose(current_size, explicit_size, rel_tol=0.0, abs_tol=0.01)
    ):
        item["size_in"] = explicit_size
        _record_correction(
            item, "size_in", current_size, explicit_size,
            f"parsed complete nominal inch fraction from product metadata: {explicit_text}",
        )
        _mark_derivation(item, "size_in", "nominal size parsed from product metadata", 1.0)
        counts["size_in"] += 1
        current_size = explicit_size
    if explicit_size is not None:
        provenance = dict(website.get("field_provenance") or {})
        size_provenance = provenance.get("size_in") or {}
        if (
            size_provenance.get("source") == "Manufacturer Sd/nominal-size audit"
            and not math.isclose(
                float(size_provenance.get("value") or 0.0),
                explicit_size,
                rel_tol=0.0,
                abs_tol=0.01,
            )
        ):
            provenance.pop("size_in", None)
            website["field_provenance"] = provenance

    current_sd = positive(driver.get("sd_cm2"))
    size_formula = str(
        ((website.get("derivations") or {}).get("size_in") or {}).get("formula")
        or ""
    )
    if (
        explicit_size is None
        and current_sd is not None
        and size_formula == "nominal frame class estimated from Sd"
    ):
        model_guess = next(
            (
                guess
                for text in _metadata_texts(item)
                if (guess := crawl_tools.infer_size_in(text, "", current_sd))
                is not None
            ),
            None,
        )
        if (
            model_guess is not None
            and (
                current_size is None
                or not math.isclose(current_size, model_guess, abs_tol=0.01)
            )
        ):
            item["size_in"] = model_guess
            _record_correction(
                item, "size_in", current_size, model_guess,
                "preferred Sd-compatible nominal size encoded in model",
            )
            _mark_derivation(
                item, "size_in",
                "nominal size inferred from compatible model prefix and Sd",
                0.9,
            )
            counts["size_in"] += 1
            current_size = model_guess
    if explicit_size is None and current_sd is not None:
        incompatible = (
            current_size is None
            or not _diameter_is_plausible(current_sd, current_size)
        )
        if incompatible:
            model_guess = next(
                (
                    guess
                    for text in _metadata_texts(item)
                    if (guess := crawl_tools.infer_size_in(text, "", current_sd))
                    is not None
                ),
                None,
            )
            if model_guess is not None:
                inferred_size, confidence = model_guess, 0.9
                formula = "nominal size inferred from compatible model prefix and Sd"
            else:
                inferred_size, confidence = nominal_size_from_sd(current_sd)
                formula = "nominal frame class estimated from Sd"
            item["size_in"] = inferred_size
            _record_correction(
                item, "size_in", current_size, inferred_size,
                "replaced incompatible model-number guess with Sd frame-class estimate",
            )
            _mark_derivation(item, "size_in", formula, confidence)
            counts["size_in"] += 1
            current_size = inferred_size

    conflict = (
        explicit_size is not None
        and current_sd is not None
        and not _has_compound_dimensions(item)
        and not _diameter_is_plausible(current_sd, explicit_size)
    )
    if conflict:
        newly_rejected = website.get("quality_status") != "rejected_size_sd_conflict"
        website["quality_status"] = "rejected_size_sd_conflict"
        website["quality_reason"] = (
            f"nominal {explicit_size:g} in versus Sd {current_sd:g} cm2 "
            f"(effective diameter {effective_diameter_in(current_sd):.2f} in)"
        )
        counts["rejected_size_sd_conflict"] += int(newly_rejected)
    elif website.get("quality_status") == "rejected_size_sd_conflict":
        website.pop("quality_status", None)
        website.pop("quality_reason", None)
    return counts


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
        model=str(item.get("part_number_override") or item.get("model") or ""),
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
        previous_provenance = website.pop("price_provenance", None)
        if isinstance(previous_provenance, dict):
            website["invalidated_price"] = {
                "reason": "cached retailer match no longer passes current identity checks",
                "previous": {
                    "price": item.pop("price", None),
                    "currency": item.pop("currency", None),
                    "price_url": item.pop("price_url", None),
                    "availability": item.pop("availability", None),
                    "provenance": previous_provenance,
                },
            }
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
    corrected: Counter = Counter()
    priced = 0
    for item in result:
        before_reconcile = set(
            (item.get("website_fields") or {}).get("derived_fields") or []
        )
        corrected.update(reconcile_sd_and_nominal_size(item))
        after_reconcile = set(
            (item.get("website_fields") or {}).get("derived_fields") or []
        )
        derived.update(after_reconcile - before_reconcile)
        derived.update(complete_physical_metadata(item))
        priced += int(synchronize_price(item, prices, min_price_confidence))
    optional_fields = ("qes", "cms_mm_per_n", "mms_g", "bl_tm", "le_mh", "xmax_mm", "pe_w")
    coverage = {
        field: sum(positive(item.get("driver", {}).get(field)) is not None for item in result)
        for field in optional_fields
    }
    correction_inventory: Counter = Counter(
        field
        for item in result
        for field in (
            (item.get("website_fields") or {}).get("field_corrections") or {}
        )
    )
    correction_inventory["rejected_size_sd_conflict"] = sum(
        (item.get("website_fields") or {}).get("quality_status")
        == "rejected_size_sd_conflict"
        for item in result
    )
    report = {
        "rows": len(result),
        "derived": dict(sorted(derived.items())),
        "corrected": dict(sorted(correction_inventory.items())),
        "changes_this_run": {
            field: count for field, count in sorted(corrected.items()) if count
        },
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
        database["usable_presets"] = sum(
            (item.get("website_fields") or {}).get("quality_status")
            != "rejected_size_sd_conflict"
            for item in presets
        )
        database["downloaded_at"] = timestamp
        atomic_write(args.database, database)
    print(
        f"rows={report['rows']} priced={report['priced']} unpriced={report['unpriced']} "
        f"derived={report['derived']} corrected={report['corrected']} "
        f"changes_this_run={report['changes_this_run']} "
        f"applied={report['applied']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
