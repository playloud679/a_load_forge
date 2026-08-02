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
* DIYSpeakersEU (diyspeakers.eu) -- fourth WooCommerce Store API source,
  small clean multi-brand catalog (Scan-Speak, SEAS, Dayton Audio).
* AnalogHiFi (analoghifi.no) -- fifth WooCommerce Store API source,
  Norwegian SEAS/Scan-Speak/Mark Audio/Dayton/Peerless reseller; brand and
  driver-vs-accessory identification both go through the category link
  path since the `brands` taxonomy field is empty on every product.
* Thomann (thomann.de) -- structured search bootstrap data, queried only for
  runtime-library brands that still have unpriced models. Pagination follows
  the canonical links returned by Thomann instead of guessing query params.
* DS18 (ds18.com) -- official Shopify catalog; only variants whose SKU exactly
  identifies a DS18 model present in the runtime library are retained.
* Fi Car Audio (ficaraudio.com) -- official BigCommerce brand pages and live
  product options, emitting one offer identity per explicit impedance choice.
* Wavecor (wavecor.com) -- official manufacturer retail price table, expanded
  from compact slash notation into individual model identities.
* AUDIO-HI.FI (audio-hi.fi) -- paginated European Tang Band catalog with
  per-unit EUR prices and direct product links.

Each harvester writes an independent JSON checkpoint under data/ so a partial
run can be resumed/merged without re-fetching everything. merge_extra_retailers
(see bottom of this file / merge_extra_retailers.py) then reuses the indexed
matcher in enrich_driver_prices.py to attach matched prices to
data/driver_prices.json.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import os
import re
import ssl
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote, urljoin
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

DIYSPEAKERSEU_CHECKPOINT = DATA_DIR / "diyspeakerseu_harvest_checkpoint.json"
DIYSPEAKERSEU_BASE = "https://diyspeakers.eu"
# Fourth confirmed WooCommerce Store API source (2026-07-25 round 9 sweep) --
# found via a Poland/general-EU DIY-driver-shop search. Small (126 products)
# but clean single-category catalog (Woofers/Tweeters/Midranges/Subwoofers/
# Fullrange/Passive radiator/Car audio) already dominated by real raw
# drivers (Scan-Speak, SEAS, Dayton Audio etc.), same `brands` taxonomy
# shape as Hogtalarshoppen/KJF Audio/TopServicePro -- allow-listed to the
# same effect as a safety net in case the catalog grows non-driver
# categories later.
DIYSPEAKERSEU_CATEGORY_ALLOW = {
    "woofers", "tweeters", "midranges", "subwoofers", "fullrange",
    "passive radiator", "car audio",
}

ANALOGHIFI_CHECKPOINT = DATA_DIR / "analoghifi_harvest_checkpoint.json"
ANALOGHIFI_BASE = "https://analoghifi.no"
# Fifth confirmed WooCommerce Store API source (2026-07-25 round 10 sweep) --
# found via a Norwegian-language search, resolving the standing Scandinavian
# gap for Norway specifically (round 7 only found Sweden's Hogtalarshoppen).
# Real multi-brand SEAS/Scan-Speak/Mark Audio/Dayton/Peerless by Tymphany
# reseller, but the catalog is dominated by crossover components (Jantzen
# capacitors/coils/binding posts) and SEAS repair kits/DIY build kits, not
# raw drivers -- unlike the taxonomy-based allow-lists above, this site's
# `brands` product field is empty on every product sampled, so driver
# identification and brand assignment both go through the WooCommerce
# category *link path* instead: every genuine standalone driver category
# lives under .../product-category/hoyttalerelementer/<brand-slug>/... ,
# while "seas-rep-kits" (repair parts, not full drivers) is the one
# sub-category under that same tree that must be denied explicitly.
ANALOGHIFI_CATEGORY_ALLOW_PATH = "/product-category/hoyttalerelementer/"
ANALOGHIFI_CATEGORY_DENY_SLUGS = {"seas-rep-kits"}
ANALOGHIFI_BRAND_BY_SLUG = {
    "seas": "SEAS",
    "scan-speak": "Scan-Speak",
    "dayton": "Dayton Audio",
    "mark-audio": "Markaudio",
    "peerless-by-thymphany": "Peerless",
    "mundorf": "Mundorf",
    "jantzen": "Jantzen Audio",
}

