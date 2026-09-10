# src/ui/account.py — auth gate and account stores

- `_render_local_account_gate` / `_render_auth_hero_and_badges` — login and
  registration UI for local accounts, OIDC and bypass modes.
- `_resolve_saas_user` — resolves the current `SaaSUser` (or `None`); renders
  the gate and calls `st.stop()` when auth is required.
- `_remember_local_account` / `_sign_out_saas` — session transitions.
- Stores: `_get_account_store`, `_get_project_store`, `_get_public_store`
  (each `@st.cache_resource`, keyed by `_runtime._SAAS_SETTINGS` and
  `_runtime._SAAS_SOURCE_TOKEN`).
- `_account_admin_emails`, `_get_current_user_account` — entitlement helpers.

## Invariants

- All globals come from `runtime` (`_runtime._SAAS_SETTINGS`, ...); never
  copy them into module constants, because they change per rerun.
- `ui_app.py` calls `initialize_saas_settings()` before
  `_resolve_saas_user()` and `_get_account_store()`.
- The account store must remain tenant-safe: queries are always scoped by
  `uid`.

## Tests

`_check_saas_*`, `_check_account_admin_*`, and the cloud persistence tests
that import `ui_app._get_project_store()`.
