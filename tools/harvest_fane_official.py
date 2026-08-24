#!/usr/bin/env python3
"""Harvest current and archived Fane cone-driver product pages."""

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
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import crawl_thiele_small as crawler

SITE_ROOT = "https://www.fane-international.com"
LISTINGS = (
    ("current products", f"{SITE_ROOT}/category/426/All-Products"),
    ("archived LF", f"{SITE_ROOT}/category/415/Low-Frequency-Driver-Archive"),
    ("archived full range", f"{SITE_ROOT}/category/417/Full-Range-Driver-Archive"),
)
DEFAULT_OUTPUT = ROOT / "data" / "fane_official_checkpoint.json"
USER_AGENT = "LoadForgeCrawler/1.0 (official catalog research)"
PRODUCT_LINK_RE = re.compile(r'href=["\'](/view-product/[^"\'?#]+)["\']', re.I)
POSTBACK_RE = re.compile(
    r"__doPostBack\(&#39;(rptPaging2\$ctl\d+\$pPage)&#39;,&#39;&#39;\)", re.I
)
HIDDEN_INPUT_RE = re.compile(r"<input\b[^>]*\btype=[\"']hidden[\"'][^>]*>", re.I)
ATTRIBUTE_RE = re.compile(r"([:\w-]+)=[\"']([^\"']*)[\"']", re.I)


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def fetch_bytes(url: str, timeout_s: float = 30.0, data: bytes | None = None) -> bytes:
    request = Request(
        url,
        data=data,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urlopen(request, timeout=timeout_s) as response:
        return response.read()


def products_from_listing(document: bytes, family: str) -> list[dict[str, str]]:
    text = document.decode("utf-8", errors="replace")
    products = []
    seen: set[str] = set()
    for path in PRODUCT_LINK_RE.findall(text):
        path = html.unescape(path).rstrip("/")
        url = f"{SITE_ROOT}{path}"
        if url in seen:
            continue
        seen.add(url)
        products.append({"url": url, "model": path.rsplit("/", 1)[-1], "family": family})
    return products


def postback_targets(document: bytes) -> list[str]:
    text = document.decode("utf-8", errors="replace")
    return list(dict.fromkeys(html.unescape(value) for value in POSTBACK_RE.findall(text)))


def postback_data(document: bytes, target: str) -> bytes:
    text = document.decode("utf-8", errors="replace")
    fields: dict[str, str] = {}
    for tag in HIDDEN_INPUT_RE.findall(text):
        attributes = {
            key.casefold(): html.unescape(value)
            for key, value in ATTRIBUTE_RE.findall(tag)
        }
        name = attributes.get("name")
        if name:
            fields[name] = attributes.get("value", "")
    fields["__EVENTTARGET"] = target
    fields["__EVENTARGUMENT"] = ""
    return urlencode(fields).encode("ascii")


def listing_pages(
    url: str,
    *,
    fetcher: Callable[[str, float, bytes | None], bytes] = fetch_bytes,
    timeout_s: float = 30.0,
) -> list[bytes]:
    first = fetcher(url, timeout_s, None)
    pages = [first]
    for target in postback_targets(first)[1:]:
        pages.append(fetcher(url, timeout_s, postback_data(first, target)))
    return pages


def preset_from_product(document: bytes, product: dict[str, str]) -> tuple[dict | None, str]:
    page = crawler.parse_html(document)
    preset, errors = crawler.build_preset(
        page,
        product["url"],
        source_name="Official manufacturer site",
        brand_hint="Fane",
    )
    if preset is None:
        return None, "; ".join(errors) or "incomplete T/S record"
    preset["brand"] = "Fane"
    preset["name"] = f"WEB: Fane {preset['model']}"
    preset["website_fields"]["brand"] = "Fane"
    preset["website_fields"]["catalog_family"] = product["family"]
    return preset, ""


def harvest(
    *,
    fetcher: Callable[[str, float, bytes | None], bytes] = fetch_bytes,
    timeout_s: float = 30.0,
    workers: int = 8,
    retries: int = 2,
) -> dict:
    products: list[dict[str, str]] = []
    failures: list[dict] = []
    listing_counts: dict[str, int] = {}
    listing_pages_seen: dict[str, int] = {}
    for family, url in LISTINGS:
        try:
            pages = listing_pages(url, fetcher=fetcher, timeout_s=timeout_s)
            family_products: list[dict[str, str]] = []
            seen_family: set[str] = set()
            for document in pages:
                for product in products_from_listing(document, family):
                    if product["url"] not in seen_family:
                        family_products.append(product)
                        seen_family.add(product["url"])
            products.extend(family_products)
            listing_counts[family] = len(family_products)
            listing_pages_seen[family] = len(pages)
            print(
                f"FANE LISTING: family={family} pages={len(pages)} products={len(family_products)}",
                flush=True,
            )
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
                return product, fetcher(product["url"], timeout_s, None), None
            except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
                if attempt >= retries:
                    return product, None, f"{type(exc).__name__}: {exc}"
                time.sleep(0.35 * (attempt + 1))
        return product, None, "retry loop exhausted"

    staged: list[dict] = []
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
                    staged.append(preset)
            if completed % 10 == 0 or completed == len(pending):
                print(
                    f"FANE PROGRESS: {completed}/{len(pending)} accepted={len(staged)} "
                    f"rejected={len(rejections)} failures={len(failures)}",
                    flush=True,
                )

    staged.sort(key=lambda item: (str(item["model"]).casefold(), str(item["url"])))
    return {
        "schema_version": 1,
        "generated_at": utc_now(),
        "source": "Fane public official current catalog and archive",
        "catalog_root": f"{SITE_ROOT}/products",
        "publication_state": "staging_only",
        "listed": len(unique_products),
        "listed_by_family": listing_counts,
        "listing_pages_by_family": listing_pages_seen,
        "accepted": len(staged),
        "rejected": len(rejections),
        "rejections": rejections,
        "failures": failures,
        "presets": staged,
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
        f"FANE OFFICIAL: listed={payload['listed']} accepted={payload['accepted']} "
        f"rejected={payload['rejected']} failures={len(payload['failures'])} output={args.output}"
    )
    return 0 if not payload["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
