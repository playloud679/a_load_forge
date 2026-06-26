# `_analytics.py` — Analytics Module

Dual-backend analytics: SQLite for local dev/dashboard + PostHog for production
on Streamlit Community Cloud.

## Architecture

SQLite stores local sessions/events in `.analytics.db` at the repo root and
feeds the `?analytics=on` operator dashboard. PostHog is lazy-initialized only
when `posthog_api_key` exists in Streamlit secrets.

| Backend | Purpose | Persistence |
|---|---|---|
| SQLite | Local dev + `?analytics=on` dashboard | Repo-local file |
| PostHog | Production analytics | PostHog Cloud |

## Setup for Production

```toml
posthog_api_key = "phc_..."
posthog_host = "https://eu.i.posthog.com"  # or https://us.i.posthog.com
```

Legacy hosts (`https://eu.posthog.com`, `https://us.posthog.com`) are normalized
to the current ingestion hosts automatically.

## Public API

```python
from _analytics import ga
```

| Method | Signature | Description |
|---|---|---|
| `start_session(ip, ua, country)` | `→ None` | Call near the top of each Streamlit run. Reuses one session/pageview across reruns. |
| `render_forum_username_prompt()` | `→ None` | Shows a one-time landing dialog asking only for a forum username. |
| `render_identity_form()` | `→ None` | Backward-compatible alias for `render_forum_username_prompt()`. |
| `set_identity(email="", forum_username="")` | `→ None` | Saves the forum username and sends `$identify`; `email` is ignored for compatibility. |
| `track(event, **metadata)` | `→ None` | Records an event. Forum username is attached automatically when available. |
| `show_dashboard()` | `→ None` | If `?analytics=on`, shows Streamlit stats. |
| `user_forum` | `→ str` | Current forum username from session/cookie, or empty string. |

## Forum Username Prompt

The public app no longer asks for email. On first landing, if no forum username
is already known, `render_forum_username_prompt()` opens a dialog with:

- one `Forum username` input
- `Save username`
- `Continue without it`

When saved, the username is:

- stored in `st.session_state["_flare_forge_forum"]`
- written to the browser cookie `_flare_forge_forum` for one year by a tiny
  client-side Streamlit component
- attached to future SQLite/PostHog events as `forum_username`
- sent to PostHog as a `$identify` user property

Streamlit Community Cloud exposes `st.context.cookies` as read-only in Python,
so cookie writes must happen in browser JavaScript. Reads are still performed
from `st.context.cookies`, and cookie loading happens even when PostHog is not
configured, so returning users are recognized in local/dev mode too.

## Privacy Defaults

The public app does **not** create a browser fingerprint and does **not** store a
persistent anonymous tracking cookie. Before the user opts in with a forum
username, PostHog events use only the current Streamlit session id. After opt-in,
the stable PostHog id is `forum:<username>`, derived from the username cookie.

The app asks for no email and no account. Session replay should remain disabled
in PostHog unless the privacy notice and consent flow are updated.

## Usage in `ui_app.py`

```python
import _analytics as _anl
ga = _anl.ga

ga.start_session()
ga.render_forum_username_prompt()

ga.track("assembly_generated", profile="Tractrix", section="Circular")
ga.track("slicer_generated", pieces=4, strategy="radial")

ga.show_dashboard()
```

## Dashboard

Visible via `?analytics=on`:

- total sessions, events, cumulative time
- events by type
- most-used profiles
- registered forum users with event counts
- recent 50 events
- daily visitors chart

## Files

- DB: `<repo_root>/.analytics.db` — auto-created, git-ignored
- Secrets: `.streamlit/secrets.toml` — git-ignored
- Source: `src/_analytics.py`
