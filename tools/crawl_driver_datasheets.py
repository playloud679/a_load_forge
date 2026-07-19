#!/usr/bin/env python3
"""Discover, archive and index loudspeaker PDF datasheets.

This is the PDF-first companion to ``crawl_thiele_small.py``.  Product pages
remain useful discovery documents, but the durable source is the linked PDF:
each file is stored by SHA-256, recorded in SQLite, parsed for T/S parameters
and merged into the Load Forge catalog with alias-aware technical matching.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse

try:
    from tools import crawl_thiele_small as ts
except ModuleNotFoundError:  # Direct execution adds tools/, not the repository root.
    import crawl_thiele_small as ts

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARCHIVE = ROOT / "data" / "datasheets"
DEFAULT_INDEX = ROOT / "data" / "driver_datasheets.sqlite3"
DEFAULT_CATALOG = ROOT / "data" / "loudspeaker_database_drivers.json"


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()


def clean_identity(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).casefold())


def is_pdf_url(url: str) -> bool:
    path = urlparse(url).path.casefold()
    return path.endswith(".pdf") or "/pdf/" in path


def discover_pdf_links(page: ts.PageData, base_url: str) -> list[str]:
    links: list[str] = []
    for raw in page.links:
        url = ts.normalize_url(raw, base_url)
        if url and is_pdf_url(url) and url not in links:
            links.append(url)
    return links


def close_enough(left: float, right: float, *, rel: float, absolute: float) -> bool:
    return abs(left - right) <= max(absolute, rel * max(abs(left), abs(right)))


def technical_identity_match(left: dict, right: dict) -> bool:
    """Match aliases using stable T/S identity fields, not marketing names."""
    if clean_identity(left.get("brand")) != clean_identity(right.get("brand")):
        return False
    left_driver = left.get("driver") or {}
    right_driver = right.get("driver") or {}
    rules = {
        "fs_hz": (0.015, 0.5),
        "qts": (0.025, 0.012),
        "re_ohm": (0.02, 0.12),
        "sd_cm2": (0.015, 1.0),
    }
    for key, (relative, absolute) in rules.items():
        a = float(left_driver.get(key) or 0.0)
        b = float(right_driver.get(key) or 0.0)
        if a <= 0 or b <= 0 or not close_enough(a, b, rel=relative, absolute=absolute):
            return False
    return True


def merge_source_metadata(target: dict, source: dict) -> bool:
    changed = False
    fields = dict(target.get("website_fields") or {})
    aliases = list(fields.get("aliases") or [])
    source_model = str(source.get("model") or "").strip()
    if source_model and clean_identity(source_model) != clean_identity(target.get("model")):
        if source_model not in aliases:
            aliases.append(source_model)
            changed = True
    fields["aliases"] = aliases

    documents = list(fields.get("datasheets") or [])
    source_fields = source.get("website_fields") or {}
    document = {
        "sha256": source_fields.get("pdf_sha256"),
        "url": source.get("url"),
        "product_url": source_fields.get("product_url"),
        "fetched_at": source_fields.get("fetched_at"),
        "confidence": source_fields.get("confidence"),
    }
    if document["url"] and not any(item.get("url") == document["url"] for item in documents):
        documents.append(document)
        changed = True
    fields["datasheets"] = documents
    target["website_fields"] = fields
    return changed


def merge_driver_values(target: dict, source: dict) -> bool:
    changed = False
    driver = dict(target.get("driver") or {})
    for key, value in (source.get("driver") or {}).items():
        if driver.get(key) in (None, "", 0, 0.0) and value not in (None, "", 0, 0.0):
            driver[key] = value
            changed = True
    target["driver"] = driver
    return changed


def consolidate_presets(presets: list[dict]) -> tuple[list[dict], dict[str, int]]:
    """Collapse exact keys and strong technical aliases, preserving first row."""
    consolidated: list[dict] = []
    stats = {"added": 0, "merged_exact": 0, "merged_alias": 0}
    for source in presets:
        exact = next((
            item for item in consolidated
            if clean_identity(item.get("brand")) == clean_identity(source.get("brand"))
            and clean_identity(item.get("model")) == clean_identity(source.get("model"))
        ), None)
        target = exact
        match_kind = "merged_exact"
        if target is None:
            matches = [item for item in consolidated if technical_identity_match(item, source)]
            target = matches[0] if len(matches) == 1 else None
            match_kind = "merged_alias"
        if target is None:
            consolidated.append(source)
            stats["added"] += 1
            continue
        merge_driver_values(target, source)
        merge_source_metadata(target, source)
        stats[match_kind] += 1
    return consolidated, stats


def merge_observations(presets: list[dict], observations: list[dict]) -> tuple[list[dict], dict[str, int]]:
    """Merge only PDF-backed observations, avoiding catalog-wide fuzzy merges."""
    merged = list(presets)
    stats = {"added": 0, "updated": 0, "merged_alias": 0, "removed_duplicates": 0}
    provisional_sources = {"web crawler", "manufacturer datasheet"}
    for observation in observations:
        brand_key = clean_identity(observation.get("brand"))
        model_key = clean_identity(observation.get("model"))
        exact = [
            item for item in merged
            if clean_identity(item.get("brand")) == brand_key
            and clean_identity(item.get("model")) == model_key
        ]
        technical = [item for item in merged if technical_identity_match(item, observation)]
        curated = [
            item for item in technical
            if str(item.get("source") or "").casefold() not in provisional_sources
            and item not in exact
        ]
        if len(curated) == 1:
            target = curated[0]
            stats["merged_alias"] += 1
        elif exact:
            target = exact[0]
        elif len(technical) == 1:
            target = technical[0]
            stats["merged_alias"] += 1
        else:
            merged.append(observation)
            stats["added"] += 1
            continue

        changed = merge_driver_values(target, observation)
        changed = merge_source_metadata(target, observation) or changed
        if changed:
            stats["updated"] += 1

        if target not in exact:
            redundant = [
                item for item in exact
                if str(item.get("source") or "").casefold() in provisional_sources
            ]
            if redundant:
                redundant_ids = {id(item) for item in redundant}
                merged = [item for item in merged if id(item) not in redundant_ids]
                stats["removed_duplicates"] += len(redundant)
    return merged, stats


class DatasheetIndex:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS documents (
                sha256 TEXT PRIMARY KEY,
                local_path TEXT NOT NULL,
                byte_count INTEGER NOT NULL,
                fetched_at TEXT NOT NULL,
                parse_status TEXT NOT NULL,
                title TEXT,
                error TEXT
            );
            CREATE TABLE IF NOT EXISTS document_urls (
                url TEXT PRIMARY KEY,
                sha256 TEXT NOT NULL REFERENCES documents(sha256),
                discovered_from TEXT,
                last_seen_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS observations (
                sha256 TEXT PRIMARY KEY REFERENCES documents(sha256),
                brand TEXT,
                model TEXT,
                confidence REAL,
                preset_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS aliases (
                brand TEXT NOT NULL,
                alias TEXT NOT NULL,
                canonical_model TEXT NOT NULL,
                sha256 TEXT REFERENCES documents(sha256),
                PRIMARY KEY (brand, alias, canonical_model)
            );
        """)
        self.connection.commit()

    def known_document(self, url: str) -> tuple[str, Path, str] | None:
        row = self.connection.execute(
            """SELECT documents.sha256, documents.local_path, documents.parse_status
               FROM document_urls
               JOIN documents ON documents.sha256 = document_urls.sha256
               WHERE document_urls.url = ?""",
            (url,),
        ).fetchone()
        return (str(row[0]), Path(row[1]), str(row[2])) if row else None

    def observation(self, sha256: str) -> dict | None:
        row = self.connection.execute(
            "SELECT preset_json FROM observations WHERE sha256 = ?",
            (sha256,),
        ).fetchone()
        if not row:
            return None
        try:
            value = json.loads(str(row[0]))
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, dict) else None

    def record_document(
        self, *, sha256: str, local_path: Path, byte_count: int, url: str,
        discovered_from: str, status: str, title: str = "", error: str = "",
    ):
        now = utc_now()
        self.connection.execute(
            """INSERT INTO documents
               (sha256, local_path, byte_count, fetched_at, parse_status, title, error)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(sha256) DO UPDATE SET
                 parse_status=excluded.parse_status, title=excluded.title, error=excluded.error""",
            (sha256, str(local_path), byte_count, now, status, title, error),
        )
        self.connection.execute(
            """INSERT INTO document_urls (url, sha256, discovered_from, last_seen_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(url) DO UPDATE SET
                 sha256=excluded.sha256, discovered_from=excluded.discovered_from,
                 last_seen_at=excluded.last_seen_at""",
            (url, sha256, discovered_from, now),
        )
        self.connection.commit()

    def record_observation(self, sha256: str, preset: dict, alias: str):
        confidence = float((preset.get("website_fields") or {}).get("confidence") or 0.0)
        self.connection.execute(
            """INSERT INTO observations (sha256, brand, model, confidence, preset_json)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(sha256) DO UPDATE SET
                 brand=excluded.brand, model=excluded.model,
                 confidence=excluded.confidence, preset_json=excluded.preset_json""",
            (sha256, preset.get("brand"), preset.get("model"), confidence,
             json.dumps(preset, sort_keys=True)),
        )
        if alias and clean_identity(alias) != clean_identity(preset.get("model")):
            self.connection.execute(
                """INSERT OR IGNORE INTO aliases (brand, alias, canonical_model, sha256)
                   VALUES (?, ?, ?, ?)""",
                (preset.get("brand"), alias, preset.get("model"), sha256),
            )
        self.connection.commit()

    def close(self):
        self.connection.close()


