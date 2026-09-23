# src/storage/catalog_staging_store.py — untrusted ingestion workspace

`CatalogStagingStore` saves candidates, ingestion-run metadata/results,
validation results and rejected records. It provides run lookup/listing and
candidate lookup by run. Both Firestore and process-local memory implementations
are available; the factory uses memory for absent/disabled/memory settings.

Firestore writes are confined to `catalog_candidates`, `ingestion_runs`,
`validation_results` and `rejected_records`. A missing run returns `None`.
Saving a candidate does not validate its acoustic values, publish it or promote
it into the runtime catalog. Ordinary UI/Bass Match flows must not query this
untrusted workspace.

The autonomous crawler lives in the separate `load_forge_crawler` repository;
this module remains the app repository's storage boundary. See
[../storage.md](../storage.md) and `tests/test_storage_boundaries.py`.
