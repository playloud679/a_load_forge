"""Streamlit session-state helpers, widget defaults and box/driver models built from state."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json

import numpy as np
import pandas as pd
import streamlit as st

import acoustics as _acoustics

from . import constants as _constants
from . import finder as _finder
from . import projects as _projects
from . import styles as _styles


def _clean_style_str(val: Any, default: str = "both") -> str:
    """Safely extract string from scalar or Streamlit radio tuple state."""
    if isinstance(val, (tuple, list)):
        return str(val[0])
    return str(val) if val is not None else default

def _persist_widget_selection(widget_key: str, state_key: str) -> None:
    """Copy a widget value into durable state before an unrelated rerun."""
    st.session_state[state_key] = st.session_state.get(widget_key)

def _mark_session_flag(flag_key: str) -> None:
    """Record a widget change that must trigger work later in the rerun."""
    st.session_state[flag_key] = True

def _normalize_stl_split_mode(value: Any, default: str = "full") -> str:
    """Return the canonical STL split slug, including legacy label values."""
    cleaned = _clean_style_str(value, default)
    if cleaned in _constants._STL_SPLIT_LABELS:
        return cleaned
    legacy_to_slug = {label: slug for slug, label in _constants._STL_SPLIT_LABELS.items()}
    return legacy_to_slug.get(cleaned, default)

def _read_json_object(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}

def _reflex_uses_passive_radiator(*, finder: bool = False) -> bool:
    """Return whether the bass-reflex resonator is a passive diaphragm."""
    key = "finder_reflex_resonator_type" if finder else "reflex_resonator_type"
    return st.session_state.get(key, _constants._RESONATOR_PORT) == _constants._RESONATOR_PR

def _select_load_type_card(load_type: str, single_select: bool) -> None:
    """Apply a load-card click before Streamlit starts the next script run."""
    if single_select:
        if st.session_state.get("load_type") == load_type:
            return
        st.session_state["load_type"] = load_type
        _finder._on_load_type_change()
        return
    selected = set(st.session_state.get("finder_load_types", []))
    if load_type in selected:
        selected.discard(load_type)
    else:
        selected.add(load_type)
    if not selected:
        selected = {"Sealed"}
    st.session_state["finder_load_types"] = sorted(
        selected, key=lambda item: _constants._ALL_LOAD_TYPES.index(item)
    )

def _render_load_type_buttons(active_set: set[str], single_select: bool = False) -> set[str]:
    """Grid of compact load diagrams that are themselves clickable buttons.

    In single-select mode clicking a new button *replaces* the set (radio behaviour).
    In multi-select mode each click toggles the load.
    Returns the (possibly modified) set.
    """
    st.markdown(_styles._load_type_card_styles(), unsafe_allow_html=True)
    for row_start, row_end in ((0, 3), (3, len(_constants._ALL_LOAD_TYPES))):
        row_load_types = _constants._ALL_LOAD_TYPES[row_start:row_end]
        row_cols = st.columns(4)
        for offset, lt in enumerate(row_load_types):
            with row_cols[offset]:
                with st.container(key=f"load_card_{_constants._LOAD_TYPE_SLUGS[lt]}"):
                    active = lt in active_set
                    st.button(
                        _constants._LOAD_TYPE_SHORT[lt],
                        key=f"load_btn_{lt}",
                        type="primary" if active else "secondary",
                        width="stretch",
                        on_click=_select_load_type_card,
                        args=(lt, single_select),
                    )
                    st.markdown(
                        f'<div class="load-card-label">{_constants._LOAD_TYPE_SHORT[lt]}</div>',
                        unsafe_allow_html=True,
                    )
    return set(active_set)

def _render_engine_only_topologies_note() -> None:
    """Declare the distributed-waveguide models that stay engine/API-only."""
    with st.expander("Engine/API-only topologies"):
        st.markdown(
            "Transmission line, MLTL, quarter-wave, back-loaded horn and tapped "
            "horn are validated engine models without interactive load cards, "
            "presets or plots. They are reached through the Python API "
            "(`simulate_transmission_line`, `simulate_mltl`, "
            "`simulate_quarter_wave`, `simulate_back_loaded_horn`, "
            "`simulate_tapped_horn`), so they are intentionally not selectable "
            "in this workspace."
        )

def _select_workspace(workspace: str) -> None:
    """Select a workspace from tabs or action buttons."""
    if workspace in {"Manage Projects", "Bass Match", "Box Design", "Catalog Maintenance", "User Management"}:
        st.session_state["workspace_mode"] = workspace
        if workspace in {"Bass Match", "Box Design", "Manage Projects"}:
            for k in ("admin_users", "maintenance", "explore", "p", "embed"):
                st.query_params.pop(k, None)

def _on_workspace_compat_change() -> None:
    val = st.session_state.get("_workspace_compat_mode")
    if val in {"Manage Projects", "Bass Match", "Box Design", "Catalog Maintenance", "User Management"}:
        _select_workspace(val)

def _render_workspace_tabs() -> None:
    """Render image tabs for the two primary technical workspaces."""
    st.markdown(_styles._workspace_tab_styles(), unsafe_allow_html=True)
    active = str(st.session_state.get("workspace_mode", "Bass Match"))
    workspaces = _available_workspaces()
    tab_columns = st.columns(len(workspaces), gap="small")
    for column, workspace in zip(tab_columns, workspaces, strict=True):
        slug = _constants._WORKSPACE_TAB_SLUGS[workspace]
        with column:
            with st.container(key=f"workspace_tab_{slug}"):
                st.button(
                    _constants._WORKSPACE_DISPLAY_LABELS[workspace],
                    key=f"workspace_tab_button_{slug}",
                    type="primary" if workspace == active else "secondary",
                    width="stretch",
                    on_click=_select_workspace,
                    args=(workspace,),
                )
    # Keep this widget in the app tree for old sessions and automated clients.
    # CSS hides it completely from people because the image tabs are the primary control.
    with st.container(key="workspace_compat_control"):
        st.segmented_control(
            "Workspace",
            (*workspaces, "Manage Projects"),
            default=active if active in (*workspaces, "Manage Projects") else "Bass Match",
            format_func=lambda value: _constants._WORKSPACE_DISPLAY_LABELS.get(value, value),
            key="_workspace_compat_mode",
            on_change=_on_workspace_compat_change,
            label_visibility="collapsed",
            width="stretch",
        )

def _available_workspaces() -> tuple[str, ...]:
    return _constants._WORKSPACES

def _is_param_key(key: str) -> bool:
    if not any(key.startswith(prefix) for prefix in _constants._PARAM_PREFIXES):
        return False
    if "apply" in key or "button" in key or key.startswith("btn_") or "combo" in key:
        return False
    # Ignore legacy nudge-button state left by sessions/projects created
    # before box fields switched to the integrated number-input stepper.
    return not key.endswith(_constants._NUDGE_KEY_SUFFIXES)

def _normalize_box_strategy(value) -> str:
    """Map v0.3 strategy names onto the objective-based strategies."""
    value = str(value)
    if value in _constants._BOX_STRATEGIES:
        return value
    if value == "Optimized":
        objective = str(st.session_state.get("opt_objective", "Max extension"))
        return objective if objective in _constants._OPT_OBJECTIVE_LABELS else "Max extension"
    # v0.3 "Suggested" (empirical starter) and unknown values.
    return "Max extension"

def _set_box_strategy_state(strategy: str) -> None:
    """Store a strategy plus the legacy keys older .lfp files round-trip."""
    previous = str(st.session_state.get("box_strategy", "Max extension"))
    st.session_state["box_strategy"] = strategy
    st.session_state["_previous_box_strategy"] = previous
    auto = strategy in _constants._OPT_OBJECTIVE_LABELS
    st.session_state["sim_auto_align"] = auto
    st.session_state["opt_align_mode"] = (
        "Optimized (goals)" if auto else "Empirical (article)"
    )
    if auto:
        st.session_state["opt_objective"] = strategy

def _box_strategy_is_auto() -> bool:
    return str(st.session_state.get("box_strategy", "Max extension")) in _constants._OPT_OBJECTIVE_LABELS

def _manual_box_keys_for_load_type(load_type: str) -> tuple[str, ...]:
    """Return the state keys that constitute the editable box for a load type."""
    if load_type == "Bass reflex":
        if _reflex_uses_passive_radiator():
            return (
                "reflex_vb_l",
                "pr_sp_cm2",
                "pr_fp_hz",
                "pr_qmp",
                "pr_mmp_g",
                "pr_added_mass_g",
                "pr_xmax_mm",
            )
        return ("reflex_vb_l", "reflex_fb_hz", "reflex_port_d_cm")
    if load_type == "Sealed":
        return ("sealed_vb_l",)
    if load_type == "Bandpass 4th order":
        return (
            "bandpass4_vs_l",
            "bandpass4_vp_l",
            "bandpass4_fp_hz",
            "bandpass4_port_d_cm",
        )
    if load_type == "Bandpass 6th order":
        return (
            "bandpass6_vr_l",
            "bandpass6_fr_hz",
            "bandpass6_vp_l",
            "bandpass6_fp_hz",
            "bandpass6_port_d_r_cm",
            "bandpass6_port_d_p_cm",
        )
    if load_type == "Bandpass 8th order":
        return (
            "bp8_v1_l",
            "bp8_f1_hz",
            "bp8_dp1_cm",
            "bp8_lp1_cm",
            "bp8_v2_l",
            "bp8_f2_hz",
            "bp8_dp2_cm",
            "bp8_lp2_cm",
            "bp8_v3_l",
            "bp8_f3_hz",
            "bp8_dp3_cm",
            "bp8_lp3_cm",
        )
    if load_type == "Infinite baffle":
        return ()
    # DCCAV
    return (
        "box_vh_l",
        "box_fh_hz",
        "box_vl_l",
        "box_fl_hz",
        "box_port_d_h_cm",
        "box_port_d_l_cm",
    )

def _snapshot_manual_box(load_type: str) -> None:
    """Save the current editable box values so Manual can restore them later."""
    snapshots = st.session_state.get("_manual_box_snapshots", {})
    snapshots[load_type] = {
        key: st.session_state.get(key)
        for key in _manual_box_keys_for_load_type(load_type)
    }
    st.session_state["_manual_box_snapshots"] = snapshots

def _restore_manual_box(load_type: str) -> bool:
    """Restore the last Manual box values for this load type, if any."""
    snapshots = st.session_state.get("_manual_box_snapshots", {})
    snapshot = snapshots.get(load_type)
    if not snapshot:
        return False
    for key, value in snapshot.items():
        st.session_state[key] = value
    return True

def _snapshot_design_state() -> None:
    """Save the full parameter set before a preset/share link overwrites it."""
    st.session_state["_design_state_backup"] = _collect_params()

def _restore_design_state() -> bool:
    """Restore the last pre-load parameter set, if one was saved."""
    backup = st.session_state.get("_design_state_backup")
    if not backup:
        return False
    _projects._apply_loaded_params(backup)
    st.session_state.pop("_design_state_backup", None)
    return True

def _collect_params() -> dict:
    out = {}
    for key, value in st.session_state.items():
        if _is_param_key(key):
            try:
                json.dumps(value)
            except (TypeError, ValueError):
                continue
            out[key] = value
    return out

def _json_safe(value):
    """Convert project state to strict JSON without NaN or NumPy scalars."""
    if isinstance(value, dict):
        return {
            str(key): _json_safe(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return [_json_safe(item) for item in value.tolist()]
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return number if np.isfinite(number) else None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TypeError(f"Unsupported project value: {type(value).__name__}")

def _driver_from_state() -> _acoustics.DriverTS:
    """Composite driver: per-driver T/S state plus the configuration."""
    return _acoustics.apply_driver_configuration(
        _single_driver_from_state(),
        str(st.session_state.get("driver_config", "Single driver")),
    )

def _single_driver_from_state() -> _acoustics.DriverTS:
    mode = st.session_state.get("driver_sd_mode", "Diameter")
    sd_cm2 = (
        _acoustics.sd_from_diameter(float(st.session_state["driver_diameter_mm"]))
        if mode == "Diameter"
        else float(st.session_state["driver_sd_cm2"])
    )
    return _acoustics.DriverTS(
        fs_hz=float(st.session_state["driver_fs_hz"]),
        vas_l=float(st.session_state["driver_vas_l"]),
        qts=float(st.session_state["driver_qts"]),
        qms=float(st.session_state["driver_qms"]),
        re_ohm=float(st.session_state["driver_re_ohm"]),
        sd_cm2=sd_cm2,
        le_mh=float(st.session_state.get("driver_le_mh", 0.0)),
        le10k_mh=_optional_positive("driver_le10k_mh"),
        xmax_mm=float(st.session_state.get("driver_xmax_mm", 0.0)),
        pe_w=float(st.session_state.get("driver_pe_w", 0.0)),
        mms_g=_optional_positive("driver_mms_g"),
        cms_mm_per_n=_optional_positive("driver_cms_mm_n"),
        bl_tm=_optional_positive("driver_bl_tm"),
        panel_air_load=bool(st.session_state.get("driver_panel_air_load", True)),
        panel_coupling=float(st.session_state.get("driver_panel_coupling", 0.90)),
    )

def _box_from_state() -> _acoustics.DccavBox:
    return _acoustics.DccavBox(
        vh_l=float(st.session_state["box_vh_l"]),
        fh_hz=float(st.session_state["box_fh_hz"]),
        vl_l=float(st.session_state["box_vl_l"]),
        fl_hz=float(st.session_state["box_fl_hz"]),
        q_abs_h=float(st.session_state["loss_q_abs_h"]),
        q_abs_l=float(st.session_state["loss_q_abs_l"]),
        q_leak_h=float(st.session_state["loss_q_leak_h"]),
        q_leak_l=float(st.session_state["loss_q_leak_l"]),
        q_port_h=float(st.session_state["loss_q_port_h"]),
        q_port_l=float(st.session_state["loss_q_port_l"]),
    )

def _reflex_box_from_state() -> _acoustics.ReflexBox:
    use_custom_losses = bool(st.session_state.get("reflex_custom_losses", False))
    return _acoustics.ReflexBox(
        vb_l=float(st.session_state["reflex_vb_l"]),
        fb_hz=float(st.session_state["reflex_fb_hz"]),
        q_abs=float(st.session_state["reflex_q_abs"]) if use_custom_losses else _constants._DEFAULT_REFLEX_Q_ABS,
        q_leak=float(st.session_state["reflex_q_leak"]) if use_custom_losses else _constants._DEFAULT_REFLEX_Q_LEAK,
        q_port=float(st.session_state["reflex_q_port"]) if use_custom_losses else _constants._DEFAULT_REFLEX_Q_PORT,
    )

def _pr_box_from_state() -> _acoustics.PassiveRadiatorBox:
    return _acoustics.PassiveRadiatorBox(
        vb_l=float(st.session_state.get(
            "reflex_vb_l", st.session_state.get("pr_vb_l", 40.0))),
        pr_sp_cm2=float(st.session_state.get("pr_sp_cm2", 200.0)),
        pr_fp_hz=float(st.session_state.get("pr_fp_hz", 20.0)),
        pr_qmp=float(st.session_state.get("pr_qmp", 5.0)),
        pr_mmp_g=float(st.session_state.get("pr_mmp_g", 100.0)),
        pr_added_mass_g=float(st.session_state.get("pr_added_mass_g", 0.0)),
        pr_xmax_mm=float(st.session_state.get("pr_xmax_mm", 0.0)),
        q_abs=float(st.session_state.get("pr_q_abs", 15.0)),
        q_leak=float(st.session_state.get("pr_q_leak", 1000.0)),
    )

def _sealed_box_from_state() -> _acoustics.SealedBox:
    return _acoustics.SealedBox(
        vb_l=float(st.session_state["sealed_vb_l"]),
        q_abs=float(st.session_state["sealed_q_abs"]),
        q_leak=float(st.session_state["sealed_q_leak"]),
    )

def _bandpass4_box_from_state() -> _acoustics.Bandpass4Box:
    return _acoustics.Bandpass4Box(
        vs_l=float(st.session_state["bandpass4_vs_l"]),
        vp_l=float(st.session_state["bandpass4_vp_l"]),
        fp_hz=float(st.session_state["bandpass4_fp_hz"]),
        q_abs_s=float(st.session_state["bandpass4_q_abs_s"]),
        q_abs_p=float(st.session_state["bandpass4_q_abs_p"]),
        q_leak_s=float(st.session_state["bandpass4_q_leak_s"]),
        q_leak_p=float(st.session_state["bandpass4_q_leak_p"]),
        q_port=float(st.session_state["bandpass4_q_port"]),
    )

def _bandpass6_box_from_state() -> _acoustics.Bandpass6Box:
    return _acoustics.Bandpass6Box(
        vr_l=float(st.session_state["bandpass6_vr_l"]),
        fr_hz=float(st.session_state["bandpass6_fr_hz"]),
        vp_l=float(st.session_state["bandpass6_vp_l"]),
        fp_hz=float(st.session_state["bandpass6_fp_hz"]),
        q_abs_r=float(st.session_state["bandpass6_q_abs_r"]),
        q_abs_p=float(st.session_state["bandpass6_q_abs_p"]),
        q_leak_r=float(st.session_state["bandpass6_q_leak_r"]),
        q_leak_p=float(st.session_state["bandpass6_q_leak_p"]),
        q_port_r=float(st.session_state["bandpass6_q_port_r"]),
        q_port_p=float(st.session_state["bandpass6_q_port_p"]),
    )

def _bandpass8_box_from_state() -> _acoustics.Bandpass8Box:
    return _acoustics.Bandpass8Box(
        v1_l=float(st.session_state["bp8_v1_l"]),
        f1_hz=float(st.session_state["bp8_f1_hz"]),
        v2_l=float(st.session_state["bp8_v2_l"]),
        f2_hz=float(st.session_state["bp8_f2_hz"]),
        v3_l=float(st.session_state["bp8_v3_l"]),
        f3_hz=float(st.session_state["bp8_f3_hz"]),
        q_abs_1=float(st.session_state.get("bp8_q_abs_1", 15.0)),
        q_abs_2=float(st.session_state.get("bp8_q_abs_2", 15.0)),
        q_abs_3=float(st.session_state.get("bp8_q_abs_3", 15.0)),
        q_leak_1=float(st.session_state.get("bp8_q_leak_1", 1000.0)),
        q_leak_2=float(st.session_state.get("bp8_q_leak_2", 1000.0)),
        q_leak_3=float(st.session_state.get("bp8_q_leak_3", 1000.0)),
        q_port_1=float(st.session_state.get("bp8_q_port_1", 15.0)),
        q_port_2=float(st.session_state.get("bp8_q_port_2", 15.0)),
        q_port_3=float(st.session_state.get("bp8_q_port_3", 15.0)),
    )

def _optional_positive(key: str) -> float | None:
    value = float(st.session_state.get(key, 0.0) or 0.0)
    return value if value > 0 else None

def _default(key: str, value):
    st.session_state.setdefault(key, value)

def _reset_response_zoom(full_window: tuple[int, int]) -> None:
    st.session_state["plot_response_window_hz"] = tuple(full_window)

def _ensure_plot_control_state() -> None:
    """Keep plot choices alive across conditionally rendered workspaces."""
    # The total response is the baseline for every design and must never vanish.
    st.session_state["plot_response_total"] = True
    # Self-assignment detaches these values from Streamlit's widget cleanup when
    # Find a driver is open and the Response fragment is not rendered.
    for key in (
        "plot_response_driver",
        "plot_response_lower_port",
        "plot_response_mol",
        "plot_show_mil",
        "plot_show_tuning_markers",
        "plot_compare_loads",
        "plot_tolerance_band",
        "plot_port_upper",
        "plot_port_lower",
        "atlas_enabled",
    ):
        if key in st.session_state:
            st.session_state[key] = bool(st.session_state[key])
    for key in (
        "plot_response_window_hz",
        "plot_tolerance_pct",
        "cursor_auto_markers",
        "atlas_metric",
    ):
        if key in st.session_state:
            st.session_state[key] = st.session_state[key]

def _reset_finder_defaults() -> None:
    """Restore a practical, quick first-pass driver search."""
    for key, value in _constants._FINDER_DEFAULTS.items():
        st.session_state[key] = value
    st.session_state["_finder_defaults_version"] = _constants._FINDER_DEFAULTS_VERSION
    st.session_state.pop("batch_results", None)
    st.session_state.pop("batch_result_context", None)
    st.session_state.pop("batch_search_completed", None)
    st.session_state.pop("finder_last_run_stats", None)
    st.session_state.pop("_restored_bass_match_controls_signature", None)
    _projects._invalidate_bass_match_results_signature()

def _ensure_finder_defaults() -> None:
    """Migrate stale Finder widgets without pre-seeding implicit UI minima."""
    # Desired F3 was retired from Bass Match: it behaved as a soft optimizer
    # preference rather than a reliable ranking constraint.
    st.session_state.pop("finder_target_f3_hz", None)
    # Every usable ranked candidate is now shown; old 1–200 display caps must
    # not survive in live sessions or restored projects.
    st.session_state.pop("finder_result_count", None)
    if st.session_state.get("_finder_defaults_version") != _constants._FINDER_DEFAULTS_VERSION:
        # Retired v3 widgets: the scan now always covers the whole filtered
        # library and every candidate goes through the optimizer.
        for key in (
            *_constants._FINDER_DEFAULTS,
            "finder_candidate_limit",
            "finder_result_count",
            "finder_use_optimizer",
            "finder_target_f3_hz",
        ):
            st.session_state.pop(key, None)
        st.session_state["_finder_defaults_version"] = _constants._FINDER_DEFAULTS_VERSION
        st.session_state.pop("batch_results", None)
        st.session_state.pop("batch_result_context", None)
        st.session_state.pop("batch_search_completed", None)
        st.session_state.pop("finder_last_run_stats", None)
        st.session_state.pop("_restored_bass_match_controls_signature", None)
        _projects._invalidate_bass_match_results_signature()
    else:
        # Keep conditionally rendered Finder values alive while Design is open.
        for key in _constants._FINDER_DEFAULTS:
            if key in st.session_state:
                st.session_state[key] = st.session_state[key]

def _ensure_price_currency_default() -> None:
    """Migrate existing sessions to the EUR price display default once."""
    if st.session_state.get("_price_currency_defaults_version") != _constants._PRICE_CURRENCY_DEFAULTS_VERSION:
        st.session_state["preset_price_currency"] = "EUR"
        st.session_state["_price_currency_defaults_version"] = _constants._PRICE_CURRENCY_DEFAULTS_VERSION

def _preserve_design_state() -> None:
    """Keep design widget values alive while the Finder workspace is open.

    Streamlit drops widget-bound state for keyed widgets that skip a rerun:
    without this, one trip through Find a driver silently resets voltage,
    manual box values and T/S edits back to their defaults or widget minima.
    """
    for key in list(st.session_state):
        if _is_param_key(key):
            st.session_state[key] = st.session_state[key]
    for tab_key in ("box_design_sidebar_tab", "manage_projects_tab"):
        if tab_key in st.session_state:
            st.session_state[tab_key] = st.session_state[tab_key]
    if "design_analysis_tab" in st.session_state:
        st.session_state["design_analysis_tab"] = st.session_state[
            "design_analysis_tab"
        ]

def _preserve_library_filters() -> None:
    """Keep Finder-only catalog filters while the Design workspace is open."""
    filter_keys = (
        "preset_search",
        "finder_load_types",
        "preset_family_filter",
        "preset_source_filter",
        "preset_size_filter",
        "preset_class_filter",
        "preset_price_enabled",
        "preset_max_price",
        "preset_price_currency",
        "bass_match_sidebar_tab",
        "finder_candidate_pool_expander",
    )
    compact_widget_keys = tuple(
        widget_key
        for filter_key in (
            "preset_family_filter",
            "preset_source_filter",
            "preset_size_filter",
            "preset_class_filter",
        )
        for widget_key in (
            f"{filter_key}__select_v5",
            f"{filter_key}__select_v5__aggregate",
        )
    )
    # Snapshot first: Streamlit can add internal widget entries while state is
    # inspected. Iterating and assigning through the live proxy in one pass can
    # otherwise raise ``dictionary changed size during iteration``.
    preserved = {
        key: st.session_state[key]
        for key in (*filter_keys, *compact_widget_keys)
        if key in st.session_state
    }
    for key, value in preserved.items():
        st.session_state[key] = value

def _reset_candidate_filters() -> None:
    """Restore every filter that can empty the unranked driver library."""
    st.session_state["preset_search"] = ""
    for key in (
        "preset_family_filter",
        "preset_source_filter",
        "preset_size_filter",
        "preset_class_filter",
    ):
        st.session_state[key] = ["All"]
    st.session_state["preset_price_enabled"] = False
    st.session_state["finder_max_mms_g"] = 0.0
    st.session_state["finder_max_le_mh"] = 0.0
    for key in list(st.session_state):
        if "__toggle_v4__" in str(key):
            del st.session_state[key]
    st.session_state.pop("finder_driver_library_table", None)

def _finder_value(key: str):
    """Read a Finder widget value, falling back to its default.

    Outside a Streamlit runtime (bare import, e.g. from the test suite) the
    widgets never register their values in session state.
    """
    return st.session_state.get(key, _constants._FINDER_DEFAULTS[key])

def _finder_number_input(label: str, key: str, **kwargs):
    """Render an explicit first value, then defer to the widget's live state."""
    if key not in st.session_state:
        kwargs["value"] = _constants._FINDER_DEFAULTS[key]
    return st.number_input(label, key=key, **kwargs)

