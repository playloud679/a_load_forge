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
LF_FIRESTORE_PRIVATE_DB=lf-private
LF_FIRESTORE_PUBLIC_DB=lf-public
LF_FIRESTORE_CATALOG_RUNTIME_DB=lf-catalog-runtime
LF_FIRESTORE_CATALOG_STAGING_DB=lf-catalog-staging
LOAD_FORGE_PROJECT_TRASH_RETENTION_DAYS=30
```

`LF_FIRESTORE_*_DB` configuration variables establish dedicated data security boundaries across the private, public, catalog runtime, and crawler staging domains (see `docs/storage.md`). If unset, they safely default to `LOAD_FORGE_FIRESTORE_DATABASE` or `(default)` in local development. `LOAD_FORGE_STRICT_MULTI_DB=true` can be enabled to forbid the default database in multi-tenant environments.

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
parameter mapping remain readable. The canonical payload is size-checked below
Firestore's document limit before the transaction begins.

## Project contract

Firestore cloud autosave is the normal persistence mechanism for authenticated
users. `.lfp` export is the independent user-controlled backup/portability
mechanism.

If a cloud write exhausts its retry window, the project header reports the
classified cause (authentication, permissions, validation or connectivity) and
offers `Retry cloud save`; local session state and the last acknowledged cloud
revision remain available until the retry succeeds.

Bass Match result context is stored as a named object rather than an array
containing another array. Firestore rejects nested arrays, while older project
records using the legacy list shape remain readable during restore.

If another tab or device commits a newer revision during an autosave, the UI
rebases its optimistic revision marker and retries the local payload once. This
prevents a recoverable `revision changed from N to N+1` race from leaving the
project permanently in a failed-save state.

Autosave does not create a cloud record until the user supplies a project name.
Legacy records named `Untitled project`, created by older releases before the
required-name flow, are excluded from the active project browser. An unnamed
local draft is shown as `Name required`; `.lfp` export and duplication remain
disabled until it has a user-supplied name.

Saved Bass Match rows, run statistics and their input context are restored when
opening a project, including in a fresh Streamlit session. Finder defaults
migrations no longer clear a valid persisted result set during that restore.

```text
Authenticated user
    Streamlit project state
        -> debounced autosave
        -> Firestore current project
        -> immutable recoverable revisions

User-controlled backup
    project -> Export .lfp -> local user file
```

Projects retain the existing tenant path:

```text
tenants/{tenant_id}/projects/{project_id}
tenants/{tenant_id}/projects/{project_id}/revisions/rev_0000000001
```

The parent document is the active pointer and contains:

- `name`, `owner_uid`, `tenant_id`, `app_version`;
- canonical validated LFP payload in `parameters`;
- `revision` (legacy-reader alias) and `current_revision`;
- `schema_version` and semantic `content_hash`;
- server-generated `created_at` and `updated_at` timestamps;
- `status` (`active` or `trashed`) and nullable `deleted_at`.

Each revision document contains the full validated payload, revision number,
schema version, semantic hash, name and a Firestore server timestamp. Parent
and revision are written atomically in one transaction. Identical semantic
states are deduplicated. The in-memory backend enforces the most recent 30
revisions; production should retain the most recent 30 through a scheduled
maintenance job rather than deleting history in an interactive request.

Every write compares `expected_revision` with `current_revision` in the same
transaction. A stale browser receives `ProjectConflictError`; the UI preserves
its local state and offers either **Reload latest** or **Save as copy**. A
historical revision becomes current only through explicit `restore_revision`,
which creates a new current revision instead of rewriting history.

Autosave computes a semantic SHA-256 hash, marks changed state dirty, waits 1.5
seconds, and writes only if the state remains changed. A two-second Streamlit
fragment supplies the follow-up run when the user stops moving a slider.
Transient failures retry without sleeping at 2, 5 and 15 seconds. Permission,
authentication, malformed data and exhausted retries remain visibly failed;
`Saved ✓` is set only after the store returns an acknowledged record.

When a new or reset session has no named project, the Project panel opens and
prompts for a name other than `Untitled project`; opening an LFP or cloud project
then replaces that name with the imported/project name.

Project payloads are strict JSON (`allow_nan=False`), capped below Firestore's
document ceiling and validated before any active revision changes. Format 2
requires project metadata, a project name, `load_type`, the core driver fields
(`driver_fs_hz`, `driver_vas_l`, `driver_qts`, `driver_qms`, `driver_re_ohm`),
a supported schema version and object-shaped Bass Match state. Existing flat
Firestore documents and format-1 LFP files remain readable and migrate on the
next successful format-2 save.

## Delete, restore and portability

```text
Delete -> Trash / soft delete -> 30-day retention target -> operator cleanup
```

The normal Delete action never removes a Firestore document. It creates a new
revision with `status=trashed` and `deleted_at`, removes the project from the
normal list, and exposes **Restore from Trash**. Permanent cleanup is a separate
scheduled operator process. Its retention target is configured with
`LOAD_FORGE_PROJECT_TRASH_RETENTION_DAYS` (1–365, default 30). Cleanup must
select only records whose `status` is `trashed` and whose `deleted_at` is older
than that threshold; it must not run from the Streamlit Delete callback.

LFP format 2 remains cloud-independent and includes project identity, every
serializable Box Design parameter, editable comparison state, Bass Match
controls and saved results. Cloud IDs, revision numbers and Trash status are
not required to open the file offline. The UI records only when it generated a
download in the current session; it does not claim that the file still exists
## Information Architecture & Dedicated Manage Projects Workspace

Project lifecycle operations are decoupled from technical engineering sidebars
(Bass Match and Box Design) and concentrated into a dedicated first-class
workspace:

```text
Primary Navigation:
  Manage Projects | Bass Match | Box Design [ | Explore ]
