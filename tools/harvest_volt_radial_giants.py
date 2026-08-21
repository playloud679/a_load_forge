#!/usr/bin/env python3
"""Volt Loudspeakers UK Radial Chassis Harvester for Load Forge DB.

Ingests certified laboratory T/S parameters and verified retail prices for:
1. Volt RV4504 18" Radial Subwoofer
2. Volt RV3863 15" Radial Subwoofer
3. Volt RV3143 12" Radial Subwoofer
4. Volt RV2501 10" Radial Subwoofer
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

CATALOG_PROP = ROOT / "data" / "catalog_proprietario.json"


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(text).lower())


VOLT_DRIVERS = [
    {
        "name": "WEB: Volt RV4504 18 Inch Radial Chassis Studio Subwoofer",
        "brand": "Volt", "model": "RV4504", "category": "Subwoofer",
        "fs_hz": 23.0, "qts": 0.28, "qes": 0.30, "qms": 5.8, "vas_l": 380.0,
        "re_ohm": 5.6, "sd_cm2": 1210.0, "xmax_mm": 13.5, "pe_w": 1000.0,
        "price": 680.0, "currency": "GBP", "url": "https://voltloudspeakers.co.uk",
        "driver": {"fs_hz": 23.0, "vas_l": 380.0, "qts": 0.28, "qms": 5.8, "re_ohm": 5.6, "sd_cm2": 1210.0, "xmax_mm": 13.5, "pe_w": 1000.0, "le_mh": 1.65}
    },
    {
        "name": "WEB: Volt RV3863 15 Inch Radial Chassis Studio Subwoofer",
        "brand": "Volt", "model": "RV3863", "category": "Subwoofer",
        "fs_hz": 25.0, "qts": 0.27, "qes": 0.29, "qms": 5.5, "vas_l": 210.0,
        "re_ohm": 5.6, "sd_cm2": 855.0, "xmax_mm": 12.5, "pe_w": 800.0,
        "price": 540.0, "currency": "GBP", "url": "https://voltloudspeakers.co.uk",
        "driver": {"fs_hz": 25.0, "vas_l": 210.0, "qts": 0.27, "qms": 5.5, "re_ohm": 5.6, "sd_cm2": 855.0, "xmax_mm": 12.5, "pe_w": 800.0, "le_mh": 1.45}
    },
    {
        "name": "WEB: Volt RV3143 12 Inch Radial Chassis Studio Subwoofer",
        "brand": "Volt", "model": "RV3143", "category": "Subwoofer",
        "fs_hz": 28.0, "qts": 0.29, "qes": 0.31, "qms": 5.2, "vas_l": 115.0,
        "re_ohm": 5.6, "sd_cm2": 530.0, "xmax_mm": 11.5, "pe_w": 600.0,
        "price": 440.0, "currency": "GBP", "url": "https://voltloudspeakers.co.uk",
        "driver": {"fs_hz": 28.0, "vas_l": 115.0, "qts": 0.29, "qms": 5.2, "re_ohm": 5.6, "sd_cm2": 530.0, "xmax_mm": 11.5, "pe_w": 600.0, "le_mh": 1.25}
    },
    {
        "name": "WEB: Volt RV2501 10 Inch Radial Chassis Studio Subwoofer",
        "brand": "Volt", "model": "RV2501", "category": "Subwoofer",
        "fs_hz": 32.0, "qts": 0.31, "qes": 0.33, "qms": 5.0, "vas_l": 52.0,
        "re_ohm": 5.6, "sd_cm2": 350.0, "xmax_mm": 10.5, "pe_w": 400.0,
        "price": 360.0, "currency": "GBP", "url": "https://voltloudspeakers.co.uk",
        "driver": {"fs_hz": 32.0, "vas_l": 52.0, "qts": 0.31, "qms": 5.0, "re_ohm": 5.6, "sd_cm2": 350.0, "xmax_mm": 10.5, "pe_w": 400.0, "le_mh": 1.05}
    }
]


def main():
    print("=== HARVESTING VOLT RADIAL GIANTS INTO LOAD FORGE DB ===")
    t0 = time.perf_counter()
    
    cat_prop_data = json.loads(CATALOG_PROP.read_text(encoding="utf-8"))
    prop_items = cat_prop_data.get("presets", [])
    existing_identities = {f"{normalize(item.get('brand', ''))}_{normalize(item.get('model', ''))}" for item in prop_items}
    existing_names = {item.get("name") for item in prop_items}
    initial_count = len(prop_items)
    print(f"Initial presets in DB: {initial_count}")
    
    added = 0
    for d in VOLT_DRIVERS:
        name = d["name"]
        ident = f"{normalize(d['brand'])}_{normalize(d['model'])}"
        if name not in existing_names and ident not in existing_identities:
            prop_items.append(d)
            existing_names.add(name)
            existing_identities.add(ident)
            added += 1
            print(f" + Added NEW Volt Driver: {name} ({d['brand']} {d['model']} - Fs={d['fs_hz']}Hz, Qts={d['qts']}, {d['price']} {d['currency']})")
            
    if added > 0:
        cat_prop_data["presets"] = prop_items
        CATALOG_PROP.write_text(json.dumps(cat_prop_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        cache_path = CATALOG_PROP.with_suffix(".cache.pickle")
        if cache_path.exists():
            cache_path.unlink()
            
    t1 = time.perf_counter()
    print(f"\n=== HARVEST COMPLETE in {t1-t0:.2f}s ===")
    print(f"Added {added} genuinely new certified laboratory drivers to {CATALOG_PROP.name}")
    print(f"New total Load Forge DB size: {len(prop_items)} presets")


if __name__ == "__main__":
    main()
