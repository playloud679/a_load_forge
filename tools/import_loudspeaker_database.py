#!/usr/bin/env python3
"""Download loudspeakerdatabase.com cards and build Load Forge presets."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import http.cookiejar
import json
import math
import re
import sys
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener


BASE_URL = "https://loudspeakerdatabase.com"
PAGE_SIZE = 40
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

RHO_AIR = 1.18
SPEED_OF_SOUND = 344.0
INTERRUPTED_EXIT = 75
COOKIE_JAR = http.cookiejar.CookieJar()
OPENER = build_opener(HTTPCookieProcessor(COOKIE_JAR))


class RateLimited(RuntimeError):
    """Raised when the site keeps returning HTTP 429 after bounded retries."""


class TimeBudgetExceeded(RuntimeError):
    """Raised when the configured scraper runtime budget is exhausted."""


class StalledPartition(RuntimeError):
    """Raised when a partition response cannot prove it reached the end."""


class WooferCardParser(HTMLParser):
    """Extract one record from each woofer card article."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.records: list[dict] = []
        self._current: dict | None = None
        self._in_h4 = False
        self._in_h4_span = False
        self._in_size_type = False
        self._h4_parts: list[str] = []
        self._h4_spans: list[str] = []
        self._h4_span_text: list[str] = []
        self._size_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        attrs_dict = {key: value or "" for key, value in attrs}
        if tag == "article" and "woofer_card" in attrs_dict.get("class", "").split():
            raw = attrs_dict.get("data-woofer")
            if raw:
                self._current = {
                    "id": attrs_dict.get("data-woofer-id", ""),
                    "raw": json.loads(html.unescape(raw)),
                }
        elif self._current is not None and tag == "h4":
            self._in_h4 = True
            self._h4_parts = []
            self._h4_spans = []
        elif self._current is not None and self._in_h4 and tag == "span":
            self._in_h4_span = True
            self._h4_span_text = []
        elif self._current is not None and tag == "td" and "size_type" in attrs_dict.get("class", "").split():
            self._in_size_type = True
            self._size_text = []

    def handle_endtag(self, tag: str):
        if self._current is None:
            return
        if tag == "h4" and self._in_h4:
            self._current["title"] = " ".join(part.strip() for part in self._h4_parts if part.strip())
            if len(self._h4_spans) >= 2:
                self._current["brand"] = self._h4_spans[0]
                self._current["model"] = " ".join(self._h4_spans[1:])
            self._in_h4 = False
        elif tag == "span" and self._in_h4_span:
            span_text = " ".join(part.strip() for part in self._h4_span_text if part.strip())
            if span_text:
                self._h4_spans.append(span_text)
            self._in_h4_span = False
        elif tag == "td" and self._in_size_type:
            self._current["size_type"] = " ".join(part.strip() for part in self._size_text if part.strip())
            self._in_size_type = False
        elif tag == "article":
            self.records.append(self._current)
            self._current = None

    def handle_data(self, data: str):
        if self._current is None:
            return
        if self._in_h4:
            self._h4_parts.append(data)
        if self._in_h4_span:
            self._h4_span_text.append(data)
        if self._in_size_type:
            self._size_text.append(data)


def log(message: str):
    print(message, flush=True)


def fetch_text(url: str, timeout_s: float, retry_delays: tuple[float, ...]) -> str:
    req = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,it;q=0.8",
            "Cache-Control": "no-cache",
        },
    )
    for attempt in range(len(retry_delays) + 1):
        try:
            with OPENER.open(req, timeout=timeout_s) as response:
                return response.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            if exc.code != 429:
                raise
            if attempt >= len(retry_delays):
                raise RateLimited(f"rate limited by loudspeakerdatabase.com: {url}") from exc
            delay = retry_delays[attempt]
            log(f"rate limited; sleeping {delay:.1f}s before retry")
            time.sleep(delay)
    raise RuntimeError("unreachable")


def parse_cards(text: str) -> list[dict]:
    parser = WooferCardParser()
    parser.feed(text)
    return parser.records


def parse_results_count(text: str) -> int | None:
    match = re.search(r'<span class="results_count">([0-9]+) results?</span>', text)
    return int(match.group(1)) if match else None


