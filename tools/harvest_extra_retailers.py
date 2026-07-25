#!/usr/bin/env python3
"""Harvest driver prices from retailers not covered by
enrich_driver_prices.py's built-in providers:

* Cinergy Audio (cinergyaudio.com) -- Shopify /products.json endpoint.
* Audiophonics (audiophonics.fr) -- PrestaShop-style storefront, English
  sitemap + product-page microdata/analytics JSON.
* DIY-Audio.eu (diy-audio.eu) -- PrestaShop-style storefront, sitemap +
  product-page data-product JSON attribute.
* Willy's HiFi (willys-hifi.com) -- Shopify /products.json endpoint, UK
  speaker-drivers-and-spares specialist, prices in GBP.
* Haut-Parleurs.fr (haut-parleurs.fr) -- PrestaShop-style storefront (French
  DIY driver specialist), sitemap + product-page data-product JSON attribute,
  same shape as Audiophonics/DIY-Audio.eu but with a direct manufacturer_name
  field so no category-name brand guessing is needed.
* Lautsprechershop (lautsprechershop.de) -- legacy multi-brand German static
  HTML storefront (Daniel Gattig GmbH), no product-per-page JSON API; each
  per-brand listing page embeds many products as repeated
  "<h2>Name</h2> order no. SKU <preis>EUR X,XX</preis>" blocks parsed with a
  dedicated regex instead of the PrestaShop/Shopify JSON patterns above.
* TopServicePro (topservicepro.it) -- WooCommerce Store API
  (/wp-json/wc/store/v1/products), public/unauthenticated, structured JSON.
* KJF Audio (kjfaudio.com) -- second confirmed WooCommerce Store API source
  (UK/EU Markaudio distributor + Bliesma/Cube Audio boutique reseller);
  category allow-list needed since most of the catalog is finished kits/
  amps/cables, not raw drivers.
* Hogtalarshoppen (hogtalarshoppen.se) -- third confirmed WooCommerce Store
  API source, Swedish multi-brand DIY driver retailer (Scan-Speak, Monacor,
  Visaton, Dayton Audio, Jantzen Audio, SB Acoustics, SEAS, Tang-Band).

Each harvester writes an independent JSON checkpoint under data/ so a partial
run can be resumed/merged without re-fetching everything. merge_extra_retailers
(see bottom of this file / merge_extra_retailers.py) then reuses
enrich_driver_prices.py's matching logic -- via the same fast precomputed
variant introduced in merge_partsexpress_harvest.py -- to attach matched
prices to data/driver_prices.json.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import enrich_driver_prices as epd  # noqa: E402

DATA_DIR = ROOT / "data"
CINERGY_CHECKPOINT = DATA_DIR / "cinergyaudio_harvest_checkpoint.json"
AUDIOPHONICS_CHECKPOINT = DATA_DIR / "audiophonics_harvest_checkpoint.json"
DIYAUDIOEU_CHECKPOINT = DATA_DIR / "diyaudioeu_harvest_checkpoint.json"
WILLYSHIFI_CHECKPOINT = DATA_DIR / "willyshifi_harvest_checkpoint.json"

CINERGY_BASE = "https://www.cinergyaudio.com"
CINERGY_DRIVER_TAGS = {"woofer", "tweeter", "midrange", "subwoofer"}

WILLYSHIFI_BASE = "https://willys-hifi.com"
WILLYSHIFI_DRIVER_TYPES = {"driver", "tweeter"}

AUDIOPHONICS_SITEMAP_INDEX = "https://www.audiophonics.fr/1_index_sitemap.xml"
AUDIOPHONICS_DRIVER_CATEGORIES = (
    "/en/woofer/",
    "/en/tweeter/",
    "/en/midrange-midbass-full-range/",
    "/en/horn-loudspeakers/",
    "/en/loudspeakers-subwoofers/",
    "/en/subwoofer-modules/",
)

DIYAUDIOEU_SITEMAP_INDEX = "https://www.diy-audio.eu/1_index_sitemap.xml"
DIYAUDIOEU_DRIVER_CATEGORIES = (
    "-woofers/",
    "-tweeters/",
)

HAUTPARLEURSFR_CHECKPOINT = DATA_DIR / "hautparleursfr_harvest_checkpoint.json"
LAUTSPRECHERSHOP_CHECKPOINT = DATA_DIR / "lautsprechershop_harvest_checkpoint.json"

HAUTPARLEURSFR_BASE = "https://www.haut-parleurs.fr/boutique"
HAUTPARLEURSFR_SITEMAP_INDEX = f"{HAUTPARLEURSFR_BASE}/sitemaps/shop_1/sitemap_shop_1_002.xml"
# Non-driver categories present in the same product sitemap -- excluded so we
# don't harvest crossover/amp-module/finished-kit prices as if they were
# drivers (product_looks_like_driver() also screens most of these out, this
# just avoids wasted fetches).
HAUTPARLEURSFR_SKIP_CATEGORIES = (
    "/modules-amplification/",
    "/kits-enceintes-diy/",
    "/cables-et-connectique/",
    "/accessoires/",
)

LAUTSPRECHERSHOP_BASE = "https://www.lautsprechershop.de"
LAUTSPRECHERSHOP_SITEMAP = f"{LAUTSPRECHERSHOP_BASE}/sitemap_en.xml"

TOPSERVICEPRO_CHECKPOINT = DATA_DIR / "topservicepro_harvest_checkpoint.json"
TOPSERVICEPRO_BASE = "https://www.topservicepro.it"
# WooCommerce Store API (public, no auth) -- returns the full catalog with
# price/brand/category data already structured as JSON, same "clean
# structured source" situation as the Parts Express/REDCATT APIs documented
# in the scrape playbook: no need for HTML scraping or a per-product fetch.
TOPSERVICEPRO_API = f"{TOPSERVICEPRO_BASE}/wp-json/wc/store/v1/products"
# Italian-language category-name allow/deny lists -- the catalog mixes real
# raw drivers (woofer/tweeter/coaxial/compression-driver/subwoofer/vintage
# lines) with recone kits, replacement diaphragms, crossovers, cables,
# connectors and other accessories under overlapping brand-scoped category
# trees. A category only counts as a "driver" category if it matches an
# allow keyword and none of the deny keywords (e.g. "Membrane Di Ricambio
# Per Driver HF" contains "driver" but is a replacement-diaphragm category,
# not a standalone product).
TOPSERVICEPRO_CATEGORY_ALLOW = (
    "woofer", "tweeter", "coassial", "compressione", "doppio cono",
    "subwoofer", "extended range", "vintage", "hi-fi", "studio monitor",
    "altoparlanti per basso", "altoparlanti per chitarra",
    "driver neodimio", "driver ferrite",
)
TOPSERVICEPRO_CATEGORY_DENY = (
    "ricambi", "recone", "crossover", "cavi", "connettori", "accessori",
    "tromb", "guida", "vaschette", "basette", "fusibili", "attenuatori",
    "condensatori", "induttanze", "colle", "tele acustiche", "terminali",
    "viti", "griglie", "angolari", "supporti", "cuffie", "microfono",
    "alimentatori", "kit", "membrane", "senza categoria",
)

KJFAUDIO_CHECKPOINT = DATA_DIR / "kjfaudio_harvest_checkpoint.json"
KJFAUDIO_BASE = "https://kjfaudio.com"
# Second confirmed WooCommerce Store API source (2026-07-24 round 7 sweep).
# KJF Audio is a UK/EU Markaudio distributor + boutique full-range/tweeter
# reseller (Bliesma, Cube Audio) but the bulk of its ~400-product catalog is
# finished speaker kits/cabinets, amplifier kits/modules, cables and
# hardware -- only a handful of WooCommerce product *categories* are actual
# standalone raw drivers, so an allow-list (not a deny-list, unlike
# TopServicePro's mostly-drivers catalog) keeps the harvest precise.
KJFAUDIO_CATEGORY_ALLOW = {
    "markaudio", "bliesma", "full range drivers", "speaker drivers",
    "tweeters", "woofers", "midrange", "subwoofers", "coaxial",
}

HOGTALARSHOPPEN_CHECKPOINT = DATA_DIR / "hogtalarshoppen_harvest_checkpoint.json"
HOGTALARSHOPPEN_BASE = "https://hogtalarshoppen.se"
# Third confirmed WooCommerce Store API source (2026-07-24 round 7 sweep) --
# found via a Swedish-language ("hogtalarelement kopa ... Sverige butik")
# search, resolving the previously-open Scandinavian gap noted in the scrape
# playbook. Multi-brand DIY driver retailer (Scan-Speak, Monacor, Visaton,
# Dayton Audio, Jantzen Audio, Markaudio, SB Acoustics, SB Audience, SEAS,
# Tang-Band) with real per-product `brands` taxonomy data, same shape as
# TopServicePro/KJF Audio. Catalog mixes raw drivers with finished kits/
# electronics/cables/capacitors/coils/terminals -- allow-listed to the
# actual driver-element categories.
HOGTALARSHOPPEN_CATEGORY_ALLOW = {
    "loudspeaker elements", "full range elements", "woofers", "midrange",
    "tweeter", "foil tweeters", "dome tweeter", "passive radiators",
    "coaxial", "passive membranes", "cone tweeters", "sound exciter",
}


def _get_json(url: str, timeout_s: float) -> dict:
    text = epd.fetch_text(url, timeout_s)
    return json.loads(text)


def _sitemap_urls_cdata(text: str) -> list[str]:
    urls = re.findall(r"<loc>\s*(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?\s*</loc>", text, re.S)
    return [epd.html_entity_decode(url.strip()) for url in urls]


def _sub_sitemaps(index_url: str, timeout_s: float) -> list[str]:
    text = epd.fetch_text(index_url, timeout_s)
    return _sitemap_urls_cdata(text)


# ---------------------------------------------------------------------------
# Cinergy Audio (Shopify)
# ---------------------------------------------------------------------------

def harvest_cinergy(sleep_s: float, timeout_s: float, limit_pages: int = 20) -> list[dict]:
    records = []
    for page in range(1, limit_pages + 1):
        url = f"{CINERGY_BASE}/products.json?limit=250&page={page}"
        try:
            payload = _get_json(url, timeout_s)
        except epd.FETCH_ERRORS as exc:
            epd.log(f"cinergy: fetch failed page={page}: {exc}")
            break
        products = payload.get("products", [])
        if not products:
            break
        for product in products:
            tags = {str(tag).strip().casefold() for tag in product.get("tags", [])}
            if not (tags & CINERGY_DRIVER_TAGS):
                continue
            title = str(product.get("title") or "")
            vendor = str(product.get("vendor") or "")
            handle = str(product.get("handle") or "")
            product_url = f"{CINERGY_BASE}/products/{handle}"
            for variant in product.get("variants", []):
                price = epd.number(variant.get("price"))
                if price is None:
                    continue
                sku = str(variant.get("sku") or "")
                records.append({
                    "name": title,
                    "brand": vendor,
                    "mpn": sku,
                    "sku": sku,
                    "url": product_url,
                    "price": round(price, 2),
                    "currency": "USD",
                    "availability": (
                        "https://schema.org/InStock" if variant.get("available")
                        else "https://schema.org/OutOfStock"
                    ),
                    "price_valid_until": "",
                })
        epd.log(f"cinergy: page={page} products={len(products)} kept={len(records)}")
        time.sleep(sleep_s)
    return records


# ---------------------------------------------------------------------------
# Willy's HiFi (Shopify, UK, GBP)
# ---------------------------------------------------------------------------

def harvest_willyshifi(sleep_s: float, timeout_s: float, limit_pages: int = 20) -> list[dict]:
    records = []
    for page in range(1, limit_pages + 1):
        url = f"{WILLYSHIFI_BASE}/products.json?limit=250&page={page}"
        try:
            payload = _get_json(url, timeout_s)
        except epd.FETCH_ERRORS as exc:
            epd.log(f"willyshifi: fetch failed page={page}: {exc}")
            break
        products = payload.get("products", [])
        if not products:
            break
        for product in products:
            product_type = str(product.get("product_type") or "").strip().casefold()
            if product_type not in WILLYSHIFI_DRIVER_TYPES:
                continue
            title = str(product.get("title") or "")
            vendor = str(product.get("vendor") or "")
            handle = str(product.get("handle") or "")
            product_url = f"{WILLYSHIFI_BASE}/products/{handle}"
            for variant in product.get("variants", []):
                price = epd.number(variant.get("price"))
                if price is None:
                    continue
                sku = str(variant.get("sku") or "")
                records.append({
                    "name": title,
                    "brand": vendor,
                    "mpn": sku,
                    "sku": sku,
                    "url": product_url,
                    "price": round(price, 2),
                    "currency": "GBP",
                    "availability": (
                        "https://schema.org/InStock" if variant.get("available")
                        else "https://schema.org/OutOfStock"
                    ),
                    "price_valid_until": "",
                })
        epd.log(f"willyshifi: page={page} products={len(products)} kept={len(records)}")
        time.sleep(sleep_s)
    return records


# ---------------------------------------------------------------------------
# Audiophonics (PrestaShop, EN storefront)
# ---------------------------------------------------------------------------

AP_ANALYTICS_RE = re.compile(
    r'\{"id":\d+,"name":"\\?"(?P<name>.*?)\\?"","category":"[^"]*","brand":"\\?"(?P<brand>.*?)\\?""'
    r'(?:,"variant":"[^"]*")?,"type":"[^"]*","position":"[^"]*",'
    r'"quantity":\d+,"list":"[^"]*","url":"[^"]*","price":"(?P<price>[0-9.]+)"\}'
)


def _audiophonics_product_urls(timeout_s: float) -> list[str]:
    sub_sitemaps = _sub_sitemaps(AUDIOPHONICS_SITEMAP_INDEX, timeout_s)
    en_sitemap = next((u for u in sub_sitemaps if "_en_" in u), sub_sitemaps[0] if sub_sitemaps else "")
    if not en_sitemap:
        return []
    text = epd.fetch_text(en_sitemap, timeout_s)
    urls = _sitemap_urls_cdata(text)
    out = []
    for url in urls:
        if not url.endswith(".html"):
            continue
        if any(cat in url for cat in AUDIOPHONICS_DRIVER_CATEGORIES) and "-p-" in url:
            out.append(url)
    return list(dict.fromkeys(out))


def _parse_audiophonics_product(text: str, url: str) -> dict | None:
    match = AP_ANALYTICS_RE.search(text)
    if match:
        name = epd.html_entity_decode(match.group("name"))
        brand = epd.html_entity_decode(match.group("brand"))
        price = epd.number(match.group("price"))
    else:
        name = ""
        brand = ""
        price = None
    if price is None:
        price_match = re.search(r'itemprop="price"\s*content="([0-9.]+)"', text)
        price = epd.number(price_match.group(1)) if price_match else None
    if price is None:
        return None
    if not name:
        h1_match = re.search(r'class="product_main_name">(.*?)</h1>', text, re.S)
        name = epd.clean_product_text(h1_match.group(1)) if h1_match else ""
    if not brand:
        brand_match = re.search(
            r'itemprop="brand"[^>]*>.*?itemprop="name"\s+content="([^"]+)"', text, re.S
        )
        brand = epd.html_entity_decode(brand_match.group(1)) if brand_match else ""
    sku_match = re.search(r'itemprop="sku"\s*content="([^"]*)"', text)
    sku = sku_match.group(1) if sku_match else ""
    currency_match = re.search(r'itemprop="priceCurrency"\s*content="([^"]+)"', text)
    currency = currency_match.group(1) if currency_match else "EUR"
    availability_match = re.search(r'itemprop="availability"\s+href="([^"]+)"', text)
    availability = availability_match.group(1) if availability_match else ""
    return {
        "name": name,
        "brand": brand,
        "mpn": sku,
        "sku": sku,
        "url": url,
        "price": round(price, 2),
        "currency": currency,
        "availability": availability,
        "price_valid_until": "",
    }


def harvest_audiophonics(sleep_s: float, timeout_s: float, limit: int | None = None) -> list[dict]:
    urls = _audiophonics_product_urls(timeout_s)
    if limit:
        urls = urls[:limit]
    epd.log(f"audiophonics: candidate product urls={len(urls)}")
    records = []
    for i, url in enumerate(urls, 1):
        try:
            text = epd.fetch_text(url, timeout_s)
        except epd.FETCH_ERRORS as exc:
            epd.log(f"audiophonics: fetch failed {url}: {exc}")
            continue
        record = _parse_audiophonics_product(text, url)
        if record:
            records.append(record)
        if i % 25 == 0:
            epd.log(f"audiophonics: {i}/{len(urls)} fetched, {len(records)} parsed")
        time.sleep(sleep_s)
    return records


# ---------------------------------------------------------------------------
# DIY-Audio.eu (PrestaShop, EN storefront)
# ---------------------------------------------------------------------------

DIYAUDIOEU_DATA_PRODUCT_RE = re.compile(
    r'data-product="(\{&quot;id_shop_default&quot;.*?&quot;availability&quot;:null\})"'
)


def _html_entity_decode_quot(value: str) -> str:
    return (
        value.replace("&quot;", '"')
        .replace("&amp;", "&")
        .replace("&#039;", "'")
    )


def _diyaudioeu_product_urls(timeout_s: float) -> list[str]:
    sub_sitemaps = _sub_sitemaps(DIYAUDIOEU_SITEMAP_INDEX, timeout_s)
    en_sitemap = next((u for u in sub_sitemaps if "_en_" in u), sub_sitemaps[0] if sub_sitemaps else "")
    if not en_sitemap:
        return []
    text = epd.fetch_text(en_sitemap, timeout_s)
    urls = _sitemap_urls_cdata(text)
    out = []
    for url in urls:
        if not url.endswith(".html"):
            continue
        if any(cat in url for cat in DIYAUDIOEU_DRIVER_CATEGORIES):
            out.append(url)
    return list(dict.fromkeys(out))


def _parse_diyaudioeu_product(text: str, url: str) -> dict | None:
    match = DIYAUDIOEU_DATA_PRODUCT_RE.search(text)
    name = ""
    brand = ""
    sku = ""
    price = None
    if match:
        blob = _html_entity_decode_quot(match.group(1))
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            data = {}
        name = str(data.get("name") or "")
        brand = str(data.get("category_name") or "")
        sku = str(data.get("reference") or "")
        price = epd.number(data.get("price_amount") or data.get("price_without_reduction"))
    if price is None:
        price_match = re.search(r"current-price-value['\"]\s+content=\"([0-9.]+)\"", text)
        price = epd.number(price_match.group(1)) if price_match else None
    if price is None:
        return None
    if not name:
        h1_match = re.search(r'class="h1 product-title-block">(.*?)</h1>', text, re.S)
        name = epd.clean_product_text(h1_match.group(1)) if h1_match else ""
    if not brand:
        brand_match = re.search(r'manufacturer-logo"\s+alt="([^"]+)"', text)
        brand = brand_match.group(1) if brand_match else ""
    return {
        "name": name,
        "brand": brand,
        "mpn": sku,
        "sku": sku,
        "url": url,
        "price": round(price, 2),
        "currency": "EUR",
        "availability": "",
        "price_valid_until": "",
    }


def harvest_diyaudioeu(sleep_s: float, timeout_s: float, limit: int | None = None) -> list[dict]:
    urls = _diyaudioeu_product_urls(timeout_s)
    if limit:
        urls = urls[:limit]
    epd.log(f"diyaudioeu: candidate product urls={len(urls)}")
    records = []
    for i, url in enumerate(urls, 1):
        try:
            text = epd.fetch_text(url, timeout_s)
        except epd.FETCH_ERRORS as exc:
            epd.log(f"diyaudioeu: fetch failed {url}: {exc}")
            continue
        record = _parse_diyaudioeu_product(text, url)
        if record:
            records.append(record)
        if i % 25 == 0:
            epd.log(f"diyaudioeu: {i}/{len(urls)} fetched, {len(records)} parsed")
        time.sleep(sleep_s)
    return records


# ---------------------------------------------------------------------------
# Haut-Parleurs.fr (PrestaShop, French DIY driver specialist)
# ---------------------------------------------------------------------------

HAUTPARLEURSFR_DATA_PRODUCT_RE = re.compile(
    r'data-product="(\{&quot;id_shop_default&quot;.*?&quot;availability&quot;:(?:null|&quot;[^&]*&quot;)\})"'
)


def _fetch_text_fr(url: str, timeout_s: float) -> str:
    """Like epd.fetch_text but with a French-priority Accept-Language.

    haut-parleurs.fr silently switches this PrestaShop store's displayed
    price from tax-included to tax-excluded (a genuine ~20% VAT difference,
    not noise) when the request's Accept-Language doesn't include "fr" --
    epd.fetch_text's fixed "en-US,en,it" header trips this, so this seller
    needs its own fetch helper rather than the shared one.
    """
    req = Request(
        epd.ascii_url(url),
        headers={
            "User-Agent": epd.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.5",
            "Cache-Control": "no-cache",
        },
    )
    with urlopen(req, timeout=timeout_s) as response:
        return response.read().decode("utf-8", errors="replace")


def _hautparleursfr_product_urls(timeout_s: float) -> list[str]:
    text = epd.fetch_text(HAUTPARLEURSFR_SITEMAP_INDEX, timeout_s)
    urls = _sitemap_urls_cdata(text)
    out = []
    for url in urls:
        if not url.endswith(".html"):
            continue
        if any(cat in url for cat in HAUTPARLEURSFR_SKIP_CATEGORIES):
            continue
        out.append(url)
    return list(dict.fromkeys(out))


def _parse_hautparleursfr_product(text: str, url: str) -> dict | None:
    match = HAUTPARLEURSFR_DATA_PRODUCT_RE.search(text)
    if not match:
        return None
    blob = _html_entity_decode_quot(match.group(1))
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return None
    price = epd.number(data.get("price_amount"))
    if price is None:
        return None
    name = str(data.get("name") or "")
    brand = str(data.get("manufacturer_name") or data.get("category_name") or "")
    sku = str(data.get("reference") or "")
    return {
        "name": name,
        "brand": brand,
        "mpn": sku,
        "sku": sku,
        "url": url,
        "price": round(price, 2),
        "currency": "EUR",
        "availability": "",
        "price_valid_until": "",
    }


def harvest_hautparleursfr(sleep_s: float, timeout_s: float, limit: int | None = None) -> list[dict]:
    urls = _hautparleursfr_product_urls(timeout_s)
    if limit:
        urls = urls[:limit]
    epd.log(f"hautparleursfr: candidate product urls={len(urls)}")
    records = []
    for i, url in enumerate(urls, 1):
        try:
            text = _fetch_text_fr(url, timeout_s)
        except epd.FETCH_ERRORS as exc:
            epd.log(f"hautparleursfr: fetch failed {url}: {exc}")
            continue
        record = _parse_hautparleursfr_product(text, url)
        if record:
            records.append(record)
        if i % 25 == 0:
            epd.log(f"hautparleursfr: {i}/{len(urls)} fetched, {len(records)} parsed")
        time.sleep(sleep_s)
    return records


# ---------------------------------------------------------------------------
# Lautsprechershop (legacy static HTML, German, multi-brand)
# ---------------------------------------------------------------------------

LSS_PRODUCT_BLOCK_RE = re.compile(
    r'<h2>([^<]+?)\s*<a name="[^"]*">.*?order no\. (\S+).*?<preis[^>]*>(.*?)</preis>',
    re.S,
)
LSS_PRICE_RE = re.compile(r"EUR\s*([0-9]+(?:[.,][0-9]+)?)")


def _lautsprechershop_category_urls(timeout_s: float) -> list[str]:
    text = epd.fetch_text(LAUTSPRECHERSHOP_SITEMAP, timeout_s)
    urls = _sitemap_urls_cdata(text)
    return [
        url for url in urls
        if "/chassis/" in url and not url.endswith("/main_en.htm")
    ]


def _parse_lautsprechershop_page(text: str, page_url: str) -> list[dict]:
    records = []
    for name_html, sku, price_html in LSS_PRODUCT_BLOCK_RE.findall(text):
        price_match = LSS_PRICE_RE.search(price_html)
        if not price_match:
            continue
        price = epd.number(price_match.group(1).replace(",", "."))
        if price is None:
            continue
        name = epd.clean_product_text(name_html)
        if not name:
            continue
        records.append({
            "name": name,
            "brand": "",
            "mpn": sku,
            "sku": sku,
            "url": f"{page_url}#{sku}",
            "price": round(price, 2),
            "currency": "EUR",
            "availability": "https://schema.org/InStock",
            "price_valid_until": "",
        })
    return records


def harvest_lautsprechershop(sleep_s: float, timeout_s: float, limit: int | None = None) -> list[dict]:
    urls = _lautsprechershop_category_urls(timeout_s)
    if limit:
        urls = urls[:limit]
    epd.log(f"lautsprechershop: candidate category pages={len(urls)}")
    records = []
    for i, url in enumerate(urls, 1):
        try:
            text = epd.fetch_text(url, timeout_s)
        except epd.FETCH_ERRORS as exc:
            epd.log(f"lautsprechershop: fetch failed {url}: {exc}")
            continue
        page_records = _parse_lautsprechershop_page(text, url)
        records.extend(page_records)
        if i % 10 == 0:
            epd.log(f"lautsprechershop: {i}/{len(urls)} pages fetched, {len(records)} parsed")
        time.sleep(sleep_s)
    return records


# ---------------------------------------------------------------------------
# TopServicePro (Italy, WooCommerce Store API -- new platform type)
# ---------------------------------------------------------------------------

def _topservicepro_is_driver_category(name: str) -> bool:
    lowered = name.casefold()
    if any(deny in lowered for deny in TOPSERVICEPRO_CATEGORY_DENY):
        return False
    return any(allow in lowered for allow in TOPSERVICEPRO_CATEGORY_ALLOW)


def _parse_topservicepro_product(product: dict) -> dict | None:
    categories = [str(c.get("name") or "") for c in product.get("categories", [])]
    if not any(_topservicepro_is_driver_category(name) for name in categories):
        return None
    prices = product.get("prices") or {}
    raw_price = epd.number(prices.get("price"))
    if raw_price is None:
        return None
    minor_unit = prices.get("currency_minor_unit")
    try:
        minor_unit = int(minor_unit)
    except (TypeError, ValueError):
        minor_unit = 2
    price = raw_price / (10 ** minor_unit)
    if price <= 0:
        return None
    name = epd.clean_product_text(epd.html_entity_decode(str(product.get("name") or "")))
    if not name:
        return None
    brands = product.get("brands") or []
    brand = epd.html_entity_decode(str(brands[0].get("name") or "")) if brands else ""
    sku = str(product.get("sku") or "")
    url = str(product.get("permalink") or "")
    if not url:
        return None
    currency = str(prices.get("currency_code") or "EUR")
    return {
        "name": name,
        "brand": brand,
        "mpn": sku,
        "sku": sku,
        "url": url,
        "price": round(price, 2),
        "currency": currency,
        "availability": "",
        "price_valid_until": "",
    }


def harvest_topservicepro(sleep_s: float, timeout_s: float, limit_pages: int = 20) -> list[dict]:
    records = []
    page = 1
    while limit_pages is None or page <= limit_pages:
        url = f"{TOPSERVICEPRO_API}?per_page=100&page={page}"
        try:
            payload = _get_json(url, timeout_s)
        except epd.FETCH_ERRORS as exc:
            epd.log(f"topservicepro: fetch failed page={page}: {exc}")
            break
        if not payload:
            break
        for product in payload:
            record = _parse_topservicepro_product(product)
            if record:
                records.append(record)
        epd.log(f"topservicepro: page={page} products={len(payload)} kept={len(records)}")
        if len(payload) < 100:
            break
        page += 1
        time.sleep(sleep_s)
    return records


def _kjfaudio_is_driver_category(name: str) -> bool:
    return name.casefold() in KJFAUDIO_CATEGORY_ALLOW


def _parse_kjfaudio_product(product: dict) -> dict | None:
    categories = [str(c.get("name") or "") for c in product.get("categories", [])]
    if not any(_kjfaudio_is_driver_category(name) for name in categories):
        return None
    prices = product.get("prices") or {}
    raw_price = epd.number(prices.get("price"))
    if raw_price is None:
        return None
    minor_unit = prices.get("currency_minor_unit")
    try:
        minor_unit = int(minor_unit)
    except (TypeError, ValueError):
        minor_unit = 2
    price = raw_price / (10 ** minor_unit)
    if price <= 0:
        return None
    name = epd.clean_product_text(epd.html_entity_decode(str(product.get("name") or "")))
    if not name:
        return None
    brands = product.get("brands") or []
    brand = epd.html_entity_decode(str(brands[0].get("name") or "")) if brands else ""
    sku = str(product.get("sku") or "")
    url = str(product.get("permalink") or "")
    if not url:
        return None
    currency = str(prices.get("currency_code") or "GBP")
    return {
        "name": name,
        "brand": brand,
        "mpn": sku,
        "sku": sku,
        "url": url,
        "price": round(price, 2),
        "currency": currency,
        "availability": "",
        "price_valid_until": "",
    }


def harvest_kjfaudio(sleep_s: float, timeout_s: float, limit_pages: int = 20) -> list[dict]:
    records = []
    page = 1
    while limit_pages is None or page <= limit_pages:
        url = f"{KJFAUDIO_BASE}/wp-json/wc/store/v1/products?per_page=100&page={page}"
        try:
            payload = _get_json(url, timeout_s)
        except epd.FETCH_ERRORS as exc:
            epd.log(f"kjfaudio: fetch failed page={page}: {exc}")
            break
        if not payload:
            break
        for product in payload:
            record = _parse_kjfaudio_product(product)
            if record:
                records.append(record)
        epd.log(f"kjfaudio: page={page} products={len(payload)} kept={len(records)}")
        if len(payload) < 100:
            break
        page += 1
        time.sleep(sleep_s)
    return records


def _hogtalarshoppen_is_driver_category(name: str) -> bool:
    return name.casefold() in HOGTALARSHOPPEN_CATEGORY_ALLOW


def _parse_hogtalarshoppen_product(product: dict) -> dict | None:
    categories = [str(c.get("name") or "") for c in product.get("categories", [])]
    if not any(_hogtalarshoppen_is_driver_category(name) for name in categories):
        return None
    prices = product.get("prices") or {}
    raw_price = epd.number(prices.get("price"))
    if raw_price is None:
        return None
    minor_unit = prices.get("currency_minor_unit")
    try:
        minor_unit = int(minor_unit)
    except (TypeError, ValueError):
        minor_unit = 2
    price = raw_price / (10 ** minor_unit)
    if price <= 0:
        return None
    name = epd.clean_product_text(epd.html_entity_decode(str(product.get("name") or "")))
    if not name:
        return None
    brands = product.get("brands") or []
    brand = epd.html_entity_decode(str(brands[0].get("name") or "")) if brands else ""
    sku = str(product.get("sku") or "")
    url = str(product.get("permalink") or "")
    if not url:
        return None
    currency = str(prices.get("currency_code") or "SEK")
    return {
        "name": name,
        "brand": brand,
        "mpn": sku,
        "sku": sku,
        "url": url,
        "price": round(price, 2),
        "currency": currency,
        "availability": "",
        "price_valid_until": "",
    }


def harvest_hogtalarshoppen(sleep_s: float, timeout_s: float, limit_pages: int = 20) -> list[dict]:
    records = []
    page = 1
    while limit_pages is None or page <= limit_pages:
        url = f"{HOGTALARSHOPPEN_BASE}/wp-json/wc/store/v1/products?per_page=100&page={page}"
        try:
            payload = _get_json(url, timeout_s)
        except epd.FETCH_ERRORS as exc:
            epd.log(f"hogtalarshoppen: fetch failed page={page}: {exc}")
            break
        if not payload:
            break
        for product in payload:
            record = _parse_hogtalarshoppen_product(product)
            if record:
                records.append(record)
        epd.log(f"hogtalarshoppen: page={page} products={len(payload)} kept={len(records)}")
        if len(payload) < 100:
            break
        page += 1
        time.sleep(sleep_s)
    return records


HARVESTERS = {
    "cinergyaudio": (harvest_cinergy, CINERGY_CHECKPOINT),
    "audiophonics": (harvest_audiophonics, AUDIOPHONICS_CHECKPOINT),
    "diyaudioeu": (harvest_diyaudioeu, DIYAUDIOEU_CHECKPOINT),
    "willyshifi": (harvest_willyshifi, WILLYSHIFI_CHECKPOINT),
    "hautparleursfr": (harvest_hautparleursfr, HAUTPARLEURSFR_CHECKPOINT),
    "lautsprechershop": (harvest_lautsprechershop, LAUTSPRECHERSHOP_CHECKPOINT),
    "topservicepro": (harvest_topservicepro, TOPSERVICEPRO_CHECKPOINT),
    "kjfaudio": (harvest_kjfaudio, KJFAUDIO_CHECKPOINT),
    "hogtalarshoppen": (harvest_hogtalarshoppen, HOGTALARSHOPPEN_CHECKPOINT),
}

PAGE_LIMIT_SOURCES = {
    "cinergyaudio", "willyshifi", "topservicepro", "kjfaudio", "hogtalarshoppen",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=sorted(HARVESTERS), required=True)
    parser.add_argument("--sleep", type=float, default=0.4)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--limit", type=int, default=None)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    harvester, checkpoint_path = HARVESTERS[args.source]
    kwargs = {"sleep_s": args.sleep, "timeout_s": args.timeout}
    if args.source not in PAGE_LIMIT_SOURCES:
        kwargs["limit"] = args.limit
    records = harvester(**kwargs)
    checkpoint_path.write_text(
        json.dumps({"source": args.source, "prices": records}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    epd.log(f"{args.source}: wrote {len(records)} records to {checkpoint_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
