#!/usr/bin/env python3
"""Harvest T/S drivers from nvx.com's own house brand ("NVX").

nvx.com is a Shopify storefront selling car-audio electronics. Most listings
(fitment enclosures, amps, wiring) have no T/S data, but component-speaker /
subwoofer product descriptions embed a genuine "T/S Parameters:" HTML list
with real Fs/Qts/Qms/Qes/Vas/Sd/Re/BL/Mms/Cms values (confirmed real DC
resistance labeled "Voice Coil Resistance (Re)", not a nominal impedance
class like the DD Audio/Incriminator/SoundQubed dead-end pattern).

Reuses tools/crawl_thiele_small.py's text-measurement extraction and
build_preset() by feeding each product's body_html through parse_html() --
same reuse pattern as the Rockville/REDCATT/Parts Express harvests.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import crawl_thiele_small as cts  # noqa: E402

STORE = "https://nvx.com"
PRODUCTS_JSON = STORE + "/products.json"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
VENDOR = "NVX"
DEFAULT_CHECKPOINT = ROOT / "data" / "nvx_harvest_checkpoint.json"


def fetch_page(page: int, limit: int = 250, timeout: float = 15.0) -> list[dict]:
    url = f"{PRODUCTS_JSON}?limit={limit}&page={page}"
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept": "application/json,text/html,*/*"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload.get("products", [])


def harvest_catalog(sleep_s: float, max_pages: int) -> list[dict]:
    products: list[dict] = []
    page = 1
    while page <= max_pages:
        batch = fetch_page(page)
        if not batch:
            break
        products.extend(batch)
        print(f"catalog page {page}: {len(batch)} products (total {len(products)})", flush=True)
        page += 1
        time.sleep(sleep_s)
    return products


def build_record(product: dict) -> tuple[dict | None, list[str]]:
    body = product.get("body_html") or ""
    if "qts" not in body.lower():
        return None, ["no qts text"]
    title = html.escape(str(product.get("title") or ""))
    synthetic_html = f"<html><head><title>{title}</title></head><body>{body}</body></html>"
    page = cts.parse_html(synthetic_html.encode("utf-8"))
    handle = product.get("handle") or ""
    url = f"{STORE}/products/{handle}" if handle else STORE
    preset, errors = cts.build_preset(
        page, url, source_name="NVX web crawler", brand_hint=VENDOR,
        extraction_method="html",
    )
    return preset, errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--sleep", type=float, default=0.3)
    parser.add_argument("--max-pages", type=int, default=20)
    parser.add_argument("--refresh-catalog", action="store_true")
    args = parser.parse_args()

    if args.checkpoint.exists():
        state = json.loads(args.checkpoint.read_text())
    else:
        state = {"catalog": [], "presets": [], "failures": []}

    if args.refresh_catalog or not state.get("catalog"):
        state["catalog"] = harvest_catalog(args.sleep, args.max_pages)
        args.checkpoint.write_text(json.dumps(state))

    vendor_products = [p for p in state["catalog"] if p.get("vendor") == VENDOR]
    print(f"vendor={VENDOR} products: {len(vendor_products)} / {len(state['catalog'])} total", flush=True)

    presets = []
    failures = []
    seen_handles = set()
    for product in vendor_products:
        handle = product.get("handle") or ""
        if handle in seen_handles:
            continue
        seen_handles.add(handle)
        preset, errors = build_record(product)
        if preset:
            presets.append(preset)
        else:
            failures.append({"handle": handle, "errors": errors})

    state["presets"] = presets
    state["failures"] = failures
    # Drop the heavy raw catalog payload once presets are extracted (mirrors
    # the Rockville harvest lesson -- don't let a checkpoint keep megabytes
    # of body_html around after use).
    state["catalog"] = []
    args.checkpoint.write_text(json.dumps(state))
    print(f"DONE presets={len(presets)} failures={len(failures)}", flush=True)


if __name__ == "__main__":
    main()
