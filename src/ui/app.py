"""Streamlit app entry point: session bootstrap, sidebar and workspace dispatch."""

from __future__ import annotations

import numpy as np
import streamlit as st

import acoustics as _acoustics
import billing as _billing
import generate_afw_dccav as _afw_export
import ranking as _ranking

from . import account as _account
from . import analysis as _analysis
from . import catalog as _catalog
from . import constants as _constants
from . import finder as _finder
from . import optimizer as _optimizer
from . import projects as _projects
from . import runtime as _runtime
from . import state as _state


def main() -> None:
    # The original script re-created functools caches on every Streamlit
    # rerun; keep that per-run scope now that modules are imported once.
    _account._get_current_user_account.cache_clear()
    _catalog._driver_preset_family.cache_clear()
    _catalog._driver_preset_identity_fields.cache_clear()
    _catalog._driver_preset_display_label.cache_clear()
    _catalog._driver_preset_source.cache_clear()
    _catalog._driver_preset_size.cache_clear()
    _projects._community_tab_image_b64.cache_clear()
    _state._default("driver_fs_hz", 48.14)
    _state._default("driver_vas_l", 11.52)
    _state._default("driver_qts", 0.362)
    _state._default("driver_qms", 2.372)
    _state._default("driver_re_ohm", 6.89)
    _state._default("driver_sd_mode", "Diameter")
    _state._default("driver_diameter_mm", 104.0)
    _state._default("driver_sd_cm2", _acoustics.sd_from_diameter(104.0))
    _state._default("driver_le_mh", 0.421)
    _state._default("driver_le10k_mh", 0.0)
    _state._default("driver_xmax_mm", 3.1)
    _state._default("driver_pe_w", 60.0)
    _state._default("driver_mms_g", 0.0)
    _state._default("driver_cms_mm_n", 0.0)
    _state._default("driver_bl_tm", 0.0)
    _state._default("driver_panel_air_load", True)
    _state._default("driver_panel_coupling", 0.90)
    _state._default("driver_preset_name", "KEF B110B article example")
    _state._default("driver_config", "Single driver")
    _state._default("preset_family_filter", ["All"])
    _state._default("preset_source_filter", ["All"])
    _state._default("preset_size_filter", ["All"])
    _state._default("preset_class_filter", ["All"])
    _state._default("preset_search", "")
    _state._default("preset_price_enabled", False)
    _state._default("preset_max_price", 0.0)
    _state._default("preset_price_currency", "EUR")
    _state._default("loss_q_abs_h", 15.0)
    _state._default("loss_q_abs_l", 15.0)
    _state._default("loss_q_leak_h", 1000.0)
    _state._default("loss_q_leak_l", 1000.0)
    _state._default("loss_q_port_h", 15.0)
    _state._default("loss_q_port_l", 15.0)
    _state._default("reflex_q_abs", _constants._DEFAULT_REFLEX_Q_ABS)
    _state._default("reflex_q_leak", _constants._DEFAULT_REFLEX_Q_LEAK)
    _state._default("reflex_q_port", _constants._DEFAULT_REFLEX_Q_PORT)
    _state._default("reflex_custom_losses", False)
    _state._default("reflex_port_d_cm", 5.0)
    _state._default("reflex_resonator_type", _constants._RESONATOR_PORT)
    _state._default("pr_preset_name", "Custom")
    _state._default("pr_sp_cm2", 200.0)
    _state._default("pr_fp_hz", 20.0)
    _state._default("pr_qmp", 5.0)
    _state._default("pr_mmp_g", 100.0)
    _state._default("pr_added_mass_g", 0.0)
    _state._default("pr_xmax_mm", 0.0)
    _state._default("pr_q_abs", 15.0)
    _state._default("pr_q_leak", 1000.0)
    _state._default("bandpass4_q_abs_s", 15.0)
    _state._default("bandpass4_q_abs_p", 15.0)
    _state._default("bandpass4_q_leak_s", 1000.0)
    _state._default("bandpass4_q_leak_p", 1000.0)
    _state._default("bandpass4_q_port", 15.0)
    _state._default("bandpass4_port_d_cm", 5.0)
    _state._default("bandpass6_q_abs_r", 15.0)
    _state._default("bandpass6_q_abs_p", 15.0)
    _state._default("bandpass6_q_leak_r", 1000.0)
    _state._default("bandpass6_q_leak_p", 1000.0)
    _state._default("bandpass6_q_port_r", 15.0)
    _state._default("bandpass6_q_port_p", 15.0)
    _state._default("bandpass6_port_d_r_cm", 5.0)
    _state._default("bandpass6_port_d_p_cm", 5.0)
    _state._default("box_port_d_h_cm", 5.0)
    _state._default("box_port_d_l_cm", 5.0)
    _state._default("sealed_q_abs", 15.0)
    _state._default("sealed_q_leak", 1000.0)
    _state._default("load_type", "DCCAV")
    if st.session_state["load_type"] in ("Suspension pneumatic", "Acoustic suspension"):
        st.session_state["load_type"] = "Sealed"
    elif st.session_state["load_type"] == "Passive radiator":
    # Compatibility for pre-0.5.2 sessions: PR is a resonator choice, not a load.
        st.session_state["load_type"] = "Bass reflex"
        st.session_state["reflex_resonator_type"] = _constants._RESONATOR_PR
        if "pr_vb_l" in st.session_state:
            st.session_state["reflex_vb_l"] = float(st.session_state["pr_vb_l"])
    _state._default("sim_f_min", 10.0)
    _state._default("sim_f_max", 500.0)
    _state._default("sim_points", 600)
    _state._default("sim_voltage", 2.83)
    _state._default("sim_series_r_ohm", 0.0)
    _state._default("sim_auto_align", True)
    _state._default("bp8_v1_l", 10.0)
    _state._default("bp8_f1_hz", 100.0)
    _state._default("bp8_dp1_cm", 5.0)
    _state._default("bp8_lp1_cm", 10.0)
    _state._default("bp8_v2_l", 30.0)
    _state._default("bp8_f2_hz", 35.0)
    _state._default("bp8_dp2_cm", 5.0)
    _state._default("bp8_lp2_cm", 10.0)
    _state._default("bp8_v3_l", 40.0)
    _state._default("bp8_f3_hz", 60.0)
    _state._default("bp8_dp3_cm", 7.0)
    _state._default("bp8_lp3_cm", 12.0)
    _state._default("bp8_q_abs_1", 15.0)
    _state._default("bp8_q_abs_2", 15.0)
    _state._default("bp8_q_abs_3", 15.0)
    _state._default("bp8_q_leak_1", 1000.0)
    _state._default("bp8_q_leak_2", 1000.0)
    _state._default("bp8_q_leak_3", 1000.0)
    _state._default("bp8_q_port_1", 15.0)
    _state._default("bp8_q_port_2", 15.0)
    _state._default("bp8_q_port_3", 15.0)
    _state._default("plot_response_traces", ["Total"])
    _state._default("plot_port_traces", list(_constants._PORT_TRACE_OPTIONS))
    _state._default("plot_response_total", "Total" in st.session_state["plot_response_traces"])
    _state._default(
        "plot_response_driver",
        "Cone" in st.session_state["plot_response_traces"]
        or "Driver" in st.session_state["plot_response_traces"],
    )
    _state._default("plot_response_lower_port", "Lower port" in st.session_state["plot_response_traces"])
    _state._default("plot_response_mol", True)
    if int(st.session_state.get("_response_defaults_version", 0) or 0) < _constants._RESPONSE_DEFAULTS_VERSION:
        st.session_state["plot_response_mol"] = True
        st.session_state["_response_defaults_version"] = _constants._RESPONSE_DEFAULTS_VERSION
    _state._default("plot_response_window_hz", (10, 500))
    _state._default("plot_show_mil", False)
    _state._default("plot_show_tuning_markers", True)
    _state._default("plot_compare_loads", False)
    _state._default("plot_tolerance_band", False)
    _state._default("plot_tolerance_pct", 15.0)
    _state._default("atlas_enabled", False)
    _state._default("atlas_metric", "F3 (Hz)")
    _state._default("plot_port_upper", "Upper port" in st.session_state["plot_port_traces"])
    _state._default("plot_port_lower", "Lower port" in st.session_state["plot_port_traces"])
    _state._default("cursor_auto_markers", list(_constants._AUTO_CURSOR_OPTIONS))
    _state._ensure_plot_control_state()
    _state._default("opt_align_mode", "Empirical (article)")
    _state._default("opt_objective", "Balanced")
    _state._default("opt_max_volume_l", 0.0)
    _state._default("opt_target_f3_hz", 0.0)
    _state._default("opt_max_ripple_db", 3.0)
    _state._default("opt_max_ripple_freq_hz", 0.0)
    _state._default("opt_excursion_ratio", 1.0)
    _state._default("opt_max_gd_ms", 0.0)
    _state._default("workspace_mode", "Bass Match")
    _state._default("ui_show_advanced", False)
    _state._ensure_finder_defaults()
    _state._ensure_price_currency_default()
    try:
        _projects._apply_pending_cloud_record()
    except Exception as exc:
        _runtime.logger.exception("Could not activate queued cloud project")
        st.error(f"Could not open the cloud project: {exc}")
    if "finder_load_types" in st.session_state:
        legacy_finder_loads = list(st.session_state["finder_load_types"])
        if "Passive radiator" in legacy_finder_loads:
            st.session_state["finder_reflex_resonator_type"] = _constants._RESONATOR_PR
            st.session_state["finder_load_types"] = list(dict.fromkeys(
                "Bass reflex" if item == "Passive radiator" else item
                for item in legacy_finder_loads
            ))
    _state._preserve_library_filters()
    _state._preserve_design_state()
    if "box_strategy" not in st.session_state:
        if st.session_state.get("sim_auto_align", True):
            _state._set_box_strategy_state("Max extension")
        elif st.session_state.get("opt_align_mode") == "Optimized (goals)":
            _state._set_box_strategy_state(_state._normalize_box_strategy("Optimized"))
        else:
            _state._set_box_strategy_state("Manual")
    else:
    # Live sessions may still carry v0.3 "Suggested"/"Optimized" values.
        _state._set_box_strategy_state(
            _state._normalize_box_strategy(st.session_state["box_strategy"]))
    if (
        st.session_state.get("load_type") == "Bass reflex"
        and _state._reflex_uses_passive_radiator()
        and _state._box_strategy_is_auto()
    ):
    # The generic optimizer sweeps duct tuning, which is not the PR mass and
    # suspension problem. Keep the radiator controls explicitly editable.
        _state._set_box_strategy_state("Manual")
    if "_optimizer_engine_revision" not in st.session_state:
        st.session_state["_optimizer_engine_revision"] = _constants._OPTIMIZER_ENGINE_REVISION
    _finder._apply_pending_batch_result()
    _finder._apply_pending_batch_comparison()
    _analysis._sync_active_design_comparison_tab()
    _finder._apply_pending_atlas_point()
    _share_token = st.query_params.get("d")
    if _share_token and st.session_state.get("_applied_share_token") != _share_token:
        st.session_state["_applied_share_token"] = _share_token
        try:
            _state._snapshot_design_state()
            _share_count = _projects._apply_loaded_params(_projects._decode_share_payload(_share_token))
            _finder._mark_auto_alignment_synced()
            st.toast(f"Loaded {_share_count} parameters from the shared link")
        except Exception:
            _runtime.logger.exception("Invalid share link payload")
            st.warning("The shared link could not be decoded; using the current parameters.")
    _finder._initialize_alignment_defaults()
    _finder._sync_auto_alignment_if_needed()
    _checkout_status = st.query_params.get("checkout")
    if _checkout_status:
        if _checkout_status == "success":
            session_id = st.query_params.get("session_id")
            if session_id and _billing.is_stripe_configured():
                try:
                    sess_info = _billing.sync_checkout_session(session_id, _runtime._ACCOUNT_STORE)
                    if sess_info.get("type") == "credit_pack":
                        st.toast(f"🎉 Payment successful! Added {sess_info.get('credits', 0):,} credits to your balance.", icon="⚡")
                    else:
                        st.toast("🎉 Subscription checkout successful! Your Pro access is active.", icon="🚀")
                except Exception:
                    st.toast("🎉 Checkout successful! Syncing account state...", icon="🚀")
            else:
                st.toast("🎉 Checkout successful! Syncing account state...", icon="🚀")
            st.session_state.pop("_cached_user_account", None)
        elif _checkout_status == "canceled":
            st.toast("Checkout canceled. No charges were made.", icon="ℹ️")
        st.query_params.pop("checkout", None)
        st.query_params.pop("session_id", None)
        st.query_params.pop("pack", None)
    if st.query_params.get("logout") in ("1", "true", "yes"):
        st.query_params.pop("logout", None)
        _account._sign_out_saas()
    finder_library_filters_slot = st.empty()
    current_ts = None
    current_alignment = None
    current_reflex_alignment = None
    current_bandpass4_alignment = None
    current_bandpass6_alignment = None
    current_sealed_alignment = None
    derived = None
    _raw_p = _projects._parse_query_param_str("p")
    _public_project_requested = _raw_p.split("&")[0].strip() if "&" in _raw_p else _raw_p
    _embed_mode_requested = (
        _projects._parse_query_param_str("embed") in {"1", "true", "yes"}
        or "embed=1" in _raw_p
        or "embed=true" in _raw_p
    )
    _explore_requested = (
        _projects._parse_query_param_str("explore") in {"1", "true", "yes"}
        or "explore=1" in _raw_p
        or "explore=true" in _raw_p
        or str(st.session_state.get("workspace_mode", "")) == "Community"
    )
    _catalog._poll_catalog_refresh()
    with st.sidebar:
        if _constants._BRAND_IMAGE.exists():
            with st.container(key="brand_logo"):
                st.image(str(_constants._BRAND_IMAGE), width=170)
            st.markdown(
                f"<div style='text-align: right; color: rgba(255,255,255,0.4); font-size: 0.7rem; margin-top: -0.4rem; margin-bottom: 0.4rem;'>v{_runtime._VERSION}</div>", 
                unsafe_allow_html=True
            )
        else:
            st.title("Load Forge")
            st.caption(f"v{_runtime._VERSION}")

        workspace_mode = str(st.session_state.get("workspace_mode", "Bass Match"))
        if _explore_requested:
            _projects._render_community_sidebar()
        elif _public_project_requested:
            _projects._render_public_project_sidebar(_public_project_requested)
        elif workspace_mode == "Manage Projects":
            _projects._render_project_menu()
            _state._render_workspace_tabs()
        elif workspace_mode == "Bass Match":
            _projects._render_project_menu()
            _state._render_workspace_tabs()
            if "finder_load_types" not in st.session_state:
                st.session_state["finder_load_types"] = [st.session_state.get("load_type", "DCCAV")]
            bm_tab1, bm_tab2, bm_tab3 = st.tabs(
                ["Load type", "Performance filters", "Library filters"],
                key="bass_match_sidebar_tab",
            )
        
            with bm_tab1:
                if "finder_load_types" not in st.session_state:
                    st.session_state["finder_load_types"] = [
                        str(st.session_state.get("load_type", "DCCAV"))]
                _finder._render_finder_scenario_selector()
                _finder_load_set = set(st.session_state["finder_load_types"])
                _state._render_load_type_buttons(_finder_load_set, single_select=False)
                st.caption("Toggle the loads you want to compare. At least one must stay active.")
                _finder._render_find_driver_target_sidebar()
                _state._render_engine_only_topologies_note()
                if _finder._show_advanced_controls():
                    with st.expander("Advanced evaluation", expanded=True):
                        _state._finder_selectbox(
                            "Search profile",
                            list(_ranking.SEARCH_PROFILES.keys()),
                            key="finder_search_profile",
                            help="Standard (1 credit/driver): budget scaled to the load topology, 20 evaluations per free axis + 10 (Sealed 30, Bass reflex 50, BP4 70, BP6/DCCAV 90, BP8 120) with adaptive spectral verification. Deep (2 credits/driver): 40 per axis + 20 (up to 240) for maximum exploration depth.",
                        )
                        _state._finder_number_input(
                            "Evaluation range start (Hz)", min_value=1.0, max_value=1000.0,
                            step=1.0, key="finder_f_min",
                            help="Lowest frequency included in response, excursion and delay evaluation.",
                        )
                        _state._finder_number_input(
                            "Evaluation range end (Hz)", min_value=10.0, max_value=5000.0,
                            step=10.0, key="finder_f_max",
                            help="Highest frequency included in the low-frequency comparison.",
                        )
                        _state._finder_number_input(
                            "Simulation resolution (points)", min_value=80, max_value=1000,
                            step=20, key="finder_points",
                        )
                        st.button(
                            "Reset Finder defaults",
                            key="finder_reset_defaults",
                            on_click=_state._reset_finder_defaults,
                            width="stretch",
                            help="Restore the practical quick-scan profile without changing the active design.",
                        )
            with bm_tab2:
                _finder._render_find_driver_goal_sidebar()

            all_preset_names = _catalog._available_driver_preset_names()
            with bm_tab3:
                _catalog._render_finder_library_filters(all_preset_names)

            def _live_or_aggregate_filter(key: str):
                live = st.session_state.get(f"{key}__select_v5")
                aggregate = st.session_state.get(key, ["All"])
            # Empty live multiselect means All only when no restored/project
            # aggregate carries a concrete selection.
                return live if live else aggregate

            filtered_preset_names = _catalog._filter_driver_preset_names(
                all_preset_names,
            # Read the live multiselect keys. The aggregate project keys are
            # updated by callbacks and can otherwise lag one rerun behind
            # when a second manufacturer is added to the selection.
                source=_live_or_aggregate_filter("preset_source_filter"),
                family=_live_or_aggregate_filter("preset_family_filter"),
                size=_live_or_aggregate_filter("preset_size_filter"),
                search=st.session_state.get("preset_search", ""),
                max_price=(
                    float(st.session_state["preset_max_price"])
                    if st.session_state.get("preset_price_enabled", False) else None
                ),
                max_price_currency=(
                    str(st.session_state["preset_price_currency"])
                    if st.session_state.get("preset_price_enabled", False) else None
                ),
                selected=None,
                driver_class=_live_or_aggregate_filter("preset_class_filter"),
                max_mms_g=(
                    float(st.session_state["finder_max_mms_g"])
                    if float(st.session_state.get("finder_max_mms_g", 0.0)) > 0.0
                    else None
                ),
                max_le_mh=(
                    float(st.session_state["finder_max_le_mh"])
                    if float(st.session_state.get("finder_max_le_mh", 0.0)) > 0.0
                    else None
                ),
            )
            _catalog._sync_finder_library_selection(filtered_preset_names)
            with bm_tab3:
                _finder._render_find_driver_actions(filtered_preset_names)

        elif not (_explore_requested or _public_project_requested):
            _projects._render_project_menu()
            _state._render_workspace_tabs()
            bd_tab1, bd_tab2, bd_tab3 = st.tabs(
                ["Driver", "Load Selection", "Enclosure Parameters"],
                key="box_design_sidebar_tab",
            )
        
            if "_pending_driver_preset_name" in st.session_state:
                st.session_state["driver_preset_name"] = st.session_state.pop(
                    "_pending_driver_preset_name"
                )
            all_preset_names = _catalog._available_driver_preset_names()
            with bd_tab1:
                col_search, col_refresh = st.columns([5, 1])
                with col_search:
                    st.text_input(
                        "Search preset",
                        key="preset_search",
                        placeholder="Manufacturer or part number",
                    )
                with col_refresh:
                    st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                    if st.button(
                        "🔄",
                        key="refresh_presets_btn_box_design",
                        help="Refresh driver library from cloud catalog & Z-Bench",
                        use_container_width=True,
                    ):
                        _acoustics.invalidate_preset_caches()
                        _acoustics.check_dynamic_catalog_freshness(force=True)
                        st.rerun()
            filtered_preset_names = _catalog._filter_driver_preset_names(
                all_preset_names,
                source="All",
                family="All",
                size="All",
                search=st.session_state.get("preset_search", ""),
                max_price=None,
                max_price_currency=None,
                selected=st.session_state.get("driver_preset_name"),
                driver_class="All"
            )
            current_preset = st.session_state.get("driver_preset_name", "Custom")
        # A 10k-option dropdown re-serialized on every rerun makes workspace
        # switches take seconds in the browser; cap it and keep the current
        # selection pinned so it never disappears from the widget.
            select_names = filtered_preset_names[:_constants._PRESET_SELECT_MAX_OPTIONS]
            if (
                current_preset != "Custom"
                and current_preset in filtered_preset_names
                and current_preset not in select_names
            ):
                select_names = [current_preset, *select_names]
            preset_options = ["Custom", *select_names]
            if current_preset not in preset_options:
                st.session_state["driver_preset_name"] = "Custom"
                current_preset = "Custom"

            with bd_tab1:
            # Captions removed to save vertical space
                preset_name = st.selectbox(
                    "Driver preset",
                    preset_options,
                    key="driver_preset_name",
                    on_change=_catalog._on_driver_preset_change,
                    format_func=lambda value: (
                        value if value == "Custom"
                        else _catalog._driver_preset_display_label(value)
                    ),
                )
                if preset_name != "Custom":
                    try:
                        preset_info = _acoustics.driver_preset_info(preset_name)
                        purchase = _catalog._purchase_markdown(preset_info)
                        preset_driver = _acoustics.get_driver_preset(preset_name)
                    except ValueError:
                        purchase = None
                        preset_info = None
                        preset_driver = None
                    if purchase:
                        st.markdown(purchase)
                    if preset_info is not None and preset_driver is not None:
                        manufacturer, part_number = _catalog._driver_preset_identity_fields(
                            preset_name
                        )
                        st.session_state["driver_identity_manufacturer"] = manufacturer
                        st.session_state["driver_identity_part_number"] = part_number
                        identity_col1, identity_col2 = st.columns(2)
                        identity_col1.text_input(
                            "Manufacturer",
                            disabled=True,
                            key="driver_identity_manufacturer",
                        )
                        identity_col2.text_input(
                            "Part number",
                            disabled=True,
                            key="driver_identity_part_number",
                        )
                        nominal = (
                            f"{preset_info.size_in:g} in"
                            if preset_info.size_in is not None
                            else "not published"
                        )
                        effective = np.sqrt(4.0 * preset_driver.sd_cm2 / np.pi) / 2.54
                        st.caption(
                            f"Nominal frame: {nominal} · Sd: {preset_driver.sd_cm2:.1f} cm² "
                            f"· equivalent effective piston: Ø {effective:.2f} in"
                        )
                        with st.expander("Mechanical drawing", expanded=False):
                            _catalog._render_driver_mechanical_drawing(preset_info.mechanical)

                catalog_source_preset = (
                    preset_name if preset_name != "Custom"
                    else str(st.session_state.get("_admin_catalog_source_preset", ""))
                )
                if (
                    _catalog._maintenance_allowed()
                    and _catalog._catalog_path_for_preset(catalog_source_preset)
                ):
                    if st.button(
                        "Save T/S to catalog",
                        key="admin_save_box_design_driver",
                        help=(
                            "Administrator only. Replace the selected source preset's "
                            "catalog T/S values with the current Box Design values."
                        ),
                    ):
                        try:
                            saved_name = _catalog._update_catalog_driver_from_box_design(
                                catalog_source_preset, _state._driver_from_state(),
                            )
                        except ValueError as exc:
                            st.error(f"Could not update catalog T/S: {exc}")
                        else:
                            st.session_state["_pending_driver_preset_name"] = (
                                catalog_source_preset
                            )
                            st.session_state["_admin_catalog_source_preset"] = (
                                catalog_source_preset
                            )
                            st.session_state["_admin_catalog_update_notice"] = (
                                f"Catalog T/S updated for {saved_name}."
                            )
                            st.rerun()
                update_notice = st.session_state.pop(
                    "_admin_catalog_update_notice", ""
                )
                if update_notice:
                    st.success(update_notice)

                c1, c2 = st.columns(2)
                with c1:
                    st.number_input("Fs (Hz)", min_value=1.0, max_value=500.0, step=_finder._step5("driver_fs_hz", 0.1),
                                    key="driver_fs_hz", on_change=_finder._on_driver_param_change)
                    st.number_input("Qts", min_value=0.05, max_value=2.0, step=_finder._step5("driver_qts", 0.001),
                                    format="%.3f", key="driver_qts", on_change=_finder._on_driver_param_change)
                    st.number_input("Re (Ω)", min_value=0.1, max_value=64.0, step=_finder._step5("driver_re_ohm", 0.01),
                                    key="driver_re_ohm", on_change=_finder._on_driver_param_change)
                with c2:
                    st.number_input("Vas (L)", min_value=0.1, max_value=1000.0, step=_finder._step5("driver_vas_l", 0.1),
                                    key="driver_vas_l", on_change=_finder._on_driver_param_change)
                    st.number_input("Qms", min_value=0.051, max_value=50.0, step=_finder._step5("driver_qms", 0.001),
                                    format="%.3f", key="driver_qms", on_change=_finder._on_driver_param_change)
                    st.number_input("Le (mH)", min_value=0.0, max_value=20.0, step=_finder._step5("driver_le_mh", 0.001),
                                    format="%.3f", key="driver_le_mh", on_change=_finder._on_driver_param_change)

                p_col1, p_col2 = st.columns([1, 1], vertical_alignment="bottom")
                with p_col1:
                    st.radio("Piston mode", ["Diameter", "Sd"], horizontal=True, key="driver_sd_mode",
                             on_change=_finder._on_driver_param_change, label_visibility="collapsed")
                with p_col2:
                    if st.session_state.get("driver_sd_mode", "Diameter") == "Diameter":
                        st.number_input("Piston diameter (mm)", min_value=10.0, max_value=1000.0,
                                        step=_finder._step5("driver_diameter_mm", 0.1), key="driver_diameter_mm",
                                        on_change=_finder._on_driver_param_change)
                    else:
                        st.number_input("Sd (cm²)", min_value=1.0, max_value=5000.0, step=_finder._step5("driver_sd_cm2", 1.0),
                                        key="driver_sd_cm2", on_change=_finder._on_driver_param_change)

                if st.session_state.get("driver_sd_mode", "Diameter") == "Diameter":
                    st.caption(f"Sd = {_acoustics.sd_from_diameter(st.session_state.get('driver_diameter_mm', 100)):.1f} cm²")

                c_col1, c_col2 = st.columns([1.2, 1.8], vertical_alignment="center")
                with c_col1:
                    st.checkbox(
                        "Panel air loading",
                        key="driver_panel_air_load",
                        on_change=_finder._on_driver_param_change,
                        help="Adds the air mass coupled to a diaphragm mounted on a finite baffle."
                    )
                with c_col2:
                    if st.session_state.get("driver_panel_air_load", True):
                        st.slider(
                            "Panel coupling",
                            min_value=0.0,
                            max_value=1.0,
                            step=0.01,
                            key="driver_panel_coupling",
                            on_change=_finder._on_driver_param_change,
                            help="Fraction of the low-frequency baffled-piston air-mass increment.",
                            label_visibility="collapsed"
                        )
            
                if st.session_state.get("driver_panel_air_load", True):
                    try:
                        _panel_mass_g, _panel_fs_hz = _acoustics.panel_air_load_metrics(_state._driver_from_state())
                        st.caption(f"Mounted Fs {_panel_fs_hz:.2f} Hz · added air mass {_panel_mass_g:.3f} g")
                    except (KeyError, ValueError):
                        pass

                output_col1, output_col2 = st.columns(2)
                with output_col1:
                    st.number_input("Xmax (mm)", min_value=0.0, max_value=100.0, step=_finder._step5("driver_xmax_mm", 0.1),
                                    key="driver_xmax_mm", on_change=_finder._on_driver_param_change)
                with output_col2:
                    st.number_input("Pe (W)", min_value=0.0, max_value=5000.0, step=_finder._step5("driver_pe_w", 1.0),
                                    key="driver_pe_w", on_change=_finder._on_driver_param_change)

                derived = None
                try:
                    derived = _acoustics.complete_driver(_state._driver_from_state())
                except Exception:
                    pass

                if _finder._show_advanced_controls():
                    with st.expander("Advanced driver parameters", expanded=True):
                        d3, d4 = st.columns(2)
                        with d3:
                            lbl_mms = f"Mms (g) [calc: {derived.mms_kg*1000:.1f}]" if (derived and not st.session_state.get("driver_mms_g")) else "Mms (g)"
                            step_mms = _finder._step5("driver_mms_g", 0.01, derived.mms_kg*1000 if derived else None)
                            st.number_input(lbl_mms, min_value=0.0, max_value=1000.0, step=step_mms,
                                            key="driver_mms_g", on_change=_finder._on_driver_param_change)

                            lbl_bl = f"Bl (T·m) [calc: {derived.bl_tm:.2f}]" if (derived and not st.session_state.get("driver_bl_tm")) else "Bl (T·m)"
                            step_bl = _finder._step5("driver_bl_tm", 0.01, derived.bl_tm if derived else None)
                            st.number_input(lbl_bl, min_value=0.0, max_value=100.0, step=step_bl,
                                            key="driver_bl_tm", on_change=_finder._on_driver_param_change)
                        with d4:
                            lbl_cms = f"Cms (mm/N) [calc: {derived.cms_m_per_n*1000:.3f}]" if (derived and not st.session_state.get("driver_cms_mm_n")) else "Cms (mm/N)"
                            step_cms = _finder._step5("driver_cms_mm_n", 0.001, derived.cms_m_per_n*1000 if derived else None)
                            st.number_input(lbl_cms, min_value=0.0, max_value=100.0, step=step_cms,
                                            format="%.3f", key="driver_cms_mm_n",
                                            on_change=_finder._on_driver_param_change)
                            st.number_input("Le10k (mH)", min_value=0.0, max_value=20.0, step=_finder._step5("driver_le10k_mh", 0.001),
                                            format="%.3f", key="driver_le10k_mh",
                                            on_change=_finder._on_driver_param_change,
                                            help="Voice coil inductance measured at 10 kHz, as "
                                                 "reported alongside Le (1 kHz) on some pro-audio "
                                                 "datasheets. Informational only — not used in the "
                                                 "impedance/response simulation.")

            with bd_tab2:
                _load_set = {st.session_state.get("load_type", "Sealed")}
                _state._render_load_type_buttons(_load_set, single_select=True)
                _state._render_engine_only_topologies_note()
                if _finder._show_advanced_controls():
                    st.selectbox(
                        "Driver configuration",
                        list(_acoustics.DRIVER_CONFIGURATIONS),
                        key="driver_config",
                        on_change=_finder._auto_align_current_driver,
                        help="Identical drivers sharing one enclosure: series, parallel "
                             "or mixed arrays up to eight drivers, or isobaric arrays "
                             "up to 16 total drivers. Each isobaric pair contributes one "
                             "radiating piston and half one driver's Vas.",
                    )
                    if st.session_state.get("driver_config", "Single driver") != "Single driver":
                        try:
                            _composite = _state._driver_from_state()
                            st.caption(
                                f"Composite: Sd {_composite.sd_cm2:.0f} cm² · "
                                f"Vas {_composite.vas_l:.1f} L · "
                                f"Re {_composite.re_ohm:.2f} Ω · Pe {_composite.pe_w:.0f} W"
                            )
                        except Exception:
                            pass
                    
            with bd_tab3:
                st.segmented_control(
                    "Box strategy",
                    _constants._BOX_STRATEGIES,
                    key="box_strategy",
                    on_change=_optimizer._on_box_strategy_change,
                    disabled=st.session_state.get("load_type", "Sealed") == "Infinite baffle",
                    width="stretch",
                    help="One optimizer drives every goal: Max extension favors the "
                         "deepest F3, Balanced trades extension against smoothness "
                         "and practicality, Flattest favors the smoothest passband. "
                         "The box re-applies automatically when the driver, load or "
                         "constraints change. Manual unlocks volumes and tuning for "
                         "direct editing.",
                )
                if not _finder._show_advanced_controls():
                    st.caption(
                        "Simple mode · the optimizer chooses the box. Enable "
                        "Advanced to edit voltage, constraints and port details."
                    )
            # Simulate Inputs
                if _finder._show_advanced_controls():
                    sim_c1, sim_c2 = st.columns(2)
                    with sim_c1:
                        st.number_input(
                            "Voltage (V)", min_value=0.01, max_value=200.0, step=_finder._step5("sim_voltage", 0.01),
                            key="sim_voltage",
                        )
                    with sim_c2:
                        st.number_input(
                            "Series R (Ω)", min_value=0.0, max_value=100.0,
                            step=_finder._step5("sim_series_r_ohm", 0.1), key="sim_series_r_ohm",
                            help="Amplifier output + cable + crossover-coil DCR in series with the "
                                 "driver. Optimizer and driver ranking evaluate at 0 Ω.",
                        )
            
                try:
                    current_ts = _state._driver_from_state()
                    active_load_type = str(st.session_state.get("load_type", "Sealed"))
                    if active_load_type == "DCCAV":
                        current_alignment = _acoustics.suggest_alignment(current_ts)
                    elif active_load_type == "Bass reflex":
                        current_reflex_alignment = _acoustics.suggest_reflex_alignment(current_ts)
                    elif active_load_type == "Bandpass 4th order":
                        current_bandpass4_alignment = _acoustics.suggest_bandpass4_alignment(current_ts)
                    elif active_load_type == "Bandpass 6th order":
                        current_bandpass6_alignment = _acoustics.suggest_bandpass6_alignment(current_ts)
                    elif active_load_type == "Bandpass 8th order":
                        current_bandpass8_alignment = _acoustics.suggest_bandpass8_alignment(current_ts)
                    elif active_load_type == "Sealed":
                        current_sealed_alignment = _acoustics.suggest_sealed_alignment(current_ts)
                    derived = _acoustics.complete_driver(current_ts)
                    panel_added_mass_g, panel_fs_hz = _acoustics.panel_air_load_metrics(current_ts)
                    load_type = st.session_state.get("load_type", "Sealed")
                    box_strategy = str(st.session_state.get("box_strategy", "Max extension"))
                    if (
                        box_strategy in _constants._OPT_OBJECTIVE_LABELS
                        and st.session_state.get("_optimizer_engine_revision", 0)
                        != _constants._OPTIMIZER_ENGINE_REVISION
                    ):
                        try:
                            refreshed = _optimizer._run_box_optimizer(current_ts)
                            _optimizer._apply_optimized_box(refreshed.box)
                            _finder._mark_auto_alignment_synced(current_ts)
                            st.toast("Optimized alignment refreshed with the current physics engine")
                        except ValueError as exc:
                            _optimizer._apply_empirical_box_for(current_ts)
                            st.session_state["opt_last_summary"] = None
                            st.warning(f"Stored optimized box was discarded: {exc}")
                        st.session_state["_optimizer_engine_revision"] = (
                            _constants._OPTIMIZER_ENGINE_REVISION)

                    if load_type != "Infinite baffle" and box_strategy in _constants._OPT_OBJECTIVE_LABELS:
                        st.caption(
                            "The optimizer re-applies this goal automatically when the "
                            "driver, load or constraints change."
                        )
                        auto_box_error = st.session_state.get("_auto_box_error")
                        if auto_box_error:
                            st.warning(
                                "No optimized box satisfies the current goal; the "
                                f"starter box is shown instead. ({auto_box_error})"
                            )
                        if _finder._show_advanced_controls():
                            st.markdown("**Optimization constraints**")
                            st.number_input("Max total volume (L, 0 = off)", min_value=0.0, max_value=2000.0,
                                            step=1.0, key="opt_max_volume_l")
                            st.number_input("Max ripple (dB)", min_value=0.0, max_value=12.0,
                                            step=0.5, key="opt_max_ripple_db")
                            st.number_input("Ripple ceiling (Hz, 0 = off)", min_value=0.0, max_value=500.0,
                                            step=5.0, key="opt_max_ripple_freq_hz",
                                            help="Ignore response variation above this frequency (e.g. 70-100 Hz for subwoofers).")
                            st.number_input("Excursion limit (x Xmax, 0 = off)", min_value=0.0, max_value=3.0,
                                            step=0.05, key="opt_excursion_ratio")
                            st.number_input("Target F3 (Hz, 0 = lowest)", min_value=0.0, max_value=500.0,
                                            step=1.0, key="opt_target_f3_hz")
                            st.number_input("Max group delay (ms, 0 = off)", min_value=0.0, max_value=100.0,
                                            step=1.0, key="opt_max_gd_ms")
                        current_optimizer_summary = _optimizer._current_optimizer_summary(current_ts)
                        if current_optimizer_summary:
                            st.caption(current_optimizer_summary)
                            _optimizer._render_optimizer_alternatives(current_ts)
                        
                except Exception as exc:
                    _runtime.logger.exception("Driver parameter setup failed")
                    current_ts = None
                    current_alignment = None
                    current_reflex_alignment = None
                    current_bandpass4_alignment = None
                    current_bandpass6_alignment = None
                    current_sealed_alignment = None
                    derived = None
                    st.error(f"Driver parameters are invalid - check the T/S values. ({exc})")

                if current_ts is not None:
                    box_edit_disabled = st.session_state.get("box_strategy", "Max extension") != "Manual"
                    if load_type == "Bass reflex":
                        _state._box_number_with_nudge(
                            "Vb box (L)", "reflex_vb_l", min_value=0.05, max_value=1000.0, step=0.01,
                            disabled=box_edit_disabled)
                        with st.expander("Ports", expanded=True):
                            st.selectbox(
                                "Resonator type",
                                _constants._RESONATOR_TYPES,
                                key="reflex_resonator_type",
                                help="Choose an air vent or a passive diaphragm for the same bass-reflex load.",
                            )
                            if _state._reflex_uses_passive_radiator():
                                st.caption("Passive radiator resonator")
                                st.selectbox(
                                    "Passive radiator preset",
                                    ["Custom", *_acoustics.passive_radiator_preset_names()],
                                    key="pr_preset_name",
                                    on_change=_finder._on_pr_preset_change,
                                    help="Loads mechanical PR data; added mass remains editable.",
                                )
                                current_pr_name = str(st.session_state.get("pr_preset_name", "Custom"))
                                if current_pr_name != "Custom" and current_pr_name in _acoustics.passive_radiator_preset_names():
                                    _pr_obj = _acoustics.get_passive_radiator_preset(current_pr_name)
                                    if _pr_obj.url:
                                        st.caption(f"[{_pr_obj.name} on {_pr_obj.source}]({_pr_obj.url})")
                                st.number_input(
                                    "PR area Sp (cm²)", min_value=1.0, max_value=5000.0,
                                    step=1.0, key="pr_sp_cm2")
                                st.number_input(
                                    "PR free-air Fp (Hz)", min_value=1.0, max_value=500.0,
                                    step=0.1, key="pr_fp_hz")
                                st.number_input(
                                    "PR mechanical Qmp", min_value=0.5, max_value=50.0,
                                    step=_finder._step5("pr_qmp", 0.1), key="pr_qmp")
                                st.number_input(
                                    "PR moving mass Mmp (g)", min_value=1.0, max_value=5000.0,
                                    step=1.0, key="pr_mmp_g")
                                st.number_input(
                                    "Added mass (g)", min_value=0.0, max_value=5000.0,
                                    step=1.0, key="pr_added_mass_g",
                                    help="Extra moving mass. Cms stays fixed and Fs decreases accordingly.",
                                )
                                st.number_input(
                                    "PR Xmax (mm, 0 = unknown)", min_value=0.0, max_value=50.0,
                                    step=0.1, key="pr_xmax_mm")
                                active_pr = _state._pr_box_from_state()
                                effective_fp = _acoustics.passive_radiator_effective_fp_hz(active_pr)
                                rho_c2 = 1.18 * 344.0 ** 2
                                cab = (active_pr.vb_l / 1000.0) / rho_c2
                                pr_sp_m2 = active_pr.pr_sp_cm2 / 10_000.0
                                pr_cmp = 1.0 / (
                                    (2 * np.pi * active_pr.pr_fp_hz) ** 2
                                    * (active_pr.pr_mmp_g / 1000.0)
                                )
                                pr_cap = pr_cmp * pr_sp_m2 ** 2
                                f_sys = (
                                    effective_fp * np.sqrt(1.0 + pr_cap / cab)
                                    if cab > 0 else effective_fp
                                )
                                st.caption(
                                    f"PR Fs eff. {effective_fp:.1f} Hz · "
                                    f"box + PR system tuning ~{f_sys:.1f} Hz"
                                )
                                if current_ts is not None and active_pr.vb_l > 0:
                                    target_tuning = (
                                        float(current_reflex_alignment.fb_hz)
                                        if current_reflex_alignment is not None
                                        else float(current_ts.fs_hz)
                                    )
                                    plausible_combos = _acoustics.plausible_passive_radiators(
                                        current_ts, active_pr.vb_l, target_tuning
                                    )
                                    if plausible_combos:
                                        with st.expander(
                                            f"Plausible PR Matches ({len(plausible_combos)})",
                                            expanded=False,
                                        ):
                                            st.caption(
                                                f"Catalog combinations for "
                                                f"{current_ts.sd_cm2:.0f} cm² driver in {active_pr.vb_l:.1f} L (target ~{target_tuning:.1f} Hz)."
                                            )
                                            for c in plausible_combos[:8]:
                                                badge = "Optimal" if c.quality_rating == "Optimal" else ("Good" if c.quality_rating == "Good" else "Acceptable")
                                                pc1, pc2 = st.columns([3.0, 1.2])
                                                with pc1:
                                                    st.markdown(
                                                        f"**{c.pr_count}x {c.preset_name}** ({badge})  \n"
                                                        f"<small>Sp={c.sp_total_cm2:.0f} cm² ({c.area_ratio:.2f}x Sd) · "
                                                        f"Vd={c.vd_ratio:.1f}x · Mass=+{c.added_mass_g:.1f}g/PR</small>",
                                                        unsafe_allow_html=True,
                                                    )
                                                with pc2:
                                                    st.button(
                                                        "Apply",
                                                        key=f"btn_apply_pr_match_{c.preset_name}_{c.pr_count}",
                                                        on_click=_finder._apply_pr_combo,
                                                        args=(c.preset_name, c.pr_count, c.added_mass_g),
                                                        help=f"Tune box to {target_tuning:.1f} Hz using {c.pr_count}x {c.preset_name} (+{c.added_mass_g:.1f}g added mass).",
                                                    )
                            else:
                                _state._box_number_with_nudge(
                                    "Fb tuning (Hz)", "reflex_fb_hz", min_value=1.0,
                                    max_value=1000.0, step=0.1, disabled=box_edit_disabled)
                        if _state._reflex_uses_passive_radiator():
                            with st.expander("Loss factors"):
                                st.number_input(
                                    "Qabs box", min_value=0.2, max_value=500.0,
                                    step=_finder._step5("pr_q_abs", 0.5), key="pr_q_abs")
                                st.number_input(
                                    "Qleak box", min_value=1.0, max_value=10000.0,
                                    step=_finder._step5("pr_q_leak", 10.0), key="pr_q_leak")
                        else:
                            active_reflex_losses = _state._reflex_box_from_state()
                            loss_mode = (
                                "custom" if st.session_state.get("reflex_custom_losses", False)
                                else "normal"
                            )
                            st.caption(
                                f"Reflex losses ({loss_mode}): "
                                f"Qabs {active_reflex_losses.q_abs:.1f} / "
                                f"Qport {active_reflex_losses.q_port:.1f} / "
                                f"Qleak {active_reflex_losses.q_leak:.0f}"
                            )
                            with st.expander("Loss factors"):
                                st.checkbox(
                                    "Use custom reflex losses",
                                    key="reflex_custom_losses",
                                    help="Turn off to use the standard loss model without changing saved values.",
                                )
                                disabled = not st.session_state.get("reflex_custom_losses", False)
                                st.number_input(
                                    "Qabs box", min_value=0.2, max_value=500.0,
                                    step=_finder._step5("reflex_q_abs", 0.5), key="reflex_q_abs", disabled=disabled)
                                st.number_input(
                                    "Qleak box", min_value=1.0, max_value=10000.0,
                                    step=_finder._step5("reflex_q_leak", 10.0), key="reflex_q_leak", disabled=disabled)
                                st.number_input(
                                    "Qport", min_value=0.2, max_value=500.0,
                                    step=_finder._step5("reflex_q_port", 0.5), key="reflex_q_port", disabled=disabled)
                    elif load_type == "Sealed":
                        _state._box_number_with_nudge(
                            "Vb sealed (L)", "sealed_vb_l", min_value=0.05, max_value=100000.0, step=0.01,
                            disabled=box_edit_disabled)
                        if current_ts is not None:
                            fc_hz, qtc = _acoustics.sealed_system_metrics(current_ts, _state._sealed_box_from_state())
                            st.caption(f"Closed-box Fc {fc_hz:.1f} Hz · Qtc {qtc:.3f}")
                        with st.expander("Sealed loss factors"):
                            st.number_input(
                                "Qabs sealed", min_value=0.2, max_value=500.0, step=_finder._step5("sealed_q_abs", 0.5),
                                key="sealed_q_abs")
                            st.number_input(
                                "Qleak sealed", min_value=1.0, max_value=10000.0, step=_finder._step5("sealed_q_leak", 10.0),
                                key="sealed_q_leak")
                    elif load_type == "Bandpass 4th order":
                        b1, b2 = st.columns(2)
                        with b1:
                            _state._box_number_with_nudge(
                                "Vs sealed rear (L)", "bandpass4_vs_l", min_value=0.05,
                                max_value=100000.0, step=0.01, disabled=box_edit_disabled)
                        with b2:
                            _state._box_number_with_nudge(
                                "Vp ported front (L)", "bandpass4_vp_l", min_value=0.05,
                                max_value=100000.0, step=0.01, disabled=box_edit_disabled)
                        _state._box_number_with_nudge(
                            "Fp front tuning (Hz)", "bandpass4_fp_hz", min_value=1.0,
                            max_value=5000.0, step=0.1, disabled=box_edit_disabled)
                        with st.expander("Bandpass loss factors"):
                            l1, l2 = st.columns(2)
                            with l1:
                                st.number_input("Qabs sealed rear", min_value=0.2, max_value=500.0,
                                                step=_finder._step5("bandpass4_q_abs_s", 0.5), key="bandpass4_q_abs_s")
                                st.number_input("Qleak sealed rear", min_value=1.0, max_value=10000.0,
                                                step=_finder._step5("bandpass4_q_leak_s", 10.0), key="bandpass4_q_leak_s")
                            with l2:
                                st.number_input("Qabs ported front", min_value=0.2, max_value=500.0,
                                                step=_finder._step5("bandpass4_q_abs_p", 0.5), key="bandpass4_q_abs_p")
                                st.number_input("Qleak ported front", min_value=1.0, max_value=10000.0,
                                                step=_finder._step5("bandpass4_q_leak_p", 10.0), key="bandpass4_q_leak_p")
                                st.number_input("Qport front", min_value=0.2, max_value=500.0,
                                                step=_finder._step5("bandpass4_q_port", 0.5), key="bandpass4_q_port")
                    elif load_type == "Bandpass 6th order":
                        b1, b2 = st.columns(2)
                        with b1:
                            _state._box_number_with_nudge(
                                "Vr rear ported (L)", "bandpass6_vr_l", min_value=0.05,
                                max_value=100000.0, step=0.01, disabled=box_edit_disabled)
                            _state._box_number_with_nudge(
                                "Fr rear tuning (Hz)", "bandpass6_fr_hz", min_value=1.0,
                                max_value=5000.0, step=0.1, disabled=box_edit_disabled)
                        with b2:
                            _state._box_number_with_nudge(
                                "Vp front ported (L)", "bandpass6_vp_l", min_value=0.05,
                                max_value=100000.0, step=0.01, disabled=box_edit_disabled)
                            _state._box_number_with_nudge(
                                "Fp front tuning (Hz)", "bandpass6_fp_hz", min_value=1.0,
                                max_value=5000.0, step=0.1, disabled=box_edit_disabled)
                        with st.expander("Bandpass loss factors"):
                            l1, l2 = st.columns(2)
                            with l1:
                                st.number_input("Qabs rear", min_value=0.2, max_value=500.0,
                                                step=_finder._step5("bandpass6_q_abs_r", 0.5), key="bandpass6_q_abs_r")
                                st.number_input("Qleak rear", min_value=1.0, max_value=10000.0,
                                                step=_finder._step5("bandpass6_q_leak_r", 10.0), key="bandpass6_q_leak_r")
                                st.number_input("Qport rear", min_value=0.2, max_value=500.0,
                                                step=_finder._step5("bandpass6_q_port_r", 0.5), key="bandpass6_q_port_r")
                            with l2:
                                st.number_input("Qabs front", min_value=0.2, max_value=500.0,
                                                step=_finder._step5("bandpass6_q_abs_p", 0.5), key="bandpass6_q_abs_p")
                                st.number_input("Qleak front", min_value=1.0, max_value=10000.0,
                                                step=_finder._step5("bandpass6_q_leak_p", 10.0), key="bandpass6_q_leak_p")
                                st.number_input("Qport front", min_value=0.2, max_value=500.0,
                                                step=_finder._step5("bandpass6_q_port_p", 0.5), key="bandpass6_q_port_p")
                    elif load_type == "Bandpass 8th order":
                        b1, b2, b3 = st.columns(3)
                        with b1:
                            _state._box_number_with_nudge(
                                "V1 front (L)", "bp8_v1_l", min_value=0.05,
                                max_value=100000.0, step=0.01, disabled=box_edit_disabled)
                            _state._box_number_with_nudge(
                                "F1 tuning (Hz)", "bp8_f1_hz", min_value=1.0,
                                max_value=5000.0, step=0.1, disabled=box_edit_disabled)
                        with b2:
                            _state._box_number_with_nudge(
                                "V2 rear (L)", "bp8_v2_l", min_value=0.05,
                                max_value=100000.0, step=0.01, disabled=box_edit_disabled)
                            _state._box_number_with_nudge(
                                "F2 tuning (Hz)", "bp8_f2_hz", min_value=1.0,
                                max_value=5000.0, step=0.1, disabled=box_edit_disabled)
                        with b3:
                            _state._box_number_with_nudge(
                                "V3 plenum (L)", "bp8_v3_l", min_value=0.05,
                                max_value=100000.0, step=0.01, disabled=box_edit_disabled)
                            _state._box_number_with_nudge(
                                "F3 tuning (Hz)", "bp8_f3_hz", min_value=1.0,
                                max_value=5000.0, step=0.1, disabled=box_edit_disabled)
                        with st.expander("Bandpass loss factors"):
                            l1, l2, l3 = st.columns(3)
                            with l1:
                                st.number_input("Qabs 1", min_value=0.2, max_value=500.0,
                                                step=_finder._step5("bp8_q_abs_1", 0.5), key="bp8_q_abs_1")
                                st.number_input("Qleak 1", min_value=1.0, max_value=10000.0,
                                                step=_finder._step5("bp8_q_leak_1", 10.0), key="bp8_q_leak_1")
                                st.number_input("Qport 1", min_value=0.2, max_value=500.0,
                                                step=_finder._step5("bp8_q_port_1", 0.5), key="bp8_q_port_1")
                            with l2:
                                st.number_input("Qabs 2", min_value=0.2, max_value=500.0,
                                                step=_finder._step5("bp8_q_abs_2", 0.5), key="bp8_q_abs_2")
                                st.number_input("Qleak 2", min_value=1.0, max_value=10000.0,
                                                step=_finder._step5("bp8_q_leak_2", 10.0), key="bp8_q_leak_2")
                                st.number_input("Qport 2", min_value=0.2, max_value=500.0,
                                                step=_finder._step5("bp8_q_port_2", 0.5), key="bp8_q_port_2")
                            with l3:
                                st.number_input("Qabs 3", min_value=0.2, max_value=500.0,
                                                step=_finder._step5("bp8_q_abs_3", 0.5), key="bp8_q_abs_3")
                                st.number_input("Qleak 3", min_value=1.0, max_value=10000.0,
                                                step=_finder._step5("bp8_q_leak_3", 10.0), key="bp8_q_leak_3")
                                st.number_input("Qport 3", min_value=0.2, max_value=500.0,
                                                step=_finder._step5("bp8_q_port_3", 0.5), key="bp8_q_port_3")
                    elif load_type == "Infinite baffle":
                        st.caption("No box controls: the rear wave is assumed to be fully isolated by an infinite partition.")
                    else:
                        b1, b2 = st.columns(2)
                        with b1:
                            _state._box_number_with_nudge(
                                "Vh upper (L)", "box_vh_l", min_value=0.05, max_value=1000.0, step=0.01,
                                disabled=box_edit_disabled)
                            _state._box_number_with_nudge(
                                "fh upper (Hz)", "box_fh_hz", min_value=1.0, max_value=1000.0, step=0.1,
                                disabled=box_edit_disabled)
                        with b2:
                            _state._box_number_with_nudge(
                                "Vl lower (L)", "box_vl_l", min_value=0.05, max_value=1000.0, step=0.01,
                                disabled=box_edit_disabled)
                            _state._box_number_with_nudge(
                                "fl lower (Hz)", "box_fl_hz", min_value=1.0, max_value=1000.0, step=0.1,
                                disabled=box_edit_disabled)

                        with st.expander("Loss factors"):
                            l1, l2 = st.columns(2)
                            with l1:
                                st.number_input("Qabs upper", min_value=0.2, max_value=500.0, step=_finder._step5("loss_q_abs_h", 0.5), key="loss_q_abs_h")
                                st.number_input("Qleak upper", min_value=1.0, max_value=10000.0, step=_finder._step5("loss_q_leak_h", 10.0), key="loss_q_leak_h")
                                st.number_input("Qport upper", min_value=0.2, max_value=500.0, step=_finder._step5("loss_q_port_h", 0.5), key="loss_q_port_h")
                            with l2:
                                st.number_input("Qabs lower", min_value=0.2, max_value=500.0, step=_finder._step5("loss_q_abs_l", 0.5), key="loss_q_abs_l")
                                st.number_input("Qleak lower", min_value=1.0, max_value=10000.0, step=_finder._step5("loss_q_leak_l", 10.0), key="loss_q_leak_l")
                                st.number_input("Qport lower", min_value=0.2, max_value=500.0, step=_finder._step5("loss_q_port_l", 0.5), key="loss_q_port_l")

                    if load_type != "Infinite baffle" and box_edit_disabled:
                        st.caption("Switch Box strategy to Manual to edit volumes and tuning directly.")

        if not (_explore_requested or _public_project_requested):
            _catalog._render_catalog_crawl_report()

            if _catalog._maintenance_allowed():
                st.markdown("---")
                with st.expander("Admin Tools", expanded=False):
                    if st.button(
                        "Catalog Maintenance",
                        key="btn_admin_catalog_maint",
                        use_container_width=True,
                    ):
                        for k in ("explore", "p", "embed", "admin_users"):
                            st.query_params.pop(k, None)
                        st.query_params["maintenance"] = "1"
                        st.session_state["workspace_mode"] = "Catalog Maintenance"
                        st.rerun()
                    if st.button(
                        "User Management",
                        key="btn_admin_user_mgmt",
                        use_container_width=True,
                    ):
                        for k in ("explore", "p", "embed", "maintenance"):
                            st.query_params.pop(k, None)
                        st.query_params["admin_users"] = "1"
                        st.session_state["workspace_mode"] = "User Management"
                        st.rerun()

        if (
            not (_explore_requested or _public_project_requested)
            and workspace_mode in ("Bass Match", "Box Design")
        ):
            st.divider()
            st.toggle(
                "Advanced mode",
                key="ui_show_advanced",
                help="Show expert controls: search profile, evaluation grid and "
                     "driver T/S overrides. Off keeps the guided workflow.",
            )
            if _finder._show_advanced_controls():
                st.caption(
                    "Advanced mode · expert controls are open in the active tabs."
                )
            else:
                st.caption(
                    "Simple mode · guided scenario, load, volume and goal. Enable "
                    "Advanced for full controls."
                )
    if _public_project_requested:
        if _embed_mode_requested:
            _projects._render_embed_project_widget(_public_project_requested)
        else:
            _projects._render_public_project_page(_public_project_requested)
        st.stop()
    if _explore_requested:
        _projects._render_explore_projects_directory()
        st.stop()
    _maintenance_requested = str(st.query_params.get("maintenance", "")) == "1"
    if _maintenance_requested:
        _catalog._render_catalog_maintenance()
        st.stop()
    _admin_users_requested = str(st.query_params.get("admin_users", "")) == "1"
    if _admin_users_requested:
        _projects._render_user_management()
        st.stop()
    if workspace_mode == "Catalog Maintenance":
        _catalog._render_catalog_maintenance()
        st.stop()
    if workspace_mode == "User Management":
        _projects._render_user_management()
        st.stop()
    if workspace_mode == "Manage Projects":
        _projects._render_manage_projects_workspace()
        st.stop()
    if (
        workspace_mode in ("Bass Match", "Box Design")
        and not (_explore_requested or _public_project_requested)
    ):
        _projects._render_main_account_header()
    if workspace_mode == "Bass Match":
        _finder._render_find_driver_workspace(filtered_preset_names)
        st.stop()
    try:
        if current_ts is None:
            raise ValueError("Driver parameters are incomplete")
        if st.session_state["sim_f_max"] <= st.session_state["sim_f_min"]:
            raise ValueError("F max must be greater than F min")
        load_type = st.session_state["load_type"]
        is_reflex_load = load_type == "Bass reflex"
        is_pr = is_reflex_load and _state._reflex_uses_passive_radiator()
        is_reflex = is_reflex_load and not is_pr
        is_bandpass4 = load_type == "Bandpass 4th order"
        is_bandpass6 = load_type == "Bandpass 6th order"
        is_bandpass8 = load_type == "Bandpass 8th order"
        is_sealed = load_type == "Sealed"
        is_infinite_baffle = load_type == "Infinite baffle"
        chart_sig = _analysis._chart_signature()
        if is_pr:
            box = _state._pr_box_from_state()
        elif is_reflex:
            box = _state._reflex_box_from_state()
        elif is_bandpass4:
            box = _state._bandpass4_box_from_state()
        elif is_bandpass6:
            box = _state._bandpass6_box_from_state()
        elif is_bandpass8:
            box = _state._bandpass8_box_from_state()
        elif is_sealed:
            box = _state._sealed_box_from_state()
        elif is_infinite_baffle:
            box = None
        else:
            box = _state._box_from_state()
        sim_f_min = float(st.session_state["sim_f_min"])
        sim_f_max = float(st.session_state["sim_f_max"])
        sim_points = int(st.session_state["sim_points"])
        sim_voltage = float(st.session_state["sim_voltage"])
        sim_series_r = float(st.session_state.get("sim_series_r_ohm", 0.0))
        engine_revision = _analysis._simulation_engine_revision()
        result, metrics, thresholds, z_peak_freqs = _analysis._simulate_design_cached(
            engine_revision,
            current_ts,
            load_type,
            box,
            sim_f_min,
            sim_f_max,
            sim_points,
            sim_voltage,
            sim_series_r,
        )
        freq = result.frequency_hz
        simulation_signature = _analysis._design_simulation_signature(
            engine_revision,
            current_ts,
            load_type,
            box,
            sim_f_min,
            sim_f_max,
            sim_points,
            sim_voltage,
            sim_series_r,
            float(st.session_state.get("opt_max_ripple_freq_hz", 0.0)),
        )
        model_warnings = [] if load_type != "DCCAV" else (
            _acoustics.alignment_diagnostics(current_ts, box)
            + _acoustics.response_sanity_warnings(current_ts, box, thresholds)
        )
        if is_bandpass4:
            model_warnings.extend(_acoustics.bandpass4_diagnostics(current_ts, box, result))
        if is_bandpass6:
            model_warnings.extend(_acoustics.bandpass6_diagnostics(current_ts, box, result))
        if is_reflex and len(z_peak_freqs) < 2:
            model_warnings.append(
                "Bass reflex should show two impedance peaks in the simulated range; "
                f"currently found {len(z_peak_freqs)}. "
                f"Check F min/F max, Vb, Fb and reflex losses "
                f"(Qabs={box.q_abs:.1f}, Qport={box.q_port:.1f}, Qleak={box.q_leak:.0f}). "
                "Low Qabs/Qport values overdamp the vent resonance; turn off custom reflex "
                "losses for a normal starter alignment."
            )
        port_geometry_rows = []
        if is_reflex:
            vent_d_cm = float(st.session_state.get("reflex_port_d_cm", 0.0))
            if vent_d_cm > 0.0:
                port_geometry_rows.append(_optimizer._port_geometry_row(
                    "Vent (External)", vent_d_cm, box.vb_l, box.fb_hz, 1.43, result, "lower"))
        elif is_pr:
            pr_box = box
            pr_sp_cm2 = pr_box.pr_sp_cm2
            pr_xmax = pr_box.pr_xmax_mm
            velocity = _acoustics.port_air_velocity_ms(result, pr_sp_cm2, "lower")
            peak_idx = int(np.nanargmax(velocity))
            velocity_mol = _acoustics.port_air_velocity_ms(result, pr_sp_cm2, "lower", at_mol=True)
            peak_mol_idx = int(np.nanargmax(velocity_mol))
            pr_exc_peak = float(np.nanmax(np.abs(result.port_l_velocity) / (2 * np.pi * result.frequency_hz * pr_sp_cm2 / 10_000.0))) * 1000.0
            port_geometry_rows.append({
                "Port": "Passive radiator (External)",
                "Diameter cm": float(np.sqrt(4 * pr_sp_cm2 / np.pi)),
                "Length cm": float("nan"),
                "Peak m/s": float(velocity[peak_idx]),
                "Peak m/s (MOL)": float(velocity_mol[peak_mol_idx]),
                "Peak at Hz": float(result.frequency_hz[peak_idx]),
                "_volume_l": float(pr_box.vb_l),
                "_fb_hz": float(_acoustics.passive_radiator_effective_fp_hz(pr_box)),
                "_end_correction": 0.0,
                "_is_pr": True,
            })
            if pr_xmax > 0 and pr_exc_peak > pr_xmax:
                model_warnings.append(
                    f"Passive radiator excursion {pr_exc_peak:.1f} mm exceeds "
                    f"rated Xmax {pr_xmax:.1f} mm at {sim_voltage:.2f} V"
                )
        elif is_bandpass4:
            vent_d_cm = float(st.session_state.get("bandpass4_port_d_cm", 0.0))
            if vent_d_cm > 0.0:
                port_geometry_rows.append(_optimizer._port_geometry_row(
                    "Front vent (External)", vent_d_cm, box.vp_l, box.fp_hz, 1.43, result, "lower"))
        elif is_bandpass6:
            rear_d_cm = float(st.session_state.get("bandpass6_port_d_r_cm", 0.0))
            front_d_cm = float(st.session_state.get("bandpass6_port_d_p_cm", 0.0))
            if rear_d_cm > 0.0:
                port_geometry_rows.append(_optimizer._port_geometry_row(
                    "Rear vent (External)", rear_d_cm, box.vr_l, box.fr_hz, 1.43, result, "upper"))
            if front_d_cm > 0.0:
                port_geometry_rows.append(_optimizer._port_geometry_row(
                    "Front vent (External)", front_d_cm, box.vp_l, box.fp_hz, 1.43, result, "lower"))
        elif is_bandpass8:
            p1_d_cm = float(st.session_state.get("bp8_dp1_cm", 0.0))
            p2_d_cm = float(st.session_state.get("bp8_dp2_cm", 0.0))
            p3_d_cm = float(st.session_state.get("bp8_dp3_cm", 0.0))
            if p1_d_cm > 0.0:
                port_geometry_rows.append(_optimizer._port_geometry_row(
                    "Port 1 (Internal -> C3)", p1_d_cm, box.v1_l, box.f1_hz, 1.43, result, "lower"))
            if p2_d_cm > 0.0:
                port_geometry_rows.append(_optimizer._port_geometry_row(
                    "Port 2 (Internal -> C3)", p2_d_cm, box.v2_l, box.f2_hz, 1.43, result, "lower"))
            if p3_d_cm > 0.0:
                port_geometry_rows.append(_optimizer._port_geometry_row(
                    "Port 3 (External radiating)", p3_d_cm, box.v3_l, box.f3_hz, 1.43, result, "upper"))
        elif load_type == "DCCAV":
            upper_d_cm = float(st.session_state.get("box_port_d_h_cm", 0.0))
            lower_d_cm = float(st.session_state.get("box_port_d_l_cm", 0.0))
            if upper_d_cm > 0.0:
                port_geometry_rows.append(_optimizer._port_geometry_row(
                    "Upper port (Internal inter-chamber)", upper_d_cm, box.vh_l, box.fh_hz, 1.64, result, "upper"))
            if lower_d_cm > 0.0:
                port_geometry_rows.append(_optimizer._port_geometry_row(
                    "Lower port (External radiating)", lower_d_cm, box.vl_l, box.fl_hz, 1.43, result, "lower"))
        for row in port_geometry_rows:
            is_pr_row = row.get("_is_pr", False)
            if not is_pr_row and row["Length cm"] <= 0.0:
                max_hz = _acoustics.port_max_tuning_hz(
                    row["_volume_l"], row["Diameter cm"], row["_end_correction"])
                min_d_cm = _acoustics.port_min_diameter_cm(
                    row["_volume_l"], row["_fb_hz"], row["_end_correction"])
                model_warnings.append(
                    f"{row['Port']}: a {row['Diameter cm']:.1f} cm opening in {row['_volume_l']:.1f} L "
                    f"tunes at most to ~{max_hz:.0f} Hz even with zero duct length; reaching "
                    f"{row['_fb_hz']:.1f} Hz needs a diameter of at least {min_d_cm:.1f} cm."
                )
            if row["Peak m/s"] > _acoustics.PORT_VELOCITY_GUIDELINE_MS:
                model_warnings.append(
                    f"{row['Port']} air speed peaks at {row['Peak m/s']:.1f} m/s near "
                    f"{row['Peak at Hz']:.0f} Hz at {float(st.session_state['sim_voltage']):.2f} V - above "
                    f"the ~{_acoustics.PORT_VELOCITY_GUIDELINE_MS:.0f} m/s (5% of c) chuffing guideline; "
                    "enlarge the port or reduce drive level."
                )
            if not is_pr_row:
                golden_cm = _acoustics.port_displacement_min_diameter_cm(
                    current_ts, row["_fb_hz"])
                if 0.0 < row["Diameter cm"] < golden_cm:
                    model_warnings.append(
                        f"{row['Port']}: {row['Diameter cm']:.1f} cm is below the minimum-area "
                        f"golden rule for this driver's displacement (needs ≥ {golden_cm:.1f} cm "
                        f"at {row['_fb_hz']:.1f} Hz); expect compression at rated excursion "
                        "regardless of the simulated drive level."
                    )
            if not is_pr_row and row["Length cm"] > 0.0:
                duct_fraction = _acoustics.port_volume_fraction(
                    row["_volume_l"], row["_fb_hz"], row["Diameter cm"],
                    row["_end_correction"])
                if duct_fraction > _acoustics.PORT_MAX_VOLUME_FRACTION:
                    duct_l = duct_fraction * row["_volume_l"]
                    model_warnings.append(
                        f"{row['Port']}: the {row['Diameter cm']:.1f} × {row['Length cm']:.1f} cm "
                        f"duct occupies {duct_l:.2f} L = {duct_fraction:.0%} of the "
                        f"{row['_volume_l']:.1f} L chamber (reflex directive ≤ "
                        f"{_acoustics.PORT_MAX_VOLUME_FRACTION:.0%}); the box is too small for "
                        "this tuning and diameter - enlarge the chamber, raise the tuning "
                        "or reduce the port."
                    )
                pipe_hz = _acoustics.port_pipe_resonance_hz(row["Length cm"])
                if pipe_hz < _acoustics.PORT_PIPE_RESONANCE_GUARD * row["_fb_hz"]:
                    model_warnings.append(
                        f"{row['Port']}: the {row['Length cm']:.1f} cm duct has its first "
                        f"pipe resonance at ~{pipe_hz:.0f} Hz, inside the working band "
                        f"(< {_acoustics.PORT_PIPE_RESONANCE_GUARD:.0f}× the {row['_fb_hz']:.1f} Hz "
                        "tuning); shorten the duct with a smaller diameter or higher tuning."
                    )
                max_straight_cm = _acoustics.port_max_straight_length_cm(row["_volume_l"])
                if row["Length cm"] > max_straight_cm:
                    model_warnings.append(
                        f"{row['Port']}: the {row['Length cm']:.1f} cm duct is longer than a "
                        f"{row['_volume_l']:.1f} L box (~{max_straight_cm:.0f} cm on a side) can "
                        "plausibly hold in a straight run; it needs an L-shaped/slot fold "
                        "(not modeled here), a bigger box, or a higher tuning."
                    )

        comparison_tabs = _analysis._update_active_design_comparison(
            load_type,
            box,
            result,
            simulation_signature,
        )
        _analysis._render_editable_design_tabs(
            comparison_tabs,
            load_type,
            box,
            result,
        )

        _analysis._render_design_analysis_tabs(
            current_ts, load_type, box, result, thresholds, freq,
            sim_voltage, sim_series_r, port_geometry_rows,
            is_pr, is_sealed, is_infinite_baffle, chart_sig,
        )
        active_load_image = _constants._LOAD_TYPE_IMAGES.get(load_type)
        with st.container(key="active_load_summary"):
        # Left: active load schematic, Right: Dense info
            if active_load_image is not None and active_load_image.exists():
                img_col, data_col = st.columns([0.65, 5], vertical_alignment="center")
                with img_col:
                    st.image(str(active_load_image), width="stretch")
            else:
                data_col = st.container()
        
            with data_col:
                st.markdown(
                    """
                <style>
                .st-key-active_load_summary [data-testid="stMetricValue"] {
                    font-size: 1.15rem !important;
                }
                .st-key-active_load_summary [data-testid="stMetricLabel"] {
                    font-size: 0.7rem !important;
                    margin-bottom: 0.05rem !important;
                }
                .st-key-active_load_summary [data-testid="stVerticalBlock"] {
                    gap: 0rem !important;
                }
                .st-key-active_load_summary [data-testid="stMetric"] {
                    padding-bottom: 0 !important;
                }
                </style>
                """,
                    unsafe_allow_html=True
                )
            
            # Calculate Forge Score (0-100)
                score_val = 100
                warning_deductions = len(model_warnings) * 12
                score_val -= warning_deductions
                for row in port_geometry_rows:
                    if row.get("Peak m/s", 0.0) > _acoustics.PORT_VELOCITY_GUIDELINE_MS:
                        score_val -= 15
                    if not row.get("_is_pr", False):
                        golden_cm = _acoustics.port_displacement_min_diameter_cm(current_ts, row["_fb_hz"])
                        if 0.0 < row["Diameter cm"] < golden_cm:
                            score_val -= 10
                        if row["Length cm"] <= 0.0:
                            score_val -= 20
                if current_ts and current_ts.xmax_mm and metrics["max_excursion_mm"] > current_ts.xmax_mm:
                    score_val -= 25
                score_val = max(10, min(100, score_val))

                flat_metrics = [
                    ("F3", _optimizer._fmt_hz(thresholds[3])),
                    ("Peak LF SPL", _optimizer._fmt_db(metrics["max_spl_db"])),
                    ("Max excursion", f"{metrics['max_excursion_mm']:.2f} mm"),
                    ("Min impedance", f"{metrics['min_impedance_ohm']:.2f} Ω"),
                ]
                if not is_infinite_baffle:
                    if load_type == "Bandpass 4th order":
                        flat_metrics.append(("Box volume", f"{box.vs_l + box.vp_l:.1f} L"))
                    elif load_type == "Bandpass 6th order":
                        flat_metrics.append(("Box volume", f"{box.vr_l + box.vp_l:.1f} L"))
                    elif load_type == "Bandpass 8th order":
                        flat_metrics.append(("Box volume", f"{box.v1_l + box.v2_l + box.v3_l:.1f} L"))
                    elif load_type == "DCCAV":
                        flat_metrics.append(("Box volume", f"{box.vh_l + box.vl_l:.1f} L"))
                    else:
                        flat_metrics.append(("Box volume", f"{box.vb_l:.1f} L"))
                flat_metrics.append(("Forge Score", f"{score_val}/100"))

                if not is_infinite_baffle:
                    ports = {row["Port"]: row for row in port_geometry_rows if not row.get("_is_pr", False)}
                
                    def _add_port(lbl):
                    # Match exact label or key starting with lbl
                        matching = [r for name, r in ports.items() if name == lbl or name.startswith(lbl)]
                        if matching:
                            pr = matching[0]
                            flat_metrics.extend([
                                (f"{lbl} tuning", f"{pr['_fb_hz']:.1f} Hz"),
                                (f"{lbl} size", f"Ø{pr['Diameter cm']:.1f}x{pr['Length cm']:.1f}")
                            ])

                    if load_type == "Bandpass 4th order":
                        flat_metrics.append(("Closed vol (Vs)", f"{box.vs_l:.1f} L"))
                        flat_metrics.append(("Ported vol (Vp)", f"{box.vp_l:.1f} L"))
                        _add_port("Front vent")
                    elif load_type == "Bandpass 6th order":
                        flat_metrics.append(("Rear vol (Vr)", f"{box.vr_l:.1f} L"))
                        _add_port("Rear vent")
                        flat_metrics.append(("Front vol (Vp)", f"{box.vp_l:.1f} L"))
                        _add_port("Front vent")
                    elif load_type == "Bandpass 8th order":
                        flat_metrics.append(("Front vol (V1)", f"{box.v1_l:.1f} L"))
                        _add_port("Port 1")
                        flat_metrics.append(("Rear vol (V2)", f"{box.v2_l:.1f} L"))
                        _add_port("Port 2")
                        flat_metrics.append(("Plenum vol (V3)", f"{box.v3_l:.1f} L"))
                        _add_port("Port 3")
                    elif load_type == "DCCAV":
                        flat_metrics.append(("High vol (Vh)", f"{box.vh_l:.1f} L"))
                        _add_port("Upper port")
                        flat_metrics.append(("Low vol (Vl)", f"{box.vl_l:.1f} L"))
                        _add_port("Lower port")
                    else:
                        _add_port("Vent")

                for i in range(0, len(flat_metrics), 6):
                    cols = st.columns(6)
                    for j, metric in enumerate(flat_metrics[i:i+6]):
                        metric_help = (
                            "Heuristic 0-100 design-health indicator, not a physical "
                            "performance metric. It starts at 100 and deducts points "
                            "for model warnings, excursion violations and impractical "
                            "port geometry; it is never used as the default ranking "
                            "criterion. Read it together with F3, excursion, MOL and "
                            "impedance."
                            if metric[0] == "Forge Score"
                            else None
                        )
                        cols[j].metric(metric[0], metric[1], help=metric_help)

                st.caption(
                    "Forge Score is a heuristic design-health indicator: comparisons "
                    "and ranking always use the physical metrics (F3, MOL, excursion, "
                    "impedance)."
                )

            # Performance Badges
                badges = []
                if not is_infinite_baffle and not is_sealed:
                    has_port_issues = any(
                        "chuffing" in w.lower() or "minimum-area" in w.lower() or "tunes at most" in w.lower()
                        for w in model_warnings
                    )
                    if len(port_geometry_rows) > 0 and not has_port_issues:
                        badges.append((
                            "Port speed within guideline",
                            "rgba(46, 204, 113, 0.08)",
                            "rgba(46, 204, 113, 0.3)",
                            "#2ecc71"
                        ))
            
                f3_val = thresholds[3]
                if not np.isnan(f3_val) and not is_infinite_baffle:
                    if is_reflex or is_sealed or is_pr:
                        vtot_l = box.vb_l
                    elif is_bandpass4:
                        vtot_l = box.vs_l + box.vp_l
                    elif is_bandpass6:
                        vtot_l = box.vr_l + box.vp_l
                    elif is_bandpass8:
                        vtot_l = box.v1_l + box.v2_l + box.v3_l
                    else:
                        vtot_l = box.vh_l + box.vl_l
                
                    if f3_val < 30.0 and vtot_l < 35.0:
                        badges.append((
                            "F3 below 30 Hz",
                            "rgba(0, 110, 219, 0.08)",
                            "rgba(0, 110, 219, 0.3)",
                            "#006edb"
                        ))
                    elif f3_val < 40.0 and vtot_l < 50.0:
                        badges.append((
                            "F3 below 40 Hz",
                            "rgba(0, 110, 219, 0.08)",
                            "rgba(0, 110, 219, 0.3)",
                            "#006edb"
                        ))
                    elif f3_val < 50.0:
                        badges.append((
                            "F3 below 50 Hz",
                            "rgba(0, 110, 219, 0.08)",
                            "rgba(0, 110, 219, 0.3)",
                            "#006edb"
                        ))

                if not any("sanity" in w.lower() or "warning" in w.lower() for w in model_warnings):
                    badges.append((
                        "Model checks passed",
                        "rgba(26, 188, 156, 0.08)",
                        "rgba(26, 188, 156, 0.3)",
                        "#1abc9c"
                    ))

                if badges:
                    badge_html = " ".join([
                        f'<span style="display: inline-block; background-color: {bg}; '
                        f'border: 1px solid {border}; border-radius: 0.35rem; '
                        f'padding: 0.15rem 0.45rem; margin-right: 0.35rem; font-size: 0.72rem; '
                        f'font-weight: 600; color: {color};">{text}</span>'
                        for text, bg, border, color in badges
                    ])
                    st.markdown(f'<div style="margin-top: 0.45rem; padding-bottom: 0.45rem; margin-bottom: 0.2rem;">{badge_html}</div>', unsafe_allow_html=True)

                if model_warnings:
                    for warning in model_warnings:
                        st.warning(warning)

    # Warnings are now rendered inside data_col compactly

        exp_c1, exp_c2 = st.columns(2)
        with exp_c1:
            with st.expander("Design details"):
                s1, s2, s3 = st.columns(3)
                s1.metric("F6", _optimizer._fmt_hz(thresholds[6]))
                s2.metric("F10", _optimizer._fmt_hz(thresholds[10]))
                s3.metric("Z peaks", ", ".join(f"{f:.0f}" for f in z_peak_freqs[:3]) or "n/a")
                if is_reflex:
                    a1, a2, a3, a4 = st.columns(4)
                    a1.metric("Vb (active)", f"{box.vb_l:.2f} L")
                    a2.metric("Fb (active)", f"{box.fb_hz:.1f} Hz")
                    a3.metric("Eq sealed Fc", f"{_acoustics.equivalent_sealed_fc_hz(current_ts, box):.1f} Hz")
                    if current_reflex_alignment is not None:
                        a4.metric("Starter Vb=Vas", f"{current_reflex_alignment.vb_l:.2f} L")
                elif is_pr:
                    a1, a2, a3, a4 = st.columns(4)
                    a1.metric("Vb (active)", f"{box.vb_l:.2f} L")
                    a2.metric(
                        "PR Fp",
                        f"{_acoustics.passive_radiator_effective_fp_hz(box):.1f} Hz",
                    )
                    a3.metric("PR Sp", f"{box.pr_sp_cm2:.0f} cm²")
                    a4.metric("PR Qmp", f"{box.pr_qmp:.1f}")
                elif is_bandpass4:
                    a1, a2, a3, a4, a5 = st.columns(5)
                    a1.metric("Vs sealed (active)", f"{box.vs_l:.2f} L")
                    a2.metric("Vp ported (active)", f"{box.vp_l:.2f} L")
                    a3.metric("Fp (active)", f"{box.fp_hz:.1f} Hz")
                    a4.metric("Vtot (active)", f"{box.vs_l + box.vp_l:.2f} L")
                    if current_bandpass4_alignment is not None:
                        a5.metric(
                            "Starter Vtot",
                            f"{current_bandpass4_alignment.vs_l + current_bandpass4_alignment.vp_l:.2f} L",
                        )
                elif is_bandpass6:
                    a1, a2, a3, a4, a5, a6, a7 = st.columns(7)
                    a1.metric("Vr rear (active)", f"{box.vr_l:.2f} L")
                    a2.metric("Fr rear (active)", f"{box.fr_hz:.1f} Hz")
                    a3.metric("Vp front (active)", f"{box.vp_l:.2f} L")
                    a4.metric("Fp front (active)", f"{box.fp_hz:.1f} Hz")
                    a5.metric("Vtot (active)", f"{box.vr_l + box.vp_l:.2f} L")
                    a6.metric("Eq sealed Fc", f"{_acoustics.equivalent_sealed_fc_hz(current_ts, box):.1f} Hz")
                    if current_bandpass6_alignment is not None:
                        a7.metric(
                            "Starter Vtot",
                            f"{current_bandpass6_alignment.vr_l + current_bandpass6_alignment.vp_l:.2f} L",
                        )
                elif is_sealed:
                    fc_hz, qtc = _acoustics.sealed_system_metrics(current_ts, box)
                    a1, a2, a3, a4 = st.columns(4)
                    a1.metric("Vb sealed (active)", f"{box.vb_l:.2f} L")
                    a2.metric("Fc (active)", f"{fc_hz:.1f} Hz")
                    a3.metric("Qtc (active)", f"{qtc:.3f}")
                    if current_sealed_alignment is not None:
                        a4.metric("Starter Vb", f"{current_sealed_alignment.vb_l:.2f} L")
                elif is_infinite_baffle:
                    a1, a2, a3 = st.columns(3)
                    a1.metric(
                        "Mounted Fs",
                        f"{_acoustics.panel_loaded_fs_hz(current_ts):.1f} Hz",
                        help=f"Free-air Fs: {current_ts.fs_hz:.1f} Hz",
                    )
                    a2.metric("Infinite baffle Qts", f"{current_ts.qts:.3f}")
                    a3.metric("Rear radiation", "Isolated")
                elif is_bandpass8:
                    a1, a2, a3, a4, a5, a6, a7 = st.columns(7)
                    a1.metric("V1 front", f"{box.v1_l:.2f} L")
                    a2.metric("F1", f"{box.f1_hz:.1f} Hz")
                    a3.metric("V2 rear", f"{box.v2_l:.2f} L")
                    a4.metric("F2", f"{box.f2_hz:.1f} Hz")
                    a5.metric("V3 plenum", f"{box.v3_l:.2f} L")
                    a6.metric("F3", f"{box.f3_hz:.1f} Hz")
                    a7.metric("Vtot (active)", f"{box.v1_l + box.v2_l + box.v3_l:.2f} L")
                else:
                    a1, a2, a3, a4, a5, a6, a7 = st.columns(7)
                    a1.metric("Vh (active)", f"{box.vh_l:.2f} L")
                    a2.metric("fh (active)", f"{box.fh_hz:.1f} Hz")
                    a3.metric("Vl (active)", f"{box.vl_l:.2f} L")
                    a4.metric("fl (active)", f"{box.fl_hz:.1f} Hz")
                    a5.metric("Vtot (active)", f"{box.vh_l + box.vl_l:.2f} L")
                    a6.metric("Eq sealed Fc", f"{_acoustics.equivalent_sealed_fc_hz(current_ts, box):.1f} Hz")
                    if current_alignment is not None:
                        a7.metric("Article Vtot", f"{current_alignment.vh_l + current_alignment.vl_l:.2f} L")


        with exp_c2:
            if derived is not None:
                with st.expander("Driver details"):
                    d1, d2, d3, d4, d5 = st.columns(5)
                    d1.metric("Qes", f"{derived.qes:.3f}")
                    d2.metric("Bl", f"{derived.bl_tm:.2f} T·m")
                    d3.metric("Mms", f"{derived.mms_kg * 1000.0:.2f} g")
                    d4.metric("Cms", f"{derived.cms_m_per_n * 1000.0:.3f} mm/N")
                    d5.metric("Sd", f"{derived.sd_m2 * 10000.0:.1f} cm²")

                    ref = _acoustics.driver_reference_metrics(current_ts)
                    bandwidth = _acoustics.classify_driver_bandwidth(current_ts)
                    e1, e2, e3, e4, e5, e6 = st.columns(6)
                    e1.metric("Eta0 ref", f"{ref.eta0 * 100.0:.2f} %")
                    e2.metric("SPL 1W/1m", f"{ref.spl_1w_db:.1f} dB")
                    e3.metric("SPL 2.83V/1m", f"{ref.spl_2v83_db:.1f} dB")
                    e4.metric("EBP", f"{ref.ebp_hz:.0f} Hz")
                    e5.metric(
                        "VC corner",
                        "n/a" if bandwidth.f_le_hz is None else f"{bandwidth.f_le_hz:.0f} Hz",
                        help="Re/(2*pi*Le): above this frequency the voice-coil inductance rolls the response off.",
                    )
                    e6.metric("Class", _catalog._driver_class_label(bandwidth.driver_class))
                    if ref.ebp_hz < 50.0:
                        ebp_hint = "EBP < 50: this driver classically favours sealed or infinite-baffle loads."
                    elif ref.ebp_hz > 100.0:
                        ebp_hint = "EBP > 100: this driver classically favours ported loads (bass reflex / DCCAV)."
                    else:
                        ebp_hint = "EBP 50-100: this driver works in both sealed and ported loads."
                    st.caption(f"{ebp_hint} Class indicators: {', '.join(bandwidth.reasons)}.")

        with st.expander("Export design"):
            dl_cols = st.columns(4) if load_type == "DCCAV" else st.columns(3)
            dl_csv, dl_frd, dl_zma = dl_cols[:3]
            with dl_csv:
                st.download_button(
                    "Download response CSV",
                    _analysis._csv_bytes(result),
                    "load_forge_response.csv",
                    "text/csv",
                    width="stretch",
                )
            with dl_frd:
                st.download_button(
                    "Download FRD (response)",
                    _acoustics.export_frd_text(result),
                    "load_forge_response.frd",
                    "text/plain",
                    width="stretch",
                    help="Total response as freq/SPL/phase text for VituixCAD, XSim or REW.",
                )
            with dl_zma:
                st.download_button(
                    "Download ZMA (impedance)",
                    _acoustics.export_zma_text(result),
                    "load_forge_impedance.zma",
                    "text/plain",
                    width="stretch",
                    help="Electrical impedance as freq/ohm/phase text for VituixCAD, XSim or REW.",
                )
            if load_type == "DCCAV":
                with dl_cols[3]:
                    try:
                        afw_text = _afw_export.generate_afw_text(_state._collect_params())
                        afw_bytes = afw_text.encode("latin-1")
                        afw_error = None
                    except Exception as exc:
                        afw_bytes = b""
                        afw_error = str(exc)
                    st.download_button(
                        "Download AFW project",
                        afw_bytes,
                        "load_forge_dccav.afw",
                        "application/octet-stream",
                        width="stretch",
                        disabled=afw_error is not None,
                        help=(
                            f"Could not build the AFW file: {afw_error}" if afw_error else
                            "AUDIO per Windows pro v2 (AFW) project cloned from a "
                            "verified DCAAV template with this design's driver T/S "
                            "and chamber values. Port geometry fields are inherited "
                            "from the template and are not this project's actual "
                            "port dimensions."
                        ),
                    )

    except ValueError as exc:
        _runtime.logger.exception("Simulation failed")
        msg = str(exc)
        if "Qms" in msg or "Qts" in msg or "DriverTS" in msg or "complete driver" in msg.lower():
            st.error(f"Driver parameters are invalid: {exc}")
        elif "F max" in msg and "F min" in msg:
            st.error(str(exc))
        elif "Infinite baffle has no box" in msg:
            st.error(str(exc))
        else:
            st.error(f"Simulation failed: {exc}")
    except Exception as exc:
        _runtime.logger.exception("Simulation failed")
        st.error(f"Simulation failed: {exc}")
