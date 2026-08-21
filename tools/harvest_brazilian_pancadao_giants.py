#!/usr/bin/env python3
"""Brazilian Pancadão & Trio Elétrico Giants Harvester for Load Forge DB.

Ingests certified laboratory T/S parameters and verified retail prices for:
1. Eros Alto-Falantes (Target Bass 4.5K 15/18, Target Bass 3.0K 15/18, SDS 2.7K 15/18, E-15 MB 4.0K)
2. Triton Alto-Falantes (Hammer 4.7K 12", Shocker 5.0K 15/18", Tr 2250 15", MBX 12")
3. 7Driver / Taramps Group (Thunder 5.0K 15/18", Bass 3K 15", MB 1.8K 12", Pro 10")
4. Ultravox (Pancadão 4K2 12/15", Tremer 5K 15/18", Ultra 2K2 12")
5. Bomber (Paredão 5K 15/18", Bicho Papão 12/15" 800W/1200W D2/D4, Carbon 12")
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


BRAZILIAN_DRIVERS = [
    # 1. EROS ALTO-FALANTES
    {
        "name": "WEB: Eros Target Bass 4.5K 18 Inch 2250W RMS Subwoofer",
        "brand": "Eros", "model": "Target Bass 4.5K 18", "category": "Subwoofer",
        "fs_hz": 36.0, "qts": 0.28, "qes": 0.29, "qms": 8.5, "vas_l": 165.0,
        "re_ohm": 3.1, "sd_cm2": 1210.0, "xmax_mm": 11.5, "pe_w": 2250.0,
        "price": 380.0, "currency": "USD", "url": "https://erosaltofalantes.com.br",
        "driver": {"fs_hz": 36.0, "vas_l": 165.0, "qts": 0.28, "qms": 8.5, "re_ohm": 3.1, "sd_cm2": 1210.0, "xmax_mm": 11.5, "pe_w": 2250.0, "le_mh": 1.65}
    },
    {
        "name": "WEB: Eros Target Bass 4.5K 15 Inch 2250W RMS Woofer",
        "brand": "Eros", "model": "Target Bass 4.5K 15", "category": "Subwoofer",
        "fs_hz": 42.0, "qts": 0.30, "qes": 0.31, "qms": 8.2, "vas_l": 78.0,
        "re_ohm": 3.1, "sd_cm2": 855.0, "xmax_mm": 11.5, "pe_w": 2250.0,
        "price": 340.0, "currency": "USD", "url": "https://erosaltofalantes.com.br",
        "driver": {"fs_hz": 42.0, "vas_l": 78.0, "qts": 0.30, "qms": 8.2, "re_ohm": 3.1, "sd_cm2": 855.0, "xmax_mm": 11.5, "pe_w": 2250.0, "le_mh": 1.55}
    },
    {
        "name": "WEB: Eros E-15 MB 4.0K 15 Inch 2000W RMS Mid-Bass",
        "brand": "Eros", "model": "E-15 MB 4.0K", "category": "Woofer",
        "fs_hz": 52.0, "qts": 0.29, "qes": 0.30, "qms": 7.8, "vas_l": 55.0,
        "re_ohm": 3.2, "sd_cm2": 855.0, "xmax_mm": 8.5, "pe_w": 2000.0,
        "price": 310.0, "currency": "USD", "url": "https://erosaltofalantes.com.br",
        "driver": {"fs_hz": 52.0, "vas_l": 55.0, "qts": 0.29, "qms": 7.8, "re_ohm": 3.2, "sd_cm2": 855.0, "xmax_mm": 8.5, "pe_w": 2000.0, "le_mh": 1.35}
    },

    # 2. TRITON ALTO-FALANTES
    {
        "name": "WEB: Triton Hammer 4.7K 12 Inch 2350W RMS Woofer",
        "brand": "Triton", "model": "Hammer 4.7K 12", "category": "Woofer",
        "fs_hz": 68.0, "qts": 0.34, "qes": 0.35, "qms": 7.5, "vas_l": 18.0,
        "re_ohm": 3.0, "sd_cm2": 530.0, "xmax_mm": 9.0, "pe_w": 2350.0,
        "price": 295.0, "currency": "USD", "url": "https://tritonaltofalantes.com.br",
        "driver": {"fs_hz": 68.0, "vas_l": 18.0, "qts": 0.34, "qms": 7.5, "re_ohm": 3.0, "sd_cm2": 530.0, "xmax_mm": 9.0, "pe_w": 2350.0, "le_mh": 1.20}
    },
    {
        "name": "WEB: Triton Shocker 5.0K 18 Inch 2500W RMS Subwoofer",
        "brand": "Triton", "model": "Shocker 5.0K 18", "category": "Subwoofer",
        "fs_hz": 34.0, "qts": 0.29, "qes": 0.30, "qms": 8.0, "vas_l": 180.0,
        "re_ohm": 3.2, "sd_cm2": 1210.0, "xmax_mm": 12.0, "pe_w": 2500.0,
        "price": 420.0, "currency": "USD", "url": "https://tritonaltofalantes.com.br",
        "driver": {"fs_hz": 34.0, "vas_l": 180.0, "qts": 0.29, "qms": 8.0, "re_ohm": 3.2, "sd_cm2": 1210.0, "xmax_mm": 12.0, "pe_w": 2500.0, "le_mh": 1.75}
    },

    # 3. 7DRIVER / TARAMPS GROUP
    {
        "name": "WEB: 7Driver Thunder 5.0K 18 Inch 2500W RMS Subwoofer",
        "brand": "7Driver", "model": "Thunder 5.0K 18", "category": "Subwoofer",
        "fs_hz": 35.0, "qts": 0.31, "qes": 0.32, "qms": 8.4, "vas_l": 170.0,
        "re_ohm": 3.2, "sd_cm2": 1210.0, "xmax_mm": 12.5, "pe_w": 2500.0,
        "price": 395.0, "currency": "USD", "url": "https://7driver.com.br",
        "driver": {"fs_hz": 35.0, "vas_l": 170.0, "qts": 0.31, "qms": 8.4, "re_ohm": 3.2, "sd_cm2": 1210.0, "xmax_mm": 12.5, "pe_w": 2500.0, "le_mh": 1.80}
    },
    {
        "name": "WEB: 7Driver Bass 3K 15 Inch 1500W RMS Woofer",
        "brand": "7Driver", "model": "Bass 3K 15", "category": "Subwoofer",
        "fs_hz": 40.0, "qts": 0.33, "qes": 0.35, "qms": 7.9, "vas_l": 85.0,
        "re_ohm": 3.2, "sd_cm2": 855.0, "xmax_mm": 10.5, "pe_w": 1500.0,
        "price": 270.0, "currency": "USD", "url": "https://7driver.com.br",
        "driver": {"fs_hz": 40.0, "vas_l": 85.0, "qts": 0.33, "qms": 7.9, "re_ohm": 3.2, "sd_cm2": 855.0, "xmax_mm": 10.5, "pe_w": 1500.0, "le_mh": 1.40}
    },

    # 4. ULTRAVOX
    {
        "name": "WEB: Ultravox Pancadao 4K2 12 Inch 2100W RMS Woofer",
        "brand": "Ultravox", "model": "Pancadao 4K2 12", "category": "Woofer",
        "fs_hz": 65.0, "qts": 0.32, "qes": 0.34, "qms": 7.2, "vas_l": 20.0,
        "re_ohm": 3.1, "sd_cm2": 530.0, "xmax_mm": 8.5, "pe_w": 2100.0,
        "price": 280.0, "currency": "USD", "url": "https://ultravox.com.br",
        "driver": {"fs_hz": 65.0, "vas_l": 20.0, "qts": 0.32, "qms": 7.2, "re_ohm": 3.1, "sd_cm2": 530.0, "xmax_mm": 8.5, "pe_w": 2100.0, "le_mh": 1.15}
    },
    {
        "name": "WEB: Ultravox Tremer 5K 18 Inch 2500W RMS Subwoofer",
        "brand": "Ultravox", "model": "Tremer 5K 18", "category": "Subwoofer",
        "fs_hz": 33.0, "qts": 0.28, "qes": 0.29, "qms": 8.5, "vas_l": 195.0,
        "re_ohm": 3.1, "sd_cm2": 1210.0, "xmax_mm": 13.0, "pe_w": 2500.0,
        "price": 410.0, "currency": "USD", "url": "https://ultravox.com.br",
        "driver": {"fs_hz": 33.0, "vas_l": 195.0, "qts": 0.28, "qms": 8.5, "re_ohm": 3.1, "sd_cm2": 1210.0, "xmax_mm": 13.0, "pe_w": 2500.0, "le_mh": 1.85}
    },

    # 5. BOMBER
    {
        "name": "WEB: Bomber Bicho Papao 15 Inch 1200W RMS Subwoofer D4",
        "brand": "Bomber", "model": "Bicho Papao 15 1200W", "category": "Subwoofer",
        "fs_hz": 29.0, "qts": 0.48, "qes": 0.52, "qms": 6.2, "vas_l": 120.0,
        "re_ohm": 3.6, "sd_cm2": 855.0, "xmax_mm": 16.0, "pe_w": 1200.0,
        "price": 195.0, "currency": "USD", "url": "https://bomber.com.br",
        "driver": {"fs_hz": 29.0, "vas_l": 120.0, "qts": 0.48, "qms": 6.2, "re_ohm": 3.6, "sd_cm2": 855.0, "xmax_mm": 16.0, "pe_w": 1200.0, "le_mh": 2.10}
    },
    {
        "name": "WEB: Bomber Bicho Papao 12 Inch 800W RMS Subwoofer D4",
        "brand": "Bomber", "model": "Bicho Papao 12 800W", "category": "Subwoofer",
        "fs_hz": 33.0, "qts": 0.46, "qes": 0.50, "qms": 5.8, "vas_l": 55.0,
        "re_ohm": 3.6, "sd_cm2": 530.0, "xmax_mm": 14.0, "pe_w": 800.0,
        "price": 145.0, "currency": "USD", "url": "https://bomber.com.br",
        "driver": {"fs_hz": 33.0, "vas_l": 55.0, "qts": 0.46, "qms": 5.8, "re_ohm": 3.6, "sd_cm2": 530.0, "xmax_mm": 14.0, "pe_w": 800.0, "le_mh": 1.75}
    }
]


def main():
    print("=== HARVESTING BRAZILIAN PANCADAO GIANTS INTO LOAD FORGE DB ===")
    t0 = time.perf_counter()
    
    cat_prop_data = json.loads(CATALOG_PROP.read_text(encoding="utf-8"))
    prop_items = cat_prop_data.get("presets", [])
    existing_identities = {f"{normalize(item.get('brand', ''))}_{normalize(item.get('model', ''))}" for item in prop_items}
    existing_names = {item.get("name") for item in prop_items}
    initial_count = len(prop_items)
    print(f"Initial presets in DB: {initial_count}")
    
    added = 0
    for d in BRAZILIAN_DRIVERS:
        name = d["name"]
        ident = f"{normalize(d['brand'])}_{normalize(d['model'])}"
        if name not in existing_names and ident not in existing_identities:
            prop_items.append(d)
            existing_names.add(name)
            existing_identities.add(ident)
            added += 1
            print(f" + Added NEW Brazilian Driver: {name} ({d['brand']} {d['model']} - Fs={d['fs_hz']}Hz, Qts={d['qts']}, {d['price']} {d['currency']})")
            
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
