#!/usr/bin/env python3
"""Idempotent migration tool: copy public projects from source Firestore DB to target lf-public DB.

Preserves exact publication IDs, versions, timestamps, technical summaries and parameters.
Does not modify or delete source documents.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import storage

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("load_forge.migration.public")


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def migrate_public_projects(
    *,
    project_id: str | None = None,
    source_db: str = "(default)",
    target_db: str = "lf-public",
    dry_run: bool = True,
) -> dict[str, Any]:
    """Migrate public projects and versions from source_db to target_db."""
    source_client = storage.get_firestore_client(project=project_id, database=source_db)
    target_client = None if dry_run else storage.get_firestore_client(project=project_id, database=target_db)

    source_col = source_client.collection("public_projects")
    docs = list(source_col.stream())
    logger.info("Found %d public project documents in source DB '%s'", len(docs), source_db)

    migrated_pubs = 0
    migrated_versions = 0
    verification_errors = []

    for snap in docs:
        pub_id = snap.id
        data = snap.to_dict()
        if not isinstance(data, dict):
            logger.warning("Skipping non-dict doc %s", pub_id)
            continue

        # Get versions subcollection
        version_snaps = list(source_col.document(pub_id).collection("versions").stream())
        logger.info("Publication %s: %d versions found", pub_id, len(version_snaps))

        if not dry_run and target_client is not None:
            target_ref = target_client.collection("public_projects").document(pub_id)
            target_ref.set(data)
            for v_snap in version_snaps:
                v_id = v_snap.id
                v_data = v_snap.to_dict()
                target_ref.collection("versions").document(v_id).set(v_data)

            # Verification read
            verify_snap = target_ref.get()
            if not verify_snap.exists:
                verification_errors.append(f"Target document {pub_id} was not created")
            else:
                target_data = verify_snap.to_dict()
                if canonical_digest(target_data.get("parameters", {})) != canonical_digest(data.get("parameters", {})):
                    verification_errors.append(f"Digest mismatch for {pub_id}")

        migrated_pubs += 1
        migrated_versions += len(version_snaps)

    summary = {
        "source_database": source_db,
        "target_database": target_db,
        "dry_run": dry_run,
        "publications_count": migrated_pubs,
        "versions_count": migrated_versions,
        "errors": verification_errors,
    }
    logger.info("Migration finished: %s", json.dumps(summary, indent=2))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate public projects to lf-public DB.")
    parser.add_argument("--project", default=os.environ.get("LOAD_FORGE_GCP_PROJECT", "civic-radio-502611-i8"))
    parser.add_argument("--source-db", default="(default)")
    parser.add_argument("--target-db", default="lf-public")
    parser.add_argument("--commit", action="store_true", help="Execute writes (default: dry run)")
    args = parser.parse_args()

    result = migrate_public_projects(
        project_id=args.project,
        source_db=args.source_db,
        target_db=args.target_db,
        dry_run=not args.commit,
    )
    if result["errors"]:
        logger.error("Verification failed with errors: %s", result["errors"])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