def archive_pdf(archive_dir: Path, content: bytes) -> tuple[str, Path]:
    digest = hashlib.sha256(content).hexdigest()
    relative = Path(digest[:2]) / f"{digest}.pdf"
    destination = archive_dir / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        temporary = destination.with_suffix(".pdf.tmp")
        temporary.write_bytes(content)
        temporary.replace(destination)
    return digest, relative


@dataclass
class LibraryConfig:
    seeds: list[str]
    sitemaps: list[str]
    manual_documents: list[tuple[str, str]] = field(default_factory=list)
    archive_dir: Path = DEFAULT_ARCHIVE
    index_path: Path = DEFAULT_INDEX
    catalog_path: Path = DEFAULT_CATALOG
    include_patterns: tuple[re.Pattern, ...] = ()
    max_pages: int = 100
    max_pdfs: int = 500
    timeout_s: float = 30.0
    sleep_s: float = 2.0
    user_agent: str = ts.DEFAULT_USER_AGENT
    brand_hint: str = ""
    reparse_known: bool = False
    dry_run: bool = False


@dataclass
class LibraryStats:
    pages: int = 0
    pdf_links: int = 0
    pdf_downloaded: int = 0
    pdf_deduplicated: int = 0
    parsed: int = 0
    rejected: int = 0
    failures: list[dict] = field(default_factory=list)


