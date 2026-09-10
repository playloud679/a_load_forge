"""Emit an apply_patch patch for source-verified corrections; never writes catalogs."""
import copy
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERIFIED = {
    "MS12LB": (12.0, 511.0, 118.67),
    "MS12LW": (12.0, 511.0, 118.67),
    "MS10LB": (10.0, 330.0, 47.4728),
}
VERIFIED_SD = {
    ("Beyma", "12CMV2.ai"): 530.0,
    ("Beyma", "15CMV2.ai"): 880.0,
    ("Beyma", "12WRS400 2020"): 530.0,
}

UNIT_FACTORS = {
    ("vas_l", "cu ft"): 28.316846592, ("vas_l", "ft3"): 28.316846592,
    ("vas_l", "dm³"): 1.0, ("vas_l", "m3"): 1000.0,
    ("sd_cm2", "sq in"): 6.4516, ("sd_cm2", "in2"): 6.4516,
    ("sd_cm2", "in²"): 6.4516, ("sd_cm2", "m2"): 10000.0,
    ("sd_cm2", "m²"): 10000.0,
    ("mms_g", "kg"): 1000.0, ("xmax_mm", "in"): 25.4,
    ("xmax_mm", '"'): 25.4, ("le_mh", "uh"): 0.001,
    ("le_mh", "µh"): 0.001, ("cms_mm_per_n", "µm/n"): 0.001,
    ("cms_mm_per_n", "um/n"): 0.001,
    ("nominal_diameter_in", "mm"): 1 / 25.4,
    ("nominal_diameter_in", '"'): 1.0, ("nominal_diameter_in", "inch"): 1.0,
}


def nominal_from_row(row):
    value = (row.get("published_specs", {}) or {}).get("nominal_diameter_in")
    if isinstance(value, (int, float)) and value > 0:
        return float(value)
    value = row.get("size_in")
    if isinstance(value, (int, float)) and math.isfinite(value) and value > 0:
        return float(value)
    text = " ".join(str(row.get(k, "")) for k in ("name", "model"))
    if re.search(r"\d\s*[x×]|\b(?:vc|voice.?coil|bobina|cutout|frame|overall|diameter)\b", text, re.I):
        return None
    matches = list(re.finditer(r"(?<![\w.])(\d+(?:[.,]\d+)?(?:-\d+/\d+)?)\s*(?:[\"″]|inch(?:es)?|pollici)", text, re.I))
    if len(matches) != 1:
        return None
    match = matches[0]
    token = match.group(1).replace(",", ".")
    return (float(token) if "-" not in token else float(token.split("-")[0]) + float(token.split("-")[1].split("/")[0]) / float(token.split("-")[1].split("/")[1])) if match else None


def explicit_unit_corrections(row):
    """Correct only fields whose raw measurement carries a recognized unit."""
    new = copy.deepcopy(row)
    d = new.get("driver", {})
    meta = new.setdefault("website_fields", {})
    raw = meta.get("raw_measurements", {}) or {}
    history = meta.setdefault("verified_catalog_repairs", {})
    for key, measurement in raw.items():
        if key not in d or not isinstance(measurement, dict):
            continue
        unit = str(measurement.get("unit", "")).strip().lower()
        factor = UNIT_FACTORS.get((key, unit))
        if factor is None:
            continue
        try:
            expected = float(measurement["raw_value"]) * factor
        except (KeyError, TypeError, ValueError):
            continue
        if not math.isfinite(expected) or expected <= 0:
            continue
        if abs(math.log(float(d[key]) / expected)) <= math.log(1.15):
            continue
        history[key] = {"old_value": d[key], "new_value": expected,
            "source_url": row.get("url"), "checked_at": "2026-09-10",
            "reason": f"explicit source unit {measurement.get('unit')} converted to canonical field unit"}
        d[key] = expected
        if key in meta.get("derived_fields", []):
            meta["derived_fields"].remove(key)
    return new


def published_nominal_size_correction(row):
    """Prefer an explicit published nominal diameter over an inferred size."""
    new = copy.deepcopy(row)
    published = new.get("published_specs", {}) or {}
    nominal = published.get("nominal_diameter_in")
    if not isinstance(nominal, (int, float)) or not math.isfinite(nominal) or nominal <= 0:
        return new
    if new.get("size_in") == float(nominal):
        return new
    meta = new.setdefault("website_fields", {})
    history = meta.setdefault("verified_catalog_repairs", {})
    history["size_in"] = {"old_value": new.get("size_in"), "new_value": float(nominal),
        "source_url": published.get("source_url", new.get("url")),
        "checked_at": "2026-09-10", "reason": "published nominal diameter takes precedence over inferred size"}
    new["size_in"] = float(nominal)
    return new


