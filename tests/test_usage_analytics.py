"""Usage analytics regressions; registered in test_all.py."""
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import usage_analytics as ua

ROOT = Path(__file__).resolve().parents[1]
_T0 = datetime(2026, 9, 20, 12, tzinfo=timezone.utc)
_SAAS_ENV = {
    "LOAD_FORGE_SAAS_ENABLED": "true", "LOAD_FORGE_SAAS_BACKEND": "memory",
    "LOAD_FORGE_AUTH_REQUIRED": "true", "LOAD_FORGE_AUTH_BYPASS": "false",
    "LOAD_FORGE_ALLOWED_EMAILS": "",
}


def _acc(email, *, admin=False, created=_T0):
    return SimpleNamespace(email=email, name=email.split("@")[0], uid="uid-" + email,
                           is_admin=admin, created_at=created)


def _ev(event, email="", anon="", days=0.0, **props):
    return ua.build_event(event, email=email, anon_id=anon, props=props,
                          now=_T0 + timedelta(days=days))


def check_event_vocabulary():
    try:
        ua.build_event("page_view")
    except ValueError:
        pass
    else:
        raise AssertionError("Unknown events must be rejected")
    doc = ua.build_event("box_design_sim", email=" A@B.com ",
                         props={"driver": "x" * 500, "interactive": True, "n": 3, "none": None})
    assert doc["email"] == "a@b.com"
    assert len(doc["props"]["driver"]) == 120
    assert doc["props"]["interactive"] is True and doc["props"]["n"] == 3
    assert "none" not in doc["props"]


def check_traction_excludes_internal_traffic():
    accounts = [_acc("admin@x.com", admin=True), _acc("tester@x.com"),
                _acc("peter@x.com"), _acc("pierre@x.com")]
    events = [
        _ev("auth_gate_view", anon="a1"), _ev("auth_gate_view", anon="a2"),
        _ev("auth_gate_view", anon="a2"),          # same visitor twice
        _ev("auth_gate_view", anon="a_admin"),
        _ev("session_start", "admin@x.com", "a_admin"),
        _ev("box_design_sim", "admin@x.com", interactive=True, load_type="Sealed"),
        _ev("box_design_sim", "tester@x.com", interactive=True, load_type="Sealed"),
        # Peter only saw the default render: not activated.
        _ev("session_start", "peter@x.com", "a1"),
        _ev("box_design_sim", "peter@x.com", interactive=False, load_type="Sealed"),
        # Pierre changed the design, saved it and returned two days later.
        _ev("session_start", "pierre@x.com", "a2"),
        _ev("box_design_sim", "pierre@x.com", interactive=True, load_type="Bass reflex", driver="SB 10"),
        _ev("project_saved", "pierre@x.com"),
        _ev("session_start", "pierre@x.com", "a2", days=2),
        _ev("paywall_seen", "pierre@x.com", days=2),
    ]
    report = ua.traction_report(events, accounts, frozenset({"TESTER@x.com"}))
    assert report.excluded_accounts == 2
    assert report.gate_visitors == 2, "Admin anon id and duplicates must not count"
    assert report.signups == 2
    assert report.activated == 1
    assert report.saved == 1 and report.returned == 1 and report.paywall == 1
    assert report.load_types == {"Bass reflex": 1}
    assert report.drivers == {"SB 10": 1}
    assert {t.email for t in report.users} == {"peter@x.com", "pierre@x.com"}


def check_memory_store_exclusions():
    store = ua.InMemoryUsageStore()
    store.set_excluded("Joe@Example.com", True)
    assert store.excluded_emails() == {"joe@example.com"}
    store.set_excluded("joe@example.com", False)
    assert not store.excluded_emails()
    store.append(ua.build_event("session_start", now=_T0))
    assert len(store.list_events(since=_T0 + timedelta(days=1))) == 0
    assert len(store.list_events(since=_T0)) == 1


def check_gate_to_signup_keeps_anonymous_id():
    from ui import constants

    ua._SHARED_MEMORY_STORE._events.clear()
    with patch.dict(os.environ, _SAAS_ENV):
        at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=60)
        at.query_params.update({"view": "box-design", "lf_aid": "u_portal123"})
        at.run()
        assert not at.exception, at.exception
        from ui import navigation
        # The id must ride the 10-minute return cookie across the OIDC redirect.
        assert "lf_aid" in navigation.DESTINATION_KEYS
        assert "lf_aid" in at.query_params
        at.run()  # a rerun on the gate must not duplicate the event
        store = ua._SHARED_MEMORY_STORE  # ui_app may have hot-reloaded the module
        gate = [e for e in store._events if e["event"] == "auth_gate_view"]
        assert len(gate) == 1 and gate[0]["anon_id"] == "u_portal123", gate
        assert gate[0]["props"]["view"] == "box-design"
        at.session_state[constants._LOCAL_ACCOUNT_SESSION_KEY] = {
            "sub": "new-user", "email": "new.user@example.invalid", "name": "New user"}
        at.run()
        assert not at.exception, at.exception
        assert "lf_aid" not in at.query_params, "Signed-in URLs must not carry the anonymous id"
    # A local secrets.toml may swap in a development identity; the contract is
    # that whoever signs in keeps the portal's anonymous id.
    names = [e["event"] for e in store._events if e["email"]]
    assert names.count("session_start") == 1 and names.count("signup_completed") == 1, names
    assert all(e["anon_id"] == "u_portal123" for e in store._events)


def check_admin_console_requires_admin():
    with patch.dict(os.environ, _SAAS_ENV):
        from ui import constants

        at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=60)
        at.session_state[constants._LOCAL_ACCOUNT_SESSION_KEY] = {
            "sub": "intruder", "email": "intruder@example.invalid", "name": "Intruder"}
        at.query_params["admin_users"] = "1"
        at.run()
        assert not at.exception, at.exception
        assert any("restricted to the administrator" in e.value for e in at.error)
        assert not at.tabs, "Non-admins must not see the traction/accounts tabs"
