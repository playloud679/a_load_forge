#!/usr/bin/env python3
"""Run retailer price enrichment concurrently, then atomically merge shards."""

from __future__ import annotations

import argparse
import copy
import fcntl
import json
import os
import subprocess
import sys
from pathlib import Path

import enrich_driver_prices as enricher


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "driver_prices.json"
DEFAULT_SHARD_DIR = ROOT / "io" / "price_shards"
DEFAULT_PROVIDERS = ("soundimports", "bluearan", "madisound", "partsexpress")


def log(message: str) -> None:
    print(message, flush=True)


def _empty_payload() -> dict:
    return {
        "schema": 1,
        "updated_at": "",
        "prices": {},
        "misses": {},
        "catalog": {},
        "catalog_misses": {},
        "category_pages": {},
    }


def _read_payload(path: Path) -> dict:
    if not path.exists():
        return _empty_payload()
    return json.loads(path.read_text(encoding="utf-8"))


def _provider_owns_price(provider: enricher.Provider, record: object) -> bool:
    if not isinstance(record, dict):
        return False
    seller = str(record.get("seller") or "").casefold()
    aliases = {provider.seller.casefold()}
    if provider.key == "soundimports":
        aliases.add("soundimports.eu")
    return seller in aliases


def _seed_shard(provider: enricher.Provider, main_payload: dict, shard_path: Path) -> None:
    if shard_path.exists():
        return
    shard = _empty_payload()
    shard["prices"] = {
        key: copy.deepcopy(record)
        for key, record in main_payload.get("prices", {}).items()
        if _provider_owns_price(provider, record)
    }
    shard["misses"] = {
        key: copy.deepcopy(record)
        for key, record in main_payload.get("misses", {}).items()
        if not isinstance(record, dict)
        or str(record.get("provider") or "soundimports").casefold() == provider.key
    }
    for section in ("catalog", "catalog_misses", "category_pages"):
        provider_values = main_payload.get(section, {}).get(provider.seller, {})
        if provider_values:
            shard[section][provider.seller] = copy.deepcopy(provider_values)
    shard_path.parent.mkdir(parents=True, exist_ok=True)
    enricher.write_output(shard_path, shard)
    log(f"provider {provider.key}: seeded {shard_path}")


def _prefer_price(existing: object, candidate: object) -> object:
    if not isinstance(candidate, dict):
        return existing
    if not isinstance(existing, dict):
        return copy.deepcopy(candidate)
    if str(existing.get("currency") or "") != str(candidate.get("currency") or ""):
        return existing
    try:
        if float(candidate.get("price")) <= float(existing.get("price")):
            return copy.deepcopy(candidate)
    except (TypeError, ValueError):
        pass
    return existing


def _merge_shards(output_path: Path, shard_paths: dict[str, Path]) -> None:
    lock_path = output_path.with_suffix(output_path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        merged = _read_payload(output_path)
        merged.setdefault("prices", {})
        merged.setdefault("misses", {})
        for section in ("catalog", "catalog_misses", "category_pages"):
            merged.setdefault(section, {})

        for provider_key in DEFAULT_PROVIDERS:
            shard_path = shard_paths.get(provider_key)
            if shard_path is None or not shard_path.exists():
                continue
            provider = enricher.PROVIDERS[provider_key]
            shard = _read_payload(shard_path)
            for price_key, record in shard.get("prices", {}).items():
                merged["prices"][price_key] = _prefer_price(
                    merged["prices"].get(price_key), record,
                )
            merged["misses"].update(copy.deepcopy(shard.get("misses", {})))
            for section in ("catalog", "catalog_misses", "category_pages"):
                provider_values = shard.get(section, {}).get(provider.seller)
                if isinstance(provider_values, dict):
                    merged[section][provider.seller] = copy.deepcopy(provider_values)

        temp_path = output_path.with_suffix(output_path.suffix + ".tmp")
        enricher.write_output(temp_path, merged)
        os.replace(temp_path, output_path)
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    log(f"merged {len(merged['prices'])} prices into {output_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=DEFAULT_OUTPUT, type=Path)
    parser.add_argument("--shard-dir", default=DEFAULT_SHARD_DIR, type=Path)
    parser.add_argument(
        "--providers", nargs="+", choices=sorted(enricher.PROVIDERS),
        default=list(DEFAULT_PROVIDERS),
    )
    parser.add_argument("--window-runtime", type=float, default=900.0)
    parser.add_argument("--sleep", type=float, default=2.0)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--min-confidence", type=float, default=0.8)
    args = parser.parse_args()

    main_payload = _read_payload(args.output)
    script = ROOT / "tools" / "enrich_driver_prices.py"
    workers: dict[str, subprocess.Popen] = {}
    shard_paths: dict[str, Path] = {}
    for provider_key in args.providers:
        provider = enricher.PROVIDERS[provider_key]
        shard_path = args.shard_dir / f"{provider_key}.json"
        shard_paths[provider_key] = shard_path
        _seed_shard(provider, main_payload, shard_path)
        command = [
            sys.executable,
            str(script),
            "--provider", provider_key,
            "--sitemap",
            "--limit", "0",
            "--sleep", str(args.sleep),
            "--timeout", str(args.timeout),
            "--max-runtime", str(args.window_runtime),
            "--min-confidence", str(args.min_confidence),
            "--output", str(shard_path),
        ]
        workers[provider_key] = subprocess.Popen(command)
        log(f"provider {provider_key}: worker pid={workers[provider_key].pid}")

    failures: list[str] = []
    for provider_key, worker in workers.items():
        returncode = worker.wait()
        if returncode:
            failures.append(provider_key)
            log(f"provider {provider_key}: failed with exit code {returncode}")
        else:
            log(f"provider {provider_key}: window completed")

    _merge_shards(args.output, shard_paths)
    if failures:
        log(f"cycle completed with failures: {', '.join(failures)}")
        return 1
    log("parallel cycle completed successfully")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
