"""Shared UI constants: assets, defaults, labels and catalog paths."""

from __future__ import annotations

from pathlib import Path
import logging

import acoustics as _acoustics
import ranking as _ranking


_PROJECT_ROOT = Path(__file__).resolve().parents[2]


logger = logging.getLogger("load_forge.ui")

_OPTIMIZER_ENGINE_REVISION = 8

_BRAND_IMAGE = _PROJECT_ROOT / "assets" / "load_forge_header.png"

_BRAND_APP_IMAGE = _PROJECT_ROOT / "assets" / "load_forge_header_app.png"

_CATALOG_CRAWL_REPORT = (
    _PROJECT_ROOT / "data" / "autonomous_crawler_latest_report.json"
)

_CATALOG_CRAWL_PROGRESS = (
    _PROJECT_ROOT / "data" / "autonomous_crawler_progress.json"
)

_RETAILER_CRAWL_REPORT = (
    _PROJECT_ROOT / "data" / "retailer_discovery_latest_report.json"
)

_CATALOG_ADDITIONS_REPORT = (
    _PROJECT_ROOT / "data" / "catalog_additions_latest_report.json"
)

_LOAD_IMAGE_DIR = _PROJECT_ROOT / "assets" / "load_types"

_WORKSPACE_TAB_IMAGES = {
    "Bass Match": _PROJECT_ROOT / "assets" / "bass_match_tab.png",
    "Box Design": _PROJECT_ROOT / "assets" / "box_design_tab.png",
}

_STL_SPLIT_LABELS = {
    "full": "Single piece (Full port)",
    "half": "2-piece symmetric halves (L/2 for 3D print)",
    "flange_only": "Outer Flange Coupling Only",
}

_FAVICON_PATH = _PROJECT_ROOT / "assets" / "load_forge_favicon.png"

_LOCAL_ACCOUNT_SESSION_KEY = "_local_saas_account"

_PARAM_PREFIXES = (
    "driver_", "box_", "reflex_", "pr_", "bandpass4_", "bandpass6_", "bp8_", "sealed_", "loss_", "sim_", "opt_", "load_type"
)

_RESPONSE_TRACE_OPTIONS = ("Total", "Cone", "Lower port")

_RESONATOR_RESPONSE_TRACES = {
    "Lower port",
    "Vent",
    "Passive radiator",
    "Front port",
}

_PORT_TRACE_OPTIONS = ("Upper port", "Lower port")

_AUTO_CURSOR_OPTIONS = ("F3", "F6", "F10")

_RESPONSE_DEFAULTS_VERSION = 1

_MAX_PINNED_RESPONSES = 8

_MAX_COMPARISON_DESIGNS = 8

_MAX_PINNED_CHART_ROWS = 4800

_PIN_TRACE_COLORS = (
    "#9aa0a6", "#ffb703", "#8ecae6", "#fb8500",
    "#c77dff", "#80ed99", "#10b981", "#a8dadc",
)

_DEFAULT_REFLEX_Q_ABS = 15.0

_DEFAULT_REFLEX_Q_LEAK = 1000.0

_DEFAULT_REFLEX_Q_PORT = 15.0

_LOAD_TYPE_IMAGES = {
    "Infinite baffle": _LOAD_IMAGE_DIR / "infinite_baffle.png",
    "Sealed": _LOAD_IMAGE_DIR / "sealed.png",
    "Bass reflex": _LOAD_IMAGE_DIR / "bass_reflex.png",
    "Bandpass 4th order": _LOAD_IMAGE_DIR / "bandpass_4th.png",
    "Bandpass 6th order": _LOAD_IMAGE_DIR / "bandpass_6th.png",
    "Bandpass 8th order": _LOAD_IMAGE_DIR / "bandpass_8th.png",
    "DCCAV": _LOAD_IMAGE_DIR / "dccav.png",
}

_LOAD_TYPE_SLUGS = {
    "Infinite baffle": "infinite_baffle",
    "Sealed": "sealed",
    "Bass reflex": "bass_reflex",
    "Bandpass 4th order": "bandpass_4th",
    "Bandpass 6th order": "bandpass_6th",
    "Bandpass 8th order": "bandpass_8th",
    "DCCAV": "dccav",
}

