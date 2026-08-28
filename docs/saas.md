# SaaS identity and project persistence

`src/saas.py` contains the framework-independent SaaS contract used by the
Streamlit UI.  It owns identity normalization, tenant isolation, plan
entitlements and persistent project records.  It must not import Streamlit.

## Activation

SaaS mode is opt-in so local acoustic development and the existing public
deployment remain unchanged:

```text
LOAD_FORGE_SAAS_ENABLED=true
LOAD_FORGE_OPEN_BETA_ENABLED=true
LOAD_FORGE_SAAS_BACKEND=firestore
LOAD_FORGE_GCP_PROJECT=civic-radio-502611-i8
LOAD_FORGE_FIRESTORE_DATABASE=(default)
```

`LOAD_FORGE_SAAS_BACKEND=memory` is available for tests and local UI
development only.  `LOAD_FORGE_AUTH_BYPASS=true` creates a local development
identity; `SaaSSettings` rejects that flag whenever Cloud Run's `K_SERVICE`
environment variable is present.

`LOAD_FORGE_OPEN_BETA_ENABLED=true` is a server-side promotional override.
It grants Free and Pro accounts the current Pro access tier and quotas while
leaving the account's stored plan unchanged; Team accounts retain their larger
limits. The UI labels this state as `Open Beta · full access`. Disabling the
flag therefore restores the normal plan entitlements without migrating users,
creating subscriptions or changing saved projects.

Authentication uses Streamlit's native OIDC support (`st.login`, `st.user`,
`st.logout`).  Mount a complete `secrets.toml` from Secret Manager at
`/app/.streamlit/secrets.toml`.  The tracked
`.streamlit/secrets.example.toml` documents the required keys without storing
credentials. The deployment requirements include both `Authlib` and `httpx`:
Authlib imports its optional HTTP client only when the first login begins, so
an image can otherwise start normally and fail late at the Sign in button.

Authentication can also be enabled independently from Firestore project
persistence. This is the recommended initial configuration for the private
Streamlit Community Cloud deployment:

```toml
LOAD_FORGE_AUTH_REQUIRED = "true"
LOAD_FORGE_ALLOWED_EMAILS = "owner@example.com,collaborator@example.com"

[auth]
redirect_uri = "https://load-forge.streamlit.app/oauth2callback"
cookie_secret = "replace-with-a-long-random-value"
client_id = "replace-with-google-oauth-client-id"
client_secret = "replace-with-google-oauth-client-secret"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
```

With `LOAD_FORGE_AUTH_REQUIRED=true` and `LOAD_FORGE_SAAS_ENABLED` unset, the
OIDC gate and exact case-insensitive email allowlist protect the workspace,
while projects remain entirely client-side via portable `.lfp` file export and import.
Commas, semicolons and newlines are accepted between addresses. An
empty `LOAD_FORGE_ALLOWED_EMAILS` permits every account authenticated by the
configured provider; malformed configured addresses fail closed at startup.

On Community Cloud these values belong at the root of the app's Secrets TOML,
before `[auth]`. The Google OAuth client must register the exact production
callback `https://load-forge.streamlit.app/oauth2callback`. Keep the app
private until this configuration has been tested; making it public before the
in-app gate is active would expose the workspace.

## Local registration demo

The complete account experience can be exercised locally without configuring
an external identity provider:

```text
LOAD_FORGE_SAAS_ENABLED=true
LOAD_FORGE_SAAS_BACKEND=memory
LOAD_FORGE_LOCAL_ACCOUNTS=true
LOAD_FORGE_LOCAL_ACCOUNT_DATABASE=.local/load_forge_accounts.sqlite3
```

This renders create-account, sign-in and sign-out flows. `LocalAccountStore`
normalizes emails, validates names and passwords, stores only salted scrypt
password hashes in a permission-restricted SQLite file and derives a separate
tenant from each stable account ID. Duplicate emails and invalid credentials
return generic user-facing errors.

Local accounts are a product-development surface, not the production identity
provider. `SaaSSettings` rejects both local accounts and the authentication
bypass whenever Cloud Run sets `K_SERVICE`. Production registration, email
verification, password recovery and MFA belong to the configured OIDC
provider.

## Identity and tenant contract

`user_from_claims()` requires a stable OIDC `sub`.  It reads `email`, `name`,
an optional `tenant_id` (or Firebase tenant claim) and an optional plan.  A
single-user tenant ID is derived from `sub` when no organization claim exists.
Unknown plans safely fall back to `free`.

The built-in entitlement seeds are:

| Plan | Saved projects | Monthly credits | Seats |
|---|---:|---:|---:|
| `free` | 3 | 100 | 1 |
| `pro` | 100 | 2,500 | 1 |
| `team` | 500 | 10,000 | 10 |

These values are server-side product defaults. Standard runs consume 1 credit per candidate; Deep runs consume 2 credits per candidate. `UserAccountStore` (backed by Firestore in production and memory in development) handles atomic credit deductions, monthly quota replenishment on the 1st of each month, and administrator management. Administrator accounts receive an automatic credit balance refill ($100,000+$) and are exempt from simulation credit blocking in Bass Match.

Editable multi-design comparison is available to every account tier. Free,
Pro and Team users may turn 2–8 selected Bass Match rows into independent Box
Design tabs or duplicate the active design into variants. New Finder
selections append to the existing design set up to the eight-tab limit; direct
duplicate and delete actions manage the active tab in Box Design. Comparison
availability is independent of stored plan and Open Beta entitlements.

New cloud-project records store the complete active Box Design parameter set
plus Bass Match controls, ranked candidates, result context and last-run
statistics. Loading a cloud project restores that last candidate list without
re-running the optimizer. Older cloud records containing only the flat design
parameter mapping remain readable. Large editable-comparison curve snapshots
stay in browser/portable LFP storage to keep cloud documents below their size
limit.

## Project contract

Projects are stored below:

```text
tenants/{tenant_id}/projects/{project_id}
```

Each document contains:

- display name, owner and tenant IDs;
- complete JSON-serializable Load Forge parameter mapping;
- application version;
- creation/update timestamps;
- monotonically increasing optimistic revision.

Project payloads are capped below Firestore's document ceiling.  Updates may
provide `expected_revision`; a stale write raises `ProjectConflictError`
instead of silently overwriting a newer design.

`InMemoryProjectStore` and `FirestoreProjectStore` expose the same
`save_project`, `load_project` and `list_projects` methods.  The UI must always
scope calls with the authenticated `SaaSUser`.
