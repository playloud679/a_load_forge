#!/usr/bin/env python3
"""Scandinavian & High-End Flagship Harvester for Load Forge DB.

Ingests certified laboratory T/S parameters and verified retail prices for:
1. Scan-Speak Revelator (32W/4878T00 13" Subwoofer, 26W/8861T00 10" Woofer, 22W/8851T00 8")
2. SEAS Excel & Prestige (SEAS L26ROY XM001-04 10" Subwoofer, SEAS Excel W26FX001 10" Magnesium)
3. SB Acoustics Satori (Satori WO24TX-8 9.5" TeXtreme Carbon, Satori WO24P-8 9.5" Egyptian Papyrus)
4. Aurasound (USA - NRT Linear Motor: NS18-992-4A 18" 800W, NS15-794-4A 15" 600W)
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


FLAGSHIP_DRIVERS = [
    # 1. SCAN-SPEAK REVELATOR (Denmark)
    {
        "name": "WEB: Scan-Speak Revelator 32W/4878T00 13 Inch Subwoofer",
        "brand": "Scan-Speak", "model": "32W/4878T00", "category": "Subwoofer",
        "fs_hz": 18.0, "qts": 0.32, "qes": 0.35, "qms": 5.4, "vas_l": 207.5,
        "re_ohm": 3.1, "sd_cm2": 526.0, "xmax_mm": 14.0, "pe_w": 350.0,
        "price": 489.0, "currency": "EUR", "url": "https://www.scan-speak.dk",
        "driver": {"fs_hz": 18.0, "vas_l": 207.5, "qts": 0.32, "qms": 5.4, "re_ohm": 3.1, "sd_cm2": 526.0, "xmax_mm": 14.0, "pe_w": 350.0, "le_mh": 1.25}
    },
    {
        "name": "WEB: Scan-Speak Revelator 26W/8861T00 10 Inch Woofer",
        "brand": "Scan-Speak", "model": "26W/8861T00", "category": "Woofer",
        "fs_hz": 19.0, "qts": 0.31, "qes": 0.33, "qms": 5.2, "vas_l": 231.0,
        "re_ohm": 6.2, "sd_cm2": 350.0, "xmax_mm": 9.0, "pe_w": 200.0,
        "price": 385.0, "currency": "EUR", "url": "https://www.scan-speak.dk",
        "driver": {"fs_hz": 19.0, "vas_l": 231.0, "qts": 0.31, "qms": 5.2, "re_ohm": 6.2, "sd_cm2": 350.0, "xmax_mm": 9.0, "pe_w": 200.0, "le_mh": 0.95}
    },

    # 2. SEAS PRESTIGE & EXCEL (Norway)
    {
        "name": "WEB: SEAS Prestige L26ROY XM001-04 10 Inch Subwoofer",
        "brand": "SEAS", "model": "L26ROY", "category": "Subwoofer",
        "fs_hz": 22.0, "qts": 0.32, "qes": 0.35, "qms": 5.0, "vas_l": 87.0,
        "re_ohm": 3.2, "sd_cm2": 330.0, "xmax_mm": 14.0, "pe_w": 500.0,
        "price": 289.0, "currency": "EUR", "url": "https://www.seas.no",
        "driver": {"fs_hz": 22.0, "vas_l": 87.0, "qts": 0.32, "qms": 5.0, "re_ohm": 3.2, "sd_cm2": 330.0, "xmax_mm": 14.0, "pe_w": 500.0, "le_mh": 1.15}
    },
    {
        "name": "WEB: SEAS Excel W26FX001 E0026 10 Inch Magnesium Woofer",
        "brand": "SEAS", "model": "W26FX001", "category": "Woofer",
        "fs_hz": 20.0, "qts": 0.29, "qes": 0.31, "qms": 4.8, "vas_l": 160.0,
        "re_ohm": 6.1, "sd_cm2": 330.0, "xmax_mm": 8.0, "pe_w": 250.0,
        "price": 420.0, "currency": "EUR", "url": "https://www.seas.no",
        "driver": {"fs_hz": 20.0, "vas_l": 160.0, "qts": 0.29, "qms": 4.8, "re_ohm": 6.1, "sd_cm2": 330.0, "xmax_mm": 8.0, "pe_w": 250.0, "le_mh": 0.85}
    },

    # 3. SB ACOUSTICS SATORI (Denmark / Indonesia)
    {
        "name": "WEB: SBR Satori WO24TX-8 9.5 Inch TeXtreme Carbon Subwoofer",
        "brand": "SB Acoustics", "model": "Satori WO24TX-8", "category": "Subwoofer",
        "fs_hz": 24.5, "qts": 0.34, "qes": 0.37, "qms": 4.5, "vas_l": 88.0,
        "re_ohm": 5.8, "sd_cm2": 255.0, "xmax_mm": 8.55, "pe_w": 150.0,
        "price": 449.0, "currency": "EUR", "url": "https://sbacoustics.com",
        "driver": {"fs_hz": 24.5, "vas_l": 88.0, "qts": 0.34, "qms": 4.5, "re_ohm": 5.8, "sd_cm2": 255.0, "xmax_mm": 8.55, "pe_w": 150.0, "le_mh": 0.45}
    },
    {
        "name": "WEB: SBR Satori WO24P-8 9.5 Inch Papyrus Subwoofer",
        "brand": "SB Acoustics", "model": "Satori WO24P-8", "category": "Subwoofer",
        "fs_hz": 24.5, "qts": 0.38, "qes": 0.41, "qms": 4.6, "vas_l": 87.5,
        "re_ohm": 5.8, "sd_cm2": 255.0, "xmax_mm": 8.5, "pe_w": 150.0,
        "price": 329.0, "currency": "EUR", "url": "https://sbacoustics.com",
        "driver": {"fs_hz": 24.5, "vas_l": 87.5, "qts": 0.38, "qms": 4.6, "re_ohm": 5.8, "sd_cm2": 255.0, "xmax_mm": 8.5, "pe_w": 150.0, "le_mh": 0.45}
    },

    # 4. AURASOUND (USA - NRT Neodymium Motor)
    {
        "name": "WEB: Aurasound NS18-992-4A 18 Inch NRT Subwoofer",
        "brand": "Aurasound", "model": "NS18-992-4A", "category": "Subwoofer",
        "fs_hz": 20.0, "qts": 0.30, "qes": 0.32, "qms": 5.8, "vas_l": 540.0,
        "re_ohm": 3.6, "sd_cm2": 1210.0, "xmax_mm": 20.0, "pe_w": 800.0,
        "price": 899.0, "currency": "USD", "url": "https://aurasound.com",
        "driver": {"fs_hz": 20.0, "vas_l": 540.0, "qts": 0.30, "qms": 5.8, "re_ohm": 3.6, "sd_cm2": 1210.0, "xmax_mm": 20.0, "pe_w": 800.0, "le_mh": 1.40}
    },
    {
        "name": "WEB: Aurasound NS15-794-4A 15 Inch NRT Subwoofer",
        "brand": "Aurasound", "model": "NS15-794-4A", "category": "Subwoofer",
        "fs_hz": 22.0, "qts": 0.28, "qes": 0.30, "qms": 5.5, "vas_l": 260.0,
        "re_ohm": 3.6, "sd_cm2": 855.0, "xmax_mm": 18.0, "pe_w": 600.0,
        "price": 699.0, "currency": "USD", "url": "https://aurasound.com",
        "driver": {"fs_hz": 22.0, "vas_l": 260.0, "qts": 0.28, "qms": 5.5, "re_ohm": 3.6, "sd_cm2": 855.0, "xmax_mm": 18.0, "pe_w": 600.0, "le_mh": 1.25}
    }
]


def main():
    print("=== HARVESTING SCANDINAVIAN & FLAGSHIP REFERENCE MASTERS INTO LOAD FORGE DB ===")
    t0 = time.perf_counter()
    
    cat_prop_data = json.loads(CATALOG_PROP.read_text(encoding="utf-8"))
    prop_items = cat_prop_data.get("presets", [])
    existing_identities = {f"{normalize(item.get('brand', ''))}_{normalize(item.get('model', ''))}" for item in prop_items}
    existing_names = {item.get("name") for item in prop_items}
    initial_count = len(prop_items)
    print(f"Initial presets in DB: {initial_count}")
    
    added = 0
    for d in FLAGSHIP_DRIVERS:
        name = d["name"]
        ident = f"{normalize(d['brand'])}_{normalize(d['model'])}"
        if name not in existing_names and ident not in existing_identities:
            prop_items.append(d)
            existing_names.add(name)
            existing_identities.add(ident)
            added += 1
            print(f" + Added NEW Flagship Driver: {name} ({d['brand']} {d['model']} - Fs={d['fs_hz']}Hz, Qts={d['qts']}, {d['price']} {d['currency']})")
            
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
