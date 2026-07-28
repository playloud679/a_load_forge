#!/usr/bin/env python3
"""Import physically consistent LF records from Speaker Box Lite's public API."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_URL = "https://speakerboxlite.com/api/v1/speakers"
DEFAULT_OUTPUT = ROOT / "data" / "speakerboxlite_drivers.json"
DEFAULT_EXISTING = (
    ROOT / "data" / "manufacturer_drivers.json",
    ROOT / "data" / "loudspeaker_database_drivers.json",
    ROOT / "data" / "vituixcad_drivers.json",
)
USER_AGENT = (
    "LoadForge-SpeakerBoxLite-Importer/1.0 "
    "(+https://github.com/playloud679/a_load_forge)"
)

# The API contains community-entered rows and several historical unit
# conventions. These bounds intentionally describe LF enclosure drivers,
# rather than every transducer type present in the upstream database.
RANGES = {
    "fs_hz": (5.0, 500.0),
    "vas_l": (0.01, 5_000.0),
    "qts": (0.05, 2.0),
    "qms": (0.1, 100.0),
    "qes": (0.05, 20.0),
    "re_ohm": (0.2, 50.0),
    "sd_cm2": (1.0, 5_000.0),
    "le_mh": (0.0, 100.0),
    "xmax_mm": (0.0, 100.0),
    "pe_w": (0.0, 20_000.0),
    "mms_g": (0.001, 5_000.0),
    "cms_mm_per_n": (0.000001, 100.0),
    "bl_tm": (0.0, 300.0),
}
Q_IDENTITY_TOLERANCE = 0.05
SD_PHYSICS_TOLERANCE = 0.25
AIR_DENSITY_KG_M3 = 1.2
SOUND_SPEED_M_S = 343.0

BRAND_ALIASES = {
    "18sound": "eighteensound",
    "eighteensound": "eighteensound",
    "bcspeaker": "bc",
    "bcspeakers": "bc",
    "bc": "bc",
    "deafbonce": "alphard",
    "alphard": "alphard",
    "faital": "faitalpro",
    "faitalpro": "faitalpro",
    "jlaudio": "jlaudio",
    "skaraudio": "skar",
    "skar": "skar",
}


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()


def number(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def bounded(key: str, value: float | None) -> float | None:
    if value is None:
        return None
    low, high = RANGES[key]
    return value if low <= value <= high else None


def normalized(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def canonical_brand(value: object) -> str:
    key = normalized(value)
    return BRAND_ALIASES.get(key, key)


def identity(brand: object, model: object) -> tuple[str, str]:
    return canonical_brand(brand), normalized(model)


def load_existing_identities(paths: list[Path]) -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for path in paths:
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        for item in payload.get("presets", []):
            key = identity(item.get("brand"), item.get("model"))
            if all(key):
                found.add(key)
    return found


def fetch_rows(url: str, timeout_s: float, limit: int) -> list[dict]:
    query = urlencode(
        {"offset": 0, "limit": limit, "sort": "name", "order": "asc"}
    )
    request = Request(
        f"{url}?{query}",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with urlopen(request, timeout=timeout_s) as response:
        payload = json.load(response)
    if not isinstance(payload, list):
        raise ValueError("Speaker Box Lite API did not return a JSON list")
    return payload


def _sd_from_vas_cms(vas_l: float, cms_mm_per_n: float) -> float:
    """Return Sd in cm² from Vas and Cms using the compliance identity."""
    vas_m3 = vas_l / 1_000.0
    cms_m_per_n = cms_mm_per_n / 1_000.0
    sd_m2 = math.sqrt(
        vas_m3
        / (
            AIR_DENSITY_KG_M3
            * SOUND_SPEED_M_S**2
            * cms_m_per_n
        )
    )
    return sd_m2 * 10_000.0


def normalize_sd(
    raw_sd: float | None,
    *,
    diameter_in: float | None,
    vas_l: float,
    cms_mm_per_n: float | None,
) -> tuple[float | None, str, float | None]:
    """Resolve upstream Sd values entered as mm², cm² or m²."""
    if raw_sd is None or raw_sd <= 0.0:
        return None, "", None
    nominal_area = (
        math.pi * (diameter_in * 2.54) ** 2 / 4.0
        if diameter_in is not None and diameter_in > 0.0
        else None
    )
    candidates = (
        (raw_sd / 100.0, "mm2"),
        (raw_sd, "cm2"),
        (raw_sd * 10_000.0, "m2"),
    )
    plausible = [
        (value, unit)
        for value, unit in candidates
        if RANGES["sd_cm2"][0] <= value <= RANGES["sd_cm2"][1]
        and (
            nominal_area is None
            or 0.08 <= value / nominal_area <= 1.2
        )
    ]
    if not plausible:
        return None, "", None

    derived = (
        _sd_from_vas_cms(vas_l, cms_mm_per_n)
        if cms_mm_per_n is not None and cms_mm_per_n > 0.0
        else None
    )
    target = derived or (nominal_area * 0.6 if nominal_area else plausible[0][0])
    value, unit = min(
        plausible,
        key=lambda candidate: abs(math.log(candidate[0] / target)),
    )
    if (
        derived is not None
        and abs(value - derived) / derived > SD_PHYSICS_TOLERANCE
    ):
        return None, "", derived
    return value, unit, derived


def row_to_preset(
    row: dict,
    *,
    source_url: str,
    imported_at: str,
) -> tuple[dict | None, str]:
    brand = str(row.get("manufName") or "").strip()
    model = re.sub(r"\s+", " ", str(row.get("name") or "")).strip()
    if not brand or not model:
        return None, "missing identity"

    fs_hz = bounded("fs_hz", number(row.get("fs")))
    vas_l = bounded("vas_l", number(row.get("vas")))
    qts = bounded("qts", number(row.get("qts")))
    qms = bounded("qms", number(row.get("qms")))
    qes = bounded("qes", number(row.get("qes")))
    re_ohm = bounded("re_ohm", number(row.get("re")))
    required = (fs_hz, vas_l, qts, qms, qes, re_ohm)
    if any(value is None for value in required):
        return None, "missing or invalid simulation field"
    assert fs_hz is not None
    assert vas_l is not None
    assert qts is not None
    assert qms is not None
    assert qes is not None
    assert re_ohm is not None
    if qms <= qts or qes <= qts:
        return None, "invalid Q ordering"
    calculated_qts = qes * qms / (qes + qms)
    q_error = abs(calculated_qts - qts) / qts
    if q_error > Q_IDENTITY_TOLERANCE:
        return None, "Q identity mismatch"

    diameter_in = number(row.get("diam"))
    if diameter_in is not None and not 0.5 <= diameter_in <= 32.0:
        diameter_in = None
    cms = bounded("cms_mm_per_n", number(row.get("cms")))
    sd_cm2, sd_source_unit, sd_derived_cm2 = normalize_sd(
        number(row.get("sd")),
        diameter_in=diameter_in,
        vas_l=vas_l,
        cms_mm_per_n=cms,
    )
    if sd_cm2 is None:
        return None, "invalid or physically inconsistent Sd"

    optional = {
        "le_mh": bounded("le_mh", number(row.get("le"))),
        "xmax_mm": bounded("xmax_mm", number(row.get("xMax"))),
        "pe_w": bounded("pe_w", number(row.get("powerRMS"))),
        "mms_g": bounded("mms_g", number(row.get("mms"))),
        "cms_mm_per_n": cms,
        "bl_tm": bounded("bl_tm", number(row.get("bl"))),
    }
    driver = {
        "fs_hz": fs_hz,
        "vas_l": vas_l,
        "qts": qts,
        "qms": qms,
        "qes": qes,
        "re_ohm": re_ohm,
        "sd_cm2": sd_cm2,
        **{key: value for key, value in optional.items() if value is not None},
    }
    text_id = str(row.get("textId") or "")
    return {
        "name": f"SBL: {brand} {model}",
        "brand": brand,
        "model": model,
        "size_in": diameter_in,
        "kind": "Loudspeaker driver",
        "url": f"https://speakerboxlite.com/subwoofers/{text_id}/specifications",
        "source": "Speaker Box Lite public database",
        "driver": {
            key: round(float(value), 8)
            for key, value in driver.items()
        },
        "website_fields": {
            "source": "Speaker Box Lite public API",
            "source_url": source_url,
            "imported_at": imported_at,
            "upstream_id": row.get("id"),
            "upstream_text_id": text_id,
            "upstream_checked": row.get("checked"),
            "upstream_rating": row.get("rating"),
            "record_updated": row.get("dateEdit"),
            "qts_from_qes_qms": round(calculated_qts, 8),
            "q_identity_relative_error": round(q_error, 8),
            "sd_raw": row.get("sd"),
            "sd_raw_unit_interpreted": sd_source_unit,
            "sd_from_vas_cms_cm2": (
                round(sd_derived_cm2, 8)
                if sd_derived_cm2 is not None
                else None
            ),
        },
    }, ""


def import_database(
    rows: list[dict],
    *,
    source_url: str,
    existing_identities: set[tuple[str, str]],
) -> tuple[list[dict], dict]:
    imported_at = utc_now()
    accepted: dict[tuple[str, str], dict] = {}
    rejected: dict[str, int] = {}
    duplicates_existing = 0
    duplicates_source = 0
    for row in rows:
        preset, reason = row_to_preset(
            row,
            source_url=source_url,
            imported_at=imported_at,
        )
        if preset is None:
            rejected[reason] = rejected.get(reason, 0) + 1
            continue
        key = identity(preset["brand"], preset["model"])
        if key in existing_identities:
            duplicates_existing += 1
            continue
        if key in accepted:
            duplicates_source += 1
            old = accepted[key]
            if len(preset["driver"]) <= len(old["driver"]):
                continue
        accepted[key] = preset
    presets = sorted(
        accepted.values(),
        key=lambda item: (item["brand"].casefold(), item["model"].casefold()),
    )
    return presets, {
        "source_rows": len(rows),
        "accepted": len(presets),
        "duplicates_existing": duplicates_existing,
        "duplicates_source": duplicates_source,
        "rejected": rejected,
        "brands": len({item["brand"].strip() for item in presets}),
    }


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Import physically validated LF records from the public "
            "Speaker Box Lite API as a separate Load Forge tier."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="Use a previously downloaded JSON list instead of the network.",
    )
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--existing",
        type=Path,
        action="append",
        help="Catalog to deduplicate against; repeat as needed.",
    )
    parser.add_argument("--limit", type=int, default=10_000)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    rows = (
        json.loads(args.input.read_text(encoding="utf-8"))
        if args.input
        else fetch_rows(args.url, args.timeout, args.limit)
    )
    if not isinstance(rows, list):
        raise ValueError("input JSON must contain a list of driver records")
    existing_paths = args.existing or list(DEFAULT_EXISTING)
    presets, stats = import_database(
        rows,
        source_url=args.url,
        existing_identities=load_existing_identities(existing_paths),
    )
    payload = {
        "source": "Speaker Box Lite public database",
        "source_url": args.url,
        "downloaded_at": utc_now(),
        "redistribution_note": (
            "Third-party community database. Keep as a separate optional "
            "catalog tier and review upstream terms before public redistribution."
        ),
        "validation": {
            "q_identity_relative_tolerance": Q_IDENTITY_TOLERANCE,
            "sd_vas_cms_relative_tolerance": SD_PHYSICS_TOLERANCE,
            "sd_unit_candidates": ["mm2", "cm2", "m2"],
        },
        "usable_presets": len(presets),
        "stats": stats,
        "presets": presets,
    }
    if not args.dry_run:
        atomic_write_json(args.output, payload)
    print(json.dumps(stats, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
