#!/usr/bin/env python3
"""Harvest complete T/S records from Monacor's first-party product catalog."""

from __future__ import annotations

import argparse
import html
import json
import math
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import crawl_thiele_small as crawler

CATALOG_ROOT = "https://www.monacor.com/products/components/speaker-technology/"
SITE_ROOT = "https://www.monacor.com/"
DEFAULT_OUTPUT = ROOT / "data" / "monacor_official_checkpoint.json"
USER_AGENT = "LoadForgeCrawler/1.0 (official catalog research)"
CATEGORY_SLUGS = (
    "pa-bass-speakers-",
    "pa-midrange-speakers-",
    "pa-coaxial-speakers-and-full-range-speakers-",
    "hi-fi-speakers-",
    "hi-fi-midrange-speakers-",
    "hi-fi-full-range-speakers-",
    "miniature-speakers-",
)
PRODUCT_LINK_RE = re.compile(
    r'<a\s+href="([^"]+)"\s+itemprop="url"[^>]*class="[^"]*\bitem\b',
    re.I,
)
RESULT_COUNT_RE = re.compile(r'<span\s+id="num_results">\s*(\d+)', re.I)
MANUFACTURER_RE = re.compile(
    r"Manufacturer information:</div>\s*<div[^>]*>(.*?)</div>",
    re.I | re.S,
)
TAG_RE = re.compile(r"<[^>]+>")


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def fetch_bytes(url: str, timeout_s: float = 30.0) -> bytes:
    request = Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
    )
    with urlopen(request, timeout=timeout_s) as response:
        return response.read()


def product_links(document: bytes, _page_url: str) -> list[str]:
    """Return stable product links, honoring Monacor's document-level base href."""
    text = document.decode("utf-8", errors="replace")
    links: list[str] = []
    seen: set[str] = set()
    for match in PRODUCT_LINK_RE.finditer(text):
        url = urljoin(SITE_ROOT, html.unescape(match.group(1))).rstrip("/") + "/"
        if url not in seen:
            seen.add(url)
            links.append(url)
    return links


def result_count(document: bytes) -> int:
    match = RESULT_COUNT_RE.search(document.decode("utf-8", errors="replace"))
    return int(match.group(1)) if match else 0


def manufacturer_text(document: bytes) -> str:
    text = document.decode("utf-8", errors="replace")
    match = MANUFACTURER_RE.search(text)
    if not match:
        return ""
    value = re.sub(r"\s+", " ", TAG_RE.sub(" ", html.unescape(match.group(1))))
    return value.strip()


def is_monacor_manufacturer(document: bytes) -> bool:
    return manufacturer_text(document).casefold().startswith("monacor international")


def preset_from_product(document: bytes, url: str) -> tuple[dict | None, str]:
    manufacturer = manufacturer_text(document)
    if not manufacturer.casefold().startswith("monacor international"):
        return None, "different or missing manufacturer"
    page = crawler.parse_html(document)
    preset, errors = crawler.build_preset(
        page,
        url,
        source_name="Official manufacturer site",
        brand_hint="Monacor",
    )
    if preset is None:
        return None, "; ".join(errors) or "incomplete T/S record"
    preset["brand"] = "Monacor"
    preset["name"] = f"WEB: Monacor {preset['model']}"
    preset["website_fields"]["brand"] = "Monacor"
    preset["website_fields"]["manufacturer_evidence"] = manufacturer
    return preset, ""


def harvest(
    *,
    fetcher: Callable[[str, float], bytes] = fetch_bytes,
    timeout_s: float = 30.0,
    sleep_s: float = 0.15,
    workers: int = 4,
    retries: int = 2,
) -> dict:
    product_urls: list[str] = []
    seen_urls: set[str] = set()
    category_counts: dict[str, int] = {}
    listing_failures: list[dict] = []
    for slug in CATEGORY_SLUGS:
        category_url = urljoin(CATALOG_ROOT, f"{slug}/")
        try:
            first = fetcher(category_url, timeout_s)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            listing_failures.append({"url": category_url, "error": f"{type(exc).__name__}: {exc}"})
            continue
        expected = result_count(first)
        category_counts[slug] = expected
        pages = max(1, math.ceil(expected / 12))
        documents = [first]
        for page_number in range(2, pages + 1):
            page_url = f"{category_url}?page={page_number}"
            try:
                documents.append(fetcher(page_url, timeout_s))
            except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
                listing_failures.append({"url": page_url, "error": f"{type(exc).__name__}: {exc}"})
            if sleep_s:
                time.sleep(sleep_s)
        for page_number, document in enumerate(documents, start=1):
            for url in product_links(document, f"{category_url}?page={page_number}"):
                if url not in seen_urls:
                    seen_urls.add(url)
                    product_urls.append(url)
        print(
            f"MONACOR LISTING: {slug} expected={expected} unique_total={len(product_urls)}",
            flush=True,
        )

    def fetch_product(url: str) -> tuple[str, bytes | None, str | None]:
        for attempt in range(retries + 1):
            try:
                return url, fetcher(url, timeout_s), None
            except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
                if attempt >= retries:
                    return url, None, f"{type(exc).__name__}: {exc}"
                time.sleep(0.25 * (attempt + 1))
        return url, None, "retry loop exhausted"

    pages: list[tuple[str, bytes]] = []
    detail_failures: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        pending = [pool.submit(fetch_product, url) for url in product_urls]
        for completed, future in enumerate(as_completed(pending), start=1):
            url, document, error = future.result()
            if document is None:
                detail_failures.append({"url": url, "error": error})
            else:
                pages.append((url, document))
            if completed % 10 == 0 or completed == len(pending):
                print(
                    f"MONACOR PROGRESS: {completed}/{len(pending)} "
                    f"detail_failures={len(detail_failures)}",
                    flush=True,
                )
            if sleep_s:
                time.sleep(sleep_s)

    presets: list[dict] = []
    rejections: list[dict] = []
    seen_models: set[str] = set()
    for url, document in sorted(pages):
        preset, reason = preset_from_product(document, url)
        if preset is None:
            rejections.append({"url": url, "reason": reason})
            continue
        model_key = str(preset["model"]).casefold()
        if model_key in seen_models:
            rejections.append({"url": url, "reason": "duplicate model"})
            continue
        presets.append(preset)
        seen_models.add(model_key)
    return {
        "schema_version": 1,
        "generated_at": utc_now(),
        "source": "Monacor public official product catalog",
        "catalog_root": CATALOG_ROOT,
        "publication_state": "staging_only",
        "category_counts": category_counts,
        "listed_unique": len(product_urls),
        "accepted": len(presets),
        "rejected": len(rejections),
        "rejections": rejections,
        "listing_failures": listing_failures,
        "detail_failures": detail_failures,
        "presets": presets,
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--sleep", type=float, default=0.15)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--retries", type=int, default=2)
    args = parser.parse_args()
    payload = harvest(
        timeout_s=args.timeout,
        sleep_s=max(0.0, args.sleep),
        workers=max(1, args.workers),
        retries=max(0, args.retries),
    )
    write_json(args.output, payload)
    print(
        f"MONACOR OFFICIAL: listed={payload['listed_unique']} "
        f"accepted={payload['accepted']} rejected={payload['rejected']} "
        f"listing_failures={len(payload['listing_failures'])} "
        f"detail_failures={len(payload['detail_failures'])} output={args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
