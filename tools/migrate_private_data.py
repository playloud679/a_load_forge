#!/usr/bin/env python3
"""Idempotent migration tool: copy private tenant data and user accounts to lf-private DB.

Migrates:
- tenants/{tenant_id}
- tenants/{tenant_id}/projects/{project_id}
- tenants/{tenant_id}/projects/{project_id}/revisions/{rev_id}
- users/{email_or_uid} (accounts, plans, credits balances)

Preserves:
- All tenant IDs, project IDs, revision numbers, content hashes, created_at, updated_at
- Exact user credits balances, plan tiers, and role memberships
- Source data is never modified or deleted
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
logger = logging.getLogger("load_forge.migration.private")


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def migrate_private_data(
    *,
    project_id: str | None = None,
    source_db: str = "(default)",
    target_db: str = "lf-private",
    dry_run: bool = True,
) -> dict[str, Any]:
    """Migrate all private tenants, projects, revisions and users from source_db to target_db."""
    source_client = storage.get_firestore_client(project=project_id, database=source_db)
    target_client = None if dry_run else storage.get_firestore_client(project=project_id, database=target_db)

    # 1. Migrate Users / Accounts
    user_docs = list(source_client.collection("users").stream())
    logger.info("Found %d user account documents in source DB '%s'", len(user_docs), source_db)
    migrated_users = 0
    verification_errors = []

    for u_snap in user_docs:
        u_id = u_snap.id
        u_data = u_snap.to_dict()
        if not isinstance(u_data, dict):
            continue
        if not dry_run and target_client is not None:
            target_u_ref = target_client.collection("users").document(u_id)
            target_u_ref.set(u_data)
            verify_snap = target_u_ref.get()
            if not verify_snap.exists:
                verification_errors.append(f"Target user account {u_id} was not created")
            else:
                target_data = verify_snap.to_dict()
                if target_data.get("credits") != u_data.get("credits"):
                    verification_errors.append(f"Credits mismatch for user {u_id}")
        migrated_users += 1

    # 2. Migrate Tenants, Projects, and Revisions
    tenant_docs = list(source_client.collection("tenants").stream())
    logger.info("Found %d tenant documents in source DB '%s'", len(tenant_docs), source_db)
    migrated_tenants = 0
    migrated_projects = 0
    migrated_revisions = 0

    for t_snap in tenant_docs:
        tenant_id = t_snap.id
        t_data = t_snap.to_dict() or {}
        if not dry_run and target_client is not None:
            target_client.collection("tenants").document(tenant_id).set(t_data)

        # Projects subcollection
        proj_docs = list(source_client.collection("tenants").document(tenant_id).collection("projects").stream())
        for p_snap in proj_docs:
            project_id_val = p_snap.id
            p_data = p_snap.to_dict()
            if not isinstance(p_data, dict):
                continue

            # Revisions subcollection
            rev_docs = list(
                source_client.collection("tenants")
                .document(tenant_id)
                .collection("projects")
                .document(project_id_val)
                .collection("revisions")
                .stream()
            )

            if not dry_run and target_client is not None:
                p_ref = (
                    target_client.collection("tenants")
                    .document(tenant_id)
                    .collection("projects")
                    .document(project_id_val)
                )
                p_ref.set(p_data)

                for r_snap in rev_docs:
                    r_id = r_snap.id
                    r_data = r_snap.to_dict()
                    p_ref.collection("revisions").document(r_id).set(r_data)

                # Verification check
                v_snap = p_ref.get()
                if not v_snap.exists:
                    verification_errors.append(f"Target project {tenant_id}/{project_id_val} not found")
                else:
                    v_dict = v_snap.to_dict()
                    if canonical_digest(v_dict.get("parameters", {})) != canonical_digest(p_data.get("parameters", {})):
                        verification_errors.append(f"Digest mismatch for project {tenant_id}/{project_id_val}")

            migrated_projects += 1
            migrated_revisions += len(rev_docs)

        migrated_tenants += 1

    summary = {
        "source_database": source_db,
        "target_database": target_db,
        "dry_run": dry_run,
        "users_count": migrated_users,
        "tenants_count": migrated_tenants,
        "projects_count": migrated_projects,
        "revisions_count": migrated_revisions,
        "errors": verification_errors,
    }
    logger.info("Private migration summary: %s", json.dumps(summary, indent=2))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate private data to lf-private DB.")
    parser.add_argument("--project", default=os.environ.get("LOAD_FORGE_GCP_PROJECT", "civic-radio-502611-i8"))
    parser.add_argument("--source-db", default="(default)")
    parser.add_argument("--target-db", default="lf-private")
    parser.add_argument("--commit", action="store_true", help="Execute writes (default: dry run)")
    args = parser.parse_args()

    result = migrate_private_data(
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
