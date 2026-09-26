# usage_analytics

Source: `src/usage_analytics.py` · UI glue: [`docs/ui/usage.md`](ui/usage.md)

Product usage events and the admin **Traction** report. The goal is to answer
"where do real users stop?" without admin or test traffic inflating the numbers.

## Event vocabulary

Only these names are accepted (`build_event` raises `ValueError` otherwise):

| Event | Emitted when | Dedup (per Streamlit session) |
|---|---|---|
| `auth_gate_view` | an anonymous visitor reaches the sign-in wall | once |
| `signup_completed` | the signed-in account was created ≤15 min ago | once |
| `session_start` | a signed-in session opens | once |
| `box_design_sim` | a Box Design simulation renders; `interactive` is false for the unprompted first render | once per load type × driver × interactive |
| `bass_match_run` | a Bass Match scan is launched | every run |
| `project_saved` | cloud autosave commits a new revision | once per project |
| `project_published` | a project is published | every publish |
| `paywall_seen` | credit shortfall or billing modal is shown | once per location |

Each document: `event, uid, email, anon_id, props, ts` (ISO UTC). `props` keeps
at most 12 scalar values, strings truncated to 120 characters. No credentials,
payment data or free text are recorded.

`anon_id` is the portal's `lf_aid` (forwarded by `load-forge.com/app?lf_aid=…`)
or one minted by the app. It lives only in the Streamlit session and crosses
the Google sign-in redirect inside the existing 10-minute return-destination
cookie, which links the anonymous visit to the new account. No long-lived
analytics cookie is set in the Studio.

## Storage

- `usage_events` collection, append-only, in the **private** Firestore database
  (`LOAD_FORGE_FIRESTORE_PRIVATE_DB`, `(default)` in production today).
- `analytics_settings/exclusions` document: `emails` array of test accounts,
  toggled from the admin console ("Test account" checkbox).
- Memory backend / SaaS disabled: one process-local `InMemoryUsageStore`.

Recording is best-effort: `ui.usage.track` logs a warning and never raises.

## Traction report

`traction_report(events, accounts, excluded_emails)` is pure. Real users are
accounts that are neither `is_admin` nor excluded. Funnel rows:

1. anonymous visitors that reached the sign-in wall (distinct `anon_id`,
   excluding any id that ever belonged to an internal account);
2. sign-ups (real accounts);
3. activated: ≥1 interactive `box_design_sim` or `bass_match_run`;
4. saved a project; 5. came back ≥1 day after sign-up (`session_start`);
6. published; 7. hit a paywall.

Load-type and driver rankings count interactive simulations only. Activity
before event tracking was deployed is not reconstructed.

## Live feed

`live_feed(portal_events, app_events, accounts, excluded_emails, limit)` is a
pure, LLOOGG-style raw stream (newest first, UTC) merging the portal's
`growth_telemetry` (read-only here; written by `load_forge_deploy`, database
`LOAD_FORGE_GROWTH_DATABASE`, default `(default)`) with Studio `usage_events`.

- A portal `anon_uid` is shown as the account email once the same id appears
  on a signed-in Studio event, so one visitor's path reads as one person.
- Hidden: `deployment_verified`, and **every** event (including earlier ones)
  of an anonymous id that was ever tagged `properties.internal` (browser
  opened once with `load-forge.com/?lf_internal=1`) or that belongs to an
  admin/test account.
- `visitor_summaries(rows)` folds the stream into one row per visitor: first
  and last seen, arrival referrer (or "direct"), entry page, portal pages
  viewed, whether they reached the Studio (Studio event or `app_open_clicked`
  / `studio_cta_clicked`), signed in, last event.
- Stores expose `recent_events(limit)` / `recent_portal_events(limit)`
  (Firestore: `order_by` descending on `ts` / `timestamp`).

The admin console's **Live** tab fetches 500 events per source, refreshes every
10 s (`@st.fragment(run_every=10)`), shows one row per visitor (latest 100)
with totals (visitors, reached the Studio, left after one page), and "Follow
one visitor" lists that visitor's events across portal → sign-in → Studio.
