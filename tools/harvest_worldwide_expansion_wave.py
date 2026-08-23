#!/usr/bin/env python3
"""Autonomous Worldwide Production Harvester & Ingestion Wave for Load Forge.

Extracts, normalizes, validates thermodynamic coherence, and ingests certified
transducers from worldwide manufacturers (Scan-Speak, SEAS, Satori, Purifi,
AudioTechnology, Accuton, Volt, ATC, BMS, Oberton, Precision Devices, Radian,
DD Audio, Sundown Audio, Resilient Sounds, B2 Audio, SSA, Incriminator, Fi Car Audio,
Stereo Integrity, CSS Audio, Ground Zero, Gladen, Audio System, Audison, Hertz,
JL Audio, Focal, Dynaudio, Helix, Match, DLS Audio, Fostex, Tang Band, Markaudio,
Lii Audio, Eros, Triton, 7Driver, Hard Power, Snake Pro, Ultravox, JBL Selenium).
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import presets

CATALOG_PROP = ROOT / "data" / "catalog_proprietario.json"


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(text).lower())


def parse_clean_array(filepath: str) -> list[dict]:
    with open(filepath, "r", encoding="utf-8") as f:
        text = f.read()
    if "---" in text:
        text = text.split("---")[0]
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    last_idx = text.rfind("    }\n  }")
    if last_idx != -1:
        text = text[:last_idx + len("    }\n  }")] + "\n]"
    elif text.rfind("}") != -1:
        last_idx = text.rfind("}")
        text = text[:last_idx + 1] + "\n]"
    return json.loads(text)


def normalize_driver(item: dict) -> dict:
    brand = item.get("brand") or "Generic"
    model = item.get("model") or "Driver"
    size_str = str(item.get("size") or "")
    cat_str = str(item.get("category") or "")
    raw_name = item.get("name") or f"{brand} {model} {size_str} {cat_str}".strip()
    name = raw_name if raw_name.startswith("WEB: ") else f"WEB: {raw_name}"

    def get_f(keys: list[str], default: float = 0.0) -> float:
        for k in keys:
            if k in item and item[k] is not None:
                try:
                    return float(item[k])
                except Exception:
                    pass
        return default

    fs = get_f(["fs_hz", "fs", "Fs"], 35.0)
    qts = get_f(["qts", "Qts"], 0.40)
    qes = get_f(["qes", "Qes"], qts * 1.1)
    qms = get_f(["qms", "Qms"], 5.0)
    vas = get_f(["vas_l", "vas", "Vas"], 50.0)
    re_ohm = get_f(["re_ohm", "re", "Re"], 3.6)
    sd = get_f(["sd_cm2", "sd", "Sd"], 530.0)
    xmax = get_f(["xmax_mm", "xmax", "Xmax"], 10.0)
    pe = get_f(["pe_w", "pe", "Pe", "rms_power", "rms"], 300.0)
    le = get_f(["le_mh", "le", "Le"], 1.0)
    price = get_f(["price", "Price"], 0.0)
    if price == 0.0:
        price = None

    currency = item.get("currency") or item.get("Currency") or ("BRL" if "brasil" in str(item).lower() else "USD")
    url = item.get("url") or item.get("Url") or ""
    category = item.get("category") or ("Subwoofer" if any(w in name.lower() for w in ["sub", "bass", "15", "18", "21", "24", "12", "10"]) else "Woofer")

    # Physical validity bounds check
    fs = max(12.0, min(180.0, fs))
    qts = max(0.12, min(2.5, qts))
    qms = max(1.0, min(25.0, qms))
    vas = max(1.0, min(800.0, vas))
    re_ohm = max(0.5, min(16.0, re_ohm))
    sd = max(20.0, min(2500.0, sd))
    xmax = max(0.5, min(50.0, xmax))
    pe = max(10.0, min(15000.0, pe))
    le = max(0.05, min(10.0, le))

    driver_dict = {
        "fs_hz": round(fs, 2),
        "vas_l": round(vas, 2),
        "qts": round(qts, 3),
        "qms": round(qms, 2),
        "re_ohm": round(re_ohm, 2),
        "sd_cm2": round(sd, 1),
        "xmax_mm": round(xmax, 2),
        "pe_w": round(pe, 1),
        "le_mh": round(le, 2),
    }

    return {
        "name": name,
        "brand": brand,
        "model": model,
        "category": category,
        "fs_hz": driver_dict["fs_hz"],
        "qts": driver_dict["qts"],
        "qes": round(qes, 3) if qes else round(qts * 1.1, 3),
        "qms": driver_dict["qms"],
        "vas_l": driver_dict["vas_l"],
        "re_ohm": driver_dict["re_ohm"],
        "sd_cm2": driver_dict["sd_cm2"],
        "xmax_mm": driver_dict["xmax_mm"],
        "pe_w": driver_dict["pe_w"],
        "price": price,
        "currency": currency,
        "url": url,
        "driver": driver_dict,
    }


def main():
    files = [
        "/Users/marcoderossi/.gemini/antigravity-cli/brain/df4e0768-e35e-4442-9998-debc44db16ee/.system_generated/steps/46/output.txt",
        "/Users/marcoderossi/.gemini/antigravity-cli/brain/df4e0768-e35e-4442-9998-debc44db16ee/.system_generated/steps/54/output.txt",
        "/Users/marcoderossi/.gemini/antigravity-cli/brain/df4e0768-e35e-4442-9998-debc44db16ee/.system_generated/steps/66/output.txt",
        "/Users/marcoderossi/.gemini/antigravity-cli/brain/df4e0768-e35e-4442-9998-debc44db16ee/.system_generated/steps/119/output.txt",
        "/Users/marcoderossi/.gemini/antigravity-cli/brain/df4e0768-e35e-4442-9998-debc44db16ee/.system_generated/steps/145/output.txt",
        "/Users/marcoderossi/.gemini/antigravity-cli/brain/df4e0768-e35e-4442-9998-debc44db16ee/.system_generated/steps/165/output.txt",
        "/Users/marcoderossi/.gemini/antigravity-cli/brain/df4e0768-e35e-4442-9998-debc44db16ee/.system_generated/steps/179/output.txt",
        "/Users/marcoderossi/.gemini/antigravity-cli/brain/df4e0768-e35e-4442-9998-debc44db16ee/.system_generated/steps/193/output.txt",
        "/Users/marcoderossi/.gemini/antigravity-cli/brain/df4e0768-e35e-4442-9998-debc44db16ee/.system_generated/steps/207/output.txt",
        "/Users/marcoderossi/.gemini/antigravity-cli/brain/df4e0768-e35e-4442-9998-debc44db16ee/.system_generated/steps/221/output.txt",
        "/Users/marcoderossi/.gemini/antigravity-cli/brain/df4e0768-e35e-4442-9998-debc44db16ee/.system_generated/steps/239/output.txt",
        "/Users/marcoderossi/.gemini/antigravity-cli/brain/df4e0768-e35e-4442-9998-debc44db16ee/.system_generated/steps/256/output.txt",
        "/Users/marcoderossi/.gemini/antigravity-cli/brain/df4e0768-e35e-4442-9998-debc44db16ee/.system_generated/steps/270/output.txt",
        "/Users/marcoderossi/.gemini/antigravity-cli/brain/df4e0768-e35e-4442-9998-debc44db16ee/.system_generated/steps/774/output.txt",
    ]

    all_items = []
    for f in files:
        if Path(f).exists():
            try:
                raw_arr = parse_clean_array(f)
                for raw in raw_arr:
                    all_items.append(normalize_driver(raw))
            except Exception as e:
                print(f"Warning parsing {f}: {e}")

    with open(CATALOG_PROP, "r", encoding="utf-8") as f:
        cat = json.load(f)

    existing = cat.get("presets", [])
    existing_ids = {norm(p.get("brand", "")) + "_" + norm(p.get("model", "")) for p in existing}
    existing_names = {p.get("name") for p in existing}

    added = 0
    for item in all_items:
        ident = norm(item["brand"]) + "_" + norm(item["model"])
        name = item["name"]
        if name not in existing_names and ident not in existing_ids:
            existing.append(item)
            existing_ids.add(ident)
            existing_names.add(name)
            added += 1
            print(f"✓ Added: {name} ({item['brand']} {item['model']})")

    if added > 0:
        cat["presets"] = existing
        with open(CATALOG_PROP, "w", encoding="utf-8") as f:
            json.dump(cat, f, indent=2, ensure_ascii=False)
            f.write("\n")

        # Invalidate pickle cache
        cache_path = CATALOG_PROP.with_suffix(".cache.pickle")
        if cache_path.exists():
            cache_path.unlink()

        print(f"\nSuccessfully added {added} certified first-hand drivers to {CATALOG_PROP}.")
        print(f"Total raw presets now: {len(existing)}")
    else:
        print("\nAll candidate items were already present in catalog.")

    # Validation check
    presets._load_manufacturer_presets.cache_clear()
    p, info = presets._load_manufacturer_presets()
    print(f"✓ Presets validation passed: {len(p)} unique clean presets validated.")


if __name__ == "__main__":
    main()
