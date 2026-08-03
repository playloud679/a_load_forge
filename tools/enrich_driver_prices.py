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
import sys
import time
from collections import defaultdict
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
    url: str = ""


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
IMPEDANCE_SUFFIX = re.compile(
    r"\s*\(?\s*\d+(?:[.,]\d+)?\s*(?:Ω|ohms?)\s*\)?\s*$",
    re.I,
)
IMPEDANCE_VALUE_RE = re.compile(
    r"(?<![\d.,])(\d+(?:[.,]\d+)?)\s*(?:Ω|ohms?)",
    re.I,
)
PAREN_IMPEDANCE_SUFFIX_RE = re.compile(r"\(\s*(2|4|6|8|12|16|32)\s*\)\s*$", re.I)


def impedance_values(text: str) -> set[float]:
    """Extract explicit nominal impedances without treating model digits as Ω."""
    values = {
        float(match.group(1).replace(",", "."))
        for match in IMPEDANCE_VALUE_RE.finditer(str(text))
    }
    parenthesized = PAREN_IMPEDANCE_SUFFIX_RE.search(str(text))
    if parenthesized:
        values.add(float(parenthesized.group(1)))
    return values


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


# 2026-07-24 QA sweep: presets that never got a clean part number (their
# `model` field is a fallback full descriptive title, e.g. "Eminence
# Delta-12B 12\" Driver 16 Ohm") were matching completely unrelated products
# of the same brand purely because a short spec fragment like "16ohm" is a
# 2-token compact that satisfies model_compacts()'s "len>=5, has a letter and
# a digit" test -- "16ohm"/"8ohm"/"100w" etc. are generic wattage/impedance
# text present on nearly every product in a catalog, not a real model
# fragment, so they must never count as a model match on their own. Confirmed
# via a 2026-07-24 price-outlier scan (Eminence Delta-12B priced from an
# unrelated Alpha 3-16, two FaitalPRO woofers priced from an unrelated 3FE25)
# -- all three shared only a brand match plus one of these generic compacts.
_GENERIC_SPEC_COMPACT_RE = re.compile(
    r"^(?:\d+(?:ohm|ohms|w|watt|watts|hz|khz|db|mm|cm|in)|(?:ohm|ohms|w|watt|watts|hz|khz|db|mm|cm|in)\d+)$"
)


def _is_code_like_token(token: str) -> bool:
    """True for tokens that look like a genuine part-number fragment (mixes
    a letter and a digit in the *same* token, e.g. "12pr310"/"3fe25") as
    opposed to plain descriptive words ("professional", "woofer") or plain
    numbers ("8", "16") that happen to sit next to each other in a title.
    """
    return any(c.isalpha() for c in token) and any(c.isdigit() for c in token)


def model_compacts(model: str) -> set[str]:
    compacts = set()
    for variant in {model, IMPEDANCE_SUFFIX.sub("", model)}:
        tokens = tokenize(variant)
        compact = "".join(tokens)
        if compact:
            compacts.add(compact)
        for start in range(len(tokens)):
            for end in range(start + 2, min(len(tokens), start + 4) + 1):
                span = tokens[start:end]
                sequence = "".join(span)
                if (
                    len(sequence) >= 5
                    and any(character.isalpha() for character in sequence)
                    and any(character.isdigit() for character in sequence)
                    and not _GENERIC_SPEC_COMPACT_RE.match(sequence)
                    # 2026-07-24 QA sweep continued: a multi-token span like
                    # "professional woofer 8" also passes the checks above
                    # (mixed alpha/digit once joined, not a bare spec unit)
                    # purely because "8" sits next to two descriptive words
                    # -- require at least one token in the span to itself be
                    # code-like (mix a letter and digit), the actual
                    # fingerprint of a real part number, not a coincidence of
                    # adjacent generic words and a spec number.
                    and any(_is_code_like_token(token) for token in span)
                ):
                    compacts.add(sequence)
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
        "recone-kit",
        "reconekit",
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
        # 2026-07-24 QA sweep: a Visaton preset was being priced from
        # PartsExpress's "Watertight Mounting Gasket for FR8WP Series"
        # listing -- a rubber gasket accessory, not the driver itself. Also
        # caught a Fostex driver preset priced from "P800E Box for P800K"
        # (an empty enclosure sold for that driver, not the driver).
        "mounting gasket",
        "box for",
        "enclosure for",
        "replacement box",
        # 2026-07-25 QA sweep (round 11): BlueAran also sells downloadable
        # cabinet-design-plan documents named "<Brand> <Model> ... Design
        # Plans for ..."/"Design Plans for <n>-way speaker with a <Model>
        # woofer"/"Design fee for ..." -- all priced 0.0 (free download), not
        # the driver itself. One had already slipped through and priced a
        # B&C 18SW115 preset at GBP 0.00. 27 such listings found in
        # BlueAran's cached catalog alone, all correctly excluded by these
        # patterns with zero false positives against any real driver name
        # checked across every cached seller catalog.
        "design plan",
        "design fee",
        "cabinet design",
        "design for",
    )
    return not any(pattern in text for pattern in accessory_patterns)


