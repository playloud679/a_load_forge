#!/usr/bin/env python3
"""Promotion pipeline tool for Load Forge catalog releases on lf-catalog-runtime.

Features:
- Validates candidate driver physics and provenance
- Verifies manifest rules and approval requirements
- Atomically writes release metadata and driver documents to lf-catalog-runtime
- Provides release rollback capability
- Idempotent and audit-ready
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import storage
import saas

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("load_forge.catalog.promotion")


def validate_driver_physics(driver: dict[str, Any]) -> list[str]:
    """Validate minimum physical bounds for a driver record."""
    errors = []
    fs = driver.get("fs_hz")
    re = driver.get("re_ohm")
    qts = driver.get("qts")
    if not isinstance(fs, (int, float)) or fs <= 0.0:
        errors.append("fs_hz must be positive and non-zero")
    if not isinstance(re, (int, float)) or re <= 0.0:
        errors.append("re_ohm must be positive and non-zero")
    if qts is not None and (not isinstance(qts, (int, float)) or qts <= 0.0):
        errors.append("qts must be positive and non-zero")
    return errors


def partition_candidate_drivers(
    drivers: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """Split candidates into (valid, errors, invalid names).

    The names let an caller that opts into dropping invalid rows record exactly
    which drivers were left out of a release, so the omission stays auditable.
    """
    valid = []
    errors = []
    invalid_names: list[str] = []
    for idx, item in enumerate(drivers):
        d = item.get("driver") if isinstance(item.get("driver"), dict) else item
        driver_errors = validate_driver_physics(dict(d))
        if not driver_errors:
            valid.append(item)
            continue
        name = str(item.get("name") or item.get("model") or f"row_{idx}")
        invalid_names.append(name)
        errors.append(f"Driver {name}: {'; '.join(driver_errors)}")
    return valid, errors, invalid_names


def validate_candidate_drivers(drivers: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """Validate driver physics and minimum required T/S parameters."""
    valid, errors, _invalid = partition_candidate_drivers(drivers)
    return valid, errors


def _runtime_store(
    *,
    project_id: str | None,
    database_id: str,
) -> Any:
    """Return the write-capable Firestore runtime store for a real release.

    ``storage.create_catalog_runtime_store`` falls back to the process-local
    in-memory store whenever the app settings resolve to a local/memory
    backend. A production promotion that silently succeeded against that store
    would report success while writing nothing to Firestore, so a committed
    release must land on the real Firestore store or fail loudly.
    """
    settings = saas.SaaSSettings.from_env()
    settings = replace(
        settings,
        enabled=True,
        backend="firestore",
        gcp_project=project_id or settings.gcp_project,
        firestore_catalog_runtime_db=database_id,
    )
    if not settings.gcp_project:
        raise RuntimeError(
            "refusing to commit a catalog release without a GCP project: set "
            "LOAD_FORGE_GCP_PROJECT or pass --project"
        )
    store = storage.create_catalog_runtime_store(settings)
    if isinstance(store, storage.InMemoryCatalogRuntimeStore):
        raise RuntimeError(
            "refusing to commit a catalog release into the in-memory store: set "
            "LOAD_FORGE_GCP_PROJECT and LOAD_FORGE_STORAGE_BACKEND=firestore "
            "(or pass --project) so the release reaches Firestore"
        )
    return store


def promote_catalog_release(
    *,
    candidate_file: Path | None = None,
    candidate_drivers: list[dict[str, Any]] | None = None,
    release_id: str,
    approved_by: str,
    metadata: dict[str, Any] | None = None,
    project_id: str | None = None,
    database_id: str = "lf-catalog-runtime",
    dry_run: bool = True,
    drop_invalid: bool = False,
) -> dict[str, Any]:
    """Execute promotion pipeline of validated drivers into lf-catalog-runtime.

    By default any invalid candidate aborts the promotion. With
    ``drop_invalid=True`` records that fail validation (for example a harvested
    driver with no voice-coil resistance, which the simulator cannot load) are
    omitted instead, and their names are stored in the release metadata so the
    omission is auditable.
    """
    if not release_id.strip():
        raise ValueError("release_id is required")
    if not approved_by.strip():
        raise ValueError("approved_by is required (explicit approval gate)")

    if candidate_drivers is not None:
        raw_drivers = list(candidate_drivers)
    elif candidate_file is not None and candidate_file.exists():
        payload = json.loads(candidate_file.read_text(encoding="utf-8"))
        raw_drivers = payload.get("presets", payload.get("drivers", []))
    else:
        raise ValueError("candidate_file or candidate_drivers must be provided")

    valid_drivers, validation_errors, invalid_names = partition_candidate_drivers(raw_drivers)
    if validation_errors:
        if not drop_invalid:
            raise ValueError(f"Candidate validation failed ({len(validation_errors)} errors): {validation_errors[:5]}")
        logger.warning(
            "Dropping %d invalid driver(s) from release %s: %s",
            len(invalid_names), release_id, invalid_names[:5],
        )

    canonical_json = json.dumps(valid_drivers, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(canonical_json).hexdigest()

    release_metadata = dict(metadata or {})
    if invalid_names:
        release_metadata["omitted_invalid_drivers"] = sorted(invalid_names)
        release_metadata["omitted_invalid_count"] = len(invalid_names)

    release_meta = {
        "release_id": release_id,
        "approved_by": approved_by,
        "promoted_at": datetime.now(UTC).isoformat(),
        "driver_count": len(valid_drivers),
        "catalog_sha256": digest,
        "metadata": release_metadata,
    }

    if dry_run:
        logger.info("DRY RUN: Validated release %s with %d drivers (digest: %s)", release_id, len(valid_drivers), digest[:12])
        return release_meta

    store = _runtime_store(project_id=project_id, database_id=database_id)
    # If store has promote_release, execute
    result = store.promote_release(
        release_id=release_id,
        approved_by=approved_by,
        drivers=valid_drivers,
        metadata=release_meta,
    )
    logger.info("Successfully promoted release %s (%d drivers)", release_id, len(valid_drivers))
    return result


def rollback_catalog_release(
    *,
    target_release_id: str,
    rolled_back_by: str,
    project_id: str | None = None,
    database_id: str = "lf-catalog-runtime",
    dry_run: bool = True,
) -> dict[str, Any]:
    """Roll back active release pointer to a previous validated release."""
    if not target_release_id.strip():
        raise ValueError("target_release_id is required")
    if not rolled_back_by.strip():
        raise ValueError("rolled_back_by operator is required")

    if dry_run:
        logger.info("DRY RUN: Would roll back active release to %s", target_release_id)
        return {"target_release_id": target_release_id, "dry_run": True}

    store = _runtime_store(project_id=project_id, database_id=database_id)
    result = store.rollback_release(
        target_release_id=target_release_id,
        rolled_back_by=rolled_back_by,
    )
    logger.info("Successfully rolled back catalog to release %s", target_release_id)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote or rollback catalog releases on lf-catalog-runtime.")
    parser.add_argument("--candidate", type=Path, help="Path to candidate catalog JSON")
    parser.add_argument("--release-id", help="Target release ID (e.g., manufacturer-20260901)")
    parser.add_argument("--approved-by", help="Operator ID or email approving the release")
    parser.add_argument("--rollback", help="Target release ID to roll back to")
    parser.add_argument("--project", default=os.environ.get("LOAD_FORGE_GCP_PROJECT", "civic-radio-502611-i8"))
    parser.add_argument("--database", default=os.environ.get("LF_FIRESTORE_CATALOG_RUNTIME_DB", "lf-catalog-runtime"))
    parser.add_argument("--commit", action="store_true", help="Execute writes to Firestore (default is dry-run)")
    parser.add_argument(
        "--drop-invalid", action="store_true",
        help="Omit records that fail physics validation instead of aborting; the "
             "omitted driver names are stored in the release metadata",
    )

    args = parser.parse_args()

    if args.rollback:
        if not args.approved_by:
            logger.error("--approved-by is required for rollback")
            return 1
        rollback_catalog_release(
            target_release_id=args.rollback,
            rolled_back_by=args.approved_by,
            project_id=args.project,
            database_id=args.database,
            dry_run=not args.commit,
        )
        return 0

    if not args.candidate or not args.release_id or not args.approved_by:
        logger.error("--candidate, --release-id, and --approved-by are required for promotion")
        return 1

    promote_catalog_release(
        candidate_file=args.candidate,
        release_id=args.release_id,
        approved_by=args.approved_by,
        project_id=args.project,
        database_id=args.database,
        dry_run=not args.commit,
        drop_invalid=args.drop_invalid,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