_LOAD_TYPE_SHORT = {
    "Infinite baffle": "Infinite baffle",
    "Sealed": "Sealed",
    "Bass reflex": "Reflex",
    "Bandpass 4th order": "BP4",
    "Bandpass 6th order": "BP6",
    "Bandpass 8th order": "BP8",
    "DCCAV": "DCCAV",
}

_ALL_LOAD_TYPES = ["Infinite baffle", "Sealed", "Bass reflex",
                   "Bandpass 4th order", "Bandpass 6th order", "Bandpass 8th order", "DCCAV"]

_RESONATOR_PORT = "Port"

_RESONATOR_PR = "Passive radiator"

_RESONATOR_TYPES = (_RESONATOR_PORT, _RESONATOR_PR)

_TRACE_COLORS = {
    "Total": "#10b981",
    "Cone": "#7cc7ff",
    "Lower port": "#006edb",
    "Vent": "#006edb",
    "MOL": "#b8f26d",
    "MIL": "#e0aaff",
    "Group delay": "#f2c14e",
    "Upper port": "#8ecaff",
    "Impedance": "#355070",
    "Excursion": "#b35c00",
    "DCCAV": "#10b981",
    "Bandpass 4th order": "#58d68d",
    "Bandpass 6th order": "#f2c14e",
    "Bandpass 8th order": "#ff9f1c",
    "Bass reflex": "#7cc7ff",
    "Sealed": "#b8f26d",
    "Infinite baffle": "#e0aaff",
}

_DESIGN_COMPARISON_TRACE_COLORS = (
    _TRACE_COLORS["Total"],
    *tuple(
        color
        for color in _PIN_TRACE_COLORS
        if color != _TRACE_COLORS["Total"]
    ),
)

_PRESET_FAMILY_ORDER = (
    "All",
    "Aiyima",
    "Beyma",
    "Turbosound",
    "Scan-Speak",
    "Dayton Audio",
    "SB Audience",
    "LaVoce",
    "MarkAudio",
    "KEF",
    "Other",
)

_PRESET_SIZE_FILTERS = (
    "All",
    "1 in",
    "2 in",
    "3 in",
    "4 in",
    "5 in",
    "6 in",
    "8 in",
    "10 in",
    "12 in",
    "15 in",
    "18 in",
    "21 in",
)

_PRESET_SOURCE_FILTERS = ("All", *_acoustics.PRESET_PROVENANCE_CATEGORIES)

_PRESET_SOURCE_FILTER_ALIASES = {
    # Saved sessions from before Load Forge-owned sources were consolidated.
    "Manufacturer": "Load Forge database",
    "Built-in": "Load Forge database",
    "Official manufacturer site": "Load Forge database",
    "Official archive / heritage": "Load Forge database",
    "Retailer / distributor": "Load Forge database",
    "User supplied": "Load Forge database",
    "Z Bench Measurement": "Z Bench",
    "Z Bench measured": "Z Bench",
    "Z-Bench": "Z Bench",
    "Loudspeaker Database": "LSDB",
}

_PRESET_FILTER_NONE = "__none__"

_PRESET_CLASS_FILTERS = ("All", "Subwoofer", "Woofer", "Midbass")

_PRESET_CLASS_FILTER_ALIASES = {
    "Midbass-capable": "Midbass",
}

_PRESET_CLASS_ENGINE_VALUES = {
    "Midbass": "Midbass-capable",
}

_WORKSPACES = ("Bass Match", "Box Design")

_WORKSPACE_DISPLAY_LABELS = {
    "Manage Projects": "Manage Projects",
    "Bass Match": "Bass Match",
    "Box Design": "Box Design",
    "Catalog Maintenance": "Catalog Maintenance",
    "User Management": "User Management (Admin)",
}

_WORKSPACE_TAB_SLUGS = {
    "Manage Projects": "manage_projects",
    "Bass Match": "bass_match",
    "Box Design": "box_design",
    "Catalog Maintenance": "catalog_maintenance",
    "User Management": "user_management",
}