THOMANN_CHECKPOINT = DATA_DIR / "thomann_harvest_checkpoint.json"
THOMANN_BASE = "https://www.thomann.de/intl/"
DS18_CHECKPOINT = DATA_DIR / "ds18_harvest_checkpoint.json"
DS18_BASE = "https://www.ds18.com"
FICARAUDIO_CHECKPOINT = DATA_DIR / "ficaraudio_harvest_checkpoint.json"
FICARAUDIO_BASE = "https://ficaraudio.com"
WAVECOR_CHECKPOINT = DATA_DIR / "wavecor_harvest_checkpoint.json"
WAVECOR_PRICE_URL = "https://wavecor.com/html/retail_price_list.html"
AUDIOHIFI_CHECKPOINT = DATA_DIR / "audiohifi_harvest_checkpoint.json"
AUDIOHIFI_TANGBAND_URL = "https://audio-hi.fi/en/tang_band-m-14.html"


def _thomann_search_payload(text: str) -> dict:
    """Extract Thomann's structured search bootstrap payload."""
    marker = "tho.bootstrapModule('search.index', "
    start = text.find(marker)
    if start < 0:
        return {}
    start += len(marker)
    try:
        values, _end = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError:
        return {}
    if not isinstance(values, list) or not values or not isinstance(values[0], dict):
        return {}
    return values[0]


def _thomann_paging_links(text: str) -> list[str]:
    """Return canonical result-page URLs exposed by Thomann's payload."""
    payload = _thomann_search_payload(text)
    paging = payload.get("pagingSettings") or {}
    pages = paging.get("pages") or []
    try:
        current_page = int(paging.get("currentPage") or 1)
    except (TypeError, ValueError):
        current_page = 1
    links = []
    for page in pages:
        if not isinstance(page, dict) or page.get("type") != "page":
            continue
        try:
            page_number = int(page.get("page") or 0)
        except (TypeError, ValueError):
            page_number = 0
        if page_number <= current_page:
            continue
        link = str(page.get("link") or "")
        if link:
            links.append(urljoin(THOMANN_BASE, link.replace("\\/", "/")))
    return list(dict.fromkeys(links))


def thomann_records_from_html(text: str, expected_brand: str) -> tuple[list[dict], int]:
    payload = _thomann_search_payload(text)
    article_lists = payload.get("articleListsSettings") or {}
    expected_compacts = epd.brand_compacts(expected_brand)
    records = []
    seen_urls = set()
    for section in ("articles", "alternativeArticles"):
        for article in article_lists.get(section, []) or []:
            if not isinstance(article, dict):
                continue
            brand = str(article.get("manufacturer") or "")
            if expected_compacts and not (expected_compacts & epd.brand_compacts(brand)):
                continue
            if article.get("isBstock") or article.get("isArchived"):
                continue
            primary = ((article.get("price") or {}).get("primary") or {})
            price = epd.number(primary.get("rawPrice"))
            currency = str((primary.get("currency") or {}).get("key") or "")
            relative_url = str(article.get("relativeLink") or "").split("?", 1)[0]
            if price is None or not currency or not relative_url:
                continue
            url = urljoin(THOMANN_BASE, relative_url)
            if url in seen_urls:
                continue
            seen_urls.add(url)
            model = str(article.get("model") or "")
            title = str(((article.get("texts") or {}).get("title")) or model)
            availability = article.get("availability") or {}
            records.append({
                "name": title,
                "brand": brand,
                "mpn": model,
                "sku": str(article.get("number") or ""),
                "url": url,
                "price": round(price, 2),
                "currency": currency,
                "availability": str(availability.get("label") or ""),
                "price_valid_until": "",
            })
    try:
        last_page = int((payload.get("pagingSettings") or {}).get("lastPage") or 1)
    except (TypeError, ValueError):
        last_page = 1
    return records, max(1, last_page)