def parse_brand_values(text: str) -> list[str]:
    brand_start = text.find('data-dropdown="brand"')
    type_start = text.find('data-dropdown="type"', brand_start + 1)
    if brand_start < 0 or type_start < 0:
        return []
    section = text[brand_start:type_start]
    return re.findall(r'<span value="([^"]+)"', section)


def number(value) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result


def positive(value) -> float | None:
    result = number(value)
    return result if result is not None and result > 0 else None


def split_title(title: str) -> tuple[str, str]:
    parts = title.strip().split(maxsplit=1)
    if not parts:
        return "Unknown", "Unknown"
    if len(parts) == 1:
        return parts[0], parts[0]
    return parts[0], parts[1]


def parse_size_type(text: str) -> tuple[float | None, str]:
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*[″\"]", text)
    size = float(match.group(1)) if match else None
    kind = re.sub(r"^[0-9]+(?:\.[0-9]+)?\s*[″\"]", "", text).strip()
    return size, kind


def make_preset(card: dict) -> dict | None:
    raw = card["raw"]
    fs = positive(raw.get("fs"))
    qts = positive(raw.get("qts"))
    re_ohm = positive(raw.get("re"))
    sd = positive(raw.get("sd"))
    mmd = positive(raw.get("mmd"))
    rms = positive(raw.get("rms"))
    cms_um_per_n = positive(raw.get("cms"))
    bl = positive(raw.get("bl"))
    if None in (fs, qts, re_ohm, sd, mmd, rms, cms_um_per_n, bl):
        return None

    qms = 2.0 * math.pi * fs * (mmd / 1000.0) / rms
    if qms <= qts:
        return None

    sd_m2 = sd / 10_000.0
    cms_m_per_n = cms_um_per_n * 1e-6
    vas_l = cms_m_per_n * RHO_AIR * SPEED_OF_SOUND**2 * sd_m2**2 * 1000.0

    title = card.get("title") or "Unknown"
    brand, model = card.get("brand"), card.get("model")
    if not brand or not model:
        brand, model = split_title(title)
    size_in, kind = parse_size_type(card.get("size_type", ""))
    url = f"{BASE_URL}/{brand}/{model}".replace(" ", "%20")
    name = f"LSDB: {title}"

    return {
        "name": name,
        "brand": brand,
        "model": model,
        "size_in": size_in,
        "kind": kind,
        "url": url,
        "lsdb_id": card.get("id", ""),
        "driver": {
            "fs_hz": round(fs, 6),
            "vas_l": round(vas_l, 6),
            "qts": round(qts, 6),
            "qms": round(qms, 6),
            "re_ohm": round(re_ohm, 6),
            "sd_cm2": round(sd, 6),
            "le_mh": round(number(raw.get("le")) or 0.0, 6),
            "xmax_mm": round(number(raw.get("xmax")) or 0.0, 6),
            "pe_w": round(number(raw.get("pmax")) or 0.0, 6),
            "mms_g": round(mmd, 6),
            "cms_mm_per_n": round(cms_um_per_n / 1000.0, 6),
            "bl_tm": round(bl, 6),
        },
        "raw": raw,
    }


def card_from_preset(item: dict) -> dict:
    name = str(item.get("name") or "").removeprefix("LSDB: ").strip()
    size = item.get("size_in")
    kind = str(item.get("kind") or "").strip()
    size_type = f"{size}″ {kind}".strip() if size is not None else kind
    return {
        "id": str(item.get("lsdb_id") or ""),
        "raw": dict(item.get("raw") or {}),
        "title": name,
        "brand": str(item.get("brand") or ""),
        "model": str(item.get("model") or ""),
        "size_type": size_type,
    }


def load_seed_cards(seed_output: Path | None) -> list[dict]:
    if seed_output is None or not seed_output.exists():
        return []
    payload = json.loads(seed_output.read_text(encoding="utf-8"))
    return [card_from_preset(item) for item in payload.get("presets", [])]


def merge_cards(cards: list[dict], extra_cards: list[dict]) -> list[dict]:
    merged = list(cards)
    seen = {
        str(card.get("id") or json.dumps(card.get("raw", {}), sort_keys=True))
        for card in merged
    }
    for card in extra_cards:
        key = str(card.get("id") or json.dumps(card.get("raw", {}), sort_keys=True))
        if key not in seen:
            seen.add(key)
            merged.append(card)
    return merged


