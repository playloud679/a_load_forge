# src/ui/account.py — auth gate and account stores

The public-store resource cache includes its source modification time as well
as the SaaS token, so a running server adopts publication access-control changes
on reload. Account and billing store policies are unchanged.

- `_render_local_account_gate` / `_render_auth_hero_and_badges` — login and
  registration UI for local accounts, OIDC and bypass modes. Registration is
  open to any valid email address (no invite code) and always collects the
  email before an account is created.
- `_resolve_saas_user` — resolves the current `SaaSUser` (or `None`); recovers
  OIDC identity from signed `_streamlit_user` cookie when Streamlit reconnects a
  pre-login session without updating `_user_info`; renders the gate and calls
  `st.stop()` when auth is required. There is no anonymous or guest identity:
  when authentication is enabled, visitors must sign in or register an email account, including Free users.
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

Local sign-in and registration set `_projects_after_login`; the entry router
honors the requested workspace or resumes engineering work. Sign-out clears the navigation choice and cached private
project summaries so the next login starts from that user’s projects.

Logout uses a local rerun for local accounts and returns directly through
Streamlit’s OAuth logout redirect for OIDC sessions. Calling a second rerun
after `st.logout()` can replace that redirect and leave the authenticated page
visible.

Google no longer publishes an `end_session_endpoint`, so `st.logout()` ends
only the Load Forge session while the browser keeps the Google SSO session. The
production `[auth]` secret sets `client_kwargs.prompt = "consent"` so every
sign-in shows Google’s confirmation screen and the next access cannot silently
reuse the previous identity; remounting the secret needs a new Cloud Run
revision. See `docs/deploy-cloudrun.md` for the secret layout.

In development auth-bypass mode, logout pauses the generated demo identity and
shows a signed-out screen with an explicit “Sign in again” action, instead of
recreating that identity on the next rerun.

OIDC sign-in preserves the portal destination through the short-lived navigation
cookie managed by [navigation](navigation.md); authentication itself is unchanged.

## Guest mode (`LOAD_FORGE_GUEST_ACCESS`, default on)

A signed-out visitor is a **guest** (`_runtime._GUEST = True`), not the local
demo user: `_get_current_user_account()` returns `None`, so guests never share
the local account or its credits and never reach the full Bass Match.

- Guests land in Box Design (portal `view=bass-match`/`projects` included) with
  a non-blocking invite (`invite_guest`, `render_guest_sign_in_invite`); the
  Bass Match and Projects tabs route through `state._select_workspace`, which
  keeps the guest in Box Design and shows the invite instead.
- `request_sign_in(reason)` (`save`, `bass_match`, `projects`, `account`)
  opens the sign-in page with reason-specific copy and a "Back to my design"
  button. The page renders no design widgets, and Streamlit drops the state of
  widgets a run does not render, so the design is snapshotted
  (`state._snapshot_design_state`) and restored on return or on same-session
  email sign-in.
- **Save → sign in → saved**: for `save`, the design (`d`, the share-link
  payload, ~1.3 kB) and the project `name` also go into the URL, hence into the
  10-minute return cookie across the Google redirect. The first signed-in run
  applies them and forces an autosave (`app.main`), then drops `name` from the URL.
- `_get_current_user_account()` memoises per **session** in `st.session_state`
  (cleared by `ui_app.py` right after resolving the user, before the first read
  of each run). It used a
  process-wide `functools.cache`, which could hand one user's account to a
  concurrent session.

Usage events: `guest_session`, `sign_in_invite_view`, `auth_gate_view`
(`props.reason`) — see [usage analytics](../usage_analytics.md).

## Administrators are Google-only

Email/password accounts are not email-verified, so anyone can register any
address. `_is_password_session()` is true for a production-style session that
signed in with the email/password form (not the local-accounts or bypass dev
modes); such sessions get no admin emails (`_account_admin_emails`) and
`catalog._maintenance_allowed` refuses them. The configured admin address
(`LOAD_FORGE_ADMIN_EMAIL`) cannot sign up or sign in with a password.
