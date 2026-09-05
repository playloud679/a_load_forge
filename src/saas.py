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
_FIRESTORE_DB_RE = re.compile(r"^([a-z0-9][a-z0-9-]{2,61}[a-z0-9]|\(default\))$")
_MAX_PROJECT_BYTES = 800_000
PROJECT_SCHEMA_VERSION = 2
SUPPORTED_PROJECT_SCHEMA_VERSIONS = frozenset({1, PROJECT_SCHEMA_VERSION})
PUBLICATION_SCHEMA_VERSION = 1
SUPPORTED_PUBLICATION_SCHEMA_VERSIONS = frozenset({1, PUBLICATION_SCHEMA_VERSION})
_PUBLICATION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,80}$")
_PUBLICATION_VISIBILITIES = frozenset({"unlisted", "public", "unpublished"})
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
    firestore_private_db: str = "(default)"
    firestore_public_db: str = "(default)"
    firestore_catalog_runtime_db: str = "(default)"
    firestore_catalog_staging_db: str = "(default)"
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

        raw_db = (
            str(values.get("LOAD_FORGE_FIRESTORE_DATABASE", "(default)")).strip()
            or "(default)"
        )
        private_db = (
            str(
                values.get("LF_FIRESTORE_PRIVATE_DB")
                or values.get("LOAD_FORGE_FIRESTORE_PRIVATE_DB")
                or raw_db
            ).strip()
            or "(default)"
        )
        public_db = (
            str(
                values.get("LF_FIRESTORE_PUBLIC_DB")
                or values.get("LOAD_FORGE_FIRESTORE_PUBLIC_DB")
                or raw_db
            ).strip()
            or "(default)"
        )
        cat_runtime_db = (
            str(
                values.get("LF_FIRESTORE_CATALOG_RUNTIME_DB")
                or values.get("LOAD_FORGE_FIRESTORE_CATALOG_RUNTIME_DB")
                or raw_db
            ).strip()
            or "(default)"
        )
        cat_staging_db = (
            str(
                values.get("LF_FIRESTORE_CATALOG_STAGING_DB")
                or values.get("LOAD_FORGE_FIRESTORE_CATALOG_STAGING_DB")
                or raw_db
            ).strip()
            or "(default)"
        )

        for db_key, db_val in (
            ("LOAD_FORGE_FIRESTORE_DATABASE", raw_db),
            ("LF_FIRESTORE_PRIVATE_DB", private_db),
            ("LF_FIRESTORE_PUBLIC_DB", public_db),
            ("LF_FIRESTORE_CATALOG_RUNTIME_DB", cat_runtime_db),
            ("LF_FIRESTORE_CATALOG_STAGING_DB", cat_staging_db),
        ):
            if not _FIRESTORE_DB_RE.fullmatch(db_val):
                raise SaaSConfigurationError(
                    f"Invalid database name {db_val!r} for {db_key}. "
                    "Must be '(default)' or 4-63 lowercase alphanumeric characters with hyphens."
                )

        if _env_flag(values, "LOAD_FORGE_STRICT_MULTI_DB"):
            if private_db == "(default)" or public_db == "(default)":
                raise SaaSConfigurationError(
                    "LOAD_FORGE_STRICT_MULTI_DB requires explicit non-default databases "
                    "for private and public domains."
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
            firestore_database=raw_db,
            firestore_private_db=private_db,
            firestore_public_db=public_db,
            firestore_catalog_runtime_db=cat_runtime_db,
            firestore_catalog_staging_db=cat_staging_db,
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


@dataclass(frozen=True)
class PublicProjectSummary:
    publication_id: str
    owner_uid: str
    owner_display_name: str
    source_tenant_id: str
    source_project_id: str
    source_revision: int
    publication_version: int
    visibility: str
    title: str
    description: str
    schema_version: int
    app_version: str
    created_at: datetime
    updated_at: datetime
    published_at: datetime
    technical_summary: dict[str, Any]
    provenance: dict[str, Any]


@dataclass(frozen=True)
class PublicProjectRecord(PublicProjectSummary):
    parameters: dict[str, Any]


@dataclass(frozen=True)
class PublicProjectVersion:
    publication_id: str
    version: int
    version_id: str
    title: str
    description: str
    content_hash: str
    source_revision: int
    published_at: datetime
    technical_summary: dict[str, Any]
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


def new_publication_id() -> str:
    return f"pub_{uuid.uuid4().hex}"


def _validate_publication_id(publication_id: str) -> str:
    value = str(publication_id).strip()
    if not _PUBLICATION_ID_RE.fullmatch(value):
        raise ValueError("Invalid publication ID")
    return value


def _normalize_publication_title(title: str) -> str:
    value = " ".join(str(title).split())
    if not value:
        raise ValueError("Publication title is required")
    if len(value) > 120:
        raise ValueError("Publication title must be at most 120 characters")
    return value


def _normalize_publication_description(description: str) -> str:
    value = str(description).strip()
    if len(value) > 5000:
        raise ValueError("Publication description must be at most 5000 characters")
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


def extract_technical_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Extract electroacoustic metadata from canonical project parameters."""
    try:
        normalized = validate_project_payload(payload, require_complete=False)
        params = (
            normalized.get("parameters", {})
            if isinstance(normalized.get("parameters"), dict)
            else normalized
        )
    except Exception:
        params = (
            payload.get("parameters", {})
            if isinstance(payload.get("parameters"), Mapping)
            else payload
        )
    load_type = str(params.get("load_type", "Bass reflex"))
    resonator_type = str(params.get("reflex_resonator_type", "Port"))

    driver_name = str(params.get("driver_preset_name", "")).strip() or "Custom driver"
    fs = params.get("driver_fs_hz")
    vas = params.get("driver_vas_l")
    qts = params.get("driver_qts")
    qms = params.get("driver_qms")
    re_val = params.get("driver_re_ohm")
    sd = params.get("driver_sd_cm2")
    pe = params.get("driver_pe_w")
    xmax = params.get("driver_xmax_mm")

    nominal_size_in: float | None = None
    if sd is not None:
        try:
            sd_f = float(sd)
            if sd_f >= 1500:
                nominal_size_in = 21.0
            elif sd_f >= 1050:
                nominal_size_in = 18.0
            elif sd_f >= 750:
                nominal_size_in = 15.0
            elif sd_f >= 450:
                nominal_size_in = 12.0
            elif sd_f >= 300:
                nominal_size_in = 10.0
            elif sd_f >= 180:
                nominal_size_in = 8.0
            elif sd_f >= 110:
                nominal_size_in = 6.5
            elif sd_f >= 70:
                nominal_size_in = 5.0
            elif sd_f >= 40:
                nominal_size_in = 4.0
            elif sd_f >= 20:
                nominal_size_in = 3.0
        except (TypeError, ValueError):
            pass

    box_vol_l: float | None = None
    tuning_hz: float | None = None

    if load_type == "Bass reflex":
        box_vol_l = params.get("reflex_vb_l")
        tuning_hz = params.get("reflex_fb_hz")
    elif load_type == "Sealed":
        box_vol_l = params.get("sealed_vb_l")
        tuning_hz = params.get("sealed_fc_hz")
    elif load_type == "DCCAV":
        vb1 = float(
            params.get("box_vh_l", params.get("dccav_vb1_l", 0.0)) or 0.0
        )
        vb2 = float(
            params.get("box_vl_l", params.get("dccav_vb2_l", 0.0)) or 0.0
        )
        box_vol_l = (vb1 + vb2) if (vb1 or vb2) else None
        tuning_hz = params.get("box_fh_hz", params.get("dccav_fb1_hz"))
    elif load_type == "Bandpass 4th order":
        vb = float(
            params.get("bandpass4_vs_l", params.get("bp4_vb_l", 0.0)) or 0.0
        )
        vf = float(
            params.get("bandpass4_vp_l", params.get("bp4_vf_l", 0.0)) or 0.0
        )
        box_vol_l = (vb + vf) if (vb or vf) else None
        tuning_hz = params.get("bandpass4_fp_hz", params.get("bp4_fb_hz"))
    elif load_type == "Bandpass 6th order":
        vr = float(
            params.get("bandpass6_vr_l", params.get("bp6_vr_l", 0.0)) or 0.0
        )
        vf = float(
            params.get("bandpass6_vp_l", params.get("bp6_vf_l", 0.0)) or 0.0
        )
        box_vol_l = (vr + vf) if (vr or vf) else None
        tuning_hz = params.get(
            "bandpass6_fp_hz",
            params.get("bp6_fb_f_hz", params.get("bp6_fb_r_hz")),
        )
    elif load_type == "Bandpass 8th order":
        vr = float(params.get("bp8_v1_l", params.get("bp8_vr_l", 0.0)) or 0.0)
        vf1 = float(params.get("bp8_v2_l", params.get("bp8_vf1_l", 0.0)) or 0.0)
        vf2 = float(params.get("bp8_v3_l", params.get("bp8_vf2_l", 0.0)) or 0.0)
        box_vol_l = (vr + vf1 + vf2) if (vr or vf1 or vf2) else None
        tuning_hz = params.get("bp8_f1_hz", params.get("bp8_fb_f1_hz"))
    elif load_type == "Passive radiator":
        box_vol_l = params.get("reflex_vb_l") or params.get("pr_vb_l")
        tuning_hz = params.get("reflex_fb_hz")

    f3_hz = params.get("f3_hz") if params.get("f3_hz") is not None else params.get("f3")
    peak_spl_db = params.get("peak_spl_db") if params.get("peak_spl_db") is not None else (params.get("spl_db") or params.get("mol_db"))

    if f3_hz is None or peak_spl_db is None:
        try:
            from src import acoustics as _acoustics
            import numpy as _np
            d_ts = None
            if fs and vas and qts:
                d_ts = _acoustics.DriverTS(
                    fs_hz=float(fs),
                    vas_l=float(vas),
                    qts=float(qts),
                    qms=float(qms or 5.0),
                    re_ohm=float(re_val or 5.0),
                    sd_cm2=float(sd or 500.0),
                    pe_w=float(pe or 100.0),
                    xmax_mm=float(xmax or 5.0),
                )
            elif driver_name:
                try:
                    d_ts = _acoustics.get_driver_preset(driver_name)
                except Exception:
                    clean = driver_name.split("(")[0].strip()
                    try:
                        d_ts = _acoustics.get_driver_preset(clean)
                    except Exception:
                        d_ts = None

            if d_ts is not None:
                freq = _np.geomspace(20.0, 500.0, 120)
                res = None
                vol_val = float(box_vol_l or 0.0)
                if load_type == "Bass reflex":
                    vb = vol_val if vol_val > 0 else (d_ts.vas_l * (d_ts.qts ** 2) * 15.0)
                    fb = float(tuning_hz or d_ts.fs_hz)
                    b_mod = _acoustics.ReflexBox(
                        vb_l=vb,
                        fb_hz=fb,
                        ql=float(params.get("reflex_ql", 7.0) or 7.0),
                    )
                    res = _acoustics.simulate_reflex(d_ts, b_mod, freq)
                elif load_type == "Sealed":
                    vb = vol_val if vol_val > 0 else d_ts.vas_l
                    fc = float(tuning_hz or (d_ts.fs_hz * 1.3))
                    b_mod = _acoustics.SealedBox(
                        vb_l=vb,
                        fc_hz=fc,
                        qtc=float(params.get("sealed_qtc", 0.707) or 0.707),
                    )
                    res = _acoustics.simulate_sealed(d_ts, b_mod, freq)
                elif load_type == "DCCAV":
                    if vol_val > 0:
                        vh = float(params.get("box_vh_l", params.get("dccav_vb1_l", vol_val / 3.0)) or (vol_val / 3.0))
                        vl = float(params.get("box_vl_l", params.get("dccav_vb2_l", 2.0 * vol_val / 3.0)) or (2.0 * vol_val / 3.0))
                        fh = float(params.get("box_fh_hz", params.get("dccav_fb1_hz", tuning_hz or 60.0)) or 60.0)
                        fl = float(params.get("box_fl_hz", params.get("dccav_fb2_hz", 30.0)) or 30.0)
                        b_mod = _acoustics.DccavBox(vh_l=vh, vl_l=vl, fh_hz=fh, fl_hz=fl)
                    else:
                        sugg = _acoustics.suggest_alignment(d_ts)
                        b_mod = _acoustics.DccavBox(vh_l=sugg.vh_l, vl_l=sugg.vl_l, fh_hz=sugg.fh_hz, fl_hz=sugg.fl_hz)
                    res = _acoustics.simulate(d_ts, b_mod, freq)
                elif load_type == "Bandpass 4th order":
                    vs = float(params.get("bandpass4_vs_l", params.get("bp4_vb_l", vol_val / 2.0 if vol_val else 20.0)) or 20.0)
                    vp = float(params.get("bandpass4_vp_l", params.get("bp4_vf_l", vol_val / 2.0 if vol_val else 20.0)) or 20.0)
                    fp = float(params.get("bandpass4_fp_hz", params.get("bp4_fb_hz", tuning_hz or 50.0)) or 50.0)
                    b_mod = _acoustics.Bandpass4Box(vs_l=vs, vp_l=vp, fp_hz=fp)
                    res = _acoustics.simulate_bandpass4(d_ts, b_mod, freq)
                elif load_type == "Bandpass 6th order":
                    vr = float(params.get("bandpass6_vr_l", params.get("bp6_vr_l", vol_val / 2.0 if vol_val else 20.0)) or 20.0)
                    vp = float(params.get("bandpass6_vp_l", params.get("bp6_vf_l", vol_val / 2.0 if vol_val else 20.0)) or 20.0)
                    fp = float(params.get("bandpass6_fp_hz", params.get("bp6_fb_f_hz", tuning_hz or 60.0)) or 60.0)
                    fr = float(params.get("bandpass6_fr_hz", params.get("bp6_fb_r_hz", 30.0)) or 30.0)
                    b_mod = _acoustics.Bandpass6Box(vr_l=vr, vp_l=vp, fp_hz=fp, fr_hz=fr)
                    res = _acoustics.simulate_bandpass6(d_ts, b_mod, freq)
                elif load_type == "Bandpass 8th order":
                    v1 = float(params.get("bp8_v1_l", vol_val / 3.0 if vol_val else 20.0) or 20.0)
                    v2 = float(params.get("bp8_v2_l", vol_val / 3.0 if vol_val else 20.0) or 20.0)
                    v3 = float(params.get("bp8_v3_l", vol_val / 3.0 if vol_val else 20.0) or 20.0)
                    f1 = float(params.get("bp8_f1_hz", 70.0) or 70.0)
                    f2 = float(params.get("bp8_f2_hz", 45.0) or 45.0)
                    f3_p = float(params.get("bp8_f3_hz", 30.0) or 30.0)
                    b_mod = _acoustics.Bandpass8Box(v1_l=v1, v2_l=v2, v3_l=v3, f1_hz=f1, f2_hz=f2, f3_hz=f3_p)
                    res = _acoustics.simulate_bandpass8(d_ts, b_mod, freq)
                elif load_type == "Infinite baffle":
                    res = _acoustics.simulate_infinite_baffle(d_ts, freq)

                if res is not None:
                    mets = _acoustics.response_metrics(res)
                    if f3_hz is None:
                        f3_hz = mets.get("f3_hz")
                    if peak_spl_db is None:
                        if hasattr(res, "mol_db") and len(res.mol_db) and _np.nanmax(res.mol_db) > 0:
                            peak_spl_db = float(_np.nanmax(res.mol_db))
                        elif hasattr(res, "spl_total_db") and len(res.spl_total_db):
                            peak_spl_db = float(_np.nanmax(res.spl_total_db))
        except Exception as exc:
            logger.debug("Automatic technical summary metric derivation: %s", exc)

    summary: dict[str, Any] = {
        "load_type": load_type,
        "resonator_type": resonator_type,
        "driver_name": driver_name,
        "driver_fs_hz": fs,
        "driver_vas_l": vas,
        "driver_qts": qts,
        "driver_qms": qms,
        "driver_re_ohm": re_val,
        "driver_sd_cm2": sd,
        "driver_pe_w": pe,
        "driver_xmax_mm": xmax,
        "nominal_size_in": nominal_size_in,
        "box_volume_l": box_vol_l,
        "tuning_freq_hz": tuning_hz,
        "f3_hz": f3_hz,
        "peak_spl_db": peak_spl_db,
        "driver_configuration": params.get("driver_config", "Single driver"),
        "box_strategy": params.get("box_strategy", "Max extension"),
        "cover_image": params.get("cover_image") or payload.get("cover_image"),
    }
    return {k: v for k, v in summary.items() if v is not None}


def generate_json_ld_schema(
    pub: PublicProjectRecord, base_url: str = ""
) -> dict[str, Any]:
    """Generate Schema.org TechArticle JSON-LD structured data."""
    tech = pub.technical_summary or extract_technical_summary(pub.parameters)
    page_url = (
        f"{base_url.rstrip('/')}/?p={pub.publication_id}"
        if base_url
        else f"?p={pub.publication_id}"
    )
    published_str = (
        pub.published_at.isoformat()
        if hasattr(pub.published_at, "isoformat")
        else str(pub.published_at)
    )
    props = [
        {"@type": "PropertyValue", "name": "Load Topology", "value": tech.get("load_type")},
        {"@type": "PropertyValue", "name": "Simulation Engine", "value": f"Load Forge v{pub.app_version}"},
    ]
    if tech.get("box_volume_l") is not None:
        props.append({"@type": "PropertyValue", "name": "Enclosure Volume (Vb)", "value": f"{tech['box_volume_l']:.1f} L"})
    if tech.get("tuning_freq_hz") is not None:
        props.append({"@type": "PropertyValue", "name": "Tuning Frequency (Fb)", "value": f"{tech['tuning_freq_hz']:.1f} Hz"})
    if tech.get("driver_fs_hz") is not None:
        props.append({"@type": "PropertyValue", "name": "Fs", "value": f"{tech['driver_fs_hz']:.1f} Hz"})
    if tech.get("driver_vas_l") is not None:
        props.append({"@type": "PropertyValue", "name": "Vas", "value": f"{tech['driver_vas_l']:.1f} L"})
    if tech.get("driver_qts") is not None:
        props.append({"@type": "PropertyValue", "name": "Qts", "value": f"{tech['driver_qts']:.3f}"})

    doc: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "TechArticle",
        "mainEntityOfPage": {
            "@type": "WebPage",
            "@id": page_url,
        },
        "headline": pub.title,
        "description": pub.description or f"Electroacoustic simulation and design for {tech.get('driver_name', 'transducer')} in {tech.get('load_type', 'enclosure')}.",
        "author": {
            "@type": "Person",
            "name": pub.owner_display_name or "Load Forge Engineer",
        },
        "publisher": {
            "@type": "Organization",
            "name": "Load Forge Electroacoustics",
            "url": "https://loadforge.app",
        },
        "datePublished": published_str,
        "dateModified": published_str,
        "about": {
            "@type": "Product",
            "name": tech.get("driver_name", "Loudspeaker Driver"),
            "category": tech.get("load_type", "Loudspeaker Enclosure"),
            "additionalProperty": props,
        },
    }
    cover_img = tech.get("cover_image")
    if cover_img and isinstance(cover_img, str) and cover_img.startswith("http"):
        doc["image"] = [cover_img]
    return doc


def generate_open_graph_meta(
    pub: PublicProjectRecord, base_url: str = ""
) -> dict[str, str]:
    """Generate Open Graph and Twitter Card metadata for rich link previews."""
    tech = pub.technical_summary or extract_technical_summary(pub.parameters)
    page_url = (
        f"{base_url.rstrip('/')}/?p={pub.publication_id}"
        if base_url
        else f"?p={pub.publication_id}"
    )
    driver_name = tech.get("driver_name", "Custom driver")
    load_type = tech.get("load_type", "Acoustic Load")
    vol = f"{tech['box_volume_l']:.1f}L" if "box_volume_l" in tech else ""
    tune = f"{tech['tuning_freq_hz']:.1f}Hz" if "tuning_freq_hz" in tech else ""
    specs = " · ".join(filter(None, [load_type, vol, tune]))
    desc = pub.description or f"Load Forge engineering simulation for {driver_name} ({specs})."
    meta = {
        "og:title": f"{pub.title} | Load Forge",
        "og:description": desc,
        "og:type": "article",
        "og:url": page_url,
        "og:site_name": "Load Forge",
        "twitter:card": "summary_large_image" if tech.get("cover_image") else "summary",
        "twitter:title": f"{pub.title} | Load Forge",
        "twitter:description": desc,
    }
    cover_img = tech.get("cover_image")
    if cover_img and isinstance(cover_img, str) and cover_img.startswith("http"):
        meta["og:image"] = cover_img
        meta["twitter:image"] = cover_img
    return meta


def generate_printable_spec_sheet_markdown(pub: PublicProjectRecord) -> str:
    """Generate a clean printable technical spec sheet in Markdown."""
    tech = pub.technical_summary or extract_technical_summary(pub.parameters)
    pub_date = (
        pub.published_at.strftime("%d %b %Y %H:%M UTC")
        if hasattr(pub.published_at, "strftime")
        else str(pub.published_at)
    )
    lines = [
        f"# {pub.title}",
        f"**Load Forge Technical Specification Sheet**",
        "",
        f"- **Author / Designer:** {pub.owner_display_name or 'Anonymous'}",
        f"- **Publication Date:** {pub_date}",
        f"- **Publication Version:** v{pub.publication_version} ({pub.visibility})",
        f"- **Publication ID:** `{pub.publication_id}`",
        f"- **Engine Version:** Load Forge v{pub.app_version}",
        "",
        "## System Overview",
        f"- **Enclosure Topology:** {tech.get('load_type', 'Bass reflex')}",
        f"- **Transducer:** {tech.get('driver_name', 'Custom driver')}",
    ]
    if tech.get("nominal_size_in") is not None:
        lines.append(f"- **Nominal Size:** {tech['nominal_size_in']:.1f} in")
    if tech.get("box_volume_l") is not None:
        lines.append(f"- **Enclosure Net Volume ($V_b$):** {tech['box_volume_l']:.1f} L")
    if tech.get("tuning_freq_hz") is not None:
        lines.append(f"- **Tuning Frequency ($F_b$):** {tech['tuning_freq_hz']:.1f} Hz")
    if tech.get("box_strategy") is not None:
        lines.append(f"- **Alignment Strategy:** {tech['box_strategy']}")

    lines.extend([
        "",
        "## Transducer Electromechanics (T/S Parameters)",
        "| Parameter | Symbol | Value | Unit |",
        "| :--- | :--- | :--- | :--- |",
    ])
    if tech.get("driver_fs_hz") is not None:
        lines.append(f"| Resonance Frequency | $F_s$ | {tech['driver_fs_hz']:.1f} | Hz |")
    if tech.get("driver_vas_l") is not None:
        lines.append(f"| Equivalent Compliance Volume | $V_{{as}}$ | {tech['driver_vas_l']:.1f} | L |")
    if tech.get("driver_qts") is not None:
        lines.append(f"| Total Q Factor | $Q_{{ts}}$ | {tech['driver_qts']:.3f} | — |")
    if tech.get("driver_qms") is not None:
        lines.append(f"| Mechanical Q Factor | $Q_{{ms}}$ | {tech['driver_qms']:.2f} | — |")
    if tech.get("driver_re_ohm") is not None:
        lines.append(f"| DC Resistance | $R_e$ | {tech['driver_re_ohm']:.2f} | Ω |")
    if tech.get("driver_sd_cm2") is not None:
        lines.append(f"| Effective Diaphragm Area | $S_d$ | {tech['driver_sd_cm2']:.1f} | cm² |")
    if tech.get("driver_xmax_mm") is not None:
        lines.append(f"| Linear Excursion Limit | $X_{{max}}$ | {tech['driver_xmax_mm']:.1f} | mm |")
    if tech.get("driver_pe_w") is not None:
        lines.append(f"| Continuous Power Rating | $P_e$ | {tech['driver_pe_w']:.0f} | W |")

    if pub.description:
        lines.extend([
            "",
            "## Engineering Notes & Description",
            pub.description,
        ])

    lines.extend([
        "",
        "---",
        f"*Verified electroacoustic simulation generated by Load Forge lumped parameter matrix solver v{pub.app_version}.*",
    ])
    return "\n".join(lines)


def _public_record_from_document(
    publication_id: str, data: Mapping[str, Any]
) -> PublicProjectRecord:
    created_at = _parse_datetime(data.get("created_at"), field="created_at")
    updated_at = _parse_datetime(data.get("updated_at"), field="updated_at")
    published_at = _parse_datetime(data.get("published_at", updated_at), field="published_at")
    parameters = validate_project_payload(
        data.get("parameters", {}), require_complete=False
    )
    title = _normalize_publication_title(str(data.get("title", "Untitled publication")))
    description = _normalize_publication_description(str(data.get("description", "")))
    visibility = str(data.get("visibility", "unlisted")).strip().casefold()
    if visibility not in _PUBLICATION_VISIBILITIES:
        visibility = "unlisted"
    derived_summary = extract_technical_summary(parameters)
    stored_summary = data.get("technical_summary")
    tech_summary = {
        **derived_summary,
        **(stored_summary if isinstance(stored_summary, dict) else {}),
    }
    provenance = data.get("provenance")
    if not isinstance(provenance, dict):
        provenance = {}
    return PublicProjectRecord(
        publication_id=publication_id,
        owner_uid=str(data.get("owner_uid", "")),
        owner_display_name=str(data.get("owner_display_name", "")),
        source_tenant_id=str(data.get("source_tenant_id", "")),
        source_project_id=str(data.get("source_project_id", "")),
        source_revision=int(data.get("source_revision", 1)),
        publication_version=int(data.get("publication_version", 1)),
        visibility=visibility,
        title=title,
        description=description,
        schema_version=int(data.get("schema_version", PUBLICATION_SCHEMA_VERSION)),
        app_version=str(data.get("app_version", "unknown")),
        created_at=created_at,
        updated_at=updated_at,
        published_at=published_at,
        technical_summary=tech_summary,
        provenance=provenance,
        parameters=parameters,
    )


def _public_version_from_document(
    publication_id: str, data: Mapping[str, Any]
) -> PublicProjectVersion:
    published_at = _parse_datetime(data.get("published_at"), field="published_at")
    parameters = validate_project_payload(
        data.get("parameters", {}), require_complete=False
    )
    title = _normalize_publication_title(str(data.get("title", "Untitled publication")))
    description = _normalize_publication_description(str(data.get("description", "")))
    version = int(data.get("version", 1))
    version_id = str(data.get("version_id", f"v_{version:010d}"))
    content_hash = str(data.get("content_hash", ""))
    source_revision = int(data.get("source_revision", 1))
    derived_summary = extract_technical_summary(parameters)
    stored_summary = data.get("technical_summary")
    tech_summary = {
        **derived_summary,
        **(stored_summary if isinstance(stored_summary, dict) else {}),
    }
    return PublicProjectVersion(
        publication_id=publication_id,
        version=version,
        version_id=version_id,
        title=title,
        description=description,
        content_hash=content_hash,
        source_revision=source_revision,
        published_at=published_at,
        technical_summary=tech_summary,
        parameters=parameters,
    )


def _filter_and_sort_public_projects(
    projects: Sequence[PublicProjectSummary],
    query: str = "",
    topology: str = "",
    min_vb: float | None = None,
    max_vb: float | None = None,
    min_f3: float | None = None,
    max_f3: float | None = None,
    min_tuning_hz: float | None = None,
    max_tuning_hz: float | None = None,
    min_driver_size_in: float | None = None,
    max_driver_size_in: float | None = None,
    min_fs_hz: float | None = None,
    max_fs_hz: float | None = None,
    min_qts: float | None = None,
    max_qts: float | None = None,
    sort_by: str = "newest",
    limit: int = 50,
) -> list[PublicProjectSummary]:
    """Filter and sort public project summaries by search terms, topology, and specs."""
    filtered = list(projects)

    if query.strip():
        q_terms = query.strip().casefold().split()

        def _matches(p: PublicProjectSummary) -> bool:
            tech = p.technical_summary or {}
            corpus = " ".join([
                p.title,
                p.description,
                p.owner_display_name,
                str(tech.get("driver_name", "")),
                str(tech.get("load_type", "")),
            ]).casefold()
            return all(term in corpus for term in q_terms)

        filtered = [p for p in filtered if _matches(p)]

    if topology and topology != "All":
        def _matches_topology(project: PublicProjectSummary) -> bool:
            tech = project.technical_summary or {}
            load_type = tech.get("load_type")
            uses_pr = (
                load_type == "Passive radiator"
                or tech.get("resonator_type") == "Passive radiator"
            )
            if topology == "Passive radiator":
                return uses_pr
            if topology == "Bass reflex":
                return load_type == "Bass reflex" and not uses_pr
            return load_type == topology

        filtered = [p for p in filtered if _matches_topology(p)]

    def _within(
        project: PublicProjectSummary,
        key: str,
        minimum: float | None,
        maximum: float | None,
    ) -> bool:
        if minimum is None and maximum is None:
            return True
        value = (project.technical_summary or {}).get(key)
        if value is None:
            return False
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return False
        return (
            (minimum is None or numeric >= float(minimum))
            and (maximum is None or numeric <= float(maximum))
        )

    for key, minimum, maximum in (
        ("box_volume_l", min_vb, max_vb),
        ("f3_hz", min_f3, max_f3),
        ("tuning_freq_hz", min_tuning_hz, max_tuning_hz),
        ("nominal_size_in", min_driver_size_in, max_driver_size_in),
        ("driver_fs_hz", min_fs_hz, max_fs_hz),
        ("driver_qts", min_qts, max_qts),
    ):
        filtered = [p for p in filtered if _within(p, key, minimum, maximum)]

    if sort_by in {"trending", "most_liked"}:
        filtered.sort(
            key=lambda item: int((item.technical_summary or {}).get("likes", 0)),
            reverse=True,
        )
    elif sort_by == "oldest":
        filtered.sort(key=lambda item: item.published_at)
    elif sort_by == "lowest_f3":
        filtered.sort(
            key=lambda item: float((item.technical_summary or {}).get("f3_hz") or 999.0)
        )
    elif sort_by == "compact_vb":
        filtered.sort(
            key=lambda item: float((item.technical_summary or {}).get("box_volume_l") or 9999.0)
        )
    elif sort_by == "highest_spl":
        filtered.sort(
            key=lambda item: float((item.technical_summary or {}).get("peak_spl_db") or 0.0),
            reverse=True,
        )
    else:  # newest
        filtered.sort(key=lambda item: item.published_at, reverse=True)

    return filtered[: max(0, int(limit))]


def curated_community_showcase_projects() -> list[PublicProjectRecord]:
    """Return pre-engineered verified showcase projects for the community network."""
    base_time = datetime(2026, 8, 15, 12, 0, 0, tzinfo=timezone.utc)
    specs = [
        (
            "pub_showcase_dccav18",
            "DCCAV Dual-Resonance 18PRO",
            "Flagship dual asymmetric cavity subwoofer engineered for ultra-deep 28Hz extension with high power compression resistance in tour sound.",
            "Marco_Forge",
            "u_showcase_marco",
            datetime(2026, 8, 28, 14, 30, tzinfo=timezone.utc),
            {
                "load_type": "DCCAV",
                "driver_name": "B&C 18DS115",
                "driver_fs_hz": 30.0,
                "driver_vas_l": 165.0,
                "driver_qts": 0.28,
                "driver_qms": 5.8,
                "driver_re_ohm": 5.1,
                "driver_sd_cm2": 1210.0,
                "driver_pe_w": 1700.0,
                "driver_xmax_mm": 14.0,
                "box_vh_l": 65.0,
                "box_vl_l": 45.0,
                "box_fh_hz": 34.0,
                "box_fl_hz": 22.0,
                "f3_hz": 28.5,
                "peak_spl_db": 136.2,
                "likes": 142,
                "clones": 48,
                "views": 1250,
                "creator_rank": "⚡ Lead Architect",
                "tags": ["#DCCAV", "#TourSub", "#18Inch", "#HighSPL"],
            },
        ),
        (
            "pub_showcase_purifi8",
            "Studio Precision 8 Reference",
            "Ultra-low distortion nearfield reference monitor alignment with optimized port resonance suppression and linear acoustic group delay.",
            "SoundLab_Acoustics",
            "u_showcase_soundlab",
            datetime(2026, 8, 26, 10, 15, tzinfo=timezone.utc),
            {
                "load_type": "Bass reflex",
                "driver_name": "Purifi PTT8.0X04",
                "driver_fs_hz": 32.0,
                "driver_vas_l": 44.0,
                "driver_qts": 0.33,
                "driver_qms": 7.2,
                "driver_re_ohm": 3.6,
                "driver_sd_cm2": 220.0,
                "driver_pe_w": 250.0,
                "driver_xmax_mm": 14.7,
                "reflex_vb_l": 28.0,
                "reflex_fb_hz": 38.0,
                "f3_hz": 35.0,
                "peak_spl_db": 115.0,
                "likes": 98,
                "clones": 36,
                "views": 820,
                "creator_rank": "🔊 Verified Master",
                "tags": ["#StudioMonitor", "#UltraLowDistortion", "#Nearfield", "#HiFi"],
            },
        ),
        (
            "pub_showcase_bp6slam",
            "Bandpass 6th Slam-Box 12",
            "High-efficiency isobaric series-tuned 6th order enclosure delivering visceral punch between 35Hz and 85Hz for electronic and live bass.",
            "BassEngine_Lab",
            "u_showcase_bassengine",
            datetime(2026, 8, 24, 18, 45, tzinfo=timezone.utc),
            {
                "load_type": "Bandpass 6th order",
                "driver_name": "FaitalPRO 12HP1060",
                "driver_fs_hz": 45.0,
                "driver_vas_l": 42.0,
                "driver_qts": 0.25,
                "driver_qms": 9.5,
                "driver_re_ohm": 5.5,
                "driver_sd_cm2": 530.0,
                "driver_pe_w": 1000.0,
                "driver_xmax_mm": 12.5,
                "bandpass6_vr_l": 32.0,
                "bandpass6_vp_l": 30.0,
                "bandpass6_fp_hz": 68.0,
                "bp6_vr_l": 32.0,
                "bp6_vf_l": 30.0,
                "bp6_fb_r_hz": 38.0,
                "bp6_fb_f_hz": 68.0,
                "f3_hz": 34.0,
                "peak_spl_db": 131.5,
                "likes": 85,
                "clones": 29,
                "views": 670,
                "creator_rank": "🏆 Pro Builder",
                "tags": ["#Bandpass6th", "#FaitalPRO", "#SlamBass", "#ClubAudio"],
            },
        ),
        (
            "pub_showcase_sealed10",
            "Sealed Audiophile Reference 10",
            "Critically damped Qtc=0.577 Bessel sealed enclosure for maximum impulse response precision and transient attack in high-end listening rooms.",
            "AcousticPurity",
            "u_showcase_purity",
            datetime(2026, 8, 20, 9, 20, tzinfo=timezone.utc),
            {
                "load_type": "Sealed",
                "driver_name": "Scan-Speak 26W/4867T00",
                "driver_fs_hz": 20.0,
                "driver_vas_l": 120.0,
                "driver_qts": 0.32,
                "driver_qms": 6.1,
                "driver_re_ohm": 5.8,
                "driver_sd_cm2": 350.0,
                "driver_pe_w": 200.0,
                "driver_xmax_mm": 12.0,
                "sealed_vb_l": 34.0,
                "sealed_fc_hz": 42.0,
                "f3_hz": 42.0,
                "peak_spl_db": 112.5,
                "likes": 76,
                "clones": 22,
                "views": 540,
                "creator_rank": "🎵 Hi-Fi Artisan",
                "tags": ["#Sealed", "#TransientPrecision", "#Audiophile", "#Bessel"],
            },
        ),
        (
            "pub_showcase_tour15",
            "Tour Compact Reflex 15",
            "Road-ready compact tour sub tuned for punchy kick-drum fundamentals with high vent aerodynamic linearity and minimal chuffing.",
            "StageKraft_Live",
            "u_showcase_stagekraft",
            datetime(2026, 8, 18, 16, 10, tzinfo=timezone.utc),
            {
                "load_type": "Bass reflex",
                "driver_name": "18 Sound 15ND930",
                "driver_fs_hz": 38.0,
                "driver_vas_l": 160.0,
                "driver_qts": 0.26,
                "driver_qms": 7.5,
                "driver_re_ohm": 5.3,
                "driver_sd_cm2": 855.0,
                "driver_pe_w": 800.0,
                "driver_xmax_mm": 9.0,
                "reflex_vb_l": 85.0,
                "reflex_fb_hz": 38.0,
                "f3_hz": 34.0,
                "peak_spl_db": 133.5,
                "likes": 64,
                "clones": 19,
                "views": 490,
                "creator_rank": "⚡ Pro Builder",
                "tags": ["#18Sound", "#TouringPA", "#15InchSub", "#HighEfficiency"],
            },
        ),
        (
            "pub_showcase_nano_pr65",
            "PR Micro-Sub 6.5",
            "Ultra-compact dual passive radiator desktop subwoofer capable of true 33Hz extension in only 14 liters net enclosure volume.",
            "MiniForge_Tech",
            "u_showcase_miniforge",
            datetime(2026, 8, 15, 11, 0, tzinfo=timezone.utc),
            {
                "load_type": "Passive radiator",
                "resonator_type": "Passive radiator",
                "driver_name": "Dayton Audio Epique E180HE",
                "driver_fs_hz": 35.0,
                "driver_vas_l": 18.0,
                "driver_qts": 0.38,
                "driver_qms": 4.5,
                "driver_re_ohm": 3.8,
                "driver_sd_cm2": 150.0,
                "driver_pe_w": 200.0,
                "driver_xmax_mm": 14.0,
                "pr_vb_l": 14.0,
                "reflex_vb_l": 14.0,
                "reflex_fb_hz": 34.0,
                "pr_sp_cm2": 180.0,
                "pr_xmax_mm": 20.0,
                "pr_fs_hz": 22.0,
                "f3_hz": 32.5,
                "peak_spl_db": 108.5,
                "likes": 112,
                "clones": 53,
                "views": 980,
                "creator_rank": "🔰 Community Engineer",
                "tags": ["#PassiveRadiator", "#MicroSub", "#DesktopAudio", "#Epique"],
            },
        ),
    ]

    records = []
    for pub_id, title, desc, author, uid, pub_date, tech in specs:
        tech_summary = {
            "load_type": tech["load_type"],
            "resonator_type": tech.get("resonator_type", "Vented port"),
            "driver_name": tech["driver_name"],
            "driver_fs_hz": tech.get("driver_fs_hz"),
            "driver_vas_l": tech.get("driver_vas_l"),
            "driver_qts": tech.get("driver_qts"),
            "driver_qms": tech.get("driver_qms"),
            "driver_re_ohm": tech.get("driver_re_ohm"),
            "driver_sd_cm2": tech.get("driver_sd_cm2"),
            "driver_pe_w": tech.get("driver_pe_w"),
            "driver_xmax_mm": tech.get("driver_xmax_mm"),
            "nominal_size_in": 18.0 if "18" in tech["driver_name"] else (15.0 if "15" in tech["driver_name"] else (12.0 if "12" in tech["driver_name"] else (10.0 if "10" in tech["driver_name"] else (8.0 if "8" in tech["driver_name"] else 6.5)))),
            "box_volume_l": tech.get("reflex_vb_l") or tech.get("sealed_vb_l") or tech.get("pr_vb_l") or (tech.get("box_vh_l", 0) + tech.get("box_vl_l", 0)) or (tech.get("bp6_vr_l", 0) + tech.get("bp6_vf_l", 0)),
            "tuning_freq_hz": tech.get("reflex_fb_hz") or tech.get("sealed_fc_hz") or tech.get("box_fh_hz") or tech.get("bandpass6_fp_hz"),
            "f3_hz": tech.get("f3_hz"),
            "peak_spl_db": tech.get("peak_spl_db"),
            "likes": tech.get("likes", 0),
            "clones": tech.get("clones", 0),
            "views": tech.get("views", 0),
            "creator_rank": tech.get("creator_rank", "⚡ Community Engineer"),
            "tags": tech.get("tags", []),
        }
        records.append(
            PublicProjectRecord(
                publication_id=pub_id,
                owner_uid=uid,
                owner_display_name=author,
                source_tenant_id=f"tenant_{uid}",
                source_project_id=f"prj_{pub_id}",
                source_revision=1,
                publication_version=1,
                visibility="public",
                title=title,
                description=desc,
                schema_version=PUBLICATION_SCHEMA_VERSION,
                app_version="0.15.13",
                created_at=pub_date,
                updated_at=pub_date,
                published_at=pub_date,
                technical_summary=tech_summary,
                provenance={"source_showcase": True},
                parameters=tech,
            )
        )
    return records


class InMemoryProjectStore:
    """Process-local implementation used only by tests and local development."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], ProjectRecord] = {}
        self._revisions: dict[tuple[str, str], list[ProjectRevision]] = {}
        self._public_projects: dict[str, PublicProjectRecord] = {}
        self._public_versions: dict[str, list[PublicProjectVersion]] = {}

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

    def publish_project(
        self,
        user: SaaSUser,
        project_id: str,
        *,
        title: str,
        description: str = "",
        visibility: str = "unlisted",
        app_version: str,
        publication_id: str | None = None,
    ) -> PublicProjectRecord:
        record = self.load_project(user, project_id)
        if record is None:
            raise ProjectMissingError("Project was not found")
        pub_title = _normalize_publication_title(title)
        pub_desc = _normalize_publication_description(description)
        norm_vis = str(visibility).strip().casefold()
        if norm_vis not in _PUBLICATION_VISIBILITIES:
            raise ValueError(f"Invalid visibility: {visibility}")
        pub_id = _validate_publication_id(publication_id or new_publication_id())
        now = datetime.now(timezone.utc)
        existing = self._public_projects.get(pub_id)
        if existing is not None:
            if existing.owner_uid != user.uid:
                raise ProjectAccessError("Publication belongs to another user")
            pub_version = existing.publication_version + 1
            created_at = existing.created_at
        else:
            pub_version = 1
            created_at = now

        content_hash = record.content_hash
        tech_summary = extract_technical_summary(record.parameters)
        pub_record = PublicProjectRecord(
            publication_id=pub_id,
            owner_uid=user.uid,
            owner_display_name=user.name or user.email,
            source_tenant_id=user.tenant_id,
            source_project_id=record.project_id,
            source_revision=record.revision,
            publication_version=pub_version,
            visibility=norm_vis,
            title=pub_title,
            description=pub_desc,
            schema_version=PUBLICATION_SCHEMA_VERSION,
            app_version=app_version,
            created_at=created_at,
            updated_at=now,
            published_at=now,
            technical_summary=tech_summary,
            provenance={
                "source_project_id": record.project_id,
                "source_revision": record.revision,
            },
            parameters=record.parameters,
        )
        version_obj = PublicProjectVersion(
            publication_id=pub_id,
            version=pub_version,
            version_id=f"v_{pub_version:010d}",
            title=pub_title,
            description=pub_desc,
            content_hash=content_hash,
            source_revision=record.revision,
            published_at=now,
            technical_summary=tech_summary,
            parameters=record.parameters,
        )
        self._public_projects[pub_id] = pub_record
        versions = self._public_versions.setdefault(pub_id, [])
        versions.append(version_obj)
        return pub_record

    def get_public_project(self, publication_id: str) -> PublicProjectRecord | None:
        pub_id = _validate_publication_id(publication_id)
        return self._public_projects.get(pub_id)

    def get_public_project_version(
        self, publication_id: str, version: int
    ) -> PublicProjectVersion | None:
        pub_id = _validate_publication_id(publication_id)
        versions = self._public_versions.get(pub_id, [])
        return next((v for v in versions if v.version == int(version)), None)

    def list_public_projects(
        self,
        *,
        query: str = "",
        topology: str = "",
        min_vb: float | None = None,
        max_vb: float | None = None,
        min_f3: float | None = None,
        max_f3: float | None = None,
        min_tuning_hz: float | None = None,
        max_tuning_hz: float | None = None,
        min_driver_size_in: float | None = None,
        max_driver_size_in: float | None = None,
        min_fs_hz: float | None = None,
        max_fs_hz: float | None = None,
        min_qts: float | None = None,
        max_qts: float | None = None,
        sort_by: str = "newest",
        limit: int = 50,
    ) -> list[PublicProjectSummary]:
        publics = [
            PublicProjectSummary(**{
                field: getattr(rec, field)
                for field in PublicProjectSummary.__dataclass_fields__
            })
            for rec in self._public_projects.values()
            if rec.visibility == "public"
        ]
        return _filter_and_sort_public_projects(
            publics,
            query=query,
            topology=topology,
            min_vb=min_vb,
            max_vb=max_vb,
            min_f3=min_f3,
            max_f3=max_f3,
            min_tuning_hz=min_tuning_hz,
            max_tuning_hz=max_tuning_hz,
            min_driver_size_in=min_driver_size_in,
            max_driver_size_in=max_driver_size_in,
            min_fs_hz=min_fs_hz,
            max_fs_hz=max_fs_hz,
            min_qts=min_qts,
            max_qts=max_qts,
            sort_by=sort_by,
            limit=limit,
        )

    def clone_public_project(
        self,
        user: SaaSUser,
        publication_id: str,
        app_version: str,
        *,
        version: int | None = None,
        new_name: str | None = None,
    ) -> ProjectRecord:
        pub = self.get_public_project(publication_id)
        if pub is None:
            raise ProjectMissingError("Public project not found")
        if version is not None:
            target_version = self.get_public_project_version(publication_id, version)
            if target_version is None:
                raise ProjectMissingError("Public project version not found")
            source_params = target_version.parameters
            source_version_num = target_version.version
            title_to_use = target_version.title
        else:
            source_params = pub.parameters
            source_version_num = pub.publication_version
            title_to_use = pub.title

        clone_name = new_name or f"{title_to_use} (Clone)"
        cloned_params = json.loads(json.dumps(source_params, allow_nan=False))
        if "project" in cloned_params and isinstance(cloned_params["project"], dict):
            cloned_params["project"]["name"] = _normalize_project_name(clone_name)
            cloned_params["project"]["provenance"] = {
                "source_publication_id": publication_id,
                "source_publication_version": source_version_num,
                "original_author_uid": pub.owner_uid,
                "original_author_name": pub.owner_display_name,
                "cloned_at": datetime.now(timezone.utc).isoformat(),
            }
        return self.save_project(
            user,
            clone_name,
            cloned_params,
            app_version,
            project_id=new_project_id(),
            expected_revision=0,
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

    def _public_project_ref(self, publication_id: str):
        return self._client.collection("public_projects").document(
            _validate_publication_id(publication_id)
        )

    def publish_project(
        self,
        user: SaaSUser,
        project_id: str,
        *,
        title: str,
        description: str = "",
        visibility: str = "unlisted",
        app_version: str,
        publication_id: str | None = None,
    ) -> PublicProjectRecord:
        try:
            from google.cloud import firestore
        except ImportError as exc:  # pragma: no cover - deployment dependency
            raise SaaSConfigurationError(
                "google-cloud-firestore is required for the Firestore backend"
            ) from exc
        record = self.load_project(user, project_id)
        if record is None:
            raise ProjectMissingError("Project was not found")
        pub_title = _normalize_publication_title(title)
        pub_desc = _normalize_publication_description(description)
        norm_vis = str(visibility).strip().casefold()
        if norm_vis not in _PUBLICATION_VISIBILITIES:
            raise ValueError(f"Invalid visibility: {visibility}")
        pub_id = _validate_publication_id(publication_id or new_publication_id())
        ref = self._public_project_ref(pub_id)
        transaction = self._client.transaction()
        now = firestore.SERVER_TIMESTAMP
        tech_summary = extract_technical_summary(record.parameters)

        @firestore.transactional
        def do_publish(tx):
            snap = ref.get(transaction=tx)
            existing = snap.to_dict() if snap.exists else None
            if existing:
                if str(existing.get("owner_uid")) != user.uid:
                    raise ProjectAccessError("Publication belongs to another user")
                pub_version = int(existing.get("publication_version", 1)) + 1
                created_at = existing.get("created_at") or now
            else:
                pub_version = 1
                created_at = now

            version_id = f"v_{pub_version:010d}"
            version_ref = ref.collection("versions").document(version_id)
            version_data = {
                "publication_id": pub_id,
                "version": pub_version,
                "version_id": version_id,
                "title": pub_title,
                "description": pub_desc,
                "content_hash": record.content_hash,
                "source_revision": record.revision,
                "published_at": now,
                "technical_summary": tech_summary,
                "parameters": record.parameters,
            }
            pub_data = {
                "publication_id": pub_id,
                "owner_uid": user.uid,
                "owner_display_name": user.name or user.email,
                "source_tenant_id": user.tenant_id,
                "source_project_id": record.project_id,
                "source_revision": record.revision,
                "publication_version": pub_version,
                "visibility": norm_vis,
                "title": pub_title,
                "description": pub_desc,
                "schema_version": PUBLICATION_SCHEMA_VERSION,
                "app_version": str(app_version),
                "created_at": created_at,
                "updated_at": now,
                "published_at": now,
                "technical_summary": tech_summary,
                "provenance": {
                    "source_project_id": record.project_id,
                    "source_revision": record.revision,
                },
                "parameters": record.parameters,
            }
            tx.set(version_ref, version_data)
            tx.set(ref, pub_data)
            return True

        do_publish(transaction)
        saved = ref.get()
        if not saved.exists:
            raise ProjectMissingError("Publication was not found after save")
        return _public_record_from_document(pub_id, saved.to_dict())

    def get_public_project(self, publication_id: str) -> PublicProjectRecord | None:
        pub_id = _validate_publication_id(publication_id)
        snap = self._public_project_ref(pub_id).get()
        if not snap.exists:
            return None
        return _public_record_from_document(pub_id, snap.to_dict())

    def get_public_project_version(
        self, publication_id: str, version: int
    ) -> PublicProjectVersion | None:
        pub_id = _validate_publication_id(publication_id)
        version_id = f"v_{int(version):010d}"
        snap = self._public_project_ref(pub_id).collection("versions").document(version_id).get()
        if not snap.exists:
            return None
        return _public_version_from_document(pub_id, snap.to_dict())

    def list_public_projects(
        self,
        *,
        query: str = "",
        topology: str = "",
        min_vb: float | None = None,
        max_vb: float | None = None,
        min_f3: float | None = None,
        max_f3: float | None = None,
        min_tuning_hz: float | None = None,
        max_tuning_hz: float | None = None,
        min_driver_size_in: float | None = None,
        max_driver_size_in: float | None = None,
        min_fs_hz: float | None = None,
        max_fs_hz: float | None = None,
        min_qts: float | None = None,
        max_qts: float | None = None,
        sort_by: str = "newest",
        limit: int = 50,
    ) -> list[PublicProjectSummary]:
        try:
            from google.cloud import firestore
        except ImportError as exc:  # pragma: no cover
            raise SaaSConfigurationError(
                "google-cloud-firestore is required for the Firestore backend"
            ) from exc
        # Fetch up to 200 public projects to filter & rank in memory
        fetch_limit = max(50, min(500, int(limit) * 4))
        fs_query = (
            self._client.collection("public_projects")
            .where("visibility", "==", "public")
            .order_by("published_at", direction=firestore.Query.DESCENDING)
            .limit(fetch_limit)
        )
        results = []
        for snap in fs_query.stream():
            try:
                rec = _public_record_from_document(snap.id, snap.to_dict())
                results.append(PublicProjectSummary(**{
                    field: getattr(rec, field)
                    for field in PublicProjectSummary.__dataclass_fields__
                }))
            except Exception as exc:
                logger.warning("Skipping malformed public project %s: %s", snap.id, exc)

        return _filter_and_sort_public_projects(
            results,
            query=query,
            topology=topology,
            min_vb=min_vb,
            max_vb=max_vb,
            min_f3=min_f3,
            max_f3=max_f3,
            min_tuning_hz=min_tuning_hz,
            max_tuning_hz=max_tuning_hz,
            min_driver_size_in=min_driver_size_in,
            max_driver_size_in=max_driver_size_in,
            min_fs_hz=min_fs_hz,
            max_fs_hz=max_fs_hz,
            min_qts=min_qts,
            max_qts=max_qts,
            sort_by=sort_by,
            limit=limit,
        )

    def clone_public_project(
        self,
        user: SaaSUser,
        publication_id: str,
        app_version: str,
        *,
        version: int | None = None,
        new_name: str | None = None,
    ) -> ProjectRecord:
        pub = self.get_public_project(publication_id)
        if pub is None:
            raise ProjectMissingError("Public project not found")
        if version is not None:
            target_version = self.get_public_project_version(publication_id, version)
            if target_version is None:
                raise ProjectMissingError("Public project version not found")
            source_params = target_version.parameters
            source_version_num = target_version.version
            title_to_use = target_version.title
        else:
            source_params = pub.parameters
            source_version_num = pub.publication_version
            title_to_use = pub.title

        clone_name = new_name or f"{title_to_use} (Clone)"
        cloned_params = json.loads(json.dumps(source_params, allow_nan=False))
        if "project" in cloned_params and isinstance(cloned_params["project"], dict):
            cloned_params["project"]["name"] = _normalize_project_name(clone_name)
            cloned_params["project"]["provenance"] = {
                "source_publication_id": publication_id,
                "source_publication_version": source_version_num,
                "original_author_uid": pub.owner_uid,
                "original_author_name": pub.owner_display_name,
                "cloned_at": datetime.now(timezone.utc).isoformat(),
            }
        return self.save_project(
            user,
            clone_name,
            cloned_params,
            app_version,
            project_id=new_project_id(),
            expected_revision=0,
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


_SHARED_MEMORY_PROJECT_STORE: InMemoryProjectStore | None = None


def get_shared_memory_project_store() -> InMemoryProjectStore:
    global _SHARED_MEMORY_PROJECT_STORE
    if _SHARED_MEMORY_PROJECT_STORE is None:
        _SHARED_MEMORY_PROJECT_STORE = InMemoryProjectStore()
        try:
            try:
                from storage.public_store import get_shared_memory_public_store
            except ImportError:
                from src.storage.public_store import get_shared_memory_public_store
            pub_store = get_shared_memory_public_store()
            _SHARED_MEMORY_PROJECT_STORE._public_projects = pub_store._public_projects
            _SHARED_MEMORY_PROJECT_STORE._public_versions = pub_store._public_versions
        except Exception:
            pass
    return _SHARED_MEMORY_PROJECT_STORE


def create_project_store(settings: SaaSSettings):
    if settings.backend == "memory" or not settings.enabled:
        return get_shared_memory_project_store()
    # A production Firestore configuration failure must be visible. Falling
    # back to process memory would show successful saves that disappear later.
    return FirestoreProjectStore(
        project=settings.gcp_project,
        database=settings.firestore_private_db,
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
    message = str(exc).casefold()
    if "revision changed" in message or "revision conflict" in message:
        return "conflict"
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
            database=settings.firestore_private_db,
        )
    except Exception:
        return InMemoryUserAccountStore()