# 2026-07-24 QA sweep: BlueAran sells both a single-unit listing and a
# separate bulk "_4PK"-style listing for the same model, and the bare
# (non brand-prefixed) preset key sometimes matched the bulk listing instead
# of the single unit -- e.g. a "Fane Colossus Prime 18XS" preset priced at
# the Four Pack's total price (~3.9x the real single-unit price). A preset
# never represents a multi-unit bundle, so any product whose own text claims
# to be a multi-unit pack is rejected outright.
_PACK_QUANTITY_RE = re.compile(
    r"\b(?:"
    r"\d+\s*[- ]?pack"
    r"|pack\s+of\s+\d+"
    r"|(?:twin|four|six|eight|value)\s*[- ]?pack"
    r")\b",
    re.IGNORECASE,
)


def product_is_multi_unit_pack(product: dict) -> bool:
    text = " ".join(str(product.get(key, "")) for key in ("name", "url")).casefold()
    return bool(_PACK_QUANTITY_RE.search(text))


DRIVER_TYPE_PATTERNS = {
    "tweeter": ("tweeter",),
    "midrange": ("midrange", "mid-range"),
    "woofer": ("woofer", "midwoofer", "midbass", "mid-bass", "mid bass"),
    "subwoofer": ("subwoofer", "sub-woofer"),
    "fullrange": ("full range", "full-range", "fullrange", "full-band", "broadband"),
    "radiator": ("passive radiator",),
    "compression": ("compression driver", "compression horn"),
    "exciter": ("exciter", "bass shaker"),
    "coaxial": ("coaxial", "co-axial"),
}

# Model-number suffix convention (Dayton Audio and others use a bare "-PR"
# model suffix for passive radiators without ever spelling out "passive
# radiator" in the product/preset text) -- found 2026-07-24 via a Hogtalar-
# shoppen.se spot-check where a Dayton "DSA135-8 ... Woofer" preset was
# priced from the site's "Dayton Audio DSA135-PR" passive-radiator listing:
# driver_types_conflict() didn't fire because the product side ("DSA135-PR")
# has no *word* the literal "passive radiator" substring check recognizes.
# Anchored with a trailing word boundary (re, not a plain substring) so it
# matches "...-PR", "...-PR 8", "...-PR)" etc. but not "-PRO"/"-PRESET"/
# other longer tokens that merely start with "pr".
_RADIATOR_SUFFIX_RE = re.compile(r"-pr\b", re.IGNORECASE)


def driver_types(text: str) -> set[str]:
    """Infer which driver-type tags (woofer/tweeter/...) a text mentions.

    Same lexicon and lookup approach as tools/fix_extra_retailer_matches.py's
    point-fix guard, kept in sync so both tools agree on what counts as a
    cross-type mismatch.
    """
    lowered = text.casefold()
    tags = {tag for tag, patterns in DRIVER_TYPE_PATTERNS.items() if any(p in lowered for p in patterns)}
    if _RADIATOR_SUFFIX_RE.search(lowered):
        tags.add("radiator")
    return tags


def driver_types_conflict(candidate_text: str, product_text: str) -> bool:
    """True when the candidate preset and matched product name disagree on
    driver type (a woofer preset priced from a tweeter product listing, etc).

    Absence of any recognized type tag on either side is not treated as a
    conflict -- most preset/product names don't spell out a category at all,
    and this guard should only reject matches where both sides *do* state a
    type and those types disagree, not silently narrow every match to only
    the names carrying an explicit type word.
    """
    candidate_types = driver_types(candidate_text)
    product_types = driver_types(product_text)
    if not candidate_types or not product_types:
        return False
    # A passive radiator has no motor/voice coil and must never stand in for
    # (or be stood in for by) any active driver type.
    if "radiator" in candidate_types or "radiator" in product_types:
        return candidate_types != product_types
    return candidate_types.isdisjoint(product_types)


