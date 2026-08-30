#!/usr/bin/env python3
"""Crawl passive radiators from SoundImports.eu and populate presets."""

from __future__ import annotations

import argparse
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
PRESETS_PATH = ROOT / "src" / "presets.py"

BASE_URL = "https://www.soundimports.eu/it/componenti-audio/woofers/radiatore-passivo/"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}


def clean_val(v: str | None) -> float | None:
    if not v:
        return None
    v = v.replace(",", ".").strip().rstrip(".")
    try:
        return float(v)
    except ValueError:
        return None


def fetch_all_product_urls() -> list[str]:
    urls: list[str] = []
    page = 1
    while True:
        page_url = BASE_URL if page == 1 else f"{BASE_URL}page{page}.html"
        try:
            req = urllib.request.Request(page_url, headers=HEADERS)
            html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8")
        except Exception as e:
            print(f"Finished or error at page {page}: {e}")
            break

        soup = BeautifulSoup(html, "html.parser")
        page_links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("https://www.soundimports.eu/it/") and href.endswith(".html"):
                if not any(
                    x in href
                    for x in [
                        "/page",
                        "/componenti-audio/",
                        "/carrello",
                        "/account",
                        "/service",
                        "/contact",
                        "/blog",
                        "/nuovi-prodotti/",
                    ]
                ):
                    page_links.append(href)

        page_links = sorted(list(set(page_links)))
        new_links = [u for u in page_links if u not in urls]
        if not new_links:
            break
        urls.extend(new_links)
        page += 1

    return urls


def extract_specs_from_desc(text: str) -> dict[str, float | None]:
    specs: dict[str, float | None] = {}
    m = re.search(r"(?:Fs|Fp|Free [Aa]ir [Rr]esonance|Resonance [Ff]requency)[^\d]*([\d.,]+)\s*Hz", text)
    if m:
        specs["fp_hz"] = clean_val(m.group(1))
    m = re.search(r"(?:Qms|Qmp|Mechanical Q)[^\d]*([\d.,]+)", text)
    if m:
        specs["qmp"] = clean_val(m.group(1))
    m = re.search(r"(?:Mms|Mmp|Moving [Mm]ass)[^\d]*([\d.,]+)\s*g", text)
    if m:
        specs["mmp_g"] = clean_val(m.group(1))
    m = re.search(r"(?:Sd|Sp|Piston [Aa]rea|Effective [Pp]iston [Aa]rea)[^\d]*([\d.,]+)\s*(?:cm[²2]|sq\.?\s*cm)", text)
    if m:
        specs["sp_cm2"] = clean_val(m.group(1))
    m = re.search(r"(?:Xmax|Linear [Ee]xcursion|Peak-to-peak excursion)[^\d]*([\d.,]+)\s*mm", text)
    if m:
        specs["xmax_mm"] = clean_val(m.group(1))
    return specs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Do not write to src/presets.py")
    args = parser.parse_args()

    print("Fetching SoundImports passive radiator catalog...")
    urls = fetch_all_product_urls()
    print(f"Found {len(urls)} passive radiators on SoundImports.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
