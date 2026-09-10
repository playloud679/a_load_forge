"""Load Forge — acoustic-load simulator (thin Streamlit entry point).

The UI implementation lives in :mod:`ui` under ``src/ui``. This file only sets
up the import path, hot-reloads the ``src`` dependencies, injects the global
CSS, initializes runtime globals and calls :func:`ui.app.main`. See
``docs/ui.md`` for the package map.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))


import atexit
import base64
import csv
import hashlib
import html
import importlib
import io
import json
import logging
import multiprocessing
import os
import re
import sys
import time
import uuid
import zlib
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from datetime import UTC, datetime
from functools import cache, lru_cache
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

logger = logging.getLogger("load_forge.ui")
_OPTIMIZER_ENGINE_REVISION = 8

sys.path.insert(0, str(Path(__file__).parent / "src"))
import acoustics as _acoustics
import engine as _engine
import port_cad as _port_cad
import presets as _presets
import pricing as _pricing
import ranking as _ranking
import saas as _saas
import storage as _storage
import storage.private_store as _private_store
import billing as _billing

sys.path.insert(0, str(Path(__file__).parent / "tools"))
import compare_afw_sealed as _afw_compare
import generate_afw_dccav as _afw_export

def _reload_if_source_changed(module) -> bool:
    """Reload only when the module's file actually changed on disk.

    Streamlit reruns this whole script on every interaction, so an
    unconditional ``importlib.reload`` here would re-execute
    ``src/presets.py`` and ``src/pricing.py`` every rerun too — wiping their
    module-level ``lru_cache`` driver-catalog/price-matching caches (tens of
    MB of JSON, multi-second to rebuild) even when nothing changed. The
    module objects themselves persist in ``sys.modules`` across reruns
    (unlike this script's own top-level locals), so stashing the last-seen
    mtime directly on the module survives to the next rerun and lets normal
    usage stay warm while still hot-reloading on real edits.
    """
    try:
        mtime = Path(module.__file__).stat().st_mtime
    except OSError:
        importlib.reload(module)
        return True
    if getattr(module, "_load_forge_reload_mtime", None) != mtime:
        importlib.reload(module)
        module._load_forge_reload_mtime = mtime
        return True
    return False

# Reload dependencies before the facade. If a dependency changed, the facade
# must be reloaded even when acoustics.py itself did not change; otherwise its
# wildcard namespace keeps the old engine symbols in a long-lived Streamlit
# process.
for _module in (
    _engine, _port_cad, _pricing, _presets, _ranking, _saas, _private_store, _storage,
    _afw_export, _afw_compare,
):
    _reload_if_source_changed(_module)
# The facade is intentionally cheap to reload and must always rebind wildcard
# exports after any dependency may have hot-reloaded on a prior UI rerun.
importlib.reload(_acoustics)
_acoustics._load_forge_reload_mtime = Path(_acoustics.__file__).stat().st_mtime


from ui import account as _ui_account
from ui import analysis as _ui_analysis
from ui import app as _ui_app
from ui import catalog as _ui_catalog
from ui import constants as _ui_constants
from ui import finder as _ui_finder
from ui import optimizer as _ui_optimizer
from ui import projects as _ui_projects
from ui import runtime as _ui_runtime
from ui import state as _ui_state
from ui import styles as _ui_styles

for _ui_module in (
    _ui_runtime, _ui_constants, _ui_styles, _ui_state, _ui_catalog, _ui_finder,
    _ui_optimizer, _ui_analysis, _ui_projects, _ui_account, _ui_app,
):
    _reload_if_source_changed(_ui_module)

st.set_page_config(
    page_title=f"Load Forge v{_ui_runtime._VERSION}",
    page_icon=str(_ui_constants._FAVICON_PATH) if _ui_constants._FAVICON_PATH.exists() else None,
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={},
)


_ui_styles.inject_global_css()
_ui_runtime.initialize_saas_settings()
_ui_runtime._CURRENT_SAAS_USER = _ui_account._resolve_saas_user()
_ui_runtime._ACCOUNT_STORE = _ui_account._get_account_store()

from ui.account import (_account_admin_emails, _cached_account_store, 
    _cached_project_store, _cached_public_store, _get_account_store, 
    _get_current_user_account, _get_project_store, _get_public_store, 
    _remember_local_account, _render_auth_hero_and_badges, _render_local_account_gate, 
    _resolve_saas_user, _sign_out_saas)
from ui.analysis import (_active_design_comparison_color, _active_design_visible, 
    _band_layer, _chart_signature, _clear_pinned_responses, _click_marker_layer, 
    _csv_bytes, _cursor_label_rows, _cursor_layer, _cursor_row, _cursor_rows, 
    _delete_active_design_comparison_tab, _delete_design_comparison_tab, 
    _design_comparison_tab_colors, _design_comparison_tab_label, _design_comparison_tabs, 
    _design_crw_download, _design_crw_parameters, _design_crw_signature, 
    _design_driver_parameter_signature, _design_simulation_signature, _design_space_cached, 
    _design_tab_label_driver, _design_tab_parameters_match_preset, 
    _duplicate_active_design_comparison, _duplicate_design_comparison_tab, 
    _duplicate_design_tab_from_click, _duplicate_standalone_design_from_click, 
    _end_design_comparison, _expand_y_domain_for_pins, _interp, _line_chart, 
    _log_frequency_scale, _marker_display_label, _pin_label, _pinned_layer, 
    _pinned_metric_frame, _pinned_metric_layer, _pinned_response_frame, 
    _pinned_response_snapshot, _pinned_responses, _plot_excursion, _plot_group_delay, 
    _plot_impedance, _plot_mil, _plot_ports, _plot_response, _port_series, 
    _prepare_design_crw_download, _recover_design_tab_preset, _remove_pinned_response, 
    _render_design_analysis_tabs, _render_editable_design_tabs, _render_ports_tab, 
    _render_response_tab, _request_design_comparison_tab, _response_amplitude_axis, 
    _response_series, _response_tuning_markers, _response_y_domain, _series_frame, 
    _set_pinned_response_visible, _simulate_design_cached, _simulation_engine_revision, 
    _snapshot_revision, _sync_active_design_comparison_tab, _toggle_design_tab_visible, 
    _tolerance_band_cached, _topology_comparison_series, _tuning_marker_layer, 
    _update_active_design_comparison)
from ui.catalog import (_all_available_preset_families, _all_preset_price_currencies, 
    _all_preset_price_values, _apply_driver_preset, _available_driver_preset_names, 
    _available_preset_families, _catalog_path_for_preset, _catalog_record_display_identity, 
    _current_exchange_rates, _deduplicate_finder_preset_names, 
    _deduplicate_finder_preset_names_tuple, _deduplicate_finder_result_rows, 
    _driver_catalog_mapping, _driver_class_label, _driver_coverage_summary, 
    _driver_library_frame, _driver_preset_class, _driver_preset_currency, 
    _driver_preset_display_label, _driver_preset_exact_source, _driver_preset_family, 
    _driver_preset_identity_fields, _driver_preset_price, _driver_preset_size, 
    _driver_preset_source, _filter_driver_preset_names, _filter_finder_performance_rows, 
    _finder_brief_constraints, _finder_candidate_precheck, _finder_controls_signature, 
    _finder_driver_identity, _finder_filter_summary, _finder_load_context, 
    _finder_prefilter, _finder_preset_preference, _finder_price_currency, 
    _finder_result_context_signature, _maintenance_allowed, _normalize_price_frame, 
    _normalized_preset_price, _on_driver_preset_change, _passive_radiator_library_frame, 
    _poll_catalog_refresh, _prefilter_finder_candidate_pools, _preset_price_currencies, 
    _preset_price_values, _purchase_markdown, _refresh_finder_result_catalog_metadata, 
    _render_catalog_crawl_report, _render_catalog_maintenance, _render_driver_library, 
    _render_driver_mechanical_drawing, _render_finder_constraint_grid, 
    _render_finder_library_filters, _render_passive_radiator_library, 
    _selected_library_preset_names, _set_filter_group_from_all, _size_bucket, 
    _sync_filter_group_all, _sync_filter_multiselect, _sync_finder_library_selection, 
    _update_catalog_driver_from_box_design, _value_sorted_frame)
from ui.constants import (_ALL_LOAD_TYPES, _AUTOSAVE_DEBOUNCE_SECONDS, 
    _AUTOSAVE_RETRY_DELAYS, _AUTO_CURSOR_OPTIONS, _BASS_MATCH_PROJECT_RESULT_KEYS, 
    _BASS_MATCH_PROJECT_STATE_KEYS, _BOX_STRATEGIES, _BRAND_APP_IMAGE, _BRAND_IMAGE, 
    _CATALOG_ADDITIONS_REPORT, _CATALOG_CRAWL_PROGRESS, _CATALOG_CRAWL_REPORT, 
    _CATALOG_PATH_BY_PROVENANCE, _COMMUNITY_TAB_IMAGE, _DEFAULT_REFLEX_Q_ABS, 
    _DEFAULT_REFLEX_Q_LEAK, _DEFAULT_REFLEX_Q_PORT, _DESIGN_COMPARISON_TRACE_COLORS, 
    _EXPLORE_FILTER_DEFAULTS, _FAVICON_PATH, _FINDER_CONTEXT_FILTERED_POOL_VERSION, 
    _FINDER_CTA_LABEL, _FINDER_DEFAULTS, _FINDER_DEFAULTS_VERSION, _FINDER_RANKING_VERSION, 
    _FINDER_RANK_F3, _FINDER_RANK_MODES, _FINDER_RANK_VALUE, _FINDER_SCENARIOS, 
    _FINDER_SPL_PREFILTER_HEADROOM_DB, _LFP_FORMAT_VERSION, _LFP_MAX_SAVED_BATCH_RESULTS, 
    _LIBRARY_TABLE_MAX_ROWS, _LOAD_IMAGE_DIR, _LOAD_TYPE_IMAGES, _LOAD_TYPE_SHORT, 
    _LOAD_TYPE_SLUGS, _LOCAL_ACCOUNT_SESSION_KEY, _MAX_COMPARISON_DESIGNS, 
    _MAX_PINNED_CHART_ROWS, _MAX_PINNED_RESPONSES, _NUDGE_KEY_SUFFIXES, 
    _OPTIMIZER_ENGINE_REVISION, _OPT_OBJECTIVE_LABELS, _PARAM_PREFIXES, _PIN_TRACE_COLORS, 
    _PORT_GEOMETRY_COLUMNS, _PORT_TRACE_OPTIONS, _PRESET_CLASS_ENGINE_VALUES, 
    _PRESET_CLASS_FILTERS, _PRESET_CLASS_FILTER_ALIASES, _PRESET_FAMILY_ORDER, 
    _PRESET_FILTER_NONE, _PRESET_SELECT_MAX_OPTIONS, _PRESET_SIZE_FILTERS, 
    _PRESET_SOURCE_FILTERS, _PRESET_SOURCE_FILTER_ALIASES, 
    _PRICE_CURRENCY_DEFAULTS_VERSION, _PROJECT_TRANSIENT_STATE_KEYS, 
    _PROJECT_TRANSIENT_STATE_PREFIXES, _RESONATOR_PORT, _RESONATOR_PR, 
    _RESONATOR_RESPONSE_TRACES, _RESONATOR_TYPES, _RESPONSE_DEFAULTS_VERSION, 
    _RESPONSE_TRACE_OPTIONS, _RESTRICTED_THIRD_PARTY_SOURCES, _RETAILER_CRAWL_REPORT, 
    _SAVE_STATUS_LABELS, _STL_SPLIT_LABELS, _TABLE_NUMBER_FORMATS, _TRACE_COLORS, 
    _UNTITLED_PROJECT_NAME, _WORKSPACES, _WORKSPACE_DISPLAY_LABELS, _WORKSPACE_TAB_IMAGES, 
    _WORKSPACE_TAB_SLUGS, logger)
from ui.finder import (_add_finder_designs_to_comparison, _apply_alignment, 
    _apply_bandpass4_alignment, _apply_bandpass6_alignment, _apply_bandpass8_alignment, 
    _apply_batch_result, _apply_finder_scenario, _apply_library_driver, _apply_library_pr, 
    _apply_pending_atlas_point, _apply_pending_batch_comparison, 
    _apply_pending_batch_result, _apply_pr_combo, _apply_reflex_alignment, 
    _apply_sealed_alignment, _atlas_frame, _atlas_loss_signature, 
    _auto_align_current_driver, _auto_alignment_signature, _batch_dccav_box, 
    _batch_rank_presets, _batch_rank_presets_parallel, _batch_rank_presets_with_progress, 
    _drop_finder_worker_pool, _finder_box_value, _finder_executor_backend, 
    _finder_optimizer_goals_from_state, _finder_per_load_stats_str, 
    _finder_pool_fingerprint, _finder_result_snapshot, _finder_row_box_params, 
    _finder_row_driver, _finder_search_blocked, _finder_total_volume_l, 
    _finder_worker_limit, _finder_worker_pool, _initialize_alignment_defaults, 
    _is_streamlit_community_cloud, _mark_auto_alignment_synced, _on_driver_param_change, 
    _on_load_type_change, _on_pr_preset_change, _optimizer_goals_signature, 
    _queue_atlas_point, _queue_finder_design_selection, _rank_value, _render_atlas_tab, 
    _render_bass_match_hero, _render_candidate_pool, _render_find_driver_actions, 
    _render_find_driver_goal_sidebar, _render_find_driver_target_sidebar, 
    _render_find_driver_workspace, _render_finder_run_statistics, 
    _render_finder_scenario_selector, _run_find_driver_search, _show_advanced_controls, 
    _step5, _sync_auto_alignment_if_needed)
from ui.optimizer import (_alignment_uses_optimizer, _alignment_warning, 
    _apply_empirical_box_for, _apply_optimized_box, _apply_optimized_port_geometry, 
    _apply_suggested_box_for, _current_optimizer_alternatives, _current_optimizer_summary, 
    _design_objective_label, _fmt_db, _fmt_hz, _on_box_strategy_change, 
    _optimized_port_diameter_cm, _optimized_summary, _optimizer_box_signature, 
    _optimizer_context_box, _optimizer_goals_from_state, _optimizer_result_context, 
    _port_geometry_row, _render_optimizer_alternatives, _run_box_optimizer, 
    _use_manual_box_strategy)
from ui.projects import (_apply_cloud_record, _apply_lfp_project, _apply_loaded_params, 
    _apply_pending_cloud_record, _bass_match_results_signature, _build_lfp_project, 
    _clear_active_project_state, _cloud_autosave_step, _cloud_persistence_error_message, 
    _cloud_persistence_fragment, _cloud_project_summaries, 
    _collect_bass_match_project_state, _community_tab_image_b64, _compact_result_row, 
    _create_new_project, _decode_share_payload, _derive_project_acoustic_metrics, 
    _detach_cloud_project, _duplicate_active_project, _encode_share_payload, 
    _explore_optional_limit, _fork_project_to_sandbox, _get_community_load_image, 
    _invalidate_bass_match_results_signature, _invalidate_cloud_project_list, 
    _mark_cloud_project_dirty, _open_billing_modal, _open_community_workspace, 
    _open_manage_projects_workspace, _open_technical_page, _parse_query_param_str, 
    _process_project_cover_image, _project_display_name, _project_download_filename, 
    _project_name_is_placeholder, _public_project_url, _queue_cloud_record_activation, 
    _record_lfp_export, _render_authenticated_account_controls, 
    _render_billing_action_button, _render_cloud_persistence_status, 
    _render_community_sidebar, _render_credits_purchase_popover, 
    _render_embed_project_widget, _render_explore_projects_directory, 
    _render_hud_explore_community_button, _render_main_account_header, 
    _render_manage_projects_cloud_list, _render_manage_projects_history, 
    _render_manage_projects_publish, _render_manage_projects_trash, 
    _render_manage_projects_workspace, _render_project_menu, _render_public_project_page, 
    _render_public_project_sidebar, _render_user_management, _request_new_project_name, 
    _reset_explore_filters, _resolve_driver_ts, _serialize_bass_match_context, 
    _set_active_cloud_record, _share_link_url, _toggle_community_project_like)
from ui.state import (_available_workspaces, _bandpass4_box_from_state, 
    _bandpass6_box_from_state, _bandpass8_box_from_state, _box_from_params, 
    _box_from_state, _box_number_with_nudge, _box_strategy_is_auto, 
    _clean_display_table_frame, _clean_style_str, _collect_params, _default, 
    _driver_from_params, _driver_from_state, _ensure_finder_defaults, 
    _ensure_plot_control_state, _ensure_price_currency_default, _finder_number_input, 
    _finder_selectbox, _finder_value, _is_param_key, _json_safe, 
    _manual_box_keys_for_load_type, _mark_session_flag, _normalize_box_strategy, 
    _normalize_stl_split_mode, _on_workspace_compat_change, _optional_positive, 
    _persist_widget_selection, _pr_box_from_state, _preserve_design_state, 
    _preserve_library_filters, _read_json_object, _reflex_box_from_state, 
    _reflex_uses_passive_radiator, _render_engine_only_topologies_note, 
    _render_load_type_buttons, _render_workspace_tabs, _reset_candidate_filters, 
    _reset_finder_defaults, _reset_response_zoom, _restore_design_state, 
    _restore_manual_box, _sealed_box_from_state, _select_load_type_card, _select_workspace, 
    _set_box_strategy_state, _single_driver_from_state, _snapshot_design_state, 
    _snapshot_manual_box, _table_value_missing)
from ui.styles import (_focused_port_flare_style, _load_type_card_styles, 
    _workspace_tab_styles)
from ui.runtime import (_ACCOUNT_STORE, _CURRENT_SAAS_USER, _SAAS_SETTINGS, 
    _SAAS_SOURCE_TOKEN, _VERSION, logger)

_ui_app.main()
