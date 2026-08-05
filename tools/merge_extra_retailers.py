#!/usr/bin/env python3
"""Merge tools/harvest_extra_retailers.py checkpoints (Cinergy Audio,
Audiophonics, DIY-Audio.eu, Willy's HiFi, Haut-Parleurs.fr, Lautsprechershop,
TopServicePro, KJF Audio, Hogtalarshoppen, DIYSpeakersEU, AnalogHiFi and
Thomann, DS18, Fi Car Audio, Wavecor, AUDIO-HI.FI, StrumentiMusicali and
Lean Audio) into
data/driver_prices.json, reusing
enrich_driver_prices.py's
indexed matcher so the catalog/prices schema stays consistent with every
other seller.

Safe to run repeatedly against partial/refreshed checkpoints.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import enrich_driver_prices as epd  # noqa: E402
from merge_partsexpress_harvest import load_all_candidates  # noqa: E402

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
    "thomann": (ROOT / "data" / "thomann_harvest_checkpoint.json", "Thomann"),
    "ds18": (ROOT / "data" / "ds18_harvest_checkpoint.json", "DS18"),
    "ficaraudio": (ROOT / "data" / "ficaraudio_harvest_checkpoint.json", "FiCarAudio"),
    "wavecor": (ROOT / "data" / "wavecor_harvest_checkpoint.json", "WavecorOfficial"),
    "audiohifi": (ROOT / "data" / "audiohifi_harvest_checkpoint.json", "AudioHiFi"),
    "strumentimusicali": (
        ROOT / "data" / "strumentimusicali_harvest_checkpoint.json",
        "StrumentiMusicali",
    ),
    "leanaudio": (ROOT / "data" / "leanaudio_harvest_checkpoint.json", "LeanAudio"),
    "bomberregional": (ROOT / "data" / "bomberregional_harvest_checkpoint.json", "BomberRegional"),
    "paudioregional": (ROOT / "data" / "paudio_regional_harvest_checkpoint.json", "PAudioRegional"),
    "phltlhp": (ROOT / "data" / "phl_tlhp_harvest_checkpoint.json", "PHL-TLHP"),
    "sicatlhp": (ROOT / "data" / "sica_soundimports_tlhp_checkpoint.json", "SICA-TLHP"),
    "toutlehautparleur": (
        ROOT / "data" / "toutlehautparleur_harvest_checkpoint.json",
        "ToutLeHautParleur",
    ),
}


def merge_source(payload: dict, checkpoint_path: Path, seller: str) -> int:
    if not checkpoint_path.exists():
        print(f"{seller}: no checkpoint at {checkpoint_path}, skipping")
        return 0
    state = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    # The checkpoint is the complete retained state for this seller. Rebuild
    # its catalog so an identity-key migration (URL -> URL+SKU) cannot leave
    # stale duplicate entries behind.
    catalog = {}
    payload.setdefault("catalog", {})[seller] = catalog
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
        variant = str(product.get("sku") or product.get("mpn") or "")
        catalog_key = f"{product['url']}#{variant}" if variant else product["url"]
        catalog[catalog_key] = epd.catalog_record(product, seller)
    return total


def main() -> None:
    payload = epd.load_output(PRICES_PATH)
    candidates = load_all_candidates()
    grand_total = 0
    for checkpoint_path, seller in SOURCES.values():
        total = merge_source(payload, checkpoint_path, seller)
        print(f"{seller}: ingested={total}")
        grand_total += total
    stats = epd.rematch_cached_catalog(candidates, payload, min_confidence=0.8)
    epd.write_output(PRICES_PATH, payload)
    print(
        f"TOTAL: ingested={grand_total} "
        + " ".join(f"{key}={value}" for key, value in stats.items())
    )


if __name__ == "__main__":
    main()
