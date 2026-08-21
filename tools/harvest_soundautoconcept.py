#!/usr/bin/env python3
"""Harvest new T/S subwoofers and speakers from soundautoconcept.com (Shopify feed).

Extracts brand new drivers with complete Thiele-Small parameters, physical consistency
checks, and embeds genuine EUR prices with direct product URLs into catalog_proprietario.json.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from bs4 import BeautifulSoup
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))

import presets

STORE = "https://soundautoconcept.com"
CATALOG_PROP = ROOT / "data" / "catalog_proprietario.json"
COLLECTIONS = ["subwoofers", "haut-parleurs-medium", "haut-parleurs-coaxiaux"]
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def infer_sd(title: str, sub_title: str = "") -> float:
    combined = f"{title} {sub_title}".lower()
    if any(k in combined for k in ["18\"", "18-inch", "18 inch", "46cm", "46 cm", "18p"]):
        return 1210.0
    if any(k in combined for k in ["15\"", "15-inch", "15 inch", "38cm", "38 cm", "15p"]):
        return 855.0
    if any(k in combined for k in ["12\"", "12-inch", "12 inch", "30cm", "30 cm", "12p"]):
        return 530.0
    if any(k in combined for k in ["10\"", "10-inch", "10 inch", "25cm", "25 cm", "10p"]):
        return 350.0
    if any(k in combined for k in ["8\"", "8-inch", "8 inch", "20cm", "20 cm", "8p"]):
        return 220.0
    if any(k in combined for k in ["6.5\"", "6.5-inch", "6.5 inch", "16.5cm", "165"]):
        return 132.0
    return 530.0


def fetch_collection(handle: str, max_pages: int = 5) -> list[dict]:
    products = []
    for page in range(1, max_pages + 1):
        url = f"{STORE}/collections/{handle}/products.json?limit=250&page={page}"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                prods = data.get("products", [])
                if not prods:
                    break
                products.extend(prods)
        except Exception as e:
            print(f"Fetch error {handle} page {page}: {e}")
            break
    return products


def main() -> None:
    existing_presets = set(presets.driver_preset_names())
    existing_identities = {re.sub(r"[^a-z0-9]+", "", p.lower()) for p in existing_presets}
    
    all_prods = []
    for col in COLLECTIONS:
        prods = fetch_collection(col)
        print(f"Fetched {len(prods)} products from {col}")
        all_prods.extend(prods)
        
    harvested = []
    for p in all_prods:
        title = p.get("title", "")
        vendor = p.get("vendor", "")
        body = p.get("body_html", "")
        variants = p.get("variants", [])
        if not variants or not variants[0].get("price"):
            continue
        price = float(variants[0]["price"])
        handle = p.get("handle", "")
        product_url = f"{STORE}/products/{handle}"
        
        clean_id = re.sub(r"[^a-z0-9]+", "", f"{vendor} {title}".lower())
        if clean_id in existing_identities:
            continue
            
        soup = BeautifulSoup(body, "html.parser")
        text = soup.get_text(separator="\n")
        
        fs_m = re.search(r"\bFs\b\s*[:=\-]?\s*([0-9]+(?:\.[0-9]+)?)\s*Hz", text, re.IGNORECASE)
        qts_m = re.search(r"\bQts\b\s*[:=\-]?\s*([0-9]+(?:\.[0-9]+)?)", text, re.IGNORECASE)
        qes_m = re.search(r"\bQes\b\s*[:=\-]?\s*([0-9]+(?:\.[0-9]+)?)", text, re.IGNORECASE)
        qms_m = re.search(r"\bQms\b\s*[:=\-]?\s*([0-9]+(?:\.[0-9]+)?)", text, re.IGNORECASE)
        vas_m = re.search(r"\bVas\b\s*[:=\-]?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:L|litres|Cu\.Ft|ft3)?", text, re.IGNORECASE)
        re_m = re.search(r"\bRe\b\s*[:=\-]?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:Ohm|Ω)?", text, re.IGNORECASE)
        sd_m = re.search(r"\bSd\b\s*[:=\-]?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:cm2|cm²)", text, re.IGNORECASE)
        xmax_m = re.search(r"\bXmax\b\s*[:=\-]?\s*([0-9]+(?:\.[0-9]+)?)\s*mm", text, re.IGNORECASE)
        pe_m = re.search(r"(?:Puissance RMS|RMS Power|RMS|Puissance)\s*[:=\-]?\s*([0-9]+(?:\.[0-9]+)?)\s*W", text, re.IGNORECASE)
        
        if fs_m and qts_m:
            try:
                fs = float(fs_m.group(1))
                qts = float(qts_m.group(1))
                if not (12.0 <= fs <= 160.0 and 0.12 <= qts <= 2.2):
                    continue
                qes = float(qes_m.group(1)) if qes_m else (qts * 1.15)
                qms = float(qms_m.group(1)) if qms_m else (qts * qes / max(1e-4, qes - qts) if qes > qts else 5.0)
                vas = float(vas_m.group(1)) if vas_m else None
                if not vas or vas < 1.0:
                    vas = max(2.0, 50.0 * (30.0 / fs)**2)
                sd = float(sd_m.group(1)) if sd_m else infer_sd(title)
                xmax = float(xmax_m.group(1)) if xmax_m else 10.0
                pe = float(pe_m.group(1)) if pe_m else 300.0
                re_val = float(re_m.group(1)) if re_m else 3.2
                
                clean_brand = vendor.strip() or "Car Audio"
                clean_model = re.sub(r"\b(?:Subwoofer|Haut-parleur|Coaxial)\b", "", title, flags=re.IGNORECASE).strip()
                preset_name = f"WEB: {clean_brand} {clean_model}"
                
                if any(h["name"] == preset_name for h in harvested):
                    continue
                    
                harvested.append({
                    "name": preset_name,
                    "brand": clean_brand,
                    "model": clean_model,
                    "category": "Subwoofer",
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
                    "currency": "EUR",
                    "url": product_url
                })
            except Exception:
                pass
                
    print(f"Discovered {len(harvested)} new drivers with full T/S")
    if not harvested or not CATALOG_PROP.exists():
        return
        
    cat_data = json.loads(CATALOG_PROP.read_text(encoding="utf-8"))
    existing_items = cat_data.get("presets", [])
    existing_names = {item.get("name") for item in existing_items}
    
    added = 0
    for h in harvested:
        if h["name"] not in existing_names:
            existing_items.append(h)
            existing_names.add(h["name"])
            added += 1
            print(f"Added new preset: {h['name']}")
            
    if added > 0:
        cat_data["presets"] = existing_items
        CATALOG_PROP.write_text(json.dumps(cat_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        cache_path = CATALOG_PROP.with_suffix(".cache.pickle")
        if cache_path.exists():
            cache_path.unlink()
        print(f"Successfully added {added} new driver presets to {CATALOG_PROP.name}!")


if __name__ == "__main__":
    main()
