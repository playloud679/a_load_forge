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

sys.path.insert(0, str(Path(__file__).parent / "src"))
import acoustics as _acoustics
import billing as _billing
import engine as _engine
import port_cad as _port_cad
import presets as _presets
import pricing as _pricing
import ranking as _ranking
import saas as _saas
import storage as _storage
import storage.private_store as _private_store

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

from ui.account import _account_admin_emails as _account_admin_emails
from ui.account import _cached_account_store as _cached_account_store
from ui.account import _cached_project_store as _cached_project_store
from ui.account import _cached_public_store as _cached_public_store
from ui.account import _get_account_store as _get_account_store
from ui.account import _get_current_user_account as _get_current_user_account
from ui.account import _get_project_store as _get_project_store
from ui.account import _get_public_store as _get_public_store
from ui.account import _remember_local_account as _remember_local_account
from ui.account import _render_auth_hero_and_badges as _render_auth_hero_and_badges
from ui.account import _render_local_account_gate as _render_local_account_gate
from ui.account import _resolve_saas_user as _resolve_saas_user
from ui.account import _sign_out_saas as _sign_out_saas
from ui.analysis import _active_design_comparison_color as _active_design_comparison_color
from ui.analysis import _active_design_visible as _active_design_visible
from ui.analysis import _band_layer as _band_layer
from ui.analysis import _chart_signature as _chart_signature
from ui.analysis import _clear_pinned_responses as _clear_pinned_responses
from ui.analysis import _click_marker_layer as _click_marker_layer
from ui.analysis import _csv_bytes as _csv_bytes
from ui.analysis import _cursor_label_rows as _cursor_label_rows
from ui.analysis import _cursor_layer as _cursor_layer
from ui.analysis import _cursor_row as _cursor_row
from ui.analysis import _cursor_rows as _cursor_rows
from ui.analysis import _delete_active_design_comparison_tab as _delete_active_design_comparison_tab
from ui.analysis import _delete_design_comparison_tab as _delete_design_comparison_tab
from ui.analysis import _design_comparison_tab_colors as _design_comparison_tab_colors
from ui.analysis import _design_comparison_tab_label as _design_comparison_tab_label
from ui.analysis import _design_comparison_tabs as _design_comparison_tabs
from ui.analysis import _design_crw_download as _design_crw_download
from ui.analysis import _design_crw_parameters as _design_crw_parameters
from ui.analysis import _design_crw_signature as _design_crw_signature
from ui.analysis import _design_driver_parameter_signature as _design_driver_parameter_signature
from ui.analysis import _design_simulation_signature as _design_simulation_signature
from ui.analysis import _design_space_cached as _design_space_cached
from ui.analysis import _design_tab_label_driver as _design_tab_label_driver
from ui.analysis import _design_tab_parameters_match_preset as _design_tab_parameters_match_preset
from ui.analysis import _duplicate_active_design_comparison as _duplicate_active_design_comparison
from ui.analysis import _duplicate_design_comparison_tab as _duplicate_design_comparison_tab
from ui.analysis import _duplicate_design_tab_from_click as _duplicate_design_tab_from_click
from ui.analysis import (
    _duplicate_standalone_design_from_click as _duplicate_standalone_design_from_click,
)
from ui.analysis import _end_design_comparison as _end_design_comparison
from ui.analysis import _expand_y_domain_for_pins as _expand_y_domain_for_pins
from ui.analysis import _interp as _interp
from ui.analysis import _line_chart as _line_chart
from ui.analysis import _log_frequency_scale as _log_frequency_scale
from ui.analysis import _marker_display_label as _marker_display_label
from ui.analysis import _pin_label as _pin_label
from ui.analysis import _pinned_layer as _pinned_layer
from ui.analysis import _pinned_metric_frame as _pinned_metric_frame
from ui.analysis import _pinned_metric_layer as _pinned_metric_layer
from ui.analysis import _pinned_response_frame as _pinned_response_frame
from ui.analysis import _pinned_response_snapshot as _pinned_response_snapshot
from ui.analysis import _pinned_responses as _pinned_responses
from ui.analysis import _plot_excursion as _plot_excursion
from ui.analysis import _plot_group_delay as _plot_group_delay
from ui.analysis import _plot_impedance as _plot_impedance
from ui.analysis import _plot_mil as _plot_mil
from ui.analysis import _plot_ports as _plot_ports
from ui.analysis import _plot_response as _plot_response
from ui.analysis import _port_series as _port_series
from ui.analysis import _prepare_design_crw_download as _prepare_design_crw_download
from ui.analysis import _recover_design_tab_preset as _recover_design_tab_preset
from ui.analysis import _remove_pinned_response as _remove_pinned_response
from ui.analysis import _render_design_analysis_tabs as _render_design_analysis_tabs
from ui.analysis import _render_editable_design_tabs as _render_editable_design_tabs
from ui.analysis import _render_ports_tab as _render_ports_tab
from ui.analysis import _render_response_tab as _render_response_tab
from ui.analysis import _request_design_comparison_tab as _request_design_comparison_tab
from ui.analysis import _response_amplitude_axis as _response_amplitude_axis
from ui.analysis import _response_series as _response_series
from ui.analysis import _response_tuning_markers as _response_tuning_markers
from ui.analysis import _response_y_domain as _response_y_domain
from ui.analysis import _series_frame as _series_frame
from ui.analysis import _set_pinned_response_visible as _set_pinned_response_visible
from ui.analysis import _simulate_design_cached as _simulate_design_cached
from ui.analysis import _simulation_engine_revision as _simulation_engine_revision
from ui.analysis import _snapshot_revision as _snapshot_revision
from ui.analysis import _sync_active_design_comparison_tab as _sync_active_design_comparison_tab
from ui.analysis import _toggle_design_tab_visible as _toggle_design_tab_visible
from ui.analysis import _tolerance_band_cached as _tolerance_band_cached
from ui.analysis import _topology_comparison_series as _topology_comparison_series
from ui.analysis import _tuning_marker_layer as _tuning_marker_layer
from ui.analysis import _update_active_design_comparison as _update_active_design_comparison
from ui.catalog import _all_available_preset_families as _all_available_preset_families
from ui.catalog import _all_preset_price_currencies as _all_preset_price_currencies
from ui.catalog import _all_preset_price_values as _all_preset_price_values
from ui.catalog import _apply_driver_preset as _apply_driver_preset
from ui.catalog import _available_driver_preset_names as _available_driver_preset_names
from ui.catalog import _available_preset_families as _available_preset_families
from ui.catalog import _catalog_path_for_preset as _catalog_path_for_preset
from ui.catalog import _catalog_record_display_identity as _catalog_record_display_identity
from ui.catalog import _current_exchange_rates as _current_exchange_rates
from ui.catalog import _deduplicate_finder_preset_names as _deduplicate_finder_preset_names
from ui.catalog import (
    _deduplicate_finder_preset_names_tuple as _deduplicate_finder_preset_names_tuple,
)
from ui.catalog import _deduplicate_finder_result_rows as _deduplicate_finder_result_rows
from ui.catalog import _driver_catalog_mapping as _driver_catalog_mapping
from ui.catalog import _driver_class_label as _driver_class_label
from ui.catalog import _driver_coverage_summary as _driver_coverage_summary
from ui.catalog import _driver_library_frame as _driver_library_frame
from ui.catalog import _driver_preset_class as _driver_preset_class
from ui.catalog import _driver_preset_currency as _driver_preset_currency
from ui.catalog import _driver_preset_display_label as _driver_preset_display_label
from ui.catalog import _driver_preset_exact_source as _driver_preset_exact_source
from ui.catalog import _driver_preset_family as _driver_preset_family
from ui.catalog import _driver_preset_identity_fields as _driver_preset_identity_fields
from ui.catalog import _driver_preset_price as _driver_preset_price
from ui.catalog import _driver_preset_size as _driver_preset_size
from ui.catalog import _driver_preset_source as _driver_preset_source
from ui.catalog import _filter_driver_preset_names as _filter_driver_preset_names
from ui.catalog import _filter_finder_performance_rows as _filter_finder_performance_rows
from ui.catalog import _finder_brief_constraints as _finder_brief_constraints
from ui.catalog import _finder_candidate_precheck as _finder_candidate_precheck
from ui.catalog import _finder_controls_signature as _finder_controls_signature
from ui.catalog import _finder_driver_identity as _finder_driver_identity
from ui.catalog import _finder_filter_summary as _finder_filter_summary
from ui.catalog import _finder_load_context as _finder_load_context
from ui.catalog import _finder_prefilter as _finder_prefilter
from ui.catalog import _finder_preset_preference as _finder_preset_preference
from ui.catalog import _finder_price_currency as _finder_price_currency
from ui.catalog import _finder_result_context_signature as _finder_result_context_signature
from ui.catalog import _maintenance_allowed as _maintenance_allowed
from ui.catalog import _normalize_price_frame as _normalize_price_frame
from ui.catalog import _normalized_preset_price as _normalized_preset_price
from ui.catalog import _on_driver_preset_change as _on_driver_preset_change
from ui.catalog import _passive_radiator_library_frame as _passive_radiator_library_frame
from ui.catalog import _poll_catalog_refresh as _poll_catalog_refresh
from ui.catalog import _prefilter_finder_candidate_pools as _prefilter_finder_candidate_pools
from ui.catalog import _preset_price_currencies as _preset_price_currencies
from ui.catalog import _preset_price_values as _preset_price_values
from ui.catalog import _purchase_markdown as _purchase_markdown
from ui.catalog import (
    _refresh_finder_result_catalog_metadata as _refresh_finder_result_catalog_metadata,
)
from ui.catalog import _render_catalog_crawl_report as _render_catalog_crawl_report
from ui.catalog import _render_catalog_maintenance as _render_catalog_maintenance
from ui.catalog import _render_driver_library as _render_driver_library
from ui.catalog import _render_driver_mechanical_drawing as _render_driver_mechanical_drawing
from ui.catalog import _render_finder_constraint_grid as _render_finder_constraint_grid
from ui.catalog import _render_finder_library_filters as _render_finder_library_filters
from ui.catalog import _render_passive_radiator_library as _render_passive_radiator_library
from ui.catalog import _selected_library_preset_names as _selected_library_preset_names
from ui.catalog import _set_filter_group_from_all as _set_filter_group_from_all
from ui.catalog import _size_bucket as _size_bucket
from ui.catalog import _sync_filter_group_all as _sync_filter_group_all
from ui.catalog import _sync_filter_multiselect as _sync_filter_multiselect
from ui.catalog import _sync_finder_library_selection as _sync_finder_library_selection
from ui.catalog import (
    _update_catalog_driver_from_box_design as _update_catalog_driver_from_box_design,
)
from ui.catalog import _value_sorted_frame as _value_sorted_frame
from ui.constants import _ALL_LOAD_TYPES as _ALL_LOAD_TYPES
from ui.constants import _AUTO_CURSOR_OPTIONS as _AUTO_CURSOR_OPTIONS
from ui.constants import _AUTOSAVE_DEBOUNCE_SECONDS as _AUTOSAVE_DEBOUNCE_SECONDS
from ui.constants import _AUTOSAVE_RETRY_DELAYS as _AUTOSAVE_RETRY_DELAYS
from ui.constants import _BASS_MATCH_PROJECT_RESULT_KEYS as _BASS_MATCH_PROJECT_RESULT_KEYS
from ui.constants import _BASS_MATCH_PROJECT_STATE_KEYS as _BASS_MATCH_PROJECT_STATE_KEYS
from ui.constants import _BOX_STRATEGIES as _BOX_STRATEGIES
from ui.constants import _BRAND_APP_IMAGE as _BRAND_APP_IMAGE
from ui.constants import _BRAND_IMAGE as _BRAND_IMAGE
from ui.constants import _CATALOG_ADDITIONS_REPORT as _CATALOG_ADDITIONS_REPORT
from ui.constants import _CATALOG_CRAWL_PROGRESS as _CATALOG_CRAWL_PROGRESS
from ui.constants import _CATALOG_CRAWL_REPORT as _CATALOG_CRAWL_REPORT
from ui.constants import _CATALOG_PATH_BY_PROVENANCE as _CATALOG_PATH_BY_PROVENANCE
from ui.constants import _COMMUNITY_TAB_IMAGE as _COMMUNITY_TAB_IMAGE
from ui.constants import _DEFAULT_REFLEX_Q_ABS as _DEFAULT_REFLEX_Q_ABS
from ui.constants import _DEFAULT_REFLEX_Q_LEAK as _DEFAULT_REFLEX_Q_LEAK
from ui.constants import _DEFAULT_REFLEX_Q_PORT as _DEFAULT_REFLEX_Q_PORT
from ui.constants import _DESIGN_COMPARISON_TRACE_COLORS as _DESIGN_COMPARISON_TRACE_COLORS
from ui.constants import _EXPLORE_FILTER_DEFAULTS as _EXPLORE_FILTER_DEFAULTS
from ui.constants import _FAVICON_PATH as _FAVICON_PATH
from ui.constants import (
    _FINDER_CONTEXT_FILTERED_POOL_VERSION as _FINDER_CONTEXT_FILTERED_POOL_VERSION,
)
from ui.constants import _FINDER_CTA_LABEL as _FINDER_CTA_LABEL
from ui.constants import _FINDER_DEFAULTS as _FINDER_DEFAULTS
from ui.constants import _FINDER_DEFAULTS_VERSION as _FINDER_DEFAULTS_VERSION
from ui.constants import _FINDER_RANK_F3 as _FINDER_RANK_F3
from ui.constants import _FINDER_RANK_MODES as _FINDER_RANK_MODES
from ui.constants import _FINDER_RANK_VALUE as _FINDER_RANK_VALUE
from ui.constants import _FINDER_RANKING_VERSION as _FINDER_RANKING_VERSION
from ui.constants import _FINDER_SCENARIOS as _FINDER_SCENARIOS
from ui.constants import _FINDER_SPL_PREFILTER_HEADROOM_DB as _FINDER_SPL_PREFILTER_HEADROOM_DB
from ui.constants import _LFP_FORMAT_VERSION as _LFP_FORMAT_VERSION
from ui.constants import _LFP_MAX_SAVED_BATCH_RESULTS as _LFP_MAX_SAVED_BATCH_RESULTS
from ui.constants import _LIBRARY_TABLE_MAX_ROWS as _LIBRARY_TABLE_MAX_ROWS
from ui.constants import _LOAD_IMAGE_DIR as _LOAD_IMAGE_DIR
from ui.constants import _LOAD_TYPE_IMAGES as _LOAD_TYPE_IMAGES
from ui.constants import _LOAD_TYPE_SHORT as _LOAD_TYPE_SHORT
from ui.constants import _LOAD_TYPE_SLUGS as _LOAD_TYPE_SLUGS
from ui.constants import _LOCAL_ACCOUNT_SESSION_KEY as _LOCAL_ACCOUNT_SESSION_KEY
from ui.constants import _MAX_COMPARISON_DESIGNS as _MAX_COMPARISON_DESIGNS
from ui.constants import _MAX_PINNED_CHART_ROWS as _MAX_PINNED_CHART_ROWS
from ui.constants import _MAX_PINNED_RESPONSES as _MAX_PINNED_RESPONSES
from ui.constants import _NUDGE_KEY_SUFFIXES as _NUDGE_KEY_SUFFIXES
from ui.constants import _OPT_OBJECTIVE_LABELS as _OPT_OBJECTIVE_LABELS
from ui.constants import _OPTIMIZER_ENGINE_REVISION as _OPTIMIZER_ENGINE_REVISION
from ui.constants import _PARAM_PREFIXES as _PARAM_PREFIXES
from ui.constants import _PIN_TRACE_COLORS as _PIN_TRACE_COLORS
from ui.constants import _PORT_GEOMETRY_COLUMNS as _PORT_GEOMETRY_COLUMNS
from ui.constants import _PORT_TRACE_OPTIONS as _PORT_TRACE_OPTIONS
from ui.constants import _PRESET_CLASS_ENGINE_VALUES as _PRESET_CLASS_ENGINE_VALUES
from ui.constants import _PRESET_CLASS_FILTER_ALIASES as _PRESET_CLASS_FILTER_ALIASES
from ui.constants import _PRESET_CLASS_FILTERS as _PRESET_CLASS_FILTERS
from ui.constants import _PRESET_FAMILY_ORDER as _PRESET_FAMILY_ORDER
from ui.constants import _PRESET_FILTER_NONE as _PRESET_FILTER_NONE
from ui.constants import _PRESET_SELECT_MAX_OPTIONS as _PRESET_SELECT_MAX_OPTIONS
from ui.constants import _PRESET_SIZE_FILTERS as _PRESET_SIZE_FILTERS
from ui.constants import _PRESET_SOURCE_FILTER_ALIASES as _PRESET_SOURCE_FILTER_ALIASES
from ui.constants import _PRESET_SOURCE_FILTERS as _PRESET_SOURCE_FILTERS
from ui.constants import _PRICE_CURRENCY_DEFAULTS_VERSION as _PRICE_CURRENCY_DEFAULTS_VERSION
from ui.constants import _PROJECT_TRANSIENT_STATE_KEYS as _PROJECT_TRANSIENT_STATE_KEYS
from ui.constants import _PROJECT_TRANSIENT_STATE_PREFIXES as _PROJECT_TRANSIENT_STATE_PREFIXES
from ui.constants import _RESONATOR_PORT as _RESONATOR_PORT
from ui.constants import _RESONATOR_PR as _RESONATOR_PR
from ui.constants import _RESONATOR_RESPONSE_TRACES as _RESONATOR_RESPONSE_TRACES
from ui.constants import _RESONATOR_TYPES as _RESONATOR_TYPES
from ui.constants import _RESPONSE_DEFAULTS_VERSION as _RESPONSE_DEFAULTS_VERSION
from ui.constants import _RESPONSE_TRACE_OPTIONS as _RESPONSE_TRACE_OPTIONS
from ui.constants import _RESTRICTED_THIRD_PARTY_SOURCES as _RESTRICTED_THIRD_PARTY_SOURCES
from ui.constants import _RETAILER_CRAWL_REPORT as _RETAILER_CRAWL_REPORT
from ui.constants import _SAVE_STATUS_LABELS as _SAVE_STATUS_LABELS
from ui.constants import _STL_SPLIT_LABELS as _STL_SPLIT_LABELS
from ui.constants import _TABLE_NUMBER_FORMATS as _TABLE_NUMBER_FORMATS
from ui.constants import _TRACE_COLORS as _TRACE_COLORS
from ui.constants import _UNTITLED_PROJECT_NAME as _UNTITLED_PROJECT_NAME
from ui.constants import _WORKSPACE_DISPLAY_LABELS as _WORKSPACE_DISPLAY_LABELS
from ui.constants import _WORKSPACE_TAB_IMAGES as _WORKSPACE_TAB_IMAGES
from ui.constants import _WORKSPACE_TAB_SLUGS as _WORKSPACE_TAB_SLUGS
from ui.constants import _WORKSPACES as _WORKSPACES
from ui.finder import _add_finder_designs_to_comparison as _add_finder_designs_to_comparison
from ui.finder import _apply_alignment as _apply_alignment
from ui.finder import _apply_bandpass4_alignment as _apply_bandpass4_alignment
from ui.finder import _apply_bandpass6_alignment as _apply_bandpass6_alignment
from ui.finder import _apply_bandpass8_alignment as _apply_bandpass8_alignment
from ui.finder import _apply_batch_result as _apply_batch_result
from ui.finder import _apply_finder_scenario as _apply_finder_scenario
from ui.finder import _apply_library_driver as _apply_library_driver
from ui.finder import _apply_library_pr as _apply_library_pr
from ui.finder import _apply_pending_atlas_point as _apply_pending_atlas_point
from ui.finder import _apply_pending_batch_comparison as _apply_pending_batch_comparison
from ui.finder import _apply_pending_batch_result as _apply_pending_batch_result
from ui.finder import _apply_pr_combo as _apply_pr_combo
from ui.finder import _apply_reflex_alignment as _apply_reflex_alignment
from ui.finder import _apply_sealed_alignment as _apply_sealed_alignment
from ui.finder import _atlas_frame as _atlas_frame
from ui.finder import _atlas_loss_signature as _atlas_loss_signature
from ui.finder import _auto_align_current_driver as _auto_align_current_driver
from ui.finder import _auto_alignment_signature as _auto_alignment_signature
from ui.finder import _batch_dccav_box as _batch_dccav_box
from ui.finder import _batch_rank_presets as _batch_rank_presets
from ui.finder import _batch_rank_presets_parallel as _batch_rank_presets_parallel
from ui.finder import _batch_rank_presets_with_progress as _batch_rank_presets_with_progress
from ui.finder import _drop_finder_worker_pool as _drop_finder_worker_pool
from ui.finder import _finder_box_value as _finder_box_value
from ui.finder import _finder_executor_backend as _finder_executor_backend
from ui.finder import _finder_optimizer_goals_from_state as _finder_optimizer_goals_from_state
from ui.finder import _finder_per_load_stats_str as _finder_per_load_stats_str
from ui.finder import _finder_pool_fingerprint as _finder_pool_fingerprint
from ui.finder import _finder_result_snapshot as _finder_result_snapshot
from ui.finder import _finder_row_box_params as _finder_row_box_params
from ui.finder import _finder_row_driver as _finder_row_driver
from ui.finder import _finder_search_blocked as _finder_search_blocked
from ui.finder import _finder_total_volume_l as _finder_total_volume_l
from ui.finder import _finder_worker_limit as _finder_worker_limit
from ui.finder import _finder_worker_pool as _finder_worker_pool
from ui.finder import _initialize_alignment_defaults as _initialize_alignment_defaults
from ui.finder import _is_streamlit_community_cloud as _is_streamlit_community_cloud
from ui.finder import _mark_auto_alignment_synced as _mark_auto_alignment_synced
from ui.finder import _on_driver_param_change as _on_driver_param_change
from ui.finder import _on_load_type_change as _on_load_type_change
from ui.finder import _on_pr_preset_change as _on_pr_preset_change
from ui.finder import _optimizer_goals_signature as _optimizer_goals_signature
from ui.finder import _queue_atlas_point as _queue_atlas_point
from ui.finder import _queue_finder_design_selection as _queue_finder_design_selection
from ui.finder import _rank_value as _rank_value
from ui.finder import _render_atlas_tab as _render_atlas_tab
from ui.finder import _render_bass_match_hero as _render_bass_match_hero
from ui.finder import _render_candidate_pool as _render_candidate_pool
from ui.finder import _render_find_driver_actions as _render_find_driver_actions
from ui.finder import _render_find_driver_goal_sidebar as _render_find_driver_goal_sidebar
from ui.finder import _render_find_driver_target_sidebar as _render_find_driver_target_sidebar
from ui.finder import _render_find_driver_workspace as _render_find_driver_workspace
from ui.finder import _render_finder_run_statistics as _render_finder_run_statistics
from ui.finder import _render_finder_scenario_selector as _render_finder_scenario_selector
from ui.finder import _run_find_driver_search as _run_find_driver_search
from ui.finder import _show_advanced_controls as _show_advanced_controls
from ui.finder import _step5 as _step5
from ui.finder import _sync_auto_alignment_if_needed as _sync_auto_alignment_if_needed
from ui.optimizer import _alignment_uses_optimizer as _alignment_uses_optimizer
from ui.optimizer import _alignment_warning as _alignment_warning
from ui.optimizer import _apply_empirical_box_for as _apply_empirical_box_for
from ui.optimizer import _apply_optimized_box as _apply_optimized_box
from ui.optimizer import _apply_optimized_port_geometry as _apply_optimized_port_geometry
from ui.optimizer import _apply_suggested_box_for as _apply_suggested_box_for
from ui.optimizer import _current_optimizer_alternatives as _current_optimizer_alternatives
from ui.optimizer import _current_optimizer_summary as _current_optimizer_summary
from ui.optimizer import _design_objective_label as _design_objective_label
from ui.optimizer import _fmt_db as _fmt_db
from ui.optimizer import _fmt_hz as _fmt_hz
from ui.optimizer import _on_box_strategy_change as _on_box_strategy_change
from ui.optimizer import _optimized_port_diameter_cm as _optimized_port_diameter_cm
from ui.optimizer import _optimized_summary as _optimized_summary
from ui.optimizer import _optimizer_box_signature as _optimizer_box_signature
from ui.optimizer import _optimizer_context_box as _optimizer_context_box
from ui.optimizer import _optimizer_goals_from_state as _optimizer_goals_from_state
from ui.optimizer import _optimizer_result_context as _optimizer_result_context
from ui.optimizer import _port_geometry_row as _port_geometry_row
from ui.optimizer import _render_optimizer_alternatives as _render_optimizer_alternatives
from ui.optimizer import _run_box_optimizer as _run_box_optimizer
from ui.optimizer import _use_manual_box_strategy as _use_manual_box_strategy
from ui.projects import _apply_cloud_record as _apply_cloud_record
from ui.projects import _apply_lfp_project as _apply_lfp_project
from ui.projects import _apply_loaded_params as _apply_loaded_params
from ui.projects import _apply_pending_cloud_record as _apply_pending_cloud_record
from ui.projects import _bass_match_results_signature as _bass_match_results_signature
from ui.projects import _build_lfp_project as _build_lfp_project
from ui.projects import _clear_active_project_state as _clear_active_project_state
from ui.projects import _cloud_autosave_step as _cloud_autosave_step
from ui.projects import _cloud_persistence_error_message as _cloud_persistence_error_message
from ui.projects import _cloud_persistence_fragment as _cloud_persistence_fragment
from ui.projects import _cloud_project_summaries as _cloud_project_summaries
from ui.projects import _collect_bass_match_project_state as _collect_bass_match_project_state
from ui.projects import _community_tab_image_b64 as _community_tab_image_b64
from ui.projects import _compact_result_row as _compact_result_row
from ui.projects import _create_new_project as _create_new_project
from ui.projects import _decode_share_payload as _decode_share_payload
from ui.projects import _derive_project_acoustic_metrics as _derive_project_acoustic_metrics
from ui.projects import _detach_cloud_project as _detach_cloud_project
from ui.projects import _duplicate_active_project as _duplicate_active_project
from ui.projects import _encode_share_payload as _encode_share_payload
from ui.projects import _explore_optional_limit as _explore_optional_limit
from ui.projects import _fork_project_to_sandbox as _fork_project_to_sandbox
from ui.projects import _get_community_load_image as _get_community_load_image
from ui.projects import (
    _invalidate_bass_match_results_signature as _invalidate_bass_match_results_signature,
)
from ui.projects import _invalidate_cloud_project_list as _invalidate_cloud_project_list
from ui.projects import _mark_cloud_project_dirty as _mark_cloud_project_dirty
from ui.projects import _open_billing_modal as _open_billing_modal
from ui.projects import _open_community_workspace as _open_community_workspace
from ui.projects import _open_manage_projects_workspace as _open_manage_projects_workspace
from ui.projects import _open_technical_page as _open_technical_page
from ui.projects import _parse_query_param_str as _parse_query_param_str
from ui.projects import _process_project_cover_image as _process_project_cover_image
from ui.projects import _project_display_name as _project_display_name
from ui.projects import _project_download_filename as _project_download_filename
from ui.projects import _project_name_is_placeholder as _project_name_is_placeholder
from ui.projects import _public_project_url as _public_project_url
from ui.projects import _queue_cloud_record_activation as _queue_cloud_record_activation
from ui.projects import _record_lfp_export as _record_lfp_export
from ui.projects import (
    _render_authenticated_account_controls as _render_authenticated_account_controls,
)
from ui.projects import _render_billing_action_button as _render_billing_action_button
from ui.projects import _render_cloud_persistence_status as _render_cloud_persistence_status
from ui.projects import _render_community_sidebar as _render_community_sidebar
from ui.projects import _render_credits_purchase_popover as _render_credits_purchase_popover
from ui.projects import _render_embed_project_widget as _render_embed_project_widget
from ui.projects import _render_explore_projects_directory as _render_explore_projects_directory
from ui.projects import _render_hud_explore_community_button as _render_hud_explore_community_button
from ui.projects import _render_main_account_header as _render_main_account_header
from ui.projects import _render_manage_projects_cloud_list as _render_manage_projects_cloud_list
from ui.projects import _render_manage_projects_history as _render_manage_projects_history
from ui.projects import _render_manage_projects_publish as _render_manage_projects_publish
from ui.projects import _render_manage_projects_trash as _render_manage_projects_trash
from ui.projects import _render_manage_projects_workspace as _render_manage_projects_workspace
from ui.projects import _render_project_menu as _render_project_menu
from ui.projects import _render_public_project_page as _render_public_project_page
from ui.projects import _render_public_project_sidebar as _render_public_project_sidebar
from ui.projects import _render_user_management as _render_user_management
from ui.projects import _request_new_project_name as _request_new_project_name
from ui.projects import _reset_explore_filters as _reset_explore_filters
from ui.projects import _resolve_driver_ts as _resolve_driver_ts
from ui.projects import _serialize_bass_match_context as _serialize_bass_match_context
from ui.projects import _set_active_cloud_record as _set_active_cloud_record
from ui.projects import _share_link_url as _share_link_url
from ui.projects import _toggle_community_project_like as _toggle_community_project_like
from ui.runtime import _ACCOUNT_STORE as _ACCOUNT_STORE
from ui.runtime import _CURRENT_SAAS_USER as _CURRENT_SAAS_USER
from ui.runtime import _SAAS_SETTINGS as _SAAS_SETTINGS
from ui.runtime import _SAAS_SOURCE_TOKEN as _SAAS_SOURCE_TOKEN
from ui.runtime import _VERSION as _VERSION
from ui.runtime import logger as logger
from ui.state import _available_workspaces as _available_workspaces
from ui.state import _bandpass4_box_from_state as _bandpass4_box_from_state
from ui.state import _bandpass6_box_from_state as _bandpass6_box_from_state
from ui.state import _bandpass8_box_from_state as _bandpass8_box_from_state
from ui.state import _box_from_params as _box_from_params
from ui.state import _box_from_state as _box_from_state
from ui.state import _box_number_with_nudge as _box_number_with_nudge
from ui.state import _box_strategy_is_auto as _box_strategy_is_auto
from ui.state import _clean_display_table_frame as _clean_display_table_frame
from ui.state import _clean_style_str as _clean_style_str
from ui.state import _collect_params as _collect_params
from ui.state import _default as _default
from ui.state import _driver_from_params as _driver_from_params
from ui.state import _driver_from_state as _driver_from_state
from ui.state import _ensure_finder_defaults as _ensure_finder_defaults
from ui.state import _ensure_plot_control_state as _ensure_plot_control_state
from ui.state import _ensure_price_currency_default as _ensure_price_currency_default
from ui.state import _finder_number_input as _finder_number_input
from ui.state import _finder_selectbox as _finder_selectbox
from ui.state import _finder_value as _finder_value
from ui.state import _is_param_key as _is_param_key
from ui.state import _json_safe as _json_safe
from ui.state import _manual_box_keys_for_load_type as _manual_box_keys_for_load_type
from ui.state import _mark_session_flag as _mark_session_flag
from ui.state import _normalize_box_strategy as _normalize_box_strategy
from ui.state import _normalize_stl_split_mode as _normalize_stl_split_mode
from ui.state import _on_workspace_compat_change as _on_workspace_compat_change
from ui.state import _optional_positive as _optional_positive
from ui.state import _persist_widget_selection as _persist_widget_selection
from ui.state import _pr_box_from_state as _pr_box_from_state
from ui.state import _preserve_design_state as _preserve_design_state
from ui.state import _preserve_library_filters as _preserve_library_filters
from ui.state import _read_json_object as _read_json_object
from ui.state import _reflex_box_from_state as _reflex_box_from_state
from ui.state import _reflex_uses_passive_radiator as _reflex_uses_passive_radiator
from ui.state import _render_engine_only_topologies_note as _render_engine_only_topologies_note
from ui.state import _render_load_type_buttons as _render_load_type_buttons
from ui.state import _render_workspace_tabs as _render_workspace_tabs
from ui.state import _reset_candidate_filters as _reset_candidate_filters
from ui.state import _reset_finder_defaults as _reset_finder_defaults
from ui.state import _reset_response_zoom as _reset_response_zoom
from ui.state import _restore_design_state as _restore_design_state
from ui.state import _restore_manual_box as _restore_manual_box
from ui.state import _sealed_box_from_state as _sealed_box_from_state
from ui.state import _select_load_type_card as _select_load_type_card
from ui.state import _select_workspace as _select_workspace
from ui.state import _set_box_strategy_state as _set_box_strategy_state
from ui.state import _single_driver_from_state as _single_driver_from_state
from ui.state import _snapshot_design_state as _snapshot_design_state
from ui.state import _snapshot_manual_box as _snapshot_manual_box
from ui.state import _table_value_missing as _table_value_missing
from ui.styles import _focused_port_flare_style as _focused_port_flare_style
from ui.styles import _load_type_card_styles as _load_type_card_styles
from ui.styles import _workspace_tab_styles as _workspace_tab_styles

