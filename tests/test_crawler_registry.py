#!/usr/bin/env python3
"""Fast policy tests for manufacturer discovery and staging-only crawling."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import build_official_source_registry as registry_builder
from crawl_retailer_discovery import parse_price_number, parse_rg_page
from services.crawler_agent.model import AgentManifest
from services.crawler_agent.agent import _crawl_stats


def row(brand: str, model: str, url: str, source: str | None = None) -> dict:
    return {
        "name": f"WEB: {brand} {model}",
        "brand": brand,
        "model": model,
        "url": url,
        "source": source,
        "driver": {},
    }


def main() -> int:
    payload = {
        "catalog_version": "1.0.0",
        "presets": [
            row("Alpha Audio", "A10", "https://alphaaudio.com/products/a10", "Manufacturer website"),
            row("Alpha Audio Reference", "A12", "https://alphaaudio.com/products/a12", "Official crawl"),
            row("Retail Brand", "R10", "https://www.rgsound.it/r10_retail-brand-id-1.html", "Retailer"),
            row("Seeded Brand", "S10", "https://www.parts-express.com/seeded-s10", "Retailer"),
            row("Legacy Seeded", "L10", "https://www.parts-express.com/legacy-l10", "Retailer"),
            row("NXL-X8TPNEO", "X8", "https://ds18.com/products/x8", "Official crawl"),
        ],
    }
    source_seeds = {
        "verified_sources": [
            {
                "brand": "Seeded Brand",
                "url": "https://seeded.example.com/woofers/",
                "evidence": "reviewed official source",
            }
        ],
        "aliases": [
            {
                "brand": "Legacy Seeded",
                "canonical_brand": "Seeded Brand",
                "evidence": "reviewed legacy label",
            }
        ],
    }
    registry = registry_builder.build_registry(
        payload, source_seeds=source_seeds
    )
    entries = {entry["brand"]: entry for entry in registry["brands"]}
    assert entries["Alpha Audio"]["status"] == "ready"
    assert entries["Alpha Audio"]["official_domain"] == "alphaaudio.com"
    assert entries["Alpha Audio Reference"]["status"] == "alias"
    assert entries["Retail Brand"]["status"] == "needs_discovery"
    assert "rgsound.it" in entries["Retail Brand"]["rejected_non_manufacturer_domains"]
    assert entries["Seeded Brand"]["status"] == "ready"
    assert entries["Seeded Brand"]["seed"] == "https://seeded.example.com/woofers/"
    assert entries["Legacy Seeded"]["status"] == "alias"
    assert entries["Legacy Seeded"]["alias_of"] == "Seeded Brand"
    assert entries["NXL-X8TPNEO"]["status"] == "needs_brand_cleanup"

    manifest_payload = registry_builder.build_manifest(registry, max_targets=3)
    manifest = AgentManifest.from_mapping(manifest_payload)
    assert len(manifest.targets) == 2
    assert {target.allowed_domains for target in manifest.targets} == {
        ("alphaaudio.com",),
        ("seeded.example.com",),
    }
    assert all(not target.include for target in manifest.targets)
    assert _crawl_stats(
        "visited=12 extracted=3 added=2 updated=1 unchanged=0 failures=4"
    ) == {
        "visited": 12,
        "extracted": 3,
        "added": 2,
        "updated": 1,
        "unchanged": 0,
        "failures": 4,
    }
    retail_rows = parse_rg_page(
        """
        <div class="prodotto prodottoLista">
          <span class="marca">Hertz</span>
          <a class="prodotto_mobile_titdescr" href="/mps_hertz-id-1.html">
            <span class="prodotto_mobile_rigo1">Hertz MPS 300 S4</span>
          </a>
          <span class="prodotto-prezzo-intero">399,</span>
          <span class="prodotto-prezzo-decimale">00</span>
        </div>
        """
    )
    assert retail_rows[0]["brand"] == "Hertz"
    assert retail_rows[0]["model"] == "MPS 300 S4"
    assert retail_rows[0]["price"] == 399.0
    assert retail_rows[0]["source_role"] == "model_gap_and_price_discovery_only"
    assert parse_price_number("653.00") == 653.0
    assert parse_price_number("1.040,76") == 1040.76

    daemon_source = (ROOT / "tools" / "autonomous_crawler_daemon.py").read_text(encoding="utf-8")
    assert "subprocess.run" not in daemon_source
    assert "infer_sd" not in daemon_source
    assert "git\", \"push" not in daemon_source
    assert "catalog_unchanged" in daemon_source
    print("CRAWLER REGISTRY PASS: manufacturer-first, retailer-isolated, staging-only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
