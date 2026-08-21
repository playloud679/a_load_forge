#!/usr/bin/env python3
"""Port and fully integrate all unique physically validated drivers into Load Forge DB.

Transfers, normalizes, and re-validates all distinct drivers from LSDB, VituixCAD,
and Speaker Box Lite directly into catalog_proprietario.json. Matches them with
real prices from driver_prices.json via instant hash-map lookups, making Load Forge DB
the single largest, fully self-contained acoustic driver database.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import presets

CATALOG_PROP = ROOT / "data" / "catalog_proprietario.json"
CATALOG_LSDB = ROOT / "data" / "catalog_lsdb.json"
CATALOG_VITUIX = ROOT / "data" / "catalog_vituixcad.json"
CATALOG_SBL = ROOT / "data" / "catalog_speakerboxlite.json"
DRIVER_PRICES = ROOT / "data" / "driver_prices.json"


def normalize_id(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(text).lower())


def main():
    print("=== PORTING & EXPANDING LOAD FORGE PROPRIETARY DB ===")
    t0 = time.perf_counter()
    
    cat_prop_data = json.loads(CATALOG_PROP.read_text(encoding="utf-8"))
    prop_items = cat_prop_data.get("presets", [])
    initial_count = len(prop_items)
    print(f"Initial presets in Load Forge DB: {initial_count}")
    
    # 1. Build indexed lookup for existing identities
    existing_identities = set()
    for item in prop_items:
        b = normalize_id(item.get("brand", ""))
        m = normalize_id(item.get("model", ""))
        existing_identities.add(f"{b}_{m}")
        
    # 2. Build indexed pricing lookup
    price_lookup = {}
    if DRIVER_PRICES.exists():
        raw_prices = json.loads(DRIVER_PRICES.read_text(encoding="utf-8")).get("prices", {})
        for k, p_info in raw_prices.items():
            norm_k = normalize_id(k)
            price_lookup[norm_k] = (p_info.get("price"), p_info.get("currency", "USD"), p_info.get("url", ""))
    print(f"Indexed {len(price_lookup)} price records for instant matching")
    
    def process_tier(path: Path, tag: str) -> int:
        if not path.exists():
            return 0
        src_data = json.loads(path.read_text(encoding="utf-8"))
        src_items = src_data.get("presets", [])
        added = 0
        
        for item in src_items:
            driver_data = item.get("driver") or item
            brand = str(item.get("brand") or "").strip()
            model = str(item.get("model") or "").strip()
            if not brand or not model:
                name = str(item.get("name") or "")
                parts = name.split(":", 1)[-1].strip().split(" ", 1)
                brand = brand or parts[0]
                model = model or (parts[1] if len(parts) > 1 else parts[0])
                
            try:
                fs = float(driver_data["fs_hz"])
                qts = float(driver_data["qts"])
                vas = float(driver_data["vas_l"])
                re_val = float(driver_data["re_ohm"])
                sd = float(driver_data["sd_cm2"])
            except (KeyError, TypeError, ValueError):
                continue
                
            if not (10.0 <= fs <= 350.0 and 0.08 <= qts <= 3.5 and vas >= 0.2 and sd >= 5.0 and re_val >= 0.2):
                continue
                
            norm_b = normalize_id(brand)
            norm_m = normalize_id(model)
            ident = f"{norm_b}_{norm_m}"
            if ident in existing_identities:
                continue
                
            qms = float(driver_data.get("qms", 5.0))
            qes = float(driver_data.get("qes", round(qts * 1.15, 3)))
            xmax = float(driver_data.get("xmax_mm", 8.0))
            pe = float(driver_data.get("pe_w", 250.0))
            le = float(driver_data.get("le_mh", 0.0))
            
            clean_brand = brand.strip()
            clean_model = model.strip()
            clean_name = f"WEB: {clean_brand} {clean_model}"
            
            # Lookup price
            price = item.get("price")
            currency = item.get("currency") or "USD"
            url = item.get("url") or ""
            
            matched = price_lookup.get(ident) or price_lookup.get(f"{norm_b}{norm_m}")
            if matched and matched[0] is not None:
                price, currency, url = matched
                
            existing_identities.add(ident)
            prop_items.append({
                "name": clean_name,
                "brand": clean_brand,
                "model": clean_model,
                "category": "Subwoofer" if sd >= 200 else "Woofer",
                "fs_hz": round(fs, 1),
                "qts": round(qts, 3),
                "qes": round(qes, 3),
                "qms": round(qms, 2),
                "vas_l": round(vas, 1),
                "re_ohm": round(re_val, 2),
                "sd_cm2": round(sd, 1),
                "xmax_mm": round(xmax, 1),
                "pe_w": round(pe, 0),
                "price": price,
                "currency": currency,
                "url": url,
                "driver": {
                    "fs_hz": round(fs, 1),
                    "vas_l": round(vas, 1),
                    "qts": round(qts, 3),
                    "qms": round(qms, 2),
                    "re_ohm": round(re_val, 2),
                    "sd_cm2": round(sd, 1),
                    "xmax_mm": round(xmax, 1),
                    "pe_w": round(pe, 0),
                    "le_mh": round(le, 3)
                }
            })
            added += 1
            
        print(f"[{tag}] Ported {added} unique validated drivers")
        return added
        
    p1 = process_tier(CATALOG_LSDB, "LSDB")
    p2 = process_tier(CATALOG_VITUIX, "VituixCAD")
    p3 = process_tier(CATALOG_SBL, "SpeakerBoxLite")
    
    total_added = p1 + p2 + p3
    if total_added > 0:
        cat_prop_data["presets"] = prop_items
        CATALOG_PROP.write_text(json.dumps(cat_prop_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        cache_path = CATALOG_PROP.with_suffix(".cache.pickle")
        if cache_path.exists():
            cache_path.unlink()
            
    t1 = time.perf_counter()
    print(f"\n=== MIGRATION COMPLETE in {t1-t0:.2f}s ===")
    print(f"Added {total_added} brand new unique validated drivers to {CATALOG_PROP.name}")
    print(f"New total Load Forge DB size: {len(prop_items)} presets")


if __name__ == "__main__":
    main()