```

- **Technical Sidebar Minimalism**: Inside Bass Match and Box Design, sidebars
  contain strictly technical engineering controls (driver parameters, load selection,
  filters, enclosure dimensions). Project management is represented solely by a compact
  Current Project header showing project name, live autosave status indicator
  (`Saved ✓` / `Saving…` / `Unsaved changes`), and a direct link to `Manage Projects →`.
- **Dedicated `Manage Projects` Page (`workspace_mode = "Manage Projects"`)**:
  - **Quick Action Toolbar**: `➕ New Project` (opens a blank required-name prompt before
    initializing a clean independent project),
    `📥 Import .lfp / .crw` (popover supporting `Import as New Project` and `Replace Active Project`),
    and `↻ Refresh`.
  - **Active Project Spotlight**: Hero card highlighting currently active project,
    real-time autosave status, electroacoustic parameter summary ($V_b, F_b, F_s, Q_{ts}$),
    primary CTAs (`Open in Box Design ⚡`, `Open in Bass Match 🔍`), backup export (`💾 Export .lfp`),
    duplication (`📋 Duplicate`), in-place rename, and shareable URL link generation.
  - **Cloud Projects Browser & History**:
    - `📂 Cloud Projects`: Table/Card grid of all active cloud projects with Name, Revision,
      Last Modified timestamp, cloud sync state, and quick actions (`Open`, `Duplicate`, `Trash`).
    - `🕒 Revision History`: Immutable snapshot timeline for the active project with `Restore Version`.
    - `🗑️ Trash`: Soft-deleted projects with 30-day retention countdown and `Restore from Trash`.
    - `🚀 Publish Snapshot`: Technical snapshot publishing with title, notes, and visibility (`Public` vs `Unlisted`).
    - `👤 Account & Quotas`: Plan status, credits balance, refill date, and simulation counters.

## Error handling

The UI distinguishes transient network/timeouts, permission denial,
authentication expiry, missing projects, malformed stored documents and stale
revision conflicts. Logs contain failure category, project ID and expected
revision, never the project payload. A production Firestore initialization
error is not allowed to fall back to process memory because that would make a
temporary save look durable. Store initialization is cached without Streamlit's
function-name spinner. Local missing/expired Application Default Credentials
are reported as an authentication failure with the recovery command
`gcloud auth application-default login`; Load Forge must be restarted after
credentials are installed. Raw exception text is logged and is shown in the UI
only for an unclassified failure.

## Account and credit isolation

Project writes are restricted to `tenants/{tenant_id}/projects/...`; account
identity, subscription and credit fields remain below `users/{account_id}` and
are written only by `FirestoreUserAccountStore`. The project API has no account
document reference and cannot overwrite those fields.

Credit deductions are transactionally protected today, but balance changes do
not yet have a durable append-only audit trail. Before payments or externally
purchased credit packs are enabled, add a `users/{id}/credit_transactions`
ledger with immutable grant/debit/adjustment entries and derive or reconcile
the cached balance transactionally. That is recommended follow-up work, not a
project-persistence migration.

`InMemoryProjectStore` and `FirestoreProjectStore` expose the same
save/load/list, revision restore, soft-delete and Trash-restore operations. The
UI always scopes calls with the authenticated `SaaSUser`.

## Public projects and technical snapshots

Load Forge separates private engineering projects from public/unlisted project
publications:

```text
Private workspace
  tenants/{tenant_id}/projects/{project_id}
         |
         | explicit publish
         v
