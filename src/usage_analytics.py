"""Product usage events and the admin traction report.

Purpose: record a small, fixed vocabulary of product events (sign-in wall,
sign-up, sessions, simulations, saves, paywall) and turn them into a funnel
over *real* users only, so admin/test traffic never inflates the numbers.

Public API:
- ``EVENTS``: the allowed event names; anything else is rejected.
- ``build_event(...)``: normalize one event document (scalar props only).
- ``InMemoryUsageStore`` / ``FirestoreUsageStore`` / ``create_usage_store``:
  append-only ``usage_events`` collection plus the ``analytics_settings/
  exclusions`` document listing test accounts.
- ``traction_report(events, accounts, excluded_emails)``: pure aggregation.

Invariants: recording is best-effort and must never break the app (callers
swallow exceptions); events carry no credentials, payment data or free text
beyond short catalog/driver labels. Accounts are never modified here.

See docs/usage_analytics.md.
"""

from __future__ import annotations

import os
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

EVENTS = frozenset({
    "auth_gate_view",     # anonymous visitor reached the sign-in wall
    "signup_completed",   # account created in this session
    "session_start",      # signed-in session opened
    "box_design_sim",     # a Box Design simulation rendered (once per load/driver per session)
    "bass_match_run",     # a Bass Match scan was launched
    "project_saved",
    "project_published",
    "paywall_seen",       # an upgrade / insufficient-credits prompt was shown
})

EVENTS_COLLECTION = "usage_events"
PORTAL_COLLECTION = "growth_telemetry"  # written by load_forge_deploy (portal)
SETTINGS_COLLECTION = "analytics_settings"
EXCLUSIONS_DOCUMENT = "exclusions"
_MAX_PROP_LEN = 120
_MAX_PROPS = 12


