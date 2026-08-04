#!/usr/bin/env python3
"""Harvest the public TLHP cone-speaker catalog through an open Safari session.

ToutLeHautParleur serves ordinary catalog HTML after an interactive Cloudflare
check, while direct non-browser requests receive only the challenge page.  This
tool opens one temporary Safari tab per page, reads that tab's public HTML, and
closes it immediately.  The checkpoint is written after every page so a crawl
can be interrupted and resumed safely.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import urlencode

import crawl_thiele_small as ts_crawler
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://en.toutlehautparleur.com/speakers/cone-speaker.html"
DEFAULT_OUTPUT = ROOT / "data" / "toutlehautparleur_harvest_checkpoint.json"
DEFAULT_CATALOG = ROOT / "data" / "manufacturer_drivers.json"
SELLER = "ToutLeHautParleur"
DEFAULT_PAGE_SIZE = 8

SAFARI_SOURCE_SCRIPT = r'''
on run argv
    set targetURL to item 1 of argv
    set timeoutSeconds to (item 2 of argv) as integer
    set readyMarker to item 3 of argv
    tell application "Safari"
        if not (exists front window) then error "Safari has no open window"
        set crawlTab to make new tab at end of tabs of front window with properties {URL:targetURL}
        set pageSource to ""
        repeat timeoutSeconds times
            delay 1
            try
                set pageSource to source of crawlTab
                if pageSource contains readyMarker then exit repeat
            end try
        end repeat
        close crawlTab
        if pageSource does not contain readyMarker then error "TLHP page did not load"
        return pageSource
    end tell
end run
'''


def page_url(page: int) -> str:
    return f"{BASE_URL}?{urlencode({'dir': 'asc', 'order': 'name', 'p': max(1, page)})}"


def fetch_safari_source(url: str, timeout_s: int, ready_marker: str) -> str:
    """Read one exact TLHP catalog URL through Safari and close the temp tab."""
    category_page = re.fullmatch(
        re.escape(BASE_URL) + r"\?dir=asc&order=name&p=\d+",
        url,
    )
    product_page = re.fullmatch(r"https://en\.toutlehautparleur\.com/[a-z0-9][a-z0-9_./-]*\.html", url)
    if not category_page and not product_page:
        raise ValueError(f"refusing non-catalog URL: {url}")
    result = subprocess.run(
        ["osascript", "-e", SAFARI_SOURCE_SCRIPT, url, str(max(5, timeout_s)), ready_marker],
        check=False,
        capture_output=True,
        text=True,
        timeout=max(10, timeout_s + 10),
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Safari source extraction failed")
    return result.stdout


def _availability(text: str) -> str:
    lowered = text.casefold()
    if "out of stock" in lowered:
        return "OutOfStock"
    if "in stock" in lowered:
        return "InStock"
    return "Unknown"


def parse_catalog_page(html: str) -> tuple[list[dict], int, int]:
    """Return product offers, total product count and total page count."""
    soup = BeautifulSoup(html, "html.parser")
    count_match = re.search(
        r"Items\s+\d+\s+to\s+\d+\s+of\s+([\d, .]+)",
        soup.get_text(" ", strip=True),
        re.IGNORECASE,
    )
    total = int(re.sub(r"\D", "", count_match.group(1))) if count_match else 0
    page_numbers = []
    for anchor in soup.select(".pages a[href]"):
        match = re.search(r"[?&]p=(\d+)", str(anchor.get("href") or ""))
        if match:
            page_numbers.append(int(match.group(1)))
    total_pages = max(page_numbers, default=math.ceil(total / DEFAULT_PAGE_SIZE) if total else 0)

    products: list[dict] = []
    for row in soup.select("table.product-list-ligne"):
        heading = row.select_one(".product-add-to-cart-ligne h3 a[href]")
        price_node = row.select_one(".price-display")
        if heading is None:
            continue
        heading_parts = list(heading.stripped_strings)
        if len(heading_parts) < 2:
            continue
        brand = heading_parts[0].strip()
        sku = " ".join(heading_parts[1:]).strip()
        description_cell = row.select_one(".product-description-ligne")
        description_parts = list(description_cell.stripped_strings) if description_cell else []
        mpn = description_parts[0].strip() if description_parts else sku
        price = None
        if price_node is not None:
            raw_price = re.sub(r"[^\d.,]", "", price_node.get_text("", strip=True))
            try:
                price = float(raw_price.replace(",", "."))
            except ValueError:
                price = None
        title = str(heading.get("title") or " ".join(heading_parts)).strip()
        url = str(heading.get("href") or "").strip()
        if not url.startswith("https://en.toutlehautparleur.com/"):
            continue
        products.append(
            {
                "name": title,
                "brand": brand,
                "mpn": mpn,
                "sku": sku,
                "url": url,
                "price": price,
                "currency": "EUR",
                "availability": _availability(row.get_text(" ", strip=True)),
            }
        )
    return products, total, total_pages


def _empty_state() -> dict:
    return {
        "source": SELLER,
        "source_url": BASE_URL,
        "updated_at": "",
        "total_products": 0,
        "total_pages": 0,
        "completed_pages": [],
        "completed_products": [],
        "ts_failures": {},
        "prices": [],
        "presets": [],
    }


def load_state(path: Path, fresh: bool) -> dict:
    if fresh or not path.exists():
        return _empty_state()
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else _empty_state()


def write_state(path: Path, state: dict) -> None:
    state["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _identity(brand: str, model: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", f"{brand} {model}".casefold())


def catalog_identities(paths: list[Path]) -> set[str]:
    identities: set[str] = set()
    for path in paths:
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        for item in payload.get("presets", []):
            if isinstance(item, dict):
                identities.add(_identity(str(item.get("brand") or ""), str(item.get("model") or "")))
    return identities


def merge_discovered_presets(catalog_path: Path, discovered: list[dict]) -> dict:
    if not discovered:
        return {"added": 0, "updated": 0, "unchanged": 0}
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    merged, stats = ts_crawler.merge_presets(payload.get("presets", []), discovered)
    payload["presets"] = merged
    ts_crawler.atomic_write_json(catalog_path, payload)
    return stats


def build_ts_preset(html: str, offer: dict) -> tuple[dict | None, list[str]]:
    page = ts_crawler.parse_html(html.encode("utf-8"))
    preset, errors = ts_crawler.build_preset(
        page,
        str(offer["url"]),
        source_name="ToutLeHautParleur product page",
        brand_hint=str(offer.get("brand") or ""),
    )
    if preset is None:
        return None, errors
    brand = str(offer.get("brand") or preset.get("brand") or "").strip()
    model = str(offer.get("sku") or offer.get("mpn") or preset.get("model") or "").strip()
    preset.update(
        name=f"WEB: {brand} {model}".strip(),
        brand=brand,
        model=model,
        price_url=str(offer["url"]),
        availability=str(offer.get("availability") or "Unknown"),
        seller=SELLER,
    )
    if offer.get("price") is not None:
        preset.update(price=float(offer["price"]), currency="EUR")
    preset["website_fields"].update(brand=brand, model=model, retailer=SELLER)
    return preset, []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--max-pages", type=int, default=0, help="0 crawls every remaining page")
    parser.add_argument("--max-products", type=int, default=0, help="0 checks every new product for T/S data")
    parser.add_argument("--prices-only", action="store_true")
    parser.add_argument("--retry-failures", action="store_true")
    parser.add_argument("--catalog-output", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--sleep", type=float, default=0.5)
    args = parser.parse_args()

    state = load_state(args.output, args.fresh)
    completed = {int(page) for page in state.get("completed_pages", [])}
    offers = {
        f"{item.get('url', '')}#{item.get('sku', '')}": item
        for item in state.get("prices", [])
        if isinstance(item, dict) and item.get("url")
    }
    page = 1
    processed = 0
    known_total_pages = int(state.get("total_pages") or 0)
    while not known_total_pages or page <= known_total_pages:
        if page in completed:
            page += 1
            continue
        if args.max_pages > 0 and processed >= args.max_pages:
            break
        url = page_url(page)
        print(f"page {page}/{known_total_pages or '?'}: {url}", flush=True)
        html = fetch_safari_source(url, args.timeout, "product-list-ligne")
        products, total_products, total_pages = parse_catalog_page(html)
        if not products:
            raise RuntimeError(f"page {page} contained no product offers")
        for item in products:
            offers[f"{item['url']}#{item['sku']}"] = item
        completed.add(page)
        known_total_pages = max(known_total_pages, total_pages)
        state.update(
            total_products=max(int(state.get("total_products") or 0), total_products),
            total_pages=known_total_pages,
            completed_pages=sorted(completed),
            prices=list(offers.values()),
        )
        write_state(args.output, state)
        processed += 1
        print(
            f"saved page={page} offers={len(products)} total_saved={len(offers)} "
            f"progress={len(completed)}/{known_total_pages}",
            flush=True,
        )
        page += 1
        time.sleep(max(0.0, args.sleep))

    if args.prices_only:
        return 0

    catalog_paths = [
        ROOT / "data" / "catalog_proprietario.json",
        ROOT / "data" / "catalog_lsdb.json",
        ROOT / "data" / "catalog_vituixcad.json",
        ROOT / "data" / "catalog_speakerboxlite.json",
    ]
    known_identities = catalog_identities(catalog_paths)
    completed_products = set(state.get("completed_products", []))
    failures = state.setdefault("ts_failures", {})
    discovered = {
        str(item.get("url")): item
        for item in state.get("presets", [])
        if isinstance(item, dict) and item.get("url")
    }
    fetched_products = 0
    for offer in state.get("prices", []):
        url = str(offer.get("url") or "")
        offer_identities = {
            _identity(str(offer.get("brand") or ""), str(offer.get(field) or ""))
            for field in ("mpn", "sku")
        }
        if known_identities.intersection(offer_identities):
            completed_products.add(url)
            continue
        if url in completed_products and not (args.retry_failures and url in failures):
            continue
        if url in failures and not args.retry_failures:
            continue
        if args.max_products > 0 and fetched_products >= args.max_products:
            break
        print(f"T/S {fetched_products + 1}: {url}", flush=True)
        try:
            html = fetch_safari_source(url, args.timeout, "product-essential")
            preset, errors = build_ts_preset(html, offer)
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            preset, errors = None, [str(exc)]
        if preset is None:
            failures[url] = errors
            print(f"rejected T/S: {'; '.join(errors)}", flush=True)
        else:
            discovered[url] = preset
            known_identities.add(_identity(str(preset["brand"]), str(preset["model"])))
            failures.pop(url, None)
            print(f"accepted T/S: {preset['brand']} {preset['model']}", flush=True)
        completed_products.add(url)
        fetched_products += 1
        state.update(
            completed_products=sorted(completed_products),
            presets=list(discovered.values()),
        )
        write_state(args.output, state)
        if fetched_products % 25 == 0:
            print(f"catalog merge: {merge_discovered_presets(args.catalog_output, list(discovered.values()))}", flush=True)
        time.sleep(max(0.0, args.sleep))
    stats = merge_discovered_presets(args.catalog_output, list(discovered.values()))
    print(
        f"done offers={len(state.get('prices', []))} T/S={len(discovered)} "
        f"rejected={len(failures)} catalog={stats}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
