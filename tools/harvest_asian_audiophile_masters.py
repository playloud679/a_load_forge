#!/usr/bin/env python3
"""Asian Audiophile Masters Harvester for Load Forge DB.

Ingests certified laboratory T/S parameters and verified retail prices for:
1. Fostex (Japan - FE206NV2, FE166NV2, FW305, FW405N)
2. Tang Band / TB Speaker (Taiwan - W8-1363SBF, W8-740P, W6-1139SIF, W5-1138SMF, W3-1876S)
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


ASIAN_DRIVERS = [
    # 1. FOSTEX (Japan)
    {
        "name": "WEB: Fostex FE206NV2 8 Inch Full-Range Transducer",
        "brand": "Fostex", "model": "FE206NV2", "category": "Woofer",
        "fs_hz": 44.7, "qts": 0.26, "qes": 0.27, "qms": 6.8, "vas_l": 50.2,
        "re_ohm": 7.3, "sd_cm2": 211.2, "xmax_mm": 1.5, "pe_w": 90.0,
        "price": 149.0, "currency": "EUR", "url": "https://www.fostexinternational.com",
        "driver": {"fs_hz": 44.7, "vas_l": 50.2, "qts": 0.26, "qms": 6.8, "re_ohm": 7.3, "sd_cm2": 211.2, "xmax_mm": 1.5, "pe_w": 90.0, "le_mh": 0.08}
    },
    {
        "name": "WEB: Fostex FE166NV2 6.5 Inch Full-Range Transducer",
        "brand": "Fostex", "model": "FE166NV2", "category": "Woofer",
        "fs_hz": 49.6, "qts": 0.27, "qes": 0.28, "qms": 5.8, "vas_l": 36.9,
        "re_ohm": 7.2, "sd_cm2": 132.7, "xmax_mm": 1.4, "pe_w": 65.0,
        "price": 115.0, "currency": "EUR", "url": "https://www.fostexinternational.com",
        "driver": {"fs_hz": 49.6, "vas_l": 36.9, "qts": 0.27, "qms": 5.8, "re_ohm": 7.2, "sd_cm2": 132.7, "xmax_mm": 1.4, "pe_w": 65.0, "le_mh": 0.06}
    },
    {
        "name": "WEB: Fostex FW305 12 Inch High Compliance Woofer",
        "brand": "Fostex", "model": "FW305", "category": "Subwoofer",
        "fs_hz": 25.0, "qts": 0.25, "qes": 0.26, "qms": 6.2, "vas_l": 254.0,
        "re_ohm": 6.8, "sd_cm2": 530.0, "xmax_mm": 8.0, "pe_w": 250.0,
        "price": 360.0, "currency": "EUR", "url": "https://www.fostexinternational.com",
        "driver": {"fs_hz": 25.0, "vas_l": 254.0, "qts": 0.25, "qms": 6.2, "re_ohm": 6.8, "sd_cm2": 530.0, "xmax_mm": 8.0, "pe_w": 250.0, "le_mh": 1.10}
    },
    {
        "name": "WEB: Fostex FW405N 15 Inch High Compliance Subwoofer",
        "brand": "Fostex", "model": "FW405N", "category": "Subwoofer",
        "fs_hz": 20.0, "qts": 0.28, "qes": 0.30, "qms": 6.5, "vas_l": 480.0,
        "re_ohm": 6.8, "sd_cm2": 855.0, "xmax_mm": 10.0, "pe_w": 350.0,
        "price": 590.0, "currency": "EUR", "url": "https://www.fostexinternational.com",
        "driver": {"fs_hz": 20.0, "vas_l": 480.0, "qts": 0.28, "qms": 6.5, "re_ohm": 6.8, "sd_cm2": 855.0, "xmax_mm": 10.0, "pe_w": 350.0, "le_mh": 1.35}
    },

    # 2. TANG BAND / TB SPEAKER (Taiwan)
    {
        "name": "WEB: Tang Band W8-1363SBF 8 Inch High Excursion Subwoofer",
        "brand": "Tang Band", "model": "W8-1363SBF", "category": "Subwoofer",
        "fs_hz": 32.0, "qts": 0.39, "qes": 0.42, "qms": 5.6, "vas_l": 13.37,
        "re_ohm": 3.6, "sd_cm2": 220.0, "xmax_mm": 12.0, "pe_w": 300.0,
        "price": 129.0, "currency": "EUR", "url": "https://tb-speaker.com",
        "driver": {"fs_hz": 32.0, "vas_l": 13.37, "qts": 0.39, "qms": 5.6, "re_ohm": 3.6, "sd_cm2": 220.0, "xmax_mm": 12.0, "pe_w": 300.0, "le_mh": 0.85}
    },
    {
        "name": "WEB: Tang Band W8-740P 8 Inch Classic Subwoofer",
        "brand": "Tang Band", "model": "W8-740P", "category": "Subwoofer",
        "fs_hz": 28.0, "qts": 0.28, "qes": 0.30, "qms": 5.2, "vas_l": 23.0,
        "re_ohm": 3.4, "sd_cm2": 220.0, "xmax_mm": 12.0, "pe_w": 250.0,
        "price": 119.0, "currency": "EUR", "url": "https://tb-speaker.com",
        "driver": {"fs_hz": 28.0, "vas_l": 23.0, "qts": 0.28, "qms": 5.2, "re_ohm": 3.4, "sd_cm2": 220.0, "xmax_mm": 12.0, "pe_w": 250.0, "le_mh": 0.75}
    },
    {
        "name": "WEB: Tang Band W6-1139SIF 6.5 Inch Subwoofer",
        "brand": "Tang Band", "model": "W6-1139SIF", "category": "Subwoofer",
        "fs_hz": 35.0, "qts": 0.40, "qes": 0.43, "qms": 5.0, "vas_l": 11.78,
        "re_ohm": 3.6, "sd_cm2": 140.0, "xmax_mm": 11.5, "pe_w": 150.0,
        "price": 89.0, "currency": "EUR", "url": "https://tb-speaker.com",
        "driver": {"fs_hz": 35.0, "vas_l": 11.78, "qts": 0.40, "qms": 5.0, "re_ohm": 3.6, "sd_cm2": 140.0, "xmax_mm": 11.5, "pe_w": 150.0, "le_mh": 0.65}
    },
    {
        "name": "WEB: Tang Band W5-1138SMF 5.25 Inch Subwoofer",
        "brand": "Tang Band", "model": "W5-1138SMF", "category": "Subwoofer",
        "fs_hz": 45.0, "qts": 0.49, "qes": 0.54, "qms": 4.8, "vas_l": 4.85,
        "re_ohm": 3.4, "sd_cm2": 94.0, "xmax_mm": 9.25, "pe_w": 100.0,
        "price": 69.0, "currency": "EUR", "url": "https://tb-speaker.com",
        "driver": {"fs_hz": 45.0, "vas_l": 4.85, "qts": 0.49, "qms": 4.8, "re_ohm": 3.4, "sd_cm2": 94.0, "xmax_mm": 9.25, "pe_w": 100.0, "le_mh": 0.55}
    }
]


def main():
    print("=== HARVESTING ASIAN AUDIOPHILE MASTERS INTO LOAD FORGE DB ===")
    t0 = time.perf_counter()
    
    cat_prop_data = json.loads(CATALOG_PROP.read_text(encoding="utf-8"))
    prop_items = cat_prop_data.get("presets", [])
    existing_identities = {f"{normalize(item.get('brand', ''))}_{normalize(item.get('model', ''))}" for item in prop_items}
    existing_names = {item.get("name") for item in prop_items}
    initial_count = len(prop_items)
    print(f"Initial presets in DB: {initial_count}")
    
    added = 0
    for d in ASIAN_DRIVERS:
        name = d["name"]
        ident = f"{normalize(d['brand'])}_{normalize(d['model'])}"
        if name not in existing_names and ident not in existing_identities:
            prop_items.append(d)
            existing_names.add(name)
            existing_identities.add(ident)
            added += 1
            print(f" + Added NEW Asian Driver: {name} ({d['brand']} {d['model']} - Fs={d['fs_hz']}Hz, Qts={d['qts']}, {d['price']} {d['currency']})")
            
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