def _finder_selectbox(label: str, options: list[str], key: str, **kwargs):
    """Select the intended first value instead of the first option in the list."""
    if key not in st.session_state:
        kwargs["index"] = options.index(str(_constants._FINDER_DEFAULTS[key]))
    return st.selectbox(label, options, key=key, **kwargs)

def _box_number_with_nudge(
    label: str,
    key: str,
    *,
    min_value: float,
    max_value: float,
    step: float,
    disabled: bool = False,
):
    st.number_input(
        label,
        min_value=min_value,
        max_value=max_value,
        step=_finder._step5(key, step),
        key=key,
        disabled=disabled,
    )

def _table_value_missing(value: object) -> bool:
    """Return true for values that must not be shown as None/nan in a table."""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return isinstance(value, (float, np.floating)) and not np.isfinite(value)

def _clean_display_table_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Hide empty columns and render partial missing values as an em dash."""
    display = frame.copy()
    empty_columns = [
        name for name in display.columns
        if display[name].map(_table_value_missing).all()
    ]
    if empty_columns:
        display = display.drop(columns=empty_columns)
    for name in display.columns:
        missing = display[name].map(_table_value_missing)
        if not missing.any():
            continue
        if name in _constants._TABLE_NUMBER_FORMATS:
            # Keep numeric columns numeric for Arrow/Streamlit.  Replacing
            # missing values with the em-dash string makes pandas infer an
            # object column and can raise ArrowTypeError when the table is
            # serialized (notably on Safari's first render).
            display[name] = pd.to_numeric(display[name], errors="coerce")
        elif name != "Response":
            display[name] = [
                "—" if is_missing else value
                for value, is_missing in zip(display[name], missing, strict=True)
            ]
    return display

def _driver_from_params(params: Mapping[str, Any]) -> _acoustics.DriverTS:
    sd_cm2 = float(params.get("driver_sd_cm2", 500.0) or 500.0)
    driver = _acoustics.DriverTS(
        fs_hz=float(params.get("driver_fs_hz", 35.0) or 35.0),
        vas_l=float(params.get("driver_vas_l", 50.0) or 50.0),
        qts=float(params.get("driver_qts", 0.35) or 0.35),
        qms=float(params.get("driver_qms", 4.0) or 4.0),
        re_ohm=float(params.get("driver_re_ohm", 6.0) or 6.0),
        sd_cm2=sd_cm2,
        le_mh=float(params.get("driver_le_mh", 0.0) or 0.0),
        xmax_mm=float(params.get("driver_xmax_mm", 0.0) or 0.0),
        pe_w=float(params.get("driver_pe_w", 0.0) or 0.0),
        panel_air_load=bool(params.get("driver_panel_air_load", True)),
        panel_coupling=float(params.get("driver_panel_coupling", 0.90) or 0.90),
    )
    return _acoustics.apply_driver_configuration(
        driver, str(params.get("driver_config", "Single driver"))
    )

def _box_from_params(params: Mapping[str, Any], load_type: str):
    if load_type == "Bass reflex":
        if params.get("reflex_resonator_type") == _constants._RESONATOR_PR or params.get("load_type") == "Passive radiator":
            return _acoustics.PassiveRadiatorBox(
                vb_l=float(params.get("reflex_vb_l", params.get("pr_vb_l", 40.0)) or 40.0),
                pr_sp_cm2=float(params.get("pr_sp_cm2", 200.0) or 200.0),
                pr_fp_hz=float(params.get("pr_fp_hz", 20.0) or 20.0),
                pr_qmp=float(params.get("pr_qmp", 5.0) or 5.0),
                pr_mmp_g=float(params.get("pr_mmp_g", 100.0) or 100.0),
                pr_added_mass_g=float(params.get("pr_added_mass_g", 0.0) or 0.0),
                pr_xmax_mm=float(params.get("pr_xmax_mm", 0.0) or 0.0),
            )
        return _acoustics.ReflexBox(
            vb_l=float(params.get("reflex_vb_l", 40.0) or 40.0),
            fb_hz=float(params.get("reflex_fb_hz", 40.0) or 40.0),
        )
    elif load_type == "Sealed":
        return _acoustics.SealedBox(
            vb_l=float(params.get("sealed_vb_l", 30.0) or 30.0),
            q_abs=float(params.get("sealed_q_abs", 20.0) or 20.0),
            q_leak=float(params.get("sealed_q_leak", 20.0) or 20.0),
        )
    elif load_type == "DCCAV":
        return _acoustics.DccavBox(
            vh_l=float(params.get("box_vh_l", params.get("dccav_vb1_l", 20.0)) or 20.0),
            fh_hz=float(params.get("box_fh_hz", params.get("dccav_fb1_hz", 60.0)) or 60.0),
            vl_l=float(params.get("box_vl_l", params.get("dccav_vb2_l", 20.0)) or 20.0),
            fl_hz=float(params.get("box_fl_hz", params.get("dccav_fb2_hz", 30.0)) or 30.0),
        )
    elif load_type == "Bandpass 4th order":
        return _acoustics.Bandpass4Box(
            vs_l=float(params.get("bandpass4_vs_l", params.get("bp4_vb_l", 25.0)) or 25.0),
            vp_l=float(params.get("bandpass4_vp_l", params.get("bp4_vf_l", 15.0)) or 15.0),
            fp_hz=float(params.get("bandpass4_fp_hz", params.get("bp4_fb_hz", 55.0)) or 55.0),
        )
    elif load_type == "Bandpass 6th order":
        return _acoustics.Bandpass6Box(
            vr_l=float(params.get("bandpass6_vr_l", params.get("bp6_vr_l", 30.0)) or 30.0),
            fr_hz=float(params.get("bandpass6_fr_hz", params.get("bp6_fb_r_hz", 35.0)) or 35.0),
            vp_l=float(params.get("bandpass6_vp_l", params.get("bp6_vf_l", 15.0)) or 15.0),
            fp_hz=float(params.get("bandpass6_fp_hz", params.get("bp6_fb_f_hz", 70.0)) or 70.0),
        )
    elif load_type == "Bandpass 8th order":
        return _acoustics.Bandpass8Box(
            v1_l=float(params.get("bp8_v1_l", params.get("bp8_vr_l", 20.0)) or 20.0),
            f1_hz=float(params.get("bp8_f1_hz", params.get("bp8_fb_r_hz", 30.0)) or 30.0),
            v2_l=float(params.get("bp8_v2_l", params.get("bp8_vf1_l", 15.0)) or 15.0),
            f2_hz=float(params.get("bp8_f2_hz", params.get("bp8_fb_f1_hz", 60.0)) or 60.0),
            v3_l=float(params.get("bp8_v3_l", params.get("bp8_vf2_l", 10.0)) or 10.0),
            f3_hz=float(params.get("bp8_f3_hz", params.get("bp8_fb_f2_hz", 100.0)) or 100.0),
        )
    elif load_type == "Infinite baffle":
        return None
    return None
