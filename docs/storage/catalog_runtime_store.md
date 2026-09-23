# src/storage/catalog_runtime_store.py — trusted catalog storage

`CatalogRuntimeStore` exposes driver lookup/search/listing, release metadata,
promotion and rollback. Firestore and in-memory implementations share that
surface. The factory chooses the process-local shared memory store when settings
are absent, disabled or use the memory backend; otherwise it selects the
configured catalog-runtime database.

Ordinary UI use reads the catalog. Promotion belongs to the explicit promoter
workflow: see [../storage.md](../storage.md) for validation, approval and database
requirements. Firestore promotion normalizes imported provenance keys and hashes
model IDs containing path separators. Missing rollback targets raise
`ProjectMissingError`.

Rollback changes the active release pointer; it does not restore the contents
of the live `drivers` collection. In-memory promotion updates its driver map
and keeps release metadata, not historical full driver snapshots. Do not assume
these APIs implement a complete data rollback transaction.

`tests/test_storage_boundaries.py` exercises the domain surface and separation.