def build_event(
    event: str,
    *,
    uid: str = "",
    email: str = "",
    anon_id: str = "",
    props: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return a storable event document; raise ValueError for unknown events."""
    if event not in EVENTS:
        raise ValueError(f"Unknown usage event {event!r}")
    clean: dict[str, Any] = {}
    for key, value in list((props or {}).items())[:_MAX_PROPS]:
        if isinstance(value, bool) or isinstance(value, (int, float)):
            clean[str(key)[:40]] = value
        elif value is not None:
            clean[str(key)[:40]] = str(value)[:_MAX_PROP_LEN]
    return {
        "event": event,
        "uid": str(uid or "")[:128],
        "email": str(email or "").strip().casefold()[:254],
        "anon_id": str(anon_id or "")[:64],
        "props": clean,
        "ts": (now or datetime.now(timezone.utc)).isoformat(),
    }


class UsageStore(Protocol):
    def append(self, event: Mapping[str, Any]) -> None: ...
    def list_events(self, since: datetime | None = None) -> list[dict[str, Any]]: ...
    def recent_events(self, limit: int) -> list[dict[str, Any]]: ...
    def recent_portal_events(self, limit: int) -> list[dict[str, Any]]: ...
    def excluded_emails(self) -> frozenset[str]: ...
    def set_excluded(self, email: str, excluded: bool) -> None: ...


class InMemoryUsageStore:
    """Process-local store for tests, local runs and the memory backend."""

    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []
        self._portal_events: list[dict[str, Any]] = []
        self._excluded: set[str] = set()

    def append(self, event: Mapping[str, Any]) -> None:
        self._events.append(dict(event))

    def list_events(self, since: datetime | None = None) -> list[dict[str, Any]]:
        cutoff = since.isoformat() if since else ""
        return [dict(e) for e in self._events if e.get("ts", "") >= cutoff]

    def recent_events(self, limit: int) -> list[dict[str, Any]]:
        return sorted(self._events, key=lambda e: e.get("ts", ""), reverse=True)[:limit]

    def recent_portal_events(self, limit: int) -> list[dict[str, Any]]:
        return sorted(self._portal_events, key=lambda e: e.get("timestamp", ""), reverse=True)[:limit]

    def excluded_emails(self) -> frozenset[str]:
        return frozenset(self._excluded)

    def set_excluded(self, email: str, excluded: bool) -> None:
        key = email.strip().casefold()
        if excluded:
            self._excluded.add(key)
        else:
            self._excluded.discard(key)


class FirestoreUsageStore:
    """Firestore store in the private database (same one as user accounts)."""

    def __init__(
        self,
        *,
        project: str | None = None,
        database: str = "(default)",
        portal_database: str = "(default)",
        client: Any = None,
        portal_client: Any = None,
    ) -> None:
        if client is None or (portal_client is None and portal_database != database):
            from google.cloud import firestore

            client = client or firestore.Client(project=project, database=database)
            if portal_client is None and portal_database != database:
                portal_client = firestore.Client(project=project, database=portal_database)
        self._client = client
        self._portal_client = portal_client or client

    def append(self, event: Mapping[str, Any]) -> None:
        self._client.collection(EVENTS_COLLECTION).document().set(dict(event))

    def list_events(self, since: datetime | None = None) -> list[dict[str, Any]]:
        query = self._client.collection(EVENTS_COLLECTION)
        if since is not None:
            query = query.where("ts", ">=", since.isoformat())
        return [snap.to_dict() for snap in query.stream()]

    def _recent(self, client: Any, collection: str, field: str, limit: int) -> list[dict[str, Any]]:
        from google.cloud import firestore

        query = client.collection(collection).order_by(field, direction=firestore.Query.DESCENDING).limit(limit)
        return [snap.to_dict() for snap in query.stream()]

    def recent_events(self, limit: int) -> list[dict[str, Any]]:
        return self._recent(self._client, EVENTS_COLLECTION, "ts", limit)

    def recent_portal_events(self, limit: int) -> list[dict[str, Any]]:
        return self._recent(self._portal_client, PORTAL_COLLECTION, "timestamp", limit)

    def _exclusions_ref(self):
        return self._client.collection(SETTINGS_COLLECTION).document(EXCLUSIONS_DOCUMENT)

    def excluded_emails(self) -> frozenset[str]:
        snap = self._exclusions_ref().get()
        data = snap.to_dict() if snap.exists else {}
        return frozenset(str(e).casefold() for e in (data or {}).get("emails", []))

    def set_excluded(self, email: str, excluded: bool) -> None:
        from google.cloud import firestore

        key = email.strip().casefold()
        op = firestore.ArrayUnion([key]) if excluded else firestore.ArrayRemove([key])
        self._exclusions_ref().set({"emails": op}, merge=True)


_SHARED_MEMORY_STORE = InMemoryUsageStore()


def create_usage_store(settings: Any) -> UsageStore:
    """Bind to the private database, or share one in-memory store offline."""
    if getattr(settings, "backend", "memory") == "memory" or not getattr(settings, "enabled", False):
        return _SHARED_MEMORY_STORE
    return FirestoreUsageStore(
        project=getattr(settings, "gcp_project", None) or None,
        database=getattr(settings, "firestore_private_db", "(default)"),
        # Same variable the portal uses to pick its growth database.
        portal_database=os.getenv("LOAD_FORGE_GROWTH_DATABASE", "(default)"),
    )


# --- Traction report -------------------------------------------------------

@dataclass
class UserTimeline:
    email: str
    name: str
    created_at: datetime
    events: list[dict[str, Any]] = field(default_factory=list)

    def count(self, *names: str) -> int:
        return sum(1 for e in self.events if e.get("event") in names)

    @property
    def interactive_sims(self) -> int:
        return sum(1 for e in self.events if _is_interactive_sim(e))

    @property
    def last_seen(self) -> str:
        return max((e.get("ts", "") for e in self.events), default="")

    @property
    def active_days(self) -> int:
        return len({e.get("ts", "")[:10] for e in self.events if e.get("ts")})


@dataclass
class TractionReport:
    gate_visitors: int
    signups: int
    activated: int
    saved: int
    published: int
    returned: int
    paywall: int
    load_types: Counter
    drivers: Counter
    users: list[UserTimeline]
    excluded_accounts: int

    def funnel(self) -> list[tuple[str, int]]:
        return [
            ("Reached sign-in wall (anonymous)", self.gate_visitors),
            ("Signed up", self.signups),
            ("Ran a simulation", self.activated),
            ("Saved a project", self.saved),
            ("Came back another day", self.returned),
            ("Published a project", self.published),
            ("Hit a paywall", self.paywall),
        ]


def _is_interactive_sim(event: Mapping[str, Any]) -> bool:
    """A Box Design render the visitor caused, not the unprompted default one."""
    return event.get("event") == "box_design_sim" and bool((event.get("props") or {}).get("interactive"))


def _parse_ts(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def traction_report(
    events: Iterable[Mapping[str, Any]],
    accounts: Iterable[Any],
    excluded_emails: frozenset[str] = frozenset(),
) -> TractionReport:
    """Aggregate events over real accounts (not admin, not excluded).

    ``accounts`` are ``saas.UserAccount``-like objects (email, name, uid,
    is_admin, created_at). Anonymous gate visitors are counted by ``anon_id``
    and exclude any anon id that ever belonged to an internal account.
    """
    events = [dict(e) for e in events]
    internal_emails = {e.casefold() for e in excluded_emails}
    real: dict[str, UserTimeline] = {}
    uid_to_email: dict[str, str] = {}
    for acc in accounts:
        email = str(acc.email).casefold()
        if acc.is_admin or email in internal_emails:
            internal_emails.add(email)
            continue
        real[email] = UserTimeline(email=email, name=acc.name, created_at=acc.created_at)
        if acc.uid:
            uid_to_email[acc.uid] = email

    internal_anon = {
        e.get("anon_id") for e in events
        if e.get("anon_id") and (e.get("email") or "").casefold() in internal_emails
    }
    gate_visitors = {
        e["anon_id"] for e in events
        if e.get("event") == "auth_gate_view" and e.get("anon_id") and e["anon_id"] not in internal_anon
    }

    load_types: Counter = Counter()
    drivers: Counter = Counter()
    for e in events:
        email = (e.get("email") or "").casefold() or uid_to_email.get(e.get("uid", ""), "")
        timeline = real.get(email)
        if timeline is None:
            continue
        timeline.events.append(e)
        if _is_interactive_sim(e):
            props = e.get("props") or {}
            if props.get("load_type"):
                load_types[props["load_type"]] += 1
            if props.get("driver"):
                drivers[props["driver"]] += 1

    def returned(t: UserTimeline) -> bool:
        created = t.created_at if t.created_at.tzinfo else t.created_at.replace(tzinfo=timezone.utc)
        return any(
            (ts := _parse_ts(e.get("ts", ""))) is not None and ts - created >= timedelta(days=1)
            for e in t.events if e.get("event") == "session_start"
        )

    users = sorted(real.values(), key=lambda t: t.created_at, reverse=True)
    for t in users:
        t.events.sort(key=lambda e: e.get("ts", ""))
    return TractionReport(
        gate_visitors=len(gate_visitors),
        signups=len(users),
        activated=sum(1 for t in users if t.interactive_sims or t.count("bass_match_run")),
        saved=sum(1 for t in users if t.count("project_saved")),
        published=sum(1 for t in users if t.count("project_published")),
        returned=sum(1 for t in users if returned(t)),
        paywall=sum(1 for t in users if t.count("paywall_seen")),
        load_types=load_types,
        drivers=drivers,
        users=users,
        excluded_accounts=len(internal_emails),
    )


# --- Live feed (LLOOGG-style raw stream) ------------------------------------

# Portal events that are infrastructure, not visitors.
_PORTAL_NOISE = frozenset({"deployment_verified"})


@dataclass(frozen=True)
class LiveRow:
    ts: str
    source: str        # "portal" | "studio"
    visitor: str       # email when known, else the anonymous id
    event: str
    detail: str
    referrer: str


def _portal_props(event: Mapping[str, Any]) -> dict[str, Any]:
    props = event.get("properties")
    return props if isinstance(props, dict) else {}


def _referrer_host(value: str) -> str:
    from urllib.parse import urlparse

    return urlparse(value).netloc if value else ""


def live_feed(
    portal_events: Iterable[Mapping[str, Any]],
    app_events: Iterable[Mapping[str, Any]],
    accounts: Iterable[Any],
    excluded_emails: frozenset[str] = frozenset(),
    limit: int = 100,
) -> list[LiveRow]:
    """Merge portal and Studio events newest-first, internal traffic removed.

    Anonymous portal ids are resolved to an email once the same id appears on
    a signed-in Studio event, so a visitor's whole path reads as one person.
    Dropped: deploy checks, and every event of an anonymous id that was ever
    tagged ``internal`` or belongs to an admin/test account.
    """
    app_events = [dict(e) for e in app_events]
    portal_events = [dict(e) for e in portal_events]
    internal = {e.casefold() for e in excluded_emails}
    internal |= {str(a.email).casefold() for a in accounts if a.is_admin}
    anon_to_email: dict[str, str] = {}
    for e in app_events:
        if e.get("anon_id") and e.get("email"):
            anon_to_email.setdefault(e["anon_id"], e["email"].casefold())
    internal_anon = {anon for anon, email in anon_to_email.items() if email in internal}
    # A browser tagged internal once (?lf_internal=1) hides its earlier visits too.
    internal_anon |= {
        str(e.get("anon_uid")) for e in portal_events
        if e.get("anon_uid") and _portal_props(e).get("internal")
    }

    rows: list[LiveRow] = []
    for e in portal_events:
        anon = str(e.get("anon_uid") or "")
        props = _portal_props(e)
        if e.get("event") in _PORTAL_NOISE or props.get("internal") or anon in internal_anon:
            continue
        detail = str(e.get("path") or "")
        extra = props.get("driver") or props.get("view") or props.get("cta") or ""
        rows.append(LiveRow(
            ts=_normalize_ts(str(e.get("timestamp") or "")),
            source="portal",
            visitor=anon_to_email.get(anon, anon),
            event=str(e.get("event") or ""),
            detail=f"{detail} · {extra}" if extra and extra not in detail else detail,
            referrer=_referrer_host(str(e.get("referrer") or "")),
        ))
    for e in app_events:
        email = (e.get("email") or "").casefold()
        anon = str(e.get("anon_id") or "")
        if email in internal or anon in internal_anon:
            continue
        props = e.get("props") or {}
        detail = " · ".join(str(v) for k, v in props.items() if k != "interactive" and v not in ("", None))
        if props.get("interactive") is False:
            detail = f"{detail} (default render)"
        rows.append(LiveRow(
            ts=_normalize_ts(str(e.get("ts") or "")),
            source="studio",
            visitor=email or anon_to_email.get(anon, anon),
            event=str(e.get("event") or ""),
            detail=detail,
            referrer="",
        ))
    rows.sort(key=lambda r: r.ts, reverse=True)
    return rows[:limit]


def _normalize_ts(value: str) -> str:
    """Portal uses ``...Z``, the Studio ``+00:00``; compare them as UTC."""
    parsed = _parse_ts(value.replace("Z", "+00:00")) if value else None
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S") if parsed else value


@dataclass(frozen=True)
class VisitorSummary:
    visitor: str
    first_seen: str
    last_seen: str
    arrived_from: str
    entry_page: str
    pages: int
    reached_studio: bool
    signed_in: bool
    last_event: str


_STUDIO_INTENT = frozenset({"app_open_clicked", "studio_cta_clicked", "bass_match_started"})


def visitor_summaries(rows: Iterable[LiveRow]) -> list[VisitorSummary]:
    """One line per visitor (most recently active first) from ``live_feed`` rows."""
    by_visitor: dict[str, list[LiveRow]] = {}
    for row in rows:
        by_visitor.setdefault(row.visitor, []).append(row)
    summaries = []
    for visitor, visits in by_visitor.items():
        visits.sort(key=lambda r: r.ts)
        first = visits[0]
        summaries.append(VisitorSummary(
            visitor=visitor,
            first_seen=first.ts,
            last_seen=visits[-1].ts,
            arrived_from=next((r.referrer for r in visits if r.referrer), "") or "direct",
            entry_page=first.detail if first.source == "portal" else "(Studio)",
            pages=sum(1 for r in visits if r.source == "portal" and r.event.endswith("_view")),
            reached_studio=any(r.source == "studio" or r.event in _STUDIO_INTENT for r in visits),
            signed_in="@" in visitor,
            last_event=visits[-1].event,
        ))
    summaries.sort(key=lambda v: v.last_seen, reverse=True)
    return summaries
