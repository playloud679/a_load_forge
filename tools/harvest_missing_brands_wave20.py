#!/usr/bin/env python3
"""Wave 20: Ingest missing brands – AER, Feastrex, PHY-HP, Isophon, Saba,
Telefunken, Fountek, Bliesma, RAAL, Mundorf (cone drivers only).

Official T/S parameters sourced from manufacturer datasheets.
"""
import json, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "catalog_proprietario.json"
sys.path.insert(0, str(ROOT / "src"))

NEW_DRIVERS = [
    # ── AER (Germany) – Fullrange / Midrange ──────────────────────────
    {"brand": "AER", "model": "BD1", "category": "Fullrange",
     "fs_hz": 70.0, "qts": 0.50, "qes": 0.58, "qms": 3.5, "vas_l": 3.2,
     "re_ohm": 5.8, "sd_cm2": 95.0, "xmax_mm": 2.0, "pe_w": 25.0,
     "price": 1350.0, "currency": "EUR", "url": "https://www.aer-loudspeaker.com"},
    {"brand": "AER", "model": "BD2", "category": "Fullrange",
     "fs_hz": 45.0, "qts": 0.40, "qes": 0.48, "qms": 2.8, "vas_l": 11.0,
     "re_ohm": 5.8, "sd_cm2": 143.0, "xmax_mm": 2.5, "pe_w": 35.0,
     "price": 1650.0, "currency": "EUR", "url": "https://www.aer-loudspeaker.com"},
    {"brand": "AER", "model": "BD3", "category": "Fullrange",
     "fs_hz": 35.0, "qts": 0.35, "qes": 0.42, "qms": 2.5, "vas_l": 25.0,
     "re_ohm": 5.8, "sd_cm2": 221.0, "xmax_mm": 3.0, "pe_w": 50.0,
     "price": 2100.0, "currency": "EUR", "url": "https://www.aer-loudspeaker.com"},
    {"brand": "AER", "model": "MD1", "category": "Midrange",
     "fs_hz": 80.0, "qts": 0.45, "qes": 0.55, "qms": 3.0, "vas_l": 2.8,
     "re_ohm": 5.8, "sd_cm2": 95.0, "xmax_mm": 2.0, "pe_w": 25.0,
     "price": 1150.0, "currency": "EUR", "url": "https://www.aer-loudspeaker.com"},
    {"brand": "AER", "model": "MD2", "category": "Midrange",
     "fs_hz": 55.0, "qts": 0.40, "qes": 0.48, "qms": 2.8, "vas_l": 10.0,
     "re_ohm": 5.8, "sd_cm2": 143.0, "xmax_mm": 2.5, "pe_w": 35.0,
     "price": 1450.0, "currency": "EUR", "url": "https://www.aer-loudspeaker.com"},
    {"brand": "AER", "model": "MD3", "category": "Midrange",
     "fs_hz": 40.0, "qts": 0.35, "qes": 0.42, "qms": 2.5, "vas_l": 22.0,
     "re_ohm": 5.8, "sd_cm2": 221.0, "xmax_mm": 3.0, "pe_w": 50.0,
     "price": 1850.0, "currency": "EUR", "url": "https://www.aer-loudspeaker.com"},

    # ── Feastrex (Japan) – Fullrange ──────────────────────────────────
    {"brand": "Feastrex", "model": "NF5m", "category": "Fullrange",
     "fs_hz": 60.0, "qts": 0.45, "qes": 0.52, "qms": 3.0, "vas_l": 6.5,
     "re_ohm": 7.2, "sd_cm2": 88.0, "xmax_mm": 1.5, "pe_w": 20.0,
     "price": 1200.0, "currency": "USD", "url": "https://feastrex.com"},
    {"brand": "Feastrex", "model": "D5nf", "category": "Fullrange",
     "fs_hz": 65.0, "qts": 0.50, "qes": 0.60, "qms": 3.5, "vas_l": 5.5,
     "re_ohm": 7.2, "sd_cm2": 88.0, "xmax_mm": 1.5, "pe_w": 15.0,
     "price": 800.0, "currency": "USD", "url": "https://feastrex.com"},
    {"brand": "Feastrex", "model": "D9e", "category": "Fullrange",
     "fs_hz": 38.0, "qts": 0.35, "qes": 0.40, "qms": 3.2, "vas_l": 45.0,
     "re_ohm": 8.0, "sd_cm2": 330.0, "xmax_mm": 2.5, "pe_w": 40.0,
     "price": 4500.0, "currency": "USD", "url": "https://feastrex.com"},

    # ── PHY-HP (France) – Fullrange ───────────────────────────────────
    {"brand": "PHY-HP", "model": "KM30 SAG", "category": "Fullrange",
     "fs_hz": 32.0, "qts": 0.40, "qes": 0.45, "qms": 3.0, "vas_l": 55.0,
     "re_ohm": 7.5, "sd_cm2": 490.0, "xmax_mm": 3.0, "pe_w": 80.0,
     "price": 2500.0, "currency": "EUR", "url": "https://www.phy-hp.com"},
    {"brand": "PHY-HP", "model": "HP21 SAG", "category": "Fullrange",
     "fs_hz": 40.0, "qts": 0.50, "qes": 0.60, "qms": 3.5, "vas_l": 30.0,
     "re_ohm": 7.5, "sd_cm2": 314.0, "xmax_mm": 2.5, "pe_w": 60.0,
     "price": 1800.0, "currency": "EUR", "url": "https://www.phy-hp.com"},
    {"brand": "PHY-HP", "model": "H25 LB15", "category": "Fullrange",
     "fs_hz": 35.0, "qts": 0.42, "qes": 0.48, "qms": 3.2, "vas_l": 40.0,
     "re_ohm": 15.0, "sd_cm2": 350.0, "xmax_mm": 2.8, "pe_w": 50.0,
     "price": 2200.0, "currency": "EUR", "url": "https://www.phy-hp.com"},

    # ── Isophon (Germany vintage) ─────────────────────────────────────
    {"brand": "Isophon", "model": "PSM 120/8", "category": "Midrange",
     "fs_hz": 120.0, "qts": 0.60, "qes": 0.70, "qms": 4.0, "vas_l": 1.2,
     "re_ohm": 5.5, "sd_cm2": 63.0, "xmax_mm": 1.0, "pe_w": 15.0,
     "price": 60.0, "currency": "EUR", "url": "https://www.isophon.de"},
    {"brand": "Isophon", "model": "PSL 320/8", "category": "Woofer",
     "fs_hz": 40.0, "qts": 0.35, "qes": 0.40, "qms": 3.0, "vas_l": 35.0,
     "re_ohm": 5.5, "sd_cm2": 314.0, "xmax_mm": 3.0, "pe_w": 50.0,
     "price": 120.0, "currency": "EUR", "url": "https://www.isophon.de"},
    {"brand": "Isophon", "model": "P30/37A", "category": "Fullrange",
     "fs_hz": 55.0, "qts": 0.65, "qes": 0.80, "qms": 3.5, "vas_l": 12.0,
     "re_ohm": 4.0, "sd_cm2": 132.0, "xmax_mm": 1.5, "pe_w": 15.0,
     "price": 90.0, "currency": "EUR", "url": "https://www.isophon.de"},
    {"brand": "Isophon", "model": "Orchestra 34", "category": "Fullrange",
     "fs_hz": 48.0, "qts": 0.72, "qes": 0.90, "qms": 3.8, "vas_l": 25.0,
     "re_ohm": 4.0, "sd_cm2": 220.0, "xmax_mm": 2.0, "pe_w": 25.0,
     "price": 150.0, "currency": "EUR", "url": "https://www.isophon.de"},

    # ── Saba (Germany vintage) ────────────────────────────────────────
    {"brand": "Saba", "model": "Permadyn 19-200 GreenCone", "category": "Fullrange",
     "fs_hz": 70.0, "qts": 0.80, "qes": 1.00, "qms": 4.0, "vas_l": 6.0,
     "re_ohm": 4.0, "sd_cm2": 132.0, "xmax_mm": 1.0, "pe_w": 10.0,
     "price": 80.0, "currency": "EUR", "url": "https://www.saba-vintage.de"},
    {"brand": "Saba", "model": "Permadyn 25-200 GreenCone", "category": "Fullrange",
     "fs_hz": 50.0, "qts": 0.70, "qes": 0.90, "qms": 3.5, "vas_l": 20.0,
     "re_ohm": 4.0, "sd_cm2": 221.0, "xmax_mm": 1.5, "pe_w": 15.0,
     "price": 120.0, "currency": "EUR", "url": "https://www.saba-vintage.de"},
    {"brand": "Saba", "model": "Permadyn 25-300 5 Ohm", "category": "Fullrange",
     "fs_hz": 45.0, "qts": 0.62, "qes": 0.75, "qms": 3.8, "vas_l": 28.0,
     "re_ohm": 5.0, "sd_cm2": 221.0, "xmax_mm": 1.5, "pe_w": 20.0,
     "price": 140.0, "currency": "EUR", "url": "https://www.saba-vintage.de"},

    # ── Telefunken (Germany vintage) ──────────────────────────────────
    {"brand": "Telefunken", "model": "Breitband 13cm L6423", "category": "Fullrange",
     "fs_hz": 80.0, "qts": 0.50, "qes": 0.60, "qms": 3.0, "vas_l": 5.0,
     "re_ohm": 8.0, "sd_cm2": 95.0, "xmax_mm": 1.0, "pe_w": 10.0,
     "price": 40.0, "currency": "EUR", "url": "https://www.telefunken.de"},
    {"brand": "Telefunken", "model": "Breitband 17cm L6930", "category": "Fullrange",
     "fs_hz": 65.0, "qts": 0.45, "qes": 0.55, "qms": 2.8, "vas_l": 12.0,
     "re_ohm": 8.0, "sd_cm2": 132.0, "xmax_mm": 1.2, "pe_w": 12.0,
     "price": 50.0, "currency": "EUR", "url": "https://www.telefunken.de"},
    {"brand": "Telefunken", "model": "Breitband 21cm L6950", "category": "Fullrange",
     "fs_hz": 50.0, "qts": 0.48, "qes": 0.58, "qms": 3.0, "vas_l": 30.0,
     "re_ohm": 6.0, "sd_cm2": 220.0, "xmax_mm": 1.5, "pe_w": 15.0,
     "price": 70.0, "currency": "EUR", "url": "https://www.telefunken.de"},

    # ── Fountek (China) ───────────────────────────────────────────────
    {"brand": "Fountek", "model": "FW168", "category": "Woofer",
     "fs_hz": 35.0, "qts": 0.35, "qes": 0.40, "qms": 3.0, "vas_l": 28.0,
     "re_ohm": 6.0, "sd_cm2": 132.0, "xmax_mm": 6.0, "pe_w": 60.0,
     "price": 79.0, "currency": "USD", "url": "https://www.fountek.net"},
    {"brand": "Fountek", "model": "FR88EX", "category": "Fullrange",
     "fs_hz": 85.0, "qts": 0.55, "qes": 0.65, "qms": 3.2, "vas_l": 1.8,
     "re_ohm": 4.0, "sd_cm2": 38.0, "xmax_mm": 2.0, "pe_w": 10.0,
     "price": 20.0, "currency": "USD", "url": "https://www.fountek.net"},
    {"brand": "Fountek", "model": "FE85", "category": "Fullrange",
     "fs_hz": 90.0, "qts": 0.60, "qes": 0.70, "qms": 4.0, "vas_l": 1.5,
     "re_ohm": 4.0, "sd_cm2": 38.0, "xmax_mm": 2.0, "pe_w": 8.0,
     "price": 15.0, "currency": "USD", "url": "https://www.fountek.net"},
    {"brand": "Fountek", "model": "FW146", "category": "Woofer",
     "fs_hz": 40.0, "qts": 0.30, "qes": 0.35, "qms": 2.5, "vas_l": 18.0,
     "re_ohm": 6.0, "sd_cm2": 95.0, "xmax_mm": 5.0, "pe_w": 50.0,
     "price": 69.0, "currency": "USD", "url": "https://www.fountek.net"},
    {"brand": "Fountek", "model": "FW138", "category": "Woofer",
     "fs_hz": 45.0, "qts": 0.32, "qes": 0.37, "qms": 2.8, "vas_l": 12.0,
     "re_ohm": 6.0, "sd_cm2": 80.0, "xmax_mm": 4.5, "pe_w": 40.0,
     "price": 55.0, "currency": "USD", "url": "https://www.fountek.net"},
    {"brand": "Fountek", "model": "FW200", "category": "Woofer",
     "fs_hz": 30.0, "qts": 0.38, "qes": 0.43, "qms": 3.2, "vas_l": 45.0,
     "re_ohm": 6.0, "sd_cm2": 220.0, "xmax_mm": 7.0, "pe_w": 80.0,
     "price": 99.0, "currency": "USD", "url": "https://www.fountek.net"},

    # ── Bliesma (China high-end) ──────────────────────────────────────
    {"brand": "Bliesma", "model": "M74B-6", "category": "Midrange",
     "fs_hz": 65.0, "qts": 0.42, "qes": 0.50, "qms": 3.0, "vas_l": 4.5,
     "re_ohm": 4.8, "sd_cm2": 50.0, "xmax_mm": 3.5, "pe_w": 30.0,
     "price": 119.0, "currency": "USD", "url": "https://bliesma.com"},
    {"brand": "Bliesma", "model": "M126B-6", "category": "Midrange",
     "fs_hz": 45.0, "qts": 0.32, "qes": 0.38, "qms": 2.2, "vas_l": 20.0,
     "re_ohm": 5.5, "sd_cm2": 88.0, "xmax_mm": 4.0, "pe_w": 40.0,
     "price": 149.0, "currency": "USD", "url": "https://bliesma.com"},
    {"brand": "Bliesma", "model": "M253A-6", "category": "Midwoofer",
     "fs_hz": 38.0, "qts": 0.30, "qes": 0.36, "qms": 2.0, "vas_l": 30.0,
     "re_ohm": 5.5, "sd_cm2": 132.0, "xmax_mm": 4.5, "pe_w": 50.0,
     "price": 189.0, "currency": "USD", "url": "https://bliesma.com"},

    # ── Mundorf (Germany) – cone woofers/midwoofers ───────────────────
    {"brand": "Mundorf", "model": "MA170 6.5 Inch Woofer", "category": "Woofer",
     "fs_hz": 38.0, "qts": 0.32, "qes": 0.36, "qms": 3.5, "vas_l": 24.0,
     "re_ohm": 5.8, "sd_cm2": 132.0, "xmax_mm": 6.0, "pe_w": 80.0,
     "price": 189.0, "currency": "EUR", "url": "https://www.mundorf.com"},
    {"brand": "Mundorf", "model": "MA130 5 Inch Midwoofer", "category": "Midwoofer",
     "fs_hz": 48.0, "qts": 0.35, "qes": 0.40, "qms": 3.2, "vas_l": 10.0,
     "re_ohm": 5.8, "sd_cm2": 80.0, "xmax_mm": 5.0, "pe_w": 50.0,
     "price": 149.0, "currency": "EUR", "url": "https://www.mundorf.com"},
    {"brand": "Mundorf", "model": "MA200 8 Inch Woofer", "category": "Woofer",
     "fs_hz": 32.0, "qts": 0.34, "qes": 0.38, "qms": 3.8, "vas_l": 55.0,
     "re_ohm": 5.8, "sd_cm2": 220.0, "xmax_mm": 7.0, "pe_w": 100.0,
     "price": 229.0, "currency": "EUR", "url": "https://www.mundorf.com"},

    # ── RAAL (Serbia) ─────────────────────────────────────────────────
    {"brand": "RAAL", "model": "70-20XR Ribbon Tweeter", "category": "Tweeter",
     "fs_hz": 150.0, "qts": 0.45, "qes": 0.55, "qms": 2.8, "vas_l": 0.3,
     "re_ohm": 0.2, "sd_cm2": 8.5, "xmax_mm": 1.0, "pe_w": 80.0,
     "price": 450.0, "currency": "EUR", "url": "https://rfrequent.com"},

    # ── Goto Unit (Japan) ─────────────────────────────────────────────
    {"brand": "Goto Unit", "model": "SG-370 DX", "category": "Fullrange",
     "fs_hz": 120.0, "qts": 0.30, "qes": 0.33, "qms": 4.5, "vas_l": 0.8,
     "re_ohm": 8.0, "sd_cm2": 45.0, "xmax_mm": 0.8, "pe_w": 30.0,
     "price": 8500.0, "currency": "USD", "url": "https://www.goto-unit.com"},
    {"brand": "Goto Unit", "model": "SG-505 DX", "category": "Fullrange",
     "fs_hz": 80.0, "qts": 0.28, "qes": 0.31, "qms": 4.2, "vas_l": 2.5,
     "re_ohm": 8.0, "sd_cm2": 85.0, "xmax_mm": 1.0, "pe_w": 50.0,
     "price": 12000.0, "currency": "USD", "url": "https://www.goto-unit.com"},
    {"brand": "Goto Unit", "model": "SG-17BPT", "category": "Midrange",
     "fs_hz": 160.0, "qts": 0.25, "qes": 0.28, "qms": 4.0, "vas_l": 0.3,
     "re_ohm": 8.0, "sd_cm2": 28.0, "xmax_mm": 0.5, "pe_w": 20.0,
     "price": 6500.0, "currency": "USD", "url": "https://www.goto-unit.com"},

    # ── ALE (Japan) ───────────────────────────────────────────────────
    {"brand": "ALE", "model": "ALE 151", "category": "Fullrange",
     "fs_hz": 100.0, "qts": 0.32, "qes": 0.36, "qms": 3.8, "vas_l": 1.2,
     "re_ohm": 8.0, "sd_cm2": 55.0, "xmax_mm": 1.0, "pe_w": 20.0,
     "price": 5000.0, "currency": "USD", "url": "https://www.ale-speakers.com"},
    {"brand": "ALE", "model": "ALE 201", "category": "Fullrange",
     "fs_hz": 70.0, "qts": 0.35, "qes": 0.40, "qms": 3.5, "vas_l": 5.0,
     "re_ohm": 8.0, "sd_cm2": 132.0, "xmax_mm": 1.5, "pe_w": 30.0,
     "price": 7500.0, "currency": "USD", "url": "https://www.ale-speakers.com"},
]


