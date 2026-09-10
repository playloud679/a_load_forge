"""Project persistence (LFP), cloud autosave, community and public project pages."""

from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import re
import time
import uuid
import zlib
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

import compare_afw_sealed as _afw_compare
import numpy as np
import pandas as pd
import streamlit as st

import acoustics as _acoustics
import billing as _billing
import saas as _saas

from . import account as _account
from . import analysis as _analysis
from . import catalog as _catalog
from . import constants as _constants
from . import runtime as _runtime
from . import state as _state


def _compact_result_row(row: dict) -> dict:
    """Omit null/NaN fields from saved rows to keep .lfp files lightweight."""
    return {
        key: value
        for key, value in row.items()
        if value is not None and not (isinstance(value, float) and not np.isfinite(value))
    }

def _serialize_bass_match_context(value) -> dict:
    """Encode Finder context without arrays nested inside Firestore arrays.

    Firestore supports arrays of scalar values/maps, but rejects an array whose
    element is another array.  The live Finder context starts with a tuple of
    selected load types, so serializing it directly creates exactly that
    invalid shape.  A named object preserves the portable format while keeping
    every context value available for restoration.
    """
    if isinstance(value, dict):
        load_types = value.get("load_types", [])
        values = value.get("values", [])
    elif isinstance(value, (list, tuple)):
        load_types = value[0] if value else []
        values = value[1:] if value else []
    else:
        load_types = []
        values = []
    if not isinstance(load_types, (list, tuple)):
        load_types = [load_types] if load_types else []
    if not isinstance(values, (list, tuple)):
        values = [values] if values else []
    return {
        "load_types": _state._json_safe(list(load_types)),
        "values": _state._json_safe(list(values)),
    }

def _collect_bass_match_project_state(
    *,
    include_results: bool = True,
) -> dict:
    state = {}
    for key in _constants._BASS_MATCH_PROJECT_STATE_KEYS:
        if key in st.session_state:
            state[key] = _state._json_safe(st.session_state[key])
    bass_match = {"state": state}
    if include_results:
        defaults = {
            "batch_results": [],
            "batch_result_context": [],
            "batch_search_completed": False,
            "finder_last_run_stats": {},
        }
        for key in _constants._BASS_MATCH_PROJECT_RESULT_KEYS:
            val = st.session_state.get(key, defaults[key])
            if key == "batch_results" and isinstance(val, list):
                val = [
                    _compact_result_row(row)
                    for row in val[:_constants._LFP_MAX_SAVED_BATCH_RESULTS]
                    if isinstance(row, dict)
                ]
            elif key == "batch_result_context":
                val = _serialize_bass_match_context(val)
            bass_match[key] = _state._json_safe(val)
    return bass_match

def _build_lfp_project(
    project: dict | None = None,
    *,
    include_results: bool = True,
) -> dict:
    """Build the complete portable project, including Bass Match state."""
    name = str(
        (project or {}).get("name")
        if (project or {}).get("name") is not None
        else st.session_state.get("project_name", "")
    ).strip()
    now = datetime.now(UTC).isoformat()
    project_id = str(
        st.session_state.get("_portable_project_id") or f"lfp_{uuid.uuid4().hex}"
    )
    created_at = str(st.session_state.get("_portable_project_created_at") or now)
    st.session_state["_portable_project_id"] = project_id
    st.session_state["_portable_project_created_at"] = created_at
    project_meta = {
        "id": project_id,
        "name": name,
        "created_at": created_at,
        "updated_at": now,
    }
    payload = {
        "_load_forge_meta": {
            "version": _runtime._VERSION,
            "format": _constants._LFP_FORMAT_VERSION,
            "kind": "project",
        },
        "project": _state._json_safe(project_meta),
        "parameters": _state._json_safe(_state._collect_params()),
        "bass_match": _collect_bass_match_project_state(
            include_results=include_results
        ),
    }
    # Keep an unnamed local draft renderable, but never treat it as a valid
    # cloud/LFP project. Autosave and export/duplication gate this payload on a
    # user-supplied name before persistence.
    if _project_name_is_placeholder(name):
        return payload
    return _saas.validate_project_payload(payload, allow_legacy=False)

def _process_project_cover_image(uploaded_file, max_dim: int = 800, quality: int = 80) -> str | None:
    """Process, resize and optimize user-uploaded build/cabinet photo into a compact WebP base64 URI."""
    if uploaded_file is None:
        return None
    try:
        import base64
        import io

        from PIL import Image

        raw_bytes = uploaded_file.getvalue() if hasattr(uploaded_file, "getvalue") else uploaded_file.read()
        if not raw_bytes:
            return None
        img = Image.open(io.BytesIO(raw_bytes))
        img = img.convert("RGB")
        img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="WEBP", quality=quality, method=4)
        encoded = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/webp;base64,{encoded}"
    except Exception as exc:
        _runtime.logger.warning("Could not process uploaded cover image: %s", exc)
        return None

