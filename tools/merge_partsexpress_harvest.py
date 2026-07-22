#!/usr/bin/env python3
"""Merge tools/harvest_partsexpress.py checkpoint(s) into the live datasets:
new T/S presets into data/manufacturer_drivers.json, price records into
data/driver_prices.json (reusing enrich_driver_prices.py's matching logic
so the catalog/prices schema stays consistent with every other seller).

Safe to run repeatedly against a partial/in-progress checkpoint.
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import enrich_driver_prices as epd  # noqa: E402

MANUFACTURER_PATH = ROOT / "data" / "manufacturer_drivers.json"
LSDB_PATH = ROOT / "data" / "loudspeaker_database_drivers.json"
PRICES_PATH = ROOT / "data" / "driver_prices.json"


def load_all_candidates() -> list[epd.PresetCandidate]:
    candidates: list[epd.PresetCandidate] = []
    for path in (MANUFACTURER_PATH, LSDB_PATH):
        if path.exists():
            candidates.extend(epd.load_candidates(path))
    return candidates


def merge_presets(checkpoint_paths: list[Path]) -> int:
    data = json.loads(MANUFACTURER_PATH.read_text(encoding="utf-8"))
    existing_keys = {(p.get("brand"), p.get("model")) for p in data["presets"]}
    added = 0
    for cp_path in checkpoint_paths:
        state = json.loads(cp_path.read_text(encoding="utf-8"))
        for preset in state.get("presets", []):
            key = (preset.get("brand"), preset.get("model"))
            if key not in existing_keys:
                data["presets"].append(preset)
                existing_keys.add(key)
                added += 1
    if added:
        MANUFACTURER_PATH.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    return added


def _precomputed_candidates(candidates: list[epd.PresetCandidate]):
    """Precompute the per-candidate data match_score() would otherwise
    recompute from scratch for every single product — that redundant work
    turns an O(N) per-candidate cost into an O(N*M) cost across M products,
    which is what made the naive merge take many minutes against ~8400
    candidates. Each candidate's query/model/brand tokens depend only on
    the candidate, never on the product being matched, so they're safe to
    compute once and reuse.
    """
    out = []
    for c in candidates:
        query = "".join(epd.tokenize(c.query))
        models = epd.model_compacts(c.model)
        brands = epd.brand_compacts(c.brand)
        weak = bool(c.brand) and epd.candidate_model_is_weak(c.model)
        out.append((c, query, models, brands, weak))
    return out


def _fast_match_score(query, models, brands, weak, strong_sequences, all_sequences) -> float:
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


def merge_prices(checkpoint_paths: list[Path], min_confidence: float = 0.8) -> tuple[int, int]:
    payload = epd.load_output(PRICES_PATH)
    candidates = load_all_candidates()
    precomputed = _precomputed_candidates(candidates)
    catalog = payload.setdefault("catalog", {}).setdefault("PartsExpress", {})
    prices = payload.setdefault("prices", {})
    matched = 0
    total = 0
    for cp_path in checkpoint_paths:
        state = json.loads(cp_path.read_text(encoding="utf-8"))
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
            catalog[product["url"]] = epd.catalog_record(product, "PartsExpress")
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
            price_rec = epd.price_record(best_candidate, product, "PartsExpress", best_score)
            existing = prices.get(best_candidate.name)
            same_currency = isinstance(existing, dict) and str(existing.get("currency", "")) == price_rec["currency"]
            if not isinstance(existing, dict) or (
                same_currency and float(price_rec["price"]) <= float(existing.get("price", float("inf")))
            ):
                prices[best_candidate.name] = price_rec
            if best_candidate.model and best_candidate.model not in prices:
                prices[best_candidate.model] = price_rec
            matched += 1
    epd.write_output(PRICES_PATH, payload)
    return matched, total


def main() -> None:
    checkpoint_paths = sorted(Path(p) for p in glob.glob(str(ROOT / "data" / "partsexpress_harvest_checkpoint*.json")))
    if not checkpoint_paths:
        print("no partsexpress harvest checkpoints found")
        return
    print("checkpoints:", [p.name for p in checkpoint_paths])
    added_presets = merge_presets(checkpoint_paths)
    matched, total = merge_prices(checkpoint_paths)
    print(f"presets added: {added_presets}")
    print(f"price records ingested: {total}, matched to existing presets: {matched}")


if __name__ == "__main__":
    main()