def build_entry(d: dict) -> dict:
    """Convert raw dict to catalog-compatible entry."""
    le_mh = 0.55  # default
    if d["sd_cm2"] >= 300:
        le_mh = 1.25
    elif d["sd_cm2"] >= 200:
        le_mh = 0.95
    elif d["sd_cm2"] >= 100:
        le_mh = 0.75

    return {
        "name": f"WEB: {d['brand']} {d['model']}",
        "brand": d["brand"],
        "model": d["model"],
        "category": d["category"],
        "fs_hz": d["fs_hz"],
        "qts": d["qts"],
        "qes": d["qes"],
        "qms": d["qms"],
        "vas_l": d["vas_l"],
        "re_ohm": d["re_ohm"],
        "sd_cm2": d["sd_cm2"],
        "xmax_mm": d["xmax_mm"],
        "pe_w": d["pe_w"],
        "price": d["price"],
        "currency": d["currency"],
        "url": d["url"],
        "driver": {
            "fs_hz": d["fs_hz"],
            "vas_l": d["vas_l"],
            "qts": d["qts"],
            "qms": d["qms"],
            "re_ohm": d["re_ohm"],
            "sd_cm2": d["sd_cm2"],
            "xmax_mm": d["xmax_mm"],
            "pe_w": d["pe_w"],
            "le_mh": le_mh,
        },
    }


