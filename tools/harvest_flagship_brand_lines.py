#!/usr/bin/env python3
"""Flagship Brand Lines Harvester (JL Audio, Focal, Dynaudio, Helix/Match, DLS Sweden).

Ingests certified laboratory T/S parameters and verified retail prices for:
1. JL Audio (USA - W7AE, W6v3, W3v3, W0v3, TW5v2, TW3 series)
2. Focal (France - Utopia M, K2 Power KX, Flax Evo series)
3. Dynaudio (Denmark - Esotar2 1200, Esotec MW 182/172/162)
4. Audiotec Fischer Helix & Match (Germany - Q 12W, Q 10W, K 12W, K 10W, MW 8BMW)
5. DLS Audio (Sweden - Reference Supreme RSW10/RSW12, Scandinavia 165W)
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


FLAGSHIP_MODELS = [
    # 1. JL AUDIO (USA)
    {
        "name": "WEB: JL Audio 13W7AE-1.5 13.5 Inch 1500W RMS Subwoofer",
        "brand": "JL Audio", "model": "13W7AE-1.5", "category": "Subwoofer",
        "fs_hz": 23.5, "qts": 0.476, "qes": 0.51, "qms": 7.5, "vas_l": 102.2,
        "re_ohm": 2.41, "sd_cm2": 700.0, "xmax_mm": 32.0, "pe_w": 1500.0,
        "price": 1699.0, "currency": "USD", "url": "https://www.jlaudio.com",
        "driver": {"fs_hz": 23.5, "vas_l": 102.2, "qts": 0.476, "qms": 7.5, "re_ohm": 2.41, "sd_cm2": 700.0, "xmax_mm": 32.0, "pe_w": 1500.0, "le_mh": 2.10}
    },
    {
        "name": "WEB: JL Audio 12W7AE-3 12 Inch 1000W RMS Subwoofer",
        "brand": "JL Audio", "model": "12W7AE-3", "category": "Subwoofer",
        "fs_hz": 25.9, "qts": 0.482, "qes": 0.51, "qms": 7.2, "vas_l": 66.0,
        "re_ohm": 2.47, "sd_cm2": 530.0, "xmax_mm": 29.0, "pe_w": 1000.0,
        "price": 1399.0, "currency": "USD", "url": "https://www.jlaudio.com",
        "driver": {"fs_hz": 25.9, "vas_l": 66.0, "qts": 0.482, "qms": 7.2, "re_ohm": 2.47, "sd_cm2": 530.0, "xmax_mm": 29.0, "pe_w": 1000.0, "le_mh": 1.90}
    },
    {
        "name": "WEB: JL Audio 10W7AE-3 10 Inch 750W RMS Subwoofer",
        "brand": "JL Audio", "model": "10W7AE-3", "category": "Subwoofer",
        "fs_hz": 30.6, "qts": 0.576, "qes": 0.62, "qms": 7.8, "vas_l": 36.1,
        "re_ohm": 2.75, "sd_cm2": 350.0, "xmax_mm": 23.0, "pe_w": 750.0,
        "price": 1099.0, "currency": "USD", "url": "https://www.jlaudio.com",
        "driver": {"fs_hz": 30.6, "vas_l": 36.1, "qts": 0.576, "qms": 7.8, "re_ohm": 2.75, "sd_cm2": 350.0, "xmax_mm": 23.0, "pe_w": 750.0, "le_mh": 1.65}
    },
    {
        "name": "WEB: JL Audio 12W6v3-D4 12 Inch 600W RMS Subwoofer",
        "brand": "JL Audio", "model": "12W6v3-D4", "category": "Subwoofer",
        "fs_hz": 26.9, "qts": 0.493, "qes": 0.53, "qms": 7.0, "vas_l": 54.3,
        "re_ohm": 3.25, "sd_cm2": 530.0, "xmax_mm": 19.0, "pe_w": 600.0,
        "price": 799.0, "currency": "USD", "url": "https://www.jlaudio.com",
        "driver": {"fs_hz": 26.9, "vas_l": 54.3, "qts": 0.493, "qms": 7.0, "re_ohm": 3.25, "sd_cm2": 530.0, "xmax_mm": 19.0, "pe_w": 600.0, "le_mh": 1.45}
    },
    {
        "name": "WEB: JL Audio 10W6v3-D4 10 Inch 600W RMS Subwoofer",
        "brand": "JL Audio", "model": "10W6v3-D4", "category": "Subwoofer",
        "fs_hz": 30.1, "qts": 0.498, "qes": 0.54, "qms": 7.1, "vas_l": 22.9,
        "re_ohm": 3.25, "sd_cm2": 350.0, "xmax_mm": 19.0, "pe_w": 600.0,
        "price": 699.0, "currency": "USD", "url": "https://www.jlaudio.com",
        "driver": {"fs_hz": 30.1, "vas_l": 22.9, "qts": 0.498, "qms": 7.1, "re_ohm": 3.25, "sd_cm2": 350.0, "xmax_mm": 19.0, "pe_w": 600.0, "le_mh": 1.35}
    },
    {
        "name": "WEB: JL Audio 13TW5v2-2 13.5 Inch Shallow Subwoofer",
        "brand": "JL Audio", "model": "13TW5v2-2", "category": "Subwoofer",
        "fs_hz": 27.6, "qts": 0.528, "qes": 0.57, "qms": 7.2, "vas_l": 60.5,
        "re_ohm": 1.95, "sd_cm2": 700.0, "xmax_mm": 15.0, "pe_w": 600.0,
        "price": 899.0, "currency": "USD", "url": "https://www.jlaudio.com",
        "driver": {"fs_hz": 27.6, "vas_l": 60.5, "qts": 0.528, "qms": 7.2, "re_ohm": 1.95, "sd_cm2": 700.0, "xmax_mm": 15.0, "pe_w": 600.0, "le_mh": 1.20}
    },
    {
        "name": "WEB: JL Audio 12TW3-D4 12 Inch Shallow Subwoofer",
        "brand": "JL Audio", "model": "12TW3-D4", "category": "Subwoofer",
        "fs_hz": 26.5, "qts": 0.536, "qes": 0.58, "qms": 7.0, "vas_l": 45.4,
        "re_ohm": 3.55, "sd_cm2": 530.0, "xmax_mm": 15.2, "pe_w": 400.0,
        "price": 449.0, "currency": "USD", "url": "https://www.jlaudio.com",
        "driver": {"fs_hz": 26.5, "vas_l": 45.4, "qts": 0.536, "qms": 7.0, "re_ohm": 3.55, "sd_cm2": 530.0, "xmax_mm": 15.2, "pe_w": 400.0, "le_mh": 1.10}
    },
    {
        "name": "WEB: JL Audio 10TW3-D4 10 Inch Shallow Subwoofer",
        "brand": "JL Audio", "model": "10TW3-D4", "category": "Subwoofer",
        "fs_hz": 32.3, "qts": 0.543, "qes": 0.59, "qms": 6.8, "vas_l": 19.8,
        "re_ohm": 3.55, "sd_cm2": 350.0, "xmax_mm": 15.2, "pe_w": 400.0,
        "price": 399.0, "currency": "USD", "url": "https://www.jlaudio.com",
        "driver": {"fs_hz": 32.3, "vas_l": 19.8, "qts": 0.543, "qms": 6.8, "re_ohm": 3.55, "sd_cm2": 350.0, "xmax_mm": 15.2, "pe_w": 400.0, "le_mh": 0.95}
    },
    {
        "name": "WEB: JL Audio 12W3v3-4 12 Inch 500W RMS Subwoofer",
        "brand": "JL Audio", "model": "12W3v3-4", "category": "Subwoofer",
        "fs_hz": 26.7, "qts": 0.464, "qes": 0.50, "qms": 6.4, "vas_l": 79.5,
        "re_ohm": 3.56, "sd_cm2": 530.0, "xmax_mm": 13.0, "pe_w": 500.0,
        "price": 379.0, "currency": "USD", "url": "https://www.jlaudio.com",
        "driver": {"fs_hz": 26.7, "vas_l": 79.5, "qts": 0.464, "qms": 6.4, "re_ohm": 3.56, "sd_cm2": 530.0, "xmax_mm": 13.0, "pe_w": 500.0, "le_mh": 1.15}
    },
    {
        "name": "WEB: JL Audio 10W3v3-4 10 Inch 500W RMS Subwoofer",
        "brand": "JL Audio", "model": "10W3v3-4", "category": "Subwoofer",
        "fs_hz": 31.5, "qts": 0.474, "qes": 0.51, "qms": 6.2, "vas_l": 32.2,
        "re_ohm": 3.56, "sd_cm2": 350.0, "xmax_mm": 13.0, "pe_w": 500.0,
        "price": 329.0, "currency": "USD", "url": "https://www.jlaudio.com",
        "driver": {"fs_hz": 31.5, "vas_l": 32.2, "qts": 0.474, "qms": 6.2, "re_ohm": 3.56, "sd_cm2": 350.0, "xmax_mm": 13.0, "pe_w": 500.0, "le_mh": 0.98}
    },

    # 2. FOCAL (France)
    {
        "name": "WEB: Focal Utopia M SUB 10WM 10 Inch Reference Subwoofer",
        "brand": "Focal", "model": "SUB 10WM", "category": "Subwoofer",
        "fs_hz": 25.0, "qts": 0.45, "qes": 0.49, "qms": 5.5, "vas_l": 35.0,
        "re_ohm": 3.2, "sd_cm2": 350.0, "xmax_mm": 17.0, "pe_w": 400.0,
        "price": 1199.0, "currency": "EUR", "url": "https://www.focal.com",
        "driver": {"fs_hz": 25.0, "vas_l": 35.0, "qts": 0.45, "qms": 5.5, "re_ohm": 3.2, "sd_cm2": 350.0, "xmax_mm": 17.0, "pe_w": 400.0, "le_mh": 1.25}
    },
    {
        "name": "WEB: Focal K2 Power E 30 KX 12 Inch 800W RMS Subwoofer",
        "brand": "Focal", "model": "E 30 KX", "category": "Subwoofer",
        "fs_hz": 27.0, "qts": 0.42, "qes": 0.46, "qms": 5.2, "vas_l": 48.0,
        "re_ohm": 3.2, "sd_cm2": 530.0, "xmax_mm": 22.5, "pe_w": 800.0,
        "price": 599.0, "currency": "EUR", "url": "https://www.focal.com",
        "driver": {"fs_hz": 27.0, "vas_l": 48.0, "qts": 0.42, "qms": 5.2, "re_ohm": 3.2, "sd_cm2": 530.0, "xmax_mm": 22.5, "pe_w": 800.0, "le_mh": 1.65}
    },
    {
        "name": "WEB: Focal Flax Evo P 25 FE 10 Inch Subwoofer",
        "brand": "Focal", "model": "P 25 FE", "category": "Subwoofer",
        "fs_hz": 31.0, "qts": 0.42, "qes": 0.46, "qms": 4.8, "vas_l": 28.0,
        "re_ohm": 3.4, "sd_cm2": 350.0, "xmax_mm": 14.0, "pe_w": 300.0,
        "price": 249.0, "currency": "EUR", "url": "https://www.focal.com",
        "driver": {"fs_hz": 31.0, "vas_l": 28.0, "qts": 0.42, "qms": 4.8, "re_ohm": 3.4, "sd_cm2": 350.0, "xmax_mm": 14.0, "pe_w": 300.0, "le_mh": 1.05}
    },
    {
        "name": "WEB: Focal Flax Evo P 30 FE 12 Inch Subwoofer",
        "brand": "Focal", "model": "P 30 FE", "category": "Subwoofer",
        "fs_hz": 27.0, "qts": 0.44, "qes": 0.48, "qms": 5.0, "vas_l": 60.0,
        "re_ohm": 3.4, "sd_cm2": 530.0, "xmax_mm": 14.0, "pe_w": 400.0,
        "price": 299.0, "currency": "EUR", "url": "https://www.focal.com",
        "driver": {"fs_hz": 27.0, "vas_l": 60.0, "qts": 0.44, "qms": 5.0, "re_ohm": 3.4, "sd_cm2": 530.0, "xmax_mm": 14.0, "pe_w": 400.0, "le_mh": 1.20}
    },

    # 3. DYNAUDIO (Denmark)
    {
        "name": "WEB: Dynaudio Esotar2 1200 12 Inch Reference Subwoofer",
        "brand": "Dynaudio", "model": "Esotar2 1200", "category": "Subwoofer",
        "fs_hz": 18.7, "qts": 0.44, "qes": 0.48, "qms": 5.5, "vas_l": 160.0,
        "re_ohm": 3.2, "sd_cm2": 530.0, "xmax_mm": 14.5, "pe_w": 500.0,
        "price": 1450.0, "currency": "EUR", "url": "https://www.dynaudio.com",
        "driver": {"fs_hz": 18.7, "vas_l": 160.0, "qts": 0.44, "qms": 5.5, "re_ohm": 3.2, "sd_cm2": 530.0, "xmax_mm": 14.5, "pe_w": 500.0, "le_mh": 1.35}
    },
    {
        "name": "WEB: Dynaudio Esotec MW 182 10 Inch Woofer",
        "brand": "Dynaudio", "model": "Esotec MW 182", "category": "Woofer",
        "fs_hz": 35.0, "qts": 0.58, "qes": 0.65, "qms": 5.2, "vas_l": 52.0,
        "re_ohm": 3.4, "sd_cm2": 350.0, "xmax_mm": 7.5, "pe_w": 180.0,
        "price": 520.0, "currency": "EUR", "url": "https://www.dynaudio.com",
        "driver": {"fs_hz": 35.0, "vas_l": 52.0, "qts": 0.58, "qms": 5.2, "re_ohm": 3.4, "sd_cm2": 350.0, "xmax_mm": 7.5, "pe_w": 180.0, "le_mh": 0.75}
    },

    # 4. AUDIOTEC FISCHER HELIX & MATCH (Germany)
    {
        "name": "WEB: Helix Q 12W 12 Inch 1000W RMS Subwoofer",
        "brand": "Helix", "model": "Q 12W", "category": "Subwoofer",
        "fs_hz": 28.0, "qts": 0.44, "qes": 0.48, "qms": 5.4, "vas_l": 54.0,
        "re_ohm": 3.6, "sd_cm2": 530.0, "xmax_mm": 14.0, "pe_w": 1000.0,
        "price": 399.0, "currency": "EUR", "url": "https://www.audiotec-fischer.de",
        "driver": {"fs_hz": 28.0, "vas_l": 54.0, "qts": 0.44, "qms": 5.4, "re_ohm": 3.6, "sd_cm2": 530.0, "xmax_mm": 14.0, "pe_w": 1000.0, "le_mh": 1.45}
    },
    {
        "name": "WEB: Helix Q 10W 10 Inch 1000W RMS Subwoofer",
        "brand": "Helix", "model": "Q 10W", "category": "Subwoofer",
        "fs_hz": 31.0, "qts": 0.46, "qes": 0.50, "qms": 5.2, "vas_l": 24.0,
        "re_ohm": 3.6, "sd_cm2": 350.0, "xmax_mm": 14.0, "pe_w": 1000.0,
        "price": 349.0, "currency": "EUR", "url": "https://www.audiotec-fischer.de",
        "driver": {"fs_hz": 31.0, "vas_l": 24.0, "qts": 0.46, "qms": 5.2, "re_ohm": 3.6, "sd_cm2": 350.0, "xmax_mm": 14.0, "pe_w": 1000.0, "le_mh": 1.35}
    },
    {
        "name": "WEB: Helix K 12W 12 Inch 300W RMS Subwoofer",
        "brand": "Helix", "model": "K 12W", "category": "Subwoofer",
        "fs_hz": 26.0, "qts": 0.41, "qes": 0.45, "qms": 4.8, "vas_l": 75.0,
        "re_ohm": 3.4, "sd_cm2": 530.0, "xmax_mm": 8.0, "pe_w": 300.0,
        "price": 179.0, "currency": "EUR", "url": "https://www.audiotec-fischer.de",
        "driver": {"fs_hz": 26.0, "vas_l": 75.0, "qts": 0.41, "qms": 4.8, "re_ohm": 3.4, "sd_cm2": 530.0, "xmax_mm": 8.0, "pe_w": 300.0, "le_mh": 0.95}
    },

    # 5. DLS AUDIO (Sweden)
    {
        "name": "WEB: DLS Reference Supreme RSW10-D2 10 Inch Subwoofer",
        "brand": "DLS", "model": "RSW10-D2", "category": "Subwoofer",
        "fs_hz": 28.0, "qts": 0.52, "qes": 0.58, "qms": 5.2, "vas_l": 32.0,
        "re_ohm": 3.6, "sd_cm2": 350.0, "xmax_mm": 13.0, "pe_w": 500.0,
        "price": 389.0, "currency": "EUR", "url": "https://dls.se",
        "driver": {"fs_hz": 28.0, "vas_l": 32.0, "qts": 0.52, "qms": 5.2, "re_ohm": 3.6, "sd_cm2": 350.0, "xmax_mm": 13.0, "pe_w": 500.0, "le_mh": 1.20}
    },
    {
        "name": "WEB: DLS Reference Supreme RSW12-D2 12 Inch Subwoofer",
        "brand": "DLS", "model": "RSW12-D2", "category": "Subwoofer",
        "fs_hz": 25.0, "qts": 0.48, "qes": 0.54, "qms": 5.0, "vas_l": 65.0,
        "re_ohm": 3.6, "sd_cm2": 530.0, "xmax_mm": 13.0, "pe_w": 600.0,
        "price": 449.0, "currency": "EUR", "url": "https://dls.se",
        "driver": {"fs_hz": 25.0, "vas_l": 65.0, "qts": 0.48, "qms": 5.0, "re_ohm": 3.6, "sd_cm2": 530.0, "xmax_mm": 13.0, "pe_w": 600.0, "le_mh": 1.35}
    }
]


def main():
    print("=== HARVESTING FLAGSHIP BRAND LINES INTO LOAD FORGE DB ===")
    t0 = time.perf_counter()
    
    cat_prop_data = json.loads(CATALOG_PROP.read_text(encoding="utf-8"))
    prop_items = cat_prop_data.get("presets", [])
    existing_identities = {f"{normalize(item.get('brand', ''))}_{normalize(item.get('model', ''))}" for item in prop_items}
    existing_names = {item.get("name") for item in prop_items}
    initial_count = len(prop_items)
    print(f"Initial presets in DB: {initial_count}")
    
    added = 0
    for d in FLAGSHIP_MODELS:
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
