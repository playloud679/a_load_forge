# src/storage/_firestore_client.py — client factory

`validate_database_name` strips whitespace and accepts `(default)` or 4–63
lowercase alphanumeric characters with internal hyphens. Invalid values raise
`SaaSConfigurationError`.

`get_firestore_client(project=..., database=..., client=...)` returns an injected
client unchanged, without revalidating its database. Otherwise it validates the
database and lazily constructs a Google Firestore client. A missing dependency
raises `SaaSConfigurationError`; initialization failures are logged and reraised.
There is no implicit client cache or fallback to in-memory storage here.

See [../storage.md](../storage.md) and `tests/test_storage_boundaries.py` for
domain configuration and isolation checks.