def harvest_thomann(sleep_s: float, timeout_s: float, limit: int | None = None) -> list[dict]:
    """Search every still-unpriced runtime brand in Thomann's live catalog."""
    candidates = epd.load_library_candidates()
    prices = epd.load_output(epd.DEFAULT_OUTPUT).get("prices", {})
    missing_brand_counts = Counter(
        candidate.brand.strip()
        for candidate in candidates
        if candidate.brand.strip()
        and candidate.brand.strip().casefold() != "other"
        and candidate.name not in prices
        and candidate.model not in prices
    )
    missing_brands = []
    seen_brand_compacts = set()
    for brand, _count in missing_brand_counts.most_common():
        compacts = epd.brand_compacts(brand)
        if compacts & seen_brand_compacts:
            continue
        missing_brands.append(brand)
        seen_brand_compacts.update(compacts)
    if limit is not None:
        missing_brands = missing_brands[:max(0, int(limit))]
    records_by_url = {}
    for brand_index, brand in enumerate(missing_brands, start=1):
        query = quote(brand, safe="")
        pending_urls = [f"{THOMANN_BASE}search_dir.html?sw={query}"]
        seen_pages = set()
        page = 0
        while pending_urls:
            url = pending_urls.pop(0)
            if url in seen_pages:
                continue
            seen_pages.add(url)
            page += 1
            try:
                text = epd.fetch_text(url, timeout_s)
            except epd.FETCH_ERRORS as exc:
                epd.log(f"thomann: miss brand={brand} page={page}: {exc}")
                break
            page_records, discovered_last_page = thomann_records_from_html(text, brand)
            if page == 1 and not page_records:
                epd.log(
                    f"thomann: brand={brand_index}/{len(missing_brands)} "
                    f"no exact-brand products"
                )
                break
            for next_url in _thomann_paging_links(text):
                if next_url not in seen_pages and next_url not in pending_urls:
                    pending_urls.append(next_url)
            for record in page_records:
                records_by_url[record["url"]] = record
            epd.log(
                f"thomann: brand={brand_index}/{len(missing_brands)} name={brand} "
                f"page={page}/{discovered_last_page} "
                f"products={len(page_records)} kept={len(records_by_url)}"
            )
            time.sleep(sleep_s)
    return list(records_by_url.values())


def ds18_records_from_products(products: list[dict], model_keys: set[str]) -> list[dict]:
    """Extract only exact runtime-library SKUs from a Shopify product page."""
    records = []
    for product in products:
        title = str(product.get("title") or "")
        handle = str(product.get("handle") or "")
        if not title or not handle:
            continue
        product_url = f"{DS18_BASE}/products/{handle}"
        for variant in product.get("variants", []) or []:
            sku = str(variant.get("sku") or "").strip()
            if not sku or epd.normalize_token(sku) not in model_keys:
                continue
            price = epd.number(variant.get("price"))
            if price is None:
                continue
            records.append({
                "name": title,
                "brand": "DS18",
                "mpn": sku,
                "sku": sku,
                "url": product_url,
                "price": round(price, 2),
                "currency": "USD",
                "availability": (
                    "https://schema.org/InStock"
                    if variant.get("available")
                    else "https://schema.org/OutOfStock"
                ),
                "price_valid_until": "",
            })
    return records


def harvest_ds18(sleep_s: float, timeout_s: float, limit_pages: int = 20) -> list[dict]:
    candidates = [
        candidate
        for candidate in epd.load_library_candidates()
        if "ds18" in epd.brand_compacts(candidate.brand)
    ]
    model_keys = {
        key
        for candidate in candidates
        for key in epd.model_compacts(candidate.model)
        if key
    }
    records_by_sku = {}
    for page in range(1, limit_pages + 1):
        try:
            payload = _get_json(
                f"{DS18_BASE}/products.json?limit=250&page={page}",
                timeout_s,
            )
        except epd.FETCH_ERRORS as exc:
            epd.log(f"ds18: fetch failed page={page}: {exc}")
            break
        products = payload.get("products", [])
        if not products:
            break
        page_records = ds18_records_from_products(products, model_keys)
        for record in page_records:
            records_by_sku[record["sku"]] = record
        epd.log(
            f"ds18: page={page} products={len(products)} "
            f"matched_skus={len(records_by_sku)}"
        )
        time.sleep(sleep_s)
    return list(records_by_sku.values())


