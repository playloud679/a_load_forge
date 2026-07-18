#!/usr/bin/env python3
"""Enrich driver presets with retailer prices.

The enrichment output is intentionally separate from T/S datasets because price
and availability are volatile.  Current provider support:

* SoundImports search, category and product pages via schema.org JSON-LD.
* Blue Aran product sitemap via schema.org JSON-LD (--provider bluearan --sitemap).
* Madisound category pages via CollectionPage JSON-LD with ?page=N pagination
  (--provider madisound --sitemap).
* Parts Express product sitemap via the public SuiteCommerce items API
  (--provider partsexpress --sitemap).
* Optional direct product URLs via --url, useful for retailer pages found by hand.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import math
import re
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PRESETS = ROOT / "data" / "loudspeaker_database_drivers.json"
DEFAULT_OUTPUT = ROOT / "data" / "driver_prices.json"
SOUNDIMPORTS_BASE = "https://www.soundimports.eu/en/"
SOUNDIMPORTS_SITEMAP = "https://www.soundimports.eu/en/sitemap.xml"
SOUNDIMPORTS_DRIVER_CATEGORY_URLS = (
    "https://www.soundimports.eu/en/audio-components/woofers/",
    "https://www.soundimports.eu/en/audio-components/tweeters/",
    "https://www.soundimports.eu/en/audio-components/exciters/",
    "https://www.soundimports.eu/en/audio-components/bass-shakers/",
    "https://www.soundimports.eu/en/accessories/speaker-repair/driver-parts/",
)
BLUEARAN_BASE = "https://www.bluearan.co.uk/"
BLUEARAN_SITEMAP = "https://www.bluearan.co.uk/sitemap_products.xml"
MADISOUND_BASE = "https://www.madisoundspeakerstore.com/"
MADISOUND_SITEMAP = "https://www.madisoundspeakerstore.com/sitemap.xml"
PARTSEXPRESS_BASE = "https://www.parts-express.com/"
PARTSEXPRESS_SITEMAP = "https://www.parts-express.com/sitemap_pages.xml"
PARTSEXPRESS_API_TEMPLATE = "api/items?language=en&country=US&currency=USD&fieldset=details&url={slug}"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
FETCH_ERRORS = (HTTPError, URLError, TimeoutError, OSError)
URL_SAFE_CHARACTERS = ":/?#[]@!$&'()*+,;=%"


@dataclass(frozen=True)
class PresetCandidate:
    name: str
    brand: str
    model: str
    query: str


@dataclass(frozen=True)
class Provider:
    key: str
    seller: str
    base_url: str
    sitemap_url: str
    kind: str = "products"  # "products" | "categories" | "api"


PROVIDERS = {
    "soundimports": Provider("soundimports", "SoundImports", SOUNDIMPORTS_BASE, SOUNDIMPORTS_SITEMAP),
    "bluearan": Provider("bluearan", "BlueAran", BLUEARAN_BASE, BLUEARAN_SITEMAP),
    "madisound": Provider("madisound", "Madisound", MADISOUND_BASE, MADISOUND_SITEMAP, kind="categories"),
    "partsexpress": Provider(
        "partsexpress", "PartsExpress", PARTSEXPRESS_BASE, PARTSEXPRESS_SITEMAP, kind="api"
    ),
}


class JsonLdParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.blocks: list[str] = []
        self._in_json_ld = False
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        if tag != "script":
            return
        attrs_dict = {key.casefold(): value or "" for key, value in attrs}
        if attrs_dict.get("type", "").casefold() == "application/ld+json":
            self._in_json_ld = True
            self._parts = []

    def handle_endtag(self, tag: str):
        if tag == "script" and self._in_json_ld:
            block = "".join(self._parts).strip()
            if block:
                self.blocks.append(block)
            self._in_json_ld = False

    def handle_data(self, data: str):
        if self._in_json_ld:
            self._parts.append(data)


def log(message: str):
    print(message, flush=True)


def ascii_url(url: str) -> str:
    """Percent-encode non-ASCII URL characters without double-encoding escapes."""
    return quote(url, safe=URL_SAFE_CHARACTERS)


def fetch_text(url: str, timeout_s: float) -> str:
    req = Request(
        ascii_url(url),
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,it;q=0.8",
            "Cache-Control": "no-cache",
        },
    )
    with urlopen(req, timeout=timeout_s) as response:
        return response.read().decode("utf-8", errors="replace")


def sitemap_urls(text: str) -> list[str]:
    urls = re.findall(r"<loc>\s*(.*?)\s*</loc>", text, re.S)
    return [html_entity_decode(url.strip()) for url in urls]


def soundimports_product_urls(text: str) -> list[str]:
    out = []
    for url in sitemap_urls(text):
        path = url.split("/en/", 1)[-1]
        if not url.endswith(".html"):
            continue
        if any(segment in path for segment in ("blog/", "service/", "brands/", "tagged/", "collection/")):
            continue
        out.append(url)
    return out


def bluearan_product_urls(text: str) -> list[str]:
    return [url for url in sitemap_urls(text) if "index.php?id=" in url]


MADISOUND_EXCLUDED_PATHS = (
    "index.php",
    "about-us",
    "contact-us",
    "ordering",
    "shipping",
    "privacy",
    "returns",
    "warranty",
    "sitemap",
)


def madisound_category_urls(text: str) -> list[str]:
    out = []
    for url in sitemap_urls(text):
        path = url.split("//", 1)[-1].split("/", 1)[-1]
        if not path or "?" in path:
            continue
        if any(segment in path for segment in MADISOUND_EXCLUDED_PATHS):
            continue
        out.append(url)
    return out


PARTSEXPRESS_PRODUCT_URL = re.compile(r"-\d{3}-\d{2,5}/?$")


def partsexpress_product_urls(text: str) -> list[str]:
    return [url for url in sitemap_urls(text) if PARTSEXPRESS_PRODUCT_URL.search(url)]


def provider_product_urls(provider: Provider, text: str) -> list[str]:
    if provider.key == "bluearan":
        urls = bluearan_product_urls(text)
    elif provider.key == "madisound":
        urls = madisound_category_urls(text)
    elif provider.key == "partsexpress":
        urls = partsexpress_product_urls(text)
    else:
        urls = soundimports_product_urls(text)
    return list(dict.fromkeys(urls))


def as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def flatten_jsonld(value) -> list[dict]:
    out: list[dict] = []
    for item in as_list(value):
        if not isinstance(item, dict):
            continue
        if "@graph" in item:
            out.extend(flatten_jsonld(item.get("@graph")))
        else:
            out.append(item)
    return out


def parse_jsonld_blocks(text: str) -> list[dict]:
    parser = JsonLdParser()
    parser.feed(text)
    objects: list[dict] = []
    for block in parser.blocks:
        try:
            objects.extend(flatten_jsonld(json.loads(block)))
        except json.JSONDecodeError:
            continue
    return objects


def type_names(item: dict) -> set[str]:
    return {str(value).casefold() for value in as_list(item.get("@type"))}


def number(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip().replace(",", ".")
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def offer_from_product(product: dict) -> dict | None:
    offers = as_list(product.get("offers"))
    for offer in offers:
        if not isinstance(offer, dict):
            continue
        price = number(offer.get("price") or offer.get("lowPrice"))
        currency = str(offer.get("priceCurrency") or "")
        if price is not None and currency:
            return {
                "price": round(price, 2),
                "currency": currency,
                "availability": str(offer.get("availability") or ""),
                "url": str(offer.get("url") or product.get("url") or ""),
                "price_valid_until": str(offer.get("priceValidUntil") or ""),
            }
    return None


def clean_product_text(value) -> str:
    text = re.sub(r"<[^>]*>", " ", html.unescape(str(value or "")))
    return re.sub(r"\s+", " ", text).strip()


def product_record_from_jsonld(product: dict, base_url: str) -> dict | None:
    offer = offer_from_product(product)
    if not offer:
        return None
    raw_url = offer["url"] or str(product.get("url") or "")
    join_base = SOUNDIMPORTS_BASE if base_url.startswith(SOUNDIMPORTS_BASE) and "/" not in raw_url else base_url
    product_url = urljoin(join_base, raw_url)
    return {
        "name": clean_product_text(product.get("name")),
        "brand": clean_product_text(
            product.get("brand", {}).get("name")
            if isinstance(product.get("brand"), dict)
            else product.get("brand")
        ),
        "mpn": str(product.get("mpn") or product.get("sku") or ""),
        "sku": str(product.get("sku") or ""),
        "url": product_url,
        "price": offer["price"],
        "currency": offer["currency"],
        "availability": offer["availability"],
        "price_valid_until": offer["price_valid_until"],
    }


def product_records_from_jsonld_item(item: dict, base_url: str) -> list[dict]:
    if "product" in type_names(item):
        product = product_record_from_jsonld(item, base_url)
        return [product] if product else []
    products = []
    for element in as_list(item.get("itemListElement")):
        if not isinstance(element, dict):
            continue
        nested = element.get("item")
        if isinstance(nested, dict):
            products.extend(product_records_from_jsonld_item(nested, base_url))
    # Madisound-style CollectionPage blocks list their products under "about".
    for nested in as_list(item.get("about")):
        if isinstance(nested, dict):
            products.extend(product_records_from_jsonld_item(nested, base_url))
    return products


def product_records_from_html(text: str, base_url: str) -> list[dict]:
    products = []
    for item in parse_jsonld_blocks(text):
        products.extend(product_records_from_jsonld_item(item, base_url))
    if not products:
        fallback = product_record_from_text(text, base_url)
        if fallback:
            products.append(fallback)
    return products


def regex_value(pattern: str, text: str) -> str:
    match = re.search(pattern, text, re.S)
    return html_entity_decode(match.group(1).strip()) if match else ""


def html_entity_decode(value: str) -> str:
    return (
        value
        .replace("&quot;", '"')
        .replace("&amp;", "&")
        .replace("&#039;", "'")
    )


def product_record_from_text(text: str, base_url: str) -> dict | None:
    product_index = text.find('"@type": "Product"')
    if product_index < 0:
        product_index = text.find("'@type': 'Product'")
    if product_index < 0:
        return None
    text = text[product_index:]
    price = number(regex_value(r'"price"\s*:\s*"([^"]+)"', text))
    currency = regex_value(r'"priceCurrency"\s*:\s*"([^"]+)"', text)
    if price is None or not currency:
        return None
    url = regex_value(r'"url"\s*:\s*"([^"]+)"', text)
    return {
        "name": regex_value(r'"name"\s*:\s*"([^"]+)"', text),
        "brand": regex_value(r'"brand"\s*:\s*\{[^}]*"name"\s*:\s*"([^"]+)"', text),
        "mpn": regex_value(r'"mpn"\s*:\s*"([^"]+)"', text),
        "sku": regex_value(r'"sku"\s*:\s*"([^"]+)"', text),
        "url": urljoin(base_url, url),
        "price": round(price, 2),
        "currency": currency,
        "availability": regex_value(r'"availability"\s*:\s*"([^"]+)"', text),
        "price_valid_until": regex_value(r'"priceValidUntil"\s*:\s*"([^"]+)"', text),
    }


def normalize_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def tokenize(value: str) -> list[str]:
    return [
        token
        for token in re.split(r"[^a-z0-9]+", html.unescape(str(value)).casefold())
        if token
    ]


def compact_token_sequences(tokens: list[str], max_len: int = 4) -> set[str]:
    compact: set[str] = set(tokens)
    for start in range(len(tokens)):
        for end in range(start + 2, min(len(tokens), start + max_len) + 1):
            compact.add("".join(tokens[start:end]))
    return compact


def product_match_sequences(product: dict) -> tuple[set[str], set[str]]:
    strong_tokens: list[str] = []
    all_tokens: list[str] = []
    for key in ("name", "brand", "mpn", "sku"):
        tokens = tokenize(str(product.get(key, "")))
        strong_tokens.extend(tokens)
        all_tokens.extend(tokens)
    all_tokens.extend(tokenize(str(product.get("url", ""))))
    return compact_token_sequences(strong_tokens), compact_token_sequences(all_tokens)


BRAND_GENERIC_TOKENS = {"speaker", "speakers", "loudspeakers", "professional", "audio"}
BRAND_ALIASES = {
    "eighteensound": ("18sound",),
    "lavoce": ("lavoceitaliana",),
}
IMPEDANCE_SUFFIX = re.compile(r"\s*\d+(?:[.,]\d+)?\s*(?:Ω|ohms?)\s*$", re.I)


def brand_compacts(brand: str) -> set[str]:
    tokens = tokenize(brand)
    if not tokens:
        return set()
    compacts = {"".join(tokens)}
    trimmed = "".join(token for token in tokens if token not in BRAND_GENERIC_TOKENS)
    if len(trimmed) >= 2:
        compacts.add(trimmed)
    for compact in tuple(compacts):
        compacts.update(BRAND_ALIASES.get(compact, ()))
    return compacts


def model_compacts(model: str) -> set[str]:
    compacts = set()
    for variant in {model, IMPEDANCE_SUFFIX.sub("", model)}:
        compact = "".join(tokenize(variant))
        if compact:
            compacts.add(compact)
    return compacts


def candidate_model_is_weak(model: str) -> bool:
    compacts = model_compacts(model)
    if not compacts:
        return False
    compact = max(compacts, key=len)
    return compact.isdigit() or len(compact) <= 5


def product_looks_like_driver(product: dict) -> bool:
    text = " ".join(str(product.get(key, "")) for key in ("name", "url")).casefold()
    accessory_patterns = (
        "surround for",
        "recone kit",
        "repair kit",
        "diaphragm for",
        "voice coil",
        "dust cap",
        "distance holder",
        "printed circuit board",
        "iron core coil",
        "air core coil",
        "capacitor",
        "fuse",
        " kit",
        "-kit",
        "crossover",
        "grill",
    )
    return not any(pattern in text for pattern in accessory_patterns)


def match_score(candidate: PresetCandidate, product: dict) -> float:
    if not product_looks_like_driver(product):
        return 0.0
    query = "".join(tokenize(candidate.query))
    models = model_compacts(candidate.model)
    brands = brand_compacts(candidate.brand)
    strong_sequences, all_sequences = product_match_sequences(product)
    score = 0.0
    model_matched = any(model in all_sequences for model in models)
    brand_matched = any(brand in all_sequences for brand in brands)
    query_matched = bool(query and query in strong_sequences)
    if model_matched:
        score += 0.65
    if brand_matched:
        score += 0.25
    if query_matched:
        score += 0.15
    if candidate.brand and not brand_matched and candidate_model_is_weak(candidate.model):
        score = min(score, 0.59)
    return min(score, 1.0)


def soundimports_search_url(query: str) -> str:
    return urljoin(SOUNDIMPORTS_BASE, f"search/{quote(query.strip(), safe='')}/")


def price_record(candidate: PresetCandidate, product: dict, source: str, score: float) -> dict:
    return {
        "price": product["price"],
        "currency": product["currency"],
        "seller": source,
        "url": product["url"],
        "availability": product.get("availability", ""),
        "price_valid_until": product.get("price_valid_until", ""),
        "matched_name": product.get("name", ""),
        "matched_brand": product.get("brand", ""),
        "matched_mpn": product.get("mpn", ""),
        "matched_by": "jsonld",
        "confidence": round(score, 3),
        "fetched_at": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
    }


def catalog_record(product: dict, source: str) -> dict:
    return {
        "price": product["price"],
        "currency": product["currency"],
        "seller": source,
        "url": product["url"],
        "availability": product.get("availability", ""),
        "price_valid_until": product.get("price_valid_until", ""),
        "name": product.get("name", ""),
        "brand": product.get("brand", ""),
        "mpn": product.get("mpn", ""),
        "sku": product.get("sku", ""),
        "fetched_at": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
    }


def best_candidate_match(candidates: list[PresetCandidate], product: dict) -> tuple[PresetCandidate | None, float]:
    best_candidate = None
    best_score = 0.0
    for candidate in candidates:
        score = match_score(candidate, product)
        if score > best_score:
            best_candidate = candidate
            best_score = score
    return best_candidate, best_score


def ingest_product(
    product: dict,
    candidates: list[PresetCandidate],
    payload: dict,
    source: str,
    min_confidence: float,
) -> bool:
    catalog = payload.setdefault("catalog", {}).setdefault(source, {})
    prices = payload.setdefault("prices", {})
    url = product.get("url") or product.get("mpn") or product.get("name")
    if not url:
        return False
    catalog[url] = catalog_record(product, source)
    candidate, score = best_candidate_match(candidates, product)
    if candidate is None or score < min_confidence:
        return False
    record = price_record(candidate, product, source, score)
    existing = prices.get(candidate.name)
    same_currency = isinstance(existing, dict) and str(existing.get("currency", "")) == record["currency"]
    if not isinstance(existing, dict) or (
        same_currency and float(record["price"]) <= float(existing.get("price", float("inf")))
    ):
        prices[candidate.name] = record
    if candidate.model and candidate.model not in prices:
        prices[candidate.model] = record
    return True


def prune_price_matches(
    candidates: list[PresetCandidate],
    payload: dict,
    min_confidence: float,
    min_price: float,
) -> int:
    candidates_by_name = {candidate.name: candidate for candidate in candidates}
    candidates_by_model = {
        candidate.model: candidate
        for candidate in candidates
        if candidate.model
    }
    prices = payload.setdefault("prices", {})
    removed = 0
    for key, record in list(prices.items()):
        if not isinstance(record, dict):
            continue
        candidate = candidates_by_name.get(key) or candidates_by_model.get(key)
        if candidate is None:
            continue
        price = number(record.get("price"))
        product = {
            "name": record.get("matched_name", ""),
            "brand": record.get("matched_brand", ""),
            "mpn": record.get("matched_mpn", ""),
            "sku": record.get("matched_mpn", ""),
            "url": record.get("url", ""),
        }
        score = match_score(candidate, product)
        if price is None or price < min_price or score < min_confidence:
            prices.pop(key, None)
            removed += 1
    return removed


def find_soundimports_price(candidate: PresetCandidate, timeout_s: float) -> dict | None:
    search_text = fetch_text(soundimports_search_url(candidate.query), timeout_s)
    products = product_records_from_html(search_text, SOUNDIMPORTS_BASE)
    if not products:
        return None
    ranked = sorted(
        ((match_score(candidate, product), product) for product in products),
        key=lambda item: item[0],
        reverse=True,
    )
    score, product = ranked[0]
    if score < 0.6:
        return None
    if product["url"]:
        try:
            product_text = fetch_text(product["url"], timeout_s)
            product_products = product_records_from_html(product_text, product["url"])
            if product_products:
                product = product_products[0]
                score = max(score, match_score(candidate, product))
        except FETCH_ERRORS:
            pass
    return price_record(candidate, product, "SoundImports", score)


def find_direct_url_price(url: str, timeout_s: float) -> dict | None:
    text = fetch_text(url, timeout_s)
    products = product_records_from_html(text, url)
    if not products:
        return None
    product = products[0]
    candidate = PresetCandidate(
        name=product.get("name", ""),
        brand=product.get("brand", ""),
        model=product.get("mpn", "") or product.get("sku", "") or product.get("name", ""),
        query=product.get("mpn", "") or product.get("sku", "") or product.get("name", ""),
    )
    seller = re.sub(r"^www\.", "", re.sub(r"^https?://", "", url).split("/", 1)[0])
    return price_record(candidate, product, seller, 1.0)


def load_candidates(path: Path) -> list[PresetCandidate]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    candidates = []
    for item in payload.get("presets", []):
        name = str(item.get("name") or "")
        brand = str(item.get("brand") or "")
        model = str(item.get("model") or name.removeprefix("LSDB: ").strip())
        query = model or name
        candidates.append(PresetCandidate(name=name, brand=brand, model=model, query=query))
    return candidates


def load_output(path: Path) -> dict:
    if not path.exists():
        return {
            "schema": 1,
            "updated_at": "",
            "prices": {},
            "misses": {},
            "catalog": {},
        }
    return json.loads(path.read_text(encoding="utf-8"))


def write_output(path: Path, payload: dict):
    payload["updated_at"] = dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def rel_next_url(text: str, base_url: str) -> str:
    match = re.search(r'<link\s+[^>]*rel=["\']next["\'][^>]*href=["\']([^"\']+)["\']', text, re.I)
    if not match:
        match = re.search(r'<a\s+[^>]*rel=["\']next["\'][^>]*href=["\']([^"\']+)["\']', text, re.I)
    return urljoin(base_url, html_entity_decode(match.group(1))) if match else ""


def madisound_next_url(text: str, page_url: str) -> str:
    """Synthesize the next ?page=N URL for Madisound category pages.

    The page's own pagination links carry sort_by parameters that Madisound's
    robots.txt disallows, so a clean ``path?page=N`` URL is built instead.
    """
    path = page_url.split("?", 1)[0]
    query = page_url.split("?", 1)[1] if "?" in page_url else ""
    match = re.search(r"(?:^|&)page=(\d+)", query)
    current = int(match.group(1)) if match else 1
    linked_pages = set()
    for href in re.findall(r'href=["\']([^"\']+)["\']', text):
        full = urljoin(page_url, html_entity_decode(href))
        if full.split("?", 1)[0] != path:
            continue
        page_match = re.search(r"[?&]page=(\d+)", full)
        if page_match:
            linked_pages.add(int(page_match.group(1)))
    if any(page > current for page in linked_pages):
        return f"{path}?page={current + 1}"
    return ""


def provider_next_url(provider: Provider, text: str, page_url: str) -> str:
    if provider.key == "madisound":
        return madisound_next_url(text, page_url)
    return rel_next_url(text, page_url)


def partsexpress_records_from_api(payload: dict, page_url: str) -> list[dict]:
    products = []
    for item in payload.get("items", []):
        raw_price = item.get("onlinecustomerprice")
        if raw_price is None:
            raw_price = item.get("pricelevel1")
        price = number(raw_price)
        if price is None:
            continue
        products.append({
            "name": str(item.get("displayname") or ""),
            "brand": str(item.get("manufacturer") or item.get("custitem_pe_brand") or ""),
            "mpn": str(item.get("itemid") or ""),
            "sku": str(item.get("itemid") or ""),
            "url": page_url,
            "price": round(price, 2),
            "currency": "USD",
            "availability": (
                "https://schema.org/InStock" if item.get("isinstock") else "https://schema.org/OutOfStock"
            ),
            "price_valid_until": "",
        })
    return products


def partsexpress_products(url: str, timeout_s: float) -> list[dict]:
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    api_url = urljoin(PARTSEXPRESS_BASE, PARTSEXPRESS_API_TEMPLATE.format(slug=quote(slug, safe="")))
    try:
        payload = json.loads(fetch_text(api_url, timeout_s))
    except json.JSONDecodeError:
        return []
    return partsexpress_records_from_api(payload, url)


def provider_page_products(provider: Provider, url: str, timeout_s: float) -> tuple[list[dict], str]:
    """Fetch one catalog page and return its products plus any next-page URL."""
    if provider.kind == "api":
        return partsexpress_products(url, timeout_s), ""
    text = fetch_text(url, timeout_s)
    return product_records_from_html(text, url), provider_next_url(provider, text, url)


def enrich_from_provider_categories(
    provider: Provider,
    candidates: list[PresetCandidate],
    payload: dict,
    output_path: Path,
    category_urls: list[str],
    timeout_s: float,
    sleep_s: float,
    limit: int,
    min_confidence: float,
    max_runtime_s: float,
    retry_catalog: bool,
) -> None:
    pages = payload.setdefault("category_pages", {}).setdefault(provider.seller, {})
    started = time.monotonic()
    scanned = 0
    matched = 0
    queue = list(category_urls)
    queued = set(queue)
    while queue:
        if limit > 0 and scanned >= limit:
            break
        if max_runtime_s > 0 and time.monotonic() - started >= max_runtime_s:
            log(f"runtime budget reached after {max_runtime_s:.0f}s")
            break
        url = queue.pop(0)
        page = pages.get(url)
        if isinstance(page, dict) and not retry_catalog:
            next_url = str(page.get("next_url") or "")
            if next_url and next_url not in queued:
                queue.append(next_url)
                queued.add(next_url)
            continue
        scanned += 1
        try:
            text = fetch_text(url, timeout_s)
            products = product_records_from_html(text, url)
            next_url = provider_next_url(provider, text, url)
        except FETCH_ERRORS as exc:
            pages[url] = {
                "error": str(exc),
                "fetched_at": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
            }
            log(f"category miss {url}: {exc}")
            write_output(output_path, payload)
            time.sleep(sleep_s)
            continue
        for product in products:
            if ingest_product(product, candidates, payload, provider.seller, min_confidence):
                matched += 1
        pages[url] = {
            "products": len(products),
            "next_url": next_url,
            "fetched_at": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
        }
        if next_url and next_url not in queued:
            queue.append(next_url)
            queued.add(next_url)
        log(f"category page products={len(products)} matched={matched} {url}")
        write_output(output_path, payload)
        time.sleep(sleep_s)
    log(
        f"{provider.key} categories done: "
        f"scanned={scanned} pages={len(pages)} catalog={len(payload.get('catalog', {}).get(provider.seller, {}))} "
        f"preset_prices={len(payload.get('prices', {}))}"
    )


def enrich_from_provider_sitemap(
    provider: Provider,
    candidates: list[PresetCandidate],
    payload: dict,
    output_path: Path,
    timeout_s: float,
    sleep_s: float,
    limit: int,
    offset: int,
    min_confidence: float,
    max_runtime_s: float,
    retry_catalog: bool,
) -> None:
    try:
        sitemap_text = fetch_text(provider.sitemap_url, timeout_s)
    except FETCH_ERRORS as exc:
        log(f"catalog sitemap miss: {exc}")
        return
    urls = provider_product_urls(provider, sitemap_text)
    catalog = payload.setdefault("catalog", {}).setdefault(provider.seller, {})
    catalog_misses = payload.setdefault("catalog_misses", {}).setdefault(provider.seller, {})
    started = time.monotonic()
    scanned = 0
    matched = 0
    for index, url in enumerate(urls[int(offset):], start=int(offset)):
        if limit > 0 and scanned >= limit:
            break
        if max_runtime_s > 0 and time.monotonic() - started >= max_runtime_s:
            log(f"runtime budget reached after {max_runtime_s:.0f}s")
            break
        if not retry_catalog and (url in catalog or url in catalog_misses):
            continue
        scanned += 1
        try:
            products, _next = provider_page_products(provider, url, timeout_s)
        except FETCH_ERRORS as exc:
            catalog_misses[url] = {
                "error": str(exc),
                "fetched_at": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
            }
            log(f"catalog miss {index}/{len(urls)} {url}: {exc}")
            write_output(output_path, payload)
            time.sleep(sleep_s)
            continue
        if products:
            for product in products:
                if ingest_product(product, candidates, payload, provider.seller, min_confidence):
                    matched += 1
            log(f"catalog {index + 1}/{len(urls)} products={len(products)} matched={matched} {url}")
        else:
            catalog_misses[url] = {
                "error": "no product offer found",
                "fetched_at": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
            }
            log(f"catalog no offer {index + 1}/{len(urls)} {url}")
        write_output(output_path, payload)
        time.sleep(sleep_s)
    log(
        f"{provider.key} sitemap done: "
        f"scanned={scanned} catalog={len(catalog)} preset_prices={len(payload.get('prices', {}))}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--presets", default=DEFAULT_PRESETS, type=Path)
    parser.add_argument("--output", default=DEFAULT_OUTPUT, type=Path)
    parser.add_argument("--provider", choices=sorted(PROVIDERS), default="soundimports")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--sleep", type=float, default=1.5)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--max-runtime", type=float, default=0.0)
    parser.add_argument("--min-confidence", type=float, default=0.8)
    parser.add_argument("--retry-misses", action="store_true")
    parser.add_argument("--retry-catalog", action="store_true")
    parser.add_argument("--sitemap", action="store_true", help="Crawl the selected provider's product sitemap.")
    parser.add_argument("--soundimports-sitemap", action="store_true", help="Deprecated alias of --sitemap.")
    parser.add_argument("--soundimports-driver-categories", action="store_true")
    parser.add_argument("--prune-prices", action="store_true", help="Remove stale price records that no longer match presets confidently.")
    parser.add_argument("--min-price", type=float, default=0.0, help="Optional lowest price kept by --prune-prices; default keeps coherent low prices.")
    parser.add_argument("--category-url", action="append", default=[], help="Category URL to parse via JSON-LD ItemList.")
    parser.add_argument("--query", action="append", default=[], help="Explicit search query to price.")
    parser.add_argument("--url", action="append", default=[], help="Direct product URL to parse.")
    args = parser.parse_args()

    payload = load_output(args.output)
    prices = payload.setdefault("prices", {})
    misses = payload.setdefault("misses", {})
    candidates = load_candidates(args.presets)

    if args.prune_prices:
        removed = prune_price_matches(candidates, payload, float(args.min_confidence), float(args.min_price))
        write_output(args.output, payload)
        log(f"pruned {removed} stale or implausible price records")
        return 0

    if args.sitemap or args.soundimports_sitemap:
        provider = PROVIDERS[args.provider]
        if provider.kind == "categories":
            try:
                sitemap_text = fetch_text(provider.sitemap_url, args.timeout)
            except FETCH_ERRORS as exc:
                log(f"catalog sitemap miss: {exc}")
                return 1
            enrich_from_provider_categories(
                provider,
                candidates,
                payload,
                args.output,
                provider_product_urls(provider, sitemap_text),
                args.timeout,
                args.sleep,
                int(args.limit),
                float(args.min_confidence),
                float(args.max_runtime),
                bool(args.retry_catalog),
            )
        else:
            enrich_from_provider_sitemap(
                provider,
                candidates,
                payload,
                args.output,
                args.timeout,
                args.sleep,
                int(args.limit),
                int(args.offset),
                float(args.min_confidence),
                float(args.max_runtime),
                bool(args.retry_catalog),
            )
        write_output(args.output, payload)
        return 0

    if args.soundimports_driver_categories or args.category_url:
        category_urls = list(args.category_url) or list(SOUNDIMPORTS_DRIVER_CATEGORY_URLS)
        enrich_from_provider_categories(
            PROVIDERS["soundimports"],
            candidates,
            payload,
            args.output,
            category_urls,
            args.timeout,
            args.sleep,
            int(args.limit),
            float(args.min_confidence),
            float(args.max_runtime),
            bool(args.retry_catalog),
        )
        write_output(args.output, payload)
        return 0

    for url in args.url:
        try:
            record = find_direct_url_price(url, args.timeout)
        except FETCH_ERRORS as exc:
            log(f"direct url failed: {url}: {exc}")
            continue
        if record:
            key = record.get("matched_mpn") or record.get("matched_name") or url
            prices[key] = record
            candidate, score = best_candidate_match(candidates, {
                "name": record.get("matched_name", ""),
                "brand": record.get("matched_brand", ""),
                "mpn": record.get("matched_mpn", ""),
                "sku": record.get("matched_mpn", ""),
                "url": record.get("url", ""),
                "price": record.get("price"),
                "currency": record.get("currency"),
            })
            if candidate is not None and score >= float(args.min_confidence):
                prices[candidate.name] = {**record, "confidence": round(score, 3)}
            log(f"direct {key}: {record['price']} {record['currency']} {record['seller']}")
            write_output(args.output, payload)

    if args.provider != "soundimports":
        if args.url:
            return 0
        log(f"provider {args.provider} supports only --sitemap crawls; use --sitemap")
        return 2

    explicit = [
        PresetCandidate(name=query, brand="", model=query, query=query)
        for query in args.query
    ]
    candidates = explicit or candidates
    scanned = 0
    for candidate in candidates[int(args.offset):]:
        if scanned >= int(args.limit):
            break
        scanned += 1
        if candidate.name in prices:
            continue
        if not args.retry_misses and candidate.name in misses:
            continue
        try:
            record = find_soundimports_price(candidate, args.timeout)
        except FETCH_ERRORS as exc:
            misses[candidate.name] = {
                "provider": "SoundImports",
                "query": candidate.query,
                "error": str(exc),
                "fetched_at": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
            }
            log(f"miss {candidate.name}: {exc}")
            write_output(args.output, payload)
            time.sleep(args.sleep)
            continue
        if record:
            prices[candidate.name] = record
            log(f"price {candidate.name}: {record['price']} {record['currency']} {record['seller']}")
        else:
            misses[candidate.name] = {
                "provider": "SoundImports",
                "query": candidate.query,
                "error": "no confident product match",
                "fetched_at": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
            }
            log(f"miss {candidate.name}: no confident product match")
        write_output(args.output, payload)
        time.sleep(args.sleep)

    log(f"done: {len(prices)} prices, {len(misses)} misses")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
