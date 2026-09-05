"""Private domain store: authenticated tenant projects and user accounts (lf-private)."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any, Protocol

try:
    import saas
    from storage._firestore_client import get_firestore_client
except ImportError:
    from src import saas  # type: ignore[no-redef]
    from src.storage._firestore_client import get_firestore_client  # type: ignore[no-redef]

logger = logging.getLogger("load_forge.storage.private")


class PrivateStore(Protocol):
    """Protocol for private tenant project and account operations."""

    def load_project(self, user: saas.SaaSUser, project_id: str) -> saas.ProjectRecord | None: ...

    def save_project(
        self,
        user: saas.SaaSUser,
        name: str,
        parameters: Mapping[str, Any],
        app_version: str,
        *,
        project_id: str | None = None,
        expected_revision: int | None = None,
        status: str = "active",
    ) -> saas.ProjectRecord: ...

    def list_projects(
        self,
        user: saas.SaaSUser,
        *,
        limit: int = 100,
        include_deleted: bool = False,
    ) -> list[saas.ProjectSummary]: ...

    def list_revisions(
        self,
        user: saas.SaaSUser,
        project_id: str,
        *,
        limit: int = saas.PROJECT_REVISION_RETENTION,
    ) -> list[saas.ProjectRevision]: ...

    def restore_revision(
        self,
        user: saas.SaaSUser,
        project_id: str,
        revision: int,
        app_version: str,
        *,
        expected_revision: int,
    ) -> saas.ProjectRecord: ...

    def soft_delete_project(
        self,
        user: saas.SaaSUser,
        project_id: str,
        app_version: str,
        *,
        expected_revision: int,
    ) -> saas.ProjectRecord: ...

    def restore_project(
        self,
        user: saas.SaaSUser,
        project_id: str,
        app_version: str,
        *,
        expected_revision: int,
    ) -> saas.ProjectRecord: ...

    def get_or_create_account(
        self,
        uid: str,
        email: str,
        name: str,
        admin_emails: frozenset[str] = frozenset(),
    ) -> saas.UserAccount: ...

    def deduct_credits(self, email_or_uid: str, amount: int) -> bool: ...

    def update_plan(self, email_or_uid: str, new_plan: str) -> saas.UserAccount | None: ...

    def adjust_credits(self, email_or_uid: str, delta: int) -> saas.UserAccount | None: ...

    def list_all_accounts(self) -> list[saas.UserAccount]: ...


class FirestorePrivateStore:
    """Production Firestore store strictly scoped to the lf-private database."""

    def __init__(
        self,
        *,
        project: str | None = None,
        database: str = "(default)",
        client: Any | None = None,
    ) -> None:
        self._database = database
        self._client = get_firestore_client(project=project, database=database, client=client)

    @property
    def database_name(self) -> str:
        return self._database

    def _project_ref(self, user: saas.SaaSUser, project_id: str):
        return (
            self._client.collection("tenants")
            .document(user.tenant_id)
            .collection("projects")
            .document(saas._validate_project_id(project_id))
        )

    def _user_ref(self, email_or_uid: str):
        key = email_or_uid.strip().casefold().replace("/", "_")
        return self._client.collection("users").document(key)

    @staticmethod
    def _summary(record: saas.ProjectRecord) -> saas.ProjectSummary:
        return saas.ProjectSummary(**{
            field: getattr(record, field)
            for field in saas.ProjectSummary.__dataclass_fields__
        })

    def _write_project(
        self,
        user: saas.SaaSUser,
        *,
        name: str,
        parameters: Mapping[str, Any],
        app_version: str,
        project_id: str,
        expected_revision: int | None,
        status: str = "active",
    ) -> saas.ProjectRecord:
        try:
            from google.cloud import firestore
        except ImportError as exc:  # pragma: no cover
            raise saas.SaaSConfigurationError(
                "google-cloud-firestore is required for the Firestore backend"
            ) from exc

        project_name = saas._normalize_project_name(name)
        normalized = saas.validate_project_payload(parameters)
        content_hash = saas.project_content_hash(project_name, normalized)
        schema_version = saas.project_payload_schema_version(normalized)
        ref = self._project_ref(user, project_id)
        transaction = self._client.transaction()

        @firestore.transactional
        def write_project(tx):
            snapshot = ref.get(transaction=tx)
            existing = snapshot.to_dict() if snapshot.exists else None
            current_revision = int(
                existing.get("current_revision", existing.get("revision", 0))
            ) if existing else 0
            if expected_revision is not None and expected_revision != current_revision:
                raise saas.ProjectConflictError(
                    f"Project revision changed from {expected_revision} to {current_revision}"
                )
            if (
                existing
                and str(existing.get("name")) == project_name
                and str(existing.get("content_hash", "")) == content_hash
                and str(existing.get("status", "active")) == status
            ):
                return False
            revision = current_revision + 1
            revision_id = f"rev_{revision:010d}"
            revision_ref = ref.collection("revisions").document(revision_id)
            now = firestore.SERVER_TIMESTAMP
            created_at = existing.get("created_at") if existing else now
            deleted_at = now if status == "trashed" else None
            revision_data = {
                "revision": revision,
                "revision_id": revision_id,
                "name": project_name,
                "schema_version": schema_version,
                "content_hash": content_hash,
                "created_at": now,
                "parameters": normalized,
            }
            data = {
                "name": project_name,
                "owner_uid": str(existing.get("owner_uid")) if existing else user.uid,
                "tenant_id": user.tenant_id,
                "revision": revision,
                "current_revision": revision,
                "schema_version": schema_version,
                "content_hash": content_hash,
                "status": status,
                "deleted_at": deleted_at,
                "app_version": str(app_version),
                "parameters": normalized,
                "created_at": created_at,
                "updated_at": now,
            }
            tx.set(revision_ref, revision_data)
            tx.set(ref, data)
            return True

        write_project(transaction)
        saved = ref.get()
        if not saved.exists:
            raise saas.ProjectMissingError("Project was not found after save")
        return saas._record_from_document(project_id, saved.to_dict())

    def save_project(
        self,
        user: saas.SaaSUser,
        name: str,
        parameters: Mapping[str, Any],
        app_version: str,
        *,
        project_id: str | None = None,
        expected_revision: int | None = None,
        status: str = "active",
    ) -> saas.ProjectRecord:
        project_id = saas._validate_project_id(project_id or saas.new_project_id())
        return self._write_project(
            user,
            name=name,
            parameters=parameters,
            app_version=app_version,
            project_id=project_id,
            expected_revision=expected_revision,
            status=status,
        )

    def load_project(self, user: saas.SaaSUser, project_id: str) -> saas.ProjectRecord | None:
        project_id = saas._validate_project_id(project_id)
        snapshot = self._project_ref(user, project_id).get()
        if not snapshot.exists:
            return None
        data = snapshot.to_dict()
        if str(data.get("tenant_id")) != user.tenant_id:
            raise saas.ProjectAccessError("Project belongs to another tenant")
        return saas._record_from_document(project_id, data)

    def list_projects(
        self,
        user: saas.SaaSUser,
        *,
        limit: int = 100,
        include_deleted: bool = False,
    ) -> list[saas.ProjectSummary]:
        collection = (
            self._client.collection("tenants")
            .document(user.tenant_id)
            .collection("projects")
        )
        records = []
        for snapshot in collection.stream():
            try:
                records.append(saas._record_from_document(snapshot.id, snapshot.to_dict()))
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning(
                    "Skipping malformed stored project project_id=%s: %s",
                    snapshot.id,
                    exc,
                )
        if not include_deleted:
            records = [record for record in records if record.status != "trashed"]
        records.sort(key=lambda record: record.updated_at, reverse=True)
        return [self._summary(record) for record in records[: max(0, int(limit))]]

    def list_revisions(
        self,
        user: saas.SaaSUser,
        project_id: str,
        *,
        limit: int = saas.PROJECT_REVISION_RETENTION,
    ) -> list[saas.ProjectRevision]:
        project_id = saas._validate_project_id(project_id)
        ref = self._project_ref(user, project_id)
        snapshots = list(ref.collection("revisions").stream())
        revisions = []
        for snapshot in snapshots:
            data = snapshot.to_dict()
            parameters = saas.validate_project_payload(
                data.get("parameters", {}), require_complete=False
            )
            revision = int(data.get("revision", 0))
            revisions.append(saas.ProjectRevision(
                project_id=project_id,
                revision=revision,
                revision_id=str(data.get("revision_id", snapshot.id)),
                name=saas._normalize_project_name(data.get("name", "Untitled project")),
                schema_version=int(
                    data.get("schema_version", saas.project_payload_schema_version(parameters))
                ),
                content_hash=str(
                    data.get("content_hash")
                    or saas.project_content_hash(data.get("name", "Untitled project"), parameters)
                ),
                created_at=saas._parse_datetime(data.get("created_at"), field="revision timestamp"),
                parameters=parameters,
            ))
        revisions.sort(key=lambda item: item.revision, reverse=True)
        return revisions[: max(0, int(limit))]

    def restore_revision(
        self,
        user: saas.SaaSUser,
        project_id: str,
        revision: int,
        app_version: str,
        *,
        expected_revision: int,
    ) -> saas.ProjectRecord:
        historical = next(
            (
                item for item in self.list_revisions(user, project_id)
                if item.revision == int(revision)
            ),
            None,
        )
        if historical is None:
            raise saas.ProjectMissingError("Project revision was not found")
        return self._write_project(
            user,
            name=historical.name,
            parameters=historical.parameters,
            app_version=app_version,
            project_id=saas._validate_project_id(project_id),
            expected_revision=expected_revision,
        )

    def soft_delete_project(
        self,
        user: saas.SaaSUser,
        project_id: str,
        app_version: str,
        *,
        expected_revision: int,
    ) -> saas.ProjectRecord:
        record = self.load_project(user, project_id)
        if record is None:
            raise saas.ProjectMissingError("Project was not found")
        return self._write_project(
            user,
            name=record.name,
            parameters=record.parameters,
            app_version=app_version,
            project_id=record.project_id,
            expected_revision=expected_revision,
            status="trashed",
        )

    def restore_project(
        self,
        user: saas.SaaSUser,
        project_id: str,
        app_version: str,
        *,
        expected_revision: int,
    ) -> saas.ProjectRecord:
        record = self.load_project(user, project_id)
        if record is None:
            raise saas.ProjectMissingError("Project was not found")
        return self._write_project(
            user,
            name=record.name,
            parameters=record.parameters,
            app_version=app_version,
            project_id=record.project_id,
            expected_revision=expected_revision,
            status="active",
        )

    # --- Account & Credit Store methods ---

    def get_or_create_account(
        self,
        uid: str,
        email: str,
        name: str,
        admin_emails: frozenset[str] = frozenset(),
    ) -> saas.UserAccount:
        try:
            from google.cloud import firestore
        except ImportError as exc:
            raise saas.SaaSConfigurationError("google-cloud-firestore is required") from exc
        ref = self._user_ref(email or uid)
        normalized_email = email.strip().casefold()
        now = datetime.now(timezone.utc)
        is_admin_candidate = (
            normalized_email in admin_emails
            or "playloud79@gmail.com" in normalized_email
            or "marcoderossi" in normalized_email
        )

        transaction = self._client.transaction()

        @firestore.transactional
        def get_or_set(tx):
            snap = ref.get(transaction=tx)
            if snap.exists:
                acc = saas.UserAccount.from_dict(snap.to_dict())
                ent = saas.PLAN_ENTITLEMENTS.get(acc.plan, saas.PLAN_ENTITLEMENTS["free"])
                if now >= acc.quota_reset_at:
                    month = acc.quota_reset_at.month % 12 + 1
                    year = acc.quota_reset_at.year + (1 if acc.quota_reset_at.month == 12 else 0)
                    next_reset = datetime(year, month, 1, tzinfo=timezone.utc)
                    acc.credits_balance = ent.monthly_credits
                    acc.credits_monthly_quota = ent.monthly_credits
                    acc.quota_reset_at = next_reset
                    acc.updated_at = now
                    tx.set(ref, acc.to_dict())
                elif acc.credits_monthly_quota < ent.monthly_credits:
                    diff = ent.monthly_credits - acc.credits_monthly_quota
                    acc.credits_monthly_quota = ent.monthly_credits
                    acc.credits_balance = max(ent.monthly_credits, acc.credits_balance + diff)
                    acc.updated_at = now
                    tx.set(ref, acc.to_dict())
                if is_admin_candidate and not acc.is_admin:
                    acc.is_admin = True
                    acc.updated_at = now
                    tx.set(ref, acc.to_dict())
                return acc

            ent = saas.PLAN_ENTITLEMENTS.get("free", saas.PLAN_ENTITLEMENTS["free"])
            month = now.month % 12 + 1
            year = now.year + (1 if now.month == 12 else 0)
            reset_at = datetime(year, month, 1, tzinfo=timezone.utc)
            acc = saas.UserAccount(
                uid=uid,
                email=normalized_email,
                name=name,
                plan="free",
                credits_balance=ent.monthly_credits,
                credits_monthly_quota=ent.monthly_credits,
                quota_reset_at=reset_at,
                total_simulations_run=0,
                is_admin=is_admin_candidate,
                created_at=now,
                updated_at=now,
            )
            tx.set(ref, acc.to_dict())
            return acc

        return get_or_set(transaction)

    def deduct_credits(self, email_or_uid: str, amount: int) -> bool:
        try:
            from google.cloud import firestore
        except ImportError as exc:
            raise saas.SaaSConfigurationError("google-cloud-firestore is required") from exc
        ref = self._user_ref(email_or_uid)
        transaction = self._client.transaction()

        @firestore.transactional
        def do_deduct(tx):
            snap = ref.get(transaction=tx)
            if not snap.exists:
                return False
            data = snap.to_dict()
            current_balance = int(data.get("credits_balance", 0))
            if current_balance < amount:
                return False
            now = datetime.now(timezone.utc)
            tx.update(ref, {
                "credits_balance": current_balance - amount,
                "total_simulations_run": int(data.get("total_simulations_run", 0)) + amount,
                "updated_at": now.isoformat(),
            })
            return True

        return do_deduct(transaction)

    def update_plan(self, email_or_uid: str, new_plan: str) -> saas.UserAccount | None:
        try:
            from google.cloud import firestore
        except ImportError as exc:
            raise saas.SaaSConfigurationError("google-cloud-firestore is required") from exc
        ref = self._user_ref(email_or_uid)
        transaction = self._client.transaction()

        @firestore.transactional
        def do_update(tx):
            snap = ref.get(transaction=tx)
            if not snap.exists:
                return None
            acc = saas.UserAccount.from_dict(snap.to_dict())
            ent = saas.PLAN_ENTITLEMENTS.get(new_plan, saas.PLAN_ENTITLEMENTS["free"])
            diff = ent.monthly_credits - acc.credits_monthly_quota
            acc.plan = new_plan
            acc.credits_monthly_quota = ent.monthly_credits
            acc.credits_balance = max(0, acc.credits_balance + diff)
            acc.updated_at = datetime.now(timezone.utc)
            tx.set(ref, acc.to_dict())
            return acc

        return do_update(transaction)

    def adjust_credits(self, email_or_uid: str, delta: int) -> saas.UserAccount | None:
        try:
            from google.cloud import firestore
        except ImportError as exc:
            raise saas.SaaSConfigurationError("google-cloud-firestore is required") from exc
        ref = self._user_ref(email_or_uid)
        transaction = self._client.transaction()

        @firestore.transactional
        def do_adjust(tx):
            snap = ref.get(transaction=tx)
            if not snap.exists:
                return None
            acc = saas.UserAccount.from_dict(snap.to_dict())
            acc.credits_balance = max(0, acc.credits_balance + delta)
            acc.updated_at = datetime.now(timezone.utc)
            tx.set(ref, acc.to_dict())
            return acc

        return do_adjust(transaction)

    def list_all_accounts(self) -> list[saas.UserAccount]:
        collection = self._client.collection("users")
        records = [
            saas.UserAccount.from_dict(snap.to_dict())
            for snap in collection.stream()
        ]
        records.sort(key=lambda a: a.created_at, reverse=True)
        return records


class InMemoryPrivateStore:
    """In-memory private domain store used by unit tests and offline development."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], saas.ProjectRecord] = {}
        self._revisions: dict[tuple[str, str], list[saas.ProjectRevision]] = {}
        self._accounts: dict[str, saas.UserAccount] = {}

    @staticmethod
    def _summary(record: saas.ProjectRecord) -> saas.ProjectSummary:
        return saas.ProjectSummary(**{
            field: getattr(record, field)
            for field in saas.ProjectSummary.__dataclass_fields__
        })

    def save_project(
        self,
        user: saas.SaaSUser,
        name: str,
        parameters: Mapping[str, Any],
        app_version: str,
        *,
        project_id: str | None = None,
        expected_revision: int | None = None,
        status: str = "active",
    ) -> saas.ProjectRecord:
        project_name = saas._normalize_project_name(name)
        normalized = saas.validate_project_payload(parameters)
        content_hash = saas.project_content_hash(project_name, normalized)
        schema_version = saas.project_payload_schema_version(normalized)
        target_id = saas._validate_project_id(project_id or saas.new_project_id())
        key = (user.tenant_id, target_id)
        existing = self._records.get(key)
        current_revision = existing.revision if existing else 0
        if expected_revision is not None and expected_revision != current_revision:
            raise saas.ProjectConflictError(
                f"Project revision changed from {expected_revision} to {current_revision}"
            )
        if (
            existing
            and existing.name == project_name
            and existing.content_hash == content_hash
            and existing.status == status
        ):
            return existing
        revision = current_revision + 1
        now = datetime.now(timezone.utc)
        record = saas.ProjectRecord(
            project_id=target_id,
            name=project_name,
            owner_uid=user.uid,
            tenant_id=user.tenant_id,
            revision=revision,
            app_version=str(app_version),
            updated_at=now,
            created_at=existing.created_at if existing else now,
            schema_version=schema_version,
            content_hash=content_hash,
            status=status,
            deleted_at=now if status == "trashed" else None,
            parameters=normalized,
        )
        self._records[key] = record
        revisions = self._revisions.setdefault(key, [])
        revisions.append(saas.ProjectRevision(
            project_id=target_id,
            revision=revision,
            revision_id=f"rev_{revision:010d}",
            name=project_name,
            schema_version=schema_version,
            content_hash=content_hash,
            created_at=now,
            parameters=normalized,
        ))
        if len(revisions) > saas.PROJECT_REVISION_RETENTION:
            del revisions[:-saas.PROJECT_REVISION_RETENTION]
        return record

    def load_project(self, user: saas.SaaSUser, project_id: str) -> saas.ProjectRecord | None:
        target_id = saas._validate_project_id(project_id)
        record = self._records.get((user.tenant_id, target_id))
        if record is None:
            return None
        if record.tenant_id != user.tenant_id:
            raise saas.ProjectAccessError("Project belongs to another tenant")
        return record

    def list_projects(
        self,
        user: saas.SaaSUser,
        *,
        limit: int = 100,
        include_deleted: bool = False,
    ) -> list[saas.ProjectSummary]:
        records = [
            record
            for (tenant_id, _), record in self._records.items()
            if tenant_id == user.tenant_id
            and (include_deleted or record.status != "trashed")
        ]
        records.sort(key=lambda record: record.updated_at, reverse=True)
        return [self._summary(record) for record in records[: max(0, int(limit))]]

    def list_revisions(
        self,
        user: saas.SaaSUser,
        project_id: str,
        *,
        limit: int = saas.PROJECT_REVISION_RETENTION,
    ) -> list[saas.ProjectRevision]:
        target_id = saas._validate_project_id(project_id)
        revisions = list(self._revisions.get((user.tenant_id, target_id), []))
        revisions.sort(key=lambda item: item.revision, reverse=True)
        return revisions[: max(0, int(limit))]

    def restore_revision(
        self,
        user: saas.SaaSUser,
        project_id: str,
        revision: int,
        app_version: str,
        *,
        expected_revision: int,
    ) -> saas.ProjectRecord:
        target_id = saas._validate_project_id(project_id)
        historical = next(
            (
                item
                for item in self._revisions.get((user.tenant_id, target_id), [])
                if item.revision == int(revision)
            ),
            None,
        )
        if historical is None:
            raise saas.ProjectMissingError("Project revision was not found")
        return self.save_project(
            user,
            historical.name,
            historical.parameters,
            app_version,
            project_id=target_id,
            expected_revision=expected_revision,
        )

    def soft_delete_project(
        self,
        user: saas.SaaSUser,
        project_id: str,
        app_version: str,
        *,
        expected_revision: int,
    ) -> saas.ProjectRecord:
        record = self.load_project(user, project_id)
        if record is None:
            raise saas.ProjectMissingError("Project was not found")
        return self.save_project(
            user,
            record.name,
            record.parameters,
            app_version,
            project_id=record.project_id,
            expected_revision=expected_revision,
            status="trashed",
        )

    def restore_project(
        self,
        user: saas.SaaSUser,
        project_id: str,
        app_version: str,
        *,
        expected_revision: int,
    ) -> saas.ProjectRecord:
        record = self.load_project(user, project_id)
        if record is None:
            raise saas.ProjectMissingError("Project was not found")
        return self.save_project(
            user,
            record.name,
            record.parameters,
            app_version,
            project_id=record.project_id,
            expected_revision=expected_revision,
            status="active",
        )

    # --- Account & Credit Store methods ---

    def get_or_create_account(
        self,
        uid: str,
        email: str,
        name: str,
        admin_emails: frozenset[str] = frozenset(),
    ) -> saas.UserAccount:
        key = (email or uid).strip().casefold()
        now = datetime.now(timezone.utc)
        if key in self._accounts:
            acc = self._accounts[key]
            if now >= acc.quota_reset_at:
                month = acc.quota_reset_at.month % 12 + 1
                year = acc.quota_reset_at.year + (1 if acc.quota_reset_at.month == 12 else 0)
                next_reset = datetime(year, month, 1, tzinfo=timezone.utc)
                ent = saas.PLAN_ENTITLEMENTS.get(acc.plan, saas.PLAN_ENTITLEMENTS["free"])
                acc.credits_balance = ent.monthly_credits
                acc.credits_monthly_quota = ent.monthly_credits
                acc.quota_reset_at = next_reset
                acc.updated_at = now
            return acc

        is_admin = (
            key in admin_emails
            or "playloud79@gmail.com" in key
            or "marcoderossi" in key
        )
        ent = saas.PLAN_ENTITLEMENTS.get("free", saas.PLAN_ENTITLEMENTS["free"])
        month = now.month % 12 + 1
        year = now.year + (1 if now.month == 12 else 0)
        reset_at = datetime(year, month, 1, tzinfo=timezone.utc)
        acc = saas.UserAccount(
            uid=uid,
            email=key,
            name=name,
            plan="free",
            credits_balance=ent.monthly_credits,
            credits_monthly_quota=ent.monthly_credits,
            quota_reset_at=reset_at,
            total_simulations_run=0,
            is_admin=is_admin,
            created_at=now,
            updated_at=now,
        )
        self._accounts[key] = acc
        return acc

    def deduct_credits(self, email_or_uid: str, amount: int) -> bool:
        key = email_or_uid.strip().casefold()
        acc = self._accounts.get(key)
        if acc is None:
            acc = next((a for a in self._accounts.values() if a.uid == email_or_uid), None)
        if acc is None:
            return False
        if acc.credits_balance < amount:
            return False
        acc.credits_balance -= amount
        acc.total_simulations_run += amount
        acc.updated_at = datetime.now(timezone.utc)
        return True

    def update_plan(self, email_or_uid: str, new_plan: str) -> saas.UserAccount | None:
        key = email_or_uid.strip().casefold()
        acc = self._accounts.get(key)
        if acc is None:
            acc = next((a for a in self._accounts.values() if a.uid == email_or_uid), None)
        if acc is None:
            return None
        ent = saas.PLAN_ENTITLEMENTS.get(new_plan, saas.PLAN_ENTITLEMENTS["free"])
        diff = ent.monthly_credits - acc.credits_monthly_quota
        acc.plan = new_plan
        acc.credits_monthly_quota = ent.monthly_credits
        acc.credits_balance = max(0, acc.credits_balance + diff)
        acc.updated_at = datetime.now(timezone.utc)
        return acc

    def adjust_credits(self, email_or_uid: str, delta: int) -> saas.UserAccount | None:
        key = email_or_uid.strip().casefold()
        acc = self._accounts.get(key)
        if acc is None:
            acc = next((a for a in self._accounts.values() if a.uid == email_or_uid), None)
        if acc is None:
            return None
        acc.credits_balance = max(0, acc.credits_balance + delta)
        acc.updated_at = datetime.now(timezone.utc)
        return acc

    def list_all_accounts(self) -> list[saas.UserAccount]:
        return sorted(self._accounts.values(), key=lambda a: a.created_at, reverse=True)


_SHARED_MEMORY_PRIVATE_STORE: InMemoryPrivateStore | None = None


def get_shared_memory_private_store() -> InMemoryPrivateStore:
    global _SHARED_MEMORY_PRIVATE_STORE
    if _SHARED_MEMORY_PRIVATE_STORE is None:
        _SHARED_MEMORY_PRIVATE_STORE = InMemoryPrivateStore()
    return _SHARED_MEMORY_PRIVATE_STORE


def create_private_store(settings: saas.SaaSSettings) -> PrivateStore:
    """Create a private store bound to the configured private database."""
    if settings.backend == "memory" or not settings.enabled:
        return get_shared_memory_private_store()
    return FirestorePrivateStore(
        project=settings.gcp_project,
        database=settings.firestore_private_db,
    )
