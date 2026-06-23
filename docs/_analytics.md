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
   - **Local**: `.streamlit/secrets.toml` → `posthog_api_key = "phc_..."`
   - **Streamlit Cloud**: App settings → Secrets → add `posthog_api_key = "phc_..."`

## Public API

```python
from _analytics import ga  # singleton Analytics instance
```

| Method | Signature | Description |
|--------|-----------|-------------|
| `start_session(ip, ua, country)` | `→ None` | Call once per page load, before widget rendering. Loads identity from cookies. |
| `render_identity_form()` | `→ None` | Shows optional sidebar expander to collect email / forum username. Saves to cookies. |
| `set_identity(email, forum)` | `→ None` | Programmatically set user identity. Sends `$identify` to PostHog. |
| `track(event, **metadata)` | `→ None` | Record event. User identity (email, forum) is attached automatically. |
| `show_dashboard()` | `→ None` | If `?analytics=on`, shows Streamlit dialog with stats. |
| `user_email` | `→ str` | Current user's email (from cookie), or empty string. |
| `user_forum` | `→ str` | Current user's forum username (from cookie), or empty string. |

## User Identity

Users can optionally provide their email and/or forum username via an expandable
sidebar form (rendered by `render_identity_form()`). The identity is:

- Stored in browser cookies (`_flare_forge_email`, `_flare_forge_forum`)
- Automatically attached to every `track()` event
- Sent to PostHog as user properties via `$identify` + event properties
- Visible in the local dashboard under "Registered Users"

No authentication — purely self-reported, optional, and stored client-side.

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

## PostHog Dashboard

PostHog Cloud provides:
- Event explorer and filtering
- User profiles (email, forum username as properties)
- Session replays
- Funnels and conversion tracking
- Retention analysis
- Custom dashboards

## Files

- DB: `<repo_root>/.analytics.db` — auto-created, git-ignored
- Secrets: `.streamlit/secrets.toml` — git-ignored (see `.example`)
- Source: `src/_analytics.py`
