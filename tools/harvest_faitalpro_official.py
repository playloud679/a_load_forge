#!/usr/bin/env python3
"""Harvest current and archived FaitalPRO LF/coaxial driver variants."""

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

SITE_ROOT = "https://faitalpro.com"
LF_ROOT = f"{SITE_ROOT}/en/products/LF_Loudspeakers/"
COAX_ROOT = f"{SITE_ROOT}/en/products/Coaxial_Loudspeakers/"
ARCHIVE_ROOT = f"{SITE_ROOT}/en/products/archived_products/"
DEFAULT_OUTPUT = ROOT / "data" / "faitalpro_official_checkpoint.json"
USER_AGENT = "LoadForgeCrawler/1.0 (official catalog research)"
VARIANT_RE = re.compile(
    r"id=['\"]chkimp_(\d+)['\"].*?data-name=['\"]([^'\"]+)['\"].*?"
    r"data-impedance=['\"]([^'\"]+)['\"]",
    re.I | re.S,
)
ARCHIVE_RE = re.compile(
    r"href=['\"]product_details/LF/index\.php\?id=(\d+)['\"].*?"
    r"archive_item_prodname['\"]>([^<]+)",
    re.I | re.S,
)


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def fetch_bytes(
    url: str, timeout_s: float = 30.0, data: bytes | None = None
) -> bytes:
    request = Request(
        url,
        data=data,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json,text/html,application/xhtml+xml",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urlopen(request, timeout=timeout_s) as response:
        return response.read()


def listing_html(document: bytes) -> str:
    payload = json.loads(document.decode("utf-8"))
    if not isinstance(payload, str):
        raise ValueError("LF search endpoint did not return an HTML string")
    return payload


def variants_from_html(document: str, family: str) -> list[dict[str, str]]:
    root = LF_ROOT if family == "LF" else COAX_ROOT
    variants: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for product_id, model, impedance in VARIANT_RE.findall(document):
        if product_id in seen_ids:
            continue
        seen_ids.add(product_id)
        variants.append(
            {
                "id": product_id,
                "model": html.unescape(model).strip(),
                "impedance": html.unescape(impedance).strip(),
                "family": family,
                "url": f"{root}product_details/index.php?id={product_id}",
            }
        )
    return variants


def archive_products(document: bytes) -> list[dict[str, str]]:
    text = document.decode("utf-8", errors="replace")
    products: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for product_id, model in ARCHIVE_RE.findall(text):
        if product_id in seen_ids:
            continue
        seen_ids.add(product_id)
        products.append(
            {
                "id": product_id,
                "model": html.unescape(model).strip(),
                "impedance": "8",
                "family": "LF archive",
                "url": f"{ARCHIVE_ROOT}product_details/LF/index.php?id={product_id}",
            }
        )
    return products


def preset_from_product(document: bytes, product: dict[str, str]) -> tuple[dict | None, str]:
    page = crawler.parse_html(document)
    preset, errors = crawler.build_preset(
        page,
        product["url"],
        source_name="Official manufacturer site",
        brand_hint="FaitalPRO",
    )
    if preset is None:
        return None, "; ".join(errors) or "incomplete T/S record"
    model = product["model"]
    if product["family"] != "LF archive":
        model = f"{model} ({product['impedance']}Ω)"
    preset["brand"] = "FaitalPRO"
    preset["model"] = model
    preset["name"] = f"WEB: FaitalPRO {model}"
    preset["website_fields"]["brand"] = "FaitalPRO"
    preset["website_fields"]["model"] = model
    preset["website_fields"]["catalog_family"] = product["family"]
    preset["website_fields"]["official_product_id"] = product["id"]
    preset.setdefault("published_specs", {})["nominal_impedance_ohm"] = float(
        product["impedance"]
    )
    return preset, ""


def harvest(
    *,
    fetcher: Callable[[str, float, bytes | None], bytes] = fetch_bytes,
    timeout_s: float = 30.0,
    workers: int = 6,
    retries: int = 2,
) -> dict:
    failures: list[dict] = []
    lf_filter = urlencode(
        {
            "neodymium": 10,
            "ferrite": 20,
            "size": "All",
            "powermin": 20,
            "powermax": 3000,
            "vcmin": 15,
            "vcmax": 170,
            "fsmin": 20,
            "fsmax": 180,
            "demod": 1,
            "nodemod": 1,
        }
    ).encode("ascii")
    try:
        lf_document = fetcher(f"{LF_ROOT}search.php", timeout_s, lf_filter)
        products = variants_from_html(listing_html(lf_document), "LF")
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        failures.append({"url": f"{LF_ROOT}search.php", "error": f"{type(exc).__name__}: {exc}"})
        products = []
    for url, family, parser in (
        (COAX_ROOT, "Coaxial", lambda data: variants_from_html(data.decode("utf-8", errors="replace"), "Coaxial")),
        (ARCHIVE_ROOT, "LF archive", archive_products),
    ):
        try:
            products.extend(parser(fetcher(url, timeout_s, None)))
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            failures.append({"url": url, "family": family, "error": f"{type(exc).__name__}: {exc}"})

    unique_products: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for product in products:
        if product["url"] not in seen_urls:
            unique_products.append(product)
            seen_urls.add(product["url"])
    family_counts: dict[str, int] = {}
    for product in unique_products:
        family_counts[product["family"]] = family_counts.get(product["family"], 0) + 1
    print(f"FAITALPRO LISTING: total={len(unique_products)} families={family_counts}", flush=True)

    def fetch_product(product: dict[str, str]) -> tuple[dict[str, str], bytes | None, str | None]:
        for attempt in range(retries + 1):
            try:
                return product, fetcher(product["url"], timeout_s, None), None
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
                    f"FAITALPRO PROGRESS: {completed}/{len(pending)} "
                    f"accepted={len(presets)} rejected={len(rejections)} failures={len(failures)}",
                    flush=True,
                )

    presets.sort(key=lambda item: (str(item["model"]).casefold(), str(item["url"])))
    return {
        "schema_version": 1,
        "generated_at": utc_now(),
        "source": "FaitalPRO public official product catalog and archive",
        "catalog_root": f"{SITE_ROOT}/en/products/",
        "publication_state": "staging_only",
        "listed": len(unique_products),
        "listed_by_family": family_counts,
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
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--retries", type=int, default=2)
    args = parser.parse_args()
    payload = harvest(timeout_s=args.timeout, workers=max(1, args.workers), retries=max(0, args.retries))
    write_json(args.output, payload)
    print(
        f"FAITALPRO OFFICIAL: listed={payload['listed']} accepted={payload['accepted']} "
        f"rejected={payload['rejected']} failures={len(payload['failures'])} output={args.output}"
    )
    return 0 if not payload["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
