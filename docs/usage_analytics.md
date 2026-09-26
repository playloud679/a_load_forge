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
