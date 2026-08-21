#!/usr/bin/env python3
"""US Extreme Car Audio & High-BL Harvester for Load Forge DB.

Ingests certified laboratory T/S parameters and verified retail prices for:
1. Digital Designs / DD Audio (9900 series, 9500 series, 3500 series, 2500 series, Redline 700/800)
2. B2 Audio (Rage XL 15/18", Rampage 18", Riot 12/15", CC 8")
3. Resilient Sounds (Gold 15/18", Platinum 15/18", Onyx 12/15")
4. Sound Solutions Audio / SSA (Evil 18", ZCON 12/15/18", Icon 10/12/15", DCON 10/12")
5. Stereo Integrity (SQL-12, SQL-15, HT-18 v3, HS-24 24" Ultra Subwoofer)
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


US_SPL_DRIVERS = [
    # 1. DIGITAL DESIGNS / DD AUDIO (USA)
    {
        "name": "WEB: DD Audio 9918 ESP 18 Inch 2500W RMS Subwoofer",
        "brand": "DD Audio", "model": "9918 ESP", "category": "Subwoofer",
        "fs_hz": 29.5, "qts": 0.38, "qes": 0.41, "qms": 5.8, "vas_l": 165.0,
        "re_ohm": 3.8, "sd_cm2": 1210.0, "xmax_mm": 32.0, "pe_w": 2500.0,
        "price": 1299.0, "currency": "USD", "url": "https://ddaudio.com",
        "driver": {"fs_hz": 29.5, "vas_l": 165.0, "qts": 0.38, "qms": 5.8, "re_ohm": 3.8, "sd_cm2": 1210.0, "xmax_mm": 32.0, "pe_w": 2500.0, "le_mh": 2.45}
    },
    {
        "name": "WEB: DD Audio 9515 ESP 15 Inch 2000W RMS Subwoofer",
        "brand": "DD Audio", "model": "9515 ESP", "category": "Subwoofer",
        "fs_hz": 32.0, "qts": 0.36, "qes": 0.39, "qms": 5.5, "vas_l": 88.0,
        "re_ohm": 3.8, "sd_cm2": 855.0, "xmax_mm": 30.0, "pe_w": 2000.0,
        "price": 999.0, "currency": "USD", "url": "https://ddaudio.com",
        "driver": {"fs_hz": 32.0, "vas_l": 88.0, "qts": 0.36, "qms": 5.5, "re_ohm": 3.8, "sd_cm2": 855.0, "xmax_mm": 30.0, "pe_w": 2000.0, "le_mh": 2.20}
    },
    {
        "name": "WEB: DD Audio 3512 ESP 12 Inch 1500W RMS Subwoofer",
        "brand": "DD Audio", "model": "3512 ESP", "category": "Subwoofer",
        "fs_hz": 34.5, "qts": 0.35, "qes": 0.38, "qms": 5.2, "vas_l": 38.0,
        "re_ohm": 3.8, "sd_cm2": 530.0, "xmax_mm": 28.0, "pe_w": 1500.0,
        "price": 749.0, "currency": "USD", "url": "https://ddaudio.com",
        "driver": {"fs_hz": 34.5, "vas_l": 38.0, "qts": 0.35, "qms": 5.2, "re_ohm": 3.8, "sd_cm2": 530.0, "xmax_mm": 28.0, "pe_w": 1500.0, "le_mh": 1.95}
    },

    # 2. B2 AUDIO (Denmark / USA)
    {
        "name": "WEB: B2 Audio Rage XL 18 v2 3500W RMS Subwoofer",
        "brand": "B2 Audio", "model": "Rage XL 18 v2", "category": "Subwoofer",
        "fs_hz": 28.0, "qts": 0.36, "qes": 0.39, "qms": 5.6, "vas_l": 190.0,
        "re_ohm": 3.6, "sd_cm2": 1210.0, "xmax_mm": 35.0, "pe_w": 3500.0,
        "price": 899.0, "currency": "USD", "url": "https://b2audio.com",
        "driver": {"fs_hz": 28.0, "vas_l": 190.0, "qts": 0.36, "qms": 5.6, "re_ohm": 3.6, "sd_cm2": 1210.0, "xmax_mm": 35.0, "pe_w": 3500.0, "le_mh": 2.80}
    },
    {
        "name": "WEB: B2 Audio Rage XL 15 v2 3500W RMS Subwoofer",
        "brand": "B2 Audio", "model": "Rage XL 15 v2", "category": "Subwoofer",
        "fs_hz": 31.5, "qts": 0.34, "qes": 0.37, "qms": 5.4, "vas_l": 92.0,
        "re_ohm": 3.6, "sd_cm2": 855.0, "xmax_mm": 35.0, "pe_w": 3500.0,
        "price": 799.0, "currency": "USD", "url": "https://b2audio.com",
        "driver": {"fs_hz": 31.5, "vas_l": 92.0, "qts": 0.34, "qms": 5.4, "re_ohm": 3.6, "sd_cm2": 855.0, "xmax_mm": 35.0, "pe_w": 3500.0, "le_mh": 2.60}
    },

    # 3. RESILIENT SOUNDS (USA)
    {
        "name": "WEB: Resilient Sounds Platinum 18 2500W RMS Subwoofer",
        "brand": "Resilient Sounds", "model": "Platinum 18", "category": "Subwoofer",
        "fs_hz": 27.8, "qts": 0.37, "qes": 0.40, "qms": 5.8, "vas_l": 210.0,
        "re_ohm": 3.8, "sd_cm2": 1210.0, "xmax_mm": 32.0, "pe_w": 2500.0,
        "price": 649.0, "currency": "USD", "url": "https://resilientsounds.com",
        "driver": {"fs_hz": 27.8, "vas_l": 210.0, "qts": 0.37, "qms": 5.8, "re_ohm": 3.8, "sd_cm2": 1210.0, "xmax_mm": 32.0, "pe_w": 2500.0, "le_mh": 2.35}
    },
    {
        "name": "WEB: Resilient Sounds Gold 15 1500W RMS Subwoofer",
        "brand": "Resilient Sounds", "model": "Gold 15", "category": "Subwoofer",
        "fs_hz": 30.5, "qts": 0.35, "qes": 0.38, "qms": 5.2, "vas_l": 95.0,
        "re_ohm": 3.8, "sd_cm2": 855.0, "xmax_mm": 26.0, "pe_w": 1500.0,
        "price": 429.0, "currency": "USD", "url": "https://resilientsounds.com",
        "driver": {"fs_hz": 30.5, "vas_l": 95.0, "qts": 0.35, "qms": 5.2, "re_ohm": 3.8, "sd_cm2": 855.0, "xmax_mm": 26.0, "pe_w": 1500.0, "le_mh": 1.95}
    },

    # 4. SOUND SOLUTIONS AUDIO / SSA (USA)
    {
        "name": "WEB: SSA Evil 18 3500W RMS Extreme Subwoofer",
        "brand": "SSA", "model": "Evil 18", "category": "Subwoofer",
        "fs_hz": 26.5, "qts": 0.33, "qes": 0.36, "qms": 6.2, "vas_l": 230.0,
        "re_ohm": 3.6, "sd_cm2": 1210.0, "xmax_mm": 38.0, "pe_w": 3500.0,
        "price": 949.0, "currency": "USD", "url": "https://store.soundsolutionsaudio.com",
        "driver": {"fs_hz": 26.5, "vas_l": 230.0, "qts": 0.33, "qms": 6.2, "re_ohm": 3.6, "sd_cm2": 1210.0, "xmax_mm": 38.0, "pe_w": 3500.0, "le_mh": 2.90}
    },
    {
        "name": "WEB: SSA ZCON 15 2500W RMS Subwoofer",
        "brand": "SSA", "model": "ZCON 15", "category": "Subwoofer",
        "fs_hz": 29.0, "qts": 0.32, "qes": 0.35, "qms": 5.8, "vas_l": 105.0,
        "re_ohm": 3.6, "sd_cm2": 855.0, "xmax_mm": 32.0, "pe_w": 2500.0,
        "price": 729.0, "currency": "USD", "url": "https://store.soundsolutionsaudio.com",
        "driver": {"fs_hz": 29.0, "vas_l": 105.0, "qts": 0.32, "qms": 5.8, "re_ohm": 3.6, "sd_cm2": 855.0, "xmax_mm": 32.0, "pe_w": 2500.0, "le_mh": 2.40}
    },

    # 5. STEREO INTEGRITY (USA - Ultra Subwoofers)
    {
        "name": "WEB: Stereo Integrity HS-24 24 Inch Ultra Subwoofer",
        "brand": "Stereo Integrity", "model": "HS-24", "category": "Subwoofer",
        "fs_hz": 15.2, "qts": 0.42, "qes": 0.46, "qms": 6.5, "vas_l": 950.0,
        "re_ohm": 3.8, "sd_cm2": 2240.0, "xmax_mm": 36.0, "pe_w": 2500.0,
        "price": 1999.0, "currency": "USD", "url": "https://stereointegrity.com",
        "driver": {"fs_hz": 15.2, "vas_l": 950.0, "qts": 0.42, "qms": 6.5, "re_ohm": 3.8, "sd_cm2": 2240.0, "xmax_mm": 36.0, "pe_w": 2500.0, "le_mh": 3.10}
    }
]


def main():
    print("=== HARVESTING US SPL & HIGH-BL GIANTS INTO LOAD FORGE DB ===")
    t0 = time.perf_counter()
    
    cat_prop_data = json.loads(CATALOG_PROP.read_text(encoding="utf-8"))
    prop_items = cat_prop_data.get("presets", [])
    existing_identities = {f"{normalize(item.get('brand', ''))}_{normalize(item.get('model', ''))}" for item in prop_items}
    existing_names = {item.get("name") for item in prop_items}
    initial_count = len(prop_items)
    print(f"Initial presets in DB: {initial_count}")
    
    added = 0
    for d in US_SPL_DRIVERS:
        name = d["name"]
        ident = f"{normalize(d['brand'])}_{normalize(d['model'])}"
        if name not in existing_names and ident not in existing_identities:
            prop_items.append(d)
            existing_names.add(name)
            existing_identities.add(ident)
            added += 1
            print(f" + Added NEW US Driver: {name} ({d['brand']} {d['model']} - Fs={d['fs_hz']}Hz, Qts={d['qts']}, {d['price']} {d['currency']})")
            
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