def product_urls(config: LibraryConfig, fetcher=ts.fetch_resource) -> list[str]:
    allowed_domains = {
        (urlparse(url).hostname or "").casefold().removeprefix("www.")
        for url in [*config.seeds, *config.sitemaps]
    }
    crawl_config = ts.CrawlConfig(
        seeds=config.seeds,
        sitemaps=config.sitemaps,
        allowed_domains=allowed_domains,
        include_patterns=config.include_patterns,
        timeout_s=config.timeout_s,
    )
    discovered = ts.sitemap_urls(config.sitemaps, crawl_config, fetcher) if config.sitemaps else []
    manual_pages = [page_url for page_url, _pdf_url in config.manual_documents]
    return list(dict.fromkeys([*config.seeds, *manual_pages, *discovered]))


def canonicalize_pdf_preset(
    preset: dict, *, product_page: ts.PageData, product_url: str,
    pdf_url: str, sha256: str, brand_hint: str = "",
) -> tuple[dict, str]:
    product_name, product_brand, product_model = ts.product_metadata(
        product_page, product_url, brand_hint
    )
    if brand_hint:
        product_brand = brand_hint
        product_model = re.sub(
            rf"\s*[|–—]\s*{re.escape(brand_hint)}\s*$",
            "",
            product_model,
            flags=re.I,
        ).strip()
    pdf_model = str(preset.get("model") or "")
    preset["brand"] = product_brand or preset.get("brand")
    preset["model"] = product_model or preset.get("model")
    preset["name"] = f"PDF: {preset['brand']} {preset['model']}".strip()
    preset["url"] = pdf_url
    preset["source"] = "Manufacturer datasheet"
    fields = dict(preset.get("website_fields") or {})
    fields.update({
        "brand": preset["brand"],
        "model": preset["model"],
        "product_title": product_name,
        "product_url": product_url,
        "pdf_sha256": sha256,
        "url": pdf_url,
        "source": "Manufacturer datasheet",
    })
    preset["website_fields"] = fields
    return preset, pdf_model


