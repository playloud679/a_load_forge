#!/usr/bin/env python3
"""Fast validation gate for catalog-only changes."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "catalog_proprietario.json"
REQUIRED_FIELDS = ("fs_hz", "vas_l", "qts", "qms", "re_ohm", "sd_cm2")


def positive(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) > 0.0
    )


def main() -> int:
    payload = json.loads(CATALOG.read_text(encoding="utf-8"))
    assert payload.get("catalog_version") == "1.0.0"
    rows = payload.get("presets")
    assert isinstance(rows, list) and rows, "catalog must contain presets"
    names = [row.get("name") for row in rows]
    assert all(isinstance(name, str) and name.strip() for name in names)
    assert len(names) == len(set(names)), "catalog preset names must be unique"
    for index, row in enumerate(rows):
        assert isinstance(row.get("driver"), dict), f"row {index}: missing driver"
        for field in REQUIRED_FIELDS:
            assert positive(row["driver"].get(field)), f"row {index}: invalid {field}"

    sys.path.insert(0, str(ROOT / "src"))
    import presets

    presets._load_manufacturer_presets.cache_clear()
    loaded, _info = presets._load_manufacturer_presets()
    assert loaded, "application loader returned no proprietary presets"
    print(
        f"CATALOG PASS: version={payload['catalog_version']} "
        f"records={len(rows)} loaded={len(loaded)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