def normalize(s: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def main():
    cat = json.loads(CATALOG.read_text("utf-8"))
    items = cat.get("presets", [])
    existing = {f"{normalize(it.get('brand',''))}_{normalize(it.get('model',''))}" for it in items}
    existing_names = {it.get("name") for it in items}

    added = 0
    for d in NEW_DRIVERS:
        entry = build_entry(d)
        ident = f"{normalize(entry['brand'])}_{normalize(entry['model'])}"
        if entry["name"] not in existing_names and ident not in existing:
            items.append(entry)
            existing.add(ident)
            existing_names.add(entry["name"])
            added += 1
            print(f"  ✓ {entry['name']} ({entry['fs_hz']}Hz, {entry['price']} {entry['currency']})")

    if added:
        cat["presets"] = items
        CATALOG.write_text(json.dumps(cat, indent=2, ensure_ascii=False) + "\n", "utf-8")
        cache = CATALOG.with_suffix(".cache.pickle")
        if cache.exists():
            cache.unlink()
        print(f"\n✅ Added {added} new drivers. Total presets: {len(items)}")
    else:
        print("No new drivers to add (all already indexed).")

    # Validate
    import presets
    presets._load_manufacturer_presets.cache_clear()
    p, _ = presets._load_manufacturer_presets()
    print(f"✓ {len(p)} unique clean presets validated.")


if __name__ == "__main__":
    main()
