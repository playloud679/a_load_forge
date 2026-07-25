#!/usr/bin/env python3
"""Merge tools/harvest_rockville.py's checkpoint into data/manufacturer_drivers.json.

Rockville's Shopify catalog lists the same physical driver under many
"+bundle" combo listings (driver + enclosure + amplifier, 2-pack, 4-pack...).
Bundle pages are dropped entirely rather than kept and deduped, because a
bundle's body_html sometimes carries T/S text for whichever component the
page lists first -- not reliably the Rockville driver itself (confirmed by
spot-checking Fs across bundle variants of the same handle). Only genuine
standalone product pages (no "+" in the raw title) are trusted.

Model titles still carry quantity/used-listing cruft ("2-Pack", "[Used]");
stripped here the same way earlier sessions cleaned up marketing-title cruft
for Supravox/BMS (cosmetic normalization, not a parsing fix).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = ROOT / "data" / "rockville_harvest_checkpoint.json"
MANUFACTURER_PATH = ROOT / "data" / "manufacturer_drivers.json"


def clean_model(title: str) -> str:
    t = re.sub(r"\s*\[.*?\]\s*", " ", title).strip()
    t = re.sub(r"^\d+[- ]Pair\s+", "", t, flags=re.I)
    t = re.sub(r"^\d+[- ]Pack\s+", "", t, flags=re.I)
    t = re.sub(r"\s+\d+[- ]Pack$", "", t, flags=re.I)
    t = re.sub(r"\s+\d+[- ]Pair$", "", t, flags=re.I)
    return t.strip()


def main() -> None:
    state = json.loads(CHECKPOINT.read_text())
    presets = state.get("presets", [])
    standalone = [p for p in presets if "+" not in p.get("model", "")]
    print(f"harvested presets: {len(presets)}, standalone (non-bundle): {len(standalone)}")

    data = json.loads(MANUFACTURER_PATH.read_text(encoding="utf-8"))
    existing_keys = {(p.get("brand"), p.get("model")) for p in data["presets"]}

    added = 0
    seen_clean = set()
    for preset in standalone:
        model = clean_model(preset["model"])
        if not model:
            continue
        key = (preset["brand"], model)
        if key in existing_keys or key in seen_clean:
            continue
        seen_clean.add(key)
        preset = dict(preset)
        preset["model"] = model
        preset["name"] = f"WEB: {preset['brand']} {model}".strip()
        preset["website_fields"] = dict(preset.get("website_fields", {}))
        preset["website_fields"]["model"] = model
        data["presets"].append(preset)
        existing_keys.add(key)
        added += 1

    if added:
        MANUFACTURER_PATH.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    print(f"presets added: {added}")


if __name__ == "__main__":
    main()
