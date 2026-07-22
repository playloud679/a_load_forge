#!/usr/bin/env python3
"""Harvest the full Parts Express catalog (T/S params + prices) via their
undocumented NetSuite SuiteCommerce REST API.

Reads product slugs from a URL list (one per line, extracted from
parts-express.com's sitemap_pages.xml), fetches
``/api/items?...&fieldset=details&url=<slug>`` for each, and writes two
outputs incrementally so the run is safely resumable:

- a manufacturer-catalog preset list (T/S params) for items with full
  Thiele/Small data
- a price record list (schema matching data/driver_prices.json's "prices"
  index) for every item with a usable price, regardless of whether it has
  T/S data
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

API_BASE = "https://www.parts-express.com/api/items"
USER_AGENT = "LoadForge-PartsExpress-Harvester/1.0"

RANGES = {
    "fs_hz": (1.0, 2000.0), "vas_l": (0.0001, 100000.0), "qts": (0.005, 10.0),
    "qms": (0.01, 1000.0), "qes": (0.005, 100.0), "re_ohm": (0.01, 1000.0),
    "sd_cm2": (0.01, 100000.0),
}
REQUIRED = ("fs_hz", "vas_l", "qts", "qms", "re_ohm", "sd_cm2")
FIELD_MAP = {
    "fs_hz": "custitem_pe_resonant_frequency_fs",
    "vas_l": "custitem_pe_compliance_equiv_volume",
    "qts": "custitem_pe_total_q_qts",
    "qms": "custitem_pe_mechanical_q_qms",
    "qes": "custitem_pe_electromagnetic_q_qes",
    "re_ohm": "custitem_pe_dc_resistance_re",
    "sd_cm2": "custitem_pe_surface_area_of_cone_sd",
    "le_mh": "custitem_pe_voice_coil_inductance_le",
    "xmax_mm": "custitem_pe_max_linear_excursion",
    "pe_w": "custitem_pe_power_handling_rms",
    "mms_g": "custitem_pe_diaphragm_mass_airload",
    "cms_mm_per_n": "custitem_pe_mech_comp_suspension",
    "bl_tm": "custitem_pe_bl_product_bl",
}


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()


def to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def slug_from_url(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1]


def fetch_item(slug: str, timeout_s: float) -> dict | None:
    qs = urllib.parse.urlencode(
        {"language": "en", "country": "US", "currency": "USD",
         "fieldset": "details", "url": slug}
    )
    req = urllib.request.Request(f"{API_BASE}?{qs}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    items = payload.get("items") or []
    return items[0] if items else None


def build_preset(item: dict) -> dict | None:
    brand = (item.get("custitem_pe_brand") or "").strip()
    if not brand:
        return None
    values = {k: to_float(item.get(f)) for k, f in FIELD_MAP.items()}
    if values.get("vas_l") is not None:
        values["vas_l"] *= 28.316846592  # ft^3 -> L
    if any(values.get(k) is None for k in REQUIRED):
        return None
    if any(values.get(k) is not None and not (lo <= values[k] <= hi) for k, (lo, hi) in RANGES.items()):
        return None
    if values["qms"] <= values["qts"]:
        return None

    displayname = item.get("displayname") or ""
    model = displayname
    if model.casefold().startswith(brand.casefold()):
        model = model[len(brand):].strip()
    urlcomponent = item.get("urlcomponent") or ""
    url = f"https://www.parts-express.com/{urlcomponent}" if urlcomponent else ""
    driver = {k: round(values.get(k) or 0.0, 8) for k in (
        "fs_hz", "vas_l", "qts", "qms", "re_ohm", "sd_cm2",
        "le_mh", "xmax_mm", "pe_w", "mms_g", "cms_mm_per_n", "bl_tm",
    )}
    return {
        "name": f"WEB: {brand} {model}".strip(),
        "brand": brand,
        "model": model,
        "kind": "Loudspeaker driver",
        "url": url,
        "source": "Parts Express API",
        "driver": driver,
        "raw": {k: v for k, v in values.items() if v is not None},
        "website_fields": {
            "title": displayname, "brand": brand, "model": model, "url": url,
            "source": "Parts Express API", "fetched_at": utc_now(),
            "extraction_method": "api", "confidence": 0.95, "raw_measurements": {},
        },
    }


def build_price_record(item: dict) -> dict | None:
    raw_price = item.get("onlinecustomerprice")
    if raw_price is None:
        raw_price = item.get("pricelevel1")
    price = to_float(raw_price)
    if price is None:
        return None
    urlcomponent = item.get("urlcomponent") or ""
    url = f"https://www.parts-express.com/{urlcomponent}" if urlcomponent else ""
    brand = (item.get("custitem_pe_brand") or item.get("manufacturer") or "").strip()
    return {
        "name": str(item.get("displayname") or ""),
        "brand": brand,
        "mpn": str(item.get("itemid") or ""),
        "sku": str(item.get("itemid") or ""),
        "url": url,
        "price": round(price, 2),
        "currency": "USD",
        "availability": (
            "https://schema.org/InStock" if item.get("isinstock") else "https://schema.org/OutOfStock"
        ),
        "price_valid_until": "",
        "seller": "PartsExpress",
        "fetched_at": utc_now(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--urls", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--sleep", type=float, default=0.35)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--max-items", type=int, default=0)
    args = parser.parse_args()

    urls = [u.strip() for u in args.urls.read_text().splitlines() if u.strip()]

    if args.checkpoint.exists():
        state = json.loads(args.checkpoint.read_text())
    else:
        state = {"visited": [], "presets": [], "prices": [], "failures": []}
    visited = set(state["visited"])

    done = 0
    for url in urls:
        if url in visited:
            continue
        if args.max_items and done >= args.max_items:
            break
        slug = slug_from_url(url)
        try:
            item = fetch_item(slug, args.timeout)
        except Exception as exc:  # noqa: BLE001
            state["failures"].append({"url": url, "error": str(exc)})
            visited.add(url)
            state["visited"] = sorted(visited)
            done += 1
            time.sleep(args.sleep)
            continue

        if item:
            preset = build_preset(item)
            if preset:
                state["presets"].append(preset)
            price = build_price_record(item)
            if price:
                state["prices"].append(price)

        visited.add(url)
        state["visited"] = sorted(visited)
        done += 1
        if done % 25 == 0:
            args.checkpoint.write_text(json.dumps(state))
            print(
                f"progress: visited={len(visited)}/{len(urls)} "
                f"presets={len(state['presets'])} prices={len(state['prices'])} "
                f"failures={len(state['failures'])}",
                flush=True,
            )
        time.sleep(args.sleep)

    args.checkpoint.write_text(json.dumps(state))
    print(
        f"DONE visited={len(visited)}/{len(urls)} presets={len(state['presets'])} "
        f"prices={len(state['prices'])} failures={len(state['failures'])}",
        flush=True,
    )


if __name__ == "__main__":
    main()
