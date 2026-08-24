#!/usr/bin/env python3
"""Harvest complete SICA and Jensen T/S records from SICA's official store API."""

from __future__ import annotations

import argparse
import html
import json
import math
import re
import sys
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

API_ROOT = "https://sica.it/wp-json/wc/store/v1/products"
DEFAULT_OUTPUT = ROOT / "data" / "sica_official_checkpoint.json"
USER_AGENT = "LoadForgeCrawler/1.0 (official catalog research)"
NUMBER_RE = re.compile(r"[-+]?\d+(?:[.,]\d+)?")


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def fetch_json(url: str, timeout_s: float = 30.0) -> list[dict]:
    request = Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with urlopen(request, timeout=timeout_s) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, list):
        raise ValueError("official store API did not return a product list")
    return payload


def first_number(value: str) -> float | None:
    match = NUMBER_RE.search(str(value).replace("\u2212", "-"))
    if not match:
        return None
    return float(match.group(0).replace(",", "."))


def product_attributes(product: dict) -> dict[str, tuple[str, str]]:
    attributes: dict[str, tuple[str, str]] = {}
    for attribute in product.get("attributes") or []:
        label = str(attribute.get("name") or "").strip()
        terms = attribute.get("terms") or []
        values = [str(term.get("name") or "").strip() for term in terms]
        value = ", ".join(item for item in values if item)
        if label and value:
            attributes[label.casefold()] = (label, value)
    return attributes


def attribute_value(
    attributes: dict[str, tuple[str, str]], *labels: str
) -> tuple[str, str] | None:
    for label in labels:
        value = attributes.get(label.casefold())
        if value is not None:
            return value
    return None


def measurement(
    attributes: dict[str, tuple[str, str]], *labels: str, scale: float = 1.0
) -> tuple[float | None, tuple[str, str] | None]:
    evidence = attribute_value(attributes, *labels)
    if evidence is None:
        return None, None
    value = first_number(evidence[1])
    return (None if value is None else value * scale), evidence


def product_brand(product: dict) -> str | None:
    links = [str(category.get("link") or "").casefold() for category in product.get("categories") or []]
    if any("/jensen/" in link for link in links):
        return "Jensen"
    if any("/sica/" in link for link in links):
        return "SICA"
    return None


def preset_from_product(product: dict, fetched_at: str | None = None) -> tuple[dict | None, str]:
    brand = product_brand(product)
    if brand is None:
        return None, "missing official SICA/Jensen category evidence"
    model = re.sub(
        r"\s+", " ", html.unescape(str(product.get("name") or ""))
    ).strip()
    url = str(product.get("permalink") or "").strip()
    if not model or not url.startswith("https://sica.it/"):
        return None, "missing model or first-party product URL"

    attributes = product_attributes(product)
    field_specs = {
        "fs_hz": (("Fs", "Fs (LF)"), 1.0),
        "vas_l": (("Vas",), 1.0),
        "qts": (("Qts",), 1.0),
        "qms": (("Qms",), 1.0),
        "qes": (("Qes",), 1.0),
        "re_ohm": (("Re", "Re (LF)"), 1.0),
        "sd_cm2": (("Sd",), 1.0),
        "xmax_mm": (("X max",), 1.0),
        "pe_w": (("Rated Power AES", "Rated Power AES LF"), 1.0),
        "mms_g": (("Mms",), 1.0),
        "cms_mm_per_n": (("Cms",), 0.001),
        "bl_tm": (("Bxl",), 1.0),
        "le_mh": (("Le (1KHz)",), 1.0),
    }
    driver: dict[str, float] = {"le10k_mh": 0.0}
    raw_measurements: dict[str, dict] = {}
    stamp = fetched_at or utc_now()
    for field, (labels, scale) in field_specs.items():
        value, evidence = measurement(attributes, *labels, scale=scale)
        if value is None or evidence is None:
            driver[field] = 0.0
            continue
        driver[field] = value
        raw_measurements[field] = {
            "value": value,
            "raw_value": evidence[1],
            "label": evidence[0],
            "unit": {
                "fs_hz": "Hz",
                "vas_l": "l",
                "re_ohm": "\u03a9",
                "sd_cm2": "cm\u00b2",
                "xmax_mm": "mm one-way",
                "pe_w": "W AES",
                "mms_g": "g",
                "cms_mm_per_n": "mm/N",
                "bl_tm": "Tm",
                "le_mh": "mH",
            }.get(field, ""),
            "method": "official_store_api.attribute",
            "source_url": url,
            "fetched_at": stamp,
        }

    errors = crawler.validate_driver(driver)
    if errors:
        return None, "; ".join(errors)

    diameter, diameter_evidence = measurement(attributes, "Nominal Diameter")
    if diameter_evidence and "/" in diameter_evidence[1]:
        inch_side = diameter_evidence[1].split("/", 1)[1]
        diameter = first_number(inch_side)
    impedance, impedance_evidence = measurement(
        attributes, "Nominal Impedance", "Nominal Impedance LF"
    )
    published_specs: dict[str, float] = {}
    if diameter and math.isfinite(diameter):
        published_specs["nominal_diameter_in"] = diameter
    if impedance and math.isfinite(impedance):
        published_specs["nominal_impedance_ohm"] = impedance

    mechanical_specs = {
        "overall_diameter_mm": ("Overall Diameter",),
        "cutout_diameter_mm": ("Baffle Cutout Diameter",),
        "depth_mm": ("Total Depth",),
        "weight_kg": ("Net Weight",),
    }
    mechanical: dict[str, float] = {}
    for field, labels in mechanical_specs.items():
        value, _evidence = measurement(attributes, *labels)
        if value is not None:
            mechanical[field] = value

    return {
        "name": f"WEB: {brand} {model}",
        "brand": brand,
        "model": model,
        "kind": "Loudspeaker driver",
        "size_in": diameter or 0.0,
        "source": "Official manufacturer site",
        "url": url.rstrip("/"),
        "driver": driver,
        "published_specs": published_specs,
        "mechanical": mechanical,
        "raw": {**driver, **published_specs, **mechanical},
        "website_fields": {
            "title": model,
            "brand": brand,
            "model": model,
            "url": url.rstrip("/"),
            "source": "Official manufacturer site",
            "confidence": 0.99,
            "extraction_method": "official_store_api",
            "fetched_at": stamp,
            "raw_measurements": raw_measurements,
            "derived_fields": [],
            "derivations": {},
        },
    }, ""


