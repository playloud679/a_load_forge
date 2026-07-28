#!/usr/bin/env python3
"""Import the public VituixCAD online driver database as a separate tier."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import math
import re
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_URL = (
    "https://kimmosaunisto.net/Software/VituixCAD/VituixCAD_Drivers.txt"
)
DEFAULT_OUTPUT = ROOT / "data" / "vituixcad_drivers.json"
DEFAULT_MANUFACTURER = ROOT / "data" / "manufacturer_drivers.json"
DEFAULT_LSDB = ROOT / "data" / "loudspeaker_database_drivers.json"
USER_AGENT = (
    "LoadForge-VituixCAD-Importer/1.0 "
    "(+https://github.com/playloud679/a_load_forge)"
)

REQUIRED_COLUMNS = {
    "Manufacturer",
    "Model",
    "Type",
    "Size [in]",
    "Re [ohm]",
    "fs [Hz]",
    "Qms",
    "Qes",
    "Qts",
    "Mms [g]",
    "Cms [mm/N]",
    "Vas [l]",
    "Sd [cm2]",
    "BL [Tm]",
    "Pmax [W]",
    "Xmax [mm]",
    "Le [mH]",
}

BRAND_ALIASES = {
    "18sound": "18sound",
    "eighteensound": "18sound",
    "aespeakers": "acousticelegance",
    "acousticelegance": "acousticelegance",
    "bcspeaker": "bc",
    "bcspeakers": "bc",
    "jbl": "jbl",
    "jblprofessional": "jbl",
    "phl": "phl",
    "phlaudio": "phl",
    "purifi": "purifi",
    "purifiaudio": "purifi",
}

TYPE_NAMES = {
    "S": "Subwoofer",
    "W": "Woofer",
    "WM": "Midwoofer",
    "M": "Midrange",
    "F": "Full-range",
    "C": "Coaxial",
}

RANGES = {
    "fs_hz": (1.0, 2000.0),
    "vas_l": (0.0001, 100_000.0),
    "qts": (0.005, 10.0),
    "qms": (0.01, 1000.0),
    "qes": (0.005, 100.0),
    "re_ohm": (0.01, 1000.0),
    "sd_cm2": (0.01, 100_000.0),
    "le_mh": (0.0, 1000.0),
    "xmax_mm": (0.0, 500.0),
    "pe_w": (0.0, 100_000.0),
    "mms_g": (0.001, 100_000.0),
    "cms_mm_per_n": (0.000001, 1000.0),
    "bl_tm": (0.0, 1000.0),
}


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()


def normalized(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def canonical_brand(value: object) -> str:
    key = normalized(value)
    return BRAND_ALIASES.get(key, key)


def identity(brand: object, model: object) -> tuple[str, str]:
    return canonical_brand(brand), normalized(model)


def number(value: object) -> float | None:
    text = str(value or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        parsed = float(text)
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def bounded(key: str, value: float | None) -> float | None:
    if value is None:
        return None
    low, high = RANGES[key]
    return value if low <= value <= high else None


def fetch_source(url: str, timeout_s: float) -> str:
    request = Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/plain,*/*;q=0.5"},
    )
    with urlopen(request, timeout=timeout_s) as response:
        return response.read().decode("utf-8-sig", errors="replace")


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


def parse_rows(text: str) -> list[dict[str, str]]:
    rows = list(csv.DictReader(io.StringIO(text), delimiter="\t"))
    if not rows:
        raise ValueError("VituixCAD database is empty")
    missing = REQUIRED_COLUMNS - set(rows[0])
    if missing:
        raise ValueError(f"missing VituixCAD columns: {sorted(missing)}")
    return rows


def row_to_preset(row: dict[str, str], source_url: str, imported_at: str) -> tuple[dict | None, str]:
    brand = row["Manufacturer"].strip()
    model = row["Model"].strip()
    driver_type = row["Type"].strip().upper()
    if not brand or not model:
        return None, "missing identity"
    if driver_type in {"T", "PR"}:
        return None, "non-LF driver type"

    driver = {
        "fs_hz": bounded("fs_hz", number(row["fs [Hz]"])),
        "vas_l": bounded("vas_l", number(row["Vas [l]"])),
        "qts": bounded("qts", number(row["Qts"])),
        "qms": bounded("qms", number(row["Qms"])),
        "qes": bounded("qes", number(row["Qes"])),
        "re_ohm": bounded("re_ohm", number(row["Re [ohm]"])),
        "sd_cm2": bounded("sd_cm2", number(row["Sd [cm2]"])),
        "le_mh": bounded("le_mh", number(row["Le [mH]"])),
        "xmax_mm": bounded("xmax_mm", number(row["Xmax [mm]"])),
        "pe_w": bounded("pe_w", number(row["Pmax [W]"])),
        "mms_g": bounded("mms_g", number(row["Mms [g]"])),
        "cms_mm_per_n": bounded("cms_mm_per_n", number(row["Cms [mm/N]"])),
        "bl_tm": bounded("bl_tm", number(row["BL [Tm]"])),
    }
    required = ("fs_hz", "vas_l", "qts", "qms", "re_ohm", "sd_cm2")
    if any(driver[key] is None for key in required):
        return None, "missing or invalid simulation field"
    if driver["qms"] <= driver["qts"]:
        return None, "Qms must be greater than Qts"
    if driver["qes"] is None:
        driver["qes"] = 1.0 / (1.0 / driver["qts"] - 1.0 / driver["qms"])

    size_in = number(row["Size [in]"])
    if size_in is not None and not 0.5 <= size_in <= 32.0:
        size_in = None
    clean_driver = {
        key: round(float(value), 8)
        for key, value in driver.items()
        if value is not None
    }
    kind = TYPE_NAMES.get(driver_type, "Loudspeaker driver")
    return {
        "name": f"VCD: {brand} {model}",
        "brand": brand,
        "model": model,
        "size_in": size_in,
        "kind": kind,
        "url": source_url,
        "source": "VituixCAD online database",
        "driver": clean_driver,
        "website_fields": {
            "source": "VituixCAD online database",
            "source_url": source_url,
            "source_format": "tab-delimited online driver database",
            "imported_at": imported_at,
            "driver_type": driver_type,
            "status": row.get("Status", "").strip(),
            "revision": row.get("Revision", "").strip(),
            "record_updated": row.get("Updated", "").strip(),
        },
    }, ""


def import_database(
    text: str,
    *,
    source_url: str,
    existing_identities: set[tuple[str, str]],
) -> tuple[list[dict], dict]:
    imported_at = utc_now()
    rows = parse_rows(text)
    accepted: dict[tuple[str, str], dict] = {}
    rejected: dict[str, int] = {}
    duplicates_existing = 0
    duplicates_source = 0
    for row in rows:
        preset, reason = row_to_preset(row, source_url, imported_at)
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
            old_score = len(old["driver"])
            if len(preset["driver"]) <= old_score:
                continue
        accepted[key] = preset
    presets = sorted(
        accepted.values(),
        key=lambda item: (item["brand"].casefold(), item["model"].casefold()),
    )
    stats = {
        "source_rows": len(rows),
        "accepted": len(presets),
        "duplicates_existing": duplicates_existing,
        "duplicates_source": duplicates_source,
        "rejected": rejected,
        "brands": len({item["brand"] for item in presets}),
    }
    return presets, stats


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
        description="Import VituixCAD's public online driver database as a separate Load Forge tier."
    )
    parser.add_argument("--input", type=Path, help="Use a previously downloaded TSV instead of the network.")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--manufacturer", type=Path, default=DEFAULT_MANUFACTURER)
    parser.add_argument("--lsdb", type=Path, default=DEFAULT_LSDB)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    text = (
        args.input.read_text(encoding="utf-8-sig")
        if args.input
        else fetch_source(args.url, args.timeout)
    )
    existing = load_existing_identities([args.manufacturer, args.lsdb])
    presets, stats = import_database(
        text,
        source_url=args.url,
        existing_identities=existing,
    )
    payload = {
        "source": "VituixCAD online database",
        "source_url": args.url,
        "downloaded_at": utc_now(),
        "redistribution_note": (
            "Third-party public online database; keep as a separate optional "
            "catalog tier and review upstream terms before public redistribution."
        ),
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
