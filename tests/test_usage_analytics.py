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


def _run(at):
    """Run, then re-assert the test environment: a developer's local
    .streamlit/secrets.toml injects root keys (e.g. an auth bypass) into
    os.environ the first time Streamlit loads secrets."""
    at.run()
    os.environ.update(_SAAS_ENV)
    return at


def check_guest_save_to_signup_keeps_design_and_id():
    from ui import constants

    ua._SHARED_MEMORY_STORE._events.clear()
    with patch.dict(os.environ, _SAAS_ENV):
        at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=60)
        at.query_params.update({"view": "bass-match", "preset": "Beyma 12CMV2", "lf_aid": "u_portal123"})
        _run(at)
        assert not at.exception, at.exception
        store = ua._SHARED_MEMORY_STORE  # ui_app may have hot-reloaded the module
        guest = [e for e in store._events if e["event"] == "guest_session"]
        # A guest lands on a result, never on a sign-in wall, even from view=bass-match.
        assert guest[0]["anon_id"] == "u_portal123"
        assert at.session_state["workspace_mode"] == "Box Design"
        assert at.session_state["driver_preset_name"] == "Beyma 12CMV2"
        assert not [e for e in store._events if e["event"] == "auth_gate_view"]
        at.session_state["project_name"] = "My Beyma sub"
        at.button(key="guest_save_btn").click()
        _run(at)
        assert not at.exception, at.exception
        gate = [e for e in store._events if e["event"] == "auth_gate_view"]
        assert len(gate) == 1 and gate[0]["props"]["reason"] == "save", gate
        from ui import navigation
        for key in ("d", "name", "lf_aid"):
            assert key in navigation.DESTINATION_KEYS and key in at.query_params, key
        assert at.query_params["name"] in ("My Beyma sub", ["My Beyma sub"])
        at.session_state[constants._LOCAL_ACCOUNT_SESSION_KEY] = {
            "sub": "new-user", "email": "new.user@example.invalid", "name": "New user"}
        _run(at)
        assert not at.exception, at.exception
        assert "lf_aid" not in at.query_params, "Signed-in URLs must not carry the anonymous id"
        assert at.session_state["project_name"] == "My Beyma sub"
        assert at.session_state["driver_preset_name"] == "Beyma 12CMV2", "the guest's design is kept"
        assert "name" not in at.query_params
    names = [e["event"] for e in store._events if e["email"]]
    assert names.count("session_start") == 1 and names.count("signup_completed") == 1, names
    assert all(e["anon_id"] == "u_portal123" for e in store._events)


def check_guest_is_invited_not_charged_for_bass_match():
    with patch.dict(os.environ, _SAAS_ENV):
        at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=60)
        at.query_params.update({"preset": "Beyma 12CMV2"})
        _run(at)
        assert not at.exception, at.exception
        store = ua._SHARED_MEMORY_STORE
        assert any(e["event"] == "guest_session" for e in store._events)
        assert at.session_state["workspace_mode"] == "Box Design"
        # Clicking the Bass Match tab keeps the guest (and their design) in Box Design.
        tab = next(b for b in at.button if (b.key or "").startswith("workspace_tab_button_")
                   and "bass" in b.key)
        tab.click()
        _run(at)
        assert not at.exception, at.exception
        assert at.session_state["workspace_mode"] == "Box Design"
        assert at.session_state["driver_preset_name"] == "Beyma 12CMV2"
        assert at.button(key="guest_invite_sign_in_bass_match") is not None
        assert "finder_run_search_main" not in [b.key for b in at.button]
        at.button(key="guest_invite_sign_in_bass_match").click()
        _run(at)
        assert any(e["event"] == "auth_gate_view" and e["props"]["reason"] == "bass_match"
                   for e in store._events)
        at.button(key="continue_as_guest").click()
        _run(at)
        assert not at.exception, at.exception
        assert at.session_state["driver_preset_name"] == "Beyma 12CMV2", "design survives the sign-in page"


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


