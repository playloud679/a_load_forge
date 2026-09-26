"""Portal/Studio regressions; registered in test_all.py's UI group."""
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import quote, urlencode

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


def app(query):
    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=60)
    at.query_params.update(query)
    at.run()
    assert not at.exception, at.exception
    return at


def check_catalog_handoff():
    at = app({"preset": "Beyma 12CMV2", "vb": "42", "fb": "30"})
    assert at.session_state["workspace_mode"] == "Box Design"
    assert at.session_state["driver_preset_name"] == "Beyma 12CMV2"
    assert at.session_state["load_type"] == "Bass reflex"
    assert at.session_state["reflex_vb_l"] == 42.0
    assert at.session_state["reflex_fb_hz"] == 30.0
    assert at.session_state["box_strategy"] == "Manual"
    at.session_state["reflex_vb_l"] = 47.0
    at.run()
    assert not at.exception, at.exception
    assert at.session_state["reflex_vb_l"] == 47.0, "Reruns must not reapply the URL"
    sealed = app({"preset": "Beyma 12CMV2", "load": "sealed", "vb": "42"})
    assert sealed.session_state["load_type"] == "Sealed"
    assert sealed.session_state["sealed_vb_l"] == 42.0
    assert sealed.session_state["box_strategy"] == "Manual"


def check_invalid_handoff():
    from ui import navigation
    # Validate before mutation, even when there is already a cloud project.
    for query in (
        {"preset": "missing-driver"},
        {"preset": "Beyma 12CMV2", "vb": "NaN"},
        {"preset": "Beyma 12CMV2", "fb": "inf"},
        {"preset": "Beyma 12CMV2", "vb": "-1"},
        {"preset": "Beyma 12CMV2", "load": "unknown"},
    ):
        state = {"driver_preset_name": "existing", "_cloud_project_id": "keep-me"}
        with patch.object(navigation.st, "query_params", query), patch.object(navigation.st, "session_state", state), patch.object(navigation.st, "warning") as warning:
            navigation.apply_catalog_handoff()
            assert state == {"driver_preset_name": "existing", "_cloud_project_id": "keep-me"}
            warning.assert_called_once()


def check_auth_return():
    from ui import navigation
    raw = quote(urlencode({"preset": "B&C 12/8 + test", "view": "box-design", "vb": "42", "redirect": "https://example.invalid", "token": "must-not-restore"}), safe="")
    for initial in ({}, {"view": "bass-match"}):
        query, state = dict(initial), {}
        with patch.object(navigation.st, "query_params", query), patch.object(navigation.st, "session_state", state), patch.object(navigation.st, "context", SimpleNamespace(cookies={"lf_return_destination": raw})), patch.object(navigation.st, "html"):
            navigation.restore_auth_destination()
            if initial:
                assert query == initial
            else:
                assert query == {"preset": "B&C 12/8 + test", "view": "box-design", "vb": "42"}
            query.clear()
            navigation.restore_auth_destination()
            assert not query, "Consumed cookie must not force navigation on rerun"


def check_handoff_preserves_cloud_project():
    env = {"LOAD_FORGE_SAAS_ENABLED": "true", "LOAD_FORGE_SAAS_BACKEND": "memory", "LOAD_FORGE_AUTH_BYPASS": "true", "LOAD_FORGE_DEV_UID": "portal-test", "LOAD_FORGE_DEV_EMAIL": "portal@example.invalid", "LOAD_FORGE_ALLOWED_EMAILS": ""}
    with patch.dict(os.environ, env):
        at = app({"view": "box-design"})
        at.session_state["project_name"] = "Existing work"
        at.session_state["_cloud_autosave_force"] = True
        at.run()
        assert not at.exception, at.exception
        old_id = at.session_state["_cloud_project_id"]
        from ui import account, runtime
        store, user = account._get_project_store(), runtime._CURRENT_SAAS_USER
        before = store.load_project(user, old_id).parameters
        at.query_params.clear()
        at.query_params.update({"preset": "Beyma 12CMV2", "vb": "42", "fb": "30"})
        at.run()
        assert not at.exception, at.exception
        assert at.session_state["driver_preset_name"] == "Beyma 12CMV2"
        assert at.session_state.filtered_state.get("_cloud_project_id") != old_id
        assert store.load_project(user, old_id).parameters == before


def check_login_destination():
    # Exercise the real email gate transition without connecting to an IdP/store.
    from ui import constants
    env = {"LOAD_FORGE_SAAS_ENABLED": "true", "LOAD_FORGE_SAAS_BACKEND": "memory", "LOAD_FORGE_AUTH_REQUIRED": "true", "LOAD_FORGE_AUTH_BYPASS": "false", "LOAD_FORGE_ALLOWED_EMAILS": "", "LOAD_FORGE_GUEST_ACCESS": "false"}
    with patch.dict(os.environ, env):
        at = app({"view": "box-design", "preset": "Beyma 12CMV2", "vb": "42", "load": "sealed"})
        assert "driver_fs_hz" not in at.session_state.filtered_state
        at.session_state[constants._LOCAL_ACCOUNT_SESSION_KEY] = {"sub": "portal-login", "email": "portal-login@example.invalid", "name": "Portal login"}
        at.session_state["_projects_after_login"] = True
        at.run()
        assert not at.exception, at.exception
        assert at.session_state["workspace_mode"] == "Box Design"
        assert at.session_state["driver_preset_name"] == "Beyma 12CMV2"
        assert at.session_state["sealed_vb_l"] == 42.0