def match_score(candidate: PresetCandidate, product: dict) -> float:
    if not product_looks_like_driver(product):
        return 0.0
    candidate_text = f"{candidate.brand} {candidate.model} {candidate.name}"
    if product_is_multi_unit_pack(product) and not _PACK_QUANTITY_RE.search(candidate_text.casefold()):
        return 0.0
    product_text = f"{product.get('name', '')} {product.get('url', '')}"
    if driver_types_conflict(candidate_text, product_text):
        return 0.0
    candidate_impedances = impedance_values(
        f"{candidate.model} {candidate.query} {candidate.name}"
    )
    product_impedances = impedance_values(
        f"{product.get('name', '')} {product.get('mpn', '')} {product.get('sku', '')}"
    )
    if (
        candidate_impedances
        and product_impedances
        and candidate_impedances.isdisjoint(product_impedances)
    ):
        return 0.0
    query = "".join(tokenize(candidate.query))
    models = model_compacts(candidate.model)
    brands = brand_compacts(candidate.brand)
    strong_sequences, all_sequences = product_match_sequences(product)
    product_fields = [
        normalize_token(str(product.get(key, "")))
        for key in ("name", "brand", "mpn", "sku", "url")
    ]
    score = 0.0
    model_matched = any(
        model in all_sequences
        or (len(model) >= 8 and any(model in field for field in product_fields))
        for model in models
    )
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
    elif candidate.brand and not brand_matched:
        # Model codes are not globally unique (for example 8MB500 exists under
        # multiple manufacturers), so a known brand must also be evidenced.
        score = min(score, 0.79)
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


def _candidate_catalog_indexes(
    candidates: list[PresetCandidate],
) -> tuple[dict[str, list[PresetCandidate]], dict[str, list[PresetCandidate]]]:
    """Build exact-name and model-token indexes for cached-catalog rematching."""
    exact: dict[str, list[PresetCandidate]] = defaultdict(list)
    models: dict[str, list[PresetCandidate]] = defaultdict(list)
    for candidate in candidates:
        display_name = re.sub(r"^(?:WEB|PDF|LSDB):\s*", "", candidate.name, flags=re.I)
        for value in (
            display_name,
            f"{candidate.brand} {candidate.model}",
            candidate.model,
            candidate.url,
        ):
            key = normalize_token(value)
            if key and candidate not in exact[key]:
                exact[key].append(candidate)
        for key in model_compacts(candidate.model):
            if key and candidate not in models[key]:
                models[key].append(candidate)
    return exact, models


def _catalog_candidate_pool(
    product: dict,
    exact_index: dict[str, list[PresetCandidate]],
    model_index: dict[str, list[PresetCandidate]],
) -> list[PresetCandidate]:
    candidates: set[PresetCandidate] = set()
    exact_values = (
        product.get("name", ""),
        f"{product.get('brand', '')} {product.get('mpn', '')}",
        product.get("mpn", ""),
        product.get("sku", ""),
        product.get("url", ""),
    )
    for value in exact_values:
        candidates.update(exact_index.get(normalize_token(str(value)), ()))
    _strong, sequences = product_match_sequences(product)
    for sequence in sequences:
        candidates.update(model_index.get(sequence, ()))
    return sorted(
        candidates,
        key=lambda candidate: (
            candidate.name.casefold(),
            candidate.brand.casefold(),
            candidate.model.casefold(),
        ),
    )


def _prefer_rematched_price(existing: object, candidate: dict) -> bool:
    if not isinstance(existing, dict):
        return True
    old_confidence = number(existing.get("confidence")) or 0.0
    new_confidence = number(candidate.get("confidence")) or 0.0
    if new_confidence > old_confidence:
        return True
    if new_confidence < old_confidence:
        return False
    if str(existing.get("currency") or "") != str(candidate.get("currency") or ""):
        return False
    old_price = number(existing.get("price"))
    new_price = number(candidate.get("price"))
    return new_price is not None and (old_price is None or new_price < old_price)


