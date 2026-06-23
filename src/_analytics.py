"""
_analytics.py — Dual-backend analytics for Streamlit (SQLite + PostHog).
SQLite for local dev / dashboard (?analytics=on). PostHog for production
on Streamlit Community Cloud (persistent, free tier: 1M events/month).

Configure PostHog in .streamlit/secrets.toml:
    posthog_api_key = "phc_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    posthog_host = "https://eu.posthog.com"   # or https://us.posthog.com

Usage in ui_app.py:
    from _analytics import ga
    ga.start_session()
    ga.track("generate", profile="tractrix", section="circular")
    ga.show_dashboard()   # shows dashboard if ?analytics=on
"""

import time, datetime, json, uuid, threading
from pathlib import Path

_DB_PATH = Path(__file__).parent.parent / ".analytics.db"


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
        """Try to import PostHog and read API key from Streamlit secrets."""
        if self._ph_disabled:
            return
        try:
            import streamlit as st
            api_key = st.secrets.get("posthog_api_key", "")
            if not api_key:
                self._ph_disabled = True
                return
            import posthog
            posthog.project_api_key = api_key
            posthog.host = st.secrets.get("posthog_host", "https://eu.posthog.com")
            posthog.debug = False
            self._ph = posthog
            self._ph_id = str(uuid.uuid4())
        except Exception:
            self._ph_disabled = True

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

    # ── Session ─────────────────────────────────────────────────────────

    def start_session(self, ip: str = "", ua: str = "", country: str = ""):
        """Call once per page load at the top of the script."""
        self._session_id = uuid.uuid4().hex[:12]
        self._session_start = time.time()

        with self._lock, self._get_conn() as conn:
            conn.execute(
                "INSERT INTO sessions (id, started_at, ip, user_agent, country) VALUES (?,?,?,?,?)",
                (self._session_id, _now_iso(), ip, ua, country),
            )

        # PostHog page view
        self._posthog_capture("$pageview", {"url": "/", "session_id": self._session_id})

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
        Sent to both SQLite (local dashboard) and PostHog (if configured)."""
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

        # PostHog
        ph_props = dict(clean)
        ph_props["session_id"] = self._session_id
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

            # ── Recent activity ────────────────────────────────
            st.markdown("#### Recent Activity")
            recent = self._fetch_all(
                "SELECT session_id, event, created_at FROM events ORDER BY created_at DESC LIMIT 50"
            )
            if recent:
                import pandas as pd
                df = pd.DataFrame(recent, columns=["Session", "Event", "Time"])
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

            st.caption("💡 Also check your PostHog dashboard for advanced analytics (funnels, retention, user paths).")

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
