#!/usr/bin/env python3
"""Use external driver libraries as identity-only radar for official-source hunts.

The command never promotes or copies technical data from third-party catalogs.
It compares only normalized brand/model/impedance identities against the
proprietary catalog and emits aggregate priorities plus small model samples.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import presets

PROPRIETARY_CATALOG = ROOT / "data" / "catalog_proprietario.json"
DEFAULT_OUTPUT = ROOT / "data" / "official_hunt_radar_report.json"
RADAR_LIBRARIES = (
    ("LSDB", ROOT / "data" / "catalog_lsdb.json"),
    ("VituixCAD", ROOT / "data" / "catalog_vituixcad.json"),
    ("Speaker Box Lite", ROOT / "data" / "catalog_speakerboxlite.json"),
    ("ZTZ Audio", ROOT / "data" / "catalog_ztzaudio_lf_ferrite_presets.json"),
    ("Manufacturer crawl legacy", ROOT / "data" / "manufacturer_drivers.json"),
)
GENERIC_BRANDS = frozenset(
    {
        "",
        "custom",
        "discontinued",
        "factory buyouts",
        "other",
        "unknown",
    }
)


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def load_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("presets", []) if isinstance(payload, dict) else payload
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def identity_for(row: dict) -> tuple[str, str, str] | None:
    brand = presets._external_catalog_manufacturer(str(row.get("brand") or "").strip())
    model = presets._external_catalog_identity_model(row, str(row.get("model") or "").strip())
    if brand.casefold() in GENERIC_BRANDS or not model:
        return None
    driver = row.get("driver") or {}
    try:
        re_ohm = float(driver["re_ohm"])
    except (KeyError, TypeError, ValueError):
        return None
    nominal = (row.get("published_specs") or {}).get("nominal_impedance_ohm")
    impedance_text = f"{nominal} ohm" if nominal is not None else ""
    return presets._external_catalog_identity(
        brand,
        model,
        SimpleNamespace(re_ohm=re_ohm),
        impedance_text,
    )


def _brand_matches(candidate: str, requested: str) -> bool:
    compact = lambda value: re.sub(r"[^a-z0-9]+", "", value.casefold())
    return compact(candidate) == compact(requested)


def build_radar(
    proprietary_rows: Iterable[dict],
    libraries: Iterable[tuple[str, Iterable[dict]]],
    *,
    sample_limit: int = 8,
) -> tuple[dict, dict[str, list[dict]]]:
    proprietary_rows = list(proprietary_rows)
    proprietary_identities = {
        identity for row in proprietary_rows if (identity := identity_for(row)) is not None
    }
    candidates: dict[tuple[str, str, str], dict] = {}
    library_stats: list[dict] = []
    total_source_records = 0

    for label, source_rows_iter in libraries:
        source_rows = list(source_rows_iter)
        total_source_records += len(source_rows)
        usable = 0
        missing = 0
        for row in source_rows:
            identity = identity_for(row)
            if identity is None:
                continue
            usable += 1
            if identity in proprietary_identities:
                continue
            missing += 1
            brand = presets._external_catalog_manufacturer(str(row.get("brand") or "").strip())
            model = presets._external_catalog_identity_model(
                row, str(row.get("model") or "").strip()
            )
            candidate = candidates.setdefault(
                identity,
                {
                    "brand": brand,
                    "model": model,
                    "impedance_ohm": identity[2],
                    "libraries": set(),
                },
            )
            candidate["libraries"].add(label)
        library_stats.append(
            {
                "library": label,
                "records": len(source_rows),
                "usable_identities": usable,
                "missing_occurrences": missing,
            }
        )

    by_brand: dict[str, list[dict]] = defaultdict(list)
    for candidate in candidates.values():
        candidate["libraries"] = sorted(candidate["libraries"])
        by_brand[candidate["brand"]].append(candidate)
    for values in by_brand.values():
        values.sort(key=lambda item: (item["model"].casefold(), item["impedance_ohm"]))

    brand_rows = []
    for brand, values in by_brand.items():
        source_counts = Counter(
            library for candidate in values for library in candidate["libraries"]
        )
        brand_rows.append(
            {
                "brand": brand,
                "missing_identities": len(values),
                "library_evidence": dict(sorted(source_counts.items())),
                "samples": values[: max(0, sample_limit)],
            }
        )
    brand_rows.sort(key=lambda item: (-item["missing_identities"], item["brand"].casefold()))

    report = {
        "schema_version": 1,
        "generated_at": utc_now(),
        "policy": "identity-only radar; never copy or promote third-party technical fields",
        "proprietary_records": len(proprietary_rows),
        "proprietary_identities": len(proprietary_identities),
        "source_records_scanned": total_source_records,
        "unique_missing_identities": len(candidates),
        "libraries": library_stats,
        "brands": brand_rows,
    }
    return report, dict(by_brand)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=PROPRIETARY_CATALOG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--brand", default="", help="Print every missing identity for one brand.")
    parser.add_argument("--sample-limit", type=int, default=8)
    args = parser.parse_args()

    proprietary_rows = load_rows(args.catalog)
    library_rows = [(label, load_rows(path)) for label, path in RADAR_LIBRARIES]
    report, by_brand = build_radar(
        proprietary_rows,
        library_rows,
        sample_limit=max(0, args.sample_limit),
    )
    write_json(args.output, report)
    print(
        f"OFFICIAL HUNT RADAR: scanned={report['source_records_scanned']} "
        f"missing={report['unique_missing_identities']} brands={len(report['brands'])} "
        f"output={args.output}"
    )
    if args.brand:
        selected = next(
            (values for brand, values in by_brand.items() if _brand_matches(brand, args.brand)),
            [],
        )
        for candidate in selected:
            evidence = ", ".join(candidate["libraries"])
            print(
                f"RADAR CANDIDATE: {candidate['brand']} {candidate['model']} "
                f"[{candidate['impedance_ohm']} ohm] <- {evidence}"
            )
        print(f"RADAR BRAND: requested={args.brand!r} missing={len(selected)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
