#!/usr/bin/env python3
"""Harvest T/S-complete driver pages from the cached SoundImports catalog."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import crawl_thiele_small as ts

ROOT = Path(__file__).resolve().parents[1]
PRICE_PATH = ROOT / "data" / "driver_prices.json"
OUTPUT_PATH = ROOT / "data" / "manufacturer_drivers.json"
CHECKPOINT_PATH = ROOT / "data" / "soundimports_driver_crawler_checkpoint.json"
REJECTIONS_PATH = ROOT / "data" / "soundimports_driver_rejections.json"

DRIVER_TERMS = re.compile(
    r"\b(?:woofer|subwoofer|midwoofer|midbass|midrange|bass[- ]?mid|"
    r"full[- ]?range|loudspeaker|speaker driver|coaxial)\b",
    re.I,
)
EXCLUDED_TERMS = re.compile(
    r"\b(?:recone|repair|kit|cabinet|enclosure|grille|cable|connector|"
    r"capacitor|inductor|amplifier|plate amp|horn|compression|tweeter|"
    r"waveguide|adapter|stand|handle|paint|terminal|crossover|book)\b",
    re.I,
)
BRAND_CANONICAL = {
    "peerless by tymphany": "Peerless",
    "beyma": "Beyma",
    "faital pro": "FaitalPRO",
    "scanspeak": "Scan-Speak",
}
DIMENSIONAL_REQUIRED = ("fs_hz", "vas_l", "re_ohm", "sd_cm2")


def clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def canonical_brand(value: object) -> str:
    brand = clean(value)
    return BRAND_CANONICAL.get(brand.casefold(), brand)


def candidate_records(payload: dict) -> list[dict]:
    catalog = payload.get("catalog", {}).get("SoundImports", {})
    rows = list(catalog.values()) if isinstance(catalog, dict) else list(catalog)
    selected = []
    for row in rows:
        name = clean(row.get("name"))
        brand = canonical_brand(row.get("brand"))
        model = clean(row.get("mpn") or row.get("sku"))
        url = clean(row.get("url"))
        if not (brand and model and url and DRIVER_TERMS.search(name)):
            continue
        if EXCLUDED_TERMS.search(name):
            continue
        selected.append({**row, "brand": brand, "model": model, "url": url})
    return list({row["url"]: row for row in selected}.values())


def quality_error(preset: dict) -> str:
    fields = preset.get("website_fields", {})
    raw = fields.get("raw_measurements", {})
    derived = set(fields.get("derived_fields", []))
    for key in DIMENSIONAL_REQUIRED:
        if key in derived:
            continue
        measurement = raw.get(key, {})
        if not ts.normalize_unit(str(measurement.get("unit") or "")):
            return f"required dimensional field {key} has no explicit unit"
    return ""


def apply_catalog_identity(preset: dict, catalog_by_url: dict[str, dict]) -> dict:
    row = catalog_by_url.get(preset.get("url", ""))
    if not row:
        return preset
    brand = canonical_brand(row.get("brand"))
    model = clean(row.get("model"))
    preset["brand"] = brand
    preset["model"] = model
    preset["name"] = f"WEB: {brand} {model}"
    preset["source"] = "SoundImports retailer"
    fields = preset.setdefault("website_fields", {})
    fields.update({
        "brand": brand,
        "model": model,
        "source": "SoundImports retailer",
        "catalog_name": clean(row.get("name")),
        "catalog_sku": clean(row.get("sku")),
    })
    return preset


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--sleep", type=float, default=0.2)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--max-pages", type=int, default=100_000)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    payload = json.loads(PRICE_PATH.read_text(encoding="utf-8"))
    records = candidate_records(payload)
    catalog_by_url = {row["url"]: row for row in records}
    config = ts.CrawlConfig(
        seeds=list(catalog_by_url),
        sitemaps=[],
        output=OUTPUT_PATH,
        checkpoint=CHECKPOINT_PATH,
        source_name="SoundImports retailer",
        allowed_domains={"soundimports.eu"},
        max_pages=min(args.max_pages, len(records)),
        max_depth=0,
        timeout_s=args.timeout,
        sleep_s=args.sleep,
        follow_links=False,
        fresh=args.fresh,
        dry_run=args.dry_run,
    )
    presets, failures, visited = ts.crawl(config)
    accepted = []
    quality_rejections = []
    for preset in presets:
        preset = apply_catalog_identity(preset, catalog_by_url)
        if error := quality_error(preset):
            quality_rejections.append({"url": preset.get("url", ""), "error": error})
        else:
            accepted.append(preset)
    ts.atomic_write_json(REJECTIONS_PATH, {
        "source": "SoundImports",
        "candidate_count": len(records),
        "visited_count": len(visited),
        "crawler_failures": failures,
        "quality_rejections": quality_rejections,
    })
    stats = {"added": 0, "updated": 0, "unchanged": 0}
    if not args.dry_run:
        stats = ts.populate_database(config, accepted)
    ts.log(
        f"candidates={len(records)} visited={len(visited)} extracted={len(presets)} "
        f"quality_rejected={len(quality_rejections)} accepted={len(accepted)} "
        f"added={stats['added']} updated={stats['updated']} unchanged={stats['unchanged']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
