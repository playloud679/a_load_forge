#!/usr/bin/env python3
"""Discover, archive and index loudspeaker PDF datasheets.

This is the PDF-first companion to ``crawl_thiele_small.py``.  Product pages
remain useful discovery documents, but the durable source is the linked PDF:
each file is stored by SHA-256, recorded in SQLite, parsed for T/S parameters
and merged into the Load Forge catalog with alias-aware technical matching.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import http.client
import json
import re
import sqlite3
import time
import threading
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
# Datasheet PDFs are fetched from manufacturer sites, never from
# loudspeakerdatabase.com; keep the catalog LSDB-free and safe to redistribute.
DEFAULT_CATALOG = ROOT / "data" / "manufacturer_drivers.json"
RECOVERABLE_FETCH_ERRORS = (
    HTTPError, URLError, TimeoutError, OSError, RuntimeError, http.client.IncompleteRead,
)


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


def discover_embedded_drawing_links(content: bytes, base_url: str) -> list[str]:
    """Find manufacturer drawing PDFs embedded as JSON assets, not anchors."""
    source = content.decode("utf-8", errors="replace").replace(r"\/", "/")
    links: list[str] = []
    for match in re.finditer(
        r"(?i)(?:https?://[^\"'\\\s]+|/?uploads/products/drawing/[^\"'\\\s]+)\.pdf",
        source,
    ):
        raw = match.group(0)
        if raw.casefold().startswith("uploads/"):
            raw = "/" + raw
        url = ts.normalize_url(raw, base_url)
        if url and url not in links:
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
    for section in ("mechanical", "published_specs"):
        values = dict(target.get(section) or {})
        for key, value in (source.get(section) or {}).items():
            if values.get(key) in (None, "") and value not in (None, ""):
                values[key] = value
                changed = True
        if values:
            target[section] = values
    target_fields = dict(target.get("website_fields") or {})
    published = dict(target_fields.get("published_measurements") or {})
    source_measurements = (
        (source.get("website_fields") or {}).get("raw_measurements") or {}
    )
    for key, value in source_measurements.items():
        if key not in published:
            published[key] = value
            changed = True
    if published:
        target_fields["published_measurements"] = published
        target["website_fields"] = target_fields
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
        elif (observation.get("website_fields") or {}).get("partial_observation"):
            # A dimensional/spec-only PDF is evidence for an existing known
            # driver, but not enough evidence to create a new acoustic record.
            continue
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

    def archived_documents(self) -> list[dict]:
        rows = self.connection.execute(
            """SELECT d.sha256, d.local_path, d.byte_count, d.title,
                      MIN(u.url), MIN(u.discovered_from), o.preset_json
               FROM documents d
               LEFT JOIN document_urls u ON u.sha256 = d.sha256
               LEFT JOIN observations o ON o.sha256 = d.sha256
               GROUP BY d.sha256, d.local_path, d.byte_count, d.title, o.preset_json
               ORDER BY d.sha256"""
        ).fetchall()
        documents = []
        for sha256, local_path, byte_count, title, url, product_url, preset_json in rows:
            try:
                existing = json.loads(preset_json) if preset_json else None
            except json.JSONDecodeError:
                existing = None
            documents.append({
                "sha256": str(sha256), "local_path": Path(str(local_path)),
                "byte_count": int(byte_count), "title": str(title or ""),
                "url": str(url or ""), "product_url": str(product_url or ""),
                "existing": existing if isinstance(existing, dict) else None,
            })
        return documents

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
    catalog_domains: tuple[str, ...] = ()
    archive_dir: Path = DEFAULT_ARCHIVE
    index_path: Path = DEFAULT_INDEX
    catalog_path: Path = DEFAULT_CATALOG
    include_patterns: tuple[re.Pattern, ...] = ()
    max_pages: int = 100
    max_pdfs: int = 500
    timeout_s: float = 30.0
    sleep_s: float = 2.0
    workers: int = 1
    per_host_delay_s: float = 0.5
    user_agent: str = ts.DEFAULT_USER_AGENT
    brand_hint: str = ""
    reparse_known: bool = False
    reparse_archive: bool = False
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


class HostThrottle:
    """Space request starts per host while allowing slow responses to overlap."""

    def __init__(self, delay_s: float):
        self.delay_s = max(0.0, delay_s)
        self._locks: dict[str, threading.Lock] = {}
        self._last_request: dict[str, float] = {}
        self._guard = threading.Lock()

    def run(self, url: str, function):
        host = (urlparse(url).hostname or "").casefold()
        with self._guard:
            lock = self._locks.setdefault(host, threading.Lock())
        with lock:
            elapsed = time.monotonic() - self._last_request.get(host, 0.0)
            if elapsed < self.delay_s:
                time.sleep(self.delay_s - elapsed)
            self._last_request[host] = time.monotonic()
        return function()


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
    catalog_pages: list[str] = []
    if config.catalog_domains and config.catalog_path.exists():
        payload = json.loads(config.catalog_path.read_text(encoding="utf-8"))
        domains = {
            value.casefold().strip().removeprefix("www.")
            for value in config.catalog_domains if value.strip()
        }
        for preset in payload.get("presets", []):
            url = ts.normalize_url(str(preset.get("url") or "").strip())
            host = (urlparse(url).hostname or "").casefold().removeprefix("www.")
            if url and any(host == domain or host.endswith(f".{domain}") for domain in domains):
                catalog_pages.append(url)
    return list(dict.fromkeys([*config.seeds, *manual_pages, *discovered, *catalog_pages]))


def catalog_identity_by_url(config: LibraryConfig) -> dict[str, dict]:
    """Return the best existing identity for exact known product URLs."""
    if not config.catalog_domains or not config.catalog_path.exists():
        return {}
    payload = json.loads(config.catalog_path.read_text(encoding="utf-8"))
    domains = {
        value.casefold().strip().removeprefix("www.")
        for value in config.catalog_domains if value.strip()
    }

    def identity_quality(preset: dict) -> tuple[int, int, int]:
        model = str(preset.get("model") or "").strip()
        boilerplate = bool(re.search(
            r"(?:professional\s+speaker\s+manufacturer|^products?(?:\s*[-|]|$))",
            model,
            re.I,
        ))
        driver_fields = sum(
            value not in (None, "", 0, 0.0) for value in (preset.get("driver") or {}).values()
        )
        return (1 if model and not boilerplate else 0, driver_fields, -len(model))

    selected: dict[str, dict] = {}
    for preset in payload.get("presets", []):
        url = ts.normalize_url(str(preset.get("url") or "").strip())
        host = (urlparse(url).hostname or "").casefold().removeprefix("www.")
        if not url or not any(host == domain or host.endswith(f".{domain}") for domain in domains):
            continue
        current = selected.get(url)
        if current is None or identity_quality(preset) > identity_quality(current):
            selected[url] = preset
    return selected


def canonicalize_pdf_preset(
    preset: dict, *, product_page: ts.PageData, product_url: str,
    pdf_url: str, sha256: str, brand_hint: str = "", catalog_identity: dict | None = None,
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
    if catalog_identity:
        product_brand = str(catalog_identity.get("brand") or product_brand).strip()
        product_model = str(catalog_identity.get("model") or product_model).strip()
        product_name = str(catalog_identity.get("name") or product_name).strip()
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
    known_identities = catalog_identity_by_url(config)
    for page_url, pdf_url in config.manual_documents:
        manual_by_page.setdefault(page_url, []).append(pdf_url)

    def parse_and_index(
        content: bytes, *, digest: str, relative: Path, pdf_url: str,
        product_url: str, page: ts.PageData,
    ) -> None:
        pdf_page = ts.parse_pdf(content)
        parsed_pdf_host = (urlparse(pdf_url).hostname or "").casefold().removeprefix("www.")
        if (
            parsed_pdf_host == "bcspeakers.com"
            and "/uploads/products/drawing/" in urlparse(pdf_url).path.casefold()
        ):
            pdf_page.embedded_measurements.extend(
                ts.bc_speakers_drawing_measurements(
                    pdf_page.text, "official B&C drawing URL",
                )
            )
        product_name, product_brand, _product_model = ts.product_metadata(
            page, product_url, config.brand_hint
        )
        preset, errors = ts.build_preset(
            pdf_page, pdf_url, "Manufacturer datasheet", product_brand, "pdf"
        )
        if preset is None:
            preset = ts.build_published_observation(
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
            catalog_identity=known_identities.get(ts.normalize_url(product_url)),
        )
        index.record_document(
            sha256=digest, local_path=relative, byte_count=len(content),
            url=pdf_url, discovered_from=product_url,
            status=("partial" if (preset.get("website_fields") or {}).get("partial_observation") else "parsed"),
            title=(preset.get("website_fields") or {}).get("title", ""),
        )
        index.record_observation(digest, preset, pdf_alias)
        observations.append(preset)
        stats.parsed += 1
        ts.log(f"indexed {preset['brand']} {preset['model']} {digest[:12]}")

    def reparse_archived_documents() -> None:
        for document in index.archived_documents():
            path = config.archive_dir / document["local_path"]
            if not path.is_file():
                stats.failures.append({"url": document["url"], "error": "archive file missing"})
                continue
            try:
                pdf_page = ts.parse_pdf(path.read_bytes())
                parsed_pdf_host = (
                    urlparse(document["url"]).hostname or ""
                ).casefold().removeprefix("www.")
                if (
                    parsed_pdf_host == "bcspeakers.com"
                    and "/uploads/products/drawing/" in urlparse(document["url"]).path.casefold()
                ):
                    pdf_page.embedded_measurements.extend(
                        ts.bc_speakers_drawing_measurements(
                            pdf_page.text, "official B&C drawing URL",
                        )
                    )
                existing = document["existing"] or {}
                brand = str(existing.get("brand") or config.brand_hint or "")
                preset, errors = ts.build_preset(
                    pdf_page, document["url"], "Manufacturer datasheet", brand, "pdf"
                )
                if preset is None:
                    preset = ts.build_published_observation(
                        pdf_page, document["url"], "Manufacturer datasheet", brand, "pdf"
                    )
                if preset is None:
                    stats.rejected += 1
                    continue
                if existing.get("brand") and existing.get("model"):
                    preset["brand"] = existing["brand"]
                    preset["model"] = existing["model"]
                    preset["name"] = f"PDF: {preset['brand']} {preset['model']}"
                fields = dict(preset.get("website_fields") or {})
                fields.update({
                    "brand": preset.get("brand"), "model": preset.get("model"),
                    "product_url": document["product_url"],
                    "pdf_sha256": document["sha256"], "url": document["url"],
                    "source": "Manufacturer datasheet",
                    # Archive reparse is enrichment-only: an unmatched PDF may
                    # retain useful indexed observations but cannot create a
                    # second catalog identity from a filename/domain fallback.
                    "partial_observation": True,
                })
                preset["website_fields"] = fields
                if not config.dry_run:
                    index.record_document(
                        sha256=document["sha256"], local_path=document["local_path"],
                        byte_count=document["byte_count"], url=document["url"],
                        discovered_from=document["product_url"],
                        status=("partial" if fields.get("partial_observation") else "parsed"),
                        title=document["title"],
                    )
                    index.record_observation(document["sha256"], preset, "")
                observations.append(preset)
                stats.parsed += 1
            except RECOVERABLE_FETCH_ERRORS as exc:
                stats.failures.append({"url": document["url"], "error": str(exc)})

    try:
        if config.reparse_archive:
            reparse_archived_documents()
            return observations, stats
        throttle = HostThrottle(config.per_host_delay_s)
        page_candidates = product_urls(config, fetcher)[:config.max_pages]
        allowed_pages: list[str] = []
        discovered_documents: list[
            tuple[str, ts.FetchResult, ts.PageData, str, bytes | None]
        ] = []
        for page_url in page_candidates:
            stats.pages += 1
            try:
                if not page_robots.allowed(page_url):
                    raise RuntimeError("product page blocked by robots.txt")
                known_direct = index.known_document(page_url) if is_pdf_url(page_url) else None
                if known_direct and (config.archive_dir / known_direct[1]).is_file():
                    identity = known_identities.get(ts.normalize_url(page_url)) or {}
                    model = str(identity.get("model") or Path(urlparse(page_url).path).stem)
                    page = ts.PageData(title=model, h1=model, text=model)
                    result = ts.FetchResult(page_url, "application/pdf", b"")
                    discovered_documents.append((page_url, result, page, page_url, None))
                    stats.pdf_links += 1
                    continue
                allowed_pages.append(page_url)
            except RECOVERABLE_FETCH_ERRORS as exc:
                stats.failures.append({"url": page_url, "error": str(exc)})

        def fetch_page(page_url: str):
            result = throttle.run(
                page_url, lambda: fetcher(page_url, config.timeout_s, config.user_agent)
            )
            direct_pdf = (
                result.content.startswith(b"%PDF")
                or result.content_type == "application/pdf"
            )
            if direct_pdf:
                identity = known_identities.get(ts.normalize_url(page_url)) or {}
                model = str(identity.get("model") or Path(urlparse(page_url).path).stem)
                page = ts.PageData(title=model, h1=model, text=model)
                links = [result.url]
            else:
                page = ts.parse_html(result.content)
                links = list(dict.fromkeys([
                    *manual_by_page.get(page_url, []),
                    *discover_pdf_links(page, result.url),
                    *discover_embedded_drawing_links(result.content, result.url),
                ]))
            return page_url, result, page, links, (result.content if direct_pdf else None)

        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, config.workers)) as executor:
            future_pages = {executor.submit(fetch_page, url): url for url in allowed_pages}
            for future in concurrent.futures.as_completed(future_pages):
                page_url = future_pages[future]
                try:
                    _original, result, page, links, direct_content = future.result()
                    stats.pdf_links += len(links)
                    discovered_documents.extend(
                        (page_url, result, page, pdf_url, direct_content) for pdf_url in links
                    )
                except RECOVERABLE_FETCH_ERRORS as exc:
                    stats.failures.append({"url": page_url, "error": str(exc)})

        pending_downloads: list[
            tuple[str, ts.FetchResult, ts.PageData, str, bytes | None]
        ] = []
        seen_pdf_urls: set[str] = set()
        for page_url, result, page, pdf_url, direct_content in discovered_documents:
            if pdf_url in seen_pdf_urls:
                continue
            seen_pdf_urls.add(pdf_url)
            try:
                known = index.known_document(pdf_url)
                if known and (config.archive_dir / known[1]).is_file():
                    stats.pdf_deduplicated += 1
                    if config.reparse_known:
                        parse_and_index(
                            (config.archive_dir / known[1]).read_bytes(),
                            digest=known[0], relative=known[1], pdf_url=pdf_url,
                            product_url=page_url, page=page,
                        )
                        continue
                    preset = index.observation(known[0])
                    if preset is not None:
                        preset, pdf_alias = canonicalize_pdf_preset(
                            preset, product_page=page, product_url=page_url,
                            pdf_url=pdf_url, sha256=known[0], brand_hint=config.brand_hint,
                            catalog_identity=known_identities.get(ts.normalize_url(page_url)),
                        )
                        index.record_observation(known[0], preset, pdf_alias)
                        observations.append(preset)
                        stats.parsed += 1
                    continue
                if len(pending_downloads) >= config.max_pdfs:
                    continue
                if not pdf_robots.allowed(pdf_url):
                    raise RuntimeError("PDF blocked by robots.txt")
                pending_downloads.append((page_url, result, page, pdf_url, direct_content))
            except RECOVERABLE_FETCH_ERRORS as exc:
                stats.failures.append({"url": pdf_url, "error": str(exc)})

        def fetch_pdf(item: tuple[str, ts.FetchResult, ts.PageData, str, bytes | None]):
            page_url, result, page, pdf_url, direct_content = item
            pdf = (
                ts.FetchResult(result.url, "application/pdf", direct_content)
                if direct_content is not None
                else throttle.run(
                    pdf_url, lambda: fetcher(pdf_url, config.timeout_s, config.user_agent)
                )
            )
            return page_url, result, page, pdf_url, pdf

        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, config.workers)) as executor:
            future_pdfs = {
                executor.submit(fetch_pdf, item): item[2] for item in pending_downloads
            }
            for future in concurrent.futures.as_completed(future_pdfs):
                pdf_url = future_pdfs[future]
                try:
                    page_url, result, page, _requested_url, pdf = future.result()
                    if not (
                        pdf.content.startswith(b"%PDF")
                        or pdf.content_type == "application/pdf"
                    ):
                        raise RuntimeError(f"not a PDF ({pdf.content_type})")
                    digest, relative = archive_pdf(config.archive_dir, pdf.content)
                    stats.pdf_downloaded += 1
                    if digest in seen_pdf_hashes:
                        stats.pdf_deduplicated += 1
                    seen_pdf_hashes.add(digest)
                    parse_and_index(
                        pdf.content, digest=digest, relative=relative,
                        pdf_url=pdf.url, product_url=page_url, page=page,
                    )
                except RECOVERABLE_FETCH_ERRORS as exc:
                    stats.failures.append({"url": pdf_url, "error": str(exc)})
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
        "--catalog-domain", action="append", default=[], metavar="HOST",
        help="Use known product URLs from --catalog for this domain; repeatable.",
    )
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
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument(
        "--per-host-delay", type=float,
        help="Seconds between request starts on one host; defaults to --sleep.",
    )
    parser.add_argument("--user-agent", default=ts.DEFAULT_USER_AGENT)
    parser.add_argument(
        "--reparse-known", action="store_true",
        help="Reparse locally archived PDFs with the current extractor.",
    )
    parser.add_argument(
        "--reparse-archive", action="store_true",
        help="Reparse every locally archived PDF without fetching product pages.",
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
    if (
        not args.seed and not args.sitemap and not manual_documents
        and not args.catalog_domain and not args.reparse_archive
    ):
        raise SystemExit("provide at least one --seed, --sitemap or --catalog-domain")
    config = LibraryConfig(
        seeds=args.seed, sitemaps=args.sitemap, manual_documents=manual_documents,
        catalog_domains=tuple(args.catalog_domain),
        archive_dir=args.archive,
        index_path=args.index, catalog_path=args.catalog,
        include_patterns=ts.compiled_patterns(args.include), max_pages=args.max_pages,
        max_pdfs=args.max_pdfs, timeout_s=args.timeout, sleep_s=args.sleep,
        workers=args.workers,
        per_host_delay_s=(args.sleep if args.per_host_delay is None else args.per_host_delay),
        user_agent=args.user_agent, brand_hint=args.brand,
        reparse_known=args.reparse_known, reparse_archive=args.reparse_archive,
        dry_run=args.dry_run,
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
