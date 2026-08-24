#!/usr/bin/env python3
"""Build source-specific catalogs containing T/S data and commercial fields."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROPRIETARY_CATALOG_VERSION = "1.0.0"
sys.path.insert(0, str(ROOT / "src"))
import pricing  # noqa: E402

SOURCES = {
    "catalog_proprietario.json": "data/manufacturer_drivers.json",
    "catalog_lsdb.json": "data/loudspeaker_database_drivers.json",
    "catalog_vituixcad.json": "data/vituixcad_drivers.json",
    "catalog_speakerboxlite.json": "data/speakerboxlite_drivers.json",
}
ADMIN_FIELDS = (
    "brand", "matched_brand", "matched_mpn", "matched_name",
    "part_number_override", "price", "currency", "price_currency",
    "price_url", "availability", "source",
)
ADMIN_DRIVER_FIELDS = ("xmax_mm", "pe_w", "le_mh")


def _manual_rows(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        str(item.get("name") or ""): item
        for item in payload.get("presets", [])
        if isinstance(item, dict)
        and item.get("name")
        and (
            str(item.get("source") or "") == "Manual catalog maintenance"
            or str(item.get("part_number_override") or "").strip()
        )
    }


def _preserve_manual_values(item: dict, previous: dict | None) -> dict:
    if not previous:
        return item
    result = dict(item)
    for field in ADMIN_FIELDS:
        if field in previous:
            result[field] = previous[field]
    driver = dict(result.get("driver") or {})
    previous_driver = previous.get("driver") or {}
    for field in ADMIN_DRIVER_FIELDS:
        if field in previous_driver:
            driver[field] = previous_driver[field]
    result["driver"] = driver
    return result


def _preserve_proprietary_rows(target: Path, rows: list[dict]) -> list[dict]:
    """Keep harvested proprietary rows absent from the current source export."""
    if target.name != "catalog_proprietario.json" or not target.exists():
        return rows
    try:
        previous = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return rows

    def identity(item: dict) -> tuple[str, str, str]:
        return (
            str(item.get("brand") or "").casefold().strip(),
            str(item.get("model") or "").casefold().strip(),
            str(item.get("name") or "").casefold().strip(),
        )

    known = {identity(item) for item in rows}
    preserved = list(rows)
    for item in previous.get("presets", []):
        if isinstance(item, dict) and identity(item) not in known:
            preserved.append(item)
            known.add(identity(item))
    return preserved


def main() -> None:
    for output, source in SOURCES.items():
        rows = json.loads((ROOT / source).read_text(encoding="utf-8")).get("presets", [])
        target = ROOT / "data" / output
        rows = _preserve_proprietary_rows(target, rows)
        manual_rows = _manual_rows(target)
        unified = []
        for row in rows:
            item = dict(row)
            price, currency, url = pricing._preset_price(
                str(row.get("name", "")), str(row.get("model", "")), str(row.get("brand", ""))
            )
            if price is not None:
                item["price"] = price
                item["price_currency"] = currency
                item["price_url"] = url
            item = _preserve_manual_values(item, manual_rows.get(str(row.get("name") or "")))
            unified.append(item)
        temporary = target.with_suffix(target.suffix + ".tmp")
        payload = {"source_file": source, "presets": unified}
        if output == "catalog_proprietario.json":
            payload["catalog_version"] = PROPRIETARY_CATALOG_VERSION
            payload = {
                "catalog_version": payload["catalog_version"],
                "source_file": payload["source_file"],
                "presets": payload["presets"],
            }
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(target)
        print(f"{target.name}: {len(unified)} records")


if __name__ == "__main__":
    main()
