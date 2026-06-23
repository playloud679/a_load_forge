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
    ga.render_identity_form()   # optional email / forum username
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

        # User identity (loaded from cookies)
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
        Uses browser fingerprint (cookie) + fallback UUID to identify users."""
        if self._ph_disabled:
            return
        try:
            import streamlit as st
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

            # User ID priority: fingerprint cookie > session fallback > new UUID.
            # Streamlit exposes context cookies as read-only on Community Cloud.
            cookies = getattr(st.context, "cookies", {})
            state = getattr(st, "session_state", {})
            self._ph_id = (cookies.get("_flare_forge_fp")
                           or state.get("_flare_forge_uid")
                           or str(uuid.uuid4()))
            try:
                state["_flare_forge_uid"] = self._ph_id
            except Exception:
                pass

            self._user_email = (
                state.get("_flare_forge_email")
                or cookies.get("_flare_forge_email")
                or ""
            )
            self._user_forum = (
                state.get("_flare_forge_forum")
                or cookies.get("_flare_forge_forum")
                or ""
            )
        except Exception:
            self._ph_disabled = True

    def _inject_fingerprint_js(self):
        """Inject a JS snippet that computes a browser fingerprint and stores
        it in a cookie. On next rerun the cookie is picked up as distinct_id.
        Needs no external dependencies — self-contained canvas + navigator hash."""
        import streamlit as st

        st.markdown("""
<script>
(function(){
  if (document.cookie.indexOf('_flare_forge_fp=') !== -1) return;
  try {
    var fp = [];
    fp.push(navigator.userAgent||'');
    fp.push(navigator.language||'');
    fp.push(screen.colorDepth+','+screen.width+'x'+screen.height);
    try { fp.push(Intl.DateTimeFormat().resolvedOptions().timeZone); } catch(e){}
    fp.push(navigator.hardwareConcurrency||'');
    fp.push(navigator.deviceMemory||'');
    fp.push(navigator.platform||'');
    // canvas fingerprint
    try {
      var c=document.createElement('canvas'), x=c.getContext('2d');
      c.width=200;c.height=50;
      x.textBaseline='top';x.font='14px Arial';
      x.fillStyle='#f60';x.fillRect(0,0,100,25);
      x.fillStyle='#069';x.fillRect(100,0,100,25);
      x.fillStyle='#fff';x.fillText('flare_forge',2,18);
      fp.push(c.toDataURL().substring(0,120));
    } catch(e){}
    // djb2 hash
    var s = fp.join('###'), hash = 5381;
    for (var i=0; i<s.length; i++) hash = ((hash<<5)+hash)+s.charCodeAt(i);
    var fpid = 'fp_' + (hash>>>0).toString(36);
    document.cookie = '_flare_forge_fp='+fpid+';path=/;max-age='+(365*86400)+';SameSite=Lax';
  } catch(e){}
})();
</script>
        """, unsafe_allow_html=True)

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

    def set_identity(self, email: str = "", forum_username: str = ""):
        """Save user identity for this Streamlit session and send it to PostHog."""
        import streamlit as st
        state = getattr(st, "session_state", {})
        changed = False

        email = (email or "").strip()
        forum_username = (forum_username or "").strip()

        if email != self._user_email:
            self._user_email = email
            try:
                state["_flare_forge_email"] = self._user_email
            except Exception:
                pass
            changed = True
        if forum_username != self._user_forum:
            self._user_forum = forum_username
            try:
                state["_flare_forge_forum"] = self._user_forum
            except Exception:
                pass
            changed = True

        if changed and (self._user_email or self._user_forum):
            self._posthog_capture("$identify", {
                "$set": {
                    "email": self._user_email,
                    "forum_username": self._user_forum,
                }
            })

    def render_identity_form(self):
        """Render an optional sidebar form to collect email / forum username.
        Call after start_session(), before any track() calls."""
        import streamlit as st

        if not self._session_id:
            return  # start_session() must be called first

        with st.sidebar:
            with st.expander("👤 Analytics Profile (optional)", expanded=False):
                st.caption(
                    "Help us understand who uses flare_forge. "
                    "Your email and forum username are only used for analytics "
                    "and will never be shared."
                )
                new_email = st.text_input(
                    "Email", value=self._user_email,
                    placeholder="you@example.com",
                    key="_anl_email",
                )
                new_forum = st.text_input(
                    "Forum username", value=self._user_forum,
                    placeholder="DIYaudio / Reddit / ...",
                    key="_anl_forum",
                )
                if st.button("Save", key="_anl_save", use_container_width=True):
                    self.set_identity(email=new_email, forum_username=new_forum)
                    st.toast("Profile saved!", icon="👤")

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

        # Inject browser fingerprint JS (cookie set on next rerun)
        self._inject_fingerprint_js()

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
            if self._user_email:
                props["email"] = self._user_email
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
        User identity (email, forum) is automatically attached."""
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
        if self._user_email:
            ph_props["email"] = self._user_email
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
                    COALESCE(json_extract(metadata, '$.email'),
                             json_extract(metadata, '$.forum_username'),
                             'anonymous') as identity,
                    COUNT(*) as events
                FROM events
                WHERE json_extract(metadata, '$.email') IS NOT NULL
                   OR json_extract(metadata, '$.forum_username') IS NOT NULL
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
                       COALESCE(json_extract(metadata, '$.email'),
                                json_extract(metadata, '$.forum_username'),
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
