# `src/storage/private_store.py`

Private Firestore and in-memory backends implement tenant project persistence,
immutable revisions, Trash, and account/credit operations. See
[storage architecture](../storage.md) and [SaaS contracts](../saas.md).

`get_or_create_account` derives `is_admin` from exact case-insensitive membership
in its explicit `admin_emails` argument using `saas.account_is_admin`. Each read
reconciles an existing flag, including revoking grants made by obsolete rules.
Neither an email substring nor the application's login allowlist grants access.
Firestore performs this reconciliation in the account transaction; changes do
not touch project documents. The UI caches reads only within one script run
and clears that cache after account mutations.