def run_library_crawl(config: LibraryConfig, fetcher=ts.fetch_resource) -> tuple[list[dict], LibraryStats]:
    stats = LibraryStats()
    observations: list[dict] = []
    index = DatasheetIndex(config.index_path)
    page_robots = ts.RobotsPolicy(config.timeout_s, config.user_agent)
    pdf_robots = ts.RobotsPolicy(config.timeout_s, config.user_agent)
    seen_pdf_hashes: set[str] = set()
    manual_by_page: dict[str, list[str]] = {}
    for page_url, pdf_url in config.manual_documents:
        manual_by_page.setdefault(page_url, []).append(pdf_url)

    def parse_and_index(
        content: bytes, *, digest: str, relative: Path, pdf_url: str,
        product_url: str, page: ts.PageData,
    ) -> None:
        pdf_page = ts.parse_pdf(content)
        product_name, product_brand, _product_model = ts.product_metadata(
            page, product_url, config.brand_hint
        )
        preset, errors = ts.build_preset(
            pdf_page, pdf_url, "Manufacturer datasheet", product_brand, "pdf"
        )
        if preset is None:
            stats.rejected += 1
            index.record_document(
                sha256=digest, local_path=relative, byte_count=len(content),
                url=pdf_url, discovered_from=product_url, status="rejected",
                title=product_name, error="; ".join(errors),
            )
            return
        preset, pdf_alias = canonicalize_pdf_preset(
            preset, product_page=page, product_url=product_url,
            pdf_url=pdf_url, sha256=digest, brand_hint=config.brand_hint,
        )
        index.record_document(
            sha256=digest, local_path=relative, byte_count=len(content),
            url=pdf_url, discovered_from=product_url, status="parsed",
            title=(preset.get("website_fields") or {}).get("title", ""),
        )
        index.record_observation(digest, preset, pdf_alias)
        observations.append(preset)
        stats.parsed += 1
        ts.log(f"indexed {preset['brand']} {preset['model']} {digest[:12]}")

    try:
        for page_url in product_urls(config, fetcher)[:config.max_pages]:
            stats.pages += 1
            try:
                if not page_robots.allowed(page_url):
                    raise RuntimeError("product page blocked by robots.txt")
                result = fetcher(page_url, config.timeout_s, config.user_agent)
                page = ts.parse_html(result.content)
                links = list(dict.fromkeys([
                    *manual_by_page.get(page_url, []),
                    *discover_pdf_links(page, result.url),
                ]))
                stats.pdf_links += len(links)
                for pdf_url in links:
                    if stats.pdf_downloaded >= config.max_pdfs:
                        break
                    try:
                        known = index.known_document(pdf_url)
                        if known and (config.archive_dir / known[1]).is_file():
                            stats.pdf_deduplicated += 1
                            if config.reparse_known:
                                parse_and_index(
                                    (config.archive_dir / known[1]).read_bytes(),
                                    digest=known[0], relative=known[1], pdf_url=pdf_url,
                                    product_url=result.url, page=page,
                                )
                                continue
                            preset = index.observation(known[0])
                            if preset is not None:
                                preset, pdf_alias = canonicalize_pdf_preset(
                                    preset,
                                    product_page=page,
                                    product_url=result.url,
                                    pdf_url=pdf_url,
                                    sha256=known[0],
                                    brand_hint=config.brand_hint,
                                )
                                index.record_observation(known[0], preset, pdf_alias)
                                observations.append(preset)
                                stats.parsed += 1
                            continue
                        if not pdf_robots.allowed(pdf_url):
                            raise RuntimeError("PDF blocked by robots.txt")
                        pdf = fetcher(pdf_url, config.timeout_s, config.user_agent)
                        if not (pdf.content.startswith(b"%PDF") or pdf.content_type == "application/pdf"):
                            raise RuntimeError(f"not a PDF ({pdf.content_type})")
                        digest, relative = archive_pdf(config.archive_dir, pdf.content)
                        stats.pdf_downloaded += 1
                        if digest in seen_pdf_hashes:
                            stats.pdf_deduplicated += 1
                        seen_pdf_hashes.add(digest)
                        parse_and_index(
                            pdf.content, digest=digest, relative=relative,
                            pdf_url=pdf.url, product_url=result.url, page=page,
                        )
                    except (HTTPError, URLError, TimeoutError, OSError, RuntimeError) as exc:
                        stats.failures.append({"url": pdf_url, "error": str(exc)})
                    if config.sleep_s:
                        time.sleep(config.sleep_s)
            except (HTTPError, URLError, TimeoutError, OSError, RuntimeError) as exc:
                stats.failures.append({"url": page_url, "error": str(exc)})
            if config.sleep_s:
                time.sleep(config.sleep_s)
    finally:
        index.close()
    return observations, stats


