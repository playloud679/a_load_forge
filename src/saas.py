"""SaaS identity, entitlement and persistent-project primitives.

The module deliberately has no Streamlit dependency.  The UI adapts OIDC
claims from ``st.user`` into :class:`SaaSUser` and delegates persistence here,
which keeps tenant boundaries and project validation testable in isolation.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sqlite3
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_PROJECT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,80}$")
_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}$")
_MAX_PROJECT_BYTES = 800_000
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1


class SaaSConfigurationError(RuntimeError):
    """Raised when SaaS mode is enabled with an unsafe configuration."""


class ProjectAccessError(PermissionError):
    """Raised when a user attempts to cross a project tenant boundary."""


class ProjectConflictError(RuntimeError):
    """Raised when an optimistic project revision is stale."""


class AccountExistsError(ValueError):
    """Raised when a local development account already exists."""


class InvalidCredentialsError(PermissionError):
    """Raised when local development credentials do not match an account."""


@dataclass(frozen=True)
class SaaSSettings:
    enabled: bool = False
    open_beta_enabled: bool = False
    backend: str = "firestore"
    gcp_project: str | None = None
    firestore_database: str = "(default)"
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
        return cls(
            enabled=enabled,
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
    monthly_finder_runs: int
    team_seats: int
    access_tier: str
    promotion: str | None = None


PLAN_ENTITLEMENTS: dict[str, PlanEntitlements] = {
    "free": PlanEntitlements(
        "free",
        saved_projects=3,
        monthly_finder_runs=10,
        team_seats=1,
        access_tier="free",
    ),
    "pro": PlanEntitlements(
        "pro",
        saved_projects=100,
        monthly_finder_runs=1_000,
        team_seats=1,
        access_tier="pro",
    ),
    "team": PlanEntitlements(
        "team",
        saved_projects=500,
        monthly_finder_runs=5_000,
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


@dataclass(frozen=True)
class ProjectRecord(ProjectSummary):
    parameters: dict[str, Any]
    created_at: datetime


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
                        datetime.now(UTC).isoformat(),
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
        monthly_finder_runs=max(
            base.monthly_finder_runs,
            pro.monthly_finder_runs,
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
        raise TypeError("Project parameters must be a mapping")
    encoded = json.dumps(parameters, sort_keys=True, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > _MAX_PROJECT_BYTES:
        raise ValueError("Project parameters exceed the persistent document limit")
    decoded = json.loads(encoded)
    if not isinstance(decoded, dict):
        raise TypeError("Project parameters must serialize to an object")
    return decoded


def _record_from_document(project_id: str, data: Mapping[str, Any]) -> ProjectRecord:
    created_at = data.get("created_at")
    updated_at = data.get("updated_at")
    if not isinstance(created_at, datetime):
        created_at = datetime.fromisoformat(str(created_at))
    if not isinstance(updated_at, datetime):
        updated_at = datetime.fromisoformat(str(updated_at))
    return ProjectRecord(
        project_id=project_id,
        name=str(data["name"]),
        owner_uid=str(data["owner_uid"]),
        tenant_id=str(data["tenant_id"]),
        revision=int(data.get("revision", 1)),
        app_version=str(data.get("app_version", "unknown")),
        updated_at=updated_at,
        parameters=_normalize_parameters(data.get("parameters", {})),
        created_at=created_at,
    )


class InMemoryProjectStore:
    """Process-local implementation used only by tests and local development."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], ProjectRecord] = {}

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
        key = (user.tenant_id, project_id)
        existing = self._records.get(key)
        if existing is not None and existing.tenant_id != user.tenant_id:
            raise ProjectAccessError("Project belongs to another tenant")
        current_revision = existing.revision if existing else 0
        if expected_revision is not None and expected_revision != current_revision:
            raise ProjectConflictError(
                f"Project revision changed from {expected_revision} to {current_revision}"
            )
        now = datetime.now(UTC)
        record = ProjectRecord(
            project_id=project_id,
            name=_normalize_project_name(name),
            owner_uid=existing.owner_uid if existing else user.uid,
            tenant_id=user.tenant_id,
            revision=current_revision + 1,
            app_version=str(app_version),
            updated_at=now,
            parameters=_normalize_parameters(parameters),
            created_at=existing.created_at if existing else now,
        )
        self._records[key] = record
        return record

    def load_project(self, user: SaaSUser, project_id: str) -> ProjectRecord | None:
        project_id = _validate_project_id(project_id)
        record = self._records.get((user.tenant_id, project_id))
        if record is not None and record.tenant_id != user.tenant_id:
            raise ProjectAccessError("Project belongs to another tenant")
        return record

    def list_projects(self, user: SaaSUser, *, limit: int = 100) -> list[ProjectSummary]:
        records = [
            record
            for (tenant_id, _), record in self._records.items()
            if tenant_id == user.tenant_id
        ]
        records.sort(key=lambda record: record.updated_at, reverse=True)
        return [
            ProjectSummary(
                project_id=record.project_id,
                name=record.name,
                owner_uid=record.owner_uid,
                tenant_id=record.tenant_id,
                revision=record.revision,
                app_version=record.app_version,
                updated_at=record.updated_at,
            )
            for record in records[: max(0, int(limit))]
        ]


