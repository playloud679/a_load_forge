"""
Retailer price records: safe preset/product matching and value scoring for
the optional ``data/driver_prices.json`` dataset.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from urllib.request import Request, urlopen
from xml.etree import ElementTree

import numpy as np

DRIVER_PRICES_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "driver_prices.json"
)
ECB_DAILY_RATES_URL = (
    "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
)


def _preset_match_tokens(value: str) -> list[str]:
    return [token for token in re.split(r"[^a-z0-9]+", str(value).casefold()) if token]


def _compact_token_sequences(tokens: list[str], max_len: int = 4) -> set[str]:
    compact = set(tokens)
    for start in range(len(tokens)):
        for end in range(start + 2, min(len(tokens), start + max_len) + 1):
            compact.add("".join(tokens[start:end]))
    return compact


_BRAND_GENERIC_TOKENS = {"speaker", "speakers", "loudspeakers", "professional", "audio"}
_BRAND_ALIASES = {"eighteensound": ("18sound",), "lavoce": ("lavoceitaliana",)}
_GENERIC_SPEC_COMPACT_RE = re.compile(
    r"^(?:\d+(?:ohm|ohms|w|watt|watts|hz|khz|db|mm|cm|in)|(?:ohm|ohms|w|watt|watts|hz|khz|db|mm|cm|in)\d+)$"
)
_IMPEDANCE_SUFFIX_RE = re.compile(r"\s*\(?\s*\d+(?:[.,]\d+)?\s*(?:Ω|ohms?)\s*\)?\s*$", re.I)
_IMPEDANCE_VALUE_RE = re.compile(
    r"(?<![\d.,])(\d+(?:[.,]\d+)?)\s*(?:Ω|ohms?)",
    re.I,
)
_PAREN_IMPEDANCE_SUFFIX_RE = re.compile(r"\(\s*(2|4|6|8|12|16|32)\s*\)\s*$", re.I)


def _brand_compacts(brand: str) -> set[str]:
    tokens = _preset_match_tokens(brand)
    if not tokens:
        return set()
    compacts = {"".join(tokens)}
    trimmed = "".join(token for token in tokens if token not in _BRAND_GENERIC_TOKENS)
    if len(trimmed) >= 2:
        compacts.add(trimmed)
    for compact in tuple(compacts):
        compacts.update(_BRAND_ALIASES.get(compact, ()))
    return compacts


def _is_code_like_token(token: str) -> bool:
    return any(character.isalpha() for character in token) and any(
        character.isdigit() for character in token
    )


def _model_compacts(model: str) -> set[str]:
    compacts = set()
    for variant in {model, _IMPEDANCE_SUFFIX_RE.sub("", model)}:
        tokens = _preset_match_tokens(variant)
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
                    and any(_is_code_like_token(token) for token in span)
                ):
                    compacts.add(sequence)
    return compacts


def _impedance_values(text: str) -> set[float]:
    values = {
        float(match.group(1).replace(",", "."))
        for match in _IMPEDANCE_VALUE_RE.finditer(str(text))
    }
    parenthesized = _PAREN_IMPEDANCE_SUFFIX_RE.search(str(text))
    if parenthesized:
        values.add(float(parenthesized.group(1)))
    return values


def _model_needs_brand(model: str) -> bool:
    compact = "".join(_preset_match_tokens(model))
    return bool(compact) and (compact.isdigit() or len(compact) <= 5)


def _record_looks_like_driver(record: dict) -> bool:
    text = " ".join(str(record.get(key, "")) for key in ("matched_name", "url")).casefold()
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
    )
    return not any(pattern in text for pattern in accessory_patterns)


def _price_record_matches_preset(record: dict, name: str, brand: str, model: str) -> bool:
    if not _record_looks_like_driver(record):
        return False
    if not record.get("matched_name") and not record.get("matched_brand") and not record.get("matched_mpn"):
        return True
    candidate_model = model or name.removeprefix("LSDB: ")
    candidate_impedances = _impedance_values(f"{candidate_model} {name}")
    product_impedances = _impedance_values(
        f"{record.get('matched_name', '')} {record.get('matched_mpn', '')}"
    )
    if (
        candidate_impedances
        and product_impedances
        and candidate_impedances.isdisjoint(product_impedances)
    ):
        return False
    model_keys = _model_compacts(candidate_model)
    brand_keys = _brand_compacts(brand)
    product_tokens: list[str] = []
    for key in ("matched_name", "matched_brand", "matched_mpn", "url"):
        product_tokens.extend(_preset_match_tokens(str(record.get(key, ""))))
    product_sequences = _compact_token_sequences(product_tokens)
    product_fields = [
        "".join(_preset_match_tokens(str(record.get(key, ""))))
        for key in ("matched_name", "matched_brand", "matched_mpn", "url")
    ]
    model_ok = any(
        model_key in product_sequences
        or (len(model_key) >= 8 and any(model_key in field for field in product_fields))
        for model_key in model_keys
    )
    brand_ok = bool(not brand_keys or brand_keys & product_sequences)
    if brand_keys and not brand_ok:
        return False
    return model_ok


def _price_from_record(record: dict | None, name: str = "", brand: str = "", model: str = "") -> tuple[float | None, str, str]:
    if not isinstance(record, dict):
        return None, "", ""
    try:
        price = float(record["price"])
    except (KeyError, TypeError, ValueError):
        return None, "", ""
    if not np.isfinite(price) or price < 0:
        return None, "", ""
    if name and not _price_record_matches_preset(record, name, brand, model):
        return None, "", ""
    return price, str(record.get("currency") or ""), str(record.get("url") or "")


def _valid_price(value) -> float | None:
    if value is None:
        return None
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    return price if np.isfinite(price) and price >= 0 else None


@lru_cache(maxsize=1)
def _load_driver_price_records() -> dict[str, dict]:
    """Load optional volatile retailer prices generated into data/."""
    if not DRIVER_PRICES_PATH.exists():
        return {}
    try:
        payload = json.loads(DRIVER_PRICES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    prices = payload.get("prices", {})
    return prices if isinstance(prices, dict) else {}


def _preset_price(name: str, model: str = "", brand: str = "") -> tuple[float | None, str, str]:
    prices = _load_driver_price_records()
    for key in (name, model):
        price, currency, url = _price_from_record(prices.get(key), name, brand, model)
        if price is not None:
            return price, currency, url
    return None, "", ""


def parse_ecb_reference_rates(payload: bytes | str) -> tuple[dict[str, float], str]:
    """Parse the ECB daily XML feed into EUR-based currency rates.

    Returned values are currency units per EUR and always include ``EUR: 1``.
    The date is the reference date published in the feed.
    """
    root = ElementTree.fromstring(payload)
    dated_cube = next(
        (element for element in root.iter() if element.attrib.get("time")),
        None,
    )
    if dated_cube is None:
        raise ValueError("ECB reference-rate date is missing")
    rates = {"EUR": 1.0}
    for element in dated_cube:
        currency = str(element.attrib.get("currency", "")).upper()
        try:
            rate = float(element.attrib["rate"])
        except (KeyError, TypeError, ValueError):
            continue
        if currency and np.isfinite(rate) and rate > 0.0:
            rates[currency] = rate
    if len(rates) == 1:
        raise ValueError("ECB reference rates are missing")
    return rates, str(dated_cube.attrib["time"])


def load_ecb_reference_rates(timeout_s: float = 3.0) -> tuple[dict[str, float], str]:
    """Download the latest ECB reference rates without making prices mandatory."""
    try:
        request = Request(
            ECB_DAILY_RATES_URL,
            headers={"User-Agent": "LoadForge/price-normalization"},
        )
        with urlopen(request, timeout=float(timeout_s)) as response:
            payload = response.read(512_000)
        return parse_ecb_reference_rates(payload)
    except (OSError, ValueError, ElementTree.ParseError):
        return {}, ""


def convert_price(
    price: float | None,
    source_currency: str,
    target_currency: str,
    rates: dict[str, float],
) -> float | None:
    """Convert a price through the EUR-based ECB reference-rate table."""
    value = _valid_price(price)
    source = str(source_currency or "").upper()
    target = str(target_currency or "").upper()
    if value is None or not source or not target:
        return None
    if source == target:
        return value
    try:
        source_rate = float(rates[source])
        target_rate = float(rates[target])
    except (KeyError, TypeError, ValueError):
        return None
    if not (
        np.isfinite(source_rate)
        and source_rate > 0.0
        and np.isfinite(target_rate)
        and target_rate > 0.0
    ):
        return None
    return value / source_rate * target_rate


def price_extension_score(f3_hz: float, price: float) -> float:
    """Lower-is-better value score: bass extension weighted by driver price.

    ``F3 * price`` rewards drivers that are simultaneously cheap and deep.
    Missing or non-positive inputs return ``inf`` so unpriced candidates sink
    to the bottom of a value-sorted ranking.
    """
    f3 = float(f3_hz)
    value = float(price)
    if not (np.isfinite(f3) and np.isfinite(value)) or f3 <= 0.0 or value <= 0.0:
        return float("inf")
    return f3 * value
