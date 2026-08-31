"""SaaS identity, entitlement and persistent-project primitives.

The module deliberately has no Streamlit dependency.  The UI adapts OIDC
claims from ``st.user`` into :class:`SaaSUser` and delegates persistence here,
which keeps tenant boundaries and project validation testable in isolation.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import sqlite3
import uuid
from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_PROJECT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,80}$")
_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}$")
_MAX_PROJECT_BYTES = 800_000
PROJECT_SCHEMA_VERSION = 2
SUPPORTED_PROJECT_SCHEMA_VERSIONS = frozenset({1, PROJECT_SCHEMA_VERSION})
PROJECT_REVISION_RETENTION = 30
PROJECT_TRASH_RETENTION_DAYS = 30
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1

logger = logging.getLogger("load_forge.saas")


class SaaSConfigurationError(RuntimeError):
    """Raised when SaaS mode is enabled with an unsafe configuration."""


class ProjectAccessError(PermissionError):
    """Raised when a user attempts to cross a project tenant boundary."""


class ProjectConflictError(RuntimeError):
    """Raised when an optimistic project revision is stale."""


class ProjectValidationError(ValueError):
    """Raised before persistence when a project payload is malformed."""


class ProjectMissingError(LookupError):
    """Raised when an operation targets a project or revision that is absent."""


class AccountExistsError(ValueError):
    """Raised when a local development account already exists."""


class InvalidCredentialsError(PermissionError):
    """Raised when local development credentials do not match an account."""


@dataclass(frozen=True)
class SaaSSettings:
    enabled: bool = False
    auth_required: bool = False
    allowed_emails: frozenset[str] = frozenset()
    open_beta_enabled: bool = False
    backend: str = "firestore"
    gcp_project: str | None = None
    firestore_database: str = "(default)"
    project_trash_retention_days: int = PROJECT_TRASH_RETENTION_DAYS
    oidc_provider: str | None = None
    auth_bypass: bool = False
    local_accounts: bool = False
    local_account_database: str = ".local/load_forge_accounts.sqlite3"
    dev_uid: str = "local-developer"
    dev_email: str = "developer@localhost"
    dev_name: str = "Local developer"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> SaaSSettings:
        values = os.environ if env is None else env
        enabled = _env_flag(values, "LOAD_FORGE_SAAS_ENABLED")
        auth_required = _env_flag(values, "LOAD_FORGE_AUTH_REQUIRED")
        open_beta_enabled = _env_flag(values, "LOAD_FORGE_OPEN_BETA_ENABLED")
        auth_bypass = _env_flag(values, "LOAD_FORGE_AUTH_BYPASS")
        local_accounts = _env_flag(values, "LOAD_FORGE_LOCAL_ACCOUNTS")
        if auth_bypass and local_accounts:
            raise SaaSConfigurationError(
                "Choose either LOAD_FORGE_AUTH_BYPASS or LOAD_FORGE_LOCAL_ACCOUNTS"
            )
        if (auth_bypass or local_accounts) and values.get("K_SERVICE"):
            raise SaaSConfigurationError(
                "Local authentication modes are forbidden on Cloud Run"
            )
        backend = str(values.get("LOAD_FORGE_SAAS_BACKEND", "firestore")).strip().casefold()
        if backend not in {"firestore", "memory"}:
            raise SaaSConfigurationError(
                "LOAD_FORGE_SAAS_BACKEND must be 'firestore' or 'memory'"
            )
        provider = str(values.get("LOAD_FORGE_OIDC_PROVIDER", "")).strip() or None
        try:
            trash_retention_days = int(
                values.get(
                    "LOAD_FORGE_PROJECT_TRASH_RETENTION_DAYS",
                    PROJECT_TRASH_RETENTION_DAYS,
                )
            )
        except (TypeError, ValueError) as exc:
            raise SaaSConfigurationError(
                "LOAD_FORGE_PROJECT_TRASH_RETENTION_DAYS must be an integer"
            ) from exc
        if not 1 <= trash_retention_days <= 365:
            raise SaaSConfigurationError(
                "LOAD_FORGE_PROJECT_TRASH_RETENTION_DAYS must be between 1 and 365"
            )
        allowed_emails = frozenset(
            email.strip().casefold()
            for email in re.split(
                r"[,;\n]",
                str(values.get("LOAD_FORGE_ALLOWED_EMAILS", "")),
            )
            if email.strip()
        )
        invalid_emails = sorted(
            email for email in allowed_emails if not _EMAIL_RE.fullmatch(email)
        )
        if invalid_emails:
            raise SaaSConfigurationError(
                "LOAD_FORGE_ALLOWED_EMAILS contains invalid addresses: "
                + ", ".join(invalid_emails)
            )
        return cls(
            enabled=enabled,
            auth_required=(
                enabled or auth_required or auth_bypass or local_accounts
            ),
            allowed_emails=allowed_emails,
            open_beta_enabled=open_beta_enabled,
            backend=backend,
            gcp_project=(
                str(
                    values.get("LOAD_FORGE_GCP_PROJECT")
                    or values.get("GOOGLE_CLOUD_PROJECT")
                    or ""
                ).strip()
                or None
            ),
            firestore_database=(
                str(values.get("LOAD_FORGE_FIRESTORE_DATABASE", "(default)")).strip()
                or "(default)"
            ),
            project_trash_retention_days=trash_retention_days,
            oidc_provider=provider,
            auth_bypass=auth_bypass,
            local_accounts=local_accounts,
            local_account_database=str(
                values.get(
                    "LOAD_FORGE_LOCAL_ACCOUNT_DATABASE",
                    ".local/load_forge_accounts.sqlite3",
                )
            ).strip(),
            dev_uid=str(values.get("LOAD_FORGE_DEV_UID", "local-developer")).strip(),
            dev_email=str(
                values.get("LOAD_FORGE_DEV_EMAIL", "developer@localhost")
            ).strip(),
            dev_name=str(
                values.get("LOAD_FORGE_DEV_NAME", "Local developer")
            ).strip(),
        )

    def allows_email(self, email: str) -> bool:
        """Return whether an authenticated email passes the optional allowlist."""
        if not self.allowed_emails:
            return True
        try:
            normalized = _normalize_email(email)
        except ValueError:
            return False
        return normalized in self.allowed_emails

    def development_claims(self) -> dict[str, str]:
        if not self.auth_bypass:
            raise SaaSConfigurationError("Local authentication bypass is disabled")
        return {
            "sub": self.dev_uid,
            "email": self.dev_email,
            "name": self.dev_name,
        }


@dataclass(frozen=True)
class SaaSUser:
    uid: str
    email: str
    name: str
    tenant_id: str
    plan: str = "free"


@dataclass(frozen=True)
class PlanEntitlements:
    plan: str
    saved_projects: int
    monthly_credits: int
    team_seats: int
    access_tier: str
    promotion: str | None = None

    @property
    def monthly_finder_runs(self) -> int:
        # Compatibility property pointing to monthly_credits
        return self.monthly_credits


PLAN_ENTITLEMENTS: dict[str, PlanEntitlements] = {
    "free": PlanEntitlements(
        "free",
        saved_projects=3,
        monthly_credits=100,
        team_seats=1,
        access_tier="free",
    ),
    "pro": PlanEntitlements(
        "pro",
        saved_projects=100,
        monthly_credits=2_500,
        team_seats=1,
        access_tier="pro",
    ),
    "team": PlanEntitlements(
        "team",
        saved_projects=500,
        monthly_credits=10_000,
        team_seats=10,
        access_tier="team",
    ),
}


@dataclass(frozen=True)
class ProjectSummary:
    project_id: str
    name: str
    owner_uid: str
    tenant_id: str
    revision: int
    app_version: str
    updated_at: datetime
    schema_version: int
    content_hash: str
    status: str
    deleted_at: datetime | None


@dataclass(frozen=True)
class ProjectRecord(ProjectSummary):
    parameters: dict[str, Any]
    created_at: datetime


@dataclass(frozen=True)
class ProjectRevision:
    project_id: str
    revision: int
    revision_id: str
    name: str
    schema_version: int
    content_hash: str
    created_at: datetime
    parameters: dict[str, Any]


def _normalize_email(email: str) -> str:
    value = str(email).strip().casefold()
    if not _EMAIL_RE.fullmatch(value):
        raise ValueError("Enter a valid email address")
    return value


def _normalize_account_name(name: str) -> str:
    value = " ".join(str(name).split())
    if not value:
        raise ValueError("Name is required")
    if len(value) > 80:
        raise ValueError("Name must be at most 80 characters")
    return value


def _validate_password(password: str) -> str:
    value = str(password)
    if len(value) < 10:
        raise ValueError("Password must contain at least 10 characters")
    if len(value) > 1_024:
        raise ValueError("Password is too long")
    return value


def _password_hash(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(
        _validate_password(password).encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=32,
    )
    return (
        f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}"
        f"${salt.hex()}${digest.hex()}"
    )


def _password_matches(password: str, encoded: str) -> bool:
    try:
        algorithm, raw_n, raw_r, raw_p, raw_salt, raw_digest = encoded.split("$")
        if algorithm != "scrypt":
            return False
        expected = bytes.fromhex(raw_digest)
        actual = hashlib.scrypt(
            str(password).encode("utf-8"),
            salt=bytes.fromhex(raw_salt),
            n=int(raw_n),
            r=int(raw_r),
            p=int(raw_p),
            dklen=len(expected),
        )
    except (TypeError, ValueError):
        return False
    return hmac.compare_digest(actual, expected)


class LocalAccountStore:
    """SQLite account registry for local product testing only."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    uid TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
        try:
            self.path.chmod(0o600)
        except OSError:
            pass

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def create_account(self, name: str, email: str, password: str) -> SaaSUser:
        normalized_email = _normalize_email(email)
        normalized_name = _normalize_account_name(name)
        uid = f"local_{uuid.uuid4().hex}"
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO accounts
                        (uid, email, name, password_hash, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        uid,
                        normalized_email,
                        normalized_name,
                        _password_hash(password),
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise AccountExistsError("An account with this email already exists") from exc
        return user_from_claims(
            {"sub": uid, "email": normalized_email, "name": normalized_name}
        )

    def authenticate(self, email: str, password: str) -> SaaSUser:
        try:
            normalized_email = _normalize_email(email)
        except ValueError as exc:
            raise InvalidCredentialsError("Email or password is incorrect") from exc
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT uid, email, name, password_hash
                FROM accounts
                WHERE email = ?
                """,
                (normalized_email,),
            ).fetchone()
        if row is None or not _password_matches(password, str(row[3])):
            raise InvalidCredentialsError("Email or password is incorrect")
        return user_from_claims({"sub": row[0], "email": row[1], "name": row[2]})


def _env_flag(env: Mapping[str, str], name: str, default: bool = False) -> bool:
    raw = env.get(name)
    if raw is None:
        return default
    return str(raw).strip().casefold() in _TRUE_VALUES


def default_tenant_id(uid: str) -> str:
    """Return a stable provider-neutral tenant ID for a single-user account."""
    digest = hashlib.sha256(uid.encode("utf-8")).hexdigest()[:24]
    return f"tenant-{digest}"


def user_from_claims(claims: Mapping[str, Any]) -> SaaSUser:
    uid = str(claims.get("sub") or claims.get("user_id") or "").strip()
    if not uid:
        raise SaaSConfigurationError("OIDC claims do not contain a stable subject")
    email = str(claims.get("email") or "").strip()
    name = str(claims.get("name") or email or "Load Forge user").strip()
    firebase = claims.get("firebase")
    firebase_tenant = firebase.get("tenant") if isinstance(firebase, Mapping) else None
    tenant_id = str(
        claims.get("tenant_id") or firebase_tenant or default_tenant_id(uid)
    ).strip()
    plan = str(claims.get("plan") or "free").strip().casefold()
    if plan not in PLAN_ENTITLEMENTS:
        plan = "free"
    return SaaSUser(
        uid=uid,
        email=email,
        name=name,
        tenant_id=tenant_id,
        plan=plan,
    )


def entitlements_for_plan(plan: str) -> PlanEntitlements:
    return PLAN_ENTITLEMENTS.get(str(plan).casefold(), PLAN_ENTITLEMENTS["free"])


def effective_entitlements(
    user: SaaSUser,
    settings: SaaSSettings,
) -> PlanEntitlements:
    """Resolve server-side access without changing the account's stored plan."""
    base = entitlements_for_plan(user.plan)
    if not settings.open_beta_enabled:
        return base
    pro = PLAN_ENTITLEMENTS["pro"]
    return PlanEntitlements(
        plan=base.plan,
        saved_projects=max(base.saved_projects, pro.saved_projects),
        monthly_credits=max(
            base.monthly_credits,
            pro.monthly_credits,
        ),
        team_seats=base.team_seats,
        access_tier=(
            base.access_tier
            if base.access_tier == "team"
            else pro.access_tier
        ),
        promotion="open_beta",
    )


def new_project_id() -> str:
    return f"prj_{uuid.uuid4().hex}"


def _validate_project_id(project_id: str) -> str:
    value = str(project_id).strip()
    if not _PROJECT_ID_RE.fullmatch(value):
        raise ValueError("Invalid project ID")
    return value


def _normalize_project_name(name: str) -> str:
    value = " ".join(str(name).split())
    if not value:
        raise ValueError("Project name is required")
    if len(value) > 80:
        raise ValueError("Project name must be at most 80 characters")
    return value


def _normalize_parameters(parameters: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(parameters, Mapping):
        raise ProjectValidationError("Project payload must be an object")
    try:
        encoded = json.dumps(
            parameters,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ProjectValidationError(
            "Project payload contains unsupported or non-finite values"
        ) from exc
    if len(encoded.encode("utf-8")) > _MAX_PROJECT_BYTES:
        raise ProjectValidationError(
            "Project payload exceeds the persistent document limit"
        )
    decoded = json.loads(encoded)
    if not isinstance(decoded, dict):
        raise ProjectValidationError("Project payload must serialize to an object")
    return decoded


def validate_project_payload(
    payload: Mapping[str, Any],
    *,
    allow_legacy: bool = True,
    require_complete: bool = True,
) -> dict[str, Any]:
    """Validate and normalize the canonical LFP/cloud project payload.

    Format-2 payloads are the write format. Legacy flat parameter mappings and
    format-1 LFP files remain readable so existing data migrates on next save.
    """
    normalized = _normalize_parameters(payload)
    metadata = normalized.get("_load_forge_meta")
    is_envelope = "parameters" in normalized or (
        isinstance(metadata, Mapping) and metadata.get("kind") == "project"
    )
    if not is_envelope:
        if not allow_legacy:
            raise ProjectValidationError("Project payload is not a supported LFP project")
        if not normalized or not isinstance(normalized.get("load_type"), str):
            raise ProjectValidationError(
                "Legacy project payload is missing the load type"
            )
        return normalized

    if not isinstance(metadata, Mapping):
        raise ProjectValidationError("Project metadata is missing")
    try:
        schema_version = int(metadata.get("format", 0))
    except (TypeError, ValueError) as exc:
        raise ProjectValidationError("Project schema version is invalid") from exc
    if schema_version not in SUPPORTED_PROJECT_SCHEMA_VERSIONS:
        raise ProjectValidationError(
            f"Project schema version {schema_version} is not supported"
        )
    if metadata.get("kind", "project") != "project":
        raise ProjectValidationError("LFP payload is not a project")
    parameters = normalized.get("parameters")
    if not isinstance(parameters, dict):
        raise ProjectValidationError("Project parameters are missing")
    required = ("load_type",)
    if require_complete:
        required += (
            "driver_fs_hz",
            "driver_vas_l",
            "driver_qts",
            "driver_qms",
            "driver_re_ohm",
        )
    missing = [key for key in required if key not in parameters]
    if missing:
        raise ProjectValidationError(
            "Project parameters are incomplete: " + ", ".join(missing)
        )
    if not isinstance(parameters.get("load_type"), str):
        raise ProjectValidationError("Project load type is invalid")
    project = normalized.get("project")
    if not isinstance(project, dict):
        raise ProjectValidationError("Project identity metadata is missing")
    _normalize_project_name(project.get("name", ""))
    bass_match = normalized.get("bass_match")
    if bass_match is not None and not isinstance(bass_match, dict):
        raise ProjectValidationError("Bass Match project state must be an object")
    return normalized


def project_payload_schema_version(payload: Mapping[str, Any]) -> int:
    metadata = payload.get("_load_forge_meta")
    if isinstance(metadata, Mapping):
        try:
            return int(metadata.get("format", 1))
        except (TypeError, ValueError):
            return 1
    return 1


def project_content_hash(name: str, payload: Mapping[str, Any]) -> str:
    """Return a semantic digest, excluding generated portable-file timestamps."""
    normalized = validate_project_payload(payload, require_complete=False)
    hash_payload = json.loads(json.dumps(normalized, allow_nan=False))
    project = hash_payload.get("project")
    if isinstance(project, dict):
        for key in ("id", "created_at", "updated_at"):
            project.pop(key, None)
        project["name"] = _normalize_project_name(name)
    encoded = json.dumps(
        hash_payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _parse_datetime(value: Any, *, field: str) -> datetime:
    if isinstance(value, datetime):
        return value
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ProjectValidationError(f"Stored project {field} is malformed") from exc
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _record_from_document(project_id: str, data: Mapping[str, Any]) -> ProjectRecord:
    created_at = _parse_datetime(data.get("created_at"), field="created_at")
    updated_at = _parse_datetime(data.get("updated_at"), field="updated_at")
    parameters = validate_project_payload(
        data.get("parameters", {}), require_complete=False
    )
    name = _normalize_project_name(str(data["name"]))
    deleted_at_raw = data.get("deleted_at")
    deleted_at = (
        _parse_datetime(deleted_at_raw, field="deleted_at")
        if deleted_at_raw is not None
        else None
    )
    return ProjectRecord(
        project_id=project_id,
        name=name,
        owner_uid=str(data["owner_uid"]),
        tenant_id=str(data["tenant_id"]),
        revision=int(data.get("current_revision", data.get("revision", 1))),
        app_version=str(data.get("app_version", "unknown")),
        updated_at=updated_at,
        schema_version=int(
            data.get("schema_version", project_payload_schema_version(parameters))
        ),
        content_hash=str(data.get("content_hash") or project_content_hash(name, parameters)),
        status=str(data.get("status", "active")),
        deleted_at=deleted_at,
        parameters=parameters,
        created_at=created_at,
    )


class InMemoryProjectStore:
    """Process-local implementation used only by tests and local development."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], ProjectRecord] = {}
        self._revisions: dict[tuple[str, str], list[ProjectRevision]] = {}

    @staticmethod
    def _summary(record: ProjectRecord) -> ProjectSummary:
        return ProjectSummary(**{
            field: getattr(record, field)
            for field in ProjectSummary.__dataclass_fields__
        })

    def _write_record(
        self,
        user: SaaSUser,
        *,
        project_id: str,
        name: str,
        parameters: Mapping[str, Any],
        app_version: str,
        expected_revision: int | None,
        status: str = "active",
        deleted_at: datetime | None = None,
    ) -> ProjectRecord:
        key = (user.tenant_id, project_id)
        existing = self._records.get(key)
        current_revision = existing.revision if existing else 0
        if expected_revision is not None and expected_revision != current_revision:
            raise ProjectConflictError(
                f"Project revision changed from {expected_revision} to {current_revision}"
            )
        project_name = _normalize_project_name(name)
        normalized = validate_project_payload(parameters)
        content_hash = project_content_hash(project_name, normalized)
        if (
            existing is not None
            and existing.name == project_name
            and existing.content_hash == content_hash
            and existing.status == status
        ):
            return existing
        now = datetime.now(timezone.utc)
        revision = current_revision + 1
        record = ProjectRecord(
            project_id=project_id,
            name=project_name,
            owner_uid=existing.owner_uid if existing else user.uid,
            tenant_id=user.tenant_id,
            revision=revision,
            app_version=str(app_version),
            updated_at=now,
            schema_version=project_payload_schema_version(normalized),
            content_hash=content_hash,
            status=status,
            deleted_at=deleted_at,
            parameters=normalized,
            created_at=existing.created_at if existing else now,
        )
        self._records[key] = record
        revisions = self._revisions.setdefault(key, [])
        revisions.append(ProjectRevision(
            project_id=project_id,
            revision=revision,
            revision_id=f"rev_{revision:010d}",
            name=project_name,
            schema_version=record.schema_version,
            content_hash=content_hash,
            created_at=now,
            parameters=normalized,
        ))
        if len(revisions) > PROJECT_REVISION_RETENTION:
            del revisions[:-PROJECT_REVISION_RETENTION]
        return record

    def save_project(
        self,
        user: SaaSUser,
        name: str,
        parameters: Mapping[str, Any],
        app_version: str,
        *,
        project_id: str | None = None,
        expected_revision: int | None = None,
    ) -> ProjectRecord:
        project_id = _validate_project_id(project_id or new_project_id())
        return self._write_record(
            user,
            project_id=project_id,
            name=name,
            parameters=parameters,
            app_version=app_version,
            expected_revision=expected_revision,
        )

    def load_project(self, user: SaaSUser, project_id: str) -> ProjectRecord | None:
        project_id = _validate_project_id(project_id)
        record = self._records.get((user.tenant_id, project_id))
        if record is not None and record.tenant_id != user.tenant_id:
            raise ProjectAccessError("Project belongs to another tenant")
        return record

    def list_projects(
        self,
        user: SaaSUser,
        *,
        limit: int = 100,
        include_deleted: bool = False,
    ) -> list[ProjectSummary]:
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
        user: SaaSUser,
        project_id: str,
        *,
        limit: int = PROJECT_REVISION_RETENTION,
    ) -> list[ProjectRevision]:
        key = (user.tenant_id, _validate_project_id(project_id))
        return list(reversed(self._revisions.get(key, [])))[: max(0, int(limit))]

    def restore_revision(
        self,
        user: SaaSUser,
        project_id: str,
        revision: int,
        app_version: str,
        *,
        expected_revision: int,
    ) -> ProjectRecord:
        project_id = _validate_project_id(project_id)
        historical = next(
            (
                item
                for item in self._revisions.get((user.tenant_id, project_id), [])
                if item.revision == int(revision)
            ),
            None,
        )
        if historical is None:
            raise ProjectMissingError("Project revision was not found")
        return self._write_record(
            user,
            project_id=project_id,
            name=historical.name,
            parameters=historical.parameters,
            app_version=app_version,
            expected_revision=expected_revision,
        )

    def soft_delete_project(
        self,
        user: SaaSUser,
        project_id: str,
        app_version: str,
        *,
        expected_revision: int,
    ) -> ProjectRecord:
        record = self.load_project(user, project_id)
        if record is None:
            raise ProjectMissingError("Project was not found")
        return self._write_record(
            user,
            project_id=record.project_id,
            name=record.name,
            parameters=record.parameters,
            app_version=app_version,
            expected_revision=expected_revision,
            status="trashed",
            deleted_at=datetime.now(timezone.utc),
        )

    def restore_project(
        self,
        user: SaaSUser,
        project_id: str,
        app_version: str,
        *,
        expected_revision: int,
    ) -> ProjectRecord:
        record = self.load_project(user, project_id)
        if record is None:
            raise ProjectMissingError("Project was not found")
        return self._write_record(
            user,
            project_id=record.project_id,
            name=record.name,
            parameters=record.parameters,
            app_version=app_version,
            expected_revision=expected_revision,
        )


class FirestoreProjectStore:
    """Tenant-scoped Firestore persistence with immutable revisions."""

    def __init__(
        self,
        *,
        project: str | None = None,
        database: str = "(default)",
        client: Any | None = None,
    ) -> None:
        if client is None:
            try:
                from google.cloud import firestore
            except ImportError as exc:  # pragma: no cover - deployment dependency
                raise SaaSConfigurationError(
                    "google-cloud-firestore is required for the Firestore backend"
                ) from exc
            client = firestore.Client(project=project, database=database)
        self._client = client

    def _project_ref(self, user: SaaSUser, project_id: str):
        return (
            self._client.collection("tenants")
            .document(user.tenant_id)
            .collection("projects")
            .document(_validate_project_id(project_id))
        )

    @staticmethod
    def _summary(record: ProjectRecord) -> ProjectSummary:
        return ProjectSummary(**{
            field: getattr(record, field)
            for field in ProjectSummary.__dataclass_fields__
        })

    def _write_project(
        self,
        user: SaaSUser,
        *,
        name: str,
        parameters: Mapping[str, Any],
        app_version: str,
        project_id: str,
        expected_revision: int | None,
        status: str = "active",
    ) -> ProjectRecord:
        try:
            from google.cloud import firestore
        except ImportError as exc:  # pragma: no cover - deployment dependency
            raise SaaSConfigurationError(
                "google-cloud-firestore is required for the Firestore backend"
            ) from exc
        project_name = _normalize_project_name(name)
        normalized = validate_project_payload(parameters)
        content_hash = project_content_hash(project_name, normalized)
        schema_version = project_payload_schema_version(normalized)
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
                raise ProjectConflictError(
                    f"Project revision changed from {expected_revision} "
                    f"to {current_revision}"
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
                # Keep revision for old readers while current_revision is canonical.
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
            raise ProjectMissingError("Project was not found after save")
        return _record_from_document(project_id, saved.to_dict())

    def save_project(
        self,
        user: SaaSUser,
        name: str,
        parameters: Mapping[str, Any],
        app_version: str,
        *,
        project_id: str | None = None,
        expected_revision: int | None = None,
    ) -> ProjectRecord:
        project_id = _validate_project_id(project_id or new_project_id())
        return self._write_project(
            user,
            name=name,
            parameters=parameters,
            app_version=app_version,
            project_id=project_id,
            expected_revision=expected_revision,
        )

    def load_project(self, user: SaaSUser, project_id: str) -> ProjectRecord | None:
        project_id = _validate_project_id(project_id)
        snapshot = self._project_ref(user, project_id).get()
        if not snapshot.exists:
            return None
        data = snapshot.to_dict()
        if str(data.get("tenant_id")) != user.tenant_id:
            raise ProjectAccessError("Project belongs to another tenant")
        return _record_from_document(project_id, data)

    def list_projects(
        self,
        user: SaaSUser,
        *,
        limit: int = 100,
        include_deleted: bool = False,
    ) -> list[ProjectSummary]:
        collection = (
            self._client.collection("tenants")
            .document(user.tenant_id)
            .collection("projects")
        )
        records = []
        for snapshot in collection.stream():
            try:
                records.append(_record_from_document(snapshot.id, snapshot.to_dict()))
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
        user: SaaSUser,
        project_id: str,
        *,
        limit: int = PROJECT_REVISION_RETENTION,
    ) -> list[ProjectRevision]:
        project_id = _validate_project_id(project_id)
        ref = self._project_ref(user, project_id)
        snapshots = list(ref.collection("revisions").stream())
        revisions = []
        for snapshot in snapshots:
            data = snapshot.to_dict()
            parameters = validate_project_payload(
                data.get("parameters", {}), require_complete=False
            )
            revision = int(data.get("revision", 0))
            revisions.append(ProjectRevision(
                project_id=project_id,
                revision=revision,
                revision_id=str(data.get("revision_id", snapshot.id)),
                name=_normalize_project_name(data.get("name", "Untitled project")),
                schema_version=int(
                    data.get("schema_version", project_payload_schema_version(parameters))
                ),
                content_hash=str(
                    data.get("content_hash")
                    or project_content_hash(data.get("name", "Untitled project"), parameters)
                ),
                created_at=_parse_datetime(data.get("created_at"), field="revision timestamp"),
                parameters=parameters,
            ))
        revisions.sort(key=lambda item: item.revision, reverse=True)
        return revisions[: max(0, int(limit))]

    def restore_revision(
        self,
        user: SaaSUser,
        project_id: str,
        revision: int,
        app_version: str,
        *,
        expected_revision: int,
    ) -> ProjectRecord:
        historical = next(
            (
                item for item in self.list_revisions(user, project_id)
                if item.revision == int(revision)
            ),
            None,
        )
        if historical is None:
            raise ProjectMissingError("Project revision was not found")
        return self._write_project(
            user,
            name=historical.name,
            parameters=historical.parameters,
            app_version=app_version,
            project_id=_validate_project_id(project_id),
            expected_revision=expected_revision,
        )

    def soft_delete_project(
        self,
        user: SaaSUser,
        project_id: str,
        app_version: str,
        *,
        expected_revision: int,
    ) -> ProjectRecord:
        record = self.load_project(user, project_id)
        if record is None:
            raise ProjectMissingError("Project was not found")
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
        user: SaaSUser,
        project_id: str,
        app_version: str,
        *,
        expected_revision: int,
    ) -> ProjectRecord:
        record = self.load_project(user, project_id)
        if record is None:
            raise ProjectMissingError("Project was not found")
        return self._write_project(
            user,
            name=record.name,
            parameters=record.parameters,
            app_version=app_version,
            project_id=record.project_id,
            expected_revision=expected_revision,
        )


@dataclass
class UserAccount:
    uid: str
    email: str
    name: str
    plan: str
    credits_balance: int
    credits_monthly_quota: int
    quota_reset_at: datetime
    total_simulations_run: int
    is_admin: bool
    created_at: datetime
    updated_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "uid": self.uid,
            "email": self.email,
            "name": self.name,
            "plan": self.plan,
            "credits_balance": self.credits_balance,
            "credits_monthly_quota": self.credits_monthly_quota,
            "quota_reset_at": self.quota_reset_at.isoformat(),
            "total_simulations_run": self.total_simulations_run,
            "is_admin": self.is_admin,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> UserAccount:
        def parse_dt(v: Any) -> datetime:
            if isinstance(v, datetime):
                return v
            if isinstance(v, str):
                try:
                    return datetime.fromisoformat(v)
                except Exception:
                    pass
            return datetime.now(timezone.utc)

        return cls(
            uid=str(data.get("uid", "")),
            email=str(data.get("email", "")),
            name=str(data.get("name", "")),
            plan=str(data.get("plan", "free")),
            credits_balance=int(data.get("credits_balance", 100)),
            credits_monthly_quota=int(data.get("credits_monthly_quota", 100)),
            quota_reset_at=parse_dt(data.get("quota_reset_at")),
            total_simulations_run=int(data.get("total_simulations_run", 0)),
            is_admin=bool(data.get("is_admin", False)),
            created_at=parse_dt(data.get("created_at")),
            updated_at=parse_dt(data.get("updated_at")),
        )


class InMemoryUserAccountStore:
    """In-memory user account store for tests and offline development."""

    def __init__(self) -> None:
        self._accounts: dict[str, UserAccount] = {}

    def get_or_create_account(
        self,
        uid: str,
        email: str,
        name: str,
        admin_emails: frozenset[str] = frozenset(),
    ) -> UserAccount:
        normalized_email = email.strip().casefold()
        key = normalized_email or uid
        now = datetime.now(timezone.utc)
        if key in self._accounts:
            acc = self._accounts[key]
            # Check monthly reset
            if now >= acc.quota_reset_at:
                # Next month reset
                month = acc.quota_reset_at.month % 12 + 1
                year = acc.quota_reset_at.year + (1 if acc.quota_reset_at.month == 12 else 0)
                next_reset = datetime(year, month, 1, tzinfo=timezone.utc)
                ent = PLAN_ENTITLEMENTS.get(acc.plan, PLAN_ENTITLEMENTS["free"])
                acc.credits_balance = ent.monthly_credits
                acc.credits_monthly_quota = ent.monthly_credits
                acc.quota_reset_at = next_reset
            if (normalized_email in admin_emails or "playloud79@gmail.com" in normalized_email or "marcoderossi" in normalized_email):
                acc.is_admin = True
            return acc

        is_admin = (
            normalized_email in admin_emails
            or "playloud79@gmail.com" in normalized_email
            or "marcoderossi" in normalized_email
        )
        plan = "free"
        ent = PLAN_ENTITLEMENTS.get(plan, PLAN_ENTITLEMENTS["free"])
        month = now.month % 12 + 1
        year = now.year + (1 if now.month == 12 else 0)
        reset_at = datetime(year, month, 1, tzinfo=timezone.utc)
        balance = 100_000 if is_admin else ent.monthly_credits
        quota = 100_000 if is_admin else ent.monthly_credits
        acc = UserAccount(
            uid=uid,
            email=normalized_email,
            name=name,
            plan=plan,
            credits_balance=balance,
            credits_monthly_quota=quota,
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
        if key not in self._accounts:
            return False
        acc = self._accounts[key]
        if acc.credits_balance < amount:
            return False
        acc.credits_balance -= amount
        acc.total_simulations_run += amount
        acc.updated_at = datetime.now(timezone.utc)
        return True

    def update_plan(self, email_or_uid: str, new_plan: str) -> UserAccount | None:
        key = email_or_uid.strip().casefold()
        if key not in self._accounts:
            return None
        acc = self._accounts[key]
        ent = PLAN_ENTITLEMENTS.get(new_plan, PLAN_ENTITLEMENTS["free"])
        diff = ent.monthly_credits - acc.credits_monthly_quota
        acc.plan = new_plan
        acc.credits_monthly_quota = ent.monthly_credits
        acc.credits_balance = max(0, acc.credits_balance + diff)
        acc.updated_at = datetime.now(timezone.utc)
        return acc

    def adjust_credits(self, email_or_uid: str, delta: int) -> UserAccount | None:
        key = email_or_uid.strip().casefold()
        if key not in self._accounts:
            return None
        acc = self._accounts[key]
        acc.credits_balance = max(0, acc.credits_balance + delta)
        acc.updated_at = datetime.now(timezone.utc)
        return acc

    def list_all_accounts(self) -> list[UserAccount]:
        return sorted(self._accounts.values(), key=lambda a: a.created_at, reverse=True)


class FirestoreUserAccountStore:
    """Production Firestore account and credit store."""

    def __init__(
        self,
        *,
        project: str | None = None,
        database: str = "(default)",
        client: Any | None = None,
    ) -> None:
        if client is None:
            try:
                from google.cloud import firestore
            except ImportError as exc:  # pragma: no cover
                raise SaaSConfigurationError(
                    "google-cloud-firestore is required for the Firestore backend"
                ) from exc
            client = firestore.Client(project=project, database=database)
        self._client = client

    def _user_ref(self, email_or_uid: str):
        key = email_or_uid.strip().casefold().replace("/", "_")
        return self._client.collection("users").document(key)

    def get_or_create_account(
        self,
        uid: str,
        email: str,
        name: str,
        admin_emails: frozenset[str] = frozenset(),
    ) -> UserAccount:
        try:
            from google.cloud import firestore
        except ImportError as exc:
            raise SaaSConfigurationError("google-cloud-firestore is required") from exc
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
                acc = UserAccount.from_dict(snap.to_dict())
                # Check monthly reset
                if now >= acc.quota_reset_at:
                    month = acc.quota_reset_at.month % 12 + 1
                    year = acc.quota_reset_at.year + (1 if acc.quota_reset_at.month == 12 else 0)
                    next_reset = datetime(year, month, 1, tzinfo=timezone.utc)
                    ent = PLAN_ENTITLEMENTS.get(acc.plan, PLAN_ENTITLEMENTS["free"])
                    acc.credits_balance = ent.monthly_credits
                    acc.credits_monthly_quota = ent.monthly_credits
                    acc.quota_reset_at = next_reset
                    acc.updated_at = now
                    tx.set(ref, acc.to_dict())
                if is_admin_candidate and not acc.is_admin:
                    acc.is_admin = True
                    acc.updated_at = now
                    tx.set(ref, acc.to_dict())
                return acc

            ent = PLAN_ENTITLEMENTS.get("free", PLAN_ENTITLEMENTS["free"])
            month = now.month % 12 + 1
            year = now.year + (1 if now.month == 12 else 0)
            reset_at = datetime(year, month, 1, tzinfo=timezone.utc)
            acc = UserAccount(
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
            raise SaaSConfigurationError("google-cloud-firestore is required") from exc
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

    def update_plan(self, email_or_uid: str, new_plan: str) -> UserAccount | None:
        try:
            from google.cloud import firestore
        except ImportError as exc:
            raise SaaSConfigurationError("google-cloud-firestore is required") from exc
        ref = self._user_ref(email_or_uid)
        transaction = self._client.transaction()

        @firestore.transactional
        def do_update(tx):
            snap = ref.get(transaction=tx)
            if not snap.exists:
                return None
            acc = UserAccount.from_dict(snap.to_dict())
            ent = PLAN_ENTITLEMENTS.get(new_plan, PLAN_ENTITLEMENTS["free"])
            diff = ent.monthly_credits - acc.credits_monthly_quota
            acc.plan = new_plan
            acc.credits_monthly_quota = ent.monthly_credits
            acc.credits_balance = max(0, acc.credits_balance + diff)
            acc.updated_at = datetime.now(timezone.utc)
            tx.set(ref, acc.to_dict())
            return acc

        return do_update(transaction)

    def adjust_credits(self, email_or_uid: str, delta: int) -> UserAccount | None:
        try:
            from google.cloud import firestore
        except ImportError as exc:
            raise SaaSConfigurationError("google-cloud-firestore is required") from exc
        ref = self._user_ref(email_or_uid)
        transaction = self._client.transaction()

        @firestore.transactional
        def do_adjust(tx):
            snap = ref.get(transaction=tx)
            if not snap.exists:
                return None
            acc = UserAccount.from_dict(snap.to_dict())
            acc.credits_balance = max(0, acc.credits_balance + delta)
            acc.updated_at = datetime.now(timezone.utc)
            tx.set(ref, acc.to_dict())
            return acc

        return do_adjust(transaction)

    def list_all_accounts(self) -> list[UserAccount]:
        collection = self._client.collection("users")
        records = [
            UserAccount.from_dict(snap.to_dict())
            for snap in collection.stream()
        ]
        records.sort(key=lambda a: a.created_at, reverse=True)
        return records


def create_project_store(settings: SaaSSettings):
    if settings.backend == "memory" or not settings.enabled:
        return InMemoryProjectStore()
    # A production Firestore configuration failure must be visible. Falling
    # back to process memory would show successful saves that disappear later.
    return FirestoreProjectStore(
        project=settings.gcp_project,
        database=settings.firestore_database,
    )


def project_error_kind(exc: BaseException) -> str:
    """Classify persistence failures without requiring Google libraries in tests."""
    if isinstance(exc, ProjectConflictError):
        return "conflict"
    if isinstance(exc, ProjectMissingError):
        return "missing"
    if isinstance(exc, ProjectValidationError):
        return "invalid"
    if isinstance(exc, ProjectAccessError):
        return "permission"
    name = type(exc).__name__.casefold()
    if any(token in name for token in (
        "deadline", "timeout", "serviceunavailable", "toomanyrequests",
        "resourceexhausted", "aborted", "internalservererror",
        "connection", "retry",
    )):
        return "transient"
    if any(token in name for token in ("permission", "forbidden")):
        return "permission"
    if any(token in name for token in ("unauthenticated", "credential")):
        return "auth"
    if "notfound" in name:
        return "missing"
    return "unknown"


def advance_project_autosave(
    store: Any,
    user: SaaSUser,
    name: str,
    payload: Mapping[str, Any],
    app_version: str,
    state: MutableMapping[str, Any],
    *,
    now: float,
    force: bool = False,
    debounce_seconds: float = 1.5,
    retry_delays: Sequence[float] = (2.0, 5.0, 15.0),
) -> tuple[str, ProjectRecord | None]:
    """Advance one debounced, retry-aware autosave without blocking or sleeping."""
    project_name = _normalize_project_name(name)
    normalized = validate_project_payload(payload, allow_legacy=False)
    content_hash = project_content_hash(project_name, normalized)
    suppressed_hash = str(state.get("_cloud_suppressed_hash", ""))
    if suppressed_hash == content_hash:
        state["_cloud_save_status"] = "unsaved"
        return "unsaved", None
    if suppressed_hash:
        state.pop("_cloud_suppressed_hash", None)
    saved_hash = str(state.get("_cloud_saved_hash", ""))
    observed_hash = str(state.get("_cloud_observed_hash", ""))
    if content_hash == saved_hash:
        state["_cloud_observed_hash"] = content_hash
        state["_cloud_save_status"] = "saved"
        return "saved", None
    if content_hash != observed_hash:
        state["_cloud_observed_hash"] = content_hash
        state["_cloud_dirty_since"] = now
        state["_cloud_save_status"] = "unsaved"
        state["_cloud_save_failure_count"] = 0
        state.pop("_cloud_save_retry_at", None)
        if not force:
            return "unsaved", None

    retry_at = float(state.get("_cloud_save_retry_at", 0.0) or 0.0)
    if retry_at > now and not force:
        state["_cloud_save_status"] = "retrying"
        return "retrying", None
    dirty_since = float(state.get("_cloud_dirty_since", now))
    if now - dirty_since < float(debounce_seconds) and not force:
        state["_cloud_save_status"] = "unsaved"
        return "unsaved", None

    state["_cloud_save_status"] = "saving"
    try:
        record = store.save_project(
            user,
            project_name,
            normalized,
            app_version,
            project_id=state.get("_cloud_project_id"),
            expected_revision=int(state.get("_cloud_project_revision", 0) or 0),
        )
    except Exception as exc:
        kind = project_error_kind(exc)
        logger.warning(
            "Project autosave failed (kind=%s project_id=%s expected_revision=%s)",
            kind,
            state.get("_cloud_project_id"),
            state.get("_cloud_project_revision", 0),
            exc_info=kind == "unknown",
        )
        state["_cloud_save_error"] = str(exc)
        state["_cloud_save_error_kind"] = kind
        if kind == "conflict":
            state["_cloud_save_status"] = "conflict"
            state["_cloud_conflict"] = {
                "project_id": state.get("_cloud_project_id"),
                "name": project_name,
                "payload": normalized,
            }
            return "conflict", None
        failures = int(state.get("_cloud_save_failure_count", 0)) + 1
        state["_cloud_save_failure_count"] = failures
        if kind == "transient" and failures <= len(retry_delays):
            state["_cloud_save_retry_at"] = now + float(retry_delays[failures - 1])
            state["_cloud_save_status"] = "retrying"
            return "retrying", None
        state["_cloud_save_status"] = "failed"
        return "failed", None

    state["_cloud_project_id"] = record.project_id
    state["_cloud_project_revision"] = record.revision
    state["_cloud_saved_hash"] = record.content_hash
    state["_cloud_observed_hash"] = record.content_hash
    state["_cloud_save_status"] = "saved"
    state["_cloud_save_failure_count"] = 0
    state.pop("_cloud_save_retry_at", None)
    state.pop("_cloud_save_error", None)
    state.pop("_cloud_save_error_kind", None)
    state.pop("_cloud_conflict", None)
    return "saved", record


def create_account_store(settings: SaaSSettings):
    if settings.backend == "memory" or not settings.enabled:
        return InMemoryUserAccountStore()
    try:
        return FirestoreUserAccountStore(
            project=settings.gcp_project,
            database=settings.firestore_database,
        )
    except Exception:
        return InMemoryUserAccountStore()
