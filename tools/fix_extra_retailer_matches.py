#!/usr/bin/env python3
"""Repair driver_prices.json entries touched by merge_extra_retailers.py.

merge_extra_retailers.py's per-source pass matched each harvested product
against candidates in isolation, using the same weak-model-code heuristic
that enrich_driver_prices.py always uses. That heuristic can mis-fire when a
preset's "model" field is actually a full descriptive name (a fallback used
for some manufacturer-catalog presets that lack a clean model code): a
generic two-token overlap such as "8" + "reference" can score 0.65 for
"model_matched" even when the matched product is a different driver
entirely (e.g. a woofer preset matched to an unrelated tweeter, or to a
passive radiator).

This script re-derives the correct price for every preset key that
merge_extra_retailers.py touched by searching the FULL historical catalog
(every seller, not just the three new ones) with an added driver-type
consistency guard: if the candidate's name/model and the matched product's
name/url disagree on driver type (woofer vs tweeter vs passive radiator vs
midrange vs subwoofer...), the match is rejected regardless of score. This
both fixes the specific bad matches introduced this run and guards against
silently clobbering a previously-correct same-currency price from another
seller.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import enrich_driver_prices as epd  # noqa: E402
from merge_partsexpress_harvest import (  # noqa: E402
    _precomputed_candidates,
    load_all_candidates,
)

PRICES_PATH = ROOT / "data" / "driver_prices.json"
NEW_SELLERS = {"CinergyAudio", "Audiophonics", "DIYAudioEU"}

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


def driver_types(text: str) -> set[str]:
    lowered = text.casefold()
    return {tag for tag, patterns in DRIVER_TYPE_PATTERNS.items() if any(p in lowered for p in patterns)}


def types_conflict(candidate_text: str, product_text: str) -> bool:
    candidate_types = driver_types(candidate_text)
    product_types = driver_types(product_text)
    if not candidate_types or not product_types:
        return False
    # "radiator" (passive radiator, no motor) must never stand in for any
    # active driver type, and vice versa -- that pairing is always wrong.
    if "radiator" in candidate_types or "radiator" in product_types:
        return candidate_types != product_types
    return candidate_types.isdisjoint(product_types)


def fast_match_score_guarded(query, models, brands, weak, strong_sequences, all_sequences,
                              candidate_text: str, product_text: str) -> float:
    if types_conflict(candidate_text, product_text):
        return 0.0
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
    if weak and not brand_matched:
        score = min(score, 0.59)
    return min(score, 1.0)


def build_catalog_products(payload: dict) -> list[tuple[str, dict]]:
    out = []
    for seller, url_map in payload.get("catalog", {}).items():
        if not isinstance(url_map, dict):
            continue
        for url, rec in url_map.items():
            if not isinstance(rec, dict) or rec.get("price") is None:
                continue
            out.append((seller, {
                "name": rec.get("name", ""),
                "brand": rec.get("brand", ""),
                "mpn": rec.get("mpn", ""),
                "sku": rec.get("sku", ""),
                "url": rec.get("url", url),
                "price": rec.get("price"),
                "currency": rec.get("currency", ""),
                "availability": rec.get("availability", ""),
                "price_valid_until": rec.get("price_valid_until", ""),
            }))
    return out


def main() -> None:
    payload = epd.load_output(PRICES_PATH)
    prices = payload.setdefault("prices", {})
    touched_keys = [k for k, v in prices.items() if isinstance(v, dict) and v.get("seller") in NEW_SELLERS]
    print(f"keys touched by the three new sellers: {len(touched_keys)}")

    candidates = load_all_candidates()
    by_name = {c.name: c for c in candidates}
    by_model = {c.model: c for c in candidates if c.model}
    target_candidates = []
    for key in touched_keys:
        c = by_name.get(key) or by_model.get(key)
        if c is not None:
            target_candidates.append(c)
    # De-duplicate by candidate identity (name+model) since a price entry can
    # be keyed by either name or model pointing at the same candidate.
    seen = set()
    unique_targets = []
    for c in target_candidates:
        ident = (c.name, c.model)
        if ident not in seen:
            seen.add(ident)
            unique_targets.append(c)
    print(f"unique candidates to re-derive: {len(unique_targets)}")

    # _precomputed_candidates returns tuples (c, query, models, brands, weak)
    precomputed = {c.name: (query, models, brands, weak)
                   for c, query, models, brands, weak in _precomputed_candidates(unique_targets)}

    catalog_products = build_catalog_products(payload)
    print(f"catalog products to search: {len(catalog_products)}")

    fixed = 0
    cleared = 0
    for c in unique_targets:
        query, models, brands, weak = precomputed[c.name]
        candidate_text = f"{c.brand} {c.model} {c.name}"
        best_seller = None
        best_product = None
        best_score = 0.0
        for seller, product in catalog_products:
            if not epd.product_looks_like_driver(product):
                continue
            strong_sequences, all_sequences = epd.product_match_sequences(product)
            product_text = f"{product.get('name','')} {product.get('url','')}"
            score = fast_match_score_guarded(
                query, models, brands, weak, strong_sequences, all_sequences,
                candidate_text, product_text,
            )
            if score > best_score or (
                score == best_score and best_product is not None
                and product.get("price") is not None
                and product["price"] < best_product["price"]
            ):
                best_seller, best_product, best_score = seller, product, score
        if best_product is not None and best_score >= 0.8:
            price_rec = epd.price_record(c, best_product, best_seller, best_score)
            for key in (c.name, c.model):
                if key:
                    prices[key] = price_rec
            fixed += 1
        else:
            for key in (c.name, c.model):
                if key in prices and isinstance(prices[key], dict) and prices[key].get("seller") in NEW_SELLERS:
                    del prices[key]
            cleared += 1

    epd.write_output(PRICES_PATH, payload)
    print(f"re-derived (kept a match): {fixed}")
    print(f"cleared (no confident match remained): {cleared}")


if __name__ == "__main__":
    main()