def harvest(
    *,
    fetcher: Callable[[str, float], list[dict]] = fetch_json,
    timeout_s: float = 30.0,
    per_page: int = 100,
) -> dict:
    products: list[dict] = []
    failures: list[dict] = []
    page = 1
    while True:
        url = f"{API_ROOT}?{urlencode({'per_page': per_page, 'page': page})}"
        try:
            batch = fetcher(url, timeout_s)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
            failures.append({"url": url, "error": f"{type(exc).__name__}: {exc}"})
            break
        products.extend(batch)
        print(f"SICA API: page={page} products={len(batch)} total={len(products)}", flush=True)
        if len(batch) < per_page:
            break
        page += 1

    presets: list[dict] = []
    rejections: list[dict] = []
    seen: set[tuple[str, str]] = set()
    stamp = utc_now()
    for product in products:
        preset, reason = preset_from_product(product, stamp)
        if preset is None:
            rejections.append({
                "url": str(product.get("permalink") or ""),
                "name": str(product.get("name") or ""),
                "reason": reason,
            })
            continue
        key = (preset["brand"].casefold(), preset["model"].casefold())
        if key in seen:
            rejections.append({"url": preset["url"], "name": preset["model"], "reason": "duplicate model"})
            continue
        seen.add(key)
        presets.append(preset)

    by_brand: dict[str, int] = {}
    for preset in presets:
        by_brand[preset["brand"]] = by_brand.get(preset["brand"], 0) + 1
    return {
        "schema_version": 1,
        "generated_at": stamp,
        "source": "SICA public official WooCommerce Store API",
        "api_root": API_ROOT,
        "publication_state": "staging_only",
        "listed": len(products),
        "accepted": len(presets),
        "accepted_by_brand": by_brand,
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
    parser.add_argument("--per-page", type=int, default=100)
    args = parser.parse_args()
    payload = harvest(timeout_s=args.timeout, per_page=max(1, min(100, args.per_page)))
    write_json(args.output, payload)
    print(
        f"SICA OFFICIAL: listed={payload['listed']} accepted={payload['accepted']} "
        f"by_brand={payload['accepted_by_brand']} rejected={payload['rejected']} "
        f"failures={len(payload['failures'])} output={args.output}"
    )
    return 0 if not payload["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
