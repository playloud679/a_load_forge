"""Load Forge multi-database data architecture and domain storage facade.

Explicit storage boundaries:
- PrivateStore (lf-private): Authenticated tenant projects, revisions, user accounts, credits.
- PublicStore (lf-public): Community publications, public project versions, galleries, discovery.
- CatalogRuntimeStore (lf-catalog-runtime): Trusted canonical driver catalog, releases, Bass Match driver source.
- CatalogStagingStore (lf-catalog-staging): Untrusted crawler ingestion workspace, runs, candidates.
"""

from __future__ import annotations

from ._firestore_client import get_firestore_client, validate_database_name
from .catalog_runtime_store import (
    CatalogRuntimeStore,
    FirestoreCatalogRuntimeStore,
    InMemoryCatalogRuntimeStore,
    create_catalog_runtime_store,
    get_shared_memory_catalog_runtime_store,
)
from .catalog_staging_store import (
    CatalogStagingStore,
    FirestoreCatalogStagingStore,
    InMemoryCatalogStagingStore,
    create_catalog_staging_store,
    get_shared_memory_catalog_staging_store,
)
from .private_store import (
    FirestorePrivateStore,
    InMemoryPrivateStore,
    PrivateStore,
    create_private_store,
    get_shared_memory_private_store,
)
from .public_store import (
    FirestorePublicStore,
    InMemoryPublicStore,
    PublicStore,
    create_public_store,
    get_shared_memory_public_store,
)

__all__ = (
    "validate_database_name",
    "get_firestore_client",
    "PrivateStore",
    "FirestorePrivateStore",
    "InMemoryPrivateStore",
    "create_private_store",
    "get_shared_memory_private_store",
    "PublicStore",
    "FirestorePublicStore",
    "InMemoryPublicStore",
    "create_public_store",
    "get_shared_memory_public_store",
    "CatalogRuntimeStore",
    "FirestoreCatalogRuntimeStore",
    "InMemoryCatalogRuntimeStore",
    "create_catalog_runtime_store",
    "get_shared_memory_catalog_runtime_store",
    "CatalogStagingStore",
    "FirestoreCatalogStagingStore",
    "InMemoryCatalogStagingStore",
    "create_catalog_staging_store",
    "get_shared_memory_catalog_staging_store",
)
