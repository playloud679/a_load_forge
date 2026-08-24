#!/usr/bin/env python3
"""Append explicitly reviewed crawler records without touching existing rows."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import crawl_thiele_small as crawler
from src import presets as runtime_presets


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def identity(item: dict[str, Any]) -> tuple[str, str]:
    return (
        str(item.get("brand") or "").strip().casefold(),
        str(item.get("model") or "").strip().casefold(),
    )


def runtime_identity(item: dict[str, Any]) -> tuple[str, str, str]:
    driver = runtime_presets._driver_ts_from_mapping(dict(item.get("driver") or {}))
    brand = runtime_presets._external_catalog_manufacturer(
        str(item.get("brand") or "")
    )
    item_model = str(item.get("model") or item.get("name") or "")
    identity_model = runtime_presets._external_catalog_identity_model(
        item, item_model
    )
    part_number = runtime_presets._external_catalog_part_number(
        brand, identity_model
    )
    return runtime_presets._external_catalog_identity(
        brand,
        part_number or item_model,
        driver,
        str(item.get("impedance") or item_model),
    )


def publish(
    catalog_path: Path,
    candidate_path: Path,
    accepted_urls: set[str],
    *,
    dry_run: bool,
) -> dict[str, Any]:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    candidates = json.loads(candidate_path.read_text(encoding="utf-8"))
    existing = list(catalog.get("presets") or [])
    old_digests = [canonical_digest(item) for item in existing]
    existing_names = {str(item.get("name") or "") for item in existing}
    existing_identities = {identity(item) for item in existing}
    existing_runtime_identities = {runtime_identity(item) for item in existing}

    selected = [
        item
        for item in candidates.get("presets", [])
        if str(item.get("url") or "").rstrip("/") in accepted_urls
    ]
    selected_urls = {str(item.get("url") or "").rstrip("/") for item in selected}
    missing = accepted_urls - selected_urls
    if missing:
        raise ValueError(f"reviewed URLs absent from candidate artifact: {sorted(missing)}")

    additions: list[dict[str, Any]] = []
    for item in selected:
        name = str(item.get("name") or "").strip()
        url = str(item.get("url") or "").rstrip("/")
        source = str(item.get("source") or "")
        confidence = float((item.get("website_fields") or {}).get("confidence", 0.0))
        errors = crawler.validate_driver(dict(item.get("driver") or {}))
        if source != "Official manufacturer site":
            raise ValueError(f"{url}: unapproved source {source!r}")
        if confidence < 0.75:
            raise ValueError(f"{url}: confidence below 0.75")
        if errors:
            raise ValueError(f"{url}: {'; '.join(errors)}")
        if not name or name in existing_names:
            raise ValueError(f"{url}: duplicate or empty display name")
        if identity(item) in existing_identities:
            raise ValueError(f"{url}: brand/model already exists in catalog")
        if runtime_identity(item) in existing_runtime_identities:
            raise ValueError(f"{url}: runtime driver identity already exists in catalog")
        additions.append(item)
        existing_names.add(name)
        existing_identities.add(identity(item))
        existing_runtime_identities.add(runtime_identity(item))

    output = dict(catalog)
    output["presets"] = [*existing, *additions]
    if [canonical_digest(item) for item in output["presets"][: len(existing)]] != old_digests:
        raise RuntimeError("append-only invariant failed: an existing row changed")

    if not dry_run:
        temporary = catalog_path.with_suffix(catalog_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(output, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(catalog_path)

    return {
        "baseline_records": len(existing),
        "added": len(additions),
        "final_records": len(existing) + len(additions),
        "existing_rows_unchanged": True,
        "dry_run": dry_run,
        "added_names": [item["name"] for item in additions],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--accept-url", action="append", default=[], required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = publish(
        args.catalog,
        args.candidate,
        {url.rstrip("/") for url in args.accept_url},
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
