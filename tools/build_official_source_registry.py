#!/usr/bin/env python3
"""Build a manufacturer-first crawl registry from catalog provenance.

The command is deliberately read-only with respect to the proprietary catalog.
It inventories every catalog brand, ranks first-party domains already present in
its provenance, excludes retailers/aggregators, and emits both an audit report
and a policy-valid crawler-agent manifest.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = ROOT / "data" / "catalog_proprietario.json"
DEFAULT_REGISTRY = ROOT / "data" / "official_source_registry.json"
DEFAULT_MANIFEST = ROOT / "services" / "crawler_agent" / "manifest.loadforge.json"
DEFAULT_DISCOVERY_CACHE = ROOT / "data" / "official_source_discovery_cache.json"
DEFAULT_SOURCE_SEEDS = ROOT / "services" / "crawler_agent" / "official_source_seeds.json"

# These sources remain useful for price discovery, but must never establish a
# manufacturer identity or become a first-party technical source.
NON_MANUFACTURER_DOMAINS = frozenset(
    {
        "audioxpress.com",
        "audiophonics.fr",
        "audioheritage.org",
        "bluearan.co.uk",
        "cinergyaudio.com",
        "diyaudio.com",
        "droppinhzcaraudio.com",
        "en.toutlehautparleur.com",
        "finiziopowerteam.it",
        "ebay.com",
        "haut-parleurs.fr",
        "lautsprechershop.de",
        "leanaudio.co.uk",
        "loudspeakerdatabase.com",
        "madisoundspeakerstore.com",
        "masori.de",
        "parts-express.com",
        "rgsound.it",
        "schema.org",
        "solen.ca",
        "soundautoconcept.com",
        "soundimports.eu",
        "speakerboxlite.com",
        "stereonet.com",
        "thomann.de",
        "topservicepro.it",
        "vituixcad.com",
        "willys-hifi.com",
    }
)
OFFICIAL_SOURCE_RE = re.compile(
    r"\b(manufacturer|official|factory|datasheet|data sheet|crawl(?:er)?)\b", re.I
)
URL_RE = re.compile(r"^https?://", re.I)
PRODUCT_RE = re.compile(
    r"/(product|products|speaker|speakers|woofer|woofers|subwoofer|subwoofers|"
    r"driver|drivers|catalog|archive|download|uploads?)/",
    re.I,
)
INCLUDE_PATTERN = r"/(product|products|speaker|speakers|woofer|woofers|subwoofer|subwoofers|driver|drivers|catalog|archive|download|uploads?)/"
EXCLUDE_PATTERN = r"/(cart|checkout|account|login|privacy|terms|dealer|accessor|amplifier|cable)/"
NON_BRAND_LABELS = frozenset(
    {"coast buyouts", "custom", "discontinued", "down4sound", "factory buyouts"}
)


def normalized(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).casefold())


def clean_domain(value: object) -> str:
    host = (urlparse(str(value)).hostname or "").casefold().removeprefix("www.")
    return host.rstrip(".")


def is_non_manufacturer(domain: str) -> bool:
    return any(domain == blocked or domain.endswith(f".{blocked}") for blocked in NON_MANUFACTURER_DOMAINS)


def walk_urls(value: object, path: str = "") -> Iterable[tuple[str, str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield from walk_urls(child, f"{path}.{key}" if path else str(key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk_urls(child, f"{path}[{index}]")
    elif isinstance(value, str) and URL_RE.match(value.strip()):
        yield path, value.strip()


@dataclass
class DomainEvidence:
    urls: set[str] = field(default_factory=set)
    records: set[str] = field(default_factory=set)
    official_votes: int = 0
    product_urls: int = 0
    homepage_urls: int = 0
    preferred_seeds: set[str] = field(default_factory=set)
    verification_notes: set[str] = field(default_factory=set)


def _domain_score(brand: str, domain: str, evidence: DomainEvidence) -> tuple[float, list[str]]:
    brand_key = normalized(brand)
    domain_key = normalized(domain.split(".", 1)[0])
    reasons: list[str] = []
    score = 0.20
    if brand_key and (brand_key in normalized(domain) or domain_key in brand_key):
        score += 0.28
        reasons.append("brand/domain name match")
    if evidence.official_votes:
        score += 0.32
        reasons.append(f"{evidence.official_votes} first-party provenance votes")
    if evidence.product_urls:
        score += min(0.12, 0.03 + 0.01 * evidence.product_urls)
        reasons.append(f"{evidence.product_urls} product/datasheet URLs")
    if evidence.homepage_urls:
        score += 0.08
        reasons.append("catalog homepage evidence")
    if len(evidence.records) >= 3:
        score += min(0.08, len(evidence.records) / 200.0)
        reasons.append(f"evidence across {len(evidence.records)} records")
    reasons.extend(sorted(evidence.verification_notes))
    return min(score, 1.0), reasons


def _target_id(brand: str, used: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", brand.casefold()).strip("-") or "brand"
    base = f"{base[:54]}-official"
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base[:58]}-{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def _initialism(brand: str) -> str:
    return "".join(word[0] for word in re.findall(r"[a-z0-9]+", brand.casefold()) if word)


def collapse_aliases(entries: list[dict[str, Any]]) -> None:
    """Collapse duplicate domains and obvious catalog aliases into one crawl."""
    by_domain: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        if entry["status"] == "ready":
            by_domain[str(entry["official_domain"])].append(entry)
    for domain, group in by_domain.items():
        if len(group) < 2:
            continue
        domain_key = normalized(domain)
        canonical = max(
            group,
            key=lambda entry: (
                normalized(entry["brand"]) in domain_key,
                int(entry.get("catalog_records", 0)),
                -len(str(entry["brand"])),
            ),
        )
        for entry in group:
            if entry is canonical:
                continue
            entry["status"] = "alias"
            entry["alias_of"] = canonical["brand"]
            entry["crawl_target_id"] = canonical["target_id"]

    canonical_entries = [entry for entry in entries if entry["status"] == "ready"]
    for entry in entries:
        if entry["status"] != "needs_discovery":
            continue
        key = normalized(entry["brand"])
        matches = []
        for canonical in canonical_entries:
            canonical_key = normalized(canonical["brand"])
            is_name_alias = (
                len(canonical_key) >= 4
                and (canonical_key in key or key in canonical_key)
            )
            is_initialism = len(key) >= 3 and key == _initialism(str(canonical["brand"]))
            if is_name_alias or is_initialism:
                matches.append(canonical)
        if not matches:
            continue
        canonical = max(
            matches,
            key=lambda candidate: (
                len(normalized(candidate["brand"])),
                int(candidate.get("catalog_records", 0)),
            ),
        )
        entry.update(
            {
                "status": "alias",
                "alias_of": canonical["brand"],
                "official_domain": canonical["official_domain"],
                "confidence": min(float(canonical["confidence"]), 0.9),
                "crawl_target_id": canonical["target_id"],
                "evidence": ["automatic catalog brand-alias resolution"],
            }
        )


def apply_declared_aliases(
    entries: list[dict[str, Any]], aliases: Iterable[dict[str, Any]]
) -> None:
    """Apply reviewed catalog-label aliases after automatic domain collapse."""
    by_brand = {normalized(entry["brand"]): entry for entry in entries}
    for declaration in aliases:
        if not isinstance(declaration, dict):
            continue
        alias = by_brand.get(normalized(declaration.get("brand")))
        canonical = by_brand.get(normalized(declaration.get("canonical_brand")))
        if alias is None or canonical is None or alias is canonical:
            continue
        seen: set[str] = set()
        while canonical.get("status") == "alias" and canonical.get("alias_of"):
            canonical_key = normalized(canonical["brand"])
            if canonical_key in seen:
                break
            seen.add(canonical_key)
            next_canonical = by_brand.get(normalized(canonical["alias_of"]))
            if next_canonical is None:
                break
            canonical = next_canonical
        if canonical.get("status") != "ready":
            continue
        note = str(declaration.get("evidence") or "reviewed catalog brand alias")
        alias.update(
            {
                "status": "alias",
                "alias_of": canonical["brand"],
                "official_domain": canonical["official_domain"],
                "confidence": min(float(canonical["confidence"]), 0.95),
                "crawl_target_id": canonical["target_id"],
                "evidence": [note],
            }
        )


def build_registry(
    payload: dict[str, Any],
    discoveries: dict[str, Any] | None = None,
    source_seeds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rows = payload.get("presets")
    if not isinstance(rows, list):
        raise ValueError("catalog must contain a presets list")

    brands: dict[str, str] = {}
    evidence: dict[str, dict[str, DomainEvidence]] = defaultdict(
        lambda: defaultdict(DomainEvidence)
    )
    rejected: dict[str, set[str]] = defaultdict(set)
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or not str(row.get("brand") or "").strip():
            continue
        brand = str(row["brand"]).strip()
        brand_key = normalized(brand)
        brands.setdefault(brand_key, brand)
        record_key = f"{index}:{normalized(row.get('model') or row.get('name'))}"
        source_is_official = bool(OFFICIAL_SOURCE_RE.search(str(row.get("source") or "")))
        for path, url in walk_urls(row):
            domain = clean_domain(url)
            if not domain:
                continue
            if is_non_manufacturer(domain):
                rejected[brand_key].add(domain)
                continue
            item = evidence[brand_key][domain]
            item.urls.add(url)
            item.records.add(record_key)
            path_key = path.casefold()
            if source_is_official and path_key in {"url", "website_fields.product_url"}:
                item.official_votes += 1
            if any(token in path_key for token in ("datasheet", "published_measurements", "source_url")):
                item.official_votes += 1
            parsed = urlparse(url)
            if PRODUCT_RE.search(parsed.path + "/") or parsed.path.casefold().endswith(".pdf"):
                item.product_urls += 1
            if parsed.path in {"", "/"}:
                item.homepage_urls += 1

    for discovery in (discoveries or {}).get("discoveries", []):
        if not isinstance(discovery, dict) or discovery.get("status") != "verified":
            continue
        brand = str(discovery.get("brand") or "").strip()
        url = str(discovery.get("url") or "").strip()
        domain = clean_domain(url)
        brand_key = normalized(brand)
        if brand_key not in brands or not domain or is_non_manufacturer(domain):
            continue
        item = evidence[brand_key][domain]
        item.urls.add(url)
        item.records.add(f"discovery:{brand_key}")
        item.official_votes += 3
        item.homepage_urls += 1
        item.preferred_seeds.add(url)
        item.verification_notes.add("automatic domain discovery verified")

    for source in (source_seeds or {}).get("verified_sources", []):
        if not isinstance(source, dict):
            continue
        brand = str(source.get("brand") or "").strip()
        url = str(source.get("url") or "").strip()
        domain = clean_domain(url)
        brand_key = normalized(brand)
        if (
            brand_key not in brands
            or not URL_RE.match(url)
            or not domain
            or is_non_manufacturer(domain)
        ):
            continue
        item = evidence[brand_key][domain]
        item.urls.add(url)
        item.records.add(f"reviewed-source:{brand_key}")
        item.official_votes += 4
        item.preferred_seeds.add(url)
        path = urlparse(url).path
        if PRODUCT_RE.search(path + "/") or path.casefold().endswith(".pdf"):
            item.product_urls += 1
        if path in {"", "/"}:
            item.homepage_urls += 1
        note = str(source.get("evidence") or "reviewed official manufacturer source")
        item.verification_notes.add(note)

    entries: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    for brand_key, brand in sorted(brands.items(), key=lambda item: item[1].casefold()):
        ranked = []
        for domain, item in evidence.get(brand_key, {}).items():
            confidence, reasons = _domain_score(brand, domain, item)
            ranked.append((confidence, len(item.records), domain, reasons, item))
        ranked.sort(
            key=lambda item: (
                -bool(item[4].verification_notes),
                -item[0],
                -item[1],
                item[2],
            )
        )
        looks_like_model = bool(re.search(r"\d", brand)) and bool(
            re.search(r"[-_/]", brand)
        )
        invalid_brand_label = brand.casefold() in NON_BRAND_LABELS or looks_like_model
        selected = (
            ranked[0]
            if ranked and ranked[0][0] >= 0.55 and not invalid_brand_label
            else None
        )
        entry: dict[str, Any] = {
            "brand": brand,
            "status": (
                "ready"
                if selected
                else "needs_brand_cleanup"
                if invalid_brand_label
                else "needs_discovery"
            ),
            "discovery_query": f"{brand} official loudspeaker drivers subwoofers",
            "rejected_non_manufacturer_domains": sorted(rejected.get(brand_key, set())),
            "candidate_domains": [
                {
                    "domain": domain,
                    "confidence": round(confidence, 3),
                    "catalog_records": records,
                    "reasons": reasons,
                    "sample_urls": sorted(item.urls)[:3],
                }
                for confidence, records, domain, reasons, item in ranked[:5]
            ],
        }
        if selected:
            confidence, records, domain, reasons, item = selected
            root_seed = f"https://{domain}/"
            seed = sorted(item.preferred_seeds, key=lambda value: (len(value), value))[0] \
                if item.preferred_seeds else root_seed
            entry.update(
                {
                    "target_id": _target_id(brand, used_ids),
                    "official_domain": domain,
                    "confidence": round(confidence, 3),
                    "seed": seed,
                    "sitemap_candidates": [
                        f"{root_seed}sitemap.xml",
                        f"{root_seed}sitemap_index.xml",
                        f"{root_seed}wp-sitemap.xml",
                    ],
                    "catalog_records": records,
                    "evidence": reasons,
                }
            )
        entries.append(entry)

    collapse_aliases(entries)
    apply_declared_aliases(entries, (source_seeds or {}).get("aliases", []))
    ready = sum(entry["status"] == "ready" for entry in entries)
    aliases = sum(entry["status"] == "alias" for entry in entries)
    discovery = sum(entry["status"] == "needs_discovery" for entry in entries)
    cleanup = sum(entry["status"] == "needs_brand_cleanup" for entry in entries)
    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "catalog_version": payload.get("catalog_version"),
        "policy": {
            "manufacturer_first": True,
            "catalog_write": False,
            "retailers_are_price_only": True,
            "non_manufacturer_domains": sorted(NON_MANUFACTURER_DOMAINS),
        },
        "summary": {
            "catalog_brands": len(entries),
            "ready_official_targets": ready,
            "covered_brand_labels": ready + aliases,
            "brand_aliases": aliases,
            "needs_discovery": discovery,
            "needs_brand_cleanup": cleanup,
        },
        "brands": entries,
    }


def build_manifest(registry: dict[str, Any], *, max_targets: int) -> dict[str, Any]:
    targets = []
    for entry in registry["brands"]:
        if entry["status"] != "ready":
            continue
        records = int(entry.get("catalog_records", 0))
        targets.append(
            {
                "target_id": entry["target_id"],
                "source_kind": "official_manufacturer_site",
                "allowed_domains": [entry["official_domain"]],
                "seeds": [entry["seed"]],
                "brand": entry["brand"],
                "include": [],
                "exclude": [EXCLUDE_PATTERN],
                "priority": max(35, 92 - min(records, 57)),
                "max_pages": 120,
                "max_depth": 2,
                "sleep_seconds": 1.0,
                "min_confidence": 0.8,
                "enabled": True,
            }
        )
    return {
        "objective": "Review every catalog brand against its official manufacturer site",
        "max_targets": max_targets,
        "user_agent": "LoadForge-Catalog-Agent/1.0 (+https://github.com/playloud679/a_load_forge)",
        "targets": targets,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--discovery-cache", type=Path, default=DEFAULT_DISCOVERY_CACHE)
    parser.add_argument("--source-seeds", type=Path, default=DEFAULT_SOURCE_SEEDS)
    parser.add_argument("--max-targets", type=int, default=5)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    payload = json.loads(args.catalog.read_text(encoding="utf-8"))
    discoveries = (
        json.loads(args.discovery_cache.read_text(encoding="utf-8"))
        if args.discovery_cache.exists()
        else None
    )
    source_seeds = (
        json.loads(args.source_seeds.read_text(encoding="utf-8"))
        if args.source_seeds.exists()
        else None
    )
    registry = build_registry(payload, discoveries, source_seeds)
    manifest = build_manifest(registry, max_targets=args.max_targets)
    write_json(args.registry, registry)
    write_json(args.manifest, manifest)
    summary = registry["summary"]
    print(
        f"REGISTRY PASS: brands={summary['catalog_brands']} "
        f"ready={summary['ready_official_targets']} "
        f"needs_discovery={summary['needs_discovery']} "
        f"catalog_unchanged={args.catalog}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
