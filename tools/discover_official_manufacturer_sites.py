#!/usr/bin/env python3
"""Verify official manufacturer homepages without requiring a hand-written list.

Candidates come from low-confidence catalog provenance plus predictable brand
domains. Verified results are cached and consumed by
``build_official_source_registry.py``. The proprietary catalog is never edited.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_official_source_registry as registry_builder

DEFAULT_REGISTRY = ROOT / "data" / "official_source_registry.json"
DEFAULT_CACHE = ROOT / "data" / "official_source_discovery_cache.json"
USER_AGENT = "LoadForge-Catalog-Agent/1.0 (+https://github.com/playloud679/a_load_forge)"
PAGE_TERMS = re.compile(
    r"\b(loudspeaker|speaker|subwoofer|woofer|audio|altoparlant|haut-parleur|"
    r"lautsprecher|falante|driver|transducer)\b",
    re.I,
)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")
IGNORED_WORDS = frozenset(
    {"audio", "acoustics", "alto", "falantes", "international", "loudspeakers", "norway", "official", "pro", "professional", "speaker", "speakers"}
)
SUFFIXES = (".com", ".net", ".audio", ".de", ".it", ".fr", ".co.uk", ".com.br")


def brand_tokens(brand: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9]+", brand.casefold())
        if len(token) >= 3 and token not in IGNORED_WORDS
    ]


def generated_domains(brand: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", brand.casefold())
    bases = {
        "".join(words),
        "-".join(words),
        "".join(word for word in words if word not in {"by", "official"}),
        "-".join(word for word in words if word not in {"by", "official"}),
    }
    if words and words[-1] in {"audio", "speakers", "speaker", "professional", "pro"}:
        bases.add("".join(words[:-1]))
        bases.add("-".join(words[:-1]))
    return [f"{base}{suffix}" for base in sorted(bases) if base for suffix in SUFFIXES]


def candidates_for(entry: dict[str, Any], limit: int) -> list[tuple[str, float, str]]:
    candidates: list[tuple[str, float, str]] = []
    seen: set[str] = set()
    for candidate in entry.get("candidate_domains", []):
        domain = str(candidate.get("domain") or "")
        if not domain or registry_builder.is_non_manufacturer(domain) or domain in seen:
            continue
        seen.add(domain)
        candidates.append((domain, float(candidate.get("confidence", 0.0)), "catalog provenance"))
    for domain in generated_domains(str(entry["brand"])):
        if registry_builder.is_non_manufacturer(domain) or domain in seen:
            continue
        seen.add(domain)
        candidates.append((domain, 0.0, "generated brand domain"))
    return candidates[:limit]


def _visible_sample(page: str) -> tuple[str, str]:
    title_match = TITLE_RE.search(page)
    title = html.unescape(TAG_RE.sub(" ", title_match.group(1))) if title_match else ""
    text = html.unescape(TAG_RE.sub(" ", page[:500_000]))
    return " ".join(title.split()), " ".join(text.split())[:120_000]


def verify_candidate(
    brand: str, domain: str, provenance_score: float, origin: str, timeout: float
) -> dict[str, Any]:
    requested = f"https://{domain}/"
    request = urllib.request.Request(
        requested,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
    )
    context = ssl.create_default_context()
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            final_url = response.geturl()
            content_type = response.headers.get_content_type()
            page = response.read(600_000).decode("utf-8", errors="ignore")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        return {"brand": brand, "domain": domain, "status": "unreachable", "error": str(exc)}

    final_domain = registry_builder.clean_domain(final_url)
    if not final_domain or registry_builder.is_non_manufacturer(final_domain):
        return {"brand": brand, "domain": domain, "status": "rejected", "error": "redirected to non-manufacturer domain"}
    if content_type not in {"text/html", "application/xhtml+xml"}:
        return {"brand": brand, "domain": domain, "status": "rejected", "error": f"unexpected content type {content_type}"}

    title, text = _visible_sample(page)
    tokens = brand_tokens(brand)
    normalized_title = registry_builder.normalized(title)
    normalized_text = registry_builder.normalized(text)
    token_hits = sum(token in normalized_text for token in tokens)
    domain_key = registry_builder.normalized(final_domain)
    score = min(provenance_score, 0.45)
    reasons = [origin]
    if tokens and all(token in domain_key for token in tokens):
        score += 0.35
        reasons.append("brand tokens match final domain")
    elif tokens and any(token in domain_key for token in tokens):
        score += 0.22
        reasons.append("brand token matches final domain")
    if tokens and all(token in normalized_title for token in tokens):
        score += 0.25
        reasons.append("brand appears in page title")
    elif token_hits:
        score += min(0.18, 0.08 * token_hits)
        reasons.append("brand appears in homepage text")
    title_has_audio = bool(PAGE_TERMS.search(title))
    text_audio_terms = {
        match.group(0).casefold() for match in PAGE_TERMS.finditer(text)
    }
    if title_has_audio:
        score += 0.12
        reasons.append("loudspeaker vocabulary verified in page title")
    elif origin == "catalog provenance" and len(text_audio_terms) >= 2:
        score += 0.08
        reasons.append("loudspeaker vocabulary verified in provenance page")
    score = min(score, 1.0)
    source_context_ok = title_has_audio or (
        origin == "catalog provenance" and len(text_audio_terms) >= 2
    )
    status = (
        "verified"
        if score >= 0.70 and token_hits and source_context_ok
        else "ambiguous"
    )
    return {
        "brand": brand,
        "domain": final_domain,
        "url": final_url,
        "status": status,
        "confidence": round(score, 3),
        "title": title[:300],
        "evidence": reasons,
    }


def discover(
    registry: dict[str, Any], *, workers: int, timeout: float, candidates_per_brand: int
) -> dict[str, Any]:
    unresolved = [entry for entry in registry["brands"] if entry["status"] == "needs_discovery"]
    jobs = []
    for entry in unresolved:
        for domain, score, origin in candidates_for(entry, candidates_per_brand):
            jobs.append((str(entry["brand"]), domain, score, origin))

    started = time.monotonic()
    attempted: list[dict[str, Any]] = []
    verified_by_brand: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(verify_candidate, brand, domain, score, origin, timeout): brand
            for brand, domain, score, origin in jobs
        }
        completed = 0
        next_update = time.monotonic() + 60.0
        for future in as_completed(futures):
            result = future.result()
            attempted.append(result)
            completed += 1
            brand = str(result["brand"])
            if result["status"] == "verified":
                current = verified_by_brand.get(brand)
                if current is None or result["confidence"] > current["confidence"]:
                    verified_by_brand[brand] = result
            if time.monotonic() >= next_update:
                print(
                    f"DISCOVERY PROGRESS: probes={completed}/{len(jobs)} "
                    f"brands_verified={len(verified_by_brand)}/{len(unresolved)} "
                    f"elapsed_s={time.monotonic() - started:.0f}",
                    flush=True,
                )
                next_update = time.monotonic() + 60.0

    discoveries = sorted(verified_by_brand.values(), key=lambda item: item["brand"].casefold())
    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "publication_state": "staging_only",
        "catalog_write": False,
        "summary": {
            "brands_considered": len(unresolved),
            "domain_probes": len(jobs),
            "verified": len(discoveries),
            "still_unresolved": len(unresolved) - len(discoveries),
        },
        "discoveries": discoveries,
        "attempts": sorted(attempted, key=lambda item: (str(item["brand"]).casefold(), str(item.get("domain")))),
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--candidates-per-brand", type=int, default=8)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    report = discover(
        registry,
        workers=args.workers,
        timeout=args.timeout,
        candidates_per_brand=args.candidates_per_brand,
    )
    write_json(args.cache, report)
    summary = report["summary"]
    print(
        f"DISCOVERY PASS: brands={summary['brands_considered']} "
        f"probes={summary['domain_probes']} verified={summary['verified']} "
        f"unresolved={summary['still_unresolved']} catalog_unchanged=true"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
