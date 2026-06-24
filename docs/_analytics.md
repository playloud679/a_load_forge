# _analytics.py — Analytics Module

Dual-backend analytics: SQLite for local dev/dashboard + PostHog for production
on Streamlit Community Cloud (persistent, free tier: 1M events/month).

## Architecture

SQLite database (`.analytics.db` at repo root) for local tracking and the
`?analytics=on` dashboard. PostHog (if configured via secrets) for persistent
cloud analytics with funnels, retention, and user paths.

### Backends

| Backend  | Purpose                                   | Persistence           |
|----------|-------------------------------------------|----------------------|
| SQLite   | Local dev + `?analytics=on` dashboard     | Repo-local file       |
| PostHog  | Production analytics (cloud)              | PostHog Cloud (free) |

PostHog is lazy-initialized: only activated if `posthog_api_key` is set in
Streamlit secrets. Falls back to SQLite-only silently if not configured.

## Setup for Production

1. Create a free project at [posthog.com](https://posthog.com)
2. Copy the project API key (starts with `phc_`)
3. Set the key:
   - **Local**: `.streamlit/secrets.toml`
   - **Streamlit Cloud**: App settings → Secrets

```toml
posthog_api_key = "phc_..."
posthog_host = "https://eu.i.posthog.com"  # or https://us.i.posthog.com
```

Legacy hosts (`https://eu.posthog.com`, `https://us.posthog.com`) are normalized
to the current ingestion hosts automatically.

## Public API

```python
from _analytics import ga  # singleton Analytics instance
```

| Method | Signature | Description |
|--------|-----------|-------------|
| `start_session(ip, ua, country)` | `→ None` | Call at the top of each Streamlit run, before widget rendering. Reuses one session/pageview across reruns. |
| `render_identity_form()` | `→ None` | Shows optional sidebar expander to collect email / forum username. Saves to the current Streamlit session. |
| `set_identity(email, forum)` | `→ None` | Programmatically set user identity. Sends `$identify` to PostHog. |
| `track(event, **metadata)` | `→ None` | Record event. User identity (email, forum) is attached automatically. |
| `show_dashboard()` | `→ None` | If `?analytics=on`, shows Streamlit dialog with stats. |
| `user_email` | `→ str` | Current user's email (from cookie), or empty string. |
| `user_forum` | `→ str` | Current user's forum username (from cookie), or empty string. |

## User Identity

Users can optionally provide their email and/or forum username via an expandable
sidebar form (rendered by `render_identity_form()`). The identity is:

- Stored in `st.session_state` for the current Streamlit session
- Loaded from legacy browser cookies (`_flare_forge_email`, `_flare_forge_forum`) if present, but never written directly because `st.context.cookies` is read-only on Streamlit Community Cloud
- Automatically attached to every `track()` event
- Sent to PostHog as user properties via `$identify` + event properties
- Re-sent to PostHog if the stable browser fingerprint appears after the user
  already saved email/forum username, so future anonymous returns are associated
  with the same PostHog person
- Visible in the local dashboard under "Registered Users"

No authentication — purely self-reported and optional.

## Usage in ui_app.py

```python
import _analytics as _anl
ga = _anl.ga

ga.start_session()              # after st.set_page_config
ga.render_identity_form()       # sidebar: optional email / forum

ga.track("assembly_generated", profile="Tractrix", section="Circular")
ga.track("slicer_generated", pieces=4, strategy="radial")

ga.show_dashboard()             # very last line
```

## Dashboard (SQLite)

Visible via `?analytics=on`:
- Total sessions, events, cumulative time
- Events by type (table)
- Most-used profiles breakdown
- Registered users with event counts
- Recent 50 events (with user identity)
- Daily visitors chart (last 30 days)

Streamlit reruns the script after many widget interactions. `start_session()`
stores `_flare_forge_session_id`, `_flare_forge_session_start`, and
`_flare_forge_pageview_sent` in `st.session_state`, so those reruns keep the
same session and do not create extra PostHog `$pageview` events.

## PostHog Dashboard

PostHog Cloud provides:
- Event explorer and filtering
- User profiles (email, forum username as properties)
- Session replays
- Funnels and conversion tracking
- Retention analysis
- Custom dashboards

The Python SDK is initialized with `Posthog(project_api_key, host=..., sync_mode=True)`
so Streamlit interactions are sent immediately instead of waiting in the SDK queue.

## Browser Fingerprinting

A self-contained JS snippet (no external CDN) computes a browser fingerprint from:
`userAgent`, `language`, `screen`, `timezone`, `hardwareConcurrency`,
`deviceMemory`, `platform`, and a canvas hash — all hashed via djb2.

The result is stored in the `_flare_forge_fp` cookie (1 year expiry) and used
as the PostHog `distinct_id` with this priority:

1. `_flare_forge_fp` cookie (fingerprint)
2. `_flare_forge_uid` in `st.session_state` (UUID fallback)
3. New UUID (first visit)

This survives cookie clearing, incognito windows, and IP changes — the same
browser produces the same fingerprint.

If the user saves email/forum username before the JS fingerprint cookie exists,
the first `$identify` may use the session UUID fallback. On the next rerun,
when `_flare_forge_fp` is available, `_analytics.py` detects that the PostHog
`distinct_id` changed and sends `$identify` again for the fingerprint id.

## Files

- DB: `<repo_root>/.analytics.db` — auto-created, git-ignored
- Secrets: `.streamlit/secrets.toml` — git-ignored (see `.example`)
- Source: `src/_analytics.py`