Public snapshot
  public_projects/{publication_id}
  public_projects/{publication_id}/versions/v_{version}
```

- **Snapshot Immutability**: Publishing creates an immutable technical version
  snapshot (`PublicProjectVersion`). Later private autosaves do not modify the
  published snapshot.
- **Visibility Modes**:
  - `unlisted`: Accessible only via direct URL (`?p=<publication_id>`). Excluded
    from explore/search listings.
  - `public`: Accessible via direct link and eligible for public exploration.
- **Provenance on Clone/Remix**: Cloning a public project creates a brand new
  private project in the caller's tenant, embedding provenance metadata
  (`source_publication_id`, `source_publication_version`, `original_author_uid`,
  `original_author_name`, and timestamp) without mutating the original project.
- **Technical Metadata Extraction**: `extract_technical_summary(payload)`
  automatically derives driver parameters, nominal size, enclosure volume ($V_b$),
  tuning frequency ($F_b$), and dynamically simulates $F_3$ cutoff and MOL / peak SPL limits
  whenever explicit cached simulation metrics are absent.
- **Explore Public Directory (`?explore=1` / Community Hub)**: Futuristic,
  cyber-neon social engineering hub with a dedicated Community sidebar. It
  provides verified cold-start showcase presets (`curated_community_showcase_projects()`),
  interactive social discovery (category pills, like toggles, creator rank badges,
  forks and views counters), Top Audio Engineers leaderboard, and live activity pulse.
  It supports keyword query (title, author and driver), peer topology filtering
  (including passive-radiator discrimination), and numeric ranges for enclosure volume
  ($V_b$), tuning ($F_b$), driver diameter, driver $F_s$, $Q_{ts}$ and response
  $F_3$. Sorting supports `trending`, `newest`, `lowest_f3`, `compact_vb` and
  `highest_spl`. Current Box Design keys and legacy project keys are both
  normalized into the published technical summary so filters remain reliable
  across saved project generations.
- **Featured Project Spotlight of the Week**: Full-width glowing hero card
  spotlighting top-rated community alignments with 1-click sandbox forking and tech sheets.
- **Real-World Measurement Validation Overlay**: Projects can store real physical measurements
  (parsed via `src/measurements.py` supporting REW, DATS, ARTA, CLIO, Klippel, FRD, ZMA) and display
  them overlaid against simulated responses with automated RMSE and tuning offset ($\Delta F_b$) metrics.
- **Verification Badge**: Each published technical snapshot displays a verified badge
  (`Verified Simulation · Load Forge Solver v{version}`) certifying the lumped-parameter
  matrix solver output.
- **Embed Widget Mode (`?p=<pub_id>&embed=1`)**: A lightweight, responsive iframe
  widget for external technical blogs, forums (DIYAudio, ASR), and build logs.
  Hides application chrome and renders key electroacoustic metrics and an interactive
  SPL response curve with a direct CTA to open the full project.
- **Printable Spec Sheet Export**: `generate_printable_spec_sheet_markdown(pub)` generates
  a publication-ready technical specification sheet in Markdown.
- **SEO & Social Previews**: `generate_json_ld_schema(pub)` and `generate_open_graph_meta(pub)`
  produce structured Schema.org `TechArticle` / `Product` JSON-LD and OpenGraph metadata
  for discovery indexing and rich social link previews.