def _portal(event, anon, ts, path="/", referrer="", **props):
    return {"event": event, "anon_uid": anon, "timestamp": ts, "path": path,
            "referrer": referrer, "properties": props}


def check_live_feed_merges_and_filters():
    accounts = [_acc("admin@x.com", admin=True), _acc("peter@x.com"), _acc("tester@x.com")]
    portal = [
        _portal("driver_page_view", "u_peter", "2026-09-20T12:00:00.000Z",
                "/drivers/sb-10", "https://www.google.com/search?q=x"),
        _portal("app_open_clicked", "u_peter", "2026-09-20T12:01:00.000Z", view="box-design"),
        _portal("landing_view", "u_me", "2026-09-20T12:02:00.000Z", internal=True),
        _portal("deployment_verified", "u_ci", "2026-09-20T12:03:00.000Z"),
        _portal("landing_view", "u_admin", "2026-09-20T12:04:00.000Z"),
        _portal("landing_view", "u_stranger", "2026-09-20T12:05:00.000Z"),
    ]
    app = [
        _ev("auth_gate_view", anon="u_peter", days=1 / 1440 * 1.5),
        ua.build_event("session_start", email="peter@x.com", anon_id="u_peter",
                       now=_T0 + timedelta(minutes=3)),
        ua.build_event("box_design_sim", email="peter@x.com", anon_id="u_peter",
                       props={"load_type": "Sealed", "interactive": False}, now=_T0 + timedelta(minutes=4)),
        ua.build_event("session_start", email="admin@x.com", anon_id="u_admin", now=_T0),
        ua.build_event("session_start", email="tester@x.com", anon_id="u_t", now=_T0),
    ]
    rows = ua.live_feed(portal, app, accounts, frozenset({"tester@x.com"}))
    assert [r.ts for r in rows] == sorted((r.ts for r in rows), reverse=True), "newest first across formats"
    assert {r.visitor for r in rows} == {"peter@x.com", "u_stranger"}, rows
    peter = [r for r in rows if r.visitor == "peter@x.com"]
    assert [r.event for r in reversed(peter)] == [
        "driver_page_view", "app_open_clicked", "auth_gate_view", "session_start", "box_design_sim"]
    assert peter[-1].referrer == "www.google.com" and peter[-1].source == "portal"
    assert peter[0].detail == "Sealed (default render)"
    assert len(ua.live_feed(portal, app, accounts, limit=2)) == 2


def check_ui_live_feed_tab_renders():
    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=60)
    at.query_params["admin_users"] = "1"
    at.run()
    assert not at.exception, at.exception
    store = ua._SHARED_MEMORY_STORE  # after ui_app's hot reload
    store._portal_events[:] = [_portal("landing_view", "u_visitor", "2026-09-20T12:00:00.000Z")]
    at.run()
    assert not at.exception, at.exception
    assert [t.label for t in at.tabs][:3] == ["Live", "Traction (real users)", "Accounts & credits"]
    assert at.selectbox(key="live_feed_visitor") is not None
    store._portal_events.clear()


def check_live_feed_visitor_summaries():
    portal = [
        # The owner browsed before tagging the browser, then opened ?lf_internal=1.
        _portal("landing_view", "u_owner", "2026-09-25T22:18:27.000Z"),
        _portal("driver_page_view", "u_owner", "2026-09-25T22:19:05.000Z", "/drivers/misco-ms10-w"),
        _portal("landing_view", "u_owner", "2026-09-26T10:00:00.000Z", internal=True),
        # A Google visitor who bounced, and one who went on to the Studio.
        _portal("driver_page_view", "u_bounce", "2026-09-26T05:40:15.000Z",
                "/drivers/lowther-pm2a", "https://www.google.com/"),
        _portal("driver_page_view", "u_keen", "2026-09-26T06:00:00.000Z",
                "/drivers/sb-10", "https://www.google.com/"),
        _portal("app_open_clicked", "u_keen", "2026-09-26T06:01:00.000Z", view="box-design"),
    ]
    rows = ua.live_feed(portal, [], [])
    assert all(r.visitor != "u_owner" for r in rows), "tagging a browser hides its earlier visits"
    summaries = {v.visitor: v for v in ua.visitor_summaries(rows)}
    assert set(summaries) == {"u_bounce", "u_keen"}
    bounce, keen = summaries["u_bounce"], summaries["u_keen"]
    assert (bounce.pages, bounce.reached_studio, bounce.arrived_from) == (1, False, "www.google.com")
    assert bounce.entry_page == "/drivers/lowther-pm2a"
    assert keen.reached_studio and keen.last_event == "app_open_clicked"
    assert [v.visitor for v in ua.visitor_summaries(rows)] == ["u_keen", "u_bounce"]


