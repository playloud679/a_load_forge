#!/usr/bin/env python3
"""Download and normalize the ZTZ Audio ferrite LF loudspeaker catalog.

The site is a WordPress catalog with one product table per detail page.  This
tool keeps the original labels and URLs alongside normalized T/S values so a
later importer can reject incomplete records without losing the source data.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from hashlib import sha1
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup


CATEGORY_URL = "https://www.ztzaudio.com/lf-loudspeakers---ferrite.html"
USER_AGENT = "LoadForge-ZTZ-catalog-import/1.0"


def fetch(url: str) -> bytes:
    try:
        result = subprocess.run(
            [
                "curl", "-fsSL", "--max-time", "40", "--retry", "2",
                "--retry-delay", "1", "-A", USER_AGENT, url,
            ],
            check=True,
            capture_output=True,
        )
        return result.stdout
    except (OSError, subprocess.CalledProcessError):
        pass
    last_error: Exception | None = None
    for attempt in range(5):
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=40) as response:  # noqa: S310 - explicit catalog URL
                return response.read()
        except (OSError, URLError) as exc:
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


def text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def parse_number(value: str, patterns: tuple[str, ...]) -> float | None:
    for pattern in patterns:
        match = re.search(pattern, value, flags=re.IGNORECASE)
        if match:
            try:
                return float(match.group(1).replace(",", "."))
            except ValueError:
                return None
    return None


def parse_category_page(url: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(fetch(url), "html.parser")
    rows: list[dict[str, str]] = []
    for card in soup.select(".products-list-right-div"):
        anchor = next(
            (
                candidate
                for candidate in card.find_all("a", href=True)
                if text(candidate.get_text(" "))
            ),
            None,
        )
        if anchor is None:
            continue
        name = text(anchor.get_text(" "))
        if not name:
            continue
        rows.append({
            "name": name,
            "url": urljoin(url, str(anchor["href"])),
            "image_url": urljoin(url, str(card.find("img").get("src", "")))
            if card.find("img") else "",
        })
    return rows


def parse_product(url: str, category_name: str) -> dict:
    soup = BeautifulSoup(fetch(url), "html.parser")
    title = text((soup.find("h1") or soup.title).get_text(" "))
    raw: dict[str, str] = {}
    for row in soup.select(".tab-content-body-div.tables tr"):
        cells = [text(cell.get_text(" ")) for cell in row.find_all(["td", "th"])]
        cells = [cell for cell in cells if cell]
        if len(cells) < 2:
            continue
        label = cells[-2] if len(cells) >= 3 else cells[0]
        value = cells[-1]
        if label.lower() == value.lower():
            continue
        raw[label] = value

    def find(*labels: str) -> str:
        folded_labels = tuple(item.casefold() for item in labels)
        for label, value in raw.items():
            folded = label.casefold()
            if any(
                folded == item
                or folded.startswith(item + " ")
                or (len(item) > 2 and item in folded)
                for item in folded_labels
            ):
                return value
        return ""

    fs_value = find("FS Hz", "Resonance(natural) Frequency")
    vas_value = find("Vas")
    mms_value = find("MMS", "Mms")
    sd_value = find("Sd")
    re_value = find("RE Ohms", "DC Resistance")
    bl_value = find("BL T", "BL")
    xmax_value = find("Xmax")
    rms_value = find("RMS Power", "RMS")
    le_value = find("Le", "Voice Coil Inductance")
    normalized = {
        "fs_hz": parse_number(fs_value, (r"([0-9]+(?:[.,][0-9]+)?)",)),
        "vas_l": parse_number(vas_value, (r"([0-9]+(?:[.,][0-9]+)?)\s*(?:dm3|dm³|l|litre)", r"([0-9]+(?:[.,][0-9]+)?)")),
        "mms_g": parse_number(mms_value, (r"([0-9]+(?:[.,][0-9]+)?)",)),
        "sd_cm2": parse_number(sd_value, (r"([0-9]+(?:[.,][0-9]+)?)",)),
        "re_ohm": parse_number(re_value, (r"([0-9]+(?:[.,][0-9]+)?)",)),
        "qms": parse_number(find("Qms"), (r"([0-9]+(?:[.,][0-9]+)?)",)),
        "qes": parse_number(find("Qes"), (r"([0-9]+(?:[.,][0-9]+)?)",)),
        "qts": parse_number(find("Qts"), (r"([0-9]+(?:[.,][0-9]+)?)",)),
        "bl_tm": parse_number(bl_value, (r"([0-9]+(?:[.,][0-9]+)?)",)),
        "xmax_mm": parse_number(xmax_value, (r"([0-9]+(?:[.,][0-9]+)?)",)),
        "pe_w": parse_number(rms_value, (r"([0-9]+(?:[.,][0-9]+)?)",)),
        "le_mh": parse_number(le_value, (r"([0-9]+(?:[.,][0-9]+)?)",)),
    }


def save_asset(url: str, directory: Path, stem: str, suffix: str) -> str:
    if not url:
        return ""
    directory.mkdir(parents=True, exist_ok=True)
    digest = sha1(url.encode("utf-8"), usedforsecurity=False).hexdigest()[:8]
    path = directory / f"{stem}-{digest}{suffix}"
    if not path.exists():
        path.write_bytes(fetch(url))
    return str(path)
    vas_raw = vas_value.casefold()
    if "ft" in vas_raw and normalized["vas_l"] is not None:
        normalized["vas_l"] *= 28.3168466
    download = soup.select_one("[data-download-url]")
    image = soup.select_one("meta[property='og:image']")
    return {
        "name": title,
        "url": url,
        "category": category_name,
        "datasheet_url": str(download.get("data-download-url", "")) if download else "",
        "image_url": str(image.get("content", "")) if image else "",
        "normalized": normalized,
        "raw_parameters": raw,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--assets-dir", type=Path)
    parser.add_argument("--delay", type=float, default=0.25)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    cards: dict[str, dict[str, str]] = {}
    for page in range(1, 11):
        page_url = CATEGORY_URL if page == 1 else f"{CATEGORY_URL}?paged={page}"
        for card in parse_category_page(page_url):
            cards[card["url"]] = card
        time.sleep(max(args.delay, 0.0))

    existing_products: dict[str, dict] = {}
    if args.output.exists() and not args.refresh:
        try:
            previous = json.loads(args.output.read_text(encoding="utf-8"))
            existing_products = {
                str(item["url"]): item for item in previous.get("products", [])
                if item.get("url")
            }
        except (OSError, json.JSONDecodeError, TypeError):
            existing_products = {}
    products: list[dict] = list(existing_products.values())
    failures: list[dict[str, str]] = []
    for index, card in enumerate(cards.values(), start=1):
        if card["url"] in existing_products:
            continue
        try:
            product = parse_product(card["url"], "LF Loudspeakers - Ferrite")
            product["listing_name"] = card["name"]
            products.append(product)
        except Exception as exc:  # keep one broken page from losing the catalog
            failures.append({"url": card["url"], "error": repr(exc)})
        checkpoint = {
            "source": "ZTZ Audio",
            "source_category": CATEGORY_URL,
            "retrieved_at": datetime.now(UTC).isoformat(),
            "product_count": len(products),
            "failures": failures,
            "products": products,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(checkpoint, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"{index}/{len(cards)} {card['name']}")
        time.sleep(max(args.delay, 0.0))

    payload = {
        "source": "ZTZ Audio",
        "source_category": CATEGORY_URL,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "product_count": len(products),
        "failures": failures,
        "products": products,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.assets_dir:
        for product in products:
            stem = re.sub(r"[^A-Za-z0-9._-]+", "_", product["name"]).strip("_")
            try:
                product["datasheet_local"] = save_asset(
                    product.get("datasheet_url", ""), args.assets_dir, stem, ".pdf")
                product["image_local"] = save_asset(
                    product.get("image_url", ""), args.assets_dir, stem, ".jpg")
            except (OSError, URLError, subprocess.CalledProcessError) as exc:
                product["asset_error"] = repr(exc)
        payload["products"] = products
        args.output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(products)} products to {args.output}; failures={len(failures)}")
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