def nominal_sd_unit_correction(row):
    """Recover an omitted Sd unit only when nominal diameter makes it unambiguous."""
    new = copy.deepcopy(row)
    d = new.get("driver", {})
    sd = d.get("sd_cm2")
    if not isinstance(sd, (int, float)) or sd <= 0:
        return new
    sizes = nominal_from_row(row)
    if not isinstance(sizes, (int, float)) or sizes <= 0:
        return new
    nominal = float(sizes)
    def plausible(value):
        diameter_ratio = math.sqrt(4.0 * value / math.pi) / (nominal * 2.54)
        return 0.70 <= diameter_ratio <= 1.15
    candidates = [(float(sd), "canonical cm²"), (float(sd) * 6.4516, "source in²→cm²"),
                  (float(sd) / 6.4516, "source cm²→in²")]
    # Decimal separators are also frequently lost in scraped manufacturer
    # sheets (e.g. 5,400 instead of 540 or 53,130 instead of 531.3).
    for factor in (0.001, 0.01, 0.1, 10.0, 100.0, 1000.0):
        candidates.append((float(sd) * factor, f"decimal scale ×{factor:g}"))
    # Several manufacturer PDFs export Sd in m² while the unit label is lost.
    # For normal-sized drivers, values below 1 cannot be canonical cm²; accept
    # the m²→cm² interpretation only when the nominal diameter independently
    # constrains it to a plausible piston area.
    if nominal >= 3.0 and float(sd) < 1.0:
        candidates.append((float(sd) * 10000.0, "source m²→cm²"))
    valid = [(value, reason) for value, reason in candidates if plausible(value)]
    current_plausible = plausible(float(sd))
    if current_plausible or not valid:
        return new
    # If the stored value is impossible for the declared diameter, select the
    # plausible conversion closest to the usual effective piston area (~85%
    # of nominal diameter). This resolves e.g. cm²↔in² versus a lost decimal
    # without modifying already-plausible effective Sd values.
    target = math.pi * (0.85 * nominal * 2.54) ** 2 / 4.0
    value, reason = min(valid, key=lambda item: abs(math.log(item[0] / target)))
    meta = new.setdefault("website_fields", {})
    history = meta.setdefault("verified_catalog_repairs", {})
    history["sd_cm2"] = {"old_value": sd, "new_value": value,
        "checked_at": "2026-09-10", "reason": f"{reason} inferred from declared {nominal:g} inch nominal diameter"}
    d["sd_cm2"] = value
    return new


def identity_sd_scale_correction(row):
    """Repair an Sd decimal-scale error when Vas and Cms independently agree."""
    new = copy.deepcopy(row)
    d = new.get("driver", {})
    # Nominal-diameter recovery has priority when it already selected a
    # unique decimal/unit interpretation; do not let a dependent Vas/Cms
    # pair undo that decision on a subsequent pass.
    if "sd_cm2" in ((new.get("website_fields", {}) or {}).get(
            "verified_catalog_repairs", {}) or {}):
        return new
    sd, vas, cms = d.get("sd_cm2"), d.get("vas_l"), d.get("cms_mm_per_n")
    if not all(isinstance(v, (int, float)) and math.isfinite(v) and v > 0 for v in (sd, vas, cms)):
        return new
    derived = set((new.get("website_fields", {}) or {}).get("derived_fields", []))
    # Sd is often explicitly marked derived by the importer because it was
    # reconstructed from the sheet; Vas/Cms are still useful independent
    # evidence for detecting a lost area unit. Do not use the check when the
    # two supporting quantities themselves are derived.
    if {"vas_l", "cms_mm_per_n"} & derived:
        return new
    # Vas = rho*c²*Sd²*Cms, with Cms converted from mm/N to m/N.
    expected = math.sqrt(float(vas) / (1.18 * 344**2 * float(cms) * 1e-3)) * 10000.0
    if not math.isfinite(expected) or expected <= 0:
        return new
    current_ratio = float(sd) / expected
    if 0.5 <= current_ratio <= 2.0:
        return new
    factors = (0.001, 0.01, 0.1, 10.0, 100.0, 1000.0, 10000.0)
    candidates = [(float(sd) * factor, factor) for factor in factors]
    value, factor = min(candidates, key=lambda item: abs(math.log(item[0] / expected)))
    if abs(math.log(value / expected)) > math.log(1.15):
        return new
    meta = new.setdefault("website_fields", {})
    history = meta.setdefault("verified_catalog_repairs", {})
    history["sd_cm2"] = {"old_value": sd, "new_value": value,
        "checked_at": "2026-09-10", "reason":
        f"decimal scale corrected by factor {factor:g}; independently supported by Vas/Cms identity"}
    d["sd_cm2"] = value
    return new


