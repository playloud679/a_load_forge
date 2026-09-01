"""Centralized Firestore client factory and validation helpers."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

try:
    import saas
except ImportError:
    from src import saas  # type: ignore[no-redef]

logger = logging.getLogger("load_forge.storage")

# Valid Firestore database IDs are "(default)" or 4-63 lowercase alphanumeric with hyphens
_FIRESTORE_DB_RE = re.compile(r"^([a-z0-9][a-z0-9-]{2,61}[a-z0-9]|\(default\))$")


def validate_database_name(name: str) -> str:
    """Validate a Firestore database identifier."""
    val = str(name).strip()
    if not val:
        raise saas.SaaSConfigurationError("Firestore database name cannot be empty")
    if not _FIRESTORE_DB_RE.fullmatch(val):
        raise saas.SaaSConfigurationError(
            f"Invalid Firestore database name {val!r}. "
            "Must be '(default)' or 4-63 lowercase alphanumeric characters with hyphens."
        )
    return val


def get_firestore_client(
    *,
    project: str | None = None,
    database: str = "(default)",
    client: Any | None = None,
) -> Any:
    """Instantiate or return an explicit Firestore client bound to a single named database.

    Avoids scattering unrestricted generic client instantiations throughout the codebase.
    """
    if client is not None:
        return client

    db_name = validate_database_name(database)

    try:
        from google.cloud import firestore
    except ImportError as exc:  # pragma: no cover - deployment dependency
        raise saas.SaaSConfigurationError(
            "google-cloud-firestore is required for the Firestore backend"
        ) from exc

    try:
        client_instance = firestore.Client(project=project, database=db_name)
        logger.info(
            "Initialized Firestore client (project=%s, database=%s)",
            project or "(default-project)",
            db_name,
        )
        return client_instance
    except Exception as exc:
        logger.error(
            "Failed to initialize Firestore client (project=%s, database=%s): %s",
            project,
            db_name,
            exc,
        )
        raise