def update_catalog(path: Path, observations: list[dict], dry_run: bool) -> dict[str, int]:
    payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"presets": []}
    merged, stats = merge_observations(list(payload.get("presets", [])), observations)
    payload["presets"] = merged
    payload["usable_presets"] = len(merged)
    payload["downloaded_at"] = utc_now()
    if not dry_run:
        ts.atomic_write_json(path, payload)
    return stats


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", action="append", default=[], help="Product page; repeatable.")
    parser.add_argument("--sitemap", action="append", default=[], help="Product sitemap; repeatable.")
    parser.add_argument(
        "--document", action="append", default=[], metavar="PRODUCT_URL::PDF_URL",
        help="Attach a corrected/direct PDF URL to its product page; repeatable.",
    )
    parser.add_argument("--include", action="append", help="Product-page URL regex; repeatable.")
    parser.add_argument("--brand", default="", help="Fallback/authoritative brand for this source.")
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--max-pages", type=int, default=100)
    parser.add_argument("--max-pdfs", type=int, default=500)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--sleep", type=float, default=2.0)
    parser.add_argument("--user-agent", default=ts.DEFAULT_USER_AGENT)
    parser.add_argument(
        "--reparse-known", action="store_true",
        help="Reparse locally archived PDFs with the current extractor.",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    manual_documents: list[tuple[str, str]] = []
    for value in args.document:
        page_url, separator, pdf_url = value.partition("::")
        if not separator or not ts.normalize_url(page_url) or not ts.normalize_url(pdf_url):
            raise SystemExit("--document must be PRODUCT_URL::PDF_URL")
        manual_documents.append((page_url, pdf_url))
    if not args.seed and not args.sitemap and not manual_documents:
        raise SystemExit("provide at least one --seed or --sitemap")
    config = LibraryConfig(
        seeds=args.seed, sitemaps=args.sitemap, manual_documents=manual_documents,
        archive_dir=args.archive,
        index_path=args.index, catalog_path=args.catalog,
        include_patterns=ts.compiled_patterns(args.include), max_pages=args.max_pages,
        max_pdfs=args.max_pdfs, timeout_s=args.timeout, sleep_s=args.sleep,
        user_agent=args.user_agent, brand_hint=args.brand,
        reparse_known=args.reparse_known, dry_run=args.dry_run,
    )
    observations, stats = run_library_crawl(config)
    merge_stats = update_catalog(config.catalog_path, observations, config.dry_run)
    ts.log(
        f"pages={stats.pages} pdf_links={stats.pdf_links} downloaded={stats.pdf_downloaded} "
        f"deduplicated={stats.pdf_deduplicated} parsed={stats.parsed} "
        f"rejected={stats.rejected} failures={len(stats.failures)} "
        f"catalog_added={merge_stats['added']} catalog_aliases={merge_stats['merged_alias']} "
        f"catalog_removed_duplicates={merge_stats['removed_duplicates']}"
    )
    if stats.failures:
        print(json.dumps({"failures": stats.failures[:50]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