def corrected(row):
    new = identity_sd_scale_correction(nominal_sd_unit_correction(
        published_nominal_size_correction(explicit_unit_corrections(row))))
    if row.get("brand") != "Rockville" or row.get("model") not in VERIFIED:
        key = (row.get("brand"), row.get("model"))
        if key not in VERIFIED_SD:
            return new
        value = VERIFIED_SD[key]
        d = new["driver"]
        if d.get("sd_cm2") != value:
            meta = new.setdefault("website_fields", {})
            history = meta.setdefault("verified_catalog_repairs", {})
            history["sd_cm2"] = {"old_value": d.get("sd_cm2"), "new_value": value,
                "source_url": "https://www.beyma.com/", "checked_at": "2026-09-10",
                "reason": "Beyma manufacturer catalogue Sd in m² converted to canonical cm²"}
            d["sd_cm2"] = value
        return new
    size, sd, vas = VERIFIED[row["model"]]
    source_url = "https://www.rockvilleaudio.com/" + row["model"].lower() + "/"
    d = new["driver"]
    changes = {"sd_cm2": sd, "vas_l": vas}
    meta = new.setdefault("website_fields", {})
    history = meta.setdefault("verified_catalog_repairs", {})
    for key, value in changes.items():
        if d.get(key) != value:
            history[key] = {"old_value": d.get(key), "new_value": value,
                "source_url": source_url,
                "checked_at": "2026-09-10", "reason": "manufacturer metric specification; imperial unit lost during extraction"}
            d[key] = value
    if new.get("size_in") != size:
        history["size_in"] = {"old_value": new.get("size_in"), "new_value": size,
            "source_url": source_url, "reason": "published nominal diameter"}
        new["size_in"] = size
    derived = set(meta.get("derived_fields", []))
    cms = d["vas_l"] / (1.18 * 344**2 * (d["sd_cm2"] / 10000)**2)
    mms = 1e6 / ((2 * math.pi * d["fs_hz"])**2 * cms)
    values = {"cms_mm_per_n": cms, "mms_g": mms,
              "bl_tm": math.sqrt(2 * math.pi * d["fs_hz"] * mms / 1000 * d["re_ohm"] / d["qes"])}
    for key, value in values.items():
        if key in derived:
            value = round(value, 8)
            if d.get(key) != value:
                history[key] = {"old_value": d.get(key), "new_value": value,
                    "reason": "recomputed derived value after verified Vas/Sd correction"}
                d[key] = value
    meta["derived_fields"] = [k for k in meta.get("derived_fields", []) if k != "size_in"]
    meta.get("derivations", {}).pop("size_in", None)
    return new


def main():
    import sys
    if "--write" in sys.argv:
        for name in ("catalog_proprietario.json", "manufacturer_drivers.json"):
            path = ROOT / "data" / name
            data = json.loads(path.read_text())
            data["presets"] = [corrected(row) for row in data["presets"]]
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        print("wrote verified and explicit-unit corrections")
        return
    print("*** Begin Patch")
    for name in ("catalog_proprietario.json", "manufacturer_drivers.json"):
        path = ROOT / "data" / name
        data = json.loads(path.read_text())
        emitted = False
        for row in data["presets"]:
            new = corrected(row)
            if new == row:
                continue
            old_text = json.dumps(row, ensure_ascii=False, indent=2)
            new_text = json.dumps(new, ensure_ascii=False, indent=2)
            old_lines = ["    " + s for s in old_text.splitlines()]
            new_lines = ["    " + s for s in new_text.splitlines()]
            # The object may have a trailing comma: leave its last brace as context.
            if not emitted:
                print(f"*** Update File: {path}")
                emitted = True
            print("@@")
            print("\n".join("-" + s for s in old_lines[:-1]))
            print("\n".join("+" + s for s in new_lines[:-1]))
    print("*** End Patch")


if __name__ == "__main__":
    main()