FI_CARD_RE = re.compile(
    r'<article\b(?P<attrs>[^>]*\bdata-name="[^"]+"[^>]*)>.*?'
    r'<a\s+href="(?P<url>https://ficaraudio\.com/[^"]+/)"[^>]*class="card-figure__link"',
    re.S | re.I,
)


def fi_category_products(text: str) -> list[dict]:
    """Extract BigCommerce product identities from a Fi brand page."""
    products = []
    seen = set()
    for match in FI_CARD_RE.finditer(text):
        attrs = match.group("attrs")
        name_match = re.search(r'\bdata-name="([^"]+)"', attrs, re.I)
        price_match = re.search(r'\bdata-product-price="\s*([0-9.,]+)\s*"', attrs, re.I)
        url = epd.html_entity_decode(match.group("url"))
        price = epd.number(price_match.group(1)) if price_match else None
        if not name_match or price is None or url in seen:
            continue
        seen.add(url)
        products.append({
            "name": epd.html_entity_decode(name_match.group(1)).strip(),
            "url": url,
            "price": round(price, 2),
        })
    return products


def fi_records_from_product_html(text: str, product: dict) -> list[dict]:
    """Expand a Fi product into its explicitly offered impedance variants."""
    price_match = re.search(
        r'<meta\s+property="product:price:amount"\s+content="([0-9.,]+)"',
        text,
        re.I,
    )
    price = epd.number(price_match.group(1)) if price_match else epd.number(product.get("price"))
    if price is None:
        return []
    impedance_start = re.search(r'>\s*Impedance:\s*<', text, re.I)
    impedance_block = text[impedance_start.start():impedance_start.start() + 5000] if impedance_start else ""
    impedances = list(dict.fromkeys(
        epd.clean_product_text(value)
        for value in re.findall(r'class="form-option-variant">(.*?)</span>', impedance_block, re.S | re.I)
        if epd.clean_product_text(value)
    ))
    if not impedances:
        impedances = [""]
    base_name = re.sub(r"\b(?:series|subwoofers?)\b", " ", str(product.get("name") or ""), flags=re.I)
    base_name = re.sub(r"\s+", " ", base_name).strip()
    records = []
    for impedance in impedances:
        model = f"{base_name} {impedance}".strip()
        records.append({
            "name": f"Fi Car Audio {model}",
            "brand": "Fi Car Audio",
            "mpn": model,
            "sku": model,
            "url": str(product.get("url") or ""),
            "price": round(price, 2),
            "currency": "USD",
            "availability": "https://schema.org/InStock",
            "price_valid_until": "",
        })
    return records


def harvest_ficaraudio(sleep_s: float, timeout_s: float, limit: int | None = None) -> list[dict]:
    products_by_url = {}
    page = 1
    while True:
        url = f"{FICARAUDIO_BASE}/fi-car-audio/?page={page}"
        try:
            text = epd.fetch_text(url, timeout_s)
        except epd.FETCH_ERRORS as exc:
            epd.log(f"ficaraudio: category page={page} failed: {exc}")
            break
        page_products = fi_category_products(text)
        if not page_products:
            break
        for product in page_products:
            products_by_url[product["url"]] = product
        epd.log(f"ficaraudio: category page={page} products={len(products_by_url)}")
        if 'rel="next"' not in text:
            break
        page += 1
        time.sleep(sleep_s)
    products = list(products_by_url.values())
    if limit is not None:
        products = products[:max(0, int(limit))]
    records = []
    for index, product in enumerate(products, start=1):
        try:
            text = epd.fetch_text(product["url"], timeout_s)
        except epd.FETCH_ERRORS as exc:
            epd.log(f"ficaraudio: product failed {product['url']}: {exc}")
            continue
        records.extend(fi_records_from_product_html(text, product))
        if index % 10 == 0 or index == len(products):
            epd.log(f"ficaraudio: products={index}/{len(products)} offers={len(records)}")
        time.sleep(sleep_s)
    return records