__all__ = [
    "Path",
    "ProcessPoolExecutor",
    "ThreadPoolExecutor",
    "UTC",
    "_ACCOUNT_STORE",
    "_ALL_LOAD_TYPES",
    "_AUTOSAVE_DEBOUNCE_SECONDS",
    "_AUTOSAVE_RETRY_DELAYS",
    "_AUTO_CURSOR_OPTIONS",
    "_BASS_MATCH_PROJECT_RESULT_KEYS",
    "_BASS_MATCH_PROJECT_STATE_KEYS",
    "_BOX_STRATEGIES",
    "_BRAND_APP_IMAGE",
    "_BRAND_IMAGE",
    "_CATALOG_ADDITIONS_REPORT",
    "_CATALOG_CRAWL_PROGRESS",
    "_CATALOG_CRAWL_REPORT",
    "_CATALOG_PATH_BY_PROVENANCE",
    "_COMMUNITY_TAB_IMAGE",
    "_CURRENT_SAAS_USER",
    "_DEFAULT_REFLEX_Q_ABS",
    "_DEFAULT_REFLEX_Q_LEAK",
    "_DEFAULT_REFLEX_Q_PORT",
    "_DESIGN_COMPARISON_TRACE_COLORS",
    "_EXPLORE_FILTER_DEFAULTS",
    "_FAVICON_PATH",
    "_FINDER_CONTEXT_FILTERED_POOL_VERSION",
    "_FINDER_CTA_LABEL",
    "_FINDER_DEFAULTS",
    "_FINDER_DEFAULTS_VERSION",
    "_FINDER_RANKING_VERSION",
    "_FINDER_RANK_F3",
    "_FINDER_RANK_MODES",
    "_FINDER_RANK_VALUE",
    "_FINDER_SCENARIOS",
    "_FINDER_SPL_PREFILTER_HEADROOM_DB",
    "_LFP_FORMAT_VERSION",
    "_LFP_MAX_SAVED_BATCH_RESULTS",
    "_LIBRARY_TABLE_MAX_ROWS",
    "_LOAD_IMAGE_DIR",
    "_LOAD_TYPE_IMAGES",
    "_LOAD_TYPE_SHORT",
    "_LOAD_TYPE_SLUGS",
    "_LOCAL_ACCOUNT_SESSION_KEY",
    "_MAX_COMPARISON_DESIGNS",
    "_MAX_PINNED_CHART_ROWS",
    "_MAX_PINNED_RESPONSES",
    "_NUDGE_KEY_SUFFIXES",
    "_OPTIMIZER_ENGINE_REVISION",
    "_OPT_OBJECTIVE_LABELS",
    "_PARAM_PREFIXES",
    "_PIN_TRACE_COLORS",
    "_PORT_GEOMETRY_COLUMNS",
    "_PORT_TRACE_OPTIONS",
    "_PRESET_CLASS_ENGINE_VALUES",
    "_PRESET_CLASS_FILTERS",
    "_PRESET_CLASS_FILTER_ALIASES",
    "_PRESET_FAMILY_ORDER",
    "_PRESET_FILTER_NONE",
    "_PRESET_SELECT_MAX_OPTIONS",
    "_PRESET_SIZE_FILTERS",
    "_PRESET_SOURCE_FILTERS",
    "_PRESET_SOURCE_FILTER_ALIASES",
    "_PRICE_CURRENCY_DEFAULTS_VERSION",
    "_PROJECT_TRANSIENT_STATE_KEYS",
    "_PROJECT_TRANSIENT_STATE_PREFIXES",
    "_RESONATOR_PORT",
    "_RESONATOR_PR",
    "_RESONATOR_RESPONSE_TRACES",
    "_RESONATOR_TYPES",
    "_RESPONSE_DEFAULTS_VERSION",
    "_RESPONSE_TRACE_OPTIONS",
    "_RESTRICTED_THIRD_PARTY_SOURCES",
    "_RETAILER_CRAWL_REPORT",
    "_SAAS_SETTINGS",
    "_SAAS_SOURCE_TOKEN",
    "_SAVE_STATUS_LABELS",
    "_STL_SPLIT_LABELS",
    "_TABLE_NUMBER_FORMATS",
    "_TRACE_COLORS",
    "_UNTITLED_PROJECT_NAME",
    "_VERSION",
    "_WORKSPACES",
    "_WORKSPACE_DISPLAY_LABELS",
    "_WORKSPACE_TAB_IMAGES",
    "_WORKSPACE_TAB_SLUGS",
    "_account_admin_emails",
    "_acoustics",
    "_active_design_comparison_color",
    "_active_design_visible",
    "_add_finder_designs_to_comparison",
    "_afw_compare",
    "_afw_export",
    "_alignment_uses_optimizer",
    "_alignment_warning",
    "_all_available_preset_families",
    "_all_preset_price_currencies",
    "_all_preset_price_values",
    "_apply_alignment",
    "_apply_bandpass4_alignment",
    "_apply_bandpass6_alignment",
    "_apply_bandpass8_alignment",
    "_apply_batch_result",
    "_apply_cloud_record",
    "_apply_driver_preset",
    "_apply_empirical_box_for",
    "_apply_finder_scenario",
    "_apply_lfp_project",
    "_apply_library_driver",
    "_apply_library_pr",
    "_apply_loaded_params",
    "_apply_optimized_box",
    "_apply_optimized_port_geometry",
    "_apply_pending_atlas_point",
    "_apply_pending_batch_comparison",
    "_apply_pending_batch_result",
    "_apply_pending_cloud_record",
    "_apply_pr_combo",
    "_apply_reflex_alignment",
    "_apply_sealed_alignment",
    "_apply_suggested_box_for",
    "_atlas_frame",
    "_atlas_loss_signature",
    "_auto_align_current_driver",
    "_auto_alignment_signature",
    "_available_driver_preset_names",
    "_available_preset_families",
    "_available_workspaces",
    "_band_layer",
    "_bandpass4_box_from_state",
    "_bandpass6_box_from_state",
    "_bandpass8_box_from_state",
    "_bass_match_results_signature",
    "_batch_dccav_box",
    "_batch_rank_presets",
    "_batch_rank_presets_parallel",
    "_batch_rank_presets_with_progress",
    "_billing",
    "_box_from_params",
    "_box_from_state",
    "_box_number_with_nudge",
    "_box_strategy_is_auto",
    "_build_lfp_project",
    "_cached_account_store",
    "_cached_project_store",
    "_cached_public_store",
    "_catalog_path_for_preset",
    "_catalog_record_display_identity",
    "_chart_signature",
    "_clean_display_table_frame",
    "_clean_style_str",
    "_clear_active_project_state",
    "_clear_pinned_responses",
    "_click_marker_layer",
    "_cloud_autosave_step",
    "_cloud_persistence_error_message",
    "_cloud_persistence_fragment",
    "_cloud_project_summaries",
    "_collect_bass_match_project_state",
    "_collect_params",
    "_community_tab_image_b64",
    "_compact_result_row",
    "_create_new_project",
    "_csv_bytes",
    "_current_exchange_rates",
    "_current_optimizer_alternatives",
    "_current_optimizer_summary",
    "_cursor_label_rows",
    "_cursor_layer",
    "_cursor_row",
    "_cursor_rows",
    "_decode_share_payload",
    "_deduplicate_finder_preset_names",
    "_deduplicate_finder_preset_names_tuple",
    "_deduplicate_finder_result_rows",
    "_default",
    "_delete_active_design_comparison_tab",
    "_delete_design_comparison_tab",
    "_derive_project_acoustic_metrics",
    "_design_comparison_tab_colors",
    "_design_comparison_tab_label",
    "_design_comparison_tabs",
    "_design_crw_download",
    "_design_crw_parameters",
    "_design_crw_signature",
    "_design_driver_parameter_signature",
    "_design_objective_label",
    "_design_simulation_signature",
    "_design_space_cached",
    "_design_tab_label_driver",
    "_design_tab_parameters_match_preset",
    "_detach_cloud_project",
    "_driver_catalog_mapping",
    "_driver_class_label",
    "_driver_coverage_summary",
    "_driver_from_params",
    "_driver_from_state",
    "_driver_library_frame",
    "_driver_preset_class",
    "_driver_preset_currency",
    "_driver_preset_display_label",
    "_driver_preset_exact_source",
    "_driver_preset_family",
    "_driver_preset_identity_fields",
    "_driver_preset_price",
    "_driver_preset_size",
    "_driver_preset_source",
    "_drop_finder_worker_pool",
    "_duplicate_active_design_comparison",
    "_duplicate_active_project",
    "_duplicate_design_comparison_tab",
    "_duplicate_design_tab_from_click",
    "_duplicate_standalone_design_from_click",
    "_encode_share_payload",
    "_end_design_comparison",
    "_engine",
    "_ensure_finder_defaults",
    "_ensure_plot_control_state",
    "_ensure_price_currency_default",
    "_expand_y_domain_for_pins",
    "_explore_optional_limit",
    "_filter_driver_preset_names",
    "_filter_finder_performance_rows",
    "_finder_box_value",
    "_finder_brief_constraints",
    "_finder_candidate_precheck",
    "_finder_controls_signature",
    "_finder_driver_identity",
    "_finder_executor_backend",
    "_finder_filter_summary",
    "_finder_load_context",
    "_finder_number_input",
    "_finder_optimizer_goals_from_state",
    "_finder_per_load_stats_str",
    "_finder_pool_fingerprint",
    "_finder_prefilter",
    "_finder_preset_preference",
    "_finder_price_currency",
    "_finder_result_context_signature",
    "_finder_result_snapshot",
    "_finder_row_box_params",
    "_finder_row_driver",
    "_finder_search_blocked",
    "_finder_selectbox",
    "_finder_total_volume_l",
    "_finder_value",
    "_finder_worker_limit",
    "_finder_worker_pool",
    "_fmt_db",
    "_fmt_hz",
    "_focused_port_flare_style",
    "_fork_project_to_sandbox",
    "_get_account_store",
    "_get_community_load_image",
    "_get_current_user_account",
    "_get_project_store",
    "_get_public_store",
    "_initialize_alignment_defaults",
    "_interp",
    "_invalidate_bass_match_results_signature",
    "_invalidate_cloud_project_list",
    "_is_param_key",
    "_is_streamlit_community_cloud",
    "_json_safe",
    "_line_chart",
    "_load_type_card_styles",
    "_log_frequency_scale",
    "_maintenance_allowed",
    "_manual_box_keys_for_load_type",
    "_mark_auto_alignment_synced",
    "_mark_cloud_project_dirty",
    "_mark_session_flag",
    "_marker_display_label",
    "_normalize_box_strategy",
    "_normalize_price_frame",
    "_normalize_stl_split_mode",
    "_normalized_preset_price",
    "_on_box_strategy_change",
    "_on_driver_param_change",
    "_on_driver_preset_change",
    "_on_load_type_change",
    "_on_pr_preset_change",
    "_on_workspace_compat_change",
    "_open_billing_modal",
    "_open_community_workspace",
    "_open_manage_projects_workspace",
    "_open_technical_page",
    "_optimized_port_diameter_cm",
    "_optimized_summary",
    "_optimizer_box_signature",
    "_optimizer_context_box",
    "_optimizer_goals_from_state",
    "_optimizer_goals_signature",
    "_optimizer_result_context",
    "_optional_positive",
    "_parse_query_param_str",
    "_passive_radiator_library_frame",
    "_persist_widget_selection",
    "_pin_label",
    "_pinned_layer",
    "_pinned_metric_frame",
    "_pinned_metric_layer",
    "_pinned_response_frame",
    "_pinned_response_snapshot",
    "_pinned_responses",
    "_plot_excursion",
    "_plot_group_delay",
    "_plot_impedance",
    "_plot_mil",
    "_plot_ports",
    "_plot_response",
    "_poll_catalog_refresh",
    "_port_cad",
    "_port_geometry_row",
    "_port_series",
    "_pr_box_from_state",
    "_prefilter_finder_candidate_pools",
    "_prepare_design_crw_download",
    "_preserve_design_state",
    "_preserve_library_filters",
    "_preset_price_currencies",
    "_preset_price_values",
    "_presets",
    "_pricing",
    "_private_store",
    "_process_project_cover_image",
    "_project_display_name",
    "_project_download_filename",
    "_project_name_is_placeholder",
    "_public_project_url",
    "_purchase_markdown",
    "_queue_atlas_point",
    "_queue_cloud_record_activation",
    "_queue_finder_design_selection",
    "_rank_value",
    "_ranking",
    "_read_json_object",
    "_record_lfp_export",
    "_recover_design_tab_preset",
    "_reflex_box_from_state",
    "_reflex_uses_passive_radiator",
    "_refresh_finder_result_catalog_metadata",
    "_remember_local_account",
    "_remove_pinned_response",
    "_render_atlas_tab",
    "_render_auth_hero_and_badges",
    "_render_authenticated_account_controls",
    "_render_bass_match_hero",
    "_render_billing_action_button",
    "_render_candidate_pool",
    "_render_catalog_crawl_report",
    "_render_catalog_maintenance",
    "_render_cloud_persistence_status",
    "_render_community_sidebar",
    "_render_credits_purchase_popover",
    "_render_design_analysis_tabs",
    "_render_driver_library",
    "_render_driver_mechanical_drawing",
    "_render_editable_design_tabs",
    "_render_embed_project_widget",
    "_render_engine_only_topologies_note",
    "_render_explore_projects_directory",
    "_render_find_driver_actions",
    "_render_find_driver_goal_sidebar",
    "_render_find_driver_target_sidebar",
    "_render_find_driver_workspace",
    "_render_finder_constraint_grid",
    "_render_finder_library_filters",
    "_render_finder_run_statistics",
    "_render_finder_scenario_selector",
    "_render_hud_explore_community_button",
    "_render_load_type_buttons",
    "_render_local_account_gate",
    "_render_main_account_header",
    "_render_manage_projects_cloud_list",
    "_render_manage_projects_history",
    "_render_manage_projects_publish",
    "_render_manage_projects_trash",
    "_render_manage_projects_workspace",
    "_render_optimizer_alternatives",
    "_render_passive_radiator_library",
    "_render_ports_tab",
    "_render_project_menu",
    "_render_public_project_page",
    "_render_public_project_sidebar",
    "_render_response_tab",
    "_render_user_management",
    "_render_workspace_tabs",
    "_request_design_comparison_tab",
    "_request_new_project_name",
    "_reset_candidate_filters",
    "_reset_explore_filters",
    "_reset_finder_defaults",
    "_reset_response_zoom",
    "_resolve_driver_ts",
    "_resolve_saas_user",
    "_response_amplitude_axis",
    "_response_series",
    "_response_tuning_markers",
    "_response_y_domain",
    "_restore_design_state",
    "_restore_manual_box",
    "_run_box_optimizer",
    "_run_find_driver_search",
    "_saas",
    "_sealed_box_from_state",
    "_select_load_type_card",
    "_select_workspace",
    "_selected_library_preset_names",
    "_serialize_bass_match_context",
    "_series_frame",
    "_set_active_cloud_record",
    "_set_box_strategy_state",
    "_set_filter_group_from_all",
    "_set_pinned_response_visible",
    "_share_link_url",
    "_show_advanced_controls",
    "_sign_out_saas",
    "_simulate_design_cached",
    "_simulation_engine_revision",
    "_single_driver_from_state",
    "_size_bucket",
    "_snapshot_design_state",
    "_snapshot_manual_box",
    "_snapshot_revision",
    "_step5",
    "_storage",
    "_sync_active_design_comparison_tab",
    "_sync_auto_alignment_if_needed",
    "_sync_filter_group_all",
    "_sync_filter_multiselect",
    "_sync_finder_library_selection",
    "_table_value_missing",
    "_toggle_community_project_like",
    "_toggle_design_tab_visible",
    "_tolerance_band_cached",
    "_topology_comparison_series",
    "_tuning_marker_layer",
    "_update_active_design_comparison",
    "_update_catalog_driver_from_box_design",
    "_use_manual_box_strategy",
    "_value_sorted_frame",
    "_workspace_tab_styles",
    "alt",
    "atexit",
    "base64",
    "cache",
    "csv",
    "datetime",
    "hashlib",
    "html",
    "importlib",
    "io",
    "json",
    "logger",
    "logging",
    "lru_cache",
    "multiprocessing",
    "np",
    "os",
    "pd",
    "re",
    "st",
    "sys",
    "time",
    "uuid",
    "zlib",
]

_ui_app.main()