class FirestoreProjectStore:
    """Tenant-scoped Firestore persistence with optimistic revisions."""

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
        try:
            from google.cloud import firestore
        except ImportError as exc:  # pragma: no cover - deployment dependency
            raise SaaSConfigurationError(
                "google-cloud-firestore is required for the Firestore backend"
            ) from exc
        project_id = _validate_project_id(project_id or new_project_id())
        project_name = _normalize_project_name(name)
        normalized = _normalize_parameters(parameters)
        ref = self._project_ref(user, project_id)
        transaction = self._client.transaction()

        @firestore.transactional
        def write_project(tx):
            snapshot = ref.get(transaction=tx)
            existing = snapshot.to_dict() if snapshot.exists else None
            current_revision = int(existing.get("revision", 0)) if existing else 0
            if expected_revision is not None and expected_revision != current_revision:
                raise ProjectConflictError(
                    f"Project revision changed from {expected_revision} "
                    f"to {current_revision}"
                )
            now = datetime.now(UTC)
            data = {
                "name": project_name,
                "owner_uid": (
                    str(existing.get("owner_uid")) if existing else user.uid
                ),
                "tenant_id": user.tenant_id,
                "revision": current_revision + 1,
                "app_version": str(app_version),
                "parameters": normalized,
                "created_at": existing.get("created_at") if existing else now,
                "updated_at": now,
            }
            tx.set(ref, data)
            return data

        return _record_from_document(project_id, write_project(transaction))

    def load_project(self, user: SaaSUser, project_id: str) -> ProjectRecord | None:
        project_id = _validate_project_id(project_id)
        snapshot = self._project_ref(user, project_id).get()
        if not snapshot.exists:
            return None
        data = snapshot.to_dict()
        if str(data.get("tenant_id")) != user.tenant_id:
            raise ProjectAccessError("Project belongs to another tenant")
        return _record_from_document(project_id, data)

    def list_projects(self, user: SaaSUser, *, limit: int = 100) -> list[ProjectSummary]:
        collection = (
            self._client.collection("tenants")
            .document(user.tenant_id)
            .collection("projects")
        )
        records = [
            _record_from_document(snapshot.id, snapshot.to_dict())
            for snapshot in collection.stream()
        ]
        records.sort(key=lambda record: record.updated_at, reverse=True)
        return [
            ProjectSummary(
                project_id=record.project_id,
                name=record.name,
                owner_uid=record.owner_uid,
                tenant_id=record.tenant_id,
                revision=record.revision,
                app_version=record.app_version,
                updated_at=record.updated_at,
            )
            for record in records[: max(0, int(limit))]
        ]


def create_project_store(settings: SaaSSettings):
    if settings.backend == "memory":
        return InMemoryProjectStore()
    return FirestoreProjectStore(
        project=settings.gcp_project,
        database=settings.firestore_database,
    )
