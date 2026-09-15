# src/ui/account.py — auth gate and account stores

- `_render_local_account_gate` / `_render_auth_hero_and_badges` — login and
  registration UI for local accounts, OIDC and bypass modes. Registration is
  open to any valid email address (no invite code) and always collects the
  email before an account is created.
- `_resolve_saas_user` — resolves the current `SaaSUser` (or `None`); renders
  the gate and calls `st.stop()` when auth is required. There is no anonymous
  or guest identity: every visitor must sign in or register an email account,
  including Free users.
- `_remember_local_account` / `_sign_out_saas` — session transitions.
- Stores: `_get_account_store`, `_get_project_store`, `_get_public_store`
  (each `@st.cache_resource`, keyed by `_runtime._SAAS_SETTINGS` and
  `_runtime._SAAS_SOURCE_TOKEN`). The registration/login form uses
  `_saas.create_credential_store(_runtime._SAAS_SETTINGS)`: SQLite
  `LocalAccountStore` in memory/local dev modes, durable
  `FirestoreCredentialStore` on Firestore deployments.
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

## Project-first UX

Local sign-in and registration set `_projects_after_login` for a one-time
project-list landing. Sign-out clears the navigation choice and cached private
project summaries so the next login starts from that user’s projects.

Logout uses a local rerun for local accounts and returns directly through
Streamlit’s OAuth logout redirect for OIDC sessions. Calling a second rerun
after `st.logout()` can replace that redirect and leave the authenticated page
visible.

In development auth-bypass mode, logout pauses the generated demo identity and
shows a signed-out screen with an explicit “Sign in again” action, instead of
recreating that identity on the next rerun.