def _candidate_has_exact_product_identity(candidate: PresetCandidate, product: dict) -> bool:
    display_name = re.sub(r"^(?:WEB|PDF|LSDB):\s*", "", candidate.name, flags=re.I)
    candidate_keys = {
        normalize_token(display_name),
        normalize_token(f"{candidate.brand} {candidate.model}"),
        normalize_token(candidate.model),
        normalize_token(candidate.url),
    }
    product_keys = {
        normalize_token(str(product.get("name", ""))),
        normalize_token(f"{product.get('brand', '')} {product.get('mpn', '')}"),
        normalize_token(str(product.get("mpn", ""))),
        normalize_token(str(product.get("sku", ""))),
        normalize_token(str(product.get("url", ""))),
    }
    candidate_keys.discard("")
    product_keys.discard("")
    if candidate_keys & product_keys:
        return True
    product_mpn = IMPEDANCE_SUFFIX.sub("", str(product.get("mpn") or ""))
    product_mpn_key = normalize_token(product_mpn)
    brand_matches = bool(
        brand_compacts(candidate.brand)
        & brand_compacts(str(product.get("brand") or product.get("name") or ""))
    )
    return bool(
        brand_matches
        and len(product_mpn_key) >= 5
        and product_mpn_key in model_compacts(candidate.model)
    )


def rematch_cached_catalog(
    candidates: list[PresetCandidate],
    payload: dict,
    min_confidence: float = 0.8,
) -> dict[str, int]:
    """Link cached retailer offers to a new preset catalog without networking."""
    exact_index, model_index = _candidate_catalog_indexes(candidates)
    prices = payload.setdefault("prices", {})
    stats = {
        "products_scanned": 0,
        "products_matched": 0,
        "candidates_priced": 0,
        "new_prices": 0,
        "replaced_prices": 0,
    }
    matched_names: set[str] = set()
    catalogs = payload.get("catalog", {})
    seller_order = ("SoundImports", "BlueAran", "Madisound", "PartsExpress")
    remaining_sellers = sorted(set(catalogs) - set(seller_order))
    for seller in (*seller_order, *remaining_sellers):
        catalog = catalogs.get(seller, {})
        if not isinstance(catalog, dict):
            continue
        for product in catalog.values():
            if not isinstance(product, dict):
                continue
            stats["products_scanned"] += 1
            pool = _catalog_candidate_pool(product, exact_index, model_index)
            candidate, score = best_candidate_match(pool, product)
            if candidate is None or score < min_confidence:
                continue
            stats["products_matched"] += 1
            selected = {candidate: score}
            for exact_candidate in pool:
                exact_score = match_score(exact_candidate, product)
                if (
                    exact_score >= min_confidence
                    and (
                        _candidate_has_exact_product_identity(exact_candidate, product)
                        # A perfect score includes brand, model and full query
                        # evidence. Propagate such an offer to duplicate rows
                        # from other runtime tiers; the impedance guard in
                        # match_score keeps 4/8/16-ohm variants separate.
                        or exact_score >= 1.0
                    )
                ):
                    selected[exact_candidate] = exact_score
            for selected_candidate, selected_score in selected.items():
                matched_names.add(selected_candidate.name)
                record = price_record(selected_candidate, product, seller, selected_score)
                existing = prices.get(selected_candidate.name)
                if _prefer_rematched_price(existing, record):
                    prices[selected_candidate.name] = record
                    if isinstance(existing, dict):
                        stats["replaced_prices"] += 1
                    else:
                        stats["new_prices"] += 1
    stats["candidates_priced"] = len(matched_names)
    return stats


def retailer_provider_for_url(url: str) -> Provider | None:
    host = str(url or "").casefold()
    for provider in PROVIDERS.values():
        if provider.base_url.casefold().removeprefix("https://www.").split("/", 1)[0] in host:
            return provider
    return None