_CATALOG_PATH_BY_PROVENANCE = {
    "LSDB": "catalog_lsdb.json",
    "Load Forge database": "catalog_proprietario.json",
    "VituixCAD": "catalog_vituixcad.json",
    "Speaker Box Lite": "catalog_speakerboxlite.json",
}

_OPT_OBJECTIVE_LABELS = {
    "Max extension": "extension",
    "Balanced": "balanced",
    "Flattest": "flat",
}

_BOX_STRATEGIES = (*_OPT_OBJECTIVE_LABELS, "Manual")

_FINDER_RANK_F3 = "Deepest bass (F3)"

_FINDER_RANK_VALUE = "Best value (F3 × price)"

_FINDER_RANK_MODES = (_FINDER_RANK_F3, _FINDER_RANK_VALUE)

_FINDER_CTA_LABEL = "Run Bass Match"

_FINDER_RANKING_VERSION = 11

_FINDER_CONTEXT_FILTERED_POOL_VERSION = "user-inputs-v2"

_FINDER_SPL_PREFILTER_HEADROOM_DB = _acoustics.FINDER_SPL_PREFILTER_HEADROOM_DB

_FINDER_DEFAULTS_VERSION = 10

_PRICE_CURRENCY_DEFAULTS_VERSION = 1

_FINDER_DEFAULTS = {
    "finder_rank_mode": _FINDER_RANK_F3,
    "finder_volume_l": 40.0,
    "finder_objective": "Max extension",
    "finder_search_profile": _ranking.SEARCH_PROFILE_STANDARD,
    "finder_voltage": 2.83,
    "finder_max_ripple_db": 3.0,
    "finder_max_ripple_freq_hz": 0.0,
    "finder_excursion_ratio": 1.0,
    "finder_max_gd_ms": 30.0,
    "finder_min_spl_db": 0.0,
    "finder_min_mol_f3_db": 0.0,
    "finder_max_f3_hz": 0.0,
    "finder_fast_prefilter": True,
    "finder_max_mms_g": 0.0,
    "finder_max_le_mh": 0.0,
    "finder_f_min": 10.0,
    "finder_f_max": 300.0,
    "finder_points": 240,
    "finder_reflex_resonator_type": _RESONATOR_PORT,
    "finder_driver_configuration": "Single driver",
}

_NUDGE_KEY_SUFFIXES = ("_minus_3", "_plus_3")

_BASS_MATCH_PROJECT_STATE_KEYS = {
    *_FINDER_DEFAULTS,
    "finder_load_types",
    "preset_search",
    "preset_family_filter",
    "preset_source_filter",
    "preset_size_filter",
    "preset_class_filter",
    "preset_price_enabled",
    "preset_max_price",
    "preset_price_currency",
    "workspace_mode",
    "design_comparison_tabs",
    "design_comparison_active_id",
    "design_comparison_loaded_id",
}

_BASS_MATCH_PROJECT_RESULT_KEYS = (
    "batch_results",
    "batch_result_context",
    "batch_search_completed",
    "finder_last_run_stats",
)

_PROJECT_TRANSIENT_STATE_PREFIXES = (
    "plot_",
    "cursor_",
    "atlas_",
)

_PROJECT_TRANSIENT_STATE_KEYS = {
    "pinned_response",
    "pinned_responses",
    "standalone_design_visible",
    "_manual_box_snapshots",
    "_auto_align_signature",
    "_auto_box_error",
    "_opt_last_context",
    "_previous_box_strategy",
    "_response_defaults_version",
}

_LFP_FORMAT_VERSION = 2

_LFP_MAX_SAVED_BATCH_RESULTS = 100

_AUTOSAVE_DEBOUNCE_SECONDS = 1.5

_AUTOSAVE_RETRY_DELAYS = (2.0, 5.0, 15.0)

_SAVE_STATUS_LABELS = {
    "saved": "Saved",
    "saving": "Saving…",
    "unsaved": "Unsaved changes",
    "retrying": "Save failed — retrying",
    "failed": "Save failed",
    "conflict": "Save conflict",
    "name_required": "Project name required",
}

