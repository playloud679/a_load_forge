# Multi-Database Storage Architecture & Domain Boundaries

`src/storage/` defines the hardened multi-database storage architecture for Load Forge. It provides explicit repository and domain boundaries across four distinct Firestore data domains.

## Target Data Domains

| Domain | Database | Environment Variable | Responsibility | Principals & Permissions |
|---|---|---|---|---|
| **Private** | `lf-private` | `LF_FIRESTORE_PRIVATE_DB` | Authenticated tenant projects, revisions, user accounts, and credits | App Service Account (Read/Write, auth context only) |
| **Public** | `lf-public` | `LF_FIRESTORE_PUBLIC_DB` | Community project publications, versions, galleries, discovery | App Service Account (Controlled Read/Write), Public Service SA |
| **Catalog Runtime** | `lf-catalog-runtime` | `LF_FIRESTORE_CATALOG_RUNTIME_DB` | Trusted canonical driver catalog, releases, Bass Match driver source | App SA (Read-Only), Catalog Promoter SA (Controlled Write) |
| **Catalog Staging** | `lf-catalog-staging` | `LF_FIRESTORE_CATALOG_STAGING_DB` | Untrusted crawler ingestion workspace, runs, candidates | Crawler Agent SA (Read/Write), Promoter SA (Read) |

## Storage Modules

### `private_store.py`
- Implements `PrivateStore`, `FirestorePrivateStore`, `InMemoryPrivateStore`.
- Manages tenant projects (`tenants/{tenant_id}/projects/{project_id}`) and revision history (`revisions/{rev_id}`).
- Manages user account states and credits balances (`users/{email_or_uid}`).
- Encapsulates optimistic locking via expected revisions and content hash deduplication.
- Strictly isolated: does not expose public publication paths.

### `public_store.py`
- Implements `PublicStore`, `FirestorePublicStore`, `InMemoryPublicStore`.
- Manages immutable publication snapshots (`public_projects/{publication_id}`) and versions (`versions/{version_id}`).
- Provides gallery discovery, topology filters, volume/F3 range filters, and search indexing.
- Supports cross-domain project cloning via explicit two-store orchestration (`clone_public_project(..., private_store=...)`).
- Strictly isolated: does not expose private project documents or user billing records.

### `catalog_runtime_store.py`
- Implements `CatalogRuntimeStore`, `FirestoreCatalogRuntimeStore`, `InMemoryCatalogRuntimeStore`.
- Provides read-only query APIs for runtime application flows (`get_driver`, `search_drivers`, `list_drivers`).
- Manages versioned catalog releases (`releases/{release_id}`) and active release pointers (`catalog_metadata/active_release`).
- Supports atomic promotion and release rollback (`rollback_release`).

### `catalog_staging_store.py`
- Implements `CatalogStagingStore`, `FirestoreCatalogStagingStore`, `InMemoryCatalogStagingStore`.
- Disposable workspace for crawler agents (`catalog_candidates/`, `ingestion_runs/`, `validation_results/`, `rejected_records/`).
- Never queried by ordinary Load Forge UI or Bass Match runtime.

### `_firestore_client.py`
- Centralized client factory (`get_firestore_client`).
- Validates database names (`^[a-z0-9][a-z0-9-]{2,61}[a-z0-9]$` or `(default)`).
- Prevents scattered, uncontrolled `firestore.Client` calls.

## Configuration & Environment Variables

```text
# Domain database identifiers (defaulting to '(default)' for dev/backward compatibility)
LF_FIRESTORE_PRIVATE_DB=lf-private
LF_FIRESTORE_PUBLIC_DB=lf-public
LF_FIRESTORE_CATALOG_RUNTIME_DB=lf-catalog-runtime
LF_FIRESTORE_CATALOG_STAGING_DB=lf-catalog-staging

# Strict multi-database enforcement (fails if any domain uses '(default)')
LOAD_FORGE_STRICT_MULTI_DB=true
```

## Invariants
1. Crawler agents cannot import or access `PrivateStore` or `PublicStore`.
2. Public gallery queries never access `tenants/` or `users/` collections.
3. Private project autosave touches only `lf-private` storage.
4. Publishing is an explicit snapshot operation and never mutates historical private revisions.
5. Catalog promotion requires versioned release manifests and explicit approval.

## Infrastructure & Runbooks
- **IAM & Provisioning**: [`infra/setup_multi_database_iam.sh`](../infra/setup_multi_database_iam.sh)
- **Backup & PITR**: [`infra/backup_schedules.sh`](../infra/backup_schedules.sh)
- **Operational Runbooks**: [`docs/runbooks_multi_database_ops.md`](runbooks_multi_database_ops.md)
- **Migration Tools**: [`tools/migrate_private_data.py`](../tools/migrate_private_data.py) and [`tools/migrate_public_projects.py`](../tools/migrate_public_projects.py)
- **Promotion Pipeline**: [`tools/promote_catalog_release.py`](../tools/promote_catalog_release.py)

