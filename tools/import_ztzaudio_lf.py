#!/usr/bin/env python3
"""Convert complete ZTZ Audio LF records into a Load Forge catalog tier."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


REQUIRED = (
    "fs_hz", "vas_l", "qts", "qms", "qes", "re_ohm", "sd_cm2",
    "mms_g", "bl_tm", "xmax_mm",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = json.loads(args.input.read_text(encoding="utf-8"))
    presets = []
    rejected = []
    for product in source.get("products", []):
        values = dict(product.get("normalized") or {})
        missing = [key for key in REQUIRED if values.get(key) is None]
        if missing or any(float(values[key]) <= 0.0 for key in REQUIRED):
            rejected.append({"name": product.get("name", ""), "missing": missing})
            continue
        q_identity = values["qms"] * values["qes"] / (values["qms"] + values["qes"])
        if abs(q_identity - values["qts"]) > 0.02:
            rejected.append({"name": product["name"], "reason": "Q identity mismatch"})
            continue
        driver_values = {
            key: value for key, value in values.items() if value is not None
        }
        raw = product.get("raw_parameters") or {}
        mechanical = {
            "overall_diameter_mm": _parse_first_mm(raw.get("Overall Diameter")),
            "cutout_diameter_mm": _parse_first_mm(raw.get("Bafﬂe cutout Diameter")),
            "depth_mm": _parse_first_mm(raw.get("Depth")),
            "bolt_circle_mm": _parse_first_mm(raw.get("Bolt Circle Diameter")),
            "weight_kg": _parse_first_number(raw.get("Net Weight")),
        }
        mechanical = {key: value for key, value in mechanical.items() if value is not None}
        name = f"ZTZ: {product['name']}"
        presets.append({
            "name": name,
            "model": product["name"],
            "brand": "ZTZ Audio",
            "kind": "Loudspeaker driver",
            "size_in": None,
            "source": "ZTZ Audio manufacturer catalog",
            "availability": "InStock",
            "currency": "",
            "price": 0.0,
            "price_url": "",
            "url": product["datasheet_url"] or product["url"],
            "driver": driver_values,
            "mechanical": mechanical,
            "raw": driver_values,
            "website_fields": {
                "brand": "ZTZ Audio",
                "model": product["name"],
                "category": product.get("category", ""),
                "product_url": product["url"],
                "datasheet_url": product.get("datasheet_url", ""),
                "image_url": product.get("image_url", ""),
                "raw_parameters": product.get("raw_parameters", {}),
                "confidence": 0.95,
                "extraction_method": "manufacturer_html",
                "fetched_at": source.get("retrieved_at", ""),
            },
        })
    payload = {
        "source_file": str(args.input),
        "source": "ZTZ Audio manufacturer catalog",
        "presets": presets,
        "rejected": rejected,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Imported {len(presets)} ZTZ presets; rejected {len(rejected)}")
    # Rejected source pages are expected for a commercial catalog: they remain
    # in the raw crawl and must not make the validated import fail.
    return 0


def _parse_first_mm(value) -> float | None:
    match = re.search(r"([0-9]+(?:[.,][0-9]+)?)\s*/\s*([0-9]+(?:[.,][0-9]+)?)\s*(?:in|inch)?\s*/?\s*mm", str(value), re.I)
    if not match:
        match = re.search(r"([0-9]+(?:[.,][0-9]+)?)\s*mm", str(value), re.I)
        return float(match.group(1).replace(",", ".")) if match else None
    return float(match.group(2).replace(",", "."))


def _parse_first_number(value) -> float | None:
    match = re.search(r"([0-9]+(?:[.,][0-9]+)?)", str(value))
    return float(match.group(1).replace(",", ".")) if match else None


if __name__ == "__main__":
    raise SystemExit(main())