_UNTITLED_PROJECT_NAME = "Untitled project"

_COMMUNITY_TAB_IMAGE = _PROJECT_ROOT / "assets" / "community_tab.png"

_RESTRICTED_THIRD_PARTY_SOURCES = frozenset({"LSDB", "VituixCAD", "Speaker Box Lite"})

_PORT_GEOMETRY_COLUMNS = ("Port", "Diameter cm", "Length cm", "Peak m/s", "Peak m/s (MOL)", "Peak at Hz")

_FINDER_SCENARIOS: dict[str, dict | None] = {
    "Custom": None,
    "Home theater": {
        "finder_objective": "Max extension",
        "finder_volume_l": 60.0,
        "finder_max_ripple_db": 3.0,
        "finder_max_ripple_freq_hz": 80.0,
        "finder_excursion_ratio": 1.0,
        "finder_max_gd_ms": 30.0,
        "finder_min_spl_db": 0.0,
        "finder_load_types": ["Bass reflex", "DCCAV"],
        "load_type": "Bass reflex",
    },
    "Car SPL": {
        "finder_objective": "Max extension",
        "finder_volume_l": 40.0,
        "finder_max_ripple_db": 4.0,
        "finder_max_ripple_freq_hz": 60.0,
        "finder_excursion_ratio": 1.0,
        "finder_max_gd_ms": 35.0,
        "finder_min_spl_db": 90.0,
        "finder_load_types": ["Bass reflex", "Bandpass 8th order"],
        "load_type": "Bass reflex",
    },
    "Hi-Fi": {
        "finder_objective": "Flattest",
        "finder_volume_l": 40.0,
        "finder_max_ripple_db": 2.0,
        "finder_max_ripple_freq_hz": 0.0,
        "finder_excursion_ratio": 1.0,
        "finder_max_gd_ms": 25.0,
        "finder_min_spl_db": 0.0,
        "finder_load_types": ["Bass reflex", "Sealed"],
        "load_type": "Bass reflex",
    },
    "Infinite baffle": {
        "finder_objective": "Balanced",
        "finder_load_types": ["Infinite baffle"],
        "load_type": "Infinite baffle",
    },
}

_LIBRARY_TABLE_MAX_ROWS = 500

_PRESET_SELECT_MAX_OPTIONS = 1000

_TABLE_NUMBER_FORMATS = {
    "Nominal in": ".1f", "Size in": ".1f", "Sd cm²": ".1f", "Effective Ø in": ".2f",
    "Fs Hz": ".1f", "Qts": ".3f", "Vas L": ".1f",
    "SPL dB": ".0f", "F3 Hz": ".1f", "Ripple dB": ".1f",
    "MOL @ F3 dB": ".1f", "Peak dB": ".1f",
    "Price": ".2f", "Value": ".0f",
    "Min ohm": ".2f", "Vb L": ".2f",
    "Vtot L": ".2f",
    "Fb Hz": ".1f", "Fc Hz": ".1f", "Qtc": ".3f", "Vs L": ".2f",
    "Vp L": ".2f", "Fp Hz": ".1f", "Vr L": ".2f", "Fr Hz": ".1f",
    "Vh L": ".2f", "fh Hz": ".1f", "Vl L": ".2f", "fl Hz": ".1f",
    "Mms g": ".1f", "Le10k mH": ".2f", "Data %": ".0f",
}

_EXPLORE_FILTER_DEFAULTS = {
    "explore_search_input": "",
    "explore_topo_filter": "All",
    "explore_sort_filter": "newest",
    "explore_min_vb_l": 0.0,
    "explore_max_vb_l": 0.0,
    "explore_min_fb_hz": 0.0,
    "explore_max_fb_hz": 0.0,
    "explore_min_size_in": 0.0,
    "explore_max_size_in": 0.0,
    "explore_min_fs_hz": 0.0,
    "explore_max_fs_hz": 0.0,
    "explore_min_qts": 0.0,
    "explore_max_qts": 0.0,
    "explore_min_f3_hz": 0.0,
    "explore_max_f3_hz": 0.0,
}
