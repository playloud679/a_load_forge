"""Offline, exhaustive catalog audit; never repairs values inferred from plausibility."""
import json
import math
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ["catalog_proprietario.json", "manufacturer_drivers.json", "catalog_lsdb.json",
         "catalog_vituixcad.json", "catalog_speakerboxlite.json",
         "catalog_ztzaudio_lf_ferrite_presets.json"]


def declared_sizes(row):
    """Independent nominal evidence; never infer nominal size from Sd/model digits."""
    sizes = []
    spec = row.get("published_specs", {}) or {}
    value = spec.get("nominal_diameter_in")
    if isinstance(value, (int, float)) and math.isfinite(value) and value > 0:
        sizes.append((float(value), "published_specs.nominal_diameter_in"))
        return sizes
    for field in ("model", "name"):
        title = str(row.get(field, ""))
        # A voice-coil dimension is not a cone/frame diameter. Flag ambiguous
        # titles for review rather than treating every quoted number as nominal.
        if re.search(r"voice.?coil|bobina|compression|tweeter|\d\s*[x×]\s*\d", title, re.I):
            continue
        if re.search(r"\d\s*[x×]|\b(?:vc|voice.?coil|bobina|cutout|frame|overall|diameter)\b", title, re.I):
            continue
        matches = list(re.finditer(r"(?<![\w.])(\d+(?:[.,]\d+)?(?:-\d+/\d+)?)\s*(?:[\"″]|inch(?:es)?\b|pollici\b)", title, re.I))
        if len(matches) != 1:
            continue
        for match in matches:
            token = match[1].replace(",", ".")
            size = float(token) if "-" not in token else float(token.split("-")[0]) + float(token.split("-")[1].split("/")[0]) / float(token.split("-")[1].split("/")[1])
            if 0.5 <= size <= 40:
                sizes.append((size, field))
    return sorted(set(sizes))


def audit(row):
    d = row.get("driver", {})
    meta = row.get("website_fields", {}) or {}
    derived = set(meta.get("derived_fields", [])) | set(meta.get("derivations", {}))
    findings = []

    def flag(code, evidence):
        findings.append({"code": code, "evidence": evidence})

    def num(key):
        value = d.get(key)
        return float(value) if isinstance(value, (int, float)) and math.isfinite(value) else None

    for key in ("fs_hz", "vas_l", "sd_cm2", "re_ohm", "qts", "qms"):
        if num(key) is None or num(key) <= 0:
            flag("invalid_required", key)
    fs, vas, sd, re, qt, qm = [num(k) for k in ("fs_hz", "vas_l", "sd_cm2", "re_ohm", "qts", "qms")]
    if qt and qm and qm <= qt:
        flag("invalid_q_order", {"qts": qt, "qms": qm})

    def identity(name, keys, actual, expected):
        if actual and expected and actual > 0 and expected > 0:
            ratio = actual / expected
            if abs(math.log(ratio)) > math.log(1.15):
                flag(name, {"actual": actual, "expected": expected, "ratio": ratio,
                            "derived_inputs": sorted(set(keys) & derived)})

    qe, cms, mms, bl = [num(k) for k in ("qes", "cms_mm_per_n", "mms_g", "bl_tm")]
    if qm and qe and qm > 0 and qe > 0:
        identity("q_identity", ["qts", "qms", "qes"], qt, qm * qe / (qm + qe))
    if cms and mms and cms > 0 and mms > 0:
        identity("fs_identity", ["fs_hz", "cms_mm_per_n", "mms_g"], fs,
                 1 / (2 * math.pi * math.sqrt(cms * mms * 1e-6)))
    if cms and sd and cms > 0 and sd > 0:
        identity("vas_identity", ["vas_l", "cms_mm_per_n", "sd_cm2"], vas,
                 1.18 * 344**2 * cms * (sd / 10000)**2)
    if fs and mms and re and bl and bl > 0:
        identity("motor_identity", ["qes", "fs_hz", "mms_g", "re_ohm", "bl_tm"], qe,
                 2 * math.pi * fs * mms / 1000 * re / bl**2)
    size = row.get("size_in")
    for nominal, source in declared_sizes(row):
        if isinstance(size, (int, float)) and abs(size - nominal) > 0.15:
            flag("declared_size_conflict", {"declared_in": nominal, "stored_in": size, "source": source})
        if sd and sd > 0:
            ratio = math.sqrt(4 * sd / math.pi) / (nominal * 2.54)
            if not 0.70 <= ratio <= 1.15:
                flag("declared_size_sd_mismatch", {"declared_in": nominal, "sd_cm2": sd,
                     "source": source, "diameter_ratio": ratio})
    if isinstance(size, (int, float)) and size > 0 and sd and sd > 0:
        ratio = math.sqrt(4 * sd / math.pi) / (size * 2.54)
        if not 0.70 <= ratio <= 1.15:
            flag("size_sd_mismatch", {"size_in": size, "sd_cm2": sd, "diameter_ratio": ratio})
    corrections = meta.get("field_corrections", {})
    if "size_in" in corrections:
        flag("size_correction_requires_source_review", corrections["size_in"])
    for key, measurement in (meta.get("raw_measurements", {}) or {}).items():
        if key not in d or not isinstance(measurement, dict):
            continue
        unit = str(measurement.get("unit", "")).strip().lower()
        if not unit and key in ("vas_l", "sd_cm2", "mms_g", "cms_mm_per_n", "xmax_mm"):
            flag("missing_source_unit", {"field": key, "raw": measurement.get("raw_value"), "stored": d[key]})
        factors = {"vas_l": {"cu ft": 28.316846592, "ft3": 28.316846592, "m3": 1000},
                   "sd_cm2": {"sq in": 6.4516, "in2": 6.4516, "m2": 10000},
                   "xmax_mm": {"in": 25.4}, "mms_g": {"kg": 1000}}
        if unit in factors.get(key, {}):
            try:
                expected = float(measurement["raw_value"]) * factors[key][unit]
                before = len(findings)
                identity("source_unit_conversion", [key], num(key), expected)
                if len(findings) > before:
                    findings[-1]["evidence"]["field"] = key
            except (ValueError, KeyError, TypeError):
                flag("unreadable_source_value", {"field": key, "measurement": measurement})
    if derived:
        flag("derived_values_not_independent_validation", sorted(derived))
    return findings


def main():
    report = {"scope": "All rows in six local simulation catalogs; no sampling, no cloud access",
              "policy": "Flags are review candidates, not proof of errors. No automatic data mutations. Identity tolerance 15%; size ratio 0.70–1.15. Derived values cannot validate their inputs.",
              "catalogs": {}, "findings": []}
    for filename in FILES:
        rows = json.loads((ROOT / "data" / filename).read_text())["presets"]
        if isinstance(rows, dict):
            rows = list(rows.values())
        counts = Counter()
        affected = 0
        for index, row in enumerate(rows):
            issues = audit(row)
            counts.update(x["code"] for x in issues)
            actionable = [x for x in issues if x["code"] != "derived_values_not_independent_validation"]
            affected += bool(actionable)
            if issues:
                report["findings"].append({"catalog": filename, "index": index,
                    "name": row.get("name", row.get("model")), "url": row.get("url"), "issues": issues})
        report["catalogs"][filename] = {"rows": len(rows), "rows_requiring_review": affected, "counts": dict(counts)}
    output = ROOT / "data" / "catalog_consistency_audit.json"
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report["catalogs"], indent=2))


if __name__ == "__main__":
    main()
