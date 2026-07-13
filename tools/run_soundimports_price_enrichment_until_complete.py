#!/usr/bin/env python3
"""Run provider price enrichment in restartable windows until complete.

Historically SoundImports-only; now supports every sitemap provider exposed by
`enrich_driver_prices.PROVIDERS` via `--provider` (SoundImports, Blue Aran,
Madisound and Parts Express).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import enrich_driver_prices as enricher


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "driver_prices.json"


def log(message: str):
    print(message, flush=True)


def output_progress(path: Path, provider: "enricher.Provider") -> tuple[int, int, int]:
    if not path.exists():
        return 0, 0, 0
    payload = json.loads(path.read_text(encoding="utf-8"))
    if provider.kind == "categories":
        done = payload.get("category_pages", {}).get(provider.seller, {})
        misses = {}
    else:
        done = payload.get("catalog", {}).get(provider.seller, {})
        misses = payload.get("catalog_misses", {}).get(provider.seller, {})
    prices = payload.get("prices", {})
    return len(done), len(misses), len(prices)


def sitemap_total(provider: "enricher.Provider", timeout_s: float) -> int:
    text = enricher.fetch_text(provider.sitemap_url, timeout_s)
    return len(enricher.provider_product_urls(provider, text))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=DEFAULT_OUTPUT, type=Path)
    parser.add_argument("--provider", choices=sorted(enricher.PROVIDERS), default="soundimports")
    parser.add_argument("--window-runtime", type=float, default=900.0)
    parser.add_argument("--pause", type=float, default=30.0)
    parser.add_argument("--sleep", type=float, default=2.0)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--min-confidence", type=float, default=0.8)
    parser.add_argument("--max-attempts", type=int, default=0, help="0 means no limit.")
    parser.add_argument("--retry-catalog", action="store_true")
    args = parser.parse_args()

    provider = enricher.PROVIDERS[args.provider]
    try:
        total = sitemap_total(provider, args.timeout)
    except enricher.FETCH_ERRORS as exc:
        log(f"cannot fetch sitemap yet: {exc}")
        total = 0

    attempt = 0
    script = ROOT / "tools" / "enrich_driver_prices.py"
    while args.max_attempts <= 0 or attempt < args.max_attempts:
        attempt += 1
        catalog, misses, prices = output_progress(args.output, provider)
        done = catalog + misses
        if provider.kind != "categories" and total and done >= total:
            log(f"complete: catalog={catalog} misses={misses} prices={prices} total={total}")
            return 0
        log(f"attempt {attempt}: catalog={catalog} misses={misses} prices={prices} total={total or 'unknown'}")
        cmd = [
            sys.executable,
            str(script),
            "--provider",
            args.provider,
            "--sitemap",
            "--limit",
            "0",
            "--sleep",
            str(args.sleep),
            "--timeout",
            str(args.timeout),
            "--max-runtime",
            str(args.window_runtime),
            "--min-confidence",
            str(args.min_confidence),
            "--output",
            str(args.output),
        ]
        if args.retry_catalog:
            cmd.append("--retry-catalog")
        before = done
        result = subprocess.run(cmd, check=False)
        catalog, misses, prices = output_progress(args.output, provider)
        done = catalog + misses
        if provider.kind == "categories":
            # Category crawls have no fixed page total: a clean window that
            # adds no new pages means the queue (including pagination) drained.
            if result.returncode == 0 and done == before and done > 0:
                log(f"complete: pages={catalog} prices={prices}")
                return 0
        elif total and done >= total:
            log(f"complete: catalog={catalog} misses={misses} prices={prices} total={total}")
            return 0
        if result.returncode != 0:
            log(f"attempt {attempt} exited with {result.returncode}; sleeping before retry")
        else:
            log(f"attempt {attempt} window done: catalog={catalog} misses={misses} prices={prices}")
        time.sleep(max(0.0, args.pause))
    catalog, misses, prices = output_progress(args.output, provider)
    log(f"stopped: catalog={catalog} misses={misses} prices={prices} total={total or 'unknown'}")
    return 75


if __name__ == "__main__":
    raise SystemExit(main())