def _expand_wavecor_models(value: str) -> list[str]:
    parts = [part.strip() for part in value.split("/") if part.strip()]
    if len(parts) <= 1:
        return parts
    first = parts[0]
    models = [first]
    for suffix in parts[1:]:
        models.append(first[:-len(suffix)] + suffix if len(suffix) < len(first) else suffix)
    return models


def wavecor_records_from_html(text: str, model_keys: set[str]) -> list[dict]:
    records = []
    for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", text, re.S | re.I):
        cells = [
            epd.clean_product_text(cell)
            for cell in re.findall(r"<td\b[^>]*>(.*?)</td>", row, re.S | re.I)
        ]
        if len(cells) < 3:
            continue
        code, description, price_text = cells[0], cells[1], cells[2]
        price_match = re.search(r"\bUSD\s*([0-9.,]+)", price_text, re.I)
        price = epd.number(price_match.group(1)) if price_match else None
        if price is None:
            continue
        for model in _expand_wavecor_models(code):
            if epd.normalize_token(model) not in model_keys:
                continue
            records.append({
                "name": f"Wavecor {model} {description}".strip(),
                "brand": "Wavecor",
                "mpn": model,
                "sku": model,
                "url": WAVECOR_PRICE_URL,
                "price": round(price, 2),
                "currency": "USD",
                "availability": "",
                "price_valid_until": "",
            })
    return records


def harvest_wavecor(sleep_s: float, timeout_s: float, limit: int | None = None) -> list[dict]:
    del sleep_s
    candidates = [
        candidate
        for candidate in epd.load_library_candidates()
        if "wavecor" in epd.brand_compacts(candidate.brand)
    ]
    model_keys = {
        epd.normalize_token(candidate.model)
        for candidate in candidates
        if candidate.model
    }
    try:
        text = epd.fetch_text(WAVECOR_PRICE_URL, timeout_s)
    except epd.FETCH_ERRORS as exc:
        epd.log(f"wavecor: price list failed: {exc}")
        return []
    records = wavecor_records_from_html(text, model_keys)
    if limit is not None:
        records = records[:max(0, int(limit))]
    epd.log(f"wavecor: official price offers={len(records)}")
    return records


def audiohifi_records_from_html(text: str, model_keys: set[str]) -> list[dict]:
    records = []
    for row in re.findall(r'<tr\s+class="productListing-[^"]+"[^>]*>(.*?)</tr>', text, re.S | re.I):
        title_match = re.search(
            r'<h3\s+class="itemTitle"><a\s+href="([^"]+)">(.*?)</a>',
            row,
            re.S | re.I,
        )
        if not title_match:
            continue
        model = epd.clean_product_text(title_match.group(2))
        if epd.normalize_token(model) not in model_keys:
            continue
        prices = re.findall(
            r'class="(?:productBasePrice|productSpecialPrice)"[^>]*>\s*&euro;\s*([0-9.,]+)',
            row,
            re.I,
        )
        price = epd.number(prices[-1]) if prices else None
        if price is None:
            continue
        description_match = re.search(r'class="listingDescription">(.*?)</div>', row, re.S | re.I)
        description = epd.clean_product_text(description_match.group(1)) if description_match else ""
        records.append({
            "name": f"Tang Band {model} {description}".strip(),
            "brand": "Tang Band",
            "mpn": model,
            "sku": model,
            "url": epd.html_entity_decode(title_match.group(1)),
            "price": round(price, 2),
            "currency": "EUR",
            "availability": "",
            "price_valid_until": "",
        })
    return records


