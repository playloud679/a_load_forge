"""Portal entry and sign-in return destinations. See docs/ui/navigation.md.

Only navigation data crosses the auth boundary; it never grants permissions.
Catalog links are validated before changing state and applied once per session.
"""
from __future__ import annotations

import json
import math
from urllib.parse import parse_qsl, quote, unquote, urlencode

import streamlit as st
import acoustics as _acoustics

from . import catalog as _catalog
from . import constants as _constants
from . import finder as _finder
from . import projects as _projects
from . import state as _state

DESTINATION_KEYS = ("view", "preset", "vb", "fb", "load", "p", "explore", "embed", "d")
_COOKIE = "lf_return_destination"


def _destination(values) -> dict[str, str]:
    return {key: str(values[key]) for key in DESTINATION_KEYS if values.get(key)}


def remember_auth_destination() -> None:
    """Keep the entry query across OIDC's new session/root redirect for 10 minutes."""
    encoded = quote(urlencode(_destination(st.query_params)), safe="")
    # Stay below browser cookie limits. No credentials, arbitrary URLs or scripts.
    if len(encoded) > 3000:
        return
    cookie = f"{_COOKIE}={encoded}; Path=/; SameSite=Lax; Max-Age={600 if encoded else 0}"
    st.html(
        '<script>document.cookie = ' + json.dumps(cookie)
        + ' + (location.protocol === "https:" ? "; Secure" : "");</script>',
        unsafe_allow_javascript=True,
    )


def restore_auth_destination() -> None:
    """Restore allowed query keys after authentication, without overriding a new link."""
    if st.session_state.get("_auth_destination_restored"):
        return
    st.session_state["_auth_destination_restored"] = True
    raw = st.context.cookies.get(_COOKIE, "")
    if not isinstance(raw, str) or not raw:
        return
    if len(raw) <= 3000 and not _destination(st.query_params):
        try:
            values = dict(parse_qsl(unquote(raw), max_num_fields=20))
        except ValueError:
            values = {}
        st.query_params.update(_destination(values))
    st.html(
        f'<script>document.cookie = "{_COOKIE}=; Path=/; SameSite=Lax; Max-Age=0";</script>',
        unsafe_allow_javascript=True,
    )


def apply_catalog_handoff(*, preserve_existing: bool = False) -> None:
    """Load an allowed catalog driver and optional sealed/reflex box into a new design."""
    name = str(st.query_params.get("preset", ""))
    if not name or st.query_params.get("d") or st.query_params.get("p"):
        return
    signature = tuple(str(st.query_params.get(key, "")) for key in ("preset", "load", "vb", "fb"))
    if st.session_state.get("_applied_catalog_handoff") == signature:
        return
    try:
        if name not in _catalog._available_driver_preset_names():
            raise ValueError("This driver is not available in the Studio catalog. Select a driver from the library.")
        load = str(st.query_params.get("load", "reflex"))
        if load not in {"sealed", "reflex"}:
            raise ValueError("This link uses an unsupported enclosure type.")
        params = {}
        for key, state_key, minimum, maximum in (
            ("vb", "sealed_vb_l" if load == "sealed" else "reflex_vb_l", 0.05, 100000.0 if load == "sealed" else 1000.0),
            ("fb", "reflex_fb_hz", 1.0, 1000.0),
        ):
            if key not in st.query_params:
                continue
            try:
                value = float(st.query_params[key])
            except (ValueError, TypeError):
                raise ValueError(f"Invalid {key} in the driver link.") from None
            if not math.isfinite(value) or not minimum <= value <= maximum:
                raise ValueError(f"The link's {key} must be between {minimum:g} and {maximum:g}.")
            if key == "fb" and load == "sealed":
                raise ValueError("A sealed enclosure does not have a port tuning frequency.")
            params[state_key] = value
        driver = _acoustics.get_driver_preset(name)
    except ValueError as exc:
        st.warning(str(exc))
        return
    if preserve_existing and not _projects._save_before_project_switch():
        st.error(st.session_state["_project_switch_error"])
        return
    _state._snapshot_design_state()
    _projects._detach_cloud_project()
    st.session_state["project_name"] = _constants._UNTITLED_PROJECT_NAME
    # An external design must not overwrite a saved comparison variant on rerun.
    for key in ("design_comparison_tabs", "design_comparison_active_id", "design_comparison_loaded_id", "_pending_driver_preset_name"):
        st.session_state.pop(key, None)
    _catalog._apply_driver_preset(driver)
    st.session_state["driver_preset_name"] = name
    st.session_state["driver_config"] = "Single driver"
    st.session_state["load_type"] = "Sealed" if load == "sealed" else "Bass reflex"
    st.session_state["reflex_resonator_type"] = _constants._RESONATOR_PORT
    st.session_state["preset_search"] = ""
    _state._set_box_strategy_state("Max extension")
    _finder._sync_auto_alignment_if_needed()
    if params:
        _state._set_box_strategy_state("Manual")
        st.session_state.update(params)
    _finder._mark_auto_alignment_synced()
    st.session_state["workspace_mode"] = "Box Design"
    st.session_state["_session_project_resumed"] = True
    st.session_state["_applied_catalog_handoff"] = signature
    _projects._mark_cloud_project_dirty()