def _bass_match_results_signature() -> str:
    """Hash heavy Finder output once, then reuse it across UI reruns."""
    cached = st.session_state.get("_bass_match_results_signature")
    if isinstance(cached, str) and cached:
        return cached
    result_payload = {
        key: _state._json_safe(st.session_state.get(key, default))
        for key, default in {
            "batch_results": [],
            "batch_result_context": [],
            "batch_search_completed": False,
            "finder_last_run_stats": {},
        }.items()
    }
    encoded = json.dumps(
        result_payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    signature = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    st.session_state["_bass_match_results_signature"] = signature
    return signature

def _invalidate_bass_match_results_signature() -> None:
    st.session_state.pop("_bass_match_results_signature", None)

def _apply_lfp_project(payload: dict) -> int:
    """Load current v2 projects and legacy flat v1 parameter presets."""
    if not isinstance(payload, dict):
        raise TypeError("LFP project must be a JSON object")
    metadata = payload.get("_load_forge_meta", {})
    format_version = int(metadata.get("format", 1)) if isinstance(metadata, dict) else 1
    if format_version < 2 or "parameters" not in payload:
        legacy = dict(payload)
        legacy.pop("_load_forge_meta", None)
        return _apply_loaded_params(legacy)

    payload = _saas.validate_project_payload(
        payload,
        allow_legacy=False,
        require_complete=False,
    )

    parameters = payload.get("parameters")
    if not isinstance(parameters, dict):
        raise TypeError("LFP project parameters must be an object")
    applied = _apply_loaded_params(parameters)

    bass_match = payload.get("bass_match", {})
    if bass_match is not None and not isinstance(bass_match, dict):
        raise TypeError("LFP Bass Match state must be an object")
    bass_match = bass_match or {}
    state = bass_match.get("state", {})
    if state is not None and not isinstance(state, dict):
        raise TypeError("LFP Bass Match controls must be an object")
    for key, value in (state or {}).items():
        if key in _constants._BASS_MATCH_PROJECT_STATE_KEYS:
            st.session_state[key] = value
    for key in list(st.session_state):
        if "__toggle_v4__" in str(key):
            st.session_state.pop(key, None)

    rows = bass_match.get("batch_results", [])
    if rows is not None and (
        not isinstance(rows, list)
        or any(not isinstance(row, dict) for row in rows)
    ):
        raise TypeError("LFP Bass Match results must be a list of rows")
    st.session_state["batch_results"] = list(rows or [])
    context = bass_match.get("batch_result_context", [])
    if isinstance(context, dict):
        load_types = context.get("load_types", [])
        values = context.get("values", [])
        if not isinstance(load_types, (list, tuple)):
            raise TypeError("LFP Bass Match context load types must be a list")
        if not isinstance(values, (list, tuple)):
            raise TypeError("LFP Bass Match context values must be a list")
        restored_context = [list(load_types), *list(values)]
    elif isinstance(context, (list, tuple)):
        # Legacy v2 projects used a nested list for the selected load types.
        # Keep accepting that shape for existing .lfp files.
        restored_context = list(context or ())
    else:
        raise TypeError("LFP Bass Match result context must be a list or object")
    if restored_context and isinstance(restored_context[0], list):
        restored_context[0] = tuple(restored_context[0])
    st.session_state["batch_result_context"] = tuple(restored_context)
    st.session_state["batch_search_completed"] = bool(
        bass_match.get("batch_search_completed", False)
    )
    run_stats = bass_match.get("finder_last_run_stats", {})
    if run_stats is not None and not isinstance(run_stats, dict):
        raise TypeError("LFP Bass Match run statistics must be an object")
    st.session_state["finder_last_run_stats"] = dict(run_stats or {})
    if st.session_state["batch_results"]:
        # A fresh Streamlit session runs _ensure_finder_defaults before the
        # project is opened. Without this marker, that migration would clear
        # the restored result rows on the following rerun because the version
        # key is not part of the user-facing Finder controls.
        st.session_state["_finder_defaults_version"] = _constants._FINDER_DEFAULTS_VERSION
        st.session_state["_restored_bass_match_controls_signature"] = "pending"
    else:
        st.session_state.pop(
            "_restored_bass_match_controls_signature",
            None,
        )
    _invalidate_bass_match_results_signature()
    _bass_match_results_signature()
    return applied + len(state or {})

def _clear_active_project_state() -> None:
    """Clear all project-owned values so normal defaults seed a clean project."""
    for key in list(st.session_state):
        if (
            _state._is_param_key(key)
            or key in _constants._BASS_MATCH_PROJECT_STATE_KEYS
            or key in _constants._BASS_MATCH_PROJECT_RESULT_KEYS
            or key in _constants._PROJECT_TRANSIENT_STATE_KEYS
            or str(key).startswith(_constants._PROJECT_TRANSIENT_STATE_PREFIXES)
            or "__toggle_v4__" in str(key)
        ):
            st.session_state.pop(key, None)
    st.session_state.pop("_design_state_backup", None)
    st.session_state.pop("_restored_bass_match_controls_signature", None)
    _invalidate_bass_match_results_signature()

def _apply_loaded_params(data: dict) -> int:
    legacy_passive_radiator = data.get("load_type") == "Passive radiator"
    applied = 0
    for key, value in data.items():
        if _state._is_param_key(key):
            if key == "load_type" and value in ("Suspension pneumatic", "Acoustic suspension"):
                value = "Sealed"
            elif key == "load_type" and value == "Passive radiator":
                value = "Bass reflex"
            st.session_state[key] = value
            applied += 1
    if legacy_passive_radiator:
        st.session_state["reflex_resonator_type"] = _constants._RESONATOR_PR
        if "pr_vb_l" in data and "reflex_vb_l" not in data:
            st.session_state["reflex_vb_l"] = float(data["pr_vb_l"])
    if "box_strategy" not in data:
        if st.session_state.get("sim_auto_align", True):
            strategy = "Max extension"
        elif st.session_state.get("opt_align_mode") == "Optimized (goals)":
            strategy = _state._normalize_box_strategy("Optimized")
        else:
            strategy = "Manual"
    else:
        strategy = _state._normalize_box_strategy(st.session_state.get("box_strategy", "Max extension"))
    _state._set_box_strategy_state(strategy)
    if strategy in _constants._OPT_OBJECTIVE_LABELS:
        st.session_state["_optimizer_engine_revision"] = 0
    return applied

def _encode_share_payload() -> str:
    payload = json.dumps(_state._collect_params(), sort_keys=True, separators=(",", ":"))
    packed = zlib.compress(payload.encode("utf-8"), 9)
    return base64.urlsafe_b64encode(packed).decode("ascii").rstrip("=")

def _share_link_url(token: str) -> str:
    """Best-effort absolute share link; falls back to a relative query string."""
    try:
        base = str(st.context.url or "").split("?", 1)[0]
    except Exception:
        base = ""
    return f"{base}?d={token}"

def _public_project_url(publication_id: str) -> str:
    """Best-effort absolute public project URL; falls back to a relative query string."""
    try:
        base = str(st.context.url or "").split("?", 1)[0]
    except Exception:
        base = ""
    return f"{base}?p={publication_id}"

def _decode_share_payload(token: str) -> dict:
    padded = token + "=" * (-len(token) % 4)
    payload = zlib.decompress(base64.urlsafe_b64decode(padded.encode("ascii")))
    data = json.loads(payload.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Share payload must be a parameter mapping")
    return data

def _render_authenticated_account_controls(user: _saas.SaaSUser) -> None:
    """Show the signed-in identity in the sidebar."""
    acc = _account._get_current_user_account()
    if acc is None:
        return
    entitlements = _saas.effective_entitlements(user, _runtime._SAAS_SETTINGS)
    if entitlements.promotion == "open_beta":
        tier_label = "Open Beta · full access"
    else:
        tier_label = f"{user.plan.capitalize()} plan"
    st.markdown(f"**Account** · *{acc.plan.upper()}*")
    st.caption(f"{user.name or user.email} · {tier_label}")
    if user.email and user.email != (user.name or ""):
        st.caption(user.email)
    st.markdown(
        f"**{acc.credits_balance:,}** / {acc.credits_monthly_quota:,} credits"
    )
    st.caption(f"Monthly refill: {acc.quota_reset_at.strftime('%d %b %Y')}")
    account_col, logout_col = st.columns([3, 2])
    with account_col:
        st.caption(f"Total simulated: {acc.total_simulations_run:,}")
    with logout_col:
        if not _runtime._SAAS_SETTINGS.auth_bypass and st.button(
            "Sign out",
            key="saas_sign_out",
            width="stretch",
        ):
            _account._sign_out_saas()
    st.divider()

def _project_download_filename(name: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", str(name).strip()).strip("._")
    return f"{stem or 'load_forge_project'}.lfp"

def _project_name_is_placeholder(name: object) -> bool:
    """Return whether a project has no user-supplied name yet."""
    normalized = str(name or "").strip().casefold()
    return not normalized or normalized == _constants._UNTITLED_PROJECT_NAME.casefold()

def _project_display_name(name: object) -> str:
    """Return a non-persisted label for an unnamed local draft."""
    value = str(name or "").strip()
    return value if not _project_name_is_placeholder(value) else "Name required"

def _mark_cloud_project_dirty(*, immediate: bool = False) -> None:
    """Flag a structural project change for the autosave fragment."""
    st.session_state["_cloud_save_status"] = "unsaved"
    st.session_state["_cloud_dirty_since"] = 0.0 if immediate else time.monotonic()
    if immediate:
        st.session_state["_cloud_autosave_force"] = True

def _set_active_cloud_record(record: _saas.ProjectRecord) -> None:
    st.session_state["_cloud_project_id"] = record.project_id
    st.session_state["_cloud_project_revision"] = record.revision
    st.session_state["_cloud_saved_hash"] = record.content_hash
    st.session_state["_cloud_observed_hash"] = record.content_hash
    st.session_state["_cloud_save_status"] = "saved"
    st.session_state["_cloud_save_failure_count"] = 0
    st.session_state.pop("_cloud_save_retry_at", None)
    st.session_state.pop("_cloud_save_error", None)
    st.session_state.pop("_cloud_save_error_kind", None)
    st.session_state.pop("_cloud_conflict", None)

def _apply_cloud_record(record: _saas.ProjectRecord) -> int:
    payload = _saas.validate_project_payload(
        record.parameters,
        require_complete=False,
    )
    _state._snapshot_design_state()
    if "parameters" in payload:
        applied = _apply_lfp_project(payload)
    else:
        applied = _apply_loaded_params(payload)
    st.session_state["project_name"] = record.name
    st.session_state["_project_name_revision"] = int(
        st.session_state.get("_project_name_revision", 0)
    ) + 1
    _set_active_cloud_record(record)
    return applied

def _queue_cloud_record_activation(
    record: _saas.ProjectRecord,
    *,
    notice: str = "",
) -> None:
    """Apply a cloud project at the start of the next Streamlit run.

    Public project actions render after the sidebar, so their click handlers
    cannot safely overwrite keys owned by already-instantiated widgets.  Keep
    only the new project identity here and load its state before widgets are
    created on the rerun.
    """
    st.session_state["_pending_cloud_project_id"] = record.project_id
    if notice:
        st.session_state["_pending_cloud_project_notice"] = notice

def _apply_pending_cloud_record() -> int:
    """Activate a queued cloud project before any widget-backed state exists."""
    project_id = st.session_state.pop("_pending_cloud_project_id", None)
    if not project_id:
        return 0
    notice = str(st.session_state.pop("_pending_cloud_project_notice", "")).strip()
    if _runtime._CURRENT_SAAS_USER is None:
        raise _saas.ProjectAccessError(
            "Sign in again to open the cloned cloud project"
        )
    record = _account._get_project_store().load_project(
        _runtime._CURRENT_SAAS_USER,
        str(project_id),
    )
    if record is None:
        raise _saas.ProjectMissingError("Cloned cloud project was not found")
    applied = _apply_cloud_record(record)
    _invalidate_cloud_project_list()
    st.session_state["workspace_mode"] = "Box Design"
    if notice:
        st.toast(notice)
    return applied

def _cloud_autosave_step(
    store,
    user: _saas.SaaSUser,
    *,
    now: float | None = None,
    force: bool = False,
) -> str:
    """Advance one non-blocking debounced autosave attempt."""
    now = time.monotonic() if now is None else float(now)
    name = str(st.session_state.get("project_name", "")).strip()
    if _project_name_is_placeholder(name):
        if st.session_state.get("_cloud_project_id"):
            # Do not keep attaching a legacy auto-created placeholder record
            # to the active draft. Naming it later will create a fresh record.
            _detach_cloud_project()
        st.session_state["_cloud_save_status"] = "name_required"
        st.session_state.pop("_cloud_save_error", None)
        st.session_state.pop("_cloud_save_error_kind", None)
        return "name_required"
    try:
        payload = _build_lfp_project({"name": name}, include_results=True)
    except Exception as exc:
        st.session_state["_cloud_save_status"] = "failed"
        st.session_state["_cloud_save_error"] = str(exc)
        st.session_state["_cloud_save_error_kind"] = "invalid"
        _runtime.logger.exception("Project autosave validation failed")
        return "failed"
    status, _ = _saas.advance_project_autosave(
        store,
        user,
        name,
        payload,
        _runtime._VERSION,
        st.session_state,
        now=now,
        force=force,
        debounce_seconds=_constants._AUTOSAVE_DEBOUNCE_SECONDS,
        retry_delays=_constants._AUTOSAVE_RETRY_DELAYS,
    )
    if status == "conflict":
        # Another tab/device may have committed one revision while this tab
        # was solving Bass Match or changing a load. Rebase the optimistic
        # revision marker and retry the local payload once, without replacing
        # the user's in-memory design with the remote one.
        project_id = st.session_state.get("_cloud_project_id")
        latest = (
            store.load_project(user, str(project_id))
            if project_id
            else None
        )
        if latest is not None:
            _set_active_cloud_record(latest)
            status, _ = _saas.advance_project_autosave(
                store,
                user,
                name,
                payload,
                _runtime._VERSION,
                st.session_state,
                now=time.monotonic(),
                force=True,
                debounce_seconds=_constants._AUTOSAVE_DEBOUNCE_SECONDS,
                retry_delays=_constants._AUTOSAVE_RETRY_DELAYS,
            )
    return status

def _render_cloud_persistence_status() -> None:
    if not (_runtime._SAAS_SETTINGS.enabled and _runtime._CURRENT_SAAS_USER is not None):
        return
    _cloud_persistence_fragment()

@st.fragment(run_every=2)
def _cloud_persistence_fragment() -> None:
    """Advance debounce/retries after the last edit without rerunning the workspace."""
    force = bool(st.session_state.pop("_cloud_autosave_force", False))
    try:
        status = _cloud_autosave_step(
            _account._get_project_store(),
            _runtime._CURRENT_SAAS_USER,
            force=force,
        )
    except Exception as exc:
        kind = _saas.project_error_kind(exc)
        _runtime.logger.exception("Could not initialize cloud project persistence")
        st.session_state["_cloud_save_status"] = "failed"
        st.session_state["_cloud_save_error"] = str(exc)
        st.session_state["_cloud_save_error_kind"] = kind
        status = "failed"
    label = _constants._SAVE_STATUS_LABELS.get(status, "Unsaved changes")
    color = "#34d399" if status == "saved" else (
        "#fbbf24"
        if status in {"unsaved", "saving", "retrying", "name_required"}
        else "#f87171"
    )
    st.markdown(
        f"<div title='Cloud persistence status' style='font-size:.76rem;"
        f"color:{color};margin:-.25rem 0 .45rem 0'>● {html.escape(label)}</div>",
        unsafe_allow_html=True,
    )
    if status == "name_required":
        st.caption("Name this project in Manage Projects to enable cloud save.")
    if status in {"failed", "conflict"}:
        error_kind = str(st.session_state.get("_cloud_save_error_kind", "unknown"))
        error = str(st.session_state.get("_cloud_save_error", "")).strip()
        st.error(_cloud_persistence_error_message(error_kind))
        if error and error_kind == "unknown":
            st.caption(error[:240])
        if st.button("Retry cloud save", key="project_cloud_retry", width="stretch"):
            st.session_state["_cloud_save_failure_count"] = 0
            _mark_cloud_project_dirty(immediate=True)
            st.rerun()

def _invalidate_cloud_project_list() -> None:
    st.session_state.pop("_cloud_project_summaries", None)
    st.session_state.pop("_cloud_project_summaries_at", None)

def _cloud_project_summaries(*, force: bool = False) -> list[_saas.ProjectSummary]:
    now = time.monotonic()
    cached = st.session_state.get("_cloud_project_summaries")
    cached_at = float(st.session_state.get("_cloud_project_summaries_at", 0.0) or 0.0)
    if not force and isinstance(cached, list) and now - cached_at < 30.0:
        return cached
    summaries = _account._get_project_store().list_projects(
        _runtime._CURRENT_SAAS_USER,
        limit=200,
        include_deleted=True,
    )
    st.session_state["_cloud_project_summaries"] = summaries
    st.session_state["_cloud_project_summaries_at"] = now
    return summaries

def _record_lfp_export() -> None:
    st.session_state["_last_lfp_export_at"] = datetime.now(UTC).isoformat()

def _cloud_persistence_error_message(kind: str) -> str:
    """Return a concise recovery instruction without exposing project contents."""
    if kind == "auth":
        if not os.environ.get("K_SERVICE"):
            return (
                "Cloud save is unavailable because local Google Cloud credentials "
                "are missing or expired. Run `gcloud auth application-default login`, "
                "then restart Load Forge."
            )
        return "Cloud save authentication expired. Sign in again, then retry."
    if kind == "permission":
        return (
            "Firestore denied this project write. Check the service account or "
            "Firestore permissions, then retry."
        )
    if kind == "invalid":
        return (
            "This project state did not pass validation, so the previous cloud "
            "revision was preserved."
        )
    if kind == "transient":
        return "Cloud save could not connect after retrying. Check the connection, then retry."
    if kind == "conflict":
        return "Another session changed this project. The latest revision was fetched; retry the local save."
    return "Cloud save failed. Check the Firestore configuration or connection, then retry."

def _detach_cloud_project(*, suppress_hash: str | None = None) -> None:
    for key in (
        "_cloud_project_id",
        "_cloud_project_revision",
        "_cloud_saved_hash",
        "_cloud_observed_hash",
        "_cloud_conflict",
    ):
        st.session_state.pop(key, None)
    if suppress_hash:
        st.session_state["_cloud_suppressed_hash"] = suppress_hash
    else:
        st.session_state.pop("_cloud_suppressed_hash", None)

def _duplicate_active_project() -> None:
    """Create an independent duplicate copy of the active project."""
    if _project_name_is_placeholder(st.session_state.get("project_name", "")):
        st.warning("Name the project before duplicating it.")
        return
    store = _account._get_project_store()
    current_name = str(st.session_state.get("project_name", _constants._UNTITLED_PROJECT_NAME))
    copy_name = f"{current_name} (Copy)"
    payload = _build_lfp_project({"name": copy_name}, include_results=True)
    if _runtime._CURRENT_SAAS_USER is not None and _runtime._SAAS_SETTINGS.enabled:
        record = store.save_project(
            _runtime._CURRENT_SAAS_USER,
            copy_name,
            payload,
            _runtime._VERSION,
            expected_revision=0,
        )
        _apply_cloud_record(record)
        _invalidate_cloud_project_list()
    else:
        st.session_state["project_name"] = copy_name
        _detach_cloud_project()
        _mark_cloud_project_dirty(immediate=True)
    st.toast(f"Duplicated project: {copy_name}")

def _create_new_project(name: str) -> None:
    """Reset active state and initialize a newly named independent project."""
    project_name = str(name).strip()
    if not project_name:
        raise ValueError("Project name is required")
    _clear_active_project_state()
    _state._reset_finder_defaults()
    st.session_state.pop("_new_project_name_prompt", None)
    st.session_state["workspace_mode"] = "Manage Projects"
    st.session_state["project_name"] = project_name[:80]
    st.session_state["_project_name_revision"] = int(
        st.session_state.get("_project_name_revision", 0)
    ) + 1
    _detach_cloud_project()
    _mark_cloud_project_dirty(immediate=True)
    st.toast(f"Initialized new project: {project_name[:80]}")

def _open_manage_projects_workspace() -> None:
    """Leave any public/admin route and open the project-management workspace."""
    for key in ("explore", "p", "embed", "maintenance", "admin_users"):
        st.query_params.pop(key, None)
    _state._select_workspace("Manage Projects")

def _open_community_workspace() -> None:
    """Leave other routes and switch into the Community Hub workspace in the same tab."""
    for key in ("p", "embed", "maintenance", "admin_users"):
        st.query_params.pop(key, None)
    st.query_params["explore"] = "1"
    st.session_state["workspace_mode"] = "Community"

def _open_technical_page(publication_id: str) -> None:
    """Open technical snapshot page within the same application session without opening new tabs."""
    for key in ("explore", "embed", "maintenance", "admin_users"):
        st.query_params.pop(key, None)
    st.query_params["p"] = publication_id
    st.session_state["workspace_mode"] = "Technical View"

def _request_new_project_name() -> None:
    """Show the required blank name prompt without changing the active project."""
    st.session_state["_new_project_name_prompt"] = True

@lru_cache(maxsize=1)
def _community_tab_image_b64() -> str:
    if _constants._COMMUNITY_TAB_IMAGE.exists():
        return base64.b64encode(_constants._COMMUNITY_TAB_IMAGE.read_bytes()).decode("ascii")
    return ""

def _render_hud_explore_community_button(key: str = "sidebar_community_btn") -> None:
    """Render the high-tech blueprint cyber-HUD button for transitioning to Community."""
    b64 = _community_tab_image_b64()
    st.markdown(
        f"""<style>
        .st-key-hud_community_nav {{
            margin: 4px 0 10px 0 !important;
            width: 100% !important;
        }}
        .st-key-hud_community_nav div[data-testid="stButton"] button {{
            background-color: transparent !important;
            border: none !important;
            border-radius: 0 !important;
            height: clamp(3.4rem, 6vw, 4.8rem) !important;
            min-height: 3.4rem !important;
            position: relative !important;
            overflow: hidden !important;
            padding: 0 !important;
            width: 100% !important;
            box-shadow: none !important;
            transition: transform .16s ease, filter .16s ease !important;
        }}
        .st-key-hud_community_nav div[data-testid="stButton"] button::before {{
            content: "" !important;
            position: absolute !important;
            inset: 0 !important;
            background-image: url("data:image/png;base64,{b64}") !important;
            background-position: center !important;
            background-repeat: no-repeat !important;
            background-size: contain !important;
            pointer-events: none !important;
            transition: filter .16s ease, transform .16s ease !important;
        }}
        .st-key-hud_community_nav div[data-testid="stButton"] button p {{
            opacity: 0 !important;
            pointer-events: none !important;
        }}
        .st-key-hud_community_nav div[data-testid="stButton"] button:hover {{
            background-color: transparent !important;
            border: none !important;
            box-shadow: none !important;
            transform: translateY(-1px) scale(1.01) !important;
        }}
        .st-key-hud_community_nav div[data-testid="stButton"] button:hover::before {{
            filter: brightness(1.22) drop-shadow(0 0 10px rgba(16, 185, 129, 0.65)) !important;
        }}
        .st-key-hud_community_nav div[data-testid="stButton"] button:focus-visible {{
            outline: 2px solid rgba(16, 185, 129, 0.8) !important;
            outline-offset: 2px !important;
        }}
        </style>""",
        unsafe_allow_html=True,
    )
    with st.container(key="hud_community_nav"):
        st.button(
            "Explore Community Prj",
            key=key,
            width="stretch",
            type="secondary",
            help="Explore verified community loudspeaker alignments and fork designs.",
            on_click=_open_community_workspace,
        )

@st.dialog("🚀 Plans & Simulation Credits", width="large")
def _open_billing_modal(acc: _saas.UserAccount, shortfall: int = 0) -> None:
    """Render a clean, modern modal dialog for subscription plans and credit packs."""
    stripe_ready = _billing.is_stripe_configured()

    # Top Balance & Status Banner
    bal_col1, bal_col2 = st.columns([3, 2], vertical_alignment="center")
    with bal_col1:
        st.markdown(f"#### 💳 Balance: **{acc.credits_balance:,}** credits · *{acc.plan.upper()} PLAN*")
        st.caption("Unlimited cloud projects · 9,800+ Driver Catalog · Community Library")
    with bal_col2:
        if shortfall > 0:
            st.warning(f"⚠️ Current scan requires **{shortfall:,} additional credits**.")

    tab_sub, tab_packs = st.tabs(["🚀 Subscriptions", "⚡ One-Time Credit Packs"])

    with tab_sub:
        st.caption("Subscribe for recurring monthly credits, priority computing, and community perks. Cancel anytime.")

        # Billing cycle selector
        interval_choice = st.segmented_control(
            "Billing cycle",
            options=["Monthly", "Yearly (Save up to 27%)"],
            default="Monthly",
            label_visibility="collapsed",
            key="modal_sub_interval_choice",
        )
        is_yearly = "Yearly" in (interval_choice or "Monthly")
        chosen_int = "yearly" if is_yearly else "monthly"

        col_h, col_p = st.columns(2)

        # HOBBY CARD
        with col_h:
            with st.container(border=True):
                st.markdown("### 🟢 Hobby")
                if is_yearly:
                    st.markdown("## **€ 29** <span style='font-size:1rem;font-weight:normal;color:#aaa;'>/ year</span>", unsafe_allow_html=True)
                    st.caption("~€ 2.41 / month · Save 20% compared to monthly")
                else:
                    st.markdown("## **€ 3** <span style='font-size:1rem;font-weight:normal;color:#aaa;'>/ month</span>", unsafe_allow_html=True)
                    st.caption("Billed monthly · Cancel anytime")

                st.markdown(
                    "- **60,000 credits** / month\n"
                    "- **Unlimited cloud-saved projects**\n"
                    "- Full 9,800+ driver library access\n"
                    "- Community project sharing\n"
                    "- Technical export sheets & CSV"
                )

                if acc.plan == "hobby":
                    st.button("✓ Current Plan", disabled=True, width="stretch", key="modal_hobby_current")
                elif acc.plan in ("pro", "team"):
                    st.caption("Included in your higher tier")
                else:
                    if stripe_ready:
                        try:
                            checkout_url = _billing.create_checkout_session(
                                acc,
                                plan="hobby",
                                interval=chosen_int,
                                account_store=_runtime._ACCOUNT_STORE,
                            )
                            st.link_button(
                                f"Subscribe to Hobby ({'€29/yr' if is_yearly else '€3/mo'})",
                                checkout_url,
                                type="primary",
                                width="stretch",
                                key="modal_hobby_sub_btn",
                            )
                        except Exception as exc:
                            st.error(f"Stripe Error: {exc}")
                    else:
                        if st.button("Activate Hobby (Demo/Test)*", key="modal_hobby_demo_btn", type="primary", width="stretch"):
                            _runtime._ACCOUNT_STORE.update_billing_info(acc.email or acc.uid, plan="hobby")
                            _account._get_current_user_account.cache_clear()
                            _runtime._ACCOUNT_STORE.adjust_credits(acc.email or acc.uid, 60_000)
                            _account._get_current_user_account.cache_clear()
                            acc.plan = "hobby"
                            acc.credits_balance += 60_000
                            st.session_state.pop("_cached_user_account", None)
                            st.toast("🎉 Account upgraded to Hobby with 60,000 credits!", icon="🚀")
                            st.rerun()

        # PRO CARD
        with col_p:
            with st.container(border=True):
                st.markdown("### ⚡ Pro ⭐ *Most Popular*")
                if is_yearly:
                    st.markdown("## **€ 79** <span style='font-size:1rem;font-weight:normal;color:#aaa;'>/ year</span>", unsafe_allow_html=True)
                    st.caption("~€ 6.58 / month · Save 27% compared to monthly")
                else:
                    st.markdown("## **€ 9** <span style='font-size:1rem;font-weight:normal;color:#aaa;'>/ month</span>", unsafe_allow_html=True)
                    st.caption("Billed monthly · Cancel anytime")

                st.markdown(
                    "- **300,000 credits** / month\n"
                    "- **Unlimited cloud-saved projects**\n"
                    "- Priority cloud computing & sweep speed\n"
                    "- Full revision history & comparison\n"
                    "- Comprehensive printable spec sheets"
                )

                if acc.plan == "pro":
                    st.button("✓ Current Plan", disabled=True, width="stretch", key="modal_pro_current")
                else:
                    if stripe_ready:
                        try:
                            checkout_url = _billing.create_checkout_session(
                                acc,
                                plan="pro",
                                interval=chosen_int,
                                account_store=_runtime._ACCOUNT_STORE,
                            )
                            st.link_button(
                                f"Subscribe to Pro ({'€79/yr' if is_yearly else '€9/mo'})",
                                checkout_url,
                                type="primary",
                                width="stretch",
                                key="modal_pro_sub_btn",
                            )
                        except Exception as exc:
                            st.error(f"Stripe Error: {exc}")
                    else:
                        if st.button("Activate Pro (Demo/Test)*", key="modal_pro_demo_btn", type="primary", width="stretch"):
                            _runtime._ACCOUNT_STORE.update_billing_info(acc.email or acc.uid, plan="pro")
                            _account._get_current_user_account.cache_clear()
                            _runtime._ACCOUNT_STORE.adjust_credits(acc.email or acc.uid, 300_000)
                            _account._get_current_user_account.cache_clear()
                            acc.plan = "pro"
                            acc.credits_balance += 300_000
                            st.session_state.pop("_cached_user_account", None)
                            st.toast("🎉 Account upgraded to Pro with 300,000 credits!", icon="🚀")
                            st.rerun()

        # Manage subscription link for active subscribers
        if acc.stripe_customer_id and stripe_ready:
            st.divider()
            try:
                portal_url = _billing.create_customer_portal_session(acc, account_store=_runtime._ACCOUNT_STORE)
                st.link_button("⚙️ Manage Existing Subscription / Invoices (Stripe Portal)", portal_url, width="stretch")
            except Exception:
                pass

    with tab_packs:
        st.caption("Need a top-up without a subscription? One-time credit packs never expire.")
        pack_cols = st.columns(len(_billing.CREDIT_PACKS))
        for idx, (pack_key, pack_info) in enumerate(_billing.CREDIT_PACKS.items()):
            with pack_cols[idx]:
                with st.container(border=True):
                    badge_label = f" · {pack_info['badge']}" if pack_info.get("badge") else ""
                    st.markdown(f"### {pack_info['name']}{badge_label}")
                    price_str = f"€ {pack_info['price_eur']:.0f}"
                    st.markdown(f"## **{price_str}**")
                    st.caption(f"One-time payment · **{pack_info['credits']:,} credits**")
                    st.markdown(f"{pack_info['description']}")
                    is_rec = (shortfall > 0 and pack_info["credits"] >= shortfall)
                    if stripe_ready:
                        try:
                            checkout_url = _billing.create_credit_pack_checkout_session(
                                acc,
                                pack_key=pack_key,
                                account_store=_runtime._ACCOUNT_STORE,
                            )
                            st.link_button(
                                f"Buy Pack ({price_str})",
                                checkout_url,
                                type="primary" if is_rec else "secondary",
                                width="stretch",
                                key=f"modal_pack_btn_{pack_key}",
                            )
                        except Exception as exc:
                            st.error(f"Error: {exc}")
                    else:
                        if st.button(
                            f"Top up ({price_str})*",
                            key=f"modal_pack_demo_{pack_key}",
                            type="primary" if is_rec else "secondary",
                            width="stretch",
                        ):
                            _runtime._ACCOUNT_STORE.adjust_credits(acc.email or acc.uid, pack_info["credits"])
                            _account._get_current_user_account.cache_clear()
                            acc.credits_balance += pack_info["credits"]
                            st.session_state.pop("_cached_user_account", None)
                            st.toast(f"🎉 Successfully added {pack_info['credits']:,} credits!", icon="⚡")
                            st.rerun()

    st.markdown(
        "<div style='text-align:center; padding-top: 1rem; color: #888; font-size: 0.85rem;'>"
        "🔒 Secure checkout powered by <b>Stripe</b> · Supports <b>Cards</b>, <b>PayPal</b>, <b>Klarna</b>, <b>Satispay</b> & <b>Amazon Pay</b>"
        "</div>",
        unsafe_allow_html=True,
    )

def _render_credits_purchase_popover(
    acc: _saas.UserAccount,
    *,
    key: str = "credits_purchase_popover",
    label: str = "🚀 Subscriptions & Credits",
    shortfall: int = 0,
    width: str = "stretch",
) -> None:
    """Render an action button that opens the modern full-screen billing modal."""
    btn_type = "primary" if shortfall > 0 else "secondary"
    if st.button(label, key=f"{key}_open_modal_btn", width=width, type=btn_type):
        _open_billing_modal(acc, shortfall=shortfall)

def _render_billing_action_button(acc: _saas.UserAccount) -> None:
    """Render upgrade to Pro or buy credits button in the sidebar."""
    _render_credits_purchase_popover(
        acc,
        key="sidebar_billing_action_popover",
        label="🚀 Subscriptions & Credits",
        width="stretch",
    )

def _render_main_account_header() -> None:
    """Expose account, project and community actions on the main screen.

    Keeping these controls out of the sidebar lets every sidebar command stay
    visible without scrolling.
    """
    if _runtime._CURRENT_SAAS_USER is not None:
        acc = _account._get_current_user_account()
        account_col, billing_col, signout_col = st.columns(
            [4.4, 2.0, 0.6], vertical_alignment="center"
        )
        with account_col:
            if acc:
                st.caption(
                    f"**{html.escape(_runtime._CURRENT_SAAS_USER.name or _runtime._CURRENT_SAAS_USER.email or 'Engineer')}**"
                    f" · *{acc.plan.upper()}* · **{acc.credits_balance:,}** credits"
                )
            elif _runtime._CURRENT_SAAS_USER.email:
                st.caption(html.escape(_runtime._CURRENT_SAAS_USER.email))
        with billing_col:
            if acc:
                _render_billing_action_button(acc)
        with signout_col:
            st.button(
                "⏻",
                key="sidebar_sign_out_btn",
                help="Sign out / Logout",
                on_click=_account._sign_out_saas,
            )
    project_name = _project_display_name(st.session_state.get("project_name", ""))
    project_col, manage_col, community_col = st.columns(
        [4.4, 1.5, 1.5], vertical_alignment="center"
    )
    with project_col:
        if _project_name_is_placeholder(project_name):
            st.markdown(
                "**Project name required** · name this project in Manage Projects "
                "to enable cloud save."
            )
        else:
            st.markdown(f"**Project**: {html.escape(project_name)}")
        _render_cloud_persistence_status()
    with manage_col:
        st.button(
            "Manage Projects",
            key="sidebar_manage_projects_btn",
            width="stretch",
            on_click=_open_manage_projects_workspace,
        )
    with community_col:
        _render_hud_explore_community_button(key="sidebar_community_btn")

def _render_project_menu() -> None:
    """Compatibility hook: the project header now lives on the main screen."""

def _render_manage_projects_cloud_list() -> None:
    """Render the cloud projects table and management cards."""
    if not (_runtime._SAAS_SETTINGS.enabled and _runtime._CURRENT_SAAS_USER is not None):
        st.info("Operating in local session mode. Projects are stored in browser memory.")
        return
    try:
        summaries = _cloud_project_summaries()
    except Exception as exc:
        _runtime.logger.exception("Could not list cloud projects")
        st.error(f"Could not list cloud projects: {exc}")
        return
    active = [
        item for item in summaries
        if item.status != "trashed" and not _project_name_is_placeholder(item.name)
    ]
    if not active:
        st.info("No saved cloud projects found. Click **New Project** or import an existing `.lfp` file.")
        return
    current_id = str(st.session_state.get("_cloud_project_id", ""))
    st.caption(f"Showing **{len(active)}** cloud projects in your account")

    for item in active:
        is_current = item.project_id == current_id
        with st.container(border=True):
            r_col1, r_col2, r_col3, r_col4 = st.columns([3.5, 2.2, 1.3, 3.0], vertical_alignment="center")
            with r_col1:
                badge = "**[ACTIVE]** " if is_current else ""
                st.markdown(f"{badge}**{html.escape(item.name)}**")
                st.caption(f"ID: `{item.project_id[:12]}...` · Revision **r{item.revision}**")
            with r_col2:
                updated_str = item.updated_at.strftime("%d %b %Y %H:%M UTC")
                st.caption(updated_str)
            with r_col3:
                st.caption("Active" if is_current else "Saved")
            with r_col4:
                b_col1, b_col2, b_col3 = st.columns([1.2, 1.2, 1.1])
                with b_col1:
                    if st.button("Open", key=f"mp_list_open_{item.project_id}", width="stretch", type="primary" if is_current else "secondary"):
                        try:
                            record = _account._get_project_store().load_project(_runtime._CURRENT_SAAS_USER, item.project_id)
                            if record is None:
                                raise _saas.ProjectMissingError("Project not found")
                            _apply_cloud_record(record)
                            st.toast(f"Opened project: {record.name}")
                            st.rerun()
                        except Exception as exc:
                            _runtime.logger.exception("Could not open project")
                            st.error(f"Open failed: {exc}")
                with b_col2:
                    if st.button("Duplicate", key=f"mp_list_dup_{item.project_id}", width="stretch"):
                        try:
                            rec = _account._get_project_store().load_project(_runtime._CURRENT_SAAS_USER, item.project_id)
                            if rec:
                                copy_rec = _account._get_project_store().save_project(
                                    _runtime._CURRENT_SAAS_USER,
                                    f"{rec.name} (Copy)",
                                    rec.parameters,
                                    _runtime._VERSION,
                                    expected_revision=0,
                                )
                                _invalidate_cloud_project_list()
                                st.toast(f"Duplicated: {copy_rec.name}")
                                st.rerun()
                        except Exception as exc:
                            _runtime.logger.exception("Could not duplicate project")
                            st.error(f"Duplicate failed: {exc}")
                with b_col3:
                    if st.button("Trash", key=f"mp_list_trash_{item.project_id}", width="stretch"):
                        try:
                            _account._get_project_store().soft_delete_project(
                                _runtime._CURRENT_SAAS_USER,
                                item.project_id,
                                _runtime._VERSION,
                                expected_revision=item.revision,
                            )
                            if is_current:
                                _detach_cloud_project(suppress_hash=item.content_hash)
                            _invalidate_cloud_project_list()
                            st.toast(f"Moved to Trash: {item.name}")
                            st.rerun()
                        except Exception as exc:
                            _runtime.logger.exception("Could not trash project")
                            st.error(f"Trash failed: {exc}")

def _render_manage_projects_history() -> None:
    """Render revision history for the active project."""
    if not (_runtime._SAAS_SETTINGS.enabled and _runtime._CURRENT_SAAS_USER is not None):
        st.info("Revision history requires an authenticated cloud session.")
        return
    project_id = st.session_state.get("_cloud_project_id")
    revision = int(st.session_state.get("_cloud_project_revision", 0) or 0)
    if not project_id:
        st.info("Select or save a cloud project to view its revision timeline.")
        return
    try:
        revisions = _account._get_project_store().list_revisions(_runtime._CURRENT_SAAS_USER, str(project_id), limit=20)
    except Exception as exc:
        _runtime.logger.exception("Could not list revisions")
        st.error(f"Could not load revision history: {exc}")
        return
    if not revisions:
        st.info("No previous revisions recorded yet for this project.")
        return
    st.caption(f"Showing last **{len(revisions)}** immutable revisions for this project")
    for rev in revisions:
        is_current_rev = rev.revision == revision
        with st.container(border=True):
            c_info, c_action = st.columns([3, 1], vertical_alignment="center")
            with c_info:
                prefix = "**Current Revision** · " if is_current_rev else ""
                st.markdown(f"{prefix}**Revision r{rev.revision}**")
                st.caption(f"Saved at {rev.created_at:%d %b %Y %H:%M:%S UTC} · Schema v{rev.schema_version}")
            with c_action:
                if not is_current_rev:
                    if st.button("Restore Version", key=f"mp_restore_rev_{rev.revision_id}", width="stretch"):
                        try:
                            restored = _account._get_project_store().restore_revision(
                                _runtime._CURRENT_SAAS_USER,
                                str(project_id),
                                rev.revision,
                                _runtime._VERSION,
                                expected_revision=revision,
                            )
                            _apply_cloud_record(restored)
                            _invalidate_cloud_project_list()
                            st.toast(f"Restored revision r{rev.revision}")
                            st.rerun()
                        except Exception as exc:
                            _runtime.logger.exception("Could not restore revision")
                            st.error(f"Restore failed: {exc}")

def _render_manage_projects_trash() -> None:
    """Render trashed projects with restore actions."""
    if not (_runtime._SAAS_SETTINGS.enabled and _runtime._CURRENT_SAAS_USER is not None):
        st.info("Trash management requires an authenticated cloud session.")
        return
    try:
        summaries = _cloud_project_summaries()
    except Exception as exc:
        _runtime.logger.exception("Could not list trashed projects")
        st.error(f"Could not list trashed projects: {exc}")
        return
    trashed = [item for item in summaries if item.status == "trashed"]
    if not trashed:
        st.info("Trash is empty. All projects are active.")
        return
    st.caption(
        f"**{len(trashed)}** trashed project(s). "
        f"Trash retention target: {_runtime._SAAS_SETTINGS.project_trash_retention_days} days."
    )
    for item in trashed:
        with st.container(border=True):
            c_info, c_action = st.columns([3, 1], vertical_alignment="center")
            with c_info:
                st.markdown(f"**{html.escape(item.name)}**")
                del_str = item.deleted_at.strftime("%d %b %Y %H:%M UTC") if item.deleted_at else "recently"
                st.caption(f"Deleted on {del_str} · Revision r{item.revision}")
            with c_action:
                if st.button("Restore from Trash", key=f"mp_trash_restore_{item.project_id}", width="stretch", type="primary"):
                    try:
                        _account._get_project_store().restore_project(
                            _runtime._CURRENT_SAAS_USER,
                            item.project_id,
                            _runtime._VERSION,
                            expected_revision=item.revision,
                        )
                        _invalidate_cloud_project_list()
                        st.toast(f"Restored project: {item.name}")
                        st.rerun()
                    except Exception as exc:
                        _runtime.logger.exception("Could not restore project")
                        st.error(f"Restore failed: {exc}")

def _render_manage_projects_publish() -> None:
    """Render public snapshot publishing controls."""
    project_id = st.session_state.get("_cloud_project_id")
    project_name = str(st.session_state.get("project_name", _constants._UNTITLED_PROJECT_NAME))
    if not (_runtime._SAAS_SETTINGS.enabled and _runtime._CURRENT_SAAS_USER is not None and project_id):
        st.info("Save or open a cloud project first before publishing an immutable technical snapshot.")
        return
    st.caption("Publish an immutable technical snapshot of the current active design to the community library.")
    pub_title_input = st.text_input(
        "Publication title",
        value=project_name,
        key="mp_pub_title_input",
        max_chars=120,
    )
    pub_desc_input = st.text_area(
        "Publication description / build notes",
        value=st.session_state.get("_pub_desc_draft", ""),
        key="mp_pub_desc_input",
        help="Summary of the design, tuning goals, or physical prototype build requirements.",
    )
    pub_vis_option = st.selectbox(
        "Visibility",
        ["Unlisted (accessible via direct link)", "Public (discoverable in Explore/Projects)"],
        key="mp_pub_vis_select",
    )
    pub_photo_upload = st.file_uploader(
        "📷 Build Photo / Real Prototype (optional)",
        type=["jpg", "jpeg", "png", "webp"],
        key="mp_pub_photo_upload",
        help="Upload a real photo or 3D render of your enclosure build to feature on the community card.",
    )
    if st.button("Publish Technical Snapshot", key="mp_pub_submit_btn", width="stretch", type="primary"):
        try:
            vis = "public" if pub_vis_option.startswith("Public") else "unlisted"
            curr_prj = _account._get_project_store().load_project(_runtime._CURRENT_SAAS_USER, str(project_id))
            if curr_prj is None:
                raise ValueError("Project not found in private workspace")
            
            project_params = dict(curr_prj.parameters)
            if pub_photo_upload is not None:
                cover_data_uri = _process_project_cover_image(pub_photo_upload)
                if cover_data_uri:
                    if "parameters" in project_params and isinstance(project_params["parameters"], dict):
                        project_params["parameters"] = dict(project_params["parameters"])
                        project_params["parameters"]["cover_image"] = cover_data_uri
                    project_params["cover_image"] = cover_data_uri

            pub_record = _account._get_public_store().publish_project(
                _runtime._CURRENT_SAAS_USER,
                str(project_id),
                project_params,
                title=pub_title_input,
                description=pub_desc_input,
                visibility=vis,
                app_version=_runtime._VERSION,
                source_revision=curr_prj.revision,
            )
            st.session_state["_last_published_id"] = pub_record.publication_id
            st.toast(f"Published snapshot: {pub_record.title}")
            st.rerun()
        except Exception as exc:
            _runtime.logger.exception("Could not publish project snapshot")
            st.error(f"Publishing failed: {exc}")

    last_pub_id = st.session_state.get("_last_published_id")
    if last_pub_id:
        st.success(f"Snapshot published (`{last_pub_id}`)")
        st.button(
            "View Published Technical Page",
            key="view_published_tech_btn",
            type="secondary",
            on_click=_open_technical_page,
            args=(str(last_pub_id),),
        )

def _render_manage_projects_workspace() -> None:
    """Dedicated first-class workspace for project lifecycle, persistence, and storage management."""
    c_back, c_title, c_logout = st.columns([1.5, 7.0, 1.5], vertical_alignment="center")
    with c_back:
        if st.button("← Back to app", key="mp_back_to_app_btn"):
            _state._select_workspace("Bass Match")
            st.rerun()
    with c_title:
        st.title("Manage Projects")
    with c_logout:
        if _runtime._CURRENT_SAAS_USER is not None:
            st.button("Sign out", key="mp_sign_out_header_btn", on_click=_account._sign_out_saas, help="Sign out / Logout")
    st.caption(
        "Centralized project lifecycle, cloud autosave, revision history, "
        ".lfp file imports/exports, and publication management."
    )

    project_name = str(st.session_state.get("project_name", "")).strip()
    project_label = _project_display_name(project_name)
    cloud_id = st.session_state.get("_cloud_project_id")
    revision = int(st.session_state.get("_cloud_project_revision", 0) or 0)
    user = _runtime._CURRENT_SAAS_USER

    if st.session_state.get("_new_project_name_prompt"):
        with st.container(border=True):
            st.subheader("Name new project")
            new_project_name = st.text_input(
                "Project name",
                value="",
                key="mp_new_project_name",
                max_chars=80,
            )
            name_col, cancel_col = st.columns(2)
            with name_col:
                if st.button(
                    "Create Project",
                    key="mp_create_project_btn",
                    type="primary",
                    width="stretch",
                ):
                    if not new_project_name.strip():
                        st.error("Enter a project name to continue.")
                    else:
                        _create_new_project(new_project_name)
                        st.rerun()
            with cancel_col:
                if st.button("Cancel", key="mp_cancel_new_project_btn", width="stretch"):
                    st.session_state.pop("_new_project_name_prompt", None)
                    st.rerun()

    # 1. Top Quick Action Toolbar
    tb_col1, tb_col2, tb_col3, tb_col4 = st.columns([1.6, 2.0, 1.0, 1.4])
    with tb_col1:
        st.button(
            "New Project",
            key="mp_new_project_btn",
            type="primary",
            width="stretch",
            on_click=_request_new_project_name,
            help="Create a clean independent project with a required name",
        )
    with tb_col2:
        with st.popover("Import .lfp / .crw", width="stretch"):
            import_mode = st.radio("Import behavior", ["Import as New Project", "Replace Active Project"], key="mp_import_mode")
            upload_revision = int(st.session_state.get("_project_upload_revision", 0))
            upload = st.file_uploader(
                "Select .lfp or .crw file",
                type=["lfp", "json", "crw"],
                key=f"mp_file_uploader_{upload_revision}",
            )
            if upload is not None:
                try:
                    if upload.name.casefold().endswith(".crw"):
                        crw = _afw_compare.parse_crw_text(upload.getvalue().decode("latin-1"))
                        _state._snapshot_design_state()
                        driver = _acoustics.DriverTS(
                            fs_hz=crw.fs_hz, vas_l=crw.vas_l, qts=crw.qts,
                            qms=crw.qms, re_ohm=crw.re_ohm, sd_cm2=crw.sd_cm2,
                            le_mh=crw.le_10khz_mh, xmax_mm=crw.xmax_mm, pe_w=crw.pe_w,
                        )
                        _catalog._apply_driver_preset(driver)
                        st.session_state["driver_preset_name"] = "Custom driver"
                        st.session_state["_project_upload_revision"] = upload_revision + 1
                        st.toast(f"Loaded CRW driver: {crw.name}")
                        st.rerun()
                    payload = json.loads(upload.getvalue().decode("utf-8"))
                    _state._snapshot_design_state()
                    count = _apply_lfp_project(payload)
                    loaded_name = upload.name
                    if isinstance(payload.get("project"), dict) and payload["project"].get("name"):
                        loaded_name = str(payload["project"]["name"]).strip()
                    elif upload.name:
                        loaded_name = Path(upload.name).stem
                    st.session_state["project_name"] = loaded_name
                    st.session_state["_project_upload_revision"] = upload_revision + 1
                    if import_mode == "Import as New Project":
                        _detach_cloud_project()
                        _mark_cloud_project_dirty(immediate=True)
                    else:
                        _mark_cloud_project_dirty(immediate=True)
                    st.toast(f"Imported project: {loaded_name} ({count} parameters)")
                    st.rerun()
                except Exception as exc:
                    _runtime.logger.exception("Could not import file")
                    st.error(f"Import failed: {exc}")
    with tb_col3:
        if st.button("Refresh", key="mp_refresh_btn", help="Refresh cloud projects list", width="stretch"):
            _invalidate_cloud_project_list()
            st.rerun()
    with tb_col4:
        if st.session_state.get("_design_state_backup"):
            if st.button("Restore Design", key="mp_restore_prev_design_btn", width="stretch", help="Undo last preset switch"):
                _state._restore_design_state()
                st.toast("Previous design restored")
                st.rerun()

    # 2. Active Project Spotlight (Hero Box)
    with st.container(border=True):
        st.markdown(f"### Active Project: {html.escape(project_label)}")
        _render_cloud_persistence_status()

        # Summary row of parameters
        load_type = st.session_state.get("load_type", "Bass reflex")
        driver_name = st.session_state.get("driver_preset_name", "Custom")
        vol_l = float(st.session_state.get("reflex_vb_l", st.session_state.get("dccav_vb1_l", 50.0)))

        m_c1, m_c2, m_c3, m_c4 = st.columns(4)
        with m_c1:
            st.metric("Topology", load_type)
        with m_c2:
            st.metric("Driver", driver_name[:20] if driver_name else "Custom")
        with m_c3:
            st.metric("Enclosure Vb", f"{vol_l:.1f} L")
        with m_c4:
            st.metric("Cloud State", f"r{revision}" if cloud_id else "Local Draft")

        # Primary Workflow Actions
        act_col1, act_col2, act_col3, act_col4 = st.columns(4)
        with act_col1:
            st.button(
                "Open in Box Design",
                key="mp_open_bd_btn",
                type="primary",
                width="stretch",
                on_click=_state._select_workspace,
                args=("Box Design",),
            )
        with act_col2:
            st.button(
                "Open in Bass Match",
                key="mp_open_bm_btn",
                width="stretch",
                on_click=_state._select_workspace,
                args=("Bass Match",),
            )
        with act_col3:
            payload = _build_lfp_project({"name": project_name}, include_results=True)
            lfp_data = json.dumps(payload, indent=2, allow_nan=False).encode("utf-8")
            st.download_button(
                "Export .lfp Backup",
                lfp_data,
                _project_download_filename(project_name),
                "application/json",
                width="stretch",
                key="mp_download_lfp_btn",
                on_click=_record_lfp_export,
                disabled=_project_name_is_placeholder(project_name),
                help="Name the project before exporting an .lfp backup.",
            )
        with act_col4:
            if st.button(
                "Duplicate Project",
                key="mp_duplicate_btn",
                width="stretch",
                disabled=_project_name_is_placeholder(project_name),
                help="Name the project before duplicating it.",
            ):
                _duplicate_active_project()
                st.rerun()

        # In-place Rename & Share accordion
        with st.expander("Project Details, Rename & Sharing Link", expanded=False):
            rn_col1, rn_col2 = st.columns([3, 1])
            with rn_col1:
                new_name = st.text_input("Project Name", value=project_name, key="mp_rename_input", max_chars=80)
            with rn_col2:
                st.write("")
                st.write("")
                if st.button("Rename", key="mp_rename_submit_btn", width="stretch"):
                    if new_name.strip() and new_name.strip() != project_name:
                        st.session_state["project_name"] = new_name.strip()
                        _mark_cloud_project_dirty(immediate=True)
                        st.toast(f"Renamed project to: {new_name.strip()}")
                        st.rerun()

            st.divider()
            sh_col1, sh_col2 = st.columns([3, 1])
            with sh_col1:
                token = _encode_share_payload()
                share_url = _share_link_url(token)
                st.text_input("Shareable Design URL", value=share_url, disabled=True, key="mp_share_url_disp")
            with sh_col2:
                st.write("")
                st.write("")
                if st.button("Copy URL Link", key="mp_copy_url_btn", width="stretch"):
                    st.query_params["d"] = token
                    st.toast("URL token added to browser query params")

    # 3. Project Management Tabs
    tab_list, tab_history, tab_trash, tab_publish, tab_account = st.tabs([
        "Cloud Projects",
        "Revision History",
        "Trash",
        "Publish Snapshot",
        "Account & Entitlements",
    ], key="manage_projects_tab", on_change="rerun")

    if tab_list.open:
        with tab_list:
            _render_manage_projects_cloud_list()

    if tab_history.open:
        with tab_history:
            _render_manage_projects_history()

    if tab_trash.open:
        with tab_trash:
            _render_manage_projects_trash()

    if tab_publish.open:
        with tab_publish:
            _render_manage_projects_publish()

    if tab_account.open:
        with tab_account:
            if user is not None:
                _render_authenticated_account_controls(user)
            else:
                st.info("Operating in standalone offline mode. Sign in to enable multi-device cloud persistence.")

def _parse_query_param_str(key: str) -> str:
    val = st.query_params.get(key, "")
    if isinstance(val, (list, tuple)):
        val = val[0] if val else ""
    return str(val).strip(" '\"[]()")

def _fork_project_to_sandbox(pub_id: str, pub_title: str) -> None:
    """Load a public project into the active Box Design sandbox with 1 click."""
    pub = _account._get_public_store().get_public_project(pub_id)
    if pub is not None and pub.parameters:
        _state._snapshot_design_state()
        _apply_lfp_project(pub.parameters)
        for key in ("explore", "p", "embed"):
            st.query_params.pop(key, None)
        st.session_state["workspace_mode"] = "Box Design"
        _detach_cloud_project()
        st.toast(f"🚀 Loaded '{pub_title}' into Box Design Sandbox!")
        st.rerun()
    else:
        st.error(f"Could not load project parameters for {pub_title}")

def _toggle_community_project_like(pub_id: str, pub_title: str, default_likes: int = 10) -> None:
    """Toggle a like for a community project with session persistence and feedback."""
    user_likes = st.session_state.setdefault("community_user_likes", set())
    likes_counts = st.session_state.setdefault("community_likes_counts", {})
    if pub_id not in likes_counts:
        likes_counts[pub_id] = default_likes

    if pub_id in user_likes:
        user_likes.remove(pub_id)
        likes_counts[pub_id] = max(0, likes_counts[pub_id] - 1)
        st.toast(f"Unliked '{pub_title}'")
    else:
        user_likes.add(pub_id)
        likes_counts[pub_id] = likes_counts[pub_id] + 1
        st.toast(f"❤️ Liked '{pub_title}'!")

def _render_community_sidebar() -> None:
    """Render a clean Community sidebar with back navigation and publish CTA."""
    if st.button("← Back to Studio Workbench", key="sidebar_comm_back_btn", type="primary", width="stretch"):
        st.query_params.pop("explore", None)
        st.query_params.pop("p", None)
        st.session_state["workspace_mode"] = "Box Design"
        st.rerun()

    st.markdown(
        """<div style="background: rgba(16,185,129,0.06); border: 1px solid rgba(16,185,129,0.25); border-radius: 8px; padding: 7px 10px; margin: 10px 0; display: flex; align-items: center; gap: 8px;">
            <span style="display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: #10b981; box-shadow: 0 0 6px rgba(16,185,129,0.6);"></span>
            <span style="color: #10b981; font-size: 0.74rem; font-weight: 600; letter-spacing: 0.4px;">COMMUNITY NETWORK ONLINE</span>
        </div>""",
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # Publish Current Design CTA
    with st.expander("🚀 Publish Active Project", expanded=False):
        st.caption("Share your active design with the Load Forge community:")
        active_proj_name = st.session_state.get("project_name", "") or "My Acoustic Project"
        pub_title_input = st.text_input("Title", value=active_proj_name, key="comm_side_pub_title")
        pub_desc_input = st.text_area("Notes", placeholder="E.g. Tuned for touring sub...", key="comm_side_pub_desc", height=70)
        pub_vis = st.selectbox("Visibility", ["public", "unlisted"], key="comm_side_pub_vis")
        pub_photo_side = st.file_uploader(
            "📷 Build Photo (optional)",
            type=["jpg", "jpeg", "png", "webp"],
            key="comm_side_pub_photo",
            help="Upload a photo or 3D render of your real build.",
        )
        if st.button("Publish Design", key="comm_side_pub_btn", type="primary", width="stretch"):
            if _runtime._CURRENT_SAAS_USER is None:
                st.warning("Please sign in to publish projects.")
            else:
                try:
                    payload = _build_lfp_project({"name": pub_title_input or active_proj_name}, include_results=True)
                    if pub_photo_side is not None:
                        cover_data_uri = _process_project_cover_image(pub_photo_side)
                        if cover_data_uri:
                            if "parameters" in payload and isinstance(payload["parameters"], dict):
                                payload["parameters"]["cover_image"] = cover_data_uri
                            payload["cover_image"] = cover_data_uri
                    pub_rec = _account._get_public_store().publish_project(
                        _runtime._CURRENT_SAAS_USER,
                        st.session_state.get("_cloud_project_id") or _saas.new_project_id(),
                        payload,
                        title=pub_title_input or active_proj_name,
                        description=pub_desc_input,
                        visibility=pub_vis,
                        app_version=_runtime._VERSION,
                    )
                    st.toast(f"Published '{pub_rec.title}' to Community!")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Publish failed: {exc}")

def _render_public_project_sidebar(pub_id: str) -> None:
    """Render sidebar when inspecting a public project."""
    st.markdown(
        """<div style="background: rgba(0,255,102,0.08); border: 1px solid rgba(0,255,102,0.3); border-radius: 8px; padding: 8px 12px; margin-bottom: 12px; display: flex; align-items: center; gap: 8px;">
            <span style="display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #00ff66; box-shadow: 0 0 8px #00ff66;"></span>
            <span style="color: #00ff66; font-size: 0.82rem; font-weight: 700; letter-spacing: 0.5px;">PROJECT TECH VIEW</span>
        </div>""",
        unsafe_allow_html=True,
    )
    if st.button("← Back to Community Feed", key="pub_side_comm_btn", width="stretch", type="secondary"):
        st.query_params.pop("p", None)
        st.query_params["explore"] = "1"
        st.session_state["workspace_mode"] = "Community"
        st.rerun()

    if st.button("← Back to Studio Workbench", key="pub_side_studio_btn", width="stretch", type="primary"):
        st.query_params.pop("p", None)
        st.query_params.pop("explore", None)
        st.session_state["workspace_mode"] = "Box Design"
        st.rerun()

def _render_user_management() -> None:
    """Admin-only dashboard to view users, credit balances, change plans and adjust credits."""
    c_back, c_title = st.columns([1.5, 8.5], vertical_alignment="center")
    with c_back:
        if st.button("← Back to app", key="user_mgmt_back_btn"):
            _state._select_workspace("Bass Match")
            st.rerun()
    with c_title:
        st.markdown("### User & Credits Management")
    st.caption("Administrator console · Real-time Firestore users & credit balances")

    accounts = _runtime._ACCOUNT_STORE.list_all_accounts()
    if not accounts:
        st.info("No registered users found yet.")
        return

    # Aggregate metrics
    total_users = len(accounts)
    total_credits_allocated = sum(a.credits_monthly_quota for a in accounts)
    total_credits_remaining = sum(a.credits_balance for a in accounts)
    total_simulations = sum(a.total_simulations_run for a in accounts)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total users", f"{total_users:,}")
    m2.metric("Allocated credits", f"{total_credits_allocated:,}")
    m3.metric("Available balance", f"{total_credits_remaining:,}")
    m4.metric("Simulations executed", f"{total_simulations:,}")

    st.divider()

    # User table and actions
    for acc in accounts:
        with st.container(border=True):
            col_info, col_plan, col_credits, col_action = st.columns([3, 2, 2, 2], vertical_alignment="center")
            with col_info:
                admin_badge = " *(Admin)*" if acc.is_admin else ""
                st.markdown(f"**{acc.name or 'User'}** ({acc.email}){admin_badge}")
                st.caption(
                    f"Refill: {acc.quota_reset_at.strftime('%d %b %Y')} · Total sims: {acc.total_simulations_run:,}"
                )
            with col_plan:
                new_plan = st.selectbox(
                    "Plan",
                    ["free", "pro", "team"],
                    index=["free", "pro", "team"].index(acc.plan) if acc.plan in ["free", "pro", "team"] else 0,
                    key=f"plan_sel_{acc.email or acc.uid}",
                    label_visibility="collapsed",
                )
                if new_plan != acc.plan:
                    if st.button("Apply plan", key=f"btn_plan_{acc.email or acc.uid}"):
                        _runtime._ACCOUNT_STORE.update_plan(acc.email or acc.uid, new_plan)
                        _account._get_current_user_account.cache_clear()
                        st.success(f"Plan updated to {new_plan}")
                        st.rerun()
            with col_credits:
                st.markdown(f"**{acc.credits_balance:,}** / {acc.credits_monthly_quota:,}")
                delta = st.number_input(
                    "Add/Sub credits",
                    value=0,
                    step=100,
                    key=f"delta_{acc.email or acc.uid}",
                    label_visibility="collapsed",
                )
            with col_action:
                if delta != 0:
                    if st.button("Update credits", key=f"btn_cr_{acc.email or acc.uid}"):
                        _runtime._ACCOUNT_STORE.adjust_credits(acc.email or acc.uid, delta)
                        _account._get_current_user_account.cache_clear()
                        st.success(f"Adjusted by {delta:+d} credits")
                        st.rerun()

def _render_embed_project_widget(publication_id: str) -> None:
    """Render an ultra-clean, minimal responsive widget for iframe embedding."""
    try:
        pub = _account._get_public_store().get_public_project(publication_id)
    except Exception:
        _runtime.logger.exception("Could not retrieve public project for embed")
        pub = None

    if pub is None:
        st.markdown(
            f"<div style='padding:20px; font-family:sans-serif; color:#94a3b8; text-align:center;'>"
            f"<h4>Load Forge Simulation</h4>"
            f"<p>Project snapshot <code>{html.escape(publication_id)}</code> was not found or is unavailable.</p>"
            f"</div>",
            unsafe_allow_html=True,
        )
        return

    tech = pub.technical_summary or _saas.extract_technical_summary(pub.parameters)
    driver_name = tech.get("driver_name", "Custom driver")
    load_type = tech.get("load_type", "Bass reflex")
    vol = tech.get("box_volume_l")
    tune = tech.get("tuning_freq_hz")
    full_url = _public_project_url(publication_id)

    # Clean embed styling: hide sidebar, header, footer, reduce padding
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] { display: none !important; }
        header[data-testid="stHeader"] { display: none !important; }
        footer { display: none !important; }
        .block-container { padding: 0.8rem 1rem !important; max-width: 100% !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Top Header
    h_col1, h_col2 = st.columns([7, 3])
    with h_col1:
        st.markdown(
            f"<div style='display:flex; align-items:center; gap:8px;'>"
            f"<span style='font-size:1.1rem; font-weight:700; color:#f8fafc;'>{html.escape(pub.title)}</span>"
            f"<span style='font-size:0.75rem; background:rgba(16,185,129,0.15); color:#10b981; padding:2px 6px; border-radius:4px; border:1px solid rgba(16,185,129,0.3); font-weight:600;'>Verified</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
        author = pub.owner_display_name or "Load Forge Engineer"
        st.caption(f"{html.escape(driver_name)} · {html.escape(load_type)} · by {html.escape(author)}")
    with h_col2:
        st.markdown(
            f"<div style='text-align:right; margin-top:4px;'>"
            f"<a href='{html.escape(full_url)}' target='_blank' style='display:inline-block; padding:5px 10px; font-size:0.8rem; font-weight:600; background:#2563eb; color:#ffffff; text-decoration:none; border-radius:6px;'>Open in Load Forge</a>"
            f"</div>",
            unsafe_allow_html=True,
        )

    # Run simulation for preview curve
    try:
        params = (
            pub.parameters.get("parameters", {})
            if isinstance(pub.parameters.get("parameters"), dict)
            else pub.parameters
        )
        driver_ts = _state._driver_from_params(params)
        box_model = _state._box_from_params(params, load_type)
        f_min = float(params.get("sim_f_min", 10.0) or 10.0)
        f_max = float(params.get("sim_f_max", 300.0) or 300.0)
        freq = np.geomspace(f_min, f_max, 160)
        voltage = float(params.get("sim_voltage", 2.83) or 2.83)
        rg = float(params.get("sim_rg_ohm", 0.0) or 0.0)

        if load_type == "Bass reflex" and isinstance(box_model, _acoustics.PassiveRadiatorBox):
            result = _acoustics.simulate_passive_radiator(driver_ts, box_model, freq, voltage, rg)
        elif load_type == "Bass reflex":
            result = _acoustics.simulate_reflex(driver_ts, box_model, freq, voltage, rg)
        elif load_type == "Sealed":
            result = _acoustics.simulate_sealed(driver_ts, box_model, freq, voltage, rg)
        elif load_type == "DCCAV":
            result = _acoustics.simulate(driver_ts, box_model, freq, voltage, rg)
        elif load_type == "Bandpass 4th order":
            result = _acoustics.simulate_bandpass4(driver_ts, box_model, freq, voltage, rg)
        elif load_type == "Bandpass 6th order":
            result = _acoustics.simulate_bandpass6(driver_ts, box_model, freq, voltage, rg)
        elif load_type == "Bandpass 8th order":
            result = _acoustics.simulate_bandpass8(driver_ts, box_model, freq, voltage, rg)
        elif load_type == "Infinite baffle":
            result = _acoustics.simulate_infinite_baffle(driver_ts, freq, voltage, rg)
        else:
            result = _acoustics.simulate(driver_ts, box_model, freq, voltage, rg)

        metrics = _acoustics.response_metrics(result)
        f3_val = metrics.get("f3_hz", 0.0)

        # Chips row
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Topology", load_type)
        with c2:
            st.metric("Box Vol (Vb)", f"{vol:.1f} L" if vol is not None else "—")
        with c3:
            st.metric("Tuning (Fb)", f"{tune:.1f} Hz" if tune is not None else "—")
        with c4:
            st.metric("F3 Cutoff", f"{f3_val:.1f} Hz" if f3_val > 0 else "—")

        spl_df = pd.DataFrame({
            "frequency_hz": result.frequency_hz,
            "value": result.spl_total_db,
            "series": "Total SPL",
        })
        spl_chart = _analysis._line_chart(
            spl_df,
            "SPL (dB)",
            height=200,
            legend=False,
            x_domain=[f_min, f_max],
        )
        st.altair_chart(spl_chart, width="stretch")
    except Exception as exc:
        _runtime.logger.exception("Could not render embed simulation curve")
        st.caption(f"Preview unavailable: {exc}")

def _render_public_project_page(publication_id: str) -> None:
    """Render the public technical project page for a published snapshot."""
    try:
        pub = _account._get_public_store().get_public_project(publication_id)
    except Exception:
        _runtime.logger.exception("Could not retrieve public project")
        pub = None

    if pub is None:
        st.error("Project snapshot not found or direct link is invalid.")
        st.caption(f"Publication ID: `{html.escape(publication_id)}`")
        if st.button("Return to Load Forge", key="pub_not_found_back_btn"):
            st.query_params.pop("p", None)
            st.rerun()
        return

    # Ingest JSON-LD structured data and OpenGraph tags into HTML head
    try:
        json_ld = _saas.generate_json_ld_schema(pub)
        st.markdown(
            f'<script type="application/ld+json">{json.dumps(json_ld)}</script>',
            unsafe_allow_html=True,
        )
    except Exception:
        pass

    # Top header bar
    back_col1, back_col2, badge_col = st.columns([3.5, 3.5, 3.0])
    with back_col1:
        if st.button("← Back to Community Feed", key="pub_back_comm_btn", width="stretch"):
            st.query_params.pop("p", None)
            st.query_params["explore"] = "1"
            st.session_state["workspace_mode"] = "Community"
            st.rerun()
    with back_col2:
        if st.button("← Back to Studio Workbench", key="pub_back_studio_btn", width="stretch"):
            st.query_params.pop("p", None)
            st.query_params.pop("explore", None)
            st.session_state["workspace_mode"] = "Box Design"
            st.rerun()
    with badge_col:
        vis_label = "Public" if pub.visibility == "public" else "Unlisted"
        st.markdown(
            f"<div style='text-align:right; font-weight:600; color:#94a3b8; font-size:0.9rem; margin-top:0.3rem;'>"
            f"{vis_label} · v{pub.publication_version}"
            f"</div>",
            unsafe_allow_html=True,
        )

    # Title & Verified Badge
    st.title(pub.title)
    badge_text = f"Verified Simulation · Load Forge Solver v{pub.app_version}"
    st.markdown(
        f"<div style='display:inline-flex; align-items:center; gap:6px; background:rgba(16,185,129,0.12); color:#10b981; font-weight:600; font-size:0.85rem; padding:4px 10px; border-radius:6px; border:1px solid rgba(16,185,129,0.25); margin-bottom:0.75rem;'>"
        f"<span>✓</span> {badge_text}"
        f"</div>",
        unsafe_allow_html=True,
    )

    author = pub.owner_display_name or "Load Forge Engineer"
    pub_date = (
        pub.published_at.strftime("%d %b %Y %H:%M UTC")
        if hasattr(pub.published_at, "strftime")
        else str(pub.published_at)
    )
    if pub.description:
        st.info(pub.description)

    pub_cover_img = (pub.technical_summary or {}).get("cover_image") or (pub.parameters or {}).get("cover_image")
    if pub_cover_img:
        st.markdown(
            f"""<div style="border-radius: 10px; overflow: hidden; margin-bottom: 1.2rem; border: 1px solid rgba(255,255,255,0.1); max-height: 420px; display: flex; align-items: center; justify-content: center; background: #0b0f19;">
                <img src="{pub_cover_img}" style="width: 100%; max-height: 400px; object-fit: contain; border-radius: 8px;" alt="Real Build Photo" />
            </div>""",
            unsafe_allow_html=True,
        )

    # Action buttons
    action_col1, action_col2, action_col3, action_col4 = st.columns([3, 3, 2, 2])
    with action_col1:
        if st.button(
            "Open in Load Forge (Preview)",
            key="pub_open_in_lf_btn",
            width="stretch",
            help="Loads this technical design into your active session as a sandbox preview.",
        ):
            _state._snapshot_design_state()
            _apply_lfp_project(pub.parameters)
            st.query_params.pop("p", None)
            st.session_state["workspace_mode"] = "Box Design"
            _detach_cloud_project()
            st.toast("Opened project in active workspace (sandbox preview)")
            st.rerun()

    with action_col2:
        if _runtime._CURRENT_SAAS_USER is not None:
            if st.button(
                "Clone to My Projects",
                key="pub_clone_btn",
                width="stretch",
                type="primary",
                help="Creates an independent copy of this design in your private cloud account with full provenance.",
            ):
                try:
                    cloned_record = _account._get_public_store().clone_public_project(
                        _runtime._CURRENT_SAAS_USER,
                        pub.publication_id,
                        _runtime._VERSION,
                        private_store=_account._get_project_store(),
                    )
                    _queue_cloud_record_activation(
                        cloned_record,
                        notice=f"Cloned design as: {cloned_record.name}",
                    )
                    st.query_params.pop("p", None)
                    st.rerun()
                except Exception as exc:
                    _runtime.logger.exception("Could not clone public project")
                    st.error(f"Clone failed: {exc}")
        else:
            st.button(
                "Clone to My Projects (Sign In Required)",
                key="pub_clone_disabled_btn",
                width="stretch",
                disabled=True,
                help="Sign in to save this design into your private cloud account.",
            )

    with action_col3:
        lfp_data = json.dumps(pub.parameters, indent=2, allow_nan=False).encode("utf-8")
        st.download_button(
            "Download .lfp",
            lfp_data,
            _project_download_filename(pub.title),
            "application/json",
            width="stretch",
            key="pub_download_lfp_btn",
            help="Download the complete portable engineering file to your computer.",
        )

    with action_col4:
        spec_sheet_md = _saas.generate_printable_spec_sheet_markdown(pub)
        st.download_button(
            "Export Spec Sheet (.md)",
            spec_sheet_md.encode("utf-8"),
            f"{_project_download_filename(pub.title).removesuffix('.lfp')}_spec_sheet.md",
            "text/markdown",
            width="stretch",
            key="pub_download_spec_btn",
            help="Download printable engineering specification sheet in Markdown.",
        )

    st.divider()

    # Technical Specifications Overview
    st.subheader("Technical Specifications & Alignment")
    tech = pub.technical_summary or _saas.extract_technical_summary(pub.parameters)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Topology / Load", tech.get("load_type", "Bass reflex"))
    with c2:
        vol = tech.get("box_volume_l")
        st.metric("Enclosure Volume (Vb)", f"{vol:.1f} L" if vol is not None else "—")
    with c3:
        tuning = tech.get("tuning_freq_hz")
        st.metric("Tuning Freq (Fb)", f"{tuning:.1f} Hz" if tuning is not None else "—")
    with c4:
        driver_name = tech.get("driver_name", "Custom driver")
        st.metric("Transducer", driver_name)

    # Simulation Curves & Performance Estimation
    st.subheader("Predicted Electroacoustic Performance")
    try:
        params = (
            pub.parameters.get("parameters", {})
            if isinstance(pub.parameters.get("parameters"), dict)
            else pub.parameters
        )
        load_type = str(tech.get("load_type", params.get("load_type", "Bass reflex")))
        driver_ts = _state._driver_from_params(params)
        box_model = _state._box_from_params(params, load_type)

        f_min = float(params.get("sim_f_min", 10.0) or 10.0)
        f_max = float(params.get("sim_f_max", 300.0) or 300.0)
        points = int(params.get("sim_points", 240) or 240)
        voltage = float(params.get("sim_voltage", 2.83) or 2.83)
        rg = float(params.get("sim_rg_ohm", 0.0) or 0.0)

        freq = np.geomspace(f_min, f_max, points)
        if load_type == "Bass reflex" and isinstance(box_model, _acoustics.PassiveRadiatorBox):
            result = _acoustics.simulate_passive_radiator(driver_ts, box_model, freq, voltage, rg)
        elif load_type == "Bass reflex":
            result = _acoustics.simulate_reflex(driver_ts, box_model, freq, voltage, rg)
        elif load_type == "Sealed":
            result = _acoustics.simulate_sealed(driver_ts, box_model, freq, voltage, rg)
        elif load_type == "DCCAV":
            result = _acoustics.simulate(driver_ts, box_model, freq, voltage, rg)
        elif load_type == "Bandpass 4th order":
            result = _acoustics.simulate_bandpass4(driver_ts, box_model, freq, voltage, rg)
        elif load_type == "Bandpass 6th order":
            result = _acoustics.simulate_bandpass6(driver_ts, box_model, freq, voltage, rg)
        elif load_type == "Bandpass 8th order":
            result = _acoustics.simulate_bandpass8(driver_ts, box_model, freq, voltage, rg)
        elif load_type == "Infinite baffle":
            result = _acoustics.simulate_infinite_baffle(driver_ts, freq, voltage, rg)
        else:
            result = _acoustics.simulate(driver_ts, box_model, freq, voltage, rg)

        metrics = _acoustics.response_metrics(result)
        f3_val = metrics.get("f3_hz", 0.0)
        f6_val = metrics.get("f6_hz", 0.0)
        f10_val = metrics.get("f10_hz", 0.0)
        peak_spl = float(np.max(result.spl_total_db)) if len(result.spl_total_db) else 0.0
        z_min = float(np.min(result.impedance_ohm)) if len(result.impedance_ohm) else 0.0
        z_min_idx = int(np.argmin(result.impedance_ohm)) if len(result.impedance_ohm) else 0
        z_min_f = float(result.frequency_hz[z_min_idx]) if len(result.frequency_hz) else 0.0
        gd = _acoustics.group_delay_ms(result)
        peak_gd = float(np.max(gd)) if len(gd) else 0.0

        # Detailed metrics row
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        with m1:
            st.metric("F3 (-3 dB)", f"{f3_val:.1f} Hz" if f3_val > 0 else "—")
        with m2:
            st.metric("F6 (-6 dB)", f"{f6_val:.1f} Hz" if f6_val > 0 else "—")
        with m3:
            st.metric("F10 (-10 dB)", f"{f10_val:.1f} Hz" if f10_val > 0 else "—")
        with m4:
            st.metric("Peak SPL @ 2.83V", f"{peak_spl:.1f} dB")
        with m5:
            st.metric("Zmin", f"{z_min:.2f} Ω", f"@{z_min_f:.0f}Hz")
        with m6:
            st.metric("Peak Group Delay", f"{peak_gd:.1f} ms")

        # 6 Performance & Validation Tabs
        tab_spl, tab_exc, tab_imp, tab_ports, tab_gd, tab_meas = st.tabs([
            "SPL Frequency Response",
            "Cone Excursion",
            "Impedance & Phase",
            "Port Air Velocity",
            "Group Delay",
            "Measurement Validation",
        ])
        with tab_spl:
            spl_df = pd.DataFrame({
                "frequency_hz": result.frequency_hz,
                "value": result.spl_total_db,
                "series": "Total SPL (2.83V)",
            })
            spl_chart = _analysis._line_chart(
                spl_df,
                "Sound Pressure Level (dB)",
                height=380,
                legend=False,
                x_domain=[f_min, f_max],
            )
            st.altair_chart(spl_chart, width="stretch")

        with tab_exc:
            xmax_mm = float(params.get("driver_xmax_mm", 0.0) or 0.0)
            exc_chart = _analysis._plot_excursion(result, xmax_mm)
            st.altair_chart(exc_chart, width="stretch")

        with tab_imp:
            imp_chart = _analysis._plot_impedance(result)
            st.altair_chart(imp_chart, width="stretch")

        with tab_ports:
            if load_type in {"Bass reflex", "DCCAV", "Bandpass 4th order", "Bandpass 6th order", "Bandpass 8th order"}:
                try:
                    port_chart = _analysis._plot_ports(result, mode="air_velocity_sim")
                    st.altair_chart(port_chart, width="stretch")
                except Exception:
                    st.info("Port air velocity curves are not applicable or port diameter is zero.")
            else:
                st.info(f"Port velocity curves are not applicable for {load_type} enclosures.")

        with tab_gd:
            gd_chart = _analysis._plot_group_delay(result)
            st.altair_chart(gd_chart, width="stretch")

        with tab_meas:
            st.markdown("#### Physical Prototype Measurement Validation")
            st.caption("Upload or inspect raw physical measurements (REW, DATS, ARTA, CLIO, Klippel, FRD, ZMA) overlaid directly on the lumped-parameter simulation.")

            meas_upload = st.file_uploader(
                "Upload Measurement File (.frd, .zma, .txt, .csv, .mdat, .dat)",
                type=["frd", "zma", "txt", "csv", "mdat", "dat"],
                key=f"meas_uploader_{pub.publication_id}",
                help="Supports REW SPL & Impedance exports, Dayton Audio DATS v2/v3, ARTA/LIMP, Audiomatica CLIO, and generic FRD/ZMA curves.",
            )

            stored_meas_list = params.get("measurements", [])
            active_curve = None

            if meas_upload is not None:
                try:
                    active_curve = _acoustics.parse_measurement_file(
                        meas_upload.getvalue(),
                        filename=meas_upload.name,
                        default_type="spl",
                    )
                except Exception as exc:
                    st.error(f"Failed to parse measurement file: {exc}")
            elif stored_meas_list and isinstance(stored_meas_list, list):
                try:
                    active_curve = _acoustics.deserialize_measurement(stored_meas_list[0])
                except Exception as exc:
                    _runtime.logger.warning("Could not load stored project measurement: %s", exc)

            if active_curve is not None:
                src_label = active_curve.metadata.get("source", active_curve.format_name.upper())
                st.success(
                    f"Loaded **{html.escape(active_curve.label)}** · Format: `{src_label}` · "
                    f"{len(active_curve.freq)} pts ({active_curve.freq[0]:.1f} Hz – {active_curve.freq[-1]:.1f} Hz)"
                )

                if active_curve.curve_type == "impedance":
                    comp = _acoustics.compare_simulation_to_measurement(
                        result.frequency_hz, result.impedance_ohm, active_curve
                    )
                    mc1, mc2, mc3, mc4 = st.columns(4)
                    with mc1:
                        st.metric("Impedance RMSE", f"{comp.rmse:.2f} Ω")
                    with mc2:
                        st.metric("Max |ΔZ|", f"{comp.max_abs_delta:.2f} Ω")
                    with mc3:
                        st.metric("Mean Offset", f"{comp.mean_delta:+.2f} Ω")
                    with mc4:
                        if comp.fb_delta_hz is not None:
                            st.metric("Tuning Error ΔFb", f"{comp.fb_delta_hz:+.1f} Hz", f"Sim: {comp.sim_fb_hz:.1f}Hz / Meas: {comp.meas_fb_hz:.1f}Hz")
                        else:
                            st.metric("Tuning Alignment", "Nominal")

                    overlay_rows = [
                        {"frequency_hz": float(f), "value": float(z), "series": "Simulated Impedance"}
                        for f, z in zip(result.frequency_hz, result.impedance_ohm, strict=False)
                    ] + [
                        {"frequency_hz": float(f), "value": float(z), "series": f"Measured ({active_curve.label})"}
                        for f, z in zip(active_curve.freq, active_curve.values, strict=False)
                        if f_min <= f <= f_max
                    ]
                    ov_chart = _analysis._line_chart(
                        pd.DataFrame(overlay_rows),
                        "Impedance (Ω)",
                        height=380,
                        legend=True,
                        x_domain=[f_min, f_max],
                    )
                    st.altair_chart(ov_chart, width="stretch")

                else:  # SPL comparison
                    comp = _acoustics.compare_simulation_to_measurement(
                        result.frequency_hz, result.spl_total_db, active_curve
                    )
                    mc1, mc2, mc3 = st.columns(3)
                    with mc1:
                        st.metric("SPL RMSE", f"{comp.rmse:.2f} dB")
                    with mc2:
                        st.metric("Max |ΔSPL|", f"{comp.max_abs_delta:.2f} dB")
                    with mc3:
                        st.metric("Mean SPL Offset", f"{comp.mean_delta:+.2f} dB")

                    overlay_rows = [
                        {"frequency_hz": float(f), "value": float(s), "series": "Simulated SPL (2.83V)"}
                        for f, s in zip(result.frequency_hz, result.spl_total_db, strict=False)
                    ] + [
                        {"frequency_hz": float(f), "value": float(s), "series": f"Measured ({active_curve.label})"}
                        for f, s in zip(active_curve.freq, active_curve.values, strict=False)
                        if f_min <= f <= f_max
                    ]
                    ov_chart = _analysis._line_chart(
                        pd.DataFrame(overlay_rows),
                        "Sound Pressure Level (dB)",
                        height=380,
                        legend=True,
                        x_domain=[f_min, f_max],
                    )
                    st.altair_chart(ov_chart, width="stretch")
            else:
                st.info("No physical measurements currently attached to this snapshot. Upload a measurement above to compare your real prototype against this simulation.")

    except Exception as exc:
        _runtime.logger.exception("Could not render public project response curves")
        st.warning(f"Simulation preview could not be computed: {exc}")

    # Driver Details Expander
    with st.expander("Driver Parameters & Transducer Electromechanics", expanded=False):
        dc1, dc2, dc3, dc4, dc5 = st.columns(5)
        with dc1:
            fs = tech.get("driver_fs_hz")
            st.metric("Fs", f"{fs:.1f} Hz" if fs is not None else "—")
        with dc2:
            vas = tech.get("driver_vas_l")
            st.metric("Vas", f"{vas:.1f} L" if vas is not None else "—")
        with dc3:
            qts = tech.get("driver_qts")
            st.metric("Qts", f"{qts:.3f}" if qts is not None else "—")
        with dc4:
            re_v = tech.get("driver_re_ohm")
            st.metric("Re", f"{re_v:.2f} Ω" if re_v is not None else "—")
        with dc5:
            sd_v = tech.get("driver_sd_cm2")
            st.metric("Sd", f"{sd_v:.1f} cm²" if sd_v is not None else "—")

    # Embed snippet expander
    with st.expander("Embed this project on forums & websites", expanded=False):
        embed_url = f"{_public_project_url(pub.publication_id)}&embed=1"
        iframe_snippet = f'<iframe src="{embed_url}" width="100%" height="420" frameborder="0"></iframe>'
        st.caption("Copy this responsive iframe embed code for DIYAudio, forums, build logs, and blogs:")
        st.code(iframe_snippet, language="html")

def _reset_explore_filters() -> None:
    """Reset Community controls in a widget-safe callback."""
    for key, value in _constants._EXPLORE_FILTER_DEFAULTS.items():
        st.session_state[key] = value
    st.session_state["explore_category_pill"] = "All"

def _explore_optional_limit(key: str) -> float | None:
    value = float(st.session_state.get(key, 0.0) or 0.0)
    return value if value > 0.0 else None

def _get_community_load_image(load_type: str) -> Path | None:
    """Return matching load diagram asset path for a community project card."""
    path = _constants._LOAD_TYPE_IMAGES.get(load_type)
    if path and path.exists():
        return path
    lt = (load_type or "").lower()
    if "dccav" in lt:
        return _constants._LOAD_TYPE_IMAGES.get("DCCAV")
    if "reflex" in lt or "pr" in lt or "passive" in lt:
        return _constants._LOAD_TYPE_IMAGES.get("Bass reflex")
    if "sealed" in lt:
        return _constants._LOAD_TYPE_IMAGES.get("Sealed")
    if "4th" in lt:
        return _constants._LOAD_TYPE_IMAGES.get("Bandpass 4th order")
    if "6th" in lt:
        return _constants._LOAD_TYPE_IMAGES.get("Bandpass 6th order")
    if "8th" in lt:
        return _constants._LOAD_TYPE_IMAGES.get("Bandpass 8th order")
    if "baffle" in lt:
        return _constants._LOAD_TYPE_IMAGES.get("Infinite baffle")
    return _constants._LOAD_TYPE_IMAGES.get("Bass reflex")

def _resolve_driver_ts(name: str, fs=None, vas=None, qts=None, qms=None, re_val=None, sd=None, pe=None, xmax=None, nominal_size_in=None) -> _acoustics.DriverTS:
    """Robustly resolve or synthesize a DriverTS from name, partial parameters or catalog lookup."""
    if fs and vas and qts:
        return _acoustics.DriverTS(
            fs_hz=float(fs),
            vas_l=float(vas),
            qts=float(qts),
            qms=float(qms or 5.0),
            re_ohm=float(re_val or 5.0),
            sd_cm2=float(sd or (float(nominal_size_in)**2 * 3.14159 * 2.54**2 / 4.0 if nominal_size_in else 500.0)),
            pe_w=float(pe or 100.0),
            xmax_mm=float(xmax or 5.0),
        )
    clean = str(name or "").strip()
    if clean:
        try:
            return _acoustics.get_driver_preset(clean)
        except Exception:
            pass
        no_paren = clean.split("(")[0].strip() if "(" in clean else clean
        try:
            return _acoustics.get_driver_preset(no_paren)
        except Exception:
            pass
        for prefix in ("WEB:", "LSDB:", "SBL:", "VCAD:", "MFG:", "ZTZAUDIO:"):
            if clean.upper().startswith(prefix):
                unprefixed = clean[len(prefix):].strip()
                no_p = unprefixed.split("(")[0].strip() if "(" in unprefixed else unprefixed
                try:
                    return _acoustics.get_driver_preset(no_p)
                except Exception:
                    pass
        all_p = _acoustics.driver_preset_names()
        norm = no_paren.lower().replace("18 sound", "eighteen sound").replace("18sound", "eighteen sound")
        for p in all_p:
            p_norm = p.lower().replace("18 sound", "eighteen sound").replace("18sound", "eighteen sound")
            if norm in p_norm or p_norm in norm:
                try:
                    return _acoustics.get_driver_preset(p)
                except Exception:
                    pass
        tokens = [t for t in re.split(r"[^A-Za-z0-9]", no_paren) if len(t) >= 4]
        for token in tokens:
            for p in all_p:
                if token.lower() in p.lower():
                    try:
                        return _acoustics.get_driver_preset(p)
                    except Exception:
                        pass
    sd_calc = 500.0
    if nominal_size_in:
        try:
            sd_calc = float(nominal_size_in)**2 * 3.14159 * 2.54**2 / 4.0
        except Exception:
            sd_calc = 500.0
    return _acoustics.DriverTS(
        fs_hz=35.0,
        vas_l=60.0,
        qts=0.35,
        qms=5.0,
        re_ohm=5.5,
        sd_cm2=sd_calc,
        pe_w=200.0,
        xmax_mm=6.0,
    )

@st.cache_data(show_spinner=False, max_entries=500)
def _derive_project_acoustic_metrics(params_items: tuple) -> tuple[float | None, float | None]:
    """Derive F3 extension and peak SPL / MOL for a project whose parameters lack explicit cached metrics."""
    params = dict(params_items)
    try:
        load_type = str(params.get("load_type", "Bass reflex"))
        driver_name = str(params.get("driver_name", params.get("driver_preset_name", ""))).strip()
        fs = params.get("driver_fs_hz")
        vas = params.get("driver_vas_l")
        qts = params.get("driver_qts")
        qms = params.get("driver_qms")
        re_val = params.get("driver_re_ohm")
        sd = params.get("driver_sd_cm2")
        pe = params.get("driver_pe_w")
        xmax = params.get("driver_xmax_mm")
        nominal_size_in = params.get("nominal_size_in")
        box_vol_l = params.get("box_volume_l", params.get("reflex_vb_l", params.get("sealed_vb_l")))
        tuning_hz = params.get("tuning_freq_hz", params.get("reflex_fb_hz", params.get("sealed_fc_hz")))

        d_ts = _resolve_driver_ts(
            driver_name,
            fs=fs,
            vas=vas,
            qts=qts,
            qms=qms,
            re_val=re_val,
            sd=sd,
            pe=pe,
            xmax=xmax,
            nominal_size_in=nominal_size_in,
        )

        freq = np.geomspace(20.0, 500.0, 120)
        res = None
        vol_val = float(box_vol_l or 0.0)
        if load_type == "Bass reflex":
            vb = vol_val if vol_val > 0 else (d_ts.vas_l * (d_ts.qts ** 2) * 15.0)
            fb = float(tuning_hz or d_ts.fs_hz)
            b_mod = _acoustics.ReflexBox(
                vb_l=vb,
                fb_hz=fb,
                ql=float(params.get("reflex_ql", 7.0) or 7.0),
            )
            res = _acoustics.simulate_reflex(d_ts, b_mod, freq)
        elif load_type == "Sealed":
            vb = vol_val if vol_val > 0 else d_ts.vas_l
            fc = float(tuning_hz or (d_ts.fs_hz * 1.3))
            b_mod = _acoustics.SealedBox(
                vb_l=vb,
                fc_hz=fc,
                qtc=float(params.get("sealed_qtc", 0.707) or 0.707),
            )
            res = _acoustics.simulate_sealed(d_ts, b_mod, freq)
        elif load_type == "DCCAV":
            if vol_val > 0:
                vh = float(params.get("box_vh_l", params.get("dccav_vb1_l", vol_val / 3.0)) or (vol_val / 3.0))
                vl = float(params.get("box_vl_l", params.get("dccav_vb2_l", 2.0 * vol_val / 3.0)) or (2.0 * vol_val / 3.0))
                fh = float(params.get("box_fh_hz", params.get("dccav_fb1_hz", tuning_hz or 60.0)) or 60.0)
                fl = float(params.get("box_fl_hz", params.get("dccav_fb2_hz", 30.0)) or 30.0)
                b_mod = _acoustics.DccavBox(vh_l=vh, vl_l=vl, fh_hz=fh, fl_hz=fl)
            else:
                sugg = _acoustics.suggest_alignment(d_ts)
                b_mod = _acoustics.DccavBox(vh_l=sugg.vh_l, vl_l=sugg.vl_l, fh_hz=sugg.fh_hz, fl_hz=sugg.fl_hz)
            res = _acoustics.simulate(d_ts, b_mod, freq)
        elif load_type == "Bandpass 4th order":
            vs = float(params.get("bandpass4_vs_l", params.get("bp4_vb_l", vol_val / 2.0 if vol_val else 20.0)) or 20.0)
            vp = float(params.get("bandpass4_vp_l", params.get("bp4_vf_l", vol_val / 2.0 if vol_val else 20.0)) or 20.0)
            fp = float(params.get("bandpass4_fp_hz", params.get("bp4_fb_hz", tuning_hz or 50.0)) or 50.0)
            b_mod = _acoustics.Bandpass4Box(vs_l=vs, vp_l=vp, fp_hz=fp)
            res = _acoustics.simulate_bandpass4(d_ts, b_mod, freq)
        elif load_type == "Bandpass 6th order":
            vr = float(params.get("bandpass6_vr_l", params.get("bp6_vr_l", vol_val / 2.0 if vol_val else 20.0)) or 20.0)
            vp = float(params.get("bandpass6_vp_l", params.get("bp6_vf_l", vol_val / 2.0 if vol_val else 20.0)) or 20.0)
            fp = float(params.get("bandpass6_fp_hz", params.get("bp6_fb_f_hz", tuning_hz or 60.0)) or 60.0)
            fr = float(params.get("bandpass6_fr_hz", params.get("bp6_fb_r_hz", 30.0)) or 30.0)
            b_mod = _acoustics.Bandpass6Box(vr_l=vr, vp_l=vp, fp_hz=fp, fr_hz=fr)
            res = _acoustics.simulate_bandpass6(d_ts, b_mod, freq)
        elif load_type == "Bandpass 8th order":
            v1 = float(params.get("bp8_v1_l", vol_val / 3.0 if vol_val else 20.0) or 20.0)
            v2 = float(params.get("bp8_v2_l", vol_val / 3.0 if vol_val else 20.0) or 20.0)
            v3 = float(params.get("bp8_v3_l", vol_val / 3.0 if vol_val else 20.0) or 20.0)
            f1 = float(params.get("bp8_f1_hz", 70.0) or 70.0)
            f2 = float(params.get("bp8_f2_hz", 45.0) or 45.0)
            f3_p = float(params.get("bp8_f3_hz", 30.0) or 30.0)
            b_mod = _acoustics.Bandpass8Box(v1_l=v1, v2_l=v2, v3_l=v3, f1_hz=f1, f2_hz=f2, f3_hz=f3_p)
            res = _acoustics.simulate_bandpass8(d_ts, b_mod, freq)
        elif load_type == "Infinite baffle":
            res = _acoustics.simulate_infinite_baffle(d_ts, freq)

        if res is not None:
            mets = _acoustics.response_metrics(res)
            f3_val = mets.get("f3_hz")
            spl_val = None
            if hasattr(res, "mol_db") and len(res.mol_db) and np.nanmax(res.mol_db) > 0:
                spl_val = float(np.nanmax(res.mol_db))
            elif hasattr(res, "spl_total_db") and len(res.spl_total_db):
                spl_val = float(np.nanmax(res.spl_total_db))
            return f3_val, spl_val
    except Exception:
        pass
    return None, None

def _render_explore_projects_directory() -> None:
    """Render the clean, visual public project discovery and community engineering hub."""
    st.markdown(
        """<style>
        .community-header {
            padding: 0.4rem 0 0.6rem 0;
            margin-bottom: 0.8rem;
            border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        }
        .community-title {
            font-size: 1.45rem;
            font-weight: 700;
            color: #10b981;
            letter-spacing: 0.5px;
            margin-bottom: 0.15rem;
        }
        .community-sub {
            color: #9ca3af;
            font-size: 0.84rem;
            margin-bottom: 0.4rem;
        }
        .community-telemetry {
            display: flex;
            flex-wrap: wrap;
            gap: 14px;
            font-size: 0.74rem;
            color: #8b949e;
        }
        .community-telemetry strong {
            color: #10b981;
            font-weight: 600;
        }
        .community-badge {
            background: rgba(16, 185, 129, 0.10);
            color: #10b981;
            border: 1px solid rgba(16, 185, 129, 0.28);
            padding: 2px 6px;
            border-radius: 6px;
            font-size: 0.66rem;
            font-weight: 600;
        }
        .community-topo-badge {
            background: rgba(16, 185, 129, 0.10);
            color: #10b981;
            border: 1px solid rgba(16, 185, 129, 0.30);
            padding: 2px 8px;
            border-radius: 6px;
            font-size: 0.70rem;
            font-weight: 600;
            letter-spacing: 0.3px;
            display: inline-block;
        }
        .community-avatar-ring {
            width: 22px;
            height: 22px;
            border-radius: 50%;
            background: rgba(16, 185, 129, 0.12);
            border: 1px solid rgba(16, 185, 129, 0.4);
            display: flex;
            align-items: center;
            justify-content: center;
            color: #10b981;
            font-weight: 700;
            font-size: 0.70rem;
        }
        .community-grid-specs {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 6px;
            margin: 8px 0 8px 0;
        }
        .spec-box {
            background: rgba(255, 255, 255, 0.025);
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 6px;
            padding: 5px 8px;
        }
        .spec-box-lbl {
            font-size: 0.60rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: #8b949e;
            margin-bottom: 2px;
        }
        .spec-box-val {
            font-size: 0.82rem;
            font-weight: 600;
            color: #e6edf3;
            font-family: monospace;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .spec-box-f3 { color: #38bdf8; font-weight: 700; }
        .spec-box-spl { color: #10b981; font-weight: 700; }
        </style>""",
        unsafe_allow_html=True,
    )

    # Clean Header Bar
    h_left, h_right = st.columns([7.5, 2.5], vertical_alignment="center")
    with h_left:
        st.markdown(
            """<div class="community-header">
                <div class="community-title">⚡ LOAD FORGE COMMUNITY // ELECTROACOUSTIC HUB</div>
                <div class="community-sub">Verified loudspeaker designs, acoustic simulations, and community alignments.</div>
                <div class="community-telemetry">
                    <span>🔨 <strong>128+</strong> Verified Builds</span>
                    <span>🔄 <strong>3.8k+</strong> Simulations & Clones</span>
                    <span>👥 <strong>86</strong> Audio Designers</span>
                </div>
            </div>""",
            unsafe_allow_html=True,
        )
    with h_right:
        if st.button("← Back to Workbench", key="explore_top_back_btn", type="secondary", width="stretch"):
            st.query_params.pop("explore", None)
            st.session_state["workspace_mode"] = "Box Design"
            st.rerun()

    for key, value in _constants._EXPLORE_FILTER_DEFAULTS.items():
        st.session_state.setdefault(key, value)

    # Search, topology and sorting bar
    f_col1, f_col2, f_col3, f_col4 = st.columns([4.2, 2.5, 2.5, 1.3])
    with f_col1:
        search_query = st.text_input(
            "Search",
            placeholder="Search builds, drivers (e.g. B&C, FaitalPRO, Purifi), authors...",
            key="explore_search_input",
            label_visibility="collapsed",
        )
    with f_col2:
        topologies = [
            "All",
            "Bass reflex",
            "DCCAV",
            "Sealed",
            "Passive radiator",
            "Bandpass 4th order",
            "Bandpass 6th order",
            "Bandpass 8th order",
            "Infinite baffle",
        ]
        selected_topo = st.selectbox(
            "Topology",
            topologies,
            key="explore_topo_filter",
            label_visibility="collapsed",
        )
    with f_col3:
        sort_options = {
            "trending": "🔥 Trending / Most Liked",
            "newest": "⚡ Newest First",
            "lowest_f3": "🎯 Deepest Extension (F3)",
            "compact_vb": "📦 Most Compact (Vb)",
            "highest_spl": "🔊 Highest Peak SPL",
        }
        selected_sort = st.selectbox(
            "Sort by",
            list(sort_options.keys()),
            format_func=lambda k: sort_options[k],
            key="explore_sort_filter",
            label_visibility="collapsed",
        )
    with f_col4:
        st.button(
            "Reset",
            key="explore_reset_btn",
            width="stretch",
            on_click=_reset_explore_filters,
        )

    with st.expander("🎛️ Fine Electroacoustic Range Filters", expanded=False):
        st.caption("Narrow the discovery catalog by physical and electroacoustic limits:")
        p1, p2, p3, p4 = st.columns(4)
        with p1:
            st.number_input("Vb min (L)", min_value=0.0, step=5.0, key="explore_min_vb_l")
        with p2:
            st.number_input("Vb max (L)", min_value=0.0, step=5.0, key="explore_max_vb_l")
        with p3:
            st.number_input("Fb min (Hz)", min_value=0.0, step=1.0, key="explore_min_fb_hz")
        with p4:
            st.number_input("Fb max (Hz)", min_value=0.0, step=1.0, key="explore_max_fb_hz")

        p5, p6, p7, p8 = st.columns(4)
        with p5:
            st.number_input("Driver min (in)", min_value=0.0, step=0.5, key="explore_min_size_in")
        with p6:
            st.number_input("Driver max (in)", min_value=0.0, step=0.5, key="explore_max_size_in")
        with p7:
            st.number_input("Fs min (Hz)", min_value=0.0, step=1.0, key="explore_min_fs_hz")
        with p8:
            st.number_input("Fs max (Hz)", min_value=0.0, step=1.0, key="explore_max_fs_hz")

        p9, p10, p11, p12 = st.columns(4)
        with p9:
            st.number_input("Qts min", min_value=0.0, step=0.01, format="%.2f", key="explore_min_qts")
        with p10:
            st.number_input("Qts max", min_value=0.0, step=0.01, format="%.2f", key="explore_max_qts")
        with p11:
            st.number_input("F3 min (Hz)", min_value=0.0, step=1.0, key="explore_min_f3_hz")
        with p12:
            st.number_input("F3 max (Hz)", min_value=0.0, step=1.0, key="explore_max_f3_hz")

    limits = {
        key: _explore_optional_limit(key)
        for key in _constants._EXPLORE_FILTER_DEFAULTS
        if key.startswith("explore_min_") or key.startswith("explore_max_")
    }
    invalid_ranges = [
        label
        for label, minimum_key, maximum_key in (
            ("Vb", "explore_min_vb_l", "explore_max_vb_l"),
            ("Fb", "explore_min_fb_hz", "explore_max_fb_hz"),
            ("driver diameter", "explore_min_size_in", "explore_max_size_in"),
            ("Fs", "explore_min_fs_hz", "explore_max_fs_hz"),
            ("Qts", "explore_min_qts", "explore_max_qts"),
            ("F3", "explore_min_f3_hz", "explore_max_f3_hz"),
        )
        if limits[minimum_key] is not None
        and limits[maximum_key] is not None
        and limits[minimum_key] > limits[maximum_key]
    ]
    if invalid_ranges:
        st.warning("Minimum exceeds maximum for: " + ", ".join(invalid_ranges) + ".")

    # Query public projects store
    store = _account._get_public_store()
    query_error = ""
    try:
        projects = [] if invalid_ranges else store.list_public_projects(
            query=search_query,
            topology=selected_topo if selected_topo != "All" else "",
            min_vb=limits["explore_min_vb_l"],
            max_vb=limits["explore_max_vb_l"],
            min_tuning_hz=limits["explore_min_fb_hz"],
            max_tuning_hz=limits["explore_max_fb_hz"],
            min_driver_size_in=limits["explore_min_size_in"],
            max_driver_size_in=limits["explore_max_size_in"],
            min_fs_hz=limits["explore_min_fs_hz"],
            max_fs_hz=limits["explore_max_fs_hz"],
            min_qts=limits["explore_min_qts"],
            max_qts=limits["explore_max_qts"],
            min_f3=limits["explore_min_f3_hz"],
            max_f3=limits["explore_max_f3_hz"],
            sort_by=selected_sort,
            limit=100,
        )
    except Exception as exc:
        _runtime.logger.exception("Failed to query public projects")
        projects = []
        query_error = str(exc)

    if query_error:
        st.error("Community projects could not be loaded from cloud. Showing verified local showcase:")
        projects = _saas.curated_community_showcase_projects()

    if not projects:
        st.info("No public projects match the active filters. Reset the filters or widen numeric bounds.")
        return

    # User like state map
    user_likes = st.session_state.setdefault("community_user_likes", set())
    likes_counts = st.session_state.setdefault("community_likes_counts", {})

    # Featured Project Spotlight Card with Compact Icon & Spec Grid
    if not search_query and selected_topo == "All" and projects:
        top_pub = projects[0]
        top_tech = top_pub.technical_summary or {}
        top_author = top_pub.owner_display_name or "Marco_Forge"
        top_rank = top_tech.get("creator_rank", "⚡ Lead Architect")
        top_likes = likes_counts.get(top_pub.publication_id, top_tech.get("likes", 142))
        top_vol = top_tech.get("box_volume_l")
        top_f3 = top_tech.get("f3_hz")
        top_spl = top_tech.get("peak_spl_db")
        top_driver = top_tech.get("driver_name", "Custom driver") or "Custom driver"
        top_load = top_tech.get("load_type", "Bass reflex") or "Bass reflex"
        top_size = top_tech.get("nominal_size_in")
        top_is_liked = top_pub.publication_id in user_likes
        top_f3_val = float(top_f3) if top_f3 is not None and float(top_f3 or 0) > 0 else None
        top_spl_val = float(top_spl) if top_spl is not None and float(top_spl or 0) > 0 else None

        if top_f3_val is None or top_spl_val is None:
            top_raw = getattr(top_pub, "parameters", {}) or {}
            inner_p = top_raw.get("parameters", {}) if isinstance(top_raw.get("parameters"), dict) else top_raw
            merged = {**inner_p, **top_tech}
            items = tuple(sorted((str(k), v) for k, v in merged.items() if isinstance(v, (str, int, float, bool))))
            f3_c, spl_c = _derive_project_acoustic_metrics(items)
            if top_f3_val is None and f3_c is not None:
                top_f3_val = f3_c
            if top_spl_val is None and spl_c is not None:
                top_spl_val = spl_c

        if top_f3_val is None or top_spl_val is None:
            try:
                full_top = store.get_public_project(top_pub.publication_id)
                if full_top is not None and full_top.parameters:
                    full_p = full_top.parameters.get("parameters", {}) if isinstance(full_top.parameters.get("parameters"), dict) else full_top.parameters
                    merged_full = {**full_p, **top_tech}
                    items_full = tuple(sorted((str(k), v) for k, v in merged_full.items() if isinstance(v, (str, int, float, bool))))
                    f3_f, spl_f = _derive_project_acoustic_metrics(items_full)
                    if top_f3_val is None and f3_f is not None:
                        top_f3_val = f3_f
                    if top_spl_val is None and spl_f is not None:
                        top_spl_val = spl_f
            except Exception:
                pass

        top_driver_str = str(top_driver)
        if isinstance(top_size, (int, float)) and top_size > 0:
            top_driver_str += f' ({top_size:.0f}")'
        top_vb_str = f"{top_vol:.1f} L" if top_vol is not None and top_vol > 0 else "—"
        top_f3_str = f"{top_f3_val:.1f} Hz" if top_f3_val is not None and top_f3_val > 0 else "—"
        top_mol_str = f"{top_spl_val:.1f} dB" if top_spl_val is not None and top_spl_val > 0 else "—"

        with st.container(border=True):
            top_cover = top_tech.get("cover_image")
            if top_cover:
                st.markdown(
                    f"""<div style="border-radius: 8px; overflow: hidden; margin-bottom: 10px; max-height: 200px; display: flex; align-items: center; justify-content: center; background: #0b0f19;">
                        <img src="{top_cover}" style="width: 100%; max-height: 190px; object-fit: cover; border-radius: 6px;" alt="Featured Build" />
                    </div>""",
                    unsafe_allow_html=True,
                )
            fh_img, fh_txt = st.columns([0.7, 5.3], vertical_alignment="center")
            with fh_img:
                top_img = _get_community_load_image(top_load)
                if top_img and top_img.exists():
                    st.image(str(top_img), width=54)
            with fh_txt:
                st.markdown(
                    f"""<div style="display: flex; align-items: center; gap: 8px; margin-bottom: 2px;">
                        <span class="community-badge">🏆 FEATURED ALIGNMENT</span>
                        <span class="community-topo-badge">{html.escape(top_load)}</span>
                        <span style="color: #8b949e; font-size: 0.74rem;">{top_pub.published_at.strftime('%d %b %Y')}</span>
                    </div>""",
                    unsafe_allow_html=True,
                )
                st.markdown(f"### {html.escape(top_pub.title)}")
                st.markdown(
                    f"""<div style="font-size: 0.78rem; color: #8b949e; margin-top: -4px;">
                        <strong>{html.escape(top_author)}</strong> <span class="community-badge" style="margin: 0 4px;">{top_rank}</span>
                    </div>""",
                    unsafe_allow_html=True,
                )

            st.markdown(
                f"""<div class="community-grid-specs">
                    <div class="spec-box"><div class="spec-box-lbl">DRIVER</div><div class="spec-box-val" title="{html.escape(top_driver_str)}">{html.escape(top_driver_str)}</div></div>
                    <div class="spec-box"><div class="spec-box-lbl">VOLUME (Vb)</div><div class="spec-box-val">{top_vb_str}</div></div>
                    <div class="spec-box"><div class="spec-box-lbl">F3 EXTENSION</div><div class="spec-box-val spec-box-f3">{top_f3_str}</div></div>
                    <div class="spec-box"><div class="spec-box-lbl">MOL / PEAK SPL</div><div class="spec-box-val spec-box-spl">{top_mol_str}</div></div>
                </div>""",
                unsafe_allow_html=True,
            )

            fb1, fb2, fb3 = st.columns([2.4, 2.0, 1.2], vertical_alignment="center")
            with fb1:
                if st.button("🚀 Fork to Sandbox", key=f"feat_fork_btn_{top_pub.publication_id}", width="stretch", type="primary"):
                    _fork_project_to_sandbox(top_pub.publication_id, top_pub.title)
            with fb2:
                st.button(
                    "📊 Tech Sheet",
                    key=f"feat_tech_btn_{top_pub.publication_id}",
                    width="stretch",
                    type="secondary",
                    on_click=_open_technical_page,
                    args=(top_pub.publication_id,),
                )
            with fb3:
                f_like_label = f"❤️ {top_likes}" if not top_is_liked else f"💖 {top_likes}"
                if st.button(f_like_label, key=f"feat_like_{top_pub.publication_id}", width="stretch"):
                    _toggle_community_project_like(top_pub.publication_id, top_pub.title, top_likes)
                    st.rerun()

    st.markdown("<div style='margin-top: 8px;'></div>", unsafe_allow_html=True)
    st.markdown(f"### 📡 Community Builds ({len(projects)})")

    # Render Visual 3-Column Grid with Small Load Icon + Basic Project Value Grid
    cols = st.columns(3)
    for idx, pub in enumerate(projects):
        col = cols[idx % 3]
        tech = pub.technical_summary or {}
        load_type = tech.get("load_type", "Bass reflex")
        if tech.get("resonator_type") == _constants._RESONATOR_PR:
            load_type = "Passive radiator"
        driver_name = tech.get("driver_name", "Custom driver")
        card_cover = tech.get("cover_image")
        f3 = tech.get("f3_hz")
        vol = tech.get("box_volume_l")
        spl = tech.get("peak_spl_db")
        size_in = tech.get("nominal_size_in")
        author_name = pub.owner_display_name or "Acoustic Engineer"
        pub_likes = likes_counts.get(pub.publication_id, tech.get("likes", 12 + (idx * 7) % 80))
        is_liked = pub.publication_id in user_likes

        f3_val = float(f3) if f3 is not None and float(f3 or 0) > 0 else None
        spl_val = float(spl) if spl is not None and float(spl or 0) > 0 else None

        if f3_val is None or spl_val is None:
            pub_raw = getattr(pub, "parameters", {}) or {}
            inner_p = pub_raw.get("parameters", {}) if isinstance(pub_raw.get("parameters"), dict) else pub_raw
            merged = {**inner_p, **tech}
            items = tuple(sorted((str(k), v) for k, v in merged.items() if isinstance(v, (str, int, float, bool))))
            f3_c, spl_c = _derive_project_acoustic_metrics(items)
            if f3_val is None and f3_c is not None:
                f3_val = f3_c
            if spl_val is None and spl_c is not None:
                spl_val = spl_c

        if f3_val is None or spl_val is None:
            try:
                full_pub = store.get_public_project(pub.publication_id)
                if full_pub is not None and full_pub.parameters:
                    full_p = full_pub.parameters.get("parameters", {}) if isinstance(full_pub.parameters.get("parameters"), dict) else full_pub.parameters
                    merged_full = {**full_p, **tech}
                    items_full = tuple(sorted((str(k), v) for k, v in merged_full.items() if isinstance(v, (str, int, float, bool))))
                    f3_f, spl_f = _derive_project_acoustic_metrics(items_full)
                    if f3_val is None and f3_f is not None:
                        f3_val = f3_f
                    if spl_val is None and spl_f is not None:
                        spl_val = spl_f
            except Exception:
                pass

        if not card_cover:
            card_cover = (pub_raw if 'pub_raw' in locals() and pub_raw else {}).get("cover_image")

        driver_str = str(driver_name)
        if isinstance(size_in, (int, float)) and size_in > 0:
            driver_str += f' ({size_in:.0f}")'
        vb_str = f"{vol:.1f} L" if vol is not None and vol > 0 else "—"
        f3_str = f"{f3_val:.1f} Hz" if f3_val is not None and f3_val > 0 else "—"
        mol_str = f"{spl_val:.1f} dB" if spl_val is not None and spl_val > 0 else "—"

        with col:
            with st.container(border=True):
                if card_cover:
                    st.markdown(
                        f"""<div style="border-radius: 6px; overflow: hidden; margin-bottom: 8px; max-height: 140px; display: flex; align-items: center; justify-content: center; background: #0b0f19;">
                            <img src="{card_cover}" style="width: 100%; height: 130px; object-fit: cover; border-radius: 4px;" alt="Build Photo" />
                        </div>""",
                        unsafe_allow_html=True,
                    )
                # Header with small load type icon and title
                h_img, h_txt = st.columns([0.7, 3.3], vertical_alignment="center")
                with h_img:
                    load_img = _get_community_load_image(load_type)
                    if load_img and load_img.exists():
                        st.image(str(load_img), width=46)
                with h_txt:
                    st.markdown(f"#### {html.escape(pub.title)}")
                    st.markdown(
                        f"""<div style="display: flex; align-items: center; gap: 6px; margin-top: -6px;">
                            <span class="community-topo-badge">{html.escape(load_type)}</span>
                            <span style="font-size: 0.68rem; color: #6e7681;">{pub.published_at.strftime('%d %b %Y')}</span>
                        </div>""",
                        unsafe_allow_html=True,
                    )

                # Basic Project Values Grid (Driver, Volume, F3, MOL)
                st.markdown(
                    f"""<div class="community-grid-specs">
                        <div class="spec-box"><div class="spec-box-lbl">DRIVER</div><div class="spec-box-val" title="{html.escape(driver_str)}">{html.escape(driver_str)}</div></div>
                        <div class="spec-box"><div class="spec-box-lbl">VOLUME (Vb)</div><div class="spec-box-val">{vb_str}</div></div>
                        <div class="spec-box"><div class="spec-box-lbl">F3 EXTENSION</div><div class="spec-box-val spec-box-f3">{f3_str}</div></div>
                        <div class="spec-box"><div class="spec-box-lbl">MOL / PEAK SPL</div><div class="spec-box-val spec-box-spl">{mol_str}</div></div>
                    </div>""",
                    unsafe_allow_html=True,
                )

                # Author line
                st.markdown(
                    f"""<div style="display: flex; align-items: center; gap: 6px; font-size: 0.74rem; color: #8b949e; margin-bottom: 8px;">
                        <div class="community-avatar-ring">{author_name[0].upper()}</div>
                        <span><strong>{html.escape(author_name)}</strong></span>
                    </div>""",
                    unsafe_allow_html=True,
                )

                # Action Row
                a_fork, a_tech, a_like = st.columns([2.0, 1.6, 1.2], vertical_alignment="center")
                with a_fork:
                    if st.button("🚀 Fork", key=f"btn_fork_{pub.publication_id}", width="stretch", type="primary", help=f"Load {pub.title} in Box Design Sandbox"):
                        _fork_project_to_sandbox(pub.publication_id, pub.title)
                with a_tech:
                    st.button(
                        "📊 Tech",
                        key=f"btn_tech_{pub.publication_id}",
                        width="stretch",
                        type="secondary",
                        on_click=_open_technical_page,
                        args=(pub.publication_id,),
                    )
                with a_like:
                    like_label = f"❤️ {pub_likes}" if not is_liked else f"💖 {pub_likes}"
                    if st.button(like_label, key=f"btn_like_{pub.publication_id}", width="stretch"):
                        _toggle_community_project_like(pub.publication_id, pub.title, pub_likes)
                        st.rerun()