def check_alternatives_similarity_is_pure_and_dedupes():
    from types import SimpleNamespace as NS

    from ui import alternatives as alt

    features = {
        "Beyma 12CMV2": (12.0, 38.0, 0.33, 95.0, 5.0),
        "WEB: SICA 12 Cx 3 PL": (12.0, 40.0, 0.35, 90.0, 4.0),
        "LSDB: SICA 12 Cx 3 PL": (12.0, 40.0, 0.35, 90.0, 4.0),   # same unit, other source
        "Tiny 4": (4.0, 80.0, 0.5, 5.0, 3.0),
        "No Xmax 12": (12.0, 38.5, 0.34, 94.0, 0.0),
    }
    picked = alt.similar_driver_names("Beyma 12CMV2", features, limit=5)
    assert len(picked) == 2 and picked[0].endswith("SICA 12 Cx 3 PL") and picked[1] == "Tiny 4", picked
    sealed = alt.similar_driver_names("Beyma 12CMV2", features, limit=5, needs_xmax=False)
    assert sealed[0] == "No Xmax 12"
    assert alt.similar_driver_names("Unknown", features) == []
    assert alt.box_total_volume_l("Bass reflex", NS(vb_l=42.0)) == 42.0
    assert alt.box_total_volume_l("DCCAV", NS(vh_l=10.0, vl_l=15.0)) == 25.0
    assert alt.box_total_volume_l("Infinite baffle", NS()) is None


def check_guest_sees_alternatives_on_landing():
    with patch.dict(os.environ, _SAAS_ENV):
        at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=90)
        at.query_params.update({"preset": "Beyma 12CMV2", "vb": "42", "fb": "30"})
        _run(at)
        assert not at.exception, at.exception
        opens = [b for b in at.button if (b.key or "").startswith("lf_alt_open_")]
        assert 1 <= len(opens) <= 5, [b.key for b in at.button]
        assert at.button(key="lf_alt_full_search") is not None
        store = ua._SHARED_MEMORY_STORE
        assert any(e["event"] == "alternatives_shown" for e in store._events)
        tabs_before = len(at.session_state["design_comparison_tabs"]) if "design_comparison_tabs" in at.session_state else 0
        opens[0].click()
        _run(at)
        assert not at.exception, at.exception
        assert any(e["event"] == "alternative_opened" for e in store._events)
        assert "batch_pending_result" not in at.session_state, "the opened alternative was applied"
        del tabs_before


def check_compare_entry_puts_alternatives_on_top():
    with patch.dict(os.environ, _SAAS_ENV):
        at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=90)
        at.query_params.update({"preset": "Beyma 12CMV2", "vb": "42", "fb": "30", "compare": "1"})
        _run(at)
        assert not at.exception, at.exception
        assert at.button(key="lf_alt_hide") is not None, "compare entries show Bass Match on top"
        assert "compare" not in at.query_params
        assert any((b.key or "").startswith("lf_alt_open_") for b in at.button)
        at.button(key="lf_alt_hide").click()
        _run(at)
        assert not at.exception, at.exception
        assert "lf_alt_hide" not in [b.key for b in at.button]
        assert any((b.key or "").startswith("lf_alt_open_") for b in at.button), "still listed under the chart"
