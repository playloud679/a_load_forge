"""Project-context regressions, registered by the active test_all runner."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
ENV = {
    "LOAD_FORGE_SAAS_ENABLED": "true",
    "LOAD_FORGE_SAAS_BACKEND": "memory",
    "LOAD_FORGE_AUTH_BYPASS": "true",
    "LOAD_FORGE_DEV_UID": "phase-b-context",
    "LOAD_FORGE_DEV_EMAIL": "phase-b@example.invalid",
    "LOAD_FORGE_ALLOWED_EMAILS": "",
}


def app(view="bass-match"):
    at = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=60)
    at.query_params["view"] = view
    at.run()
    assert not at.exception, at.exception
    return at


def save(at):
    at.session_state["_cloud_autosave_force"] = True
    at.run()
    assert not at.exception, at.exception
    assert at.session_state["_cloud_save_status"] == "saved"


def visibility(at, value):
    field = next(item for item in at.selectbox if str(item.key).startswith("temp_project_visibility_"))
    field.set_value(value).run()
    at.button(key="action_project_visibility").click().run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]


def check_direct_entry_and_project_identity():
    with patch.dict(os.environ, ENV):
        idle = app("projects")
        idle.run()
        assert not idle.session_state.filtered_state.get("_cloud_project_id")
        assert any(".st-key-workspace_compat_control" in item.value and "display: none !important" in item.value for item in idle.markdown), "Legacy navigation must stay hidden without the illustrated stylesheet"
        for route, workspace in (("bass-match", "Bass Match"), ("box-design", "Box Design")):
            at = app(route)
            assert at.session_state["workspace_mode"] == workspace
            assert at.session_state["project_name"] == "Untitled project"
            save(at)
            project_id = at.session_state["_cloud_project_id"]
            from ui import account, runtime
            store, user = account._get_project_store(), runtime._CURRENT_SAAS_USER
            count = len(store.list_projects(user))
            for key in ("sidebar_manage_projects_btn", "workspace_tab_button_bass_match", "workspace_tab_button_box_design", "sidebar_manage_projects_btn"):
                at.button(key=key).click().run()
                assert not at.exception, at.exception
                save(at)
                assert at.session_state["_cloud_project_id"] == project_id
            assert len(store.list_projects(user)) == count
            name = next(item for item in at.text_input if str(item.key).startswith("temp_project_header_name_"))
            name.set_value("Compact 18 PA").run()
            at.button(key="action_project_header_rename").click().run()
            save(at)
            assert at.session_state["_cloud_project_id"] == project_id
            assert store.load_project(user, project_id).name == "Compact 18 PA"
            at.button(key="workspace_tab_button_bass_match").click().run()
            at.session_state["batch_pending_comparison"] = {
                "designs": [
                    {"load_type": "Bass reflex", "row": {"Driver": "Beyma 12CMV2", "Load": "Bass reflex", "Vb L": 38.0, "Fb Hz": 48.0}},
                    {"load_type": "Sealed", "row": {"Driver": "Beyma 12CMV2", "Load": "Sealed", "Vb L": 32.0}},
                ],
            }
            at.run()
            assert not at.exception, at.exception
            assert at.session_state["workspace_mode"] == "Box Design"
            assert len(at.session_state["design_comparison_tabs"]) >= 2
            assert at.session_state["_cloud_project_id"] == project_id


def check_visibility_lifecycle():
    with patch.dict(os.environ, ENV):
        at = app("box-design")
        save(at)
        from ui import account, runtime
        store, private, user = account._get_public_store(), account._get_project_store(), runtime._CURRENT_SAAS_USER
        project_id = at.session_state["_cloud_project_id"]
        visibility(at, "Public")
        original = store.project_publications(user, project_id)[0]
        assert original.visibility == "public"
        assert not any(c.value == "Changes not published" for c in at.caption)
        at.session_state["sim_voltage"] = 5.5
        save(at)
        assert any(c.value == "Changes not published" for c in at.caption)
        assert store.get_public_project(original.publication_id).parameters == original.parameters
        visibility(at, "Unlisted")
        assert store.get_public_project(original.publication_id).parameters == original.parameters
        assert store.get_public_project(original.publication_id).visibility == "unlisted"
        at.button(key="action_project_publish_update").click().run()
        assert not at.exception, at.exception
        updated = store.get_public_project(original.publication_id)
        assert updated.publication_version == original.publication_version + 1
        assert updated.parameters["parameters"]["sim_voltage"] == 5.5
        assert not any(c.value == "Changes not published" for c in at.caption)

        # Fresh session restores publication association without session-only IDs.
        reopened = app("projects")
        reopened.button(key=f"mp_list_open_{project_id}").click().run()
        assert not reopened.exception, reopened.exception
        assert next(item.value for item in reopened.selectbox if str(item.key).startswith("temp_project_visibility_")) == "Unlisted"
        # Withdraw every historical link, including old duplicate publications.
        legacy = store.publish_project(user, project_id, original.parameters, title=original.title, visibility="public", app_version="test")
        visibility(reopened, "Private")
        for published in (original, legacy):
            assert store.get_public_project(published.publication_id) is None
            assert store.get_public_project_version(published.publication_id, 1) is None
            try:
                store.clone_public_project(user, published.publication_id, "test", private_store=private)
            except Exception as exc:
                assert type(exc).__name__ == "ProjectMissingError"
            else:
                raise AssertionError("Withdrawn project was cloned")
        for embed in (False, True):
            withdrawn = AppTest.from_file(str(ROOT / "ui_app.py"), default_timeout=60)
            withdrawn.query_params["p"] = original.publication_id
            if embed:
                withdrawn.query_params["embed"] = "1"
            withdrawn.run()
            assert not withdrawn.exception, withdrawn.exception
            assert withdrawn.error or any("unavailable" in item.value for item in withdrawn.markdown), "Withdrawn content must not render through a direct link or embed"
        assert private.load_project(user, project_id) is not None
        visibility(reopened, "Public")
        assert len(store.project_publications(user, project_id)) == 2


def check_failed_save_prevents_switch():
    with patch.dict(os.environ, ENV):
        at = app("box-design")
        save(at)
        from ui import account, runtime
        store, user = account._get_project_store(), runtime._CURRENT_SAAS_USER
        project_id = at.session_state["_cloud_project_id"]
        other = store.save_project(user, "Other saved project", {"load_type": "Sealed", "sealed_vb_l": 20.0}, "test")
        at.session_state["sim_voltage"] = 7.25
        at.button(key="sidebar_manage_projects_btn").click().run()
        with patch.object(type(store), "save_project", side_effect=ConnectionError("offline")):
            visibility_field = next(item for item in at.selectbox if str(item.key).startswith("temp_project_visibility_"))
            visibility_field.set_value("Public").run()
            at.button(key="action_project_visibility").click().run()
            assert account._get_public_store().project_publications(user, project_id) == []
            at.button(key=f"mp_list_open_{other.project_id}").click().run()
            assert not at.exception, at.exception
            assert at.session_state["_cloud_project_id"] == project_id
            assert at.session_state["sim_voltage"] == 7.25
            assert at.error
            assert at.session_state["_cloud_save_status"] != "saved"
        at.button(key=f"mp_list_open_{other.project_id}").click().run()
        assert at.session_state["_cloud_project_id"] == other.project_id
        assert store.load_project(user, project_id).parameters["parameters"]["sim_voltage"] == 7.25


def check_public_store_access():
    import saas
    from storage.public_store import FirestorePublicStore, InMemoryPublicStore
    user = saas.user_from_claims({"sub": "phase-b-owner", "email": "owner@example.invalid"})
    stranger = saas.user_from_claims({"sub": "phase-b-stranger", "email": "stranger@example.invalid"})
    store = InMemoryPublicStore()
    record = store.publish_project(user, "prj_phase_b", {"load_type": "Sealed", "sealed_vb_l": 20.0}, title="Access test", visibility="public", app_version="test")
    assert store.project_publications(stranger, "prj_phase_b") == []
    try:
        store.set_visibility(stranger, record.publication_id, "unpublished")
    except saas.ProjectAccessError:
        pass
    else:
        raise AssertionError("Non-owner changed access")
    store.set_visibility(user, record.publication_id, "unpublished")
    assert store.get_public_project(record.publication_id) is None
    assert store.get_public_project_version(record.publication_id, 1) is None
    store.set_visibility(user, record.publication_id, "unlisted")
    assert store.get_public_project_version(record.publication_id, 1) is not None
    assert store.get_public_project(record.publication_id).publication_version == 1

    # Firestore access checks must use the current parent visibility for old versions.
    client = MagicMock()
    snapshot = client.collection.return_value.document.return_value.get.return_value
    snapshot.exists = True
    from dataclasses import asdict
    snapshot.to_dict.return_value = {**asdict(record), "visibility": "unpublished"}
    firestore = FirestorePublicStore(client=client)
    assert firestore.get_public_project(record.publication_id) is None
    assert firestore.get_public_project_version(record.publication_id, 1) is None
    with patch("google.cloud.firestore.transactional", side_effect=lambda fn: fn):
        firestore.set_visibility(user, record.publication_id, "unlisted")
        client.transaction.return_value.update.assert_called_once()
        try:
            firestore.set_visibility(stranger, record.publication_id, "public")
        except saas.ProjectAccessError:
            pass
        else:
            raise AssertionError("Firestore accepted non-owner access change")
