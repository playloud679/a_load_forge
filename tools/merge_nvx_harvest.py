#!/usr/bin/env python3
"""Merge tools/harvest_nvx.py's checkpoint presets into
data/manufacturer_drivers.json, deduped by (brand, model).

NVX product titles are full marketing strings (e.g. "XQS65KITv2 600W Peak
(300W RMS) 6.5\" X-Series 2-Way Component Speaker System with Carbon Fiber
Cones and 30mm Silk Dome Tweeters"). The leading token is always the real
part number -- same cosmetic-cleanup precedent as Supravox/BMS/Rockville.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = ROOT / "data" / "nvx_harvest_checkpoint.json"
CATALOG = ROOT / "data" / "manufacturer_drivers.json"

MODEL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9\-]*\d[A-Za-z0-9\-]*")


def clean_model(raw_title: str) -> str:
    first_token = raw_title.strip().split(" ", 1)[0]
    match = MODEL_RE.match(first_token)
    return match.group(0) if match else first_token


def main() -> None:
    state = json.loads(CHECKPOINT.read_text())
    presets = state.get("presets", [])
    catalog = json.loads(CATALOG.read_text())
    existing = catalog["presets"]
    existing_keys = {(p["brand"], p["model"]) for p in existing}

    added = 0
    for preset in presets:
        model = clean_model(preset["model"])
        preset["model"] = model
        preset["name"] = f"WEB: {preset['brand']} {model}"
        key = (preset["brand"], model)
        if key in existing_keys:
            continue
        existing_keys.add(key)
        existing.append(preset)
        added += 1

    catalog["presets"] = existing
    CATALOG.write_text(json.dumps(catalog, indent=2))
    print(f"Added {added} new NVX presets. Catalog now has {len(existing)} presets.")


if __name__ == "__main__":
    main()
