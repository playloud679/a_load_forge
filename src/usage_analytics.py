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
    def excluded_emails(self) -> frozenset[str]: ...
    def set_excluded(self, email: str, excluded: bool) -> None: ...


class InMemoryUsageStore:
    """Process-local store for tests, local runs and the memory backend."""

    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []
        self._excluded: set[str] = set()

    def append(self, event: Mapping[str, Any]) -> None:
        self._events.append(dict(event))

    def list_events(self, since: datetime | None = None) -> list[dict[str, Any]]:
        cutoff = since.isoformat() if since else ""
        return [dict(e) for e in self._events if e.get("ts", "") >= cutoff]

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

    def __init__(self, *, project: str | None = None, database: str = "(default)", client: Any = None) -> None:
        if client is None:
            from google.cloud import firestore

            client = firestore.Client(project=project, database=database)
        self._client = client

    def append(self, event: Mapping[str, Any]) -> None:
        self._client.collection(EVENTS_COLLECTION).document().set(dict(event))

    def list_events(self, since: datetime | None = None) -> list[dict[str, Any]]:
        query = self._client.collection(EVENTS_COLLECTION)
        if since is not None:
            query = query.where("ts", ">=", since.isoformat())
        return [snap.to_dict() for snap in query.stream()]

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
