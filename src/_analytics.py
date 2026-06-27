"""
_analytics.py — Dual-backend analytics for Streamlit (SQLite + PostHog).
SQLite for local dev / dashboard (?analytics=on). PostHog for production
on Streamlit Community Cloud (persistent, free tier: 1M events/month).

Configure PostHog in .streamlit/secrets.toml:
    posthog_api_key = "phc_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    posthog_host = "https://eu.i.posthog.com"   # or https://us.i.posthog.com

Usage in ui_app.py:
    from _analytics import ga
    ga.start_session()
    ga.render_forum_username_prompt()   # optional forum username popup
    ga.track("generate", profile="tractrix", section="circular")
    ga.show_dashboard()         # shows dashboard if ?analytics=on
"""

import time, datetime, json, uuid, threading
from pathlib import Path

_DB_PATH = Path(__file__).parent.parent / ".analytics.db"
_DEFAULT_POSTHOG_HOST = "https://eu.i.posthog.com"
_POSTHOG_HOST_ALIASES = {
    "https://eu.posthog.com": "https://eu.i.posthog.com",
    "https://us.posthog.com": "https://us.i.posthog.com",
}
_SESSION_ID_KEY = "_flare_forge_session_id"
_SESSION_START_KEY = "_flare_forge_session_start"
_SESSION_RECORDED_KEY = "_flare_forge_session_recorded"
_PAGEVIEW_SENT_KEY = "_flare_forge_pageview_sent"
_IDENTIFIED_ID_KEY = "_flare_forge_identified_id"
_FORUM_COOKIE_NAME = "_flare_forge_forum"
_FORUM_PROMPT_DISMISSED_KEY = "_flare_forge_forum_prompt_dismissed"


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class Analytics:
    """Dual-backend analytics: SQLite (always) + PostHog (if configured)."""

    def __init__(self, db_path: Path | None = None):
        self._db = db_path or _DB_PATH
        self._lock = threading.Lock()
        self._session_id: str | None = None
        self._session_start: float = 0.0

        # PostHog — lazy init
        self._ph = None
        self._ph_disabled = False
        self._ph_id: str = ""

        # User identity (loaded from session state / cookies)
        self._user_email: str = ""
        self._user_forum: str = ""

        self._init_db()

    # ── DB setup ────────────────────────────────────────────────────────

    def _get_conn(self):
        import sqlite3
        conn = sqlite3.connect(str(self._db))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id          TEXT PRIMARY KEY,
                    started_at  TEXT NOT NULL,
                    ip          TEXT DEFAULT '',
                    user_agent  TEXT DEFAULT '',
                    country     TEXT DEFAULT '',
                    duration_s  REAL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS events (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id  TEXT NOT NULL REFERENCES sessions(id),
                    event       TEXT NOT NULL,
                    metadata    TEXT DEFAULT '{}',
                    created_at  TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_events_event   ON events(event, created_at);
            """)

    # ── PostHog lazy setup ──────────────────────────────────────────────

    def _init_posthog(self):
        """Try to import PostHog and read API key from Streamlit secrets.
        Uses a forum username only after opt-in; otherwise uses the session id."""
        if self._ph_disabled:
            return
        try:
            import streamlit as st
            self._load_identity_from_context()
            api_key = st.secrets.get("posthog_api_key", "")
            if not api_key:
                self._ph_disabled = True
                return
            from posthog import Posthog
            host = st.secrets.get("posthog_host", _DEFAULT_POSTHOG_HOST)
            host = _POSTHOG_HOST_ALIASES.get(host.rstrip("/"), host.rstrip("/"))
            self._ph = Posthog(
                api_key,
                host=host,
                debug=False,
                sync_mode=True,
            )

            state = getattr(st, "session_state", {})
            self._ph_id = self._posthog_distinct_id(state)
            try:
                state["_flare_forge_uid"] = self._ph_id
            except Exception:
                pass

            self._identify_current_user_if_needed()
        except Exception:
            self._ph_disabled = True

    def _load_identity_from_context(self):
        """Load the saved forum username from Streamlit state or browser cookie."""
        try:
            import streamlit as st
            cookies = getattr(st.context, "cookies", {})
            state = getattr(st, "session_state", {})
            forum_username = (
                state.get(_FORUM_COOKIE_NAME)
                or cookies.get(_FORUM_COOKIE_NAME)
                or self._read_cookie_component(_FORUM_COOKIE_NAME)
                or ""
            )
            forum_username = str(forum_username).strip()
            if forum_username:
                self._user_forum = forum_username
                try:
                    state[_FORUM_COOKIE_NAME] = forum_username
                except Exception:
                    pass
        except Exception:
            pass

    def _cookie_manager(self):
        """Return an optional bidirectional cookie manager for Streamlit Cloud."""
        try:
            import extra_streamlit_components as stx
            # Instantiate on every run. CookieManager reads browser cookies by
            # rendering a component; caching the Python object in session_state
            # prevents that component from mounting on later Streamlit reruns.
            return stx.CookieManager(key="flare_forge_cookie_manager")
        except Exception:
            return None

    def _read_cookie_component(self, name: str) -> str:
        manager = self._cookie_manager()
        if manager is None:
            return ""
        try:
            try:
                manager.get_all(key="flare_forge_get_all")
            except Exception:
                pass
            value = manager.get(cookie=name)
            return "" if value is None else str(value)
        except TypeError:
            try:
                value = manager.get(name)
                return "" if value is None else str(value)
            except Exception:
                return ""
        except Exception:
            return ""

    def _posthog_distinct_id(self, state) -> str:
        """Return the least persistent useful PostHog id.

        Before opt-in, events use only the current Streamlit session id. After
        the user saves a forum username, future visits use that username cookie.
        """
        if self._user_forum:
            return f"forum:{self._user_forum}"
        return self._session_id or state.get("_flare_forge_uid") or uuid.uuid4().hex

    def _write_cookie_js(self, name: str, value: str, max_age_days: int = 365):
        """Persist a first-party cookie from the browser side.

        Prefer ``extra_streamlit_components.CookieManager`` because plain
        ``components.html`` can be iframe-isolated on Streamlit Cloud.
        """
        manager = self._cookie_manager()
        if manager is not None:
            try:
                expires_at = (
                    datetime.datetime.now(datetime.timezone.utc)
                    + datetime.timedelta(days=int(max_age_days))
                )
                manager.set(
                    name,
                    value,
                    key=f"set_{name}",
                    path="/",
                    expires_at=expires_at,
                    same_site="lax",
                )
                return
            except TypeError:
                try:
                    manager.set(name, value)
                    return
                except Exception:
                    pass
            except Exception:
                pass

        try:
            import streamlit.components.v1 as components
            js_name = json.dumps(str(name))
            js_value = json.dumps(str(value))
            max_age = int(max_age_days) * 86400
            components.html(f"""
<script>
(function(){{
  var name = {js_name};
  var value = encodeURIComponent({js_value});
  document.cookie = name + '=' + value + ';path=/;max-age={max_age};SameSite=Lax';
}})();
</script>
            """, height=0, width=0)
        except Exception:
            pass

    def _posthog_capture(self, event: str, properties: dict):
        """Send event to PostHog if configured."""
        if self._ph is None and not self._ph_disabled:
            self._init_posthog()
        if self._ph is None:
            return
        try:
            self._ph.capture(
                distinct_id=self._ph_id,
                event=event,
                properties=properties,
            )
        except Exception:
            pass  # never break the app for analytics

    # ── User identity ───────────────────────────────────────────────────

    def _identify_current_user_if_needed(self):
        """Associate the current PostHog distinct_id with saved optional identity."""
        if not self._ph_id or not self._user_forum:
            return
        try:
            import streamlit as st
            state = getattr(st, "session_state", {})
            if state.get(_IDENTIFIED_ID_KEY) == self._ph_id:
                return
            self._posthog_capture("$identify", {
                "$set": {
                    "forum_username": self._user_forum,
                }
            })
            state[_IDENTIFIED_ID_KEY] = self._ph_id
        except Exception:
            pass

    def set_identity(self, email: str = "", forum_username: str = ""):
        """Save forum username for this Streamlit session and send it to PostHog.

        ``email`` is retained only for backward compatibility with older calls;
        it is intentionally ignored because the UI no longer asks for email.
        """
        import streamlit as st
        state = getattr(st, "session_state", {})
        changed = False

        forum_username = (forum_username or "").strip()

        if forum_username != self._user_forum:
            self._user_forum = forum_username
            try:
                state[_FORUM_COOKIE_NAME] = self._user_forum
            except Exception:
                pass
            if self._user_forum:
                self._write_cookie_js(_FORUM_COOKIE_NAME, self._user_forum)
            changed = True

        if changed:
            if self._ph is not None:
                self._ph_id = self._posthog_distinct_id(state)
                try:
                    state["_flare_forge_uid"] = self._ph_id
                except Exception:
                    pass
            try:
                state.pop(_IDENTIFIED_ID_KEY, None)
            except Exception:
                pass
            self._identify_current_user_if_needed()

    def render_forum_username_prompt(self):
        """Show a one-time landing dialog asking only for a forum username."""
        import streamlit as st

        if not self._session_id:
            return  # start_session() must be called first
        self._load_identity_from_context()
        if self._user_forum:
            return

        state = getattr(st, "session_state", {})
        if state.get(_FORUM_PROMPT_DISMISSED_KEY):
            return

        @st.dialog("Before you start")
        def _forum_prompt():
            st.caption(
                "Optional: save your forum username in a cookie so I can connect "
                "bug reports with app activity. No email, no account. Generation "
                "parameters and STL files are not logged."
            )
            with st.form("_forum_username_form"):
                new_forum = st.text_input(
                    "Forum username",
                    value="",
                    placeholder="DIYAudio / Reddit username",
                    key="_anl_forum_prompt",
                )
                save = st.form_submit_button("Save username", use_container_width=True)
                skip = st.form_submit_button("Continue without it", use_container_width=True)

            if save:
                new_forum = (new_forum or "").strip()
                if new_forum:
                    self.set_identity(forum_username=new_forum)
                    state[_FORUM_PROMPT_DISMISSED_KEY] = True
                    st.success("Username saved. You can close this popup.")
                else:
                    st.warning("Write a username, or continue without it.")
            if skip:
                state[_FORUM_PROMPT_DISMISSED_KEY] = True
                st.rerun()

        _forum_prompt()

    def render_identity_form(self):
        """Backward-compatible wrapper for the old sidebar identity form."""
        self.render_forum_username_prompt()

    @property
    def user_email(self) -> str:
        return self._user_email

    @property
    def user_forum(self) -> str:
        return self._user_forum

    # ── Session ─────────────────────────────────────────────────────────

    def start_session(self, ip: str = "", ua: str = "", country: str = ""):
        """Call at the top of each Streamlit run; records one session/pageview."""
        import streamlit as st

        state = getattr(st, "session_state", {})
        self._load_identity_from_context()
        now = time.time()
        self._session_id = state.get(_SESSION_ID_KEY) or uuid.uuid4().hex[:12]
        self._session_start = float(state.get(_SESSION_START_KEY) or now)
        try:
            state[_SESSION_ID_KEY] = self._session_id
            state[_SESSION_START_KEY] = self._session_start
        except Exception:
            pass

        # Lazy-init PostHog (also loads cookies)
        self._init_posthog()

        if not state.get(_SESSION_RECORDED_KEY):
            with self._lock, self._get_conn() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO sessions (id, started_at, ip, user_agent, country) VALUES (?,?,?,?,?)",
                    (self._session_id, _now_iso(), ip, ua, country),
                )
            try:
                state[_SESSION_RECORDED_KEY] = True
            except Exception:
                pass

        # PostHog page view
        if not state.get(_PAGEVIEW_SENT_KEY):
            props: dict = {"url": "/", "session_id": self._session_id}
            if self._user_forum:
                props["forum_username"] = self._user_forum
            self._posthog_capture("$pageview", props)
            try:
                state[_PAGEVIEW_SENT_KEY] = True
            except Exception:
                pass

    def _update_duration(self):
        if not self._session_id:
            return
        duration = time.time() - self._session_start
        with self._lock, self._get_conn() as conn:
            conn.execute(
                "UPDATE sessions SET duration_s = ? WHERE id = ?",
                (duration, self._session_id),
            )

    # ── Event tracking ──────────────────────────────────────────────────

    def track(self, event: str, **metadata):
        """Track a named event with optional keyword metadata.
        Sent to both SQLite (local dashboard) and PostHog (if configured).
        Forum username is automatically attached when available."""
        if not self._session_id:
            return
        # Sanitise metadata — only JSON-serialisable primitives
        clean = {}
        for k, v in metadata.items():
            try:
                json.dumps(v)
                clean[k] = v
            except (TypeError, ValueError):
                clean[k] = str(v)

        # SQLite
        with self._lock, self._get_conn() as conn:
            conn.execute(
                "INSERT INTO events (session_id, event, metadata, created_at) VALUES (?,?,?,?)",
                (self._session_id, event, json.dumps(clean), _now_iso()),
            )

        # PostHog — attach identity automatically
        ph_props = dict(clean)
        ph_props["session_id"] = self._session_id
        if self._user_forum:
            ph_props["forum_username"] = self._user_forum
        self._posthog_capture(event, ph_props)

    # ── Dashboard (SQLite-based) ────────────────────────────────────────

    def show_dashboard(self):
        """Render analytics dashboard if ?analytics=on is in the URL."""
        import streamlit as st

        query = st.query_params
        if "analytics" not in query or "on" not in query["analytics"]:
            self._update_duration()
            return

        self._update_duration()

        @st.dialog("flare_forge Analytics", width="large")
        def _dashboard():
            st.markdown("#### Session Overview")
            sessions = self._query_sessions()
            if not sessions:
                st.info("No data yet. Interact with the app to collect events.")
                return

            total_sessions = len(sessions)
            total_events = sum(
                self._fetch_one("SELECT COUNT(*) FROM events") or (0,)
            )
            total_time_s = sum(
                s["duration_s"] for s in sessions if s["duration_s"]
            )
            hours = int(total_time_s // 3600)
            minutes = int((total_time_s % 3600) // 60)

            c1, c2, c3 = st.columns(3)
            c1.metric("Total Sessions", total_sessions)
            c2.metric("Total Events", total_events)
            c3.metric("Total Time", f"{hours}h {minutes}m")

            # ── Events by type ─────────────────────────────────
            st.markdown("#### Events by Type")
            rows = self._fetch_all(
                "SELECT event, COUNT(*) as cnt FROM events GROUP BY event ORDER BY cnt DESC"
            )
            if rows:
                import pandas as pd
                df = pd.DataFrame(rows, columns=["Event", "Count"])
                st.dataframe(df, use_container_width=True, hide_index=True)

            # ── Profile usage ──────────────────────────────────
            st.markdown("#### Most Used Profiles")
            profile_rows = self._fetch_all("""
                SELECT json_extract(metadata, '$.profile') as profile,
                       COUNT(*) as cnt
                FROM events
                WHERE profile IS NOT NULL AND profile != ''
                GROUP BY profile ORDER BY cnt DESC
            """)
            if profile_rows:
                import pandas as pd
                df = pd.DataFrame(profile_rows, columns=["Profile", "Count"])
                st.dataframe(df, use_container_width=True, hide_index=True)

            # ── User identities ────────────────────────────────
            st.markdown("#### Registered Users")
            id_rows = self._fetch_all("""
                SELECT DISTINCT
                    COALESCE(json_extract(metadata, '$.forum_username'),
                             'anonymous') as identity,
                    COUNT(*) as events
                FROM events
                WHERE json_extract(metadata, '$.forum_username') IS NOT NULL
                GROUP BY identity ORDER BY events DESC
                LIMIT 20
            """)
            if id_rows:
                import pandas as pd
                df = pd.DataFrame(id_rows, columns=["User", "Events"])
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.caption("No users have registered their identity yet.")

            # ── Recent activity ────────────────────────────────
            st.markdown("#### Recent Activity")
            recent = self._fetch_all("""
                SELECT session_id, event,
                       COALESCE(json_extract(metadata, '$.forum_username'),
                                '') as user,
                       created_at
                FROM events ORDER BY created_at DESC LIMIT 50
            """)
            if recent:
                import pandas as pd
                df = pd.DataFrame(recent, columns=["Session", "Event", "User", "Time"])
                st.dataframe(df, use_container_width=True, hide_index=True)

            # ── Daily activity ─────────────────────────────────
            st.markdown("#### Daily Visitors (last 30 days)")
            daily = self._fetch_all("""
                SELECT DATE(started_at) as day, COUNT(*) as visitors
                FROM sessions
                WHERE started_at >= DATE('now', '-30 days')
                GROUP BY day ORDER BY day
            """)
            if daily:
                import pandas as pd
                df = pd.DataFrame(daily, columns=["Day", "Visitors"])
                st.bar_chart(df.set_index("Day"), use_container_width=True)

            st.caption("💡 PostHog dashboard: funnels, retention, user paths.")

        _dashboard()

    # ── Query helpers ───────────────────────────────────────────────────

    def _query_sessions(self) -> list[dict]:
        rows = self._fetch_all(
            "SELECT id, started_at, ip, user_agent, country, duration_s FROM sessions ORDER BY started_at DESC"
        )
        cols = ["id", "started_at", "ip", "user_agent", "country", "duration_s"]
        return [dict(zip(cols, r)) for r in rows]

    def _fetch_all(self, sql: str, params=()):
        with self._lock, self._get_conn() as conn:
            return conn.execute(sql, params).fetchall()

    def _fetch_one(self, sql: str, params=()):
        with self._lock, self._get_conn() as conn:
            return conn.execute(sql, params).fetchone()


# Convenience singleton
ga = Analytics()
