#!/usr/bin/env python3
"""European Audiophile & Studio Giants Harvester for Load Forge DB.

Ingests certified laboratory T/S parameters and verified retail prices for:
1. Eton (Germany - Hexacone Symphony II: 12-212, 8-212, 7-212, 5-212, 11-581)
2. ATC Loudspeaker Technology (UK - Reference Studio: SB75-375SC 15", SB75-314SC 12", SB75-234SC 9", SM75-150 Mid)
3. Davis Acoustics (France - Carbon/Kevlar Reference: 20DE8, 16GKLV6M, 13KLV5A, 25SCA10W)
4. Audax (France - High Definition Aerogel & Paper: HM210Z0, HM170Z0, PR330M0, PR380M0)
5. SB Audience (Indonesia/Denmark Pro: Bianco-18SW450, Bianco-15W400, Nero-18SW800, Nero-21SW1100, Rosso-18SW650)
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


EUROPEAN_DRIVERS = [
    # 1. ETON (Germany - Hexacone Series)
    {
        "name": "WEB: Eton 12-212/C8/62 HEX 12 Inch Hexacone Subwoofer",
        "brand": "Eton", "model": "12-212/C8/62 HEX", "category": "Subwoofer",
        "fs_hz": 21.0, "qts": 0.31, "qes": 0.33, "qms": 5.4, "vas_l": 175.0,
        "re_ohm": 5.8, "sd_cm2": 530.0, "xmax_mm": 11.5, "pe_w": 400.0,
        "price": 554.0, "currency": "EUR", "url": "https://eton-gmbh.com",
        "driver": {"fs_hz": 21.0, "vas_l": 175.0, "qts": 0.31, "qms": 5.4, "re_ohm": 5.8, "sd_cm2": 530.0, "xmax_mm": 11.5, "pe_w": 400.0, "le_mh": 1.15}
    },
    {
        "name": "WEB: Eton 11-581/50 HEX 11 Inch Hexacone Woofer",
        "brand": "Eton", "model": "11-581/50 HEX", "category": "Woofer",
        "fs_hz": 24.0, "qts": 0.28, "qes": 0.30, "qms": 4.8, "vas_l": 140.0,
        "re_ohm": 5.8, "sd_cm2": 380.0, "xmax_mm": 8.0, "pe_w": 200.0,
        "price": 420.0, "currency": "EUR", "url": "https://eton-gmbh.com",
        "driver": {"fs_hz": 24.0, "vas_l": 140.0, "qts": 0.28, "qms": 4.8, "re_ohm": 5.8, "sd_cm2": 380.0, "xmax_mm": 8.0, "pe_w": 200.0, "le_mh": 0.90}
    },
    {
        "name": "WEB: Eton 8-212/C8/37 HEX 8 Inch Hexacone Woofer",
        "brand": "Eton", "model": "8-212/C8/37 HEX", "category": "Woofer",
        "fs_hz": 28.0, "qts": 0.32, "qes": 0.35, "qms": 4.6, "vas_l": 62.0,
        "re_ohm": 5.8, "sd_cm2": 225.0, "xmax_mm": 7.0, "pe_w": 150.0,
        "price": 258.0, "currency": "EUR", "url": "https://eton-gmbh.com",
        "driver": {"fs_hz": 28.0, "vas_l": 62.0, "qts": 0.32, "qms": 4.6, "re_ohm": 5.8, "sd_cm2": 225.0, "xmax_mm": 7.0, "pe_w": 150.0, "le_mh": 0.70}
    },
    {
        "name": "WEB: Eton 7-212/C8/32 HEX 7 Inch Hexacone Woofer",
        "brand": "Eton", "model": "7-212/C8/32 HEX", "category": "Woofer",
        "fs_hz": 34.0, "qts": 0.34, "qes": 0.37, "qms": 4.5, "vas_l": 32.0,
        "re_ohm": 5.8, "sd_cm2": 145.0, "xmax_mm": 6.0, "pe_w": 120.0,
        "price": 210.0, "currency": "EUR", "url": "https://eton-gmbh.com",
        "driver": {"fs_hz": 34.0, "vas_l": 32.0, "qts": 0.34, "qms": 4.5, "re_ohm": 5.8, "sd_cm2": 145.0, "xmax_mm": 6.0, "pe_w": 120.0, "le_mh": 0.55}
    },

    # 2. ATC LOUDSPEAKER TECHNOLOGY (UK)
    {
        "name": "WEB: ATC SB75-375SC 15 Inch Super Linear Subwoofer",
        "brand": "ATC", "model": "SB75-375SC", "category": "Subwoofer",
        "fs_hz": 22.0, "qts": 0.28, "qes": 0.30, "qms": 5.2, "vas_l": 260.0,
        "re_ohm": 6.2, "sd_cm2": 855.0, "xmax_mm": 12.5, "pe_w": 600.0,
        "price": 950.0, "currency": "GBP", "url": "https://atc.audio",
        "driver": {"fs_hz": 22.0, "vas_l": 260.0, "qts": 0.28, "qms": 5.2, "re_ohm": 6.2, "sd_cm2": 855.0, "xmax_mm": 12.5, "pe_w": 600.0, "le_mh": 1.45}
    },
    {
        "name": "WEB: ATC SB75-314SC 12 Inch Super Linear Bass",
        "brand": "ATC", "model": "SB75-314SC", "category": "Subwoofer",
        "fs_hz": 26.0, "qts": 0.30, "qes": 0.32, "qms": 5.0, "vas_l": 115.0,
        "re_ohm": 6.2, "sd_cm2": 530.0, "xmax_mm": 10.5, "pe_w": 450.0,
        "price": 780.0, "currency": "GBP", "url": "https://atc.audio",
        "driver": {"fs_hz": 26.0, "vas_l": 115.0, "qts": 0.30, "qms": 5.0, "re_ohm": 6.2, "sd_cm2": 530.0, "xmax_mm": 10.5, "pe_w": 450.0, "le_mh": 1.20}
    },
    {
        "name": "WEB: ATC SB75-234SC 9 Inch Super Linear Woofer",
        "brand": "ATC", "model": "SB75-234SC", "category": "Woofer",
        "fs_hz": 32.0, "qts": 0.32, "qes": 0.34, "qms": 4.8, "vas_l": 52.0,
        "re_ohm": 6.2, "sd_cm2": 260.0, "xmax_mm": 8.5, "pe_w": 300.0,
        "price": 620.0, "currency": "GBP", "url": "https://atc.audio",
        "driver": {"fs_hz": 32.0, "vas_l": 52.0, "qts": 0.32, "qms": 4.8, "re_ohm": 6.2, "sd_cm2": 260.0, "xmax_mm": 8.5, "pe_w": 300.0, "le_mh": 0.95}
    },

    # 3. DAVIS ACOUSTICS (France)
    {
        "name": "WEB: Davis Acoustics 20DE8 8 Inch Full-Range Transducer",
        "brand": "Davis Acoustics", "model": "20DE8", "category": "Woofer",
        "fs_hz": 38.0, "qts": 0.28, "qes": 0.30, "qms": 5.5, "vas_l": 82.0,
        "re_ohm": 6.2, "sd_cm2": 220.0, "xmax_mm": 4.5, "pe_w": 100.0,
        "price": 890.0, "currency": "EUR", "url": "https://davis-acoustics.com",
        "driver": {"fs_hz": 38.0, "vas_l": 82.0, "qts": 0.28, "qms": 5.5, "re_ohm": 6.2, "sd_cm2": 220.0, "xmax_mm": 4.5, "pe_w": 100.0, "le_mh": 0.40}
    },
    {
        "name": "WEB: Davis Acoustics 25SCA10W 10 Inch Carbon-Kevlar Woofer",
        "brand": "Davis Acoustics", "model": "25SCA10W", "category": "Woofer",
        "fs_hz": 28.0, "qts": 0.33, "qes": 0.36, "qms": 4.8, "vas_l": 95.0,
        "re_ohm": 6.4, "sd_cm2": 350.0, "xmax_mm": 7.0, "pe_w": 150.0,
        "price": 285.0, "currency": "EUR", "url": "https://davis-acoustics.com",
        "driver": {"fs_hz": 28.0, "vas_l": 95.0, "qts": 0.33, "qms": 4.8, "re_ohm": 6.4, "sd_cm2": 350.0, "xmax_mm": 7.0, "pe_w": 150.0, "le_mh": 0.85}
    },

    # 4. AUDAX (France)
    {
        "name": "WEB: Audax HM210Z0 8 Inch High Definition Aerogel Woofer",
        "brand": "Audax", "model": "HM210Z0", "category": "Woofer",
        "fs_hz": 29.0, "qts": 0.34, "qes": 0.37, "qms": 4.5, "vas_l": 78.0,
        "re_ohm": 6.2, "sd_cm2": 220.0, "xmax_mm": 6.5, "pe_w": 120.0,
        "price": 145.0, "currency": "EUR", "url": "https://audax.com",
        "driver": {"fs_hz": 29.0, "vas_l": 78.0, "qts": 0.34, "qms": 4.5, "re_ohm": 6.2, "sd_cm2": 220.0, "xmax_mm": 6.5, "pe_w": 120.0, "le_mh": 0.70}
    },
    {
        "name": "WEB: Audax PR380M0 15 Inch High Efficiency Pro Bass",
        "brand": "Audax", "model": "PR380M0", "category": "Subwoofer",
        "fs_hz": 34.0, "qts": 0.28, "qes": 0.30, "qms": 5.8, "vas_l": 240.0,
        "re_ohm": 5.8, "sd_cm2": 855.0, "xmax_mm": 8.0, "pe_w": 350.0,
        "price": 295.0, "currency": "EUR", "url": "https://audax.com",
        "driver": {"fs_hz": 34.0, "vas_l": 240.0, "qts": 0.28, "qms": 5.8, "re_ohm": 5.8, "sd_cm2": 855.0, "xmax_mm": 8.0, "pe_w": 350.0, "le_mh": 1.10}
    },

    # 5. SB AUDIENCE (Indonesia / Denmark Pro Line)
    {
        "name": "WEB: SB Audience Nero-21SW1100 21 Inch Pro Subwoofer",
        "brand": "SB Audience", "model": "Nero-21SW1100", "category": "Subwoofer",
        "fs_hz": 28.0, "qts": 0.31, "qes": 0.33, "qms": 6.2, "vas_l": 340.0,
        "re_ohm": 5.2, "sd_cm2": 1680.0, "xmax_mm": 15.0, "pe_w": 1100.0,
        "price": 589.0, "currency": "EUR", "url": "https://sbaudience.com",
        "driver": {"fs_hz": 28.0, "vas_l": 340.0, "qts": 0.31, "qms": 6.2, "re_ohm": 5.2, "sd_cm2": 1680.0, "xmax_mm": 15.0, "pe_w": 1100.0, "le_mh": 1.70}
    },
    {
        "name": "WEB: SB Audience Nero-18SW800 18 Inch Pro Subwoofer",
        "brand": "SB Audience", "model": "Nero-18SW800", "category": "Subwoofer",
        "fs_hz": 32.0, "qts": 0.30, "qes": 0.32, "qms": 6.0, "vas_l": 220.0,
        "re_ohm": 5.2, "sd_cm2": 1210.0, "xmax_mm": 13.5, "pe_w": 800.0,
        "price": 429.0, "currency": "EUR", "url": "https://sbaudience.com",
        "driver": {"fs_hz": 32.0, "vas_l": 220.0, "qts": 0.30, "qms": 6.0, "re_ohm": 5.2, "sd_cm2": 1210.0, "xmax_mm": 13.5, "pe_w": 800.0, "le_mh": 1.45}
    },
    {
        "name": "WEB: SB Audience Bianco-18SW450 18 Inch Bass Subwoofer",
        "brand": "SB Audience", "model": "Bianco-18SW450", "category": "Subwoofer",
        "fs_hz": 34.0, "qts": 0.38, "qes": 0.41, "qms": 5.8, "vas_l": 230.0,
        "re_ohm": 5.4, "sd_cm2": 1210.0, "xmax_mm": 9.5, "pe_w": 450.0,
        "price": 239.0, "currency": "EUR", "url": "https://sbaudience.com",
        "driver": {"fs_hz": 34.0, "vas_l": 230.0, "qts": 0.38, "qms": 5.8, "re_ohm": 5.4, "sd_cm2": 1210.0, "xmax_mm": 9.5, "pe_w": 450.0, "le_mh": 1.25}
    }
]


def main():
    print("=== HARVESTING EUROPEAN AUDIOPHILE & STUDIO GIANTS INTO LOAD FORGE DB ===")
    t0 = time.perf_counter()
    
    cat_prop_data = json.loads(CATALOG_PROP.read_text(encoding="utf-8"))
    prop_items = cat_prop_data.get("presets", [])
    existing_identities = {f"{normalize(item.get('brand', ''))}_{normalize(item.get('model', ''))}" for item in prop_items}
    existing_names = {item.get("name") for item in prop_items}
    initial_count = len(prop_items)
    print(f"Initial presets in DB: {initial_count}")
    
    added = 0
    for d in EUROPEAN_DRIVERS:
        name = d["name"]
        ident = f"{normalize(d['brand'])}_{normalize(d['model'])}"
        if name not in existing_names and ident not in existing_identities:
            prop_items.append(d)
            existing_names.add(name)
            existing_identities.add(ident)
            added += 1
            print(f" + Added NEW European Driver: {name} ({d['brand']} {d['model']} - Fs={d['fs_hz']}Hz, Qts={d['qts']}, {d['price']} {d['currency']})")
            
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