def harvest_audiohifi(sleep_s: float, timeout_s: float, limit: int | None = None) -> list[dict]:
    candidates = [
        candidate
        for candidate in epd.load_library_candidates()
        if "tangband" in epd.brand_compacts(candidate.brand)
    ]
    model_keys = {epd.normalize_token(candidate.model) for candidate in candidates}
    records_by_model = {}
    for page in range(1, 50):
        url = AUDIOHIFI_TANGBAND_URL if page == 1 else f"{AUDIOHIFI_TANGBAND_URL}?page={page}"
        try:
            text = _fetch_text_certifi(url, timeout_s)
        except epd.FETCH_ERRORS as exc:
            epd.log(f"audiohifi: page={page} failed: {exc}")
            break
        page_records = audiohifi_records_from_html(text, model_keys)
        if not page_records:
            break
        for record in page_records:
            records_by_model[record["mpn"]] = record
        epd.log(f"audiohifi: page={page} matched_models={len(records_by_model)}")
        if "Go to Next Page" not in text:
            break
        if limit is not None and len(records_by_model) >= int(limit):
            break
        time.sleep(sleep_s)
    records = list(records_by_model.values())
    return records[:int(limit)] if limit is not None else records


def _get_json(url: str, timeout_s: float) -> dict:
    text = epd.fetch_text(url, timeout_s)
    return json.loads(text)


def _fetch_text_certifi(url: str, timeout_s: float) -> str:
    """Fetch a public page whose certificate chain macOS Python lacks."""
    import certifi

    request = Request(url, headers={"User-Agent": "LoadForge/1.0 (+price catalog)"})
    context = ssl.create_default_context(cafile=certifi.where())
    try:
        with urlopen(request, timeout=timeout_s, context=context) as response:
            return response.read(8_000_000).decode("utf-8", errors="replace")
    except epd.FETCH_ERRORS:
        # curl uses the host trust store, which can contain an intermediate
        # missing from Python/certifi. It still performs normal TLS checking.
        completed = subprocess.run(
            [
                "curl", "-sS", "-L", "--max-time", str(max(1, int(timeout_s))),
                "-A", "LoadForge/1.0 (+price catalog)", url,
            ],
            check=False,
            capture_output=True,
        )
        if completed.returncode:
            raise OSError(completed.stderr.decode("utf-8", errors="replace").strip())
        return completed.stdout[:8_000_000].decode("utf-8", errors="replace")


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


def _diyspeakerseu_is_driver_category(name: str) -> bool:
    return name.casefold() in DIYSPEAKERSEU_CATEGORY_ALLOW


def _parse_diyspeakerseu_product(product: dict) -> dict | None:
    categories = [str(c.get("name") or "") for c in product.get("categories", [])]
    if not any(_diyspeakerseu_is_driver_category(name) for name in categories):
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


def harvest_diyspeakerseu(sleep_s: float, timeout_s: float, limit_pages: int = 20) -> list[dict]:
    records = []
    page = 1
    while limit_pages is None or page <= limit_pages:
        url = f"{DIYSPEAKERSEU_BASE}/wp-json/wc/store/v1/products?per_page=100&page={page}"
        try:
            payload = _get_json(url, timeout_s)
        except epd.FETCH_ERRORS as exc:
            epd.log(f"diyspeakerseu: fetch failed page={page}: {exc}")
            break
        if not payload:
            break
        for product in payload:
            record = _parse_diyspeakerseu_product(product)
            if record:
                records.append(record)
        epd.log(f"diyspeakerseu: page={page} products={len(payload)} kept={len(records)}")
        if len(payload) < 100:
            break
        page += 1
        time.sleep(sleep_s)
    return records


def _analoghifi_category_brand(product: dict) -> tuple[bool, str]:
    """Return (is_driver_category, brand) derived from the category link path."""
    brand = ""
    is_driver = False
    for category in product.get("categories", []) or []:
        slug = str(category.get("slug") or "")
        link = str(category.get("link") or "")
        if slug in ANALOGHIFI_CATEGORY_DENY_SLUGS:
            continue
        if ANALOGHIFI_CATEGORY_ALLOW_PATH not in link:
            continue
        is_driver = True
        tail = link.split(ANALOGHIFI_CATEGORY_ALLOW_PATH, 1)[1]
        brand_slug = tail.strip("/").split("/", 1)[0] if tail else ""
        mapped = ANALOGHIFI_BRAND_BY_SLUG.get(brand_slug)
        if mapped:
            brand = mapped
    return is_driver, brand