def enrich_preset_product_urls(
    candidates: list[PresetCandidate],
    payload: dict,
    output_path: Path,
    timeout_s: float,
    sleep_s: float,
    limit: int,
    min_confidence: float,
) -> dict[str, int]:
    """Refresh missing prices from retailer URLs already attached to presets."""
    prices = payload.setdefault("prices", {})
    stats = {"scanned": 0, "matched": 0, "missed": 0}
    for candidate in candidates:
        if limit > 0 and stats["scanned"] >= limit:
            break
        if candidate.name in prices:
            continue
        provider = retailer_provider_for_url(candidate.url)
        if provider is None:
            continue
        stats["scanned"] += 1
        try:
            products, _next = provider_page_products(provider, candidate.url, timeout_s)
        except FETCH_ERRORS as exc:
            stats["missed"] += 1
            log(f"preset url miss {candidate.name}: {exc}")
            time.sleep(sleep_s)
            continue
        ranked = sorted(
            ((match_score(candidate, product), product) for product in products),
            key=lambda pair: pair[0],
            reverse=True,
        )
        if not ranked or ranked[0][0] < min_confidence:
            stats["missed"] += 1
            log(f"preset url no confident offer {candidate.name}")
        else:
            score, product = ranked[0]
            prices[candidate.name] = price_record(candidate, product, provider.seller, score)
            catalog = payload.setdefault("catalog", {}).setdefault(provider.seller, {})
            catalog[candidate.url] = catalog_record(product, provider.seller)
            stats["matched"] += 1
            log(f"preset url price {candidate.name}: {product['price']} {product['currency']}")
            write_output(output_path, payload)
        time.sleep(sleep_s)
    return stats


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
        candidates.append(PresetCandidate(
            name=name,
            brand=brand,
            model=model,
            query=query,
            url=str(item.get("url") or ""),
        ))
    return candidates


def load_library_candidates() -> list[PresetCandidate]:
    """Return every driver that the application can expose at runtime.

    Price crawling used to default to the LSDB JSON alone, which meant cached
    retailer offers could never match built-ins, manufacturer crawls,
    VituixCAD or Speaker Box Lite rows. Importing the catalog facade here keeps
    the enrichment target identical to the actual Finder library, including
    its cross-tier deduplication and canonical display names.
    """
    root_text = str(ROOT)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    from src import presets

    candidates = []
    for name in presets.driver_preset_names():
        info = presets.driver_preset_info(name)
        model = str(info.model or name.removeprefix("LSDB: ").strip())
        candidates.append(PresetCandidate(
            name=name,
            brand=str(info.brand or ""),
            model=model,
            query=model or name,
            url=str(info.url or ""),
        ))
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
    parser.add_argument(
        "--presets",
        type=Path,
        help="Optional single preset JSON; omitted targets the complete runtime library.",
    )
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
    parser.add_argument(
        "--rematch-catalog",
        action="store_true",
        help="Match cached retailer catalogs against the complete library or --presets override.",
    )
    parser.add_argument(
        "--refresh-preset-urls",
        action="store_true",
        help="Fetch missing prices from recognized retailer URLs in the library or --presets override.",
    )
    parser.add_argument("--min-price", type=float, default=0.0, help="Optional lowest price kept by --prune-prices; default keeps coherent low prices.")
    parser.add_argument("--category-url", action="append", default=[], help="Category URL to parse via JSON-LD ItemList.")
    parser.add_argument("--query", action="append", default=[], help="Explicit search query to price.")
    parser.add_argument("--url", action="append", default=[], help="Direct product URL to parse.")
    args = parser.parse_args()

    payload = load_output(args.output)
    prices = payload.setdefault("prices", {})
    misses = payload.setdefault("misses", {})
    candidates = (
        load_candidates(args.presets)
        if args.presets is not None
        else load_library_candidates()
    )
    log(f"loaded {len(candidates)} price candidates")

    if args.prune_prices:
        removed = prune_price_matches(candidates, payload, float(args.min_confidence), float(args.min_price))
        write_output(args.output, payload)
        log(f"pruned {removed} stale or implausible price records")
        return 0

    if args.rematch_catalog:
        stats = rematch_cached_catalog(candidates, payload, float(args.min_confidence))
        write_output(args.output, payload)
        log("cached catalog rematch: " + " ".join(f"{key}={value}" for key, value in stats.items()))
        return 0

    if args.refresh_preset_urls:
        stats = enrich_preset_product_urls(
            candidates,
            payload,
            args.output,
            float(args.timeout),
            float(args.sleep),
            int(args.limit),
            float(args.min_confidence),
        )
        write_output(args.output, payload)
        log("preset URL refresh: " + " ".join(f"{key}={value}" for key, value in stats.items()))
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

    if args.url and not args.query:
        return 0

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
