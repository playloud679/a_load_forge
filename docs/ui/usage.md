# ui/usage

Source: `src/ui/usage.py` · Model and event vocabulary: [`docs/usage_analytics.md`](../usage_analytics.md)

Streamlit glue for product usage events.

- `track(event, props=None, *, once=None)` — records one event for the current
  visitor (uid/email from `_runtime._CURRENT_SAAS_USER`, plus `anon_id()`).
  `once` deduplicates within the session so widget reruns do not multiply
  writes. Never raises; skipped in finder worker processes.
- `track_session(account)` — called by `ui_app.py` on every rerun once a user
  is resolved; emits `session_start` once and `signup_completed` when the
  account is at most 15 minutes old.
- `anon_id()` — `lf_aid` from the query string (portal handoff), else a new
  `a_<hex>`; kept only in `st.session_state`. No long-lived analytics cookie.
- `remember_anon_id_for_sign_in()` — at the sign-in wall, puts the id in the
  URL so `navigation.remember_auth_destination` carries it in the existing
  10-minute return cookie across the Google redirect. `track_session` removes
  it from the URL once the user is signed in, so shared links never carry it.
- `get_usage_store()` — cached `usage_analytics.create_usage_store(settings)`.

Call sites: `account._resolve_saas_user` (sign-in wall), `app.main`
(Box Design render), `finder` (Bass Match run, credit shortfall),
`projects` (autosave, publish, billing modal, admin Traction tab).
