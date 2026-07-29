"""Promote approved crawler staging artifacts into an immutable catalog release."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tools import crawl_thiele_small as crawler

from .model import (
    SOURCE_LABELS,
    AgentManifest,
    AgentPolicyError,
    validate_target_url,
)

ALLOWED_RELEASE_SOURCES = frozenset(
    {
        "Official manufacturer site",
        "Official archive / heritage",
        "Retailer / distributor",
    }
)


def _load_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: catalog must be a JSON object")
    return payload


def _validated_candidates(
    paths: list[Path],
    manifest: AgentManifest,
) -> list[dict[str, Any]]:
    accepted: list[dict[str, Any]] = []
    targets = {target.target_id: target for target in manifest.targets}
    for path in paths:
        target_id = path.parent.name
        target = targets.get(target_id)
        if target is None or not target.enabled:
            raise ValueError(f"{path}: artifact target is not enabled in the manifest")
        expected_source = SOURCE_LABELS[target.source_kind]
        for item in _load_payload(path).get("presets", []):
            source = str(item.get("source") or "")
            url = str(item.get("url") or "")
            confidence = float((item.get("website_fields") or {}).get("confidence", 0.0))
            errors = crawler.validate_driver(dict(item.get("driver") or {}))
            if source not in ALLOWED_RELEASE_SOURCES or source != expected_source:
                raise ValueError(f"{path}: forbidden candidate source {source!r}")
            try:
                validate_target_url(target, url)
            except AgentPolicyError as exc:
                raise ValueError(f"{path}: candidate URL violates manifest: {url!r}") from exc
            if confidence < 0.75:
                raise ValueError(f"{path}: candidate confidence below 0.75")
            if errors:
                raise ValueError(f"{path}: invalid driver: {'; '.join(errors)}")
            accepted.append(item)
    return accepted


def build_release(
    baseline_path: Path,
    candidate_paths: list[Path],
    output_path: Path,
    *,
    manifest: AgentManifest,
    release_id: str,
    approved_by: str,
) -> dict[str, Any]:
    """Create a new file; approval is required and the baseline is untouched."""
    if not release_id.strip() or not approved_by.strip():
        raise ValueError("release_id and approved_by are required")
    if output_path.exists():
        raise FileExistsError(f"immutable release already exists: {output_path}")
    baseline = _load_payload(baseline_path)
    candidates = _validated_candidates(candidate_paths, manifest)
    merged, stats = crawler.merge_presets(
        list(baseline.get("presets", [])),
        candidates,
        overwrite=False,
    )
    canonical = json.dumps(merged, sort_keys=True, separators=(",", ":")).encode("utf-8")
    payload = {
        "release_id": release_id,
        "approved_by": approved_by,
        "created_at": datetime.now(UTC).isoformat(),
        "source_release": str(baseline_path),
        "candidate_artifacts": [str(path) for path in candidate_paths],
        "catalog_sha256": hashlib.sha256(canonical).hexdigest(),
        "usable_presets": len(merged),
        "merge_stats": stats,
        "presets": merged,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(f"{output_path.suffix}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(output_path)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, action="append", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--approved-by", required=True)
    args = parser.parse_args()
    payload = build_release(
        args.baseline,
        args.candidate,
        args.output,
        manifest=AgentManifest.from_path(args.manifest),
        release_id=args.release_id,
        approved_by=args.approved_by,
    )
    print(
        json.dumps(
            {
                "release_id": payload["release_id"],
                "usable_presets": payload["usable_presets"],
                "merge_stats": payload["merge_stats"],
                "catalog_sha256": payload["catalog_sha256"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