def load_checkpoint(path: Path, seed_output: Path | None = None) -> tuple[list[dict], set[str]]:
    seed_cards = load_seed_cards(seed_output)
    if not path.exists():
        return seed_cards, set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    cards = merge_cards(list(payload.get("cards", [])), seed_cards)
    return cards, set(payload.get("completed_brands", []))


def write_checkpoint(
    path: Path,
    cards: list[dict],
    completed_brands: set[str],
    deferred_brands: set[str] | None = None,
):
    payload = {
        "source": BASE_URL,
        "updated_at": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
        "cards": cards,
        "completed_brands": sorted(completed_brands),
        "deferred_brands": sorted(deferred_brands or set()),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def ensure_time_budget(started_at: float, max_runtime_s: float):
    if max_runtime_s > 0 and time.monotonic() - started_at >= max_runtime_s:
        raise TimeBudgetExceeded(f"runtime budget reached after {max_runtime_s:.0f}s")


def require_search_response(text: str, label: str, offset: int):
    stripped = text.lstrip()
    is_search_page = '<main class="search">' in text
    is_api_fragment = stripped.startswith("<article")
    if is_search_page or is_api_fragment:
        return
    title = re.search(r"<title>(.*?)</title>", text, re.S)
    title_text = re.sub(r"\s+", " ", title.group(1)).strip() if title else "unknown response"
    raise StalledPartition(f"{label} offset {offset} returned non-search page: {title_text}")


def download_partition(
    page_path: str,
    api_path: str,
    label: str,
    cards: list[dict],
    seen_ids: set[str],
    timeout_s: float,
    sleep_s: float,
    retry_delays: tuple[float, ...],
    started_at: float,
    max_runtime_s: float,
    max_cards: int | None,
) -> str:
    offset = 0
    partition_seen = 0
    expected_count: int | None = None
    while True:
        ensure_time_budget(started_at, max_runtime_s)
        if offset == 0:
            url = f"{BASE_URL}{page_path}"
        else:
            url = f"{BASE_URL}/next_page_api{api_path}/offset={offset}"
        text = fetch_text(url, timeout_s, retry_delays)
        require_search_response(text, label, offset)
        if expected_count is None:
            expected_count = parse_results_count(text)
        page_cards = parse_cards(text)
        new_cards = []
        for card in page_cards:
            key = card.get("id") or json.dumps(card.get("raw", {}), sort_keys=True)
            if key not in seen_ids:
                seen_ids.add(key)
                new_cards.append(card)
        cards.extend(new_cards)
        partition_seen += len(page_cards)
        expected = f"/{expected_count}" if expected_count is not None else ""
        log(
            f"{label:18s} offset={offset:5d} "
            f"page={len(page_cards):2d} new={len(new_cards):2d} "
            f"part={partition_seen:4d}{expected:>6s} total={len(cards):4d}"
        )
        if not page_cards:
            return "complete"
        if expected_count is not None and partition_seen >= expected_count:
            return "complete"
        if not new_cards and expected_count is None:
            return "stalled"
        if max_cards is not None and len(cards) >= max_cards:
            del cards[max_cards:]
            return "max_cards"
        offset += PAGE_SIZE
        time.sleep(sleep_s)


def download_cards(
    timeout_s: float,
    sleep_s: float,
    retry_delays: tuple[float, ...],
    max_runtime_s: float,
    max_cards: int | None,
    checkpoint_path: Path,
    seed_output: Path,
    brand_cache_path: Path,
) -> tuple[list[dict], set[str], bool]:
    started_at = time.monotonic()
    cards, completed_brands = load_checkpoint(checkpoint_path, seed_output)
    seen_ids = {
        str(card.get("id") or json.dumps(card.get("raw", {}), sort_keys=True))
        for card in cards
    }
    if cards:
        log(f"resuming from {checkpoint_path}: {len(cards)} cards, {len(completed_brands)} brands done")
    deferred_brands: set[str] = set()
    if checkpoint_path.exists():
        checkpoint_payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        deferred_brands = set(checkpoint_payload.get("deferred_brands", []))

    home = fetch_text(BASE_URL, timeout_s, retry_delays)
    brands = parse_brand_values(home)
    if brands:
        brand_cache_path.parent.mkdir(parents=True, exist_ok=True)
        brand_cache_path.write_text(json.dumps(brands, indent=2) + "\n", encoding="utf-8")
    elif brand_cache_path.exists():
        brands = json.loads(brand_cache_path.read_text(encoding="utf-8"))
    if not brands:
        status = download_partition(
            "", "", "all", cards, seen_ids, timeout_s, sleep_s, retry_delays,
            started_at, max_runtime_s, max_cards,
        )
        return cards, completed_brands, status == "complete" and max_cards is None

    log(f"found {len(brands)} brand partitions")
    ordered_brands = [
        *[brand for brand in brands if brand not in deferred_brands],
        *[brand for brand in brands if brand in deferred_brands],
    ]
    for brand in ordered_brands:
        if brand in completed_brands:
            continue
        brand_path = quote(brand, safe="")
        try:
            status = download_partition(
                f"/{brand_path}",
                f"/brand={brand_path}",
                brand,
                cards,
                seen_ids,
                timeout_s,
                sleep_s,
                retry_delays,
                started_at,
                max_runtime_s,
                max_cards,
            )
        except (RateLimited, TimeBudgetExceeded):
            write_checkpoint(checkpoint_path, cards, completed_brands, deferred_brands)
            raise
        except StalledPartition as exc:
            deferred_brands.add(brand)
            write_checkpoint(checkpoint_path, cards, completed_brands, deferred_brands)
            log(f"deferred {brand}: {exc}")
            time.sleep(sleep_s)
            continue
        if status == "stalled":
            deferred_brands.add(brand)
            write_checkpoint(checkpoint_path, cards, completed_brands, deferred_brands)
            log(f"deferred {brand}: response had no new cards before a known end")
            time.sleep(sleep_s)
            continue
        if status == "complete":
            completed_brands.add(brand)
            deferred_brands.discard(brand)
        write_checkpoint(checkpoint_path, cards, completed_brands, deferred_brands)
        if status == "max_cards":
            return cards, completed_brands, max_cards is None
        time.sleep(sleep_s)
    return cards, completed_brands, not deferred_brands


def write_dataset(cards: list[dict], output: Path, complete: bool):
    presets = [preset for card in cards if (preset := make_preset(card)) is not None]
    payload = {
        "source": BASE_URL,
        "downloaded_at": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
        "complete": complete,
        "total_cards": len(cards),
        "usable_presets": len(presets),
        "presets": presets,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    status = "complete" if complete else "partial"
    log(f"wrote {status} dataset: {len(presets)} usable presets from {len(cards)} cards to {output}")


def parse_retry_delays(raw: str) -> tuple[float, ...]:
    if not raw.strip():
        return ()
    return tuple(float(part.strip()) for part in raw.split(",") if part.strip())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="data/loudspeaker_database_drivers.json", type=Path)
    parser.add_argument("--checkpoint", default="data/loudspeaker_database_checkpoint.json", type=Path)
    parser.add_argument("--brand-cache", default="data/loudspeaker_database_brands.json", type=Path)
    parser.add_argument("--timeout", default=20.0, type=float)
    parser.add_argument("--sleep", default=5.0, type=float)
    parser.add_argument(
        "--retry-delays",
        default="5,15,30",
        help="Comma-separated seconds to wait after HTTP 429 before giving up for this run.",
    )
    parser.add_argument(
        "--max-runtime",
        default=600.0,
        type=float,
        help="Stop cleanly after this many seconds. Use 0 for no runtime budget.",
    )
    parser.add_argument("--max-cards", default=None, type=int)
    args = parser.parse_args()

    try:
        cards, _completed_brands, complete = download_cards(
            args.timeout,
            args.sleep,
            parse_retry_delays(args.retry_delays),
            args.max_runtime,
            args.max_cards,
            args.checkpoint,
            args.output,
            args.brand_cache,
        )
    except (RateLimited, TimeBudgetExceeded, StalledPartition) as exc:
        cards, completed_brands = load_checkpoint(args.checkpoint, args.output)
        write_dataset(cards, args.output, complete=False)
        log(f"stopped without blocking: {exc}")
        log(f"resume with: {Path(sys.argv[0])} --output {args.output} --checkpoint {args.checkpoint}")
        return INTERRUPTED_EXIT
    except (HTTPError, URLError, TimeoutError) as exc:
        raise SystemExit(f"download failed: {exc}") from exc
    write_dataset(cards, args.output, complete)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
