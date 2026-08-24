#!/usr/bin/env python3
"""Harvest current and archived Ciare LF/coaxial driver variants."""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import crawl_thiele_small as crawler

SITE_ROOT = "https://www.ciare.com"
LISTINGS = (
    ("current LF", f"{SITE_ROOT}/en/products/lf-driver?category=lf-driver"),
    ("current coaxial", f"{SITE_ROOT}/en/products/coaxial?category=coaxial"),
    ("archived LF", f"{SITE_ROOT}/en/products-archive/lf-driver?category=lf-driver"),
    ("archived coaxial", f"{SITE_ROOT}/en/products-archive/coaxial?category=coaxial"),
)
DEFAULT_OUTPUT = ROOT / "data" / "ciare_official_checkpoint.json"
USER_AGENT = "LoadForgeCrawler/1.0 (official catalog research)"
PRODUCT_LINK_RE = re.compile(
    r'href=["\'](/en/products(?:-archive)?/(?:lf-driver|coaxial)/[^"\'?#]+)["\']',
    re.I,
)


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def fetch_bytes(url: str, timeout_s: float = 30.0) -> bytes:
    request = Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
    )
    with urlopen(request, timeout=timeout_s) as response:
        return response.read()


def products_from_listing(document: bytes, family: str) -> list[dict[str, str]]:
    text = document.decode("utf-8", errors="replace")
    products: list[dict[str, str]] = []
    seen: set[str] = set()
    for path in PRODUCT_LINK_RE.findall(text):
        path = html.unescape(path).rstrip("/")
        url = f"{SITE_ROOT}{path}"
        if url in seen:
            continue
        seen.add(url)
        parts = urlparse(url).path.rstrip("/").split("/")
        if len(parts) < 3:
            continue
        products.append(
            {
                "url": url,
                "model": html.unescape(parts[-1]),
                "impedance": html.unescape(parts[-2]),
                "family": family,
            }
        )
    return products


def preset_from_product(document: bytes, product: dict[str, str]) -> tuple[dict | None, str]:
    page = crawler.parse_html(document)
    preset, errors = crawler.build_preset(
        page,
        product["url"],
        source_name="Official manufacturer site",
        brand_hint="Ciare",
    )
    if preset is None:
        return None, "; ".join(errors) or "incomplete T/S record"
    impedance = float(product["impedance"])
    model = f"{product['model']} ({product['impedance']}Ω)"
    preset["brand"] = "Ciare"
    preset["model"] = model
    preset["name"] = f"WEB: Ciare {model}"
    preset["website_fields"]["brand"] = "Ciare"
    preset["website_fields"]["model"] = model
    preset["website_fields"]["catalog_family"] = product["family"]
    preset.setdefault("published_specs", {})["nominal_impedance_ohm"] = impedance
    return preset, ""


def harvest(
    *,
    fetcher: Callable[[str, float], bytes] = fetch_bytes,
    timeout_s: float = 30.0,
    workers: int = 8,
    retries: int = 2,
) -> dict:
    products: list[dict[str, str]] = []
    failures: list[dict] = []
    listing_counts: dict[str, int] = {}
    for family, url in LISTINGS:
        try:
            batch = products_from_listing(fetcher(url, timeout_s), family)
            products.extend(batch)
            listing_counts[family] = len(batch)
            print(f"CIARE LISTING: family={family} products={len(batch)}", flush=True)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            failures.append({"url": url, "family": family, "error": f"{type(exc).__name__}: {exc}"})

    unique_products: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for product in products:
        if product["url"] not in seen_urls:
            unique_products.append(product)
            seen_urls.add(product["url"])

    def fetch_product(product: dict[str, str]) -> tuple[dict[str, str], bytes | None, str | None]:
        for attempt in range(retries + 1):
            try:
                return product, fetcher(product["url"], timeout_s), None
            except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
                if attempt >= retries:
                    return product, None, f"{type(exc).__name__}: {exc}"
                time.sleep(0.35 * (attempt + 1))
        return product, None, "retry loop exhausted"

    presets: list[dict] = []
    rejections: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        pending = [pool.submit(fetch_product, product) for product in unique_products]
        for completed, future in enumerate(as_completed(pending), start=1):
            product, document, error = future.result()
            if document is None:
                failures.append({"url": product["url"], "error": error})
            else:
                preset, reason = preset_from_product(document, product)
                if preset is None:
                    rejections.append({"url": product["url"], "model": product["model"], "reason": reason})
                else:
                    presets.append(preset)
            if completed % 10 == 0 or completed == len(pending):
                print(
                    f"CIARE PROGRESS: {completed}/{len(pending)} accepted={len(presets)} "
                    f"rejected={len(rejections)} failures={len(failures)}",
                    flush=True,
                )

    presets.sort(key=lambda item: (str(item["model"]).casefold(), str(item["url"])))
    return {
        "schema_version": 1,
        "generated_at": utc_now(),
        "source": "Ciare public official current catalog and archive",
        "catalog_root": f"{SITE_ROOT}/en/products",
        "publication_state": "staging_only",
        "listed": len(unique_products),
        "listed_by_family": listing_counts,
        "accepted": len(presets),
        "rejected": len(rejections),
        "rejections": rejections,
        "failures": failures,
        "presets": presets,
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--retries", type=int, default=2)
    args = parser.parse_args()
    payload = harvest(timeout_s=args.timeout, workers=max(1, args.workers), retries=max(0, args.retries))
    write_json(args.output, payload)
    print(
        f"CIARE OFFICIAL: listed={payload['listed']} accepted={payload['accepted']} "
        f"rejected={payload['rejected']} failures={len(payload['failures'])} output={args.output}"
    )
    return 0 if not payload["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
