#!/usr/bin/env python3
"""Adopt projects left behind by removed anonymous guest accounts.

Anonymous guest identities (guest+<uid>@loadforge.local) can no longer sign
in, so their projects remain under the deterministic guest tenant and are
unreachable from the UI. This tool copies each guest project's current payload
into a real account tenant so it stays reachable.

Safety:
- dry-run by default; pass --apply to write
- the source guest documents are never modified or deleted
- a target project with the same ID is skipped, so reruns are idempotent
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import saas
import storage
import storage.private_store as _private_store


def _app_version() -> str:
    return (ROOT / "VERSION").read_text(encoding="utf-8").strip()


def _user_from_account(key: str, data: dict[str, Any]) -> saas.SaaSUser:
    email = str(data.get("email") or "").strip()
    uid = str(data.get("uid") or "").strip()
    if not uid and email.casefold().startswith("guest+"):
        uid = email.split("@", 1)[0][len("guest+"):]
    if not uid:
        raise ValueError(f"account {key!r} has no uid")
    return saas.SaaSUser(
        uid=uid,
        email=email,
        name=str(data.get("name") or "Load Forge user").strip(),
        tenant_id=saas.default_tenant_id(uid),
        plan=str(data.get("plan") or "free").strip().casefold(),
    )


def _account_document(client: Any, email: str) -> dict[str, Any] | None:
    key = email.strip().casefold().replace("/", "_")
    snapshot = client.collection("users").document(key).get()
    return snapshot.to_dict() if snapshot.exists else None


def _guest_accounts(client: Any) -> list[tuple[str, dict[str, Any]]]:
    accounts = []
    for document in client.collection("users").stream():
        data = document.to_dict() or {}
        email = str(data.get("email", "")).strip()
        if email.casefold().startswith("guest+"):
            accounts.append((document.id, data))
    return accounts


def adopt_guest_projects(
    *,
    project: str | None = None,
    database: str = "(default)",
    guest_email: str | None = None,
    target_email: str,
    dry_run: bool = True,
) -> dict[str, Any]:
    client = storage.get_firestore_client(project=project, database=database)
    settings = saas.SaaSSettings(
        enabled=True,
        backend="firestore",
        gcp_project=project,
        firestore_database=database,
        firestore_private_db=database,
    )
    store = _private_store.create_private_store(settings)

    target_data = _account_document(client, target_email)
    if not target_data:
        raise SystemExit(f"Target account {target_email!r} was not found in users/")
    target_user = _user_from_account(target_email, target_data)

    guests = _guest_accounts(client)
    if guest_email:
        wanted = guest_email.strip().casefold()
        guests = [item for item in guests if str(item[1].get("email", "")).casefold() == wanted]
    if not guests:
        raise SystemExit("No matching guest accounts found")

    report: dict[str, Any] = {
        "target_email": target_email,
        "target_tenant": target_user.tenant_id,
        "dry_run": dry_run,
        "copied": [],
        "skipped": [],
        "guests_scanned": len(guests),
    }
    for key, data in sorted(guests):
        guest_user = _user_from_account(key, data)
        projects = list(
            client.collection("tenants")
            .document(guest_user.tenant_id)
            .collection("projects")
            .stream()
        )
        for snapshot in projects:
            project_id = snapshot.id
            if store.load_project(target_user, project_id) is not None:
                report["skipped"].append(project_id)
                print(f"SKIP  {project_id} (already exists for {target_email})")
                continue
            record = store.load_project(guest_user, project_id)
            if record is None:
                report["skipped"].append(project_id)
                print(f"SKIP  {project_id} (no longer readable)")
                continue
            print(
                f"{'DRY' if dry_run else 'COPY'} {project_id} "
                f"name={record.name!r} rev={record.revision} "
                f"guest={guest_user.email} -> {target_email}"
            )
            if not dry_run:
                store.save_project(
                    target_user,
                    record.name,
                    record.parameters,
                    _app_version(),
                    project_id=project_id,
                )
            report["copied"].append(project_id)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=None, help="GCP project ID for Firestore")
    parser.add_argument("--database", default="(default)", help="Firestore database ID")
    parser.add_argument("--guest-email", default=None, help="Only adopt this guest account")
    parser.add_argument("--to-email", required=True, help="Destination account email")
    parser.add_argument("--apply", action="store_true", help="Write the copies (default: dry-run)")
    args = parser.parse_args()
    report = adopt_guest_projects(
        project=args.project,
        database=args.database,
        guest_email=args.guest_email,
        target_email=args.to_email,
        dry_run=not args.apply,
    )
    print(
        f"\n{'DRY-RUN' if report['dry_run'] else 'APPLIED'}: "
        f"copied={len(report['copied'])} skipped={len(report['skipped'])} "
        f"guests_scanned={report['guests_scanned']}"
    )


if __name__ == "__main__":
    main()