def _parse_analoghifi_product(product: dict) -> dict | None:
    is_driver, brand = _analoghifi_category_brand(product)
    if not is_driver:
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
    sku = str(product.get("sku") or "")
    url = str(product.get("permalink") or "")
    if not url:
        return None
    currency = str(prices.get("currency_code") or "NOK")
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


def harvest_analoghifi(sleep_s: float, timeout_s: float, limit_pages: int = 50) -> list[dict]:
    records = []
    page = 1
    while limit_pages is None or page <= limit_pages:
        url = f"{ANALOGHIFI_BASE}/wp-json/wc/store/v1/products?per_page=100&page={page}"
        try:
            payload = _get_json(url, timeout_s)
        except epd.FETCH_ERRORS as exc:
            epd.log(f"analoghifi: fetch failed page={page}: {exc}")
            break
        if not payload:
            break
        for product in payload:
            record = _parse_analoghifi_product(product)
            if record:
                records.append(record)
        epd.log(f"analoghifi: page={page} products={len(payload)} kept={len(records)}")
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
    "diyspeakerseu": (harvest_diyspeakerseu, DIYSPEAKERSEU_CHECKPOINT),
    "analoghifi": (harvest_analoghifi, ANALOGHIFI_CHECKPOINT),
    "thomann": (harvest_thomann, THOMANN_CHECKPOINT),
    "ds18": (harvest_ds18, DS18_CHECKPOINT),
    "ficaraudio": (harvest_ficaraudio, FICARAUDIO_CHECKPOINT),
    "wavecor": (harvest_wavecor, WAVECOR_CHECKPOINT),
    "audiohifi": (harvest_audiohifi, AUDIOHIFI_CHECKPOINT),
}

PAGE_LIMIT_SOURCES = {
    "cinergyaudio", "willyshifi", "topservicepro", "kjfaudio", "hogtalarshoppen",
    "diyspeakerseu", "analoghifi", "ds18",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=sorted(HARVESTERS), required=True)
    parser.add_argument("--sleep", type=float, default=0.4)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--limit", type=int, default=None)
    return parser


def checkpoint_record_key(record: dict, index: int = 0) -> str:
    """Keep variants sharing a product page distinct in retailer checkpoints."""
    url = str(record.get("url") or "")
    variant = str(record.get("sku") or record.get("mpn") or "")
    if url and variant:
        return f"{url}#{variant}"
    return url or variant or str(record.get("name") or index)


def main() -> int:
    args = build_parser().parse_args()
    harvester, checkpoint_path = HARVESTERS[args.source]
    kwargs = {"sleep_s": args.sleep, "timeout_s": args.timeout}
    if args.source not in PAGE_LIMIT_SOURCES:
        kwargs["limit"] = args.limit
    records = harvester(**kwargs)
    # A transient retailer outage must not replace a useful checkpoint with an
    # empty/partial file. Merge by canonical product URL so fresh observations
    # replace old ones while previously known offers survive interrupted runs.
    existing_records = []
    if checkpoint_path.exists():
        try:
            existing_payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            existing_records = list(existing_payload.get("prices", []))
        except (OSError, json.JSONDecodeError, TypeError):
            existing_records = []
    merged = {
        checkpoint_record_key(record, index): record
        for index, record in enumerate(existing_records)
        if isinstance(record, dict)
    }
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        key = checkpoint_record_key(record, index)
        merged[key] = record
    payload = {"source": args.source, "prices": list(merged.values())}
    temp_path = checkpoint_path.with_suffix(checkpoint_path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    os.replace(temp_path, checkpoint_path)
    epd.log(
        f"{args.source}: refreshed={len(records)} retained={len(existing_records)} "
        f"checkpoint={len(merged)} {checkpoint_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
