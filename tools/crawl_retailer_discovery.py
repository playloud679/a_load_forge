#!/usr/bin/env python3
"""Stage retailer model/price observations without editing the catalog."""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "catalog_proprietario.json"
OUTPUT = ROOT / "data" / "retailer_discovery_latest_report.json"
RG_SEED = "https://www.rgsound.it/subwoofer/subwoofer/"
USER_AGENT = "LoadForge-Retail-Gap-Agent/1.0 (+https://github.com/playloud679/a_load_forge)"


def normalized(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).casefold())


def parse_price_number(raw: str) -> float | None:
    value = re.sub(r"[^0-9.,]", "", raw)
    if not value:
        return None
    if "," in value and "." in value:
        decimal = "," if value.rfind(",") > value.rfind(".") else "."
        thousands = "." if decimal == "," else ","
        value = value.replace(thousands, "").replace(decimal, ".")
    elif "," in value:
        head, tail = value.rsplit(",", 1)
        value = f"{head.replace(',', '')}.{tail}" if len(tail) == 2 else value.replace(",", "")
    elif "." in value:
        head, tail = value.rsplit(".", 1)
        value = f"{head.replace('.', '')}.{tail}" if len(tail) == 2 else value.replace(".", "")
    try:
        number = float(value)
    except ValueError:
        return None
    return number if number > 0 else None


def fetch(url: str, timeout: float) -> str:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="ignore")


def _price(card: Any) -> float | None:
    whole = card.select_one(".prodotto-prezzo-intero")
    decimal = card.select_one(".prodotto-prezzo-decimale")
    if whole:
        raw_text = whole.get_text(" ", strip=True)
        if "," in raw_text:
            value = parse_price_number(raw_text)
            if value is not None:
                return value
        raw = re.sub(r"[^0-9]", "", raw_text)
        cents = re.sub(r"[^0-9]", "", decimal.get_text()) if decimal else "00"
        if raw:
            value = float(f"{raw}.{(cents + '00')[:2]}")
            return value if value > 0 else None
    price_link = card.select_one(".prodotto_mobile_linkprezzo")
    match = re.search(r"€\s*([0-9][0-9.,]*)", price_link.get_text(" ", strip=True) if price_link else "")
    if not match:
        return None
    return parse_price_number(match.group(1))


def parse_rg_page(page: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(page, "html.parser")
    observations = []
    seen: set[str] = set()
    for card in soup.select("div.prodottoLista"):
        link = card.select_one("a.prodotto_mobile_titdescr[href]")
        brand_node = card.select_one("span.marca")
        title_node = card.select_one("span.prodotto_mobile_rigo1")
        if not link or not brand_node or not title_node:
            continue
        brand = " ".join(brand_node.get_text(" ", strip=True).split())
        title = " ".join(title_node.get_text(" ", strip=True).split())
        model = re.sub(rf"^{re.escape(brand)}\s*", "", title, flags=re.I).strip()
        url = urllib.parse.urljoin(RG_SEED, str(link["href"]))
        identity = f"{normalized(brand)}:{normalized(model)}"
        if not all(identity.split(":")) or identity in seen:
            continue
        seen.add(identity)
        observations.append(
            {
                "brand": brand,
                "model": model,
                "title": title,
                "price": _price(card),
                "currency": "EUR",
                "availability": "listed",
                "url": url,
                "source": "RG Sound",
                "source_role": "model_gap_and_price_discovery_only",
            }
        )
    return observations


def existing_identities(payload: dict[str, Any]) -> set[str]:
    return {
        f"{normalized(row.get('brand'))}:{normalized(row.get('model'))}"
        for row in payload.get("presets", [])
        if isinstance(row, dict) and row.get("brand") and row.get("model")
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def crawl_rg(*, max_pages: int, sleep_seconds: float, timeout: float) -> dict[str, Any]:
    catalog_bytes = CATALOG.read_bytes()
    catalog = json.loads(catalog_bytes.decode("utf-8"))
    known = existing_identities(catalog)
    observations: dict[str, dict[str, Any]] = {}
    failures = []
    started = time.monotonic()
    next_update = started + 60.0
    for page_number in range(1, max_pages + 1):
        query = urllib.parse.urlencode(
            {"pag": page_number, "num": 20, "order_by": "n", "f_stock": 0, "f_view": "list"}
        )
        url = f"{RG_SEED}?{query}"
        try:
            for item in parse_rg_page(fetch(url, timeout)):
                key = f"{normalized(item['brand'])}:{normalized(item['model'])}"
                observations[key] = item
        except Exception as exc:
            failures.append({"page": page_number, "url": url, "error": str(exc)})
        if time.monotonic() >= next_update:
            missing = sum(key not in known for key in observations)
            print(
                f"RETAIL PROGRESS: source=RG_Sound pages={page_number}/{max_pages} "
                f"observations={len(observations)} catalog_gaps={missing} failures={len(failures)}",
                flush=True,
            )
            next_update = time.monotonic() + 60.0
        if sleep_seconds and page_number < max_pages:
            time.sleep(sleep_seconds)

    staged = []
    matched = 0
    for key, item in sorted(observations.items()):
        item = dict(item)
        item["catalog_match"] = key in known
        matched += int(item["catalog_match"])
        staged.append(item)
    if CATALOG.read_bytes() != catalog_bytes:
        raise RuntimeError("catalog changed during retailer staging crawl")
    brand_counts = Counter(item["brand"] for item in staged)
    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "publication_state": "staging_only",
        "catalog_write": False,
        "catalog_unchanged": True,
        "source": "RG Sound",
        "source_url": RG_SEED,
        "source_role": "model_gap_and_price_discovery_only",
        "summary": {
            "pages_requested": max_pages,
            "pages_failed": len(failures),
            "observations": len(staged),
            "exact_catalog_matches": matched,
            "potential_catalog_gaps": len(staged) - matched,
            "brands": len(brand_counts),
            "elapsed_seconds": round(time.monotonic() - started, 3),
        },
        "brand_counts": dict(brand_counts.most_common()),
        "failures": failures,
        "observations": staged,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("rg-sound",), default="rg-sound")
    parser.add_argument("--max-pages", type=int, default=83)
    parser.add_argument("--sleep", type=float, default=0.5)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report = crawl_rg(max_pages=args.max_pages, sleep_seconds=args.sleep, timeout=args.timeout)
    write_json(args.output, report)
    summary = report["summary"]
    print(
        f"RETAIL PASS: source=RG_Sound observations={summary['observations']} "
        f"exact_matches={summary['exact_catalog_matches']} "
        f"potential_gaps={summary['potential_catalog_gaps']} "
        f"catalog_unchanged=true"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
