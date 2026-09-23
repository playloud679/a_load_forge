# src/storage/__init__.py — storage facade

Re-exports the four domain protocols, Firestore/in-memory implementations,
factories, shared memory accessors and centralized client helpers through
`__all__`. Importing this facade does not authorize cross-domain access or
instantiate a Firestore client. Callers must select the appropriate store.

See [../storage.md](../storage.md) for database boundaries and settings, and the
per-module contracts in this directory. `tests/test_storage_boundaries.py`
checks storage separation; private/public workflows also run in `test_all.py`.
