"""Manifest validation and autonomous coverage planning for crawler jobs."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ALLOWED_SOURCE_KINDS = frozenset(
    {
        "official_manufacturer_site",
        "official_archive",
        "authorized_retailer",
    }
)
SOURCE_LABELS = {
    "official_manufacturer_site": "Official manufacturer site",
    "official_archive": "Official archive / heritage",
    "authorized_retailer": "Retailer / distributor",
}
_DATABASE_TERMS = re.compile(
    r"\b(database|driver[\s_-]*db|loudspeaker[\s_-]*database|"
    r"vituixcad|speaker[\s_-]*box[\s_-]*lite|lsdb)\b",
    re.I,
)


class AgentPolicyError(ValueError):
    """Raised when a requested crawl exceeds the service policy."""


@dataclass(frozen=True)
class SourceTarget:
    target_id: str
    source_kind: str
    allowed_domains: tuple[str, ...]
    seeds: tuple[str, ...] = ()
    sitemaps: tuple[str, ...] = ()
    brand: str = ""
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    priority: int = 50
    max_pages: int = 200
    max_depth: int = 2
    sleep_seconds: float = 1.0
    min_confidence: float = 0.75
    enabled: bool = True

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> SourceTarget:
        target = cls(
            target_id=str(data.get("target_id") or "").strip(),
            source_kind=str(data.get("source_kind") or "").strip().casefold(),
            allowed_domains=tuple(
                _clean_domain(value) for value in data.get("allowed_domains", [])
            ),
            seeds=tuple(str(value).strip() for value in data.get("seeds", [])),
            sitemaps=tuple(str(value).strip() for value in data.get("sitemaps", [])),
            brand=str(data.get("brand") or "").strip(),
            include=tuple(str(value) for value in data.get("include", [])),
            exclude=tuple(str(value) for value in data.get("exclude", [])),
            priority=int(data.get("priority", 50)),
            max_pages=int(data.get("max_pages", 200)),
            max_depth=int(data.get("max_depth", 2)),
            sleep_seconds=float(data.get("sleep_seconds", 1.0)),
            min_confidence=float(data.get("min_confidence", 0.75)),
            enabled=bool(data.get("enabled", True)),
        )
        target.validate()
        return target

    def validate(self) -> None:
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{2,63}", self.target_id):
            raise AgentPolicyError(f"Invalid target_id: {self.target_id!r}")
        if self.source_kind not in ALLOWED_SOURCE_KINDS:
            raise AgentPolicyError(f"{self.target_id}: source_kind must be a direct website source")
        if not self.allowed_domains or any(not domain for domain in self.allowed_domains):
            raise AgentPolicyError(f"{self.target_id}: explicit domains are required")
        if not self.seeds and not self.sitemaps:
            raise AgentPolicyError(f"{self.target_id}: seed or sitemap required")
        for url in (*self.seeds, *self.sitemaps):
            validate_target_url(self, url)
        if not 1 <= self.priority <= 100:
            raise AgentPolicyError(f"{self.target_id}: priority must be 1..100")
        if not 1 <= self.max_pages <= 5_000:
            raise AgentPolicyError(f"{self.target_id}: max_pages must be 1..5000")
        if not 0 <= self.max_depth <= 4:
            raise AgentPolicyError(f"{self.target_id}: max_depth must be 0..4")
        if self.sleep_seconds < 0.5:
            raise AgentPolicyError(f"{self.target_id}: request delay must be at least 0.5 seconds")
        if not 0.75 <= self.min_confidence <= 1.0:
            raise AgentPolicyError(f"{self.target_id}: min_confidence must be 0.75..1.0")
        for pattern in (*self.include, *self.exclude):
            try:
                re.compile(pattern)
            except re.error as exc:
                raise AgentPolicyError(
                    f"{self.target_id}: invalid URL pattern {pattern!r}"
                ) from exc


@dataclass(frozen=True)
class AgentManifest:
    objective: str
    max_targets: int
    user_agent: str
    targets: tuple[SourceTarget, ...]

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> AgentManifest:
        manifest = cls(
            objective=str(data.get("objective") or "Improve direct-source coverage").strip(),
            max_targets=int(data.get("max_targets", 3)),
            user_agent=str(data.get("user_agent") or "").strip(),
            targets=tuple(SourceTarget.from_mapping(item) for item in data.get("targets", [])),
        )
        manifest.validate()
        return manifest

    @classmethod
    def from_path(cls, path: Path) -> AgentManifest:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise AgentPolicyError("Agent manifest must be a JSON object")
        return cls.from_mapping(payload)

    def validate(self) -> None:
        if not self.targets:
            raise AgentPolicyError("Agent manifest has no targets")
        if not 1 <= self.max_targets <= 25:
            raise AgentPolicyError("max_targets must be 1..25")
        if not self.user_agent or not re.search(r"(https?://|@)", self.user_agent):
            raise AgentPolicyError(
                "user_agent must identify Load Forge and provide a contact URL/email"
            )
        target_ids = [target.target_id for target in self.targets]
        if len(set(target_ids)) != len(target_ids):
            raise AgentPolicyError("target_id values must be unique")


@dataclass(frozen=True)
class PlannedTarget:
    target: SourceTarget
    score: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class CrawlPlan:
    objective: str
    selected: tuple[PlannedTarget, ...]
    skipped: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective": self.objective,
            "selected": [
                {
                    "target_id": item.target.target_id,
                    "source_kind": item.target.source_kind,
                    "score": item.score,
                    "reasons": list(item.reasons),
                }
                for item in self.selected
            ],
            "skipped": list(self.skipped),
        }


def _clean_domain(value: object) -> str:
    return str(value).strip().casefold().removeprefix("www.")


def validate_target_url(target: SourceTarget, url: str) -> None:
    """Require a direct HTTP(S) URL on one exact manifest domain."""
    parsed = urlparse(url)
    host = _clean_domain(parsed.hostname or "")
    if parsed.scheme not in {"http", "https"} or not host:
        raise AgentPolicyError(f"{target.target_id}: invalid crawl URL {url!r}")
    if host not in target.allowed_domains:
        raise AgentPolicyError(f"{target.target_id}: URL host {host!r} is outside its allow-list")
    if _DATABASE_TERMS.search(f"{host} {parsed.path}"):
        raise AgentPolicyError(f"{target.target_id}: aggregated database sources are forbidden")


def _catalog_brands(catalog: dict[str, Any]) -> set[str]:
    return {
        re.sub(r"[^a-z0-9]+", "", str(item.get("brand") or "").casefold())
        for item in catalog.get("presets", [])
        if item.get("brand")
    }


def build_plan(
    manifest: AgentManifest,
    catalog: dict[str, Any] | None = None,
) -> CrawlPlan:
    """Prioritize policy-valid sources from coverage gaps and crawl utility."""
    covered_brands = _catalog_brands(catalog or {})
    ranked: list[PlannedTarget] = []
    skipped: list[str] = []
    for target in manifest.targets:
        if not target.enabled:
            skipped.append(f"{target.target_id}: disabled")
            continue
        reasons = [f"manifest priority {target.priority}"]
        score = float(target.priority)
        normalized_brand = re.sub(r"[^a-z0-9]+", "", target.brand.casefold())
        if normalized_brand and normalized_brand not in covered_brands:
            score += 35.0
            reasons.append("brand absent from current direct-source catalog")
        if target.sitemaps:
            score += 8.0
            reasons.append("bounded sitemap discovery available")
        if target.source_kind.startswith("official_"):
            score += 12.0
            reasons.append("first-party source")
        score -= min(target.max_pages / 1_000.0, 5.0)
        ranked.append(PlannedTarget(target, round(score, 3), tuple(reasons)))
    ranked.sort(key=lambda item: (-item.score, item.target.target_id))
    selected = tuple(ranked[: manifest.max_targets])
    skipped.extend(
        f"{item.target.target_id}: below this run's target budget"
        for item in ranked[manifest.max_targets :]
    )
    return CrawlPlan(manifest.objective, selected, tuple(skipped))
