#!/usr/bin/env python3
"""Build source-specific catalogs containing T/S data and commercial fields."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import pricing  # noqa: E402

SOURCES = {
    "catalog_proprietario.json": "data/manufacturer_drivers.json",
    "catalog_lsdb.json": "data/loudspeaker_database_drivers.json",
    "catalog_vituixcad.json": "data/vituixcad_drivers.json",
    "catalog_speakerboxlite.json": "data/speakerboxlite_drivers.json",
}


def main() -> None:
    for output, source in SOURCES.items():
        rows = json.loads((ROOT / source).read_text(encoding="utf-8")).get("presets", [])
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
            unified.append(item)
        target = ROOT / "data" / output
        target.write_text(json.dumps({"source_file": source, "presets": unified}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{target.name}: {len(unified)} records")


if __name__ == "__main__":
    main()
