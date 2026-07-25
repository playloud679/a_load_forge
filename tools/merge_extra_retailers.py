#!/usr/bin/env python3
"""Merge tools/harvest_extra_retailers.py checkpoints (Cinergy Audio,
Audiophonics, DIY-Audio.eu, Willy's HiFi, Haut-Parleurs.fr, Lautsprechershop,
TopServicePro, KJF Audio, Hogtalarshoppen) into data/driver_prices.json, reusing
enrich_driver_prices.py's matching logic via the fast precomputed-candidate
variant introduced in merge_partsexpress_harvest.py so the catalog/prices
schema stays consistent with every other seller.

Safe to run repeatedly against partial/refreshed checkpoints.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import enrich_driver_prices as epd  # noqa: E402
from merge_partsexpress_harvest import (  # noqa: E402
    _fast_match_score,
    _precomputed_candidates,
    load_all_candidates,
)

PRICES_PATH = ROOT / "data" / "driver_prices.json"

SOURCES = {
    "cinergyaudio": (ROOT / "data" / "cinergyaudio_harvest_checkpoint.json", "CinergyAudio"),
    "audiophonics": (ROOT / "data" / "audiophonics_harvest_checkpoint.json", "Audiophonics"),
    "diyaudioeu": (ROOT / "data" / "diyaudioeu_harvest_checkpoint.json", "DIYAudioEU"),
    "willyshifi": (ROOT / "data" / "willyshifi_harvest_checkpoint.json", "WillysHiFi"),
    "hautparleursfr": (ROOT / "data" / "hautparleursfr_harvest_checkpoint.json", "HautParleursFr"),
    "lautsprechershop": (ROOT / "data" / "lautsprechershop_harvest_checkpoint.json", "Lautsprechershop"),
    "topservicepro": (ROOT / "data" / "topservicepro_harvest_checkpoint.json", "TopServicePro"),
    "kjfaudio": (ROOT / "data" / "kjfaudio_harvest_checkpoint.json", "KJFAudio"),
    "hogtalarshoppen": (ROOT / "data" / "hogtalarshoppen_harvest_checkpoint.json", "Hogtalarshoppen"),
    "diyspeakerseu": (ROOT / "data" / "diyspeakerseu_harvest_checkpoint.json", "DIYSpeakersEU"),
    "analoghifi": (ROOT / "data" / "analoghifi_harvest_checkpoint.json", "AnalogHiFi"),
}


def merge_source(payload: dict, precomputed, checkpoint_path: Path, seller: str, min_confidence: float) -> tuple[int, int]:
    if not checkpoint_path.exists():
        print(f"{seller}: no checkpoint at {checkpoint_path}, skipping")
        return 0, 0
    state = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    catalog = payload.setdefault("catalog", {}).setdefault(seller, {})
    prices = payload.setdefault("prices", {})
    matched = 0
    total = 0
    for record in state.get("prices", []):
        product = {
            "name": record.get("name", ""),
            "brand": record.get("brand", ""),
            "mpn": record.get("mpn", ""),
            "sku": record.get("sku", ""),
            "url": record.get("url", ""),
            "price": record.get("price"),
            "currency": record.get("currency", "USD"),
            "availability": record.get("availability", ""),
            "price_valid_until": record.get("price_valid_until", ""),
        }
        if product["price"] is None or not product["url"]:
            continue
        total += 1
        catalog[product["url"]] = epd.catalog_record(product, seller)
        if not epd.product_looks_like_driver(product):
            continue
        strong_sequences, all_sequences = epd.product_match_sequences(product)
        best_candidate = None
        best_score = 0.0
        for c, query, models, brands, weak in precomputed:
            score = _fast_match_score(query, models, brands, weak, strong_sequences, all_sequences)
            if score > best_score:
                best_candidate, best_score = c, score
        if best_candidate is None or best_score < min_confidence:
            continue
        # _fast_match_score (unlike enrich_driver_prices.match_score) has no
        # driver-type consistency guard -- restore it here as a post-hoc
        # check so this merge path can't reintroduce the woofer<->tweeter
        # class of false positive that match_score() itself was fixed
        # against (see docs/pricing.md / scrape playbook for the history).
        candidate_text = f"{best_candidate.brand} {best_candidate.model} {best_candidate.name}"
        product_text = f"{product.get('name', '')} {product.get('url', '')}"
        if epd.driver_types_conflict(candidate_text, product_text):
            continue
        # Same lineage gap as above: _fast_match_score also has no guard
        # against matching a single-unit preset to a multi-unit bulk pack
        # listing (e.g. a BlueAran "Four Pack" SKU priced ~4x the single
        # unit) -- restore epd.match_score()'s post-2026-07-24 pack guard
        # here too, post-hoc.
        if epd.product_is_multi_unit_pack(product) and not epd._PACK_QUANTITY_RE.search(candidate_text.casefold()):
            continue
        price_rec = epd.price_record(best_candidate, product, seller, best_score)
        existing = prices.get(best_candidate.name)
        same_currency = isinstance(existing, dict) and str(existing.get("currency", "")) == price_rec["currency"]
        if not isinstance(existing, dict) or (
            same_currency and float(price_rec["price"]) <= float(existing.get("price", float("inf")))
        ):
            prices[best_candidate.name] = price_rec
        if best_candidate.model and best_candidate.model not in prices:
            prices[best_candidate.model] = price_rec
        matched += 1
    return matched, total


def main() -> None:
    payload = epd.load_output(PRICES_PATH)
    candidates = load_all_candidates()
    precomputed = _precomputed_candidates(candidates)
    grand_matched = 0
    grand_total = 0
    for key, (checkpoint_path, seller) in SOURCES.items():
        matched, total = merge_source(payload, precomputed, checkpoint_path, seller, min_confidence=0.8)
        print(f"{seller}: ingested={total} matched={matched}")
        grand_matched += matched
        grand_total += total
    epd.write_output(PRICES_PATH, payload)
    print(f"TOTAL: ingested={grand_total} matched={grand_matched}")


if __name__ == "__main__":
    main()
