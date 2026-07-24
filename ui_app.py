"""
Load Forge — acoustic-load simulator.

Single-page Streamlit dashboard for DCCAV, fourth/sixth-order bandpass,
bass-reflex, passive-radiator, sealed and infinite-baffle loads, with response
plots and derived data.
"""

from __future__ import annotations

import atexit
import base64
import csv
import hashlib
import importlib
import io
import json
import logging
import multiprocessing
import os
import sys
import time
import zlib
from concurrent.futures import ProcessPoolExecutor
from functools import cache
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

logger = logging.getLogger("load_forge.ui")
_OPTIMIZER_ENGINE_REVISION = 3

sys.path.insert(0, str(Path(__file__).parent / "src"))
import dccav as _dccav
import engine as _engine
import presets as _presets
import pricing as _pricing
import ranking as _ranking

sys.path.insert(0, str(Path(__file__).parent / "tools"))
import generate_afw_dccav as _afw_export


def _reload_if_source_changed(module) -> None:
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
        return
    if getattr(module, "_load_forge_reload_mtime", None) != mtime:
        importlib.reload(module)
        module._load_forge_reload_mtime = mtime


# Reload dependencies before the facade so it rebinds to the fresh modules.
for _module in (_engine, _pricing, _presets, _ranking, _dccav, _afw_export):
    _reload_if_source_changed(_module)


try:
    _VERSION = (Path(__file__).parent / "VERSION").read_text().strip()
except OSError:
    _VERSION = "dev"
_BRAND_IMAGE = Path(__file__).parent / "assets" / "load_forge_header.png"
_LOAD_IMAGE_DIR = Path(__file__).parent / "assets" / "load_types"
_WORKSPACE_TAB_IMAGES = {
    "Bass Match": Path(__file__).parent / "assets" / "bass_match_tab.png",
    "Box Design": Path(__file__).parent / "assets" / "box_design_tab.png",
}


st.set_page_config(
    page_title=f"Load Forge v{_VERSION}",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={},
)

st.markdown(
    """
    <style>
    @media (max-width: 768px) {
        section[data-testid="stSidebar"],
        section[data-testid="stSidebar"] > div,
        div[data-testid="stSidebarContent"] {
            width: 100vw !important;
            min-width: 100vw !important;
            max-width: 100vw !important;
        }
    }
    .block-container,
    [data-testid="stMainBlockContainer"] {
        padding-top: 0.2rem !important;
        padding-bottom: 0.2rem !important;
    }
    section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
        padding-top: 0 !important;
    }
    section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
        padding-top: 0 !important;
    }
    section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h3 {
        border-top: 1px solid rgba(255,255,255,.10);
        color: rgba(255,255,255,.96);
        font-size: 1rem;
        line-height: 1.25;
        margin: .55rem 0 .35rem !important;
        padding-top: .8rem !important;
        padding-bottom: .3rem !important;
    }
    [data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] {
        gap: .9rem !important;
    }
    section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
        gap: 0.2rem !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stNumberInput"] {
        margin-bottom: -0.2rem !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stSelectbox"] {
        margin-bottom: -0.2rem !important;
    }
    [data-testid="stMainBlockContainer"] [data-testid="stMarkdownContainer"] h1,
    [data-testid="stMainBlockContainer"] [data-testid="stMarkdownContainer"] h2,
    [data-testid="stMainBlockContainer"] [data-testid="stMarkdownContainer"] h3,
    [data-testid="stMainBlockContainer"] [data-testid="stMarkdownContainer"] h4 {
        padding-top: 0.35rem !important;
        padding-bottom: 0.2rem !important;
    }
    section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
    section[data-testid="stSidebar"] label p {
        font-size: 0.83rem !important;
        line-height: 1.3 !important;
        margin-bottom: 0.4rem !important;
    }
    section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {
        line-height: 1.45 !important;
    }
    section[data-testid="stSidebar"] [data-testid="stNumberInput"]
    div[data-baseweb="input"] {
        border-radius: .72rem;
        min-height: 3.15rem;
        overflow: hidden;
    }
    section[data-testid="stSidebar"] [data-testid="stNumberInput"] button {
        align-items: center !important;
        align-self: stretch !important;
        background: rgba(255,255,255,.035) !important;
        border-left: 1px solid rgba(255,255,255,.09) !important;
        border-radius: 0 !important;
        color: rgba(255,255,255,.94) !important;
        display: flex !important;
        height: auto !important;
        justify-content: center !important;
        margin: 0 !important;
        min-width: 2.55rem !important;
        padding: 0 !important;
        transition: background-color .15s ease, color .15s ease;
    }
    section[data-testid="stSidebar"] [data-testid="stNumberInput"] button:hover:not(:disabled) {
        background: rgba(255,59,48,.16) !important;
        color: white !important;
    }
    section[data-testid="stSidebar"] [data-testid="stNumberInput"] button svg {
        height: 1.15rem !important;
        width: 1.15rem !important;
    }
    hr {
        margin-top: 0.5rem !important;
        margin-bottom: 0.5rem !important;
    }

    header[data-testid="stHeader"] {
        background-color: transparent !important;
    }

    [data-testid="stCaptionContainer"] {
        color: rgba(250,250,250,.72);
    }
    .st-key-finder_library_filters {
        background: rgba(255,255,255,.025);
        border-color: rgba(255,255,255,.10) !important;
        margin-block: .25rem .55rem;
    }
    .st-key-finder_library_filters [data-testid="stVerticalBlock"] {
        gap: .55rem !important;
    }

    .st-key-active_load_summary {
        border: 1px solid rgba(127,127,127,.22) !important;
        border-radius: .55rem !important;
        padding: .45rem .6rem .45rem !important;
    }
    .st-key-finder_run_search_main div[data-testid="stButton"] button {
        background: linear-gradient(180deg, #f02a35 0%, #cf111c 100%);
        border: 1px solid rgba(255,255,255,.12);
        box-shadow: 0 .35rem 1rem rgba(207,17,28,.18);
        min-height: 2.8rem;
        transition: filter .16s ease, transform .16s ease, box-shadow .16s ease;
    }
    .st-key-finder_run_search_main div[data-testid="stButton"] button p {
        font-size: clamp(1.02rem, 1.25vw, 1.2rem);
        font-weight: 750;
        letter-spacing: .01em;
    }
    .st-key-finder_run_search_main div[data-testid="stButton"] button:hover {
        box-shadow: 0 .45rem 1.25rem rgba(207,17,28,.28);
        filter: brightness(1.06);
        transform: translateY(-1px);
    }
    .st-key-finder_match_progress [role="progressbar"],
    .st-key-finder_match_progress [data-testid="stProgressBar"] > div {
        border-radius: .6rem !important;
        height: 1.1rem !important;
        min-height: 1.1rem !important;
    }
    .st-key-finder_match_progress [role="progressbar"] > div {
        border-radius: inherit !important;
        height: 100% !important;
    }
    .stMetric { border: 1px solid rgba(127,127,127,.22); padding: .3rem .5rem !important; }
    .stMetric label { font-size: 0.72rem !important; margin-bottom: -0.2rem !important; }
    .stMetric div[data-testid="stMetricValue"] { font-size: 1.05rem !important; line-height: 1.2 !important; padding-bottom: 0.1rem !important; }
    div[data-testid="stTabs"] { gap: 0 !important; }
    button[data-baseweb="tab"] { padding-top: 0.2rem !important; padding-bottom: 0.2rem !important; }
    div[data-testid="stExpander"] details {
        margin-top: 0 !important;
        margin-bottom: 0.2rem !important;
    }
    @media (max-width: 768px) {
        html {
            font-size: 16px !important;
        }
        .block-container,
        [data-testid="stMainBlockContainer"] {
            padding-left: 1rem !important;
            padding-right: 1rem !important;
            padding-top: 1rem !important;
        }
        section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
            padding-top: .75rem !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


_PARAM_PREFIXES = (
    "driver_", "box_", "reflex_", "pr_", "bandpass4_", "bandpass6_", "sealed_", "loss_", "sim_", "opt_", "load_type"
)
_RESPONSE_TRACE_OPTIONS = ("Total", "Cone", "Lower port")
_PORT_TRACE_OPTIONS = ("Upper port", "Lower port")
_AUTO_CURSOR_OPTIONS = ("F3", "F6", "F10")
_RESPONSE_DEFAULTS_VERSION = 1
_MAX_PINNED_RESPONSES = 8
_MAX_PINNED_CHART_ROWS = 4800
_PIN_TRACE_COLORS = (
    "#9aa0a6", "#ffb703", "#8ecae6", "#fb8500",
    "#c77dff", "#80ed99", "#ff758f", "#a8dadc",
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
    "DCCAV": _LOAD_IMAGE_DIR / "dccav.png",
}

_LOAD_TYPE_SLUGS = {
    "Infinite baffle": "infinite_baffle",
    "Sealed": "sealed",
    "Bass reflex": "bass_reflex",
    "Bandpass 4th order": "bandpass_4th",
    "Bandpass 6th order": "bandpass_6th",
    "DCCAV": "dccav",
}

_LOAD_TYPE_SHORT = {
    "Infinite baffle": "Infinite baffle",
    "Sealed": "Sealed",
    "Bass reflex": "Reflex",
    "Bandpass 4th order": "BP4",
    "Bandpass 6th order": "BP6",
    "DCCAV": "DCCAV",
}

_ALL_LOAD_TYPES = ["Infinite baffle", "Sealed", "Bass reflex",
                   "Bandpass 4th order", "Bandpass 6th order", "DCCAV"]
_RESONATOR_PORT = "Port"
_RESONATOR_PR = "Passive radiator"
_RESONATOR_TYPES = (_RESONATOR_PORT, _RESONATOR_PR)


def _reflex_uses_passive_radiator(*, finder: bool = False) -> bool:
    """Return whether the bass-reflex resonator is a passive diaphragm."""
    key = "finder_reflex_resonator_type" if finder else "reflex_resonator_type"
    return st.session_state.get(key, _RESONATOR_PORT) == _RESONATOR_PR


@cache
def _load_type_card_styles() -> str:
    """Return compact clickable-card CSS with the supplied diagrams embedded."""
    rules = [
        """
        <style>
        [class*="st-key-load_card_"] {
            min-height: 6rem;
        }
        [class*="st-key-load_card_"] div[data-testid="stButton"] button {
            background-color: #f2f2f0;
            background-position: center;
            background-repeat: no-repeat;
            background-size: cover;
            border: 1px solid rgba(255,255,255,.16);
            border-radius: .58rem;
            box-shadow: inset 0 1px 0 rgba(255,255,255,.06);
            filter: saturate(.72) brightness(.82) contrast(1.04);
            height: 4.55rem;
            min-height: 4.55rem;
            opacity: .88;
            overflow: hidden;
            padding: 0;
            position: relative;
            transition: border-color .16s ease, box-shadow .16s ease,
                        filter .16s ease, transform .16s ease;
            width: 100%;
        }
        [class*="st-key-load_card_"] div[data-testid="stButton"] button::after {
            display: none;
        }
        [class*="st-key-load_card_"] div[data-testid="stButton"] button p {
            opacity: 0;
        }
        .load-card-label {
            color: rgba(250,250,250,.88);
            font-size: .7rem;
            font-weight: 650;
            line-height: .9rem;
            margin: .2rem 0 .15rem;
            min-height: .9rem;
            text-align: center;
        }
        [class*="st-key-load_card_"] div[data-testid="stButton"] button:hover {
            border-color: #ff3b30;
            box-shadow: 0 .35rem .9rem rgba(0,0,0,.25);
            filter: saturate(.9) brightness(1.02);
            opacity: 1;
            transform: translateY(-1px);
        }
        [class*="st-key-load_card_"] div[data-testid="stButton"] button[data-testid="stBaseButton-primary"] {
            border: 2px solid #ff3b30;
            box-shadow: 0 0 0 2px rgba(255,59,48,.20),
                        0 .35rem 1rem rgba(255,59,48,.16);
            filter: none;
            opacity: 1;
        }
        [class*="st-key-load_card_"] div[data-testid="stButton"] button[data-testid="stBaseButton-primary"]::before {
            align-items: center;
            background: #ff3b30;
            border-radius: 50%;
            color: white;
            content: "\\2713";
            display: flex;
            font-size: .62rem;
            font-weight: 900;
            height: 1rem;
            justify-content: center;
            position: absolute;
            right: .2rem;
            top: .2rem;
            width: 1rem;
            z-index: 2;
        }
        [class*="st-key-load_card_"] div[data-testid="stButton"] button:focus-visible {
            outline: 3px solid rgba(255,59,48,.72);
            outline-offset: 2px;
        }
        """
    ]
    for load_type, image_path in _LOAD_TYPE_IMAGES.items():
        if not image_path.exists():
            continue
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        slug = _LOAD_TYPE_SLUGS[load_type]
        rules.append(
            f'.st-key-load_card_{slug} button '
            f'{{ background-image: url("data:image/png;base64,{encoded}"); }}'
        )
    rules.append("</style>")
    return "".join(rules)


def _render_load_type_buttons(active_set: set[str], single_select: bool = False) -> set[str]:
    """Grid of compact load diagrams that are themselves clickable buttons.

    In single-select mode clicking a new button *replaces* the set (radio behaviour).
    In multi-select mode each click toggles the load.
    Returns the (possibly modified) set.
    """
    modified = set(active_set)
    st.markdown(_load_type_card_styles(), unsafe_allow_html=True)
    for row_start, row_end in ((0, 3), (3, len(_ALL_LOAD_TYPES))):
        row_load_types = _ALL_LOAD_TYPES[row_start:row_end]
        row_cols = st.columns(len(row_load_types))
        for offset, lt in enumerate(row_load_types):
            with row_cols[offset]:
                with st.container(key=f"load_card_{_LOAD_TYPE_SLUGS[lt]}"):
                    active = lt in active_set
                    clicked = st.button(
                        _LOAD_TYPE_SHORT[lt],
                        key=f"load_btn_{lt}",
                        type="primary" if active else "secondary",
                        use_container_width=True,
                        help=lt,
                    )
                    st.markdown(
                        f'<div class="load-card-label">{_LOAD_TYPE_SHORT[lt]}</div>',
                        unsafe_allow_html=True,
                    )
                    if clicked:
                        if single_select:
                            modified = {lt}
                        else:
                            if lt in modified:
                                modified.discard(lt)
                            else:
                                modified.add(lt)
    return modified


@cache
def _workspace_tab_styles() -> str:
    """Return the two full-image workspace-tab styles with embedded assets."""
    rules = [
        """
        <style>
        [class*="st-key-workspace_tab_"] div[data-testid="stButton"] button {
            background-color: transparent;
            background-position: center;
            background-repeat: no-repeat;
            background-size: contain;
            border: 1px solid rgba(127,127,127,.30);
            border-radius: .7rem;
            filter: grayscale(18%) brightness(.72);
            height: clamp(3.5rem, 6vw, 5rem);
            min-height: 3.5rem;
            overflow: hidden;
            padding: 0;
            transition: border-color .16s ease, box-shadow .16s ease,
                        filter .16s ease, transform .16s ease;
            width: 100%;
        }
        [class*="st-key-workspace_tab_"] div[data-testid="stButton"] button p {
            opacity: 0;
        }
        [class*="st-key-workspace_tab_"] div[data-testid="stButton"] button:hover {
            border-color: rgba(255,255,255,.70);
            filter: brightness(.94);
            transform: translateY(-1px);
        }
        .st-key-workspace_tab_bass_match div[data-testid="stButton"]
        button[data-testid="stBaseButton-primary"] {
            border: 2px solid #ff202b;
            box-shadow: 0 0 0 1px rgba(255,32,43,.22), 0 0 18px rgba(255,32,43,.16);
            filter: none;
        }
        .st-key-workspace_tab_box_design div[data-testid="stButton"]
        button[data-testid="stBaseButton-primary"] {
            border: 2px solid #00a8ff;
            box-shadow: 0 0 0 1px rgba(0,168,255,.22), 0 0 18px rgba(0,168,255,.16);
            filter: none;
        }
        [class*="st-key-workspace_tab_"] div[data-testid="stButton"]
        button:focus-visible {
            outline: 3px solid rgba(255,255,255,.82);
            outline-offset: 2px;
        }
        .st-key-workspace_compat_control {
            display: none;
        }
        .st-key-workspace_tab_bass_match,
        .st-key-workspace_tab_box_design {
            margin-bottom: -0.75rem;
        }
        .workspace-tab-desc {
            color: rgba(250,250,250,.78);
            font-size: 1rem;
            margin-top: .1rem;
        }
        @media (max-width: 768px) {
            div[data-testid="stHorizontalBlock"]:has(.st-key-workspace_tab_bass_match) {
                flex-direction: column;
            }
            div[data-testid="stHorizontalBlock"]:has(.st-key-workspace_tab_bass_match)
            > div[data-testid="stColumn"] {
                min-width: 100% !important;
                width: 100% !important;
            }
            [class*="st-key-workspace_tab_"] div[data-testid="stButton"] button {
                height: 4.2rem;
                min-height: 4.2rem;
            }
        }
        """
    ]
    for workspace, image_path in _WORKSPACE_TAB_IMAGES.items():
        if not image_path.exists():
            continue
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        slug = _WORKSPACE_TAB_SLUGS[workspace]
        rules.append(
            f'.st-key-workspace_tab_{slug} button '
            f'{{ background-image: url("data:image/png;base64,{encoded}"); }}'
        )
    rules.append("</style>")
    return "".join(rules)


def _select_workspace(workspace: str) -> None:
    """Select a workspace from one of the large visual tabs."""
    if workspace in _WORKSPACES:
        st.session_state["workspace_mode"] = workspace


def _render_workspace_tabs() -> None:
    """Render image tabs while retaining the state-compatible control."""
    st.markdown(_workspace_tab_styles(), unsafe_allow_html=True)
    active = str(st.session_state.get("workspace_mode", "Bass Match"))
    descriptions = {
        "Bass Match": "Find the right driver for your performance target.",
        "Box Design": "Simulate and refine your acoustic alignment.",
    }
    tab_columns = st.columns(2, gap="small")
    for column, workspace in zip(tab_columns, _WORKSPACES, strict=True):
        slug = _WORKSPACE_TAB_SLUGS[workspace]
        with column:
            with st.container(key=f"workspace_tab_{slug}"):
                st.button(
                    _WORKSPACE_DISPLAY_LABELS[workspace],
                    key=f"workspace_tab_button_{slug}",
                    type="primary" if workspace == active else "secondary",
                    use_container_width=True,
                    help=descriptions[workspace],
                    on_click=_select_workspace,
                    args=(workspace,),
                )
    # Keep this widget in the app tree for old sessions and automated clients.
    # CSS hides it from people because the image tabs are the primary control.
    with st.container(key="workspace_compat_control"):
        st.segmented_control(
            "Workspace",
            _WORKSPACES,
            format_func=lambda value: _WORKSPACE_DISPLAY_LABELS.get(value, value),
            key="workspace_mode",
            label_visibility="collapsed",
            width="stretch",
        )

_TRACE_COLORS = {
    "Total": "#f28e8e",
    "Cone": "#7cc7ff",
    "Lower port": "#006edb",
    "Vent": "#006edb",
    "MOL": "#b8f26d",
    "MIL": "#e0aaff",
    "Group delay": "#f2c14e",
    "Upper port": "#8ecaff",
    "Impedance": "#355070",
    "Excursion": "#b35c00",
    "DCCAV": "#f28e8e",
    "Bandpass 4th order": "#58d68d",
    "Bandpass 6th order": "#f2c14e",
    "Bass reflex": "#7cc7ff",
    "Sealed": "#b8f26d",
    "Infinite baffle": "#e0aaff",
}
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
_PRESET_SOURCE_FILTERS = ("All", "Built-in", "Loudspeaker Database", "Manufacturer")
# Raw preset "source" values bucketed for the filter dropdown above. Anything
# not "Built-in" or "Loudspeaker Database" (e.g. "Manufacturer website",
# "Manufacturer datasheet", "Manufacturer crawl", the generic crawler
# default "Web crawler") falls into "Manufacturer".
_PRESET_SOURCE_EXACT_BUCKETS = {"Built-in", "Loudspeaker Database"}
_PRESET_CLASS_FILTERS = ("All", *_dccav.DRIVER_CLASSES)
_WORKSPACES = ("Bass Match", "Box Design")
_WORKSPACE_DISPLAY_LABELS = {
    "Bass Match": "Bass Match",
    "Box Design": "Box Design",
}
_WORKSPACE_TAB_SLUGS = {
    "Bass Match": "bass_match",
    "Box Design": "box_design",
}
# One box algorithm: the optimizer, with three selectable objectives.  The
# labels map onto engine OptimizationGoals.objective; Manual unlocks fields.
_OPT_OBJECTIVE_LABELS = {
    "Max extension": "extension",
    "Balanced": "balanced",
    "Flattest": "flat",
}
_BOX_STRATEGIES = (*_OPT_OBJECTIVE_LABELS, "Manual")
_FINDER_RANK_F3 = "Deepest bass (F3)"
_FINDER_RANK_VALUE = "Best value (F3 × price)"
_FINDER_RANK_MODES = (_FINDER_RANK_F3, _FINDER_RANK_VALUE)
_FINDER_CTA_LABEL = "Run a Match"
_FINDER_RANKING_VERSION = 3
_FINDER_DEFAULTS_VERSION = 5
_FINDER_DEFAULTS = {
    "finder_rank_mode": _FINDER_RANK_F3,
    "finder_volume_l": 40.0,
    "finder_objective": "Balanced",
    "finder_voltage": 2.83,
    "finder_target_f3_hz": 0.0,
    "finder_max_ripple_db": 3.0,
    "finder_excursion_ratio": 1.0,
    "finder_max_gd_ms": 30.0,
    "finder_min_spl_db": 0.0,
    "finder_f_min": 10.0,
    "finder_f_max": 300.0,
    "finder_result_count": 20,
    "finder_points": 240,
    "finder_reflex_resonator_type": _RESONATOR_PORT,
}


_NUDGE_KEY_SUFFIXES = ("_minus_3", "_plus_3")


def _is_param_key(key: str) -> bool:
    if not any(key.startswith(prefix) for prefix in _PARAM_PREFIXES):
        return False
    # Ignore legacy nudge-button state left by sessions/projects created
    # before box fields switched to the integrated number-input stepper.
    return not key.endswith(_NUDGE_KEY_SUFFIXES)


def _normalize_box_strategy(value) -> str:
    """Map v0.3 strategy names onto the objective-based strategies."""
    value = str(value)
    if value in _BOX_STRATEGIES:
        return value
    if value == "Optimized":
        objective = str(st.session_state.get("opt_objective", "Balanced"))
        return objective if objective in _OPT_OBJECTIVE_LABELS else "Balanced"
    # v0.3 "Suggested" (empirical starter) and unknown values.
    return "Balanced"


def _set_box_strategy_state(strategy: str) -> None:
    """Store a strategy plus the legacy keys older .lfp files round-trip."""
    previous = str(st.session_state.get("box_strategy", "Balanced"))
    st.session_state["box_strategy"] = strategy
    st.session_state["_previous_box_strategy"] = previous
    auto = strategy in _OPT_OBJECTIVE_LABELS
    st.session_state["sim_auto_align"] = auto
    st.session_state["opt_align_mode"] = (
        "Optimized (goals)" if auto else "Empirical (article)"
    )
    if auto:
        st.session_state["opt_objective"] = strategy


def _box_strategy_is_auto() -> bool:
    return str(st.session_state.get("box_strategy", "Balanced")) in _OPT_OBJECTIVE_LABELS


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
    _apply_loaded_params(backup)
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


def _apply_loaded_params(data: dict) -> int:
    legacy_passive_radiator = data.get("load_type") == "Passive radiator"
    applied = 0
    for key, value in data.items():
        if _is_param_key(key):
            if key == "load_type" and value in ("Suspension pneumatic", "Acoustic suspension"):
                value = "Sealed"
            elif key == "load_type" and value == "Passive radiator":
                value = "Bass reflex"
            st.session_state[key] = value
            applied += 1
    if legacy_passive_radiator:
        st.session_state["reflex_resonator_type"] = _RESONATOR_PR
        if "pr_vb_l" in data and "reflex_vb_l" not in data:
            st.session_state["reflex_vb_l"] = float(data["pr_vb_l"])
    # v0.2 presets used two overlapping controls for the same decision and
    # v0.3 offered a starter-based "Suggested" next to one "Optimized" mode.
    # Both collapse onto the single optimizer-objective strategy control.
    if "box_strategy" not in data:
        if st.session_state.get("sim_auto_align", True):
            strategy = "Balanced"
        elif st.session_state.get("opt_align_mode") == "Optimized (goals)":
            strategy = _normalize_box_strategy("Optimized")
        else:
            strategy = "Manual"
    else:
        strategy = _normalize_box_strategy(st.session_state.get("box_strategy", "Balanced"))
    _set_box_strategy_state(strategy)
    if strategy in _OPT_OBJECTIVE_LABELS:
        # A loaded auto box may predate the current engine or come from the
        # retired starter algorithm: force the sidebar refresh to re-derive
        # it with the one active optimizer.
        st.session_state["_optimizer_engine_revision"] = 0
    return applied


def _encode_share_payload() -> str:
    payload = json.dumps(_collect_params(), sort_keys=True, separators=(",", ":"))
    packed = zlib.compress(payload.encode("utf-8"), 9)
    return base64.urlsafe_b64encode(packed).decode("ascii").rstrip("=")


def _share_link_url(token: str) -> str:
    """Best-effort absolute share link; falls back to a relative query string."""
    try:
        base = str(st.context.url or "").split("?", 1)[0]
    except Exception:
        base = ""
    return f"{base}?d={token}"


def _decode_share_payload(token: str) -> dict:
    padded = token + "=" * (-len(token) % 4)
    payload = zlib.decompress(base64.urlsafe_b64decode(padded.encode("ascii")))
    data = json.loads(payload.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Share payload must be a parameter mapping")
    return data


def _render_project_menu() -> None:
    """Keep occasional project actions in the sidebar, away from workspaces."""
    with st.popover("Project", use_container_width=True):
        preset = {"_load_forge_meta": {"version": _VERSION, "format": 1}, **_collect_params()}
        st.download_button(
            "Save preset",
            json.dumps(preset, indent=2).encode("utf-8"),
            "load_forge.lfp",
            "application/json",
            use_container_width=True,
        )
        if st.button(
            "Share via URL",
            key="project_share_url",
            use_container_width=True,
            help="Encodes the current design into the page URL and shows the "
                 "link below, ready to copy.",
        ):
            token = _encode_share_payload()
            st.session_state["_applied_share_token"] = token
            st.query_params["d"] = token
            st.toast("Share link ready - copy it below")
        active_share_token = st.query_params.get("d")
        if active_share_token:
            st.code(_share_link_url(str(active_share_token)), language=None)
            if st.button(
                "Clear share link",
                key="project_clear_share_url",
                use_container_width=True,
            ):
                st.session_state["_applied_share_token"] = None
                st.query_params.pop("d", None)
                st.rerun()
        upload = st.file_uploader("Load preset", type=["lfp", "json"])
        if upload is not None:
            try:
                payload = json.loads(upload.getvalue().decode("utf-8"))
                payload.pop("_load_forge_meta", None)
                _snapshot_design_state()
                count = _apply_loaded_params(payload)
                st.toast(f"Loaded {count} parameters")
                st.rerun()
            except Exception as exc:
                logger.exception("Invalid preset")
                st.error(f"Invalid preset: {exc}")
        if st.session_state.get("_design_state_backup"):
            if st.button(
                "Restore previous design",
                key="project_restore_previous_design",
                use_container_width=True,
                help="Undo the last preset or shared-link load and restore the previous parameters.",
            ):
                _restore_design_state()
                st.toast("Previous design restored")
                st.rerun()


def _chart_signature() -> str:
    prefixes = (
        "driver_", "box_", "reflex_", "sealed_", "loss_", "sim_", "plot_", "cursor_",
        "load_type", "pinned_",
    )
    data = {}
    for key, value in st.session_state.items():
        if not any(key.startswith(prefix) for prefix in prefixes):
            continue
        # Zooming must update the mounted chart in place: remounting inside the
        # response fragment makes Vega measure a collapsed container width.
        if key == "plot_response_window_hz":
            continue
        try:
            json.dumps(value)
        except (TypeError, ValueError):
            continue
        data[key] = value
    payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha1(payload).hexdigest()[:12]


def _driver_from_state() -> _dccav.DriverTS:
    """Composite driver: per-driver T/S state plus the configuration."""
    return _dccav.apply_driver_configuration(
        _single_driver_from_state(),
        str(st.session_state.get("driver_config", "Single driver")),
    )


def _single_driver_from_state() -> _dccav.DriverTS:
    mode = st.session_state.get("driver_sd_mode", "Diameter")
    sd_cm2 = (
        _dccav.sd_from_diameter(float(st.session_state["driver_diameter_mm"]))
        if mode == "Diameter"
        else float(st.session_state["driver_sd_cm2"])
    )
    return _dccav.DriverTS(
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


def _box_from_state() -> _dccav.DccavBox:
    return _dccav.DccavBox(
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


def _reflex_box_from_state() -> _dccav.ReflexBox:
    use_custom_losses = bool(st.session_state.get("reflex_custom_losses", False))
    return _dccav.ReflexBox(
        vb_l=float(st.session_state["reflex_vb_l"]),
        fb_hz=float(st.session_state["reflex_fb_hz"]),
        q_abs=float(st.session_state["reflex_q_abs"]) if use_custom_losses else _DEFAULT_REFLEX_Q_ABS,
        q_leak=float(st.session_state["reflex_q_leak"]) if use_custom_losses else _DEFAULT_REFLEX_Q_LEAK,
        q_port=float(st.session_state["reflex_q_port"]) if use_custom_losses else _DEFAULT_REFLEX_Q_PORT,
    )


def _pr_box_from_state() -> _dccav.PassiveRadiatorBox:
    return _dccav.PassiveRadiatorBox(
        vb_l=float(st.session_state.get(
            "reflex_vb_l", st.session_state.get("pr_vb_l", 40.0))),
        pr_sp_cm2=float(st.session_state.get("pr_sp_cm2", 200.0)),
        pr_fp_hz=float(st.session_state.get("pr_fp_hz", 20.0)),
        pr_qmp=float(st.session_state.get("pr_qmp", 5.0)),
        pr_mmp_g=float(st.session_state.get("pr_mmp_g", 100.0)),
        pr_xmax_mm=float(st.session_state.get("pr_xmax_mm", 0.0)),
        q_abs=float(st.session_state.get("pr_q_abs", 15.0)),
        q_leak=float(st.session_state.get("pr_q_leak", 1000.0)),
    )


def _sealed_box_from_state() -> _dccav.SealedBox:
    return _dccav.SealedBox(
        vb_l=float(st.session_state["sealed_vb_l"]),
        q_abs=float(st.session_state["sealed_q_abs"]),
        q_leak=float(st.session_state["sealed_q_leak"]),
    )


def _bandpass4_box_from_state() -> _dccav.Bandpass4Box:
    return _dccav.Bandpass4Box(
        vs_l=float(st.session_state["bandpass4_vs_l"]),
        vp_l=float(st.session_state["bandpass4_vp_l"]),
        fp_hz=float(st.session_state["bandpass4_fp_hz"]),
        q_abs_s=float(st.session_state["bandpass4_q_abs_s"]),
        q_abs_p=float(st.session_state["bandpass4_q_abs_p"]),
        q_leak_s=float(st.session_state["bandpass4_q_leak_s"]),
        q_leak_p=float(st.session_state["bandpass4_q_leak_p"]),
        q_port=float(st.session_state["bandpass4_q_port"]),
    )


def _bandpass6_box_from_state() -> _dccav.Bandpass6Box:
    return _dccav.Bandpass6Box(
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
    for key, value in _FINDER_DEFAULTS.items():
        st.session_state[key] = value
    st.session_state["_finder_defaults_version"] = _FINDER_DEFAULTS_VERSION
    st.session_state.pop("batch_results", None)
    st.session_state.pop("batch_result_context", None)
    st.session_state.pop("batch_search_completed", None)


def _ensure_finder_defaults() -> None:
    """Migrate stale Finder widgets without pre-seeding implicit UI minima."""
    if st.session_state.get("_finder_defaults_version") != _FINDER_DEFAULTS_VERSION:
        # Retired v3 widgets: the scan now always covers the whole filtered
        # library and every candidate goes through the optimizer.
        for key in (*_FINDER_DEFAULTS, "finder_candidate_limit", "finder_use_optimizer"):
            st.session_state.pop(key, None)
        st.session_state["_finder_defaults_version"] = _FINDER_DEFAULTS_VERSION
        st.session_state.pop("batch_results", None)
        st.session_state.pop("batch_result_context", None)
        st.session_state.pop("batch_search_completed", None)
    else:
        # Keep conditionally rendered Finder values alive while Design is open.
        for key in _FINDER_DEFAULTS:
            if key in st.session_state:
                st.session_state[key] = st.session_state[key]


def _preserve_design_state() -> None:
    """Keep design widget values alive while the Finder workspace is open.

    Streamlit drops widget-bound state for keyed widgets that skip a rerun:
    without this, one trip through Find a driver silently resets voltage,
    manual box values and T/S edits back to their defaults or widget minima.
    """
    for key in list(st.session_state):
        if _is_param_key(key):
            st.session_state[key] = st.session_state[key]


def _preserve_library_filters() -> None:
    """Keep Finder-only catalog filters while the Design workspace is open."""
    for key in (
        "preset_family_filter",
        "preset_source_filter",
        "preset_size_filter",
        "preset_class_filter",
        "preset_price_enabled",
        "preset_max_price",
        "preset_price_currency",
    ):
        if key in st.session_state:
            st.session_state[key] = st.session_state[key]


def _finder_value(key: str):
    """Read a Finder widget value, falling back to its default.

    Outside a Streamlit runtime (bare import, e.g. from the test suite) the
    widgets never register their values in session state.
    """
    return st.session_state.get(key, _FINDER_DEFAULTS[key])


def _finder_number_input(label: str, key: str, **kwargs):
    """Render an explicit first value, then defer to the widget's live state."""
    if key not in st.session_state:
        kwargs["value"] = _FINDER_DEFAULTS[key]
    return st.number_input(label, key=key, **kwargs)


def _finder_selectbox(label: str, options: list[str], key: str, **kwargs):
    """Select the intended first value instead of the first option in the list."""
    if key not in st.session_state:
        kwargs["index"] = options.index(str(_FINDER_DEFAULTS[key]))
    return st.selectbox(label, options, key=key, **kwargs)


def _apply_alignment(alignment: _dccav.DccavAlignment):
    st.session_state["box_vh_l"] = float(alignment.vh_l)
    st.session_state["box_fh_hz"] = float(alignment.fh_hz)
    st.session_state["box_vl_l"] = float(alignment.vl_l)
    st.session_state["box_fl_hz"] = float(alignment.fl_hz)


def _apply_reflex_alignment(alignment: _dccav.ReflexAlignment):
    st.session_state["reflex_vb_l"] = float(alignment.vb_l)
    st.session_state["reflex_fb_hz"] = float(alignment.fb_hz)


def _apply_sealed_alignment(alignment: _dccav.SealedAlignment):
    st.session_state["sealed_vb_l"] = float(alignment.vb_l)


def _apply_bandpass4_alignment(alignment: _dccav.Bandpass4Alignment):
    st.session_state["bandpass4_vs_l"] = float(alignment.vs_l)
    st.session_state["bandpass4_vp_l"] = float(alignment.vp_l)
    st.session_state["bandpass4_fp_hz"] = float(alignment.fp_hz)


def _apply_bandpass6_alignment(alignment: _dccav.Bandpass6Alignment):
    st.session_state["bandpass6_vr_l"] = float(alignment.vr_l)
    st.session_state["bandpass6_fr_hz"] = float(alignment.fr_hz)
    st.session_state["bandpass6_vp_l"] = float(alignment.vp_l)
    st.session_state["bandpass6_fp_hz"] = float(alignment.fp_hz)


def _design_objective_label() -> str:
    strategy = str(st.session_state.get("box_strategy", "Balanced"))
    if strategy in _OPT_OBJECTIVE_LABELS:
        return strategy
    fallback = str(st.session_state.get("opt_objective", "Balanced"))
    return fallback if fallback in _OPT_OBJECTIVE_LABELS else "Balanced"


def _optimizer_goals_from_state() -> _dccav.OptimizationGoals:
    return _dccav.OptimizationGoals(
        objective=_OPT_OBJECTIVE_LABELS[_design_objective_label()],
        max_total_volume_l=float(st.session_state.get("opt_max_volume_l", 0.0)) or None,
        target_f3_hz=float(st.session_state.get("opt_target_f3_hz", 0.0)) or None,
        max_ripple_db=float(st.session_state.get("opt_max_ripple_db", 3.0)),
        max_excursion_ratio=float(st.session_state.get("opt_excursion_ratio", 1.0)),
        max_group_delay_ms=float(st.session_state.get("opt_max_gd_ms", 0.0)) or None,
    )


def _alignment_uses_optimizer() -> bool:
    return (
        st.session_state.get("load_type", "DCCAV") != "Infinite baffle"
        and _box_strategy_is_auto()
    )


def _apply_optimized_box(
    box: _dccav.DccavBox | _dccav.ReflexBox | _dccav.Bandpass4Box | _dccav.Bandpass6Box | _dccav.SealedBox,
):
    if isinstance(box, _dccav.ReflexBox):
        st.session_state["reflex_vb_l"] = float(box.vb_l)
        st.session_state["reflex_fb_hz"] = float(box.fb_hz)
    elif isinstance(box, _dccav.SealedBox):
        st.session_state["sealed_vb_l"] = float(box.vb_l)
    elif isinstance(box, _dccav.Bandpass4Box):
        st.session_state["bandpass4_vs_l"] = float(box.vs_l)
        st.session_state["bandpass4_vp_l"] = float(box.vp_l)
        st.session_state["bandpass4_fp_hz"] = float(box.fp_hz)
    elif isinstance(box, _dccav.Bandpass6Box):
        st.session_state["bandpass6_vr_l"] = float(box.vr_l)
        st.session_state["bandpass6_fr_hz"] = float(box.fr_hz)
        st.session_state["bandpass6_vp_l"] = float(box.vp_l)
        st.session_state["bandpass6_fp_hz"] = float(box.fp_hz)
    else:
        st.session_state["box_vh_l"] = float(box.vh_l)
        st.session_state["box_fh_hz"] = float(box.fh_hz)
        st.session_state["box_vl_l"] = float(box.vl_l)
        st.session_state["box_fl_hz"] = float(box.fl_hz)


def _optimized_port_diameter_cm(
    driver: _dccav.DriverTS,
    result: _dccav.SimulationResult,
    volume_l: float,
    tuning_hz: float,
    end_correction: float,
    port: str,
    voltage_v: float | None = None,
) -> float:
    """Size an optimized circular vent honoring every reflex sizing directive.

    Floors on the zero-length tuning boundary, the displacement golden rule
    and the 5%-of-c air-speed guideline; above that floor, grows toward a
    fabricable ~5 cm duct without breaking the 10% duct-volume directive
    (`port_diameter_for_load`) — a fatter port to chase a "nice" length is
    counterproductive once it starts eating the chamber it tunes.
    """
    if voltage_v is None:
        voltage_v = float(st.session_state.get("sim_voltage", 2.83))
    volume_velocity = (
        result.port_h_velocity if port == "upper" else result.port_l_velocity)
    floor_cm = max(
        _dccav.port_min_diameter_cm(volume_l, tuning_hz, end_correction),
        _dccav.port_displacement_min_diameter_cm(driver, tuning_hz),
        _dccav.rated_velocity_diameter_cm(
            driver, result, voltage_v,
            volume_velocity),
    )
    sized_cm = _dccav.port_diameter_for_load(
        volume_l, tuning_hz, end_correction, floor_cm)
    maximum_cm = float(_dccav.OPTIMIZER_MAX_PORT_DIAMETER_CM)
    # sized_cm is already snapped to the sidebar's 0.5 cm grid; sized_cm is
    # only None for a box the optimizer should already have rejected, so
    # keep the (grid-rounded) mandatory floor and let the Port Geometry
    # warnings flag the mismatch instead of silently applying an undersized vent.
    if sized_cm is not None:
        diameter_cm = sized_cm
    else:
        diameter_cm = np.ceil(max(1.0, floor_cm) * 2.0) / 2.0
    return float(min(max(1.0, diameter_cm), maximum_cm))


def _apply_optimized_port_geometry(
    driver: _dccav.DriverTS,
    box: _dccav.DccavBox | _dccav.ReflexBox | _dccav.Bandpass4Box | _dccav.Bandpass6Box | _dccav.SealedBox,
) -> None:
    """Replace stale preset diameters with geometry for the optimized box."""
    if isinstance(box, _dccav.SealedBox):
        return
    if isinstance(box, _dccav.ReflexBox) and _reflex_uses_passive_radiator():
        return
    freq = np.geomspace(
        min(10.0, driver.fs_hz / 4.0), max(400.0, 4.0 * driver.fs_hz), 240)
    voltage_v = float(st.session_state.get("sim_voltage", 2.83))
    if isinstance(box, _dccav.ReflexBox):
        result = _dccav.simulate_reflex(driver, box, freq, voltage_v)
        st.session_state["reflex_port_d_cm"] = _optimized_port_diameter_cm(
            driver, result, box.vb_l, box.fb_hz, 1.43, "lower")
    elif isinstance(box, _dccav.Bandpass4Box):
        result = _dccav.simulate_bandpass4(driver, box, freq, voltage_v)
        st.session_state["bandpass4_port_d_cm"] = _optimized_port_diameter_cm(
            driver, result, box.vp_l, box.fp_hz, 1.43, "lower")
    elif isinstance(box, _dccav.Bandpass6Box):
        result = _dccav.simulate_bandpass6(driver, box, freq, voltage_v)
        st.session_state["bandpass6_port_d_r_cm"] = _optimized_port_diameter_cm(
            driver, result, box.vr_l, box.fr_hz, 1.43, "upper")
        st.session_state["bandpass6_port_d_p_cm"] = _optimized_port_diameter_cm(
            driver, result, box.vp_l, box.fp_hz, 1.43, "lower")
    else:
        result = _dccav.simulate(driver, box, freq, voltage_v)
        st.session_state["box_port_d_h_cm"] = _optimized_port_diameter_cm(
            driver, result, box.vh_l, box.fh_hz, 1.64, "upper")
        st.session_state["box_port_d_l_cm"] = _optimized_port_diameter_cm(
            driver, result, box.vl_l, box.fl_hz, 1.43, "lower")


def _optimized_summary(optimized: _dccav.OptimizedAlignment) -> str:
    parts = [
        f"Optimized: F3 {optimized.f3_hz:.1f} Hz",
        f"ripple {optimized.ripple_db:.1f} dB" if np.isfinite(optimized.ripple_db) else "ripple n/a",
        f"Vtot {optimized.total_volume_l:.1f} L",
    ]
    if np.isfinite(optimized.excursion_ratio):
        parts.append(f"exc {optimized.excursion_ratio:.2f}x Xmax")
    if np.isfinite(optimized.group_delay_ms):
        parts.append(f"GD {optimized.group_delay_ms:.1f} ms")
    return " · ".join(parts)


def _optimizer_box_signature(
    box: _dccav.DccavBox | _dccav.ReflexBox | _dccav.Bandpass4Box | _dccav.Bandpass6Box | _dccav.SealedBox,
) -> tuple:
    if isinstance(box, _dccav.ReflexBox):
        return ("reflex", box.vb_l, box.fb_hz, box.q_abs, box.q_leak, box.q_port)
    if isinstance(box, _dccav.SealedBox):
        return ("sealed", box.vb_l, box.q_abs, box.q_leak)
    if isinstance(box, _dccav.Bandpass4Box):
        return (
            "bandpass4", box.vs_l, box.vp_l, box.fp_hz,
            box.q_abs_s, box.q_abs_p, box.q_leak_s, box.q_leak_p, box.q_port,
        )
    if isinstance(box, _dccav.Bandpass6Box):
        return (
            "bandpass6", box.vr_l, box.fr_hz, box.vp_l, box.fp_hz,
            box.q_abs_r, box.q_abs_p, box.q_leak_r, box.q_leak_p,
            box.q_port_r, box.q_port_p,
        )
    return (
        "dccav", box.vh_l, box.fh_hz, box.vl_l, box.fl_hz,
        box.q_abs_h, box.q_abs_l, box.q_leak_h, box.q_leak_l,
        box.q_port_h, box.q_port_l,
    )


def _optimizer_result_context(
    driver: _dccav.DriverTS,
    load_type: str,
    box: _dccav.DccavBox | _dccav.ReflexBox | _dccav.Bandpass4Box | _dccav.Bandpass6Box | _dccav.SealedBox,
) -> tuple:
    goals = _optimizer_goals_from_state()
    return (
        load_type,
        driver,
        goals,
        round(float(st.session_state.get("sim_voltage", 2.83)), 9),
        _optimizer_box_signature(box),
    )


def _current_optimizer_summary(driver: _dccav.DriverTS) -> str | None:
    load_type = st.session_state.get("load_type", "DCCAV")
    if load_type == "Bass reflex":
        box = _reflex_box_from_state()
    elif load_type == "Sealed":
        box = _sealed_box_from_state()
    elif load_type == "Bandpass 4th order":
        box = _bandpass4_box_from_state()
    elif load_type == "Bandpass 6th order":
        box = _bandpass6_box_from_state()
    elif load_type == "DCCAV":
        box = _box_from_state()
    else:
        return None
    context = _optimizer_result_context(driver, load_type, box)
    if st.session_state.get("_opt_last_context") != context:
        return None
    return st.session_state.get("opt_last_summary")


def _run_box_optimizer(driver: _dccav.DriverTS) -> _dccav.OptimizedAlignment:
    load_type = st.session_state.get("load_type", "DCCAV")
    if load_type == "Bass reflex":
        template = _reflex_box_from_state()
    elif load_type == "Sealed":
        template = _sealed_box_from_state()
    elif load_type == "Bandpass 4th order":
        template = _bandpass4_box_from_state()
    elif load_type == "Bandpass 6th order":
        template = _bandpass6_box_from_state()
    elif load_type == "Infinite baffle":
        raise ValueError("Infinite baffle has no box to optimize")
    else:
        template = _box_from_state()
    optimized = _dccav.optimize_alignment(
        driver,
        _optimizer_goals_from_state(),
        load_type=load_type,
        box_template=template,
        voltage_v=float(st.session_state.get("sim_voltage", 2.83)),
    )
    _apply_optimized_port_geometry(driver, optimized.box)
    st.session_state["opt_last_summary"] = _optimized_summary(optimized)
    st.session_state["_opt_last_context"] = _optimizer_result_context(
        driver, load_type, optimized.box,
    )
    return optimized


def _apply_suggested_box_for(driver: _dccav.DriverTS):
    """Apply the optimizer box for the active objective strategy."""
    if st.session_state.get("load_type", "DCCAV") == "Infinite baffle":
        return
    try:
        optimized = _run_box_optimizer(driver)
    except ValueError as exc:
        # Infeasible goal/constraints: keep a buildable starter box and
        # surface the reason in the sidebar instead of failing silently.
        _apply_empirical_box_for(driver)
        st.session_state["opt_last_summary"] = None
        st.session_state["_auto_box_error"] = str(exc)
        return
    st.session_state.pop("_auto_box_error", None)
    _apply_optimized_box(optimized.box)


def _apply_empirical_box_for(driver: _dccav.DriverTS) -> None:
    """Apply the lightweight starter regardless of the selected strategy."""
    load_type = st.session_state.get("load_type", "DCCAV")
    if load_type == "Bass reflex":
        _apply_reflex_alignment(_dccav.suggest_reflex_alignment(driver))
    elif load_type == "Sealed":
        _apply_sealed_alignment(_dccav.suggest_sealed_alignment(driver))
    elif load_type == "Bandpass 4th order":
        _apply_bandpass4_alignment(_dccav.suggest_bandpass4_alignment(driver))
    elif load_type == "Bandpass 6th order":
        _apply_bandpass6_alignment(_dccav.suggest_bandpass6_alignment(driver))
    elif load_type == "DCCAV":
        _apply_alignment(_dccav.suggest_alignment(driver))


def _on_box_strategy_change() -> None:
    strategy = str(st.session_state.get("box_strategy", "Balanced"))
    previous = str(st.session_state.get("_previous_box_strategy", "Balanced"))
    load_type = str(st.session_state.get("load_type", "DCCAV"))
    _set_box_strategy_state(strategy)
    if previous == "Manual" and strategy in _OPT_OBJECTIVE_LABELS:
        # Remember the user's hand-tuned box before the optimizer overwrites it.
        _snapshot_manual_box(load_type)
    elif previous in _OPT_OBJECTIVE_LABELS and strategy == "Manual":
        # Returning to Manual: bring back the last hand-tuned values.
        _restore_manual_box(load_type)
    if strategy in _OPT_OBJECTIVE_LABELS:
        try:
            driver = _driver_from_state()
            _apply_suggested_box_for(driver)
            _mark_auto_alignment_synced(driver)
        except Exception:
            logger.exception("Could not apply the selected box strategy")


def _use_manual_box_strategy() -> None:
    _set_box_strategy_state("Manual")


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
        step=_step5(key, step),
        key=key,
        disabled=disabled,
    )


def _alignment_warning(ts: _dccav.DriverTS, box: _dccav.DccavBox) -> str | None:
    """Warn only when the DCCAV box currently being simulated is very small."""
    v_total = box.vh_l + box.vl_l
    if ts.sd_cm2 >= 500.0 and v_total < 25.0:
        return (
            f"Very small active 12 in alignment: Vh+Vl = {v_total:.1f} L. "
            "Verify gross volume, port displacement, air velocity, compression "
            "and max-SPL limits before building."
        )
    return None


def _fmt_hz(value: float) -> str:
    return f"{value:.1f} Hz" if np.isfinite(float(value)) else "n/a"


def _fmt_db(value: float) -> str:
    return f"{value:.1f} dB" if np.isfinite(float(value)) else "n/a"


def _driver_preset_family(name: str) -> str:
    try:
        return _dccav.driver_preset_info(name).brand
    except ValueError:
        return "Other"


def _driver_preset_source(name: str) -> str:
    try:
        raw = _dccav.driver_preset_info(name).source
    except ValueError:
        return "Built-in"
    return raw if raw in _PRESET_SOURCE_EXACT_BUCKETS else "Manufacturer"


def _driver_preset_price(name: str) -> float | None:
    try:
        return _dccav.driver_preset_info(name).price
    except ValueError:
        return None


def _driver_preset_currency(name: str) -> str:
    try:
        return _dccav.driver_preset_info(name).currency
    except ValueError:
        return ""


@st.cache_data(ttl=6 * 60 * 60, show_spinner=False)
def _current_exchange_rates() -> tuple[dict[str, float], str]:
    """Return current EUR-based ECB rates and their published reference date."""
    return _pricing.load_ecb_reference_rates()


def _normalized_preset_price(
    name: str, target_currency: str, rates: dict[str, float] | None = None
) -> float | None:
    # Callers iterating the full preset catalog must pass ``rates``: hitting
    # the st.cache_data-backed rates once per preset costs ~0.5 s of pure
    # cache overhead per rerun.
    if rates is None:
        rates, _ = _current_exchange_rates()
    return _pricing.convert_price(
        _driver_preset_price(name),
        _driver_preset_currency(name),
        target_currency,
        rates,
    )


def _preset_price_currencies(names: list[str]) -> list[str]:
    return sorted(
        {
            _driver_preset_currency(name)
            for name in names
            if _driver_preset_price(name) is not None and _driver_preset_currency(name)
        }
    )


def _preset_price_values(names: list[str], currency: str | None = None) -> list[float]:
    values = []
    rates = _current_exchange_rates()[0] if currency else None
    for name in names:
        price = (
            _normalized_preset_price(name, currency, rates)
            if currency
            else _driver_preset_price(name)
        )
        if price is not None and np.isfinite(float(price)):
            values.append(float(price))
    return values


def _purchase_markdown(info: _dccav.DriverPresetInfo) -> str | None:
    """Return a markdown purchase link for a preset, or None without a URL."""
    if not info.url:
        return None
    host = info.url.split("//", 1)[-1].split("/", 1)[0].removeprefix("www.")
    if info.price is not None and np.isfinite(float(info.price)):
        label = f"Buy · {float(info.price):.2f} {info.currency}".rstrip() + f" · {host}"
    else:
        label = f"Buy · {host}"
    return f"[{label}]({info.url})"


def _size_bucket(size_in: float) -> str:
    if size_in <= 1.5:
        return "1 in"
    if size_in <= 2.5:
        return "2 in"
    if size_in <= 3.5:
        return "3 in"
    if size_in <= 4.5:
        return "4 in"
    if size_in <= 5.5:
        return "5 in"
    if size_in <= 7.0:
        return "6 in"
    if size_in <= 9.0:
        return "8 in"
    if size_in <= 11.0:
        return "10 in"
    if size_in <= 13.5:
        return "12 in"
    if size_in <= 16.5:
        return "15 in"
    if size_in <= 19.5:
        return "18 in"
    return "21 in"


def _driver_preset_size(name: str) -> str:
    try:
        info = _dccav.driver_preset_info(name)
        if info.size_in is not None:
            return _size_bucket(info.size_in)
    except ValueError:
        pass
    lower = name.lower()
    if lower.startswith("turbosound ts-15"):
        return "15 in"
    if (
        lower.startswith("beyma 12")
        or lower.startswith("turbosound ts-12")
        or lower.startswith("sb audience bianco-12")
        or lower.startswith("lavoce wsf122")
        or "rss315" in lower
        or "30w/4558" in lower
    ):
        return "12 in"
    try:
        driver = _dccav.get_driver_preset(name)
    except ValueError:
        return "Other"
    piston_diameter_mm = float(np.sqrt(driver.sd_cm2 / 10_000.0 * 4.0 / np.pi) * 1000.0)
    piston_inches = piston_diameter_mm / 25.4
    return _size_bucket(piston_inches)


def _available_preset_families(names: list[str]) -> list[str]:
    present = {_driver_preset_family(name) for name in names}
    ordered = [family for family in _PRESET_FAMILY_ORDER if family == "All" or family in present]
    extras = sorted(present.difference(ordered), key=str.casefold)
    return [*ordered, *extras]


def _render_finder_library_filters(all_preset_names: list[str]) -> None:
    """Render Finder library filters."""
    st.text_input("Search preset", key="preset_search", placeholder="Brand or model")
    st.selectbox("Source", _PRESET_SOURCE_FILTERS, key="preset_source_filter")
    st.selectbox("Brand", _available_preset_families(all_preset_names), key="preset_family_filter")
    st.selectbox("Size", _PRESET_SIZE_FILTERS, key="preset_size_filter")
    st.selectbox(
        "Class",
        _PRESET_CLASS_FILTERS,
        key="preset_class_filter",
        help="Heuristic bandwidth class from T/S: pure subwoofers vs woofers "
             "that can reach the mids (voice-coil corner, cone mass, Fs, sensitivity).",
    )

    preset_currencies = _preset_price_currencies(all_preset_names)
    if preset_currencies:
        if st.session_state["preset_price_currency"] not in preset_currencies:
            st.session_state["preset_price_currency"] = preset_currencies[0]
        st.selectbox("Price currency", preset_currencies, key="preset_price_currency")
        price_currency = str(st.session_state["preset_price_currency"])
        rates, rates_date = _current_exchange_rates()
        preset_prices = _preset_price_values(all_preset_names, price_currency)
        price_max_available = max(preset_prices)
        if st.session_state["preset_max_price"] <= 0.0:
            st.session_state["preset_max_price"] = float(price_max_available)
        st.session_state["preset_max_price"] = min(
            float(price_max_available),
            max(0.0, float(st.session_state["preset_max_price"])),
        )
        st.checkbox("Filter by max price", key="preset_price_enabled")
        if st.session_state["preset_price_enabled"]:
            st.number_input(
                f"Max price ({price_currency})",
                min_value=0.0,
                max_value=float(price_max_available),
                step=1.0,
                key="preset_max_price",
            )
        if len(preset_currencies) > 1:
            if rates and rates_date:
                st.caption(
                    f"Prices normalized to {price_currency} · ECB reference rates "
                    f"{rates_date}."
                )
            else:
                st.warning(
                    f"ECB rates unavailable: only prices already in "
                    f"{price_currency} can be compared."
                )
    else:
        st.session_state["preset_price_enabled"] = False
        st.checkbox("Filter by max price", key="preset_price_enabled", disabled=True)
        st.caption("Price unavailable in the current preset dataset.")


def _filter_driver_preset_names(
    names: list[str],
    *,
    source: str,
    family: str,
    size: str,
    search: str,
    max_price: float | None = None,
    max_price_currency: str | None = None,
    selected: str | None = None,
    driver_class: str = "All",
) -> list[str]:
    query = search.strip().casefold()
    rates = _current_exchange_rates()[0] if max_price is not None else None
    filtered = []
    for name in names:
        if source != "All" and _driver_preset_source(name) != source:
            continue
        if family != "All" and _driver_preset_family(name) != family:
            continue
        if size != "All" and _driver_preset_size(name) != size:
            continue
        if driver_class != "All" and _driver_preset_class(name) != driver_class:
            continue
        if query and query not in name.casefold():
            continue
        if max_price is not None:
            price = _normalized_preset_price(name, str(max_price_currency or ""), rates)
            if price is None or float(price) > float(max_price):
                continue
        filtered.append(name)
    if selected and selected != "Custom" and selected in names and selected not in filtered:
        filtered.insert(0, selected)
    return filtered


def _driver_preset_class(name: str) -> str:
    # functools.cache would restart cold on every Streamlit rerun (this whole
    # script is re-executed, redefining the function); the session_state dict
    # survives reruns so the 10k-preset catalog is classified once per session.
    class_cache = st.session_state.setdefault("_driver_class_cache", {})
    cached = class_cache.get(name)
    if cached is None:
        try:
            cached = _dccav.classify_driver_bandwidth(
                _dccav.get_driver_preset(name)).driver_class
        except Exception:
            cached = "Woofer"
        class_cache[name] = cached
    return cached


def _apply_driver_preset(driver: _dccav.DriverTS):
    st.session_state["driver_fs_hz"] = float(driver.fs_hz)
    st.session_state["driver_vas_l"] = float(driver.vas_l)
    st.session_state["driver_qts"] = float(driver.qts)
    st.session_state["driver_qms"] = float(driver.qms)
    st.session_state["driver_re_ohm"] = float(driver.re_ohm)
    st.session_state["driver_sd_mode"] = "Sd"
    st.session_state["driver_sd_cm2"] = float(driver.sd_cm2)
    st.session_state["driver_diameter_mm"] = float(np.sqrt(driver.sd_cm2 / 10_000.0 * 4.0 / np.pi) * 1000.0)
    st.session_state["driver_le_mh"] = float(driver.le_mh)
    st.session_state["driver_le10k_mh"] = float(driver.le10k_mh or 0.0)
    st.session_state["driver_xmax_mm"] = float(driver.xmax_mm)
    st.session_state["driver_pe_w"] = float(driver.pe_w)
    st.session_state["driver_mms_g"] = float(driver.mms_g or 0.0)
    st.session_state["driver_cms_mm_n"] = float(driver.cms_mm_per_n or 0.0)
    st.session_state["driver_bl_tm"] = float(driver.bl_tm or 0.0)


def _auto_align_current_driver():
    if not _box_strategy_is_auto():
        return
    try:
        driver = _driver_from_state()
        _apply_suggested_box_for(driver)
        _mark_auto_alignment_synced(driver)
    except Exception:
        pass


def _optimizer_goals_signature() -> tuple:
    if not _alignment_uses_optimizer():
        return ()
    goals = _optimizer_goals_from_state()
    return (
        "optimized",
        goals.objective,
        goals.max_total_volume_l,
        goals.target_f3_hz,
        goals.max_ripple_db,
        goals.max_excursion_ratio,
        goals.max_group_delay_ms,
        round(float(st.session_state.get("sim_voltage", 2.83)), 3),
    )


def _auto_alignment_signature(driver: _dccav.DriverTS | None = None) -> tuple:
    driver = driver or _driver_from_state()
    return (
        st.session_state.get("load_type", "DCCAV"),
        st.session_state.get("reflex_resonator_type", _RESONATOR_PORT),
        *_optimizer_goals_signature(),
        round(float(driver.fs_hz), 6),
        round(float(driver.vas_l), 6),
        round(float(driver.qts), 6),
        round(float(driver.qms), 6),
        round(float(driver.re_ohm), 6),
        round(float(driver.sd_cm2), 6),
        round(float(driver.le_mh), 6),
        round(float(driver.xmax_mm), 6),
        round(float(driver.pe_w), 6),
        round(float(driver.mms_g or 0.0), 6),
        round(float(driver.cms_mm_per_n or 0.0), 6),
        round(float(driver.bl_tm or 0.0), 6),
        bool(driver.panel_air_load),
        round(float(driver.panel_coupling), 6),
    )


def _mark_auto_alignment_synced(driver: _dccav.DriverTS | None = None):
    try:
        st.session_state["_auto_align_signature"] = _auto_alignment_signature(driver)
    except Exception:
        pass


def _sync_auto_alignment_if_needed():
    if not _box_strategy_is_auto():
        return
    try:
        driver = _driver_from_state()
        signature = _auto_alignment_signature(driver)
        if st.session_state.get("_auto_align_signature") == signature:
            return
        _apply_suggested_box_for(driver)
        st.session_state["_auto_align_signature"] = signature
    except Exception:
        pass


def _on_driver_preset_change():
    preset_name = st.session_state.get("driver_preset_name", "Custom")
    if preset_name == "Custom":
        return
    try:
        _apply_driver_preset(_dccav.get_driver_preset(preset_name))
        # Re-read through the configuration so multi-driver setups get a box
        # sized for the composite Vas/Sd, not the single unit.
        composite = _driver_from_state()
        if _box_strategy_is_auto():
            _apply_suggested_box_for(composite)
            _mark_auto_alignment_synced(composite)
    except Exception:
        logger.exception("Could not apply driver preset")


def _step5(key, default, calc_val=None):
    val = st.session_state.get(key)
    if val is not None:
        try:
            val = float(val)
            if val == 0.0 and calc_val is not None:
                val = float(calc_val)
            if val > 0:
                s_default = str(default)
                decimals = len(s_default.split('.')[1]) if '.' in s_default else 0
                step_val = round(val * 0.05, decimals)
                if isinstance(default, int):
                    return max(default, int(step_val))
                return max(default, step_val)
        except (ValueError, TypeError):
            pass
    return default

def _on_driver_param_change():
    st.session_state["driver_preset_name"] = "Custom"
    _auto_align_current_driver()


def _on_load_type_change():
    _auto_align_current_driver()


def _series_frame(result: _dccav.SimulationResult, series: dict[str, np.ndarray]) -> pd.DataFrame:
    rows = []
    for name, values in series.items():
        for freq, value in zip(result.frequency_hz, values, strict=True):
            freq_f = float(freq)
            value_f = float(value)
            if not np.isfinite(freq_f) or not np.isfinite(value_f):
                continue
            rows.append({
                "frequency_hz": freq_f,
                "series": name,
                "value": value_f,
            })
    return pd.DataFrame(rows)


def _log_frequency_scale(domain: list[float] | None = None) -> alt.Scale:
    if domain is None:
        return alt.Scale(type="log", nice=False)
    return alt.Scale(type="log", domain=domain, nice=False)


def _response_amplitude_axis() -> alt.Axis:
    """Keep the numbered dB scale visible across every response overlay."""
    return alt.Axis(
        title="Amplitude (dB)",
        orient="left",
        format=".0f",
        tickCount=7,
        labels=True,
        ticks=True,
        domain=True,
        grid=True,
        labelPadding=6,
        titlePadding=10,
        zindex=1,
    )


def _line_chart(
    data: pd.DataFrame,
    y_title: str,
    *,
    height: int,
    legend: bool = True,
    x_domain: list[float] | None = None,
    y_domain: list[float] | None = None,
    y_axis: alt.Axis | None = None,
    default_visible: list[str] | None = None,
    y_field: str = "value",
) -> alt.Chart:
    if not legend and default_visible is not None:
        data = data[data["series"].isin(default_visible)]
    
    series_names = list(dict.fromkeys(data["series"].tolist()))
    color_scale = alt.Scale(
        domain=series_names,
        range=[_TRACE_COLORS.get(name, "#7cc7ff") for name in series_names],
    )
    color = alt.Color(
        "series:N",
        title=None,
        legend=None if not legend else alt.Legend(title=None, orient="bottom", direction="horizontal"),
        scale=color_scale,
    )
    
    chart = alt.Chart(data).mark_line(point=False, clip=True, strokeWidth=2.2)
    
    if legend:
        kwargs = {"fields": ["series"], "bind": "legend"}
        if default_visible is not None:
            kwargs["value"] = [{"series": name} for name in default_visible]
        selection = alt.selection_point(**kwargs)
        opacity = alt.condition(selection, alt.value(1), alt.value(0))
        chart = chart.encode(
            x=alt.X(
                "frequency_hz:Q",
                title="Frequency (Hz)",
                scale=_log_frequency_scale(x_domain),
                axis=alt.Axis(format="~g"),
            ),
            y=alt.Y(
                f"{y_field}:Q",
                title=y_title,
                scale=alt.Scale(domain=y_domain, nice=False) if y_domain else alt.Undefined,
                axis=y_axis if y_axis is not None else alt.Undefined,
            ),
            color=color,
            opacity=opacity,
            tooltip=[
                alt.Tooltip("frequency_hz:Q", title="Hz", format=".2f"),
                alt.Tooltip("series:N", title="Trace"),
                alt.Tooltip("value:Q", title=y_title, format=".3f"),
            ],
        ).add_params(selection)
    else:
        chart = chart.encode(
            x=alt.X(
                "frequency_hz:Q",
                title="Frequency (Hz)",
                scale=_log_frequency_scale(x_domain),
                axis=alt.Axis(format="~g"),
            ),
            y=alt.Y(
                f"{y_field}:Q",
                title=y_title,
                scale=alt.Scale(domain=y_domain, nice=False) if y_domain else alt.Undefined,
                axis=y_axis if y_axis is not None else alt.Undefined,
            ),
            color=color,
            tooltip=[
                alt.Tooltip("frequency_hz:Q", title="Hz", format=".2f"),
                alt.Tooltip("series:N", title="Trace"),
                alt.Tooltip(f"{y_field}:Q", title=y_title, format=".3f"),
            ],
        )
    return chart.properties(height=height, width="container")


def _response_series(result: _dccav.SimulationResult) -> dict[str, np.ndarray]:
    series = {}
    load_type = st.session_state.get("load_type", "DCCAV")
    series["Total"] = result.spl_total_db
    series["Cone"] = result.spl_driver_db
    if load_type in {
        "DCCAV", "Bass reflex", "Bandpass 4th order", "Bandpass 6th order",
    }:
        if load_type == "Bass reflex" and _reflex_uses_passive_radiator():
            label = "Passive radiator"
        else:
            label = "Vent" if load_type in {"Bass reflex", "Bandpass 4th order"} else "Lower port"
        series[label] = result.spl_port_db
    if not st.session_state.get("plot_compare_loads", False):
        series["MOL"] = result.mol_db
        series["MIL"] = result.mil_w
    return series


def _response_y_domain(
    result: _dccav.SimulationResult,
    series: dict[str, np.ndarray],
    frequency_window: list[float] | None = None,
) -> list[float] | None:
    total = np.asarray(result.spl_total_db, dtype=float)
    finite = total[np.isfinite(total)]
    if not finite.size:
        return None
    frequencies = np.asarray(result.frequency_hz, dtype=float)
    zoomed = False
    visible = np.isfinite(frequencies)
    if frequency_window is not None:
        low_hz, high_hz = map(float, frequency_window)
        visible &= (frequencies >= low_hz) & (frequencies <= high_hz)
        zoomed = low_hz > float(frequencies[0]) or high_hz < float(frequencies[-1])
    visible_total = total[visible & np.isfinite(total)]
    if not visible_total.size:
        visible_total = finite

    if zoomed:
        bottom = float(np.min(visible_total)) - 2.0
        top = float(np.max(visible_total)) + 5.0
        for values in series.values():
            trace = np.asarray(values, dtype=float)
            trace = trace[visible & np.isfinite(trace)]
            if trace.size:
                top = max(top, float(np.max(trace)) + 5.0)
        if top - bottom < 12.0:
            midpoint = (top + bottom) / 2.0
            bottom, top = midpoint - 6.0, midpoint + 6.0
        return [float(bottom), float(top)]

    bottom = _interp(result.frequency_hz, result.spl_total_db, 10.0)
    if not np.isfinite(bottom):
        bottom = float(np.min(finite))
    top = float(np.max(finite))
    # Traces such as MOL sit well above the small-signal total; widen the
    # window to every displayed trace so none is clipped out of the chart.
    for values in series.values():
        trace = np.asarray(values, dtype=float)
        trace = trace[np.isfinite(trace)]
        if trace.size:
            top = max(top, float(np.max(trace)))
    top += 5.0
    if not np.isfinite(top):
        return None
    if top <= bottom:
        top = bottom + 10.0
    return [float(bottom), float(top)]


def _port_series(result: _dccav.SimulationResult) -> dict[str, np.ndarray]:
    series = {}
    load_type = st.session_state.get("load_type", "DCCAV")
    if load_type not in {"DCCAV", "Bass reflex", "Bandpass 4th order", "Bandpass 6th order"}:
        return series
    if st.session_state.get("plot_port_upper", True) and load_type in ("DCCAV", "Bandpass 6th order"):
        series["Upper port"] = result.port_h_velocity
    if st.session_state.get("plot_port_lower", True):
        if load_type == "Bass reflex" and _reflex_uses_passive_radiator():
            label = "Passive radiator"
        else:
            label = "Vent" if load_type in {"Bass reflex", "Bandpass 4th order"} else "Lower port"
        series[label] = result.port_l_velocity
    return series


def _cursor_rows(result: _dccav.SimulationResult, thresholds: dict[int, float]) -> list[dict]:
    rows = []
    auto_markers = set(st.session_state.get("cursor_auto_markers", _AUTO_CURSOR_OPTIONS))
    if "F3" in auto_markers and np.isfinite(thresholds[3]):
        rows.append(_cursor_row(result, "F3", thresholds[3]))
    if "F6" in auto_markers and np.isfinite(thresholds[6]):
        rows.append(_cursor_row(result, "F6", thresholds[6]))
    if "F10" in auto_markers and np.isfinite(thresholds[10]):
        rows.append(_cursor_row(result, "F10", thresholds[10]))
    return rows


def _marker_display_label(row: dict, show_mol: bool) -> str:
    label = (
        f"{row['label']} {float(row['frequency_hz']):.1f} Hz "
        f"{float(row['spl_total_db']):.1f} dB"
    )
    mol_db = float(row.get("mol_db", np.nan))
    if show_mol and np.isfinite(mol_db):
        label += f" · MOL {mol_db:.1f} dB"
    return label


def _cursor_label_rows(
    rows: list[dict],
    y_domain: list[float] | None,
    show_mol: bool = False,
) -> list[dict]:
    if not rows:
        return rows
    if y_domain is None:
        finite_spl = [
            float(row["spl_total_db"])
            for row in rows
            if np.isfinite(float(row.get("spl_total_db", np.nan)))
        ]
        top = max(finite_spl) if finite_spl else 100.0
        bottom = top - 20.0
    else:
        bottom, top = y_domain
    span = max(float(top) - float(bottom), 1.0)
    out = []
    for lane, row in enumerate(rows):
        label_row = dict(row)
        label_row["display_label"] = _marker_display_label(label_row, show_mol)
        label_row["label_y_db"] = top - span * (0.05 + lane * 0.09)
        out.append(label_row)
    return out


def _cursor_row(result: _dccav.SimulationResult, label: str, frequency_hz: float) -> dict:
    f = float(np.clip(frequency_hz, result.frequency_hz[0], result.frequency_hz[-1]))
    spl_total_db = _interp(result.frequency_hz, result.spl_total_db, f)
    return {
        "label": label,
        "frequency_hz": f,
        "spl_total_db": spl_total_db,
        "mol_db": _interp(result.frequency_hz, result.mol_db, f),
        "impedance_ohm": _interp(result.frequency_hz, result.impedance_ohm, f),
        "excursion_mm": _interp(result.frequency_hz, result.excursion_mm, f),
    }


def _interp(x: np.ndarray, y: np.ndarray, value: float) -> float:
    return float(np.interp(float(value), np.asarray(x, dtype=float), np.asarray(y, dtype=float)))


def _cursor_layer(
    rows: list[dict],
    y_domain: list[float] | None = None,
    x_domain: list[float] | None = None,
    show_mol: bool = False,
    show_legend: bool = False,
) -> alt.LayerChart | None:
    if x_domain is not None:
        low_hz, high_hz = map(float, x_domain)
        rows = [
            row for row in rows
            if low_hz <= float(row["frequency_hz"]) <= high_hz
        ]
    if not rows:
        return None
    data = pd.DataFrame(_cursor_label_rows(rows, y_domain, show_mol))
    y_scale = alt.Scale(domain=y_domain, nice=False) if y_domain else alt.Undefined
    color = alt.Color(
        "label:N",
        title="Cursor",
        scale=alt.Scale(
            domain=["F3", "F6", "F10"],
            range=["#ffd166", "#f77f00", "#d62828"],
        ),
        legend=None if not show_legend else alt.Legend(title="Cursor", orient="bottom", direction="horizontal"),
    )
    tooltips = [
        alt.Tooltip("label:N", title="Cursor"),
        alt.Tooltip("frequency_hz:Q", title="Hz", format=".2f"),
        alt.Tooltip("spl_total_db:Q", title="Total dB", format=".2f"),
        alt.Tooltip("impedance_ohm:Q", title="Ω", format=".2f"),
        alt.Tooltip("excursion_mm:Q", title="mm", format=".3f"),
    ]
    if show_mol:
        tooltips.insert(3, alt.Tooltip("mol_db:Q", title="MOL dB", format=".2f"))
    rules = alt.Chart(data).mark_rule(strokeWidth=1.5).encode(
        x=alt.X(
            "frequency_hz:Q",
            scale=_log_frequency_scale(x_domain),
        ),
        color=color,
        tooltip=tooltips,
    )
    labels = alt.Chart(data).mark_text(
        align="left",
        baseline="top",
        fontSize=16,
        fontWeight="bold",
        stroke="#0b1018",
        strokeWidth=3,
        strokeOpacity=0.85,
    ).encode(
        x=alt.value(22),
        y=alt.Y(
            "label_y_db:Q",
            scale=y_scale,
            axis=_response_amplitude_axis(),
        ),
        text="display_label:N",
        color=color,
    )
    labels_fill = alt.Chart(data).mark_text(
        align="left",
        baseline="top",
        fontSize=16,
        fontWeight="bold",
    ).encode(
        x=alt.value(22),
        y=alt.Y(
            "label_y_db:Q",
            scale=y_scale,
            axis=_response_amplitude_axis(),
        ),
        text="display_label:N",
        color=color,
    )
    return rules + labels + labels_fill


def _click_marker_layer(
    result: _dccav.SimulationResult,
    x_domain: list[float] | None = None,
    y_domain: list[float] | None = None,
    show_mol: bool = False,
) -> alt.LayerChart:
    marker_data = pd.DataFrame({
        "frequency_hz": result.frequency_hz.astype(float),
        "spl_total_db": result.spl_total_db.astype(float),
        "mol_db": result.mol_db.astype(float),
    })
    marker_data = marker_data[np.isfinite(marker_data["frequency_hz"]) & np.isfinite(marker_data["spl_total_db"])]
    if x_domain is not None:
        # Unclipped selector points beyond the zoom window would make Vega
        # shrink the plot area to fit them inside the container width.
        low_hz, high_hz = map(float, x_domain)
        marker_data = marker_data[
            (marker_data["frequency_hz"] >= low_hz)
            & (marker_data["frequency_hz"] <= high_hz)
        ]
    marker_data["display_label"] = [
        (
            f"{frequency_hz:.1f} Hz {total_db:.1f} dB"
            + (f" · MOL {mol_db:.1f} dB" if show_mol and np.isfinite(mol_db) else "")
        )
        for frequency_hz, total_db, mol_db in marker_data[
            ["frequency_hz", "spl_total_db", "mol_db"]
        ].itertuples(index=False, name=None)
    ]
    click_marker = alt.selection_point(
        name="click_marker",
        fields=["frequency_hz"],
        nearest=True,
        on="click",
        clear="dblclick",
        empty=False,
    )
    base = alt.Chart(marker_data).encode(
        x=alt.X(
            "frequency_hz:Q",
            scale=_log_frequency_scale(x_domain),
        ),
        y=alt.Y(
            "spl_total_db:Q",
            scale=alt.Scale(domain=y_domain, nice=False) if y_domain else alt.Undefined,
            axis=_response_amplitude_axis(),
        ),
    )
    selectors = base.mark_point(filled=True, size=180, opacity=0.001).add_params(click_marker)
    rule = base.mark_rule(color="#06d6a0", strokeWidth=2.0).transform_filter(click_marker)
    point = base.mark_point(
        filled=True,
        size=95,
        color="#06d6a0",
        stroke="#0b1018",
        strokeWidth=1.5,
        clip=True,
    ).transform_filter(click_marker)
    label = base.mark_text(
        align="left",
        baseline="bottom",
        dx=9,
        dy=-10,
        fontSize=18,
        fontWeight="bold",
        color="#06d6a0",
    ).encode(
        text="display_label:N",
    ).transform_filter(click_marker)
    return selectors + rule + point + label


def _band_layer(
    band: _dccav.ToleranceBand,
    y_domain: list[float] | None,
    x_domain: list[float] | None = None,
) -> alt.Chart | None:
    data = pd.DataFrame({
        "frequency_hz": np.asarray(band.frequency_hz, dtype=float),
        "lower_db": np.asarray(band.lower_db, dtype=float),
        "upper_db": np.asarray(band.upper_db, dtype=float),
    })
    data = data[np.isfinite(data["frequency_hz"])
                & np.isfinite(data["lower_db"]) & np.isfinite(data["upper_db"])]
    if data.empty:
        return None
    y_scale = alt.Scale(domain=y_domain, nice=False) if y_domain else alt.Undefined
    return alt.Chart(data).mark_area(
        opacity=0.22, color=_TRACE_COLORS["Total"], clip=True,
    ).encode(
        x=alt.X(
            "frequency_hz:Q",
            scale=_log_frequency_scale(x_domain),
        ),
        y=alt.Y(
            "lower_db:Q",
            scale=y_scale,
            axis=_response_amplitude_axis(),
        ),
        y2="upper_db:Q",
        tooltip=[
            alt.Tooltip("frequency_hz:Q", title="Hz", format=".2f"),
            alt.Tooltip("lower_db:Q", title="P5 dB", format=".2f"),
            alt.Tooltip("upper_db:Q", title="P95 dB", format=".2f"),
        ],
    )


def _plot_response(
    result: _dccav.SimulationResult,
    cursor_rows: list[dict],
    series_override: dict[str, np.ndarray] | None = None,
    band: _dccav.ToleranceBand | None = None,
    frequency_window: list[float] | None = None,
    show_legend: bool = False,
    default_visible: list[str] | None = None,
) -> alt.Chart:
    series = dict(series_override if series_override else _response_series(result))
    mil_w_data = series.pop("MIL", None)
    
    db_series_to_plot = series if series else {"Total": result.spl_total_db}
    
    data = _series_frame(result, db_series_to_plot)
    y_domain = _response_y_domain(result, db_series_to_plot, frequency_window)
    y_domain = _expand_y_domain_for_pins(y_domain, frequency_window)
    if band is not None and y_domain is not None:
        finite_upper = np.asarray(band.upper_db, dtype=float)
        finite_upper = finite_upper[np.isfinite(finite_upper)]
        if finite_upper.size:
            y_domain[1] = max(y_domain[1], float(np.max(finite_upper)) + 2.0)
    chart = _line_chart(
        data,
        "LF pressure estimate (dB)",
        height=600,
        legend=show_legend,
        x_domain=frequency_window,
        y_domain=y_domain,
        y_axis=_response_amplitude_axis(),
        default_visible=default_visible,
    )
    
    if mil_w_data is not None and (default_visible is None or "MIL" in default_visible):
        mil_data = _series_frame(result, {"MIL": mil_w_data}).rename(columns={"value": "mil_value"})
        mil_max = float(np.max(mil_w_data[np.isfinite(mil_w_data)]))
        mil_y_domain = [0.0, max(1.0, mil_max * 1.05)]
        
        mil_chart = _line_chart(
            mil_data,
            "Max input power (W)",
            height=600,
            legend=show_legend,
            x_domain=frequency_window,
            y_domain=mil_y_domain,
            y_axis=alt.Axis(
                orient="right",
                titleColor=_TRACE_COLORS.get("MIL", "#e0aaff"),
                labelColor=_TRACE_COLORS.get("MIL", "#e0aaff")
            ),
            default_visible=["MIL"],
            y_field="mil_value",
        )
        chart = alt.layer(chart, mil_chart).resolve_scale(y="independent")

    if band is not None:
        band_area = _band_layer(band, y_domain, frequency_window)
        if band_area is not None:
            chart = band_area + chart
    show_mol = "MOL" in series
    chart = chart + _click_marker_layer(
        result, frequency_window, y_domain, show_mol=show_mol
    )
    pinned = _pinned_layer(frequency_window, y_domain, show_legend=show_legend)
    if pinned is not None:
        chart = chart + pinned
    cursors = _cursor_layer(
        cursor_rows, y_domain, frequency_window, show_mol=show_mol, show_legend=show_legend
    )
    if cursors is not None:
        chart = chart + cursors
    if pinned is not None or cursors is not None:
        return chart.resolve_scale(color="independent", strokeDash="independent")
    return chart


def _plot_excursion(result: _dccav.SimulationResult, xmax_mm: float) -> alt.Chart:
    data = _series_frame(result, {"Excursion": result.excursion_mm})
    chart = _line_chart(data, "Excursion (mm)", height=285, legend=False)
    if xmax_mm > 0:
        xmax_rule = alt.Chart(pd.DataFrame({"xmax_mm": [float(xmax_mm)]})).mark_rule(
            color="#9b2226",
            strokeDash=[6, 4],
        ).encode(y="xmax_mm:Q")
        chart = chart + xmax_rule
    pinned = _pinned_metric_layer("excursion_mm", "Excursion (mm)", ".3f")
    if pinned is not None:
        chart = (chart + pinned).resolve_scale(
            color="independent", strokeDash="independent")
    return chart


def _plot_impedance(result: _dccav.SimulationResult) -> alt.Chart:
    data = _series_frame(result, {"Impedance": result.impedance_ohm})
    chart = _line_chart(data, "Impedance (Ω)", height=285, legend=False)
    pinned = _pinned_metric_layer("impedance_ohm", "Impedance (Ω)", ".3f")
    if pinned is not None:
        chart = (chart + pinned).resolve_scale(
            color="independent", strokeDash="independent")
    return chart


def _plot_mil(result: _dccav.SimulationResult) -> alt.Chart:
    mil_w_data = result.mil_w
    data = _series_frame(result, {"MIL": mil_w_data}).rename(columns={"value": "mil_value"})
    mil_max = float(np.max(mil_w_data[np.isfinite(mil_w_data)]))
    mil_y_domain = [0.0, max(1.0, mil_max * 1.05)]
    chart = _line_chart(data, "Max input power (W)", height=240, legend=False, y_domain=mil_y_domain, y_field="mil_value")
    pinned = _pinned_metric_layer("mil_w", "Max input power (W)", ".3f")
    if pinned is not None:
        chart = (chart + pinned).resolve_scale(
            color="independent", strokeDash="independent")
    return chart


def _pin_label(load_type: str, box) -> str:
    preset = str(st.session_state.get("driver_preset_name", "Custom"))
    config = str(st.session_state.get("driver_config", "Single driver"))
    if config != "Single driver":
        preset = f"{preset} ({config})"
    if load_type == "Bass reflex":
        if isinstance(box, _dccav.PassiveRadiatorBox):
            box_txt = f"Vb {box.vb_l:.1f} L · PR Fp {box.pr_fp_hz:.1f} Hz"
        else:
            box_txt = f"Vb {box.vb_l:.1f} L · Fb {box.fb_hz:.1f} Hz"
    elif load_type == "Bandpass 4th order":
        box_txt = f"Vs {box.vs_l:.1f} L / Vp {box.vp_l:.1f} L · Fp {box.fp_hz:.1f} Hz"
    elif load_type == "Bandpass 6th order":
        box_txt = f"Vr {box.vr_l:.1f} L / Vp {box.vp_l:.1f} L · Fr {box.fr_hz:.1f} Hz / Fp {box.fp_hz:.1f} Hz"
    elif load_type == "Sealed":
        box_txt = f"Vb {box.vb_l:.1f} L"
    elif load_type == "Infinite baffle":
        box_txt = "no box"
    else:
        box_txt = (
            f"Vh {box.vh_l:.1f} L / Vl {box.vl_l:.1f} L · "
            f"fh {box.fh_hz:.0f} Hz / fl {box.fl_hz:.0f} Hz"
        )
    return f"{load_type} · {preset} · {box_txt}"


def _pinned_responses() -> list[dict]:
    """Return all response pins, migrating the legacy single-pin state."""
    pins = st.session_state.get("pinned_responses")
    if pins is None:
        legacy = st.session_state.get("pinned_response")
        pins = [legacy] if isinstance(legacy, dict) and legacy else []
        st.session_state["pinned_responses"] = pins
    if not isinstance(pins, list):
        pins = []
        st.session_state["pinned_responses"] = pins
    valid_pins = [pin for pin in pins if isinstance(pin, dict)]
    for pin in valid_pins:
        pin.setdefault("visible", True)
    return valid_pins


def _pinned_response_snapshot(
    load_type: str,
    box,
    result: _dccav.SimulationResult,
) -> dict:
    """Capture every comparable curve independently of later UI changes."""
    if load_type == "DCCAV":
        port_traces = {
            "Upper port": [float(v) for v in result.port_h_velocity],
            "Lower port": [float(v) for v in result.port_l_velocity],
        }
    elif load_type == "Bandpass 6th order":
        port_traces = {
            "Rear port": [float(v) for v in result.port_h_velocity],
            "Front port": [float(v) for v in result.port_l_velocity],
        }
    elif load_type in {"Bass reflex", "Bandpass 4th order"}:
        port_label = (
            "Passive radiator"
            if isinstance(box, _dccav.PassiveRadiatorBox)
            else "Vent"
        )
        port_traces = {
            port_label: [float(v) for v in result.port_l_velocity],
        }
    else:
        port_traces = {}
    return {
        "label": _pin_label(load_type, box),
        "load_type": load_type,
        "visible": True,
        "frequency_hz": [float(v) for v in result.frequency_hz],
        "spl_total_db": [float(v) for v in result.spl_total_db],
        "excursion_mm": [float(v) for v in result.excursion_mm],
        "impedance_ohm": [float(v) for v in result.impedance_ohm],
        "mil_w": [float(v) for v in result.mil_w],
        "group_delay_ms": [float(v) for v in _dccav.group_delay_ms(result)],
        "port_traces": port_traces,
    }


def _remove_pinned_response(index: int) -> None:
    pins = _pinned_responses()
    if 0 <= index < len(pins):
        pins.pop(index)
    st.session_state["pinned_responses"] = pins


def _set_pinned_response_visible(index: int, visible: bool) -> None:
    pins = _pinned_responses()
    if 0 <= index < len(pins):
        pins[index]["visible"] = bool(visible)
    st.session_state["pinned_responses"] = pins


def _clear_pinned_responses() -> None:
    st.session_state["pinned_responses"] = []
    # Do not let a pre-0.5 session migrate the already-cleared legacy pin again.
    st.session_state["pinned_response"] = None


def _pinned_metric_frame(value_key: str) -> tuple[pd.DataFrame, list[str]]:
    """Flatten one stored metric across valid pins and preserve legend order."""
    frames = []
    labels = []
    pinned_responses = _pinned_responses()
    visible_pins = [pin for pin in pinned_responses if pin.get("visible", True)]
    trace_budget = 2 if value_key == "port_traces" else 1
    rows_per_pin = max(
        1,
        _MAX_PINNED_CHART_ROWS // max(1, len(visible_pins) * trace_budget),
    )
    for index, pinned in enumerate(pinned_responses):
        if not pinned.get("visible", True):
            continue
        frequencies = np.asarray(pinned.get("frequency_hz", []), dtype=float)
        trace_label = f"{index + 1} · {pinned.get('label', 'Pinned response')}"
        stored = pinned.get(value_key, {})
        stored_traces = stored if isinstance(stored, dict) else {"Pinned": stored}
        pin_has_data = False
        for series_name, stored_values in stored_traces.items():
            values = np.asarray(stored_values, dtype=float)
            count = min(frequencies.size, values.size)
            if not count:
                continue
            data = pd.DataFrame({
                "frequency_hz": frequencies[:count],
                "value": values[:count],
                "label": trace_label,
                "trace": str(series_name),
            })
            data = data[
                np.isfinite(data["frequency_hz"]) & np.isfinite(data["value"])
            ]
            if data.empty:
                continue
            if len(data) > rows_per_pin:
                sampled = np.linspace(0, len(data) - 1, rows_per_pin).round().astype(int)
                data = data.iloc[np.unique(sampled)]
            frames.append(data)
            pin_has_data = True
        if pin_has_data:
            labels.append(trace_label)
    if not frames:
        return pd.DataFrame(
            columns=("frequency_hz", "value", "label", "trace")
        ), []
    return pd.concat(frames, ignore_index=True), labels


def _pinned_response_frame() -> tuple[pd.DataFrame, list[str]]:
    """Return the legacy total-response view of the generic pin store."""
    return _pinned_metric_frame("spl_total_db")


def _expand_y_domain_for_pins(
    y_domain: list[float] | None,
    frequency_window: list[float] | None,
) -> list[float] | None:
    """Keep every pinned trace visible in the selected response window."""
    if y_domain is None:
        return None
    data, _ = _pinned_response_frame()
    if frequency_window is not None and not data.empty:
        low_hz, high_hz = map(float, frequency_window)
        data = data[
            (data["frequency_hz"] >= low_hz) & (data["frequency_hz"] <= high_hz)
        ]
    if data.empty:
        return y_domain
    padding = 2.0 if frequency_window is not None else 5.0
    return [
        min(float(y_domain[0]), float(data["value"].min()) - padding),
        max(float(y_domain[1]), float(data["value"].max()) + padding),
    ]


def _pinned_metric_layer(
    value_key: str,
    y_title: str,
    tooltip_format: str,
    x_domain: list[float] | None = None,
    y_domain: list[float] | None = None,
    y_axis: alt.Axis | None = None,
    show_legend: bool = False,
) -> alt.Chart | None:
    data, labels = _pinned_metric_frame(value_key)
    if data.empty:
        return None
    traces = list(dict.fromkeys(data["trace"].tolist()))
    line = alt.Chart(data)
    if len(traces) > 1:
        line = line.mark_line(strokeWidth=2.0, clip=True)
    else:
        line = line.mark_line(strokeDash=[6, 4], strokeWidth=2.0, clip=True)
    encodings = {
        "x": alt.X(
            "frequency_hz:Q",
            scale=_log_frequency_scale(x_domain),
        ),
        "y": alt.Y(
            "value:Q",
            title=y_title,
            scale=alt.Scale(domain=y_domain, nice=False) if y_domain else alt.Undefined,
            axis=y_axis if y_axis is not None else alt.Undefined,
        ),
        "color": alt.Color(
            "label:N",
            title="Pinned simulations",
            legend=None if not show_legend else alt.Legend(title="Pinned simulations", orient="bottom", direction="horizontal"),
            scale=alt.Scale(
                domain=labels,
                range=[
                    _PIN_TRACE_COLORS[index % len(_PIN_TRACE_COLORS)]
                    for index in range(len(labels))
                ],
            ),
        ),
        "detail": alt.Detail("trace:N"),
        "tooltip": [
            alt.Tooltip("frequency_hz:Q", title="Hz", format=".2f"),
            alt.Tooltip("label:N", title="Pinned"),
            alt.Tooltip("trace:N", title="Trace"),
            alt.Tooltip("value:Q", title=y_title, format=tooltip_format),
        ],
    }
    if len(traces) > 1:
        encodings["strokeDash"] = alt.StrokeDash(
            "trace:N",
            title="Pinned trace",
            scale=alt.Scale(
                domain=traces,
                range=[[3, 3], [9, 4], [12, 3], [6, 2]],
            ),
        )
    return line.encode(**encodings)


def _pinned_layer(
    x_domain: list[float] | None = None,
    y_domain: list[float] | None = None,
    show_legend: bool = False,
) -> alt.Chart | None:
    return _pinned_metric_layer(
        "spl_total_db",
        "LF pressure estimate (dB)",
        ".3f",
        x_domain,
        y_domain,
        _response_amplitude_axis(),
        show_legend=show_legend,
    )


def _topology_comparison_series(
    ts: _dccav.DriverTS,
    load_type: str,
    box,
    freq: np.ndarray,
    voltage_v: float,
    series_r_ohm: float,
) -> tuple[float, dict[str, np.ndarray]]:
    """Simulate the loads at a shared total volume for the overlay chart.

    The active load keeps its exact box; the other topologies use their
    standard starters constrained to the same total volume.  Infinite baffle
    has no volume, so when it is active the comparison volume falls back to
    the driver's Vas.
    """
    if load_type in {"Bass reflex", "Sealed"}:
        vtot = float(box.vb_l)
    elif load_type == "Bandpass 4th order":
        vtot = float(box.vs_l + box.vp_l)
    elif load_type == "Bandpass 6th order":
        vtot = float(box.vr_l + box.vp_l)
    elif load_type == "Infinite baffle":
        vtot = float(ts.vas_l)
    else:
        vtot = float(box.vh_l + box.vl_l)
    series: dict[str, np.ndarray] = {}
    try:
        d_box = box if load_type == "DCCAV" else _batch_dccav_box(ts, vtot)
        series["DCCAV"] = _dccav.simulate(ts, d_box, freq, voltage_v, series_r_ohm).spl_total_db
    except Exception:
        logger.exception("Comparison DCCAV simulation failed")
    try:
        bp_start = _dccav.suggest_bandpass4_alignment(ts)
        bp_box = box if load_type == "Bandpass 4th order" else _dccav.design_space_box(
            ts, "Bandpass 4th order", vtot, bp_start.fp_hz)
        series["Bandpass 4th order"] = _dccav.simulate_bandpass4(
            ts, bp_box, freq, voltage_v, series_r_ohm).spl_total_db
    except Exception:
        logger.exception("Comparison bandpass simulation failed")
    try:
        bp6_start = _dccav.suggest_bandpass6_alignment(ts)
        bp6_box = box if load_type == "Bandpass 6th order" else _dccav.design_space_box(
            ts, "Bandpass 6th order", vtot, bp6_start.fp_hz)
        series["Bandpass 6th order"] = _dccav.simulate_bandpass6(
            ts, bp6_box, freq, voltage_v, series_r_ohm).spl_total_db
    except Exception:
        logger.exception("Comparison bandpass6 simulation failed")
    try:
        if load_type == "Bass reflex" and isinstance(box, _dccav.PassiveRadiatorBox):
            series["Bass reflex"] = _dccav.simulate_passive_radiator(
                ts, box, freq, voltage_v, series_r_ohm).spl_total_db
        else:
            r_box = box if load_type == "Bass reflex" else _dccav.ReflexBox(
                vb_l=vtot, fb_hz=_dccav.suggest_reflex_alignment(ts).fb_hz)
            series["Bass reflex"] = _dccav.simulate_reflex(
                ts, r_box, freq, voltage_v, series_r_ohm).spl_total_db
    except Exception:
        logger.exception("Comparison reflex simulation failed")
    try:
        s_box = box if load_type == "Sealed" else _dccav.SealedBox(vb_l=vtot)
        series["Sealed"] = _dccav.simulate_sealed(
            ts, s_box, freq, voltage_v, series_r_ohm).spl_total_db
    except Exception:
        logger.exception("Comparison sealed simulation failed")
    try:
        series["Infinite baffle"] = _dccav.simulate_infinite_baffle(
            ts, freq, voltage_v, series_r_ohm).spl_total_db
    except Exception:
        logger.exception("Comparison infinite-baffle simulation failed")
    return vtot, series


def _port_geometry_row(
    label: str,
    diameter_cm: float,
    volume_l: float,
    fb_hz: float,
    end_correction: float,
    result: _dccav.SimulationResult,
    port: str,
) -> dict:
    area_cm2 = np.pi * (diameter_cm / 2.0) ** 2
    velocity = _dccav.port_air_velocity_ms(result, area_cm2, port)
    peak_idx = int(np.nanargmax(velocity))
    return {
        "Port": label,
        "Diameter cm": float(diameter_cm),
        "Length cm": _dccav.port_length_cm(volume_l, fb_hz, diameter_cm, end_correction),
        "Peak m/s": float(velocity[peak_idx]),
        "Peak at Hz": float(result.frequency_hz[peak_idx]),
        "_volume_l": float(volume_l),
        "_fb_hz": float(fb_hz),
        "_end_correction": float(end_correction),
    }


_PORT_GEOMETRY_COLUMNS = ("Port", "Diameter cm", "Length cm", "Peak m/s", "Peak at Hz")


def _plot_group_delay(result: _dccav.SimulationResult, limit_ms: float = 0.0) -> alt.Chart:
    data = _series_frame(result, {"Group delay": _dccav.group_delay_ms(result)})
    chart = _line_chart(data, "Group delay (ms)", height=240, legend=False)
    if limit_ms > 0.0:
        limit_rule = alt.Chart(pd.DataFrame({"limit_ms": [float(limit_ms)]})).mark_rule(
            color="#9b2226",
            strokeDash=[6, 4],
        ).encode(y="limit_ms:Q")
        chart = chart + limit_rule
    pinned = _pinned_metric_layer("group_delay_ms", "Group delay (ms)", ".3f")
    if pinned is not None:
        chart = (chart + pinned).resolve_scale(
            color="independent", strokeDash="independent")
    return chart


def _plot_ports(result: _dccav.SimulationResult) -> alt.Chart:
    series = _port_series(result)
    if not series:
        raise ValueError("No port traces selected")
    data = _series_frame(result, series)
    chart = _line_chart(data, "Volume velocity (m³/s)", height=320)
    pinned = _pinned_metric_layer(
        "port_traces", "Volume velocity (m³/s)", ".6f")
    if pinned is not None:
        chart = (chart + pinned).resolve_scale(
            color="independent", strokeDash="independent")
    return chart


def _rank_value(value: float) -> float:
    return _dccav.rank_sort_value(value)


def _batch_dccav_box(ts: _dccav.DriverTS, total_volume_l: float) -> _dccav.DccavBox:
    """Starter-shaped DCCAV box constrained to an exact total volume."""
    return _dccav.design_space_box(
        ts, "DCCAV", float(total_volume_l), _dccav.suggest_alignment(ts).fl_hz)


@st.cache_data(show_spinner=False)
def _batch_rank_presets(
    preset_names: tuple[str, ...],
    load_type: str,
    max_volume_l: float,
    voltage_v: float,
    f_min_hz: float,
    f_max_hz: float,
    points: int,
    candidate_limit: int,
    goals: _dccav.OptimizationGoals | None = None,
    ranking_version: int = _FINDER_RANKING_VERSION,
) -> list[dict]:
    if ranking_version != _FINDER_RANKING_VERSION:
        raise ValueError("Unsupported Finder ranking revision")
    rows: list[dict] = []
    for name in preset_names[:int(candidate_limit)]:
        row = _dccav.rank_preset_row(
            name, load_type, float(max_volume_l), float(voltage_v),
            float(f_min_hz), float(f_max_hz), int(points), goals,
        )
        if row is not None:
            rows.append(row)
    return _dccav.sort_ranked_rows(rows)


def _finder_pool_fingerprint(workers: int) -> tuple:
    """Identity of the code+data the Finder workers hold in memory."""
    paths = [
        Path(module.__file__)
        for module in (_engine, _presets, _pricing, _ranking, _dccav)
    ]
    paths.extend([
        _presets.MANUFACTURER_DATABASE_PATH,
        _presets.LOUDSPEAKER_DATABASE_PATH,
        _pricing.DRIVER_PRICES_PATH,
    ])
    mtimes = tuple(
        path.stat().st_mtime if path.exists() else None for path in paths
    )
    return (_FINDER_RANKING_VERSION, workers, *mtimes)


def _finder_worker_pool(workers: int) -> ProcessPoolExecutor:
    """Return the process-wide match worker pool, warming it on first use.

    Spawning the pool and cold-importing the simulation stack in every worker
    costs seconds per Run match when the executor is recreated on each click.
    The pool is stashed on the persistent ``ranking`` module (this script's
    own globals are wiped by every Streamlit rerun, and one pool per session
    would leak workers across sessions/AppTest runs), and it is rebuilt
    whenever the src modules or driver/price datasets change on disk so the
    workers never serve stale code or catalogs.
    """
    key = _finder_pool_fingerprint(workers)
    pool = getattr(_ranking, "_finder_shared_pool", None)
    if pool is not None and getattr(_ranking, "_finder_shared_pool_key", None) == key:
        return pool
    if pool is not None:
        pool.shutdown(wait=False, cancel_futures=True)
    # forkserver: no re-import of the caller's __main__ in the workers (the
    # spawn method would re-execute entrypoint scripts) and no fork of a
    # thread-filled Streamlit process.
    mp_context = multiprocessing.get_context(
        "forkserver" if "forkserver" in multiprocessing.get_all_start_methods()
        else "spawn"
    )
    pool = ProcessPoolExecutor(max_workers=workers, mp_context=mp_context)
    try:
        # Fire-and-forget warm-up: force each worker to import the stack and
        # build the preset catalog now, while the user is still reading the UI.
        for _ in range(workers):
            pool.submit(_presets.driver_preset_names)
    except Exception:
        logger.warning("Finder worker warm-up submit failed", exc_info=True)
    _ranking._finder_shared_pool = pool
    _ranking._finder_shared_pool_key = key
    if not getattr(_ranking, "_finder_pool_atexit_registered", False):
        atexit.register(_drop_finder_worker_pool)
        _ranking._finder_pool_atexit_registered = True
    return pool


def _drop_finder_worker_pool() -> None:
    pool = getattr(_ranking, "_finder_shared_pool", None)
    _ranking._finder_shared_pool = None
    _ranking._finder_shared_pool_key = None
    if pool is not None:
        pool.shutdown(wait=False, cancel_futures=True)


def _batch_rank_presets_parallel(
    preset_names: tuple[str, ...],
    load_type: str,
    max_volume_l: float,
    voltage_v: float,
    f_min_hz: float,
    f_max_hz: float,
    points: int,
    candidate_limit: int,
    goals: _dccav.OptimizationGoals | None,
    progress_widget: object | None = None,
    progress_text_widget: object | None = None,
    completed_offset: int = 0,
    progress_total: int | None = None,
) -> list[dict]:
    """Rank candidates across worker processes with a real progress bar."""
    names = list(preset_names)[:int(candidate_limit)]
    total = max(len(names), 1)
    overall_total = max(int(progress_total or total), 1)
    workers = max(1, min(os.cpu_count() or 2, 8))
    owns_progress = progress_widget is None
    if progress_widget is None:
        progress_text_widget = st.empty()
        progress = st.progress(completed_offset / overall_total)
        progress_text_widget.caption(f"Matching {completed_offset}/{overall_total} simulations")
    else:
        progress = progress_widget
    rows: list[dict] = []
    done = 0
    try:
        pool = _finder_worker_pool(workers)
        # Small chunks keep the ordered map streaming: with large chunks the
        # first result (and the progress bar) stalls until a whole chunk of
        # hundreds of simulations completes, which reads as a hung start.
        results = pool.map(
            _dccav.rank_preset_row,
            names,
            [load_type] * len(names),
            [float(max_volume_l)] * len(names),
            [float(voltage_v)] * len(names),
            [float(f_min_hz)] * len(names),
            [float(f_max_hz)] * len(names),
            [int(points)] * len(names),
            [goals] * len(names),
            chunksize=max(1, min(32, len(names) // (workers * 4))),
        )
        for row in results:
            done += 1
            if done % max(1, overall_total // 100) == 0 or done == len(names):
                progress.progress(min((completed_offset + done) / overall_total, 1.0))
                if progress_text_widget is not None:
                    progress_text_widget.caption(
                        f"Matching {completed_offset + done}/{overall_total} simulations"
                        f" · {load_type}"
                    )
            if row is not None:
                rows.append(row)
    except Exception:
        _drop_finder_worker_pool()
        logger.warning(
            "Parallel Finder optimization unavailable; falling back to serial ranking",
            exc_info=True,
        )
        progress.progress(completed_offset / overall_total)
        if progress_text_widget is not None:
            progress_text_widget.caption("Parallel matching unavailable; continuing in safe mode")
        return _batch_rank_presets_with_progress(
            tuple(names), load_type, float(max_volume_l), float(voltage_v),
            float(f_min_hz), float(f_max_hz), int(points), len(names), goals,
            progress, progress_text_widget, completed_offset, overall_total,
        )
    finally:
        if owns_progress:
            progress.empty()
            if progress_text_widget is not None:
                progress_text_widget.empty()
    return _dccav.sort_ranked_rows(rows)


def _batch_rank_presets_with_progress(
    preset_names: tuple[str, ...],
    load_type: str,
    max_volume_l: float,
    voltage_v: float,
    f_min_hz: float,
    f_max_hz: float,
    points: int,
    candidate_limit: int,
    goals: _dccav.OptimizationGoals | None,
    progress: object,
    progress_text: object | None,
    completed_offset: int,
    progress_total: int,
) -> list[dict]:
    """Serial ranking path that reports real per-candidate progress."""
    names = list(preset_names)[:int(candidate_limit)]
    overall_total = max(int(progress_total), 1)
    rows: list[dict] = []
    for done, name in enumerate(names, start=1):
        row = _dccav.rank_preset_row(
            name, load_type, float(max_volume_l), float(voltage_v),
            float(f_min_hz), float(f_max_hz), int(points), goals,
        )
        if row is not None:
            rows.append(row)
        current = completed_offset + done
        if done % max(1, overall_total // 20) == 0 or done == len(names):
            progress.progress(min(current / overall_total, 1.0))
            if progress_text is not None:
                progress_text.caption(f"Matching {current}/{overall_total} simulations · {load_type}")
    return _dccav.sort_ranked_rows(rows)


def _apply_batch_result(row: dict, load_type: str) -> None:
    if load_type in ("Suspension pneumatic", "Acoustic suspension"):
        load_type = "Sealed"
    legacy_pr = load_type == "Passive radiator"
    if legacy_pr:
        load_type = "Bass reflex"
    name = str(row["Driver"])
    driver = _dccav.get_driver_preset(name)
    st.session_state["load_type"] = load_type
    st.session_state["driver_preset_name"] = name
    # Candidates are ranked as single drivers; the applied box matches that.
    st.session_state["driver_config"] = "Single driver"
    _apply_driver_preset(driver)
    _use_manual_box_strategy()
    st.session_state["workspace_mode"] = "Box Design"
    if load_type == "Bass reflex":
        st.session_state["reflex_vb_l"] = float(row["Vb L"])
        resonator = str(row.get(
            "Resonator", _RESONATOR_PR if legacy_pr else _RESONATOR_PORT))
        st.session_state["reflex_resonator_type"] = resonator
        if resonator == _RESONATOR_PR:
            pr = _dccav.suggest_pr_alignment(driver)
            st.session_state["pr_sp_cm2"] = float(pr.pr_sp_cm2)
            st.session_state["pr_fp_hz"] = float(pr.pr_fp_hz)
            st.session_state["pr_qmp"] = float(pr.pr_qmp)
            st.session_state["pr_mmp_g"] = float(pr.pr_mmp_g)
            st.session_state["pr_xmax_mm"] = float(pr.pr_xmax_mm)
        else:
            st.session_state["reflex_fb_hz"] = float(row["Fb Hz"])
    elif load_type == "Bandpass 4th order":
        st.session_state["bandpass4_vs_l"] = float(row["Vs L"])
        st.session_state["bandpass4_vp_l"] = float(row["Vp L"])
        st.session_state["bandpass4_fp_hz"] = float(row["Fp Hz"])
    elif load_type == "Bandpass 6th order":
        st.session_state["bandpass6_vr_l"] = float(row["Vr L"])
        st.session_state["bandpass6_fr_hz"] = float(row["Fr Hz"])
        st.session_state["bandpass6_vp_l"] = float(row["Vp L"])
        st.session_state["bandpass6_fp_hz"] = float(row["Fp Hz"])
    elif load_type == "Sealed":
        st.session_state["sealed_vb_l"] = float(row["Vb L"])
    elif load_type == "DCCAV":
        st.session_state["box_vh_l"] = float(row["Vh L"])
        st.session_state["box_fh_hz"] = float(row["fh Hz"])
        st.session_state["box_vl_l"] = float(row["Vl L"])
        st.session_state["box_fl_hz"] = float(row["fl Hz"])
    if load_type == "Bass reflex" and not _reflex_uses_passive_radiator():
        optimized_box = _reflex_box_from_state()
    elif load_type == "Bandpass 4th order":
        optimized_box = _bandpass4_box_from_state()
    elif load_type == "Bandpass 6th order":
        optimized_box = _bandpass6_box_from_state()
    elif load_type == "DCCAV":
        optimized_box = _box_from_state()
    else:
        optimized_box = None
    if optimized_box is not None:
        _apply_optimized_port_geometry(driver, optimized_box)
    _mark_auto_alignment_synced(driver)


def _apply_pending_batch_result() -> None:
    pending = st.session_state.pop("batch_pending_result", None)
    if not pending:
        return
    _apply_batch_result(pending["row"], str(pending["load_type"]))
    st.toast(f"Applied {pending['row']['Driver']} to the design")


def _apply_library_driver(name: str) -> None:
    """Load one library preset into the current simulation workspace."""
    driver = _dccav.get_driver_preset(name)
    st.session_state["driver_preset_name"] = name
    st.session_state["driver_config"] = "Single driver"
    _apply_driver_preset(driver)
    if _box_strategy_is_auto():
        _apply_suggested_box_for(driver)
        _mark_auto_alignment_synced(driver)
    st.session_state["workspace_mode"] = "Box Design"


def _apply_pending_atlas_point() -> None:
    pending = st.session_state.pop("atlas_pending_point", None)
    if not pending:
        return
    load_type = str(pending["load_type"])
    try:
        driver = _driver_from_state()
        if load_type == "Bass reflex":
            template = _reflex_box_from_state()
        elif load_type == "Bandpass 4th order":
            template = _bandpass4_box_from_state()
        elif load_type == "Bandpass 6th order":
            template = _bandpass6_box_from_state()
        elif load_type == "Sealed":
            template = _sealed_box_from_state()
        else:
            template = _box_from_state()
        box = _dccav.design_space_box(
            driver, load_type, float(pending["x"]), float(pending["y"]), template)
    except Exception:
        logger.exception("Could not apply the atlas point")
        return
    _use_manual_box_strategy()
    _apply_optimized_box(box)
    _mark_auto_alignment_synced(driver)
    st.toast("Applied the atlas box to the design (Manual strategy)")


def _atlas_loss_signature(load_type: str, box) -> tuple:
    if load_type == "Bass reflex":
        return (box.q_abs, box.q_leak, box.q_port)
    if load_type == "Bandpass 4th order":
        return (box.q_abs_s, box.q_abs_p, box.q_leak_s, box.q_leak_p, box.q_port)
    if load_type == "Bandpass 6th order":
        return (
            box.q_abs_r, box.q_abs_p, box.q_leak_r, box.q_leak_p,
            box.q_port_r, box.q_port_p,
        )
    if load_type == "Sealed":
        return (box.q_abs, box.q_leak)
    return (
        box.q_abs_h, box.q_abs_l, box.q_leak_h, box.q_leak_l,
        box.q_port_h, box.q_port_l,
    )


@st.cache_data(show_spinner="Mapping the design space...")
def _design_space_cached(
    ts: _dccav.DriverTS, load_type: str, losses: tuple, voltage_v: float,
) -> _dccav.DesignSpaceMap:
    # The map only reads loss factors from the template; geometry is swept.
    if load_type == "Bass reflex":
        template = _dccav.ReflexBox(
            vb_l=ts.vas_l, fb_hz=ts.fs_hz,
            q_abs=losses[0], q_leak=losses[1], q_port=losses[2])
    elif load_type == "Sealed":
        template = _dccav.SealedBox(vb_l=ts.vas_l, q_abs=losses[0], q_leak=losses[1])
    elif load_type == "Bandpass 4th order":
        template = _dccav.Bandpass4Box(
            vs_l=1.0, vp_l=1.0, fp_hz=80.0,
            q_abs_s=losses[0], q_abs_p=losses[1],
            q_leak_s=losses[2], q_leak_p=losses[3], q_port=losses[4])
    elif load_type == "Bandpass 6th order":
        template = _dccav.Bandpass6Box(
            vr_l=1.0, fr_hz=60.0, vp_l=1.0, fp_hz=80.0,
            q_abs_r=losses[0], q_abs_p=losses[1],
            q_leak_r=losses[2], q_leak_p=losses[3],
            q_port_r=losses[4], q_port_p=losses[5])
    else:
        template = _dccav.DccavBox(
            vh_l=1.0, fh_hz=100.0, vl_l=1.0, fl_hz=50.0,
            q_abs_h=losses[0], q_abs_l=losses[1],
            q_leak_h=losses[2], q_leak_l=losses[3],
            q_port_h=losses[4], q_port_l=losses[5])
    return _dccav.design_space_map(
        ts, load_type=load_type, box_template=template, voltage_v=voltage_v)


def _atlas_frame(space: _dccav.DesignSpaceMap) -> pd.DataFrame:
    rows = []
    for iy, y in enumerate(space.y_values):
        for ix, x in enumerate(space.x_values):
            rows.append({
                "x_value": round(float(x), 3),
                "y_value": round(float(y), 3),
                "f3_hz": float(space.f3_hz[iy, ix]),
                "ripple_db": float(space.ripple_db[iy, ix]),
            })
    return pd.DataFrame(rows)


def _render_atlas_tab(current_ts, load_type: str, box, sim_voltage: float) -> None:
    st.subheader("Design Space Atlas")
    if load_type == "Infinite baffle":
        st.caption("Infinite baffle has no box parameters to map.")
        return
    st.toggle(
        "Compute atlas", key="atlas_enabled",
        help="Simulates a grid of boxes around the empirical starter "
             "(a few hundred runs, cached per driver, losses and voltage).",
    )
    if not st.session_state.get("atlas_enabled", False):
        st.caption(
            "Enable to map F3 and ripple over the box plane and apply any "
            "point to the design with a click."
        )
        return
    space = _design_space_cached(
        current_ts, load_type, _atlas_loss_signature(load_type, box), sim_voltage)
    frame = _atlas_frame(space)
    metric = st.radio(
        "Color by", ("F3 (Hz)", "Ripple (dB)"), horizontal=True, key="atlas_metric")
    field = "f3_hz" if str(metric).startswith("F3") else "ripple_db"
    picker = alt.selection_point(
        name="atlas_point", fields=["x_value", "y_value"], on="click", empty=False)
    color = alt.Color(
        f"{field}:Q", title=str(metric),
        scale=alt.Scale(scheme="viridis", reverse=True))
    tooltips = [
        alt.Tooltip("x_value:Q", title=space.x_label, format=".2f"),
        alt.Tooltip("y_value:Q", title=space.y_label or "-", format=".2f"),
        alt.Tooltip("f3_hz:Q", title="F3 (Hz)", format=".1f"),
        alt.Tooltip("ripple_db:Q", title="Ripple (dB)", format=".2f"),
    ]
    if len(space.y_values) > 1:
        chart = alt.Chart(frame).mark_rect().encode(
            x=alt.X(
                "x_value:O", title=space.x_label,
                axis=alt.Axis(format="~g", labelAngle=-45, labelOverlap="greedy"),
            ),
            y=alt.Y(
                "y_value:O", title=space.y_label, sort="descending",
                axis=alt.Axis(format="~g"),
            ),
            color=color,
            tooltip=tooltips,
        ).add_params(picker).properties(height=520)
    else:
        chart = alt.Chart(frame).mark_line(point=True).encode(
            x=alt.X(
                "x_value:Q", title=space.x_label,
                scale=alt.Scale(type="log", nice=False),
            ),
            y=alt.Y("f3_hz:Q", title="F3 (Hz)"),
            tooltip=tooltips,
        ).add_params(picker).properties(height=420)
    event = st.altair_chart(
        chart, use_container_width=True, key="atlas_chart", on_select="rerun")
    st.caption(
        f"{len(space.x_values)}×{len(space.y_values)} grid around the empirical "
        f"starter, evaluated at {sim_voltage:.2f} V with 0 Ω series resistance "
        "and the current loss factors."
    )
    try:
        picked = list(event.selection["atlas_point"])
    except Exception:
        picked = []
    if not picked:
        st.caption("Click a point to inspect it, then apply it to the design.")
        return
    point = picked[0]
    x_sel = float(point.get("x_value", 0.0))
    y_sel = float(point.get("y_value", 0.0))
    match = frame[(frame["x_value"] == x_sel) & (frame["y_value"] == y_sel)]
    if match.empty:
        return
    row = match.iloc[0]
    y_txt = f" · {space.y_label} {y_sel:.2f}" if space.y_label else ""
    st.markdown(
        f"**Selected:** {space.x_label} {x_sel:.2f}{y_txt} · "
        f"F3 {_fmt_hz(row['f3_hz'])} · ripple {_fmt_db(row['ripple_db'])}"
    )
    if st.button("Apply selected box", type="primary", use_container_width=True):
        st.session_state["atlas_pending_point"] = {
            "load_type": load_type, "x": x_sel, "y": y_sel}
        st.rerun()


def _finder_price_currency(df: pd.DataFrame) -> str:
    """Currency used for value ranking: sidebar choice, else the most common."""
    priced = df[df["Price"].notna() & df["Currency"].astype(bool)]
    if priced.empty:
        return ""
    currencies = priced["Currency"].astype(str)
    sidebar = str(st.session_state.get("preset_price_currency", ""))
    if sidebar and (currencies == sidebar).any():
        return sidebar
    return str(currencies.mode().iloc[0])


def _value_sorted_frame(df: pd.DataFrame, currency: str) -> pd.DataFrame:
    """Sort by F3 × price in one currency; rows without it keep F3 order below."""
    scored = df.copy()
    scored["Value"] = [
        _dccav.price_extension_score(
            f3, price if str(cur) == currency else float("nan"))
        for f3, price, cur in zip(
            scored["F3 Hz"], scored["Price"], scored["Currency"], strict=True)
    ]
    scored = scored.sort_values(
        ["Value", "F3 Hz"], kind="stable").reset_index(drop=True)
    scored["Value"] = scored["Value"].replace(np.inf, np.nan)
    return scored


def _normalize_price_frame(df: pd.DataFrame, target_currency: str) -> pd.DataFrame:
    """Return a copy whose available prices share one display currency."""
    normalized = df.copy()
    rates, _ = _current_exchange_rates()
    converted = [
        _pricing.convert_price(price, source, target_currency, rates)
        for price, source in zip(
            normalized["Price"], normalized["Currency"], strict=True
        )
    ]
    normalized["Price"] = [
        value if value is not None else np.nan for value in converted
    ]
    normalized["Currency"] = [
        target_currency if value is not None else "" for value in converted
    ]
    return normalized


def _finder_optimizer_goals_from_state() -> _dccav.OptimizationGoals:
    return _dccav.OptimizationGoals(
        objective=_OPT_OBJECTIVE_LABELS[
            st.session_state.get("finder_objective", "Balanced")
        ],
        max_total_volume_l=float(st.session_state.get("finder_volume_l", 0.0)) or None,
        target_f3_hz=float(st.session_state.get("finder_target_f3_hz", 0.0)) or None,
        max_ripple_db=float(st.session_state.get("finder_max_ripple_db", 3.0)),
        max_excursion_ratio=float(st.session_state.get("finder_excursion_ratio", 1.0)),
        max_group_delay_ms=float(st.session_state.get("finder_max_gd_ms", 0.0)) or None,
        min_spl_db=float(st.session_state.get("finder_min_spl_db", 0.0)) or None,
    )


def _finder_load_context() -> tuple[list[str], bool]:
    """Return active Finder loads and whether infinite baffle is the only one."""
    finder_load_types = list(st.session_state.get("finder_load_types", []))
    if not finder_load_types:
        finder_load_types = [str(st.session_state.get("load_type", "DCCAV"))]
    return finder_load_types, finder_load_types == ["Infinite baffle"]


def _render_find_driver_target_sidebar() -> None:
    """Render the enclosure conditions used for every Finder candidate."""
    finder_load_types, only_infinite_baffle = _finder_load_context()
    _finder_number_input(
        "Maximum volume (L)",
        min_value=0.1,
        max_value=2000.0,
        step=1.0,
        key="finder_volume_l",
        disabled=only_infinite_baffle,
        help="Upper limit for Vh+Vl (DCCAV), chamber total (bandpass), or Vb "
             "(reflex/sealed). Finder may choose a smaller optimal volume.",
    )
    if only_infinite_baffle:
        st.caption("Infinite baffle does not use a box volume.")
    if "Bass reflex" in finder_load_types:
        with st.expander("Ports", expanded=True):
            _finder_selectbox(
                "Bass-reflex resonator",
                list(_RESONATOR_TYPES),
                key="finder_reflex_resonator_type",
                help="Rank the reflex enclosure with an air vent or a passive radiator.",
            )
    _finder_number_input(
        "Comparison voltage (V)", min_value=0.01, max_value=200.0,
        step=0.01, key="finder_voltage",
        help="All candidates are compared at the same input voltage; 2.83 V is the standard reference.",
    )


def _run_find_driver_search(filtered_preset_names: list[str]) -> None:
    """Rank the filtered candidates from the current Finder sidebar state."""
    finder_load_types = list(st.session_state.get("finder_load_types", []))
    if not finder_load_types:
        finder_load_types = [str(st.session_state.get("load_type", "DCCAV"))]
    finder_volume_l = float(_finder_value("finder_volume_l"))
    scan_count = len(filtered_preset_names)
    progress_total = max(scan_count * len(finder_load_types), 1)
    t_start = time.perf_counter()
    with st.container(key="finder_match_progress"):
        progress_text = st.empty()
        progress = st.progress(0.0)
        progress_text.caption(f"Matching 0/{progress_total} simulations")
    st.session_state.pop("_finder_match_completion", None)
    all_rows: list[dict] = []
    for load_index, lt in enumerate(finder_load_types):
        is_infinite_baffle = lt == "Infinite baffle"
        uses_pr = lt == "Bass reflex" and _reflex_uses_passive_radiator(finder=True)
        ranking_load_type = "Passive radiator" if uses_pr else lt
        # PR ranking uses the dedicated physical starter because the generic
        # enclosure optimizer currently sweeps vented-box geometry only.
        goals = (
            None if is_infinite_baffle or uses_pr
            else _finder_optimizer_goals_from_state()
        )
        rank_args = (
            tuple(filtered_preset_names),
            ranking_load_type,
            finder_volume_l,
            float(_finder_value("finder_voltage")),
            float(_finder_value("finder_f_min")),
            float(_finder_value("finder_f_max")),
            int(_finder_value("finder_points")),
            scan_count,
        )
        completed_offset = load_index * scan_count
        if scan_count > 8:
            batch_rows = _batch_rank_presets_parallel(
                *rank_args,
                goals,
                progress,
                progress_text,
                completed_offset,
                progress_total,
            )
        else:
            batch_rows = _batch_rank_presets_with_progress(
                *rank_args,
                goals,
                progress,
                progress_text,
                completed_offset,
                progress_total,
            )
        if lt == "Bass reflex":
            for row in batch_rows:
                row["_load_type"] = "Bass reflex"
                row["Resonator"] = _RESONATOR_PR if uses_pr else _RESONATOR_PORT
        all_rows.extend(batch_rows)
    min_spl_db = float(st.session_state.get("finder_min_spl_db", 0.0) or 0.0)
    if min_spl_db > 0.0:
        all_rows = [
            row for row in all_rows
            if np.isfinite(float(row.get("Peak dB", np.nan)))
            and float(row["Peak dB"]) >= min_spl_db
        ]
    all_rows = _dccav.sort_ranked_rows(all_rows)
    t_end = time.perf_counter()
    elapsed_s = t_end - t_start
    elapsed_ms_per_driver = (elapsed_s * 1000) / progress_total if progress_total > 0 else 0.0
    completion_text = (
        f"Match complete · {progress_total}/{progress_total} simulations · "
        f"{len(all_rows)} usable candidates · "
        f"Elapsed: {elapsed_s:.1f} s ({elapsed_ms_per_driver:.1f} ms/driver)"
    )
    progress.progress(1.0)
    progress_text.caption(completion_text)
    st.session_state["_finder_match_completion"] = completion_text
    st.session_state["batch_results"] = all_rows
    st.session_state["batch_search_completed"] = True
    st.session_state["batch_result_context"] = (
        tuple(finder_load_types),
        finder_volume_l,
        scan_count,
        bool(_finder_optimizer_goals_from_state()),
        str(st.session_state.get("finder_objective", "Balanced")),
        str(st.session_state.get("finder_reflex_resonator_type", _RESONATOR_PORT)),
        min_spl_db,
        _FINDER_RANKING_VERSION,
    )


def _render_find_driver_goal_sidebar() -> None:
    """Render Finder objective and constraints as the second workflow step."""
    finder_load_types, only_infinite_baffle = _finder_load_context()
    only_passive_radiator = (
        finder_load_types == ["Bass reflex"]
        and _reflex_uses_passive_radiator(finder=True)
    )
    if only_infinite_baffle:
        st.caption(
            "Infinite baffle has no enclosure to optimize; candidates are "
            "ranked on their free-air response."
        )
    elif only_passive_radiator:
        st.caption(
            "Passive-radiator candidates use the dedicated physical starter, "
            "capped by the selected maximum Vb, and are ranked by the resulting response."
        )
    else:
        if "Bass reflex" in finder_load_types and _reflex_uses_passive_radiator(finder=True):
            st.caption(
                "The selected objective optimizes the other loads; passive-radiator "
                "candidates use their dedicated starter under the same volume cap."
            )
        _finder_selectbox(
            "Optimization goal", list(_OPT_OBJECTIVE_LABELS), key="finder_objective",
            help="Every candidate box is derived by the same optimizer as the "
                 "Design workspace, without exceeding Maximum volume. Balanced "
                 "trades extension against smoothness and box practicality.",
        )
        _finder_number_input(
            "Desired bass extension F3 (Hz, 0 = deepest)", min_value=0.0,
            max_value=500.0, step=1.0, key="finder_target_f3_hz",
            help="Desired -3 dB cutoff. Lower values ask for deeper bass; enter 0 for no target.",
        )
        _finder_number_input(
            "Allowed response ripple (dB)", min_value=0.0, max_value=12.0,
            step=0.5, key="finder_max_ripple_db",
            help="Maximum peak-to-valley variation in the evaluated low-frequency passband.",
        )
        _finder_number_input(
            "Maximum excursion (× driver Xmax)", min_value=0.0, max_value=3.0,
            step=0.05, key="finder_excursion_ratio",
            help="1.0 means cone travel stays within published Xmax; 0 disables the constraint.",
        )
        _finder_number_input(
            "Maximum group delay (ms)", min_value=0.0, max_value=100.0,
            step=1.0, key="finder_max_gd_ms",
            help="Maximum allowed low-frequency group delay; 0 disables this constraint.",
        )
        _finder_number_input(
            "Minimum SPL (dB, 0 = off)", min_value=0.0, max_value=150.0,
            step=0.5, key="finder_min_spl_db",
            help="Require the candidate to reach at least this peak SPL at the comparison voltage; 0 disables.",
        )

    _finder_number_input(
        "Evaluation range start (Hz)", min_value=1.0, max_value=1000.0,
        step=1.0, key="finder_f_min",
        help="Lowest frequency included in response, excursion and delay evaluation.",
    )
    _finder_number_input(
        "Evaluation range end (Hz)", min_value=10.0, max_value=5000.0,
        step=10.0, key="finder_f_max",
        help="Highest frequency included in the low-frequency comparison.",
    )
    _finder_number_input(
        "Top results to show", min_value=1, max_value=200,
        step=5, key="finder_result_count",
    )
    _finder_number_input(
        "Simulation resolution (points)", min_value=80, max_value=1000,
        step=20, key="finder_points",
    )
    st.button(
        "Reset Finder defaults",
        key="finder_reset_defaults",
        on_click=_reset_finder_defaults,
        use_container_width=True,
        help="Restore the practical quick-scan profile without changing the active design.",
    )


def _finder_search_blocked(filtered_preset_names: list[str]) -> bool:
    """Return whether the Finder inputs are insufficient for a valid search."""
    _, only_infinite_baffle = _finder_load_context()
    return (
        not filtered_preset_names
        or float(_finder_value("finder_f_max")) <= float(_finder_value("finder_f_min"))
        or (
            not only_infinite_baffle
            and float(_finder_value("finder_volume_l")) <= 0.0
        )
    )


def _render_find_driver_actions(filtered_preset_names: list[str]) -> None:
    """Render the live Finder summary; the workspace owns the single CTA."""
    try:
        # Spin up and warm the match workers while the user is still browsing
        # so Run match starts immediately instead of paying worker cold-start.
        _finder_worker_pool(max(1, min(os.cpu_count() or 2, 8)))
    except Exception:
        logger.warning("Finder worker pool warm-up failed", exc_info=True)
    finder_load_types, only_infinite_baffle = _finder_load_context()

    finder_volume_l = float(_finder_value("finder_volume_l"))
    display_loads = [
        "Bass reflex (PR)"
        if item == "Bass reflex" and _reflex_uses_passive_radiator(finder=True)
        else item
        for item in finder_load_types
    ]
    load_label = " + ".join(display_loads) if len(display_loads) <= 2 else f"{len(display_loads)} loads"
    st.caption(
        f"Scans all {len(filtered_preset_names)} matching presets · {load_label}"
        + ("" if only_infinite_baffle else f" · ≤ {finder_volume_l:.1f} L")
    )


# Frontend payload caps: tables/dropdowns above these sizes make every rerun
# (row selection, workspace switch, any widget change) take seconds in the
# browser even when the server-side work is already cached.
_LIBRARY_TABLE_MAX_ROWS = 500
_PRESET_SELECT_MAX_OPTIONS = 1000


_TABLE_NUMBER_FORMATS = {
    "Size in": ".1f", "Fs Hz": ".1f", "Qts": ".3f", "Vas L": ".1f",
    "SPL dB": ".0f", "F3 Hz": ".1f", "F6 Hz": ".1f", "F10 Hz": ".1f",
    "Peak dB": ".1f", "Ripple dB": ".1f", "Price": ".2f", "Value": ".0f",
    "Max excursion mm": ".2f", "Min ohm": ".2f", "Vb L": ".2f",
    "Fb Hz": ".1f", "Fc Hz": ".1f", "Qtc": ".3f", "Vs L": ".2f",
    "Vp L": ".2f", "Fp Hz": ".1f", "Vr L": ".2f", "Fr Hz": ".1f",
    "Vh L": ".2f", "fh Hz": ".1f", "Vl L": ".2f", "fl Hz": ".1f",
}


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
        if name in _TABLE_NUMBER_FORMATS:
            spec = _TABLE_NUMBER_FORMATS[name]
            display[name] = [
                "—" if is_missing else format(float(value), spec)
                for value, is_missing in zip(display[name], missing, strict=True)
            ]
        elif name != "Response":
            display[name] = [
                "—" if is_missing else value
                for value, is_missing in zip(display[name], missing, strict=True)
            ]
    return display


@st.cache_data(show_spinner=False)
def _driver_library_frame(
    preset_names: tuple[str, ...],
    target_currency: str = "",
    exchange_rates: tuple[tuple[str, float], ...] = (),
) -> pd.DataFrame:
    """Build the complete filtered driver library table once per filter set."""
    rates = dict(exchange_rates)
    rows = []
    for name in preset_names:
        try:
            info = _dccav.driver_preset_info(name)
            ts_p = _dccav.get_driver_preset(name)
            ref = _dccav.driver_reference_metrics(ts_p)
            price = (
                _pricing.convert_price(
                    info.price, info.currency, target_currency, rates
                )
                if target_currency
                else info.price
            )
            rows.append({
                "Driver": name,
                "Size in": info.size_in,
                "Fs Hz": ts_p.fs_hz,
                "Qts": ts_p.qts,
                "Vas L": ts_p.vas_l,
                "SPL dB": ref.spl_2v83_db,
                "Price": price if price is not None else np.nan,
                "Currency": (
                    target_currency if target_currency and price is not None
                    else info.currency if not target_currency and price is not None
                    else ""
                ),
                "Source": info.source,
            })
        except Exception:
            rows.append({"Driver": name})
    library_columns = [
        "Driver", "Size in", "Fs Hz", "Qts", "Vas L", "SPL dB",
        "Price", "Currency", "Source",
    ]
    if not rows:
        return pd.DataFrame(columns=(
            *library_columns,
        ))
    display = _clean_display_table_frame(pd.DataFrame(rows))
    if "Price" not in display:
        display["Price"] = np.nan
    if "Currency" not in display:
        display["Currency"] = ""
    return display[[name for name in library_columns if name in display]]


def _render_driver_library(filtered_preset_names: list[str]) -> None:
    """Render every filtered driver in a scrollable, selectable library."""
    st.subheader("Candidate library")
    st.caption(
        "All matching loudspeakers are shown below. Select a row to use that driver "
        "directly in the simulation, or run a match to rank optimized enclosures."
    )
    if st.button(
        _FINDER_CTA_LABEL,
        type="primary",
        use_container_width=True,
        disabled=_finder_search_blocked(filtered_preset_names),
        key="finder_run_search_main",
    ):
        _run_find_driver_search(filtered_preset_names)
        st.rerun()

    if not filtered_preset_names:
        st.warning("No presets match the current library filters.")
        return

    # Re-serializing the full 10k-row catalog to the browser on every rerun
    # (each row selection or widget change) costs seconds of frontend time;
    # cap the table and let search/filters narrow the rest.
    shown_names = filtered_preset_names[:_LIBRARY_TABLE_MAX_ROWS]
    if len(shown_names) < len(filtered_preset_names):
        st.caption(
            f"{len(filtered_preset_names)} presets match the current filters · "
            f"showing the first {len(shown_names)}. Use the search box or the "
            "library filters to narrow the list."
        )
    else:
        st.caption(
            f"{len(filtered_preset_names)} presets match the current filters. "
            "Scroll the table to browse the complete library."
        )
    price_currency = str(st.session_state.get("preset_price_currency", ""))
    rates, rates_date = _current_exchange_rates()
    library_df = _driver_library_frame(
        tuple(shown_names),
        price_currency,
        tuple(sorted(rates.items())),
    )
    if price_currency:
        rate_note = f" · ECB {rates_date}" if rates_date else ""
        st.caption(f"Library prices shown in {price_currency}{rate_note}.")
    table_state = st.dataframe(
        library_df,
        use_container_width=True,
        height=520,
        hide_index=True,
        key="finder_driver_library_table",
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "Size in": st.column_config.NumberColumn(format="%.1f"),
            "Fs Hz": st.column_config.NumberColumn(format="%.1f"),
            "Qts": st.column_config.NumberColumn(format="%.3f"),
            "Vas L": st.column_config.NumberColumn(format="%.1f"),
            "SPL dB": st.column_config.NumberColumn(format="%.0f"),
            "Price": st.column_config.NumberColumn(
                f"Price ({price_currency})" if price_currency else "Price",
                format="%.2f",
            ),
            "Currency": None,
        },
    )
    selected_rows = getattr(table_state.selection, "rows", []) if table_state else []
    if not selected_rows:
        st.info("Select a loudspeaker row to load it into the simulation.")
        return
    selected_index = int(selected_rows[0])
    if not 0 <= selected_index < len(library_df):
        return
    selected_name = str(library_df.iloc[selected_index]["Driver"])
    st.button(
        f"Use {selected_name} in simulation",
        type="primary",
        use_container_width=True,
        key="finder_use_library_driver",
        on_click=_apply_library_driver,
        args=(selected_name,),
    )


def _render_find_driver_workspace(filtered_preset_names: list[str]) -> None:
    """Render Finder results and candidate application, separate from inputs."""
    load_type = str(st.session_state.get("load_type", "DCCAV"))

    match_completion = st.session_state.pop("_finder_match_completion", None)
    if match_completion:
        st.success(str(match_completion), icon="✅")

    finder_volume_l = float(st.session_state.get("finder_volume_l", 0.0))
    finder_loads = tuple(st.session_state.get("finder_load_types", []))
    finder_resonator = str(st.session_state.get(
        "finder_reflex_resonator_type", _RESONATOR_PORT))
    batch_rows = st.session_state.get("batch_results", [])
    context = st.session_state.get("batch_result_context", ())
    current_min_spl_db = float(
        st.session_state.get("finder_min_spl_db", 0.0) or 0.0)
    context_matches = not (
        len(context) < 2
        or tuple(context[:2]) != (finder_loads, finder_volume_l)
        or (len(context) > 5 and str(context[5]) != finder_resonator)
        or (len(context) > 6 and float(context[6]) != current_min_spl_db)
        or (len(context) <= 6 and current_min_spl_db > 0.0)
        or len(context) <= 7
        or int(context[7]) != _FINDER_RANKING_VERSION
    )
    if not context_matches:
        batch_rows = []
    if not batch_rows:
        _render_driver_library(filtered_preset_names)
        if st.session_state.get("batch_search_completed", False) and context_matches:
            st.subheader("No matching drivers")
            if current_min_spl_db > 0.0:
                st.warning(
                    f"No candidate reached the minimum SPL of "
                    f"{current_min_spl_db:.1f} dB with the current enclosure, "
                    "voltage and filters. Lower Minimum SPL or raise the comparison voltage."
                )
            else:
                st.warning(
                    "No usable candidate satisfies the current enclosure and constraints."
                )
            return
        return

    st.subheader("Recommended drivers")
    display_finder_loads = [
        "Bass reflex (PR)"
        if item == "Bass reflex" and finder_resonator == _RESONATOR_PR
        else item
        for item in finder_loads
    ]
    load_summary = (
        " + ".join(display_finder_loads)
        if len(display_finder_loads) <= 2
        else f"{len(display_finder_loads)} loads"
    )
    objective = str(context[4]) if len(context) > 4 else str(st.session_state.get("finder_objective", "Balanced"))
    volume_summary = (
        "" if finder_loads == ("Infinite baffle",)
        else f" · ≤ {finder_volume_l:.1f} L"
    )
    st.caption(
        f"{len(batch_rows)} usable candidates from {context[2]} scanned presets · "
        f"{load_summary}{volume_summary} · {objective}"
    )
    full_df = pd.DataFrame(batch_rows)
    if "_load_type" in full_df.columns:
        full_df = full_df.rename(columns={"_load_type": "Load"})
    for name, default in (
        ("Load", ""), ("Price", np.nan), ("Currency", ""), ("Buy", ""),
        ("Ripple dB", np.nan), ("Response", None), ("Class", ""),
        ("Resonator", ""), ("Mms g", np.nan), ("Le10k mH", np.nan),
    ):
        if name not in full_df.columns:
            full_df[name] = default

    selected_price_currency = str(
        st.session_state.get("preset_price_currency", "")
    )
    if selected_price_currency:
        full_df = _normalize_price_frame(full_df, selected_price_currency)

    value_currency = _finder_price_currency(full_df)
    rank_mode = _FINDER_RANK_F3
    if value_currency:
        rank_mode = st.radio(
            "Rank by",
            _FINDER_RANK_MODES,
            horizontal=True,
            key="finder_rank_mode",
            help="Best value re-sorts the scan by F3 × price: the cheapest way "
                 "to reach deep bass ranks first. Use the sidebar price filter "
                 "to cap the budget.",
        )
    if rank_mode == _FINDER_RANK_VALUE and value_currency:
        full_df = _value_sorted_frame(full_df, value_currency)
        st.caption(
            f"Best value = lowest F3 × price in {value_currency}; candidates "
            f"without a {value_currency} price keep the F3 order at the bottom."
        )
    batch_df = full_df.head(int(_finder_value("finder_result_count")))

    columns = [
        "Load", "Driver", "Brand", "Size in", "F3 Hz", "F6 Hz", "F10 Hz",
        "Peak dB", "Max excursion mm", "Min ohm",
    ]
    if batch_df["Resonator"].fillna("").astype(bool).any():
        columns.insert(1, "Resonator")
    if batch_df["Class"].fillna("").astype(bool).any():
        columns.insert(columns.index("Size in") + 1, "Class")
    if batch_df["Response"].map(lambda v: bool(v) if isinstance(v, list) else False).any():
        columns.insert(columns.index("F3 Hz"), "Response")
    if batch_df["Ripple dB"].notna().any():
        columns.insert(columns.index("Peak dB") + 1, "Ripple dB")
    if batch_df["Price"].notna().any():
        columns.insert(3, "Price")
        columns.insert(4, "Currency")
        if "Value" in batch_df.columns and batch_df["Value"].notna().any():
            columns.insert(5, "Value")
    if batch_df["Mms g"].notna().any():
        columns.insert(columns.index("Size in") + 1, "Mms g")
    if batch_df["Le10k mH"].notna().any():
        columns.insert(columns.index("Min ohm") + 1, "Le10k mH")
    if len(finder_loads) > 1:
        columns += ["Vb L", "Fb Hz", "Vh L", "fh Hz", "Vl L", "fl Hz",
                     "Vs L", "Vp L", "Fp Hz", "Vr L", "Fr Hz", "Fc Hz", "Qtc"]
    elif finder_loads == ("Bass reflex",):
        columns += ["Vb L", "Fb Hz"]
    elif finder_loads == ("Bandpass 4th order",):
        columns += ["Vs L", "Vp L", "Fp Hz"]
    elif finder_loads == ("Bandpass 6th order",):
        columns += ["Vr L", "Fr Hz", "Vp L", "Fp Hz"]
    elif finder_loads == ("Sealed",):
        columns += ["Vb L", "Fc Hz", "Qtc"]
    elif finder_loads == ("Infinite baffle",):
        columns += ["Fc Hz", "Qtc"]
    else:
        columns += ["Vh L", "fh Hz", "Vl L", "fl Hz"]
    if batch_df["Buy"].fillna("").astype(bool).any():
        columns.append("Buy")

    display_df = _clean_display_table_frame(batch_df[columns])
    columns = list(display_df.columns)
    table_state = st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        key=f"batch_results_table_{'value' if 'Value' in columns else 'f3'}",
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "F3 Hz": st.column_config.NumberColumn(format="%.1f"),
            "F6 Hz": st.column_config.NumberColumn(format="%.1f"),
            "F10 Hz": st.column_config.NumberColumn(format="%.1f"),
            "Peak dB": st.column_config.NumberColumn(format="%.1f"),
            "Ripple dB": st.column_config.NumberColumn(format="%.1f"),
            "Price": st.column_config.NumberColumn(format="%.2f"),
            "Value": st.column_config.NumberColumn(
                "Value (F3 × price)", format="%.0f",
                help="Lower is better: cheapest path to deep bass.",
            ),
            "Max excursion mm": st.column_config.NumberColumn(format="%.2f"),
            "Min ohm": st.column_config.NumberColumn(format="%.2f"),
            "Size in": st.column_config.NumberColumn(format="%.1f"),
            "Mms g": st.column_config.NumberColumn(format="%.1f"),
            "Le10k mH": st.column_config.NumberColumn(format="%.3f"),
            "Vb L": st.column_config.NumberColumn(format="%.2f"),
            "Fb Hz": st.column_config.NumberColumn(format="%.1f"),
            "Fc Hz": st.column_config.NumberColumn(format="%.1f"),
            "Qtc": st.column_config.NumberColumn(format="%.3f"),
            "Vs L": st.column_config.NumberColumn(format="%.2f"),
            "Vp L": st.column_config.NumberColumn(format="%.2f"),
            "Fp Hz": st.column_config.NumberColumn(format="%.1f"),
            "Vr L": st.column_config.NumberColumn(format="%.2f"),
            "Fr Hz": st.column_config.NumberColumn(format="%.1f"),
            "Vh L": st.column_config.NumberColumn(format="%.2f"),
            "fh Hz": st.column_config.NumberColumn(format="%.1f"),
            "Vl L": st.column_config.NumberColumn(format="%.2f"),
            "fl Hz": st.column_config.NumberColumn(format="%.1f"),
            "Buy": st.column_config.LinkColumn(display_text="Buy"),
            "Response": st.column_config.LineChartColumn(
                "Response (rel dB)", y_min=_dccav.SPARKLINE_FLOOR_DB, y_max=0.0,
            ),
        },
    )
    csv_columns = [name for name in columns if name != "Response"]
    st.download_button(
        "Download candidate CSV",
        batch_df[csv_columns].to_csv(index=False).encode("utf-8"),
        "load_forge_candidates.csv",
        "text/csv",
        use_container_width=True,
    )

    selected_rows = getattr(table_state.selection, "rows", []) if table_state else []
    if not selected_rows:
        st.info("Select one candidate to inspect it without replacing the current design.")
        _render_driver_library(filtered_preset_names)
        return
    selected_index = int(selected_rows[0])
    if not 0 <= selected_index < len(batch_df):
        _render_driver_library(filtered_preset_names)
        return
    selected_row = batch_df.iloc[selected_index].to_dict()
    row_load_type = str(selected_row.get("Load", load_type))
    with st.container(border=True):
        st.markdown(f"#### Candidate preview · {selected_row['Driver']} · {row_load_type}")
        p1, p2, p3, p4 = st.columns(4)
        p1.metric("F3", f"{float(selected_row['F3 Hz']):.1f} Hz")
        p2.metric("Peak LF SPL", f"{float(selected_row['Peak dB']):.1f} dB")
        p3.metric("Max excursion", f"{float(selected_row['Max excursion mm']):.2f} mm")
        p4.metric("Min impedance", f"{float(selected_row['Min ohm']):.2f} Ω")
        if row_load_type == "DCCAV":
            st.caption(
                f"Vh {float(selected_row['Vh L']):.2f} L / "
                f"{float(selected_row['fh Hz']):.1f} Hz · "
                f"Vl {float(selected_row['Vl L']):.2f} L / "
                f"{float(selected_row['fl Hz']):.1f} Hz"
            )
        elif row_load_type == "Bass reflex":
            resonator = str(selected_row.get("Resonator", _RESONATOR_PORT))
            tuning_label = "PR system tuning" if resonator == _RESONATOR_PR else "Fb"
            st.caption(
                f"{resonator} · Vb {float(selected_row['Vb L']):.2f} L · "
                f"{tuning_label} {float(selected_row['Fb Hz']):.1f} Hz"
            )
        elif row_load_type == "Bandpass 4th order":
            st.caption(
                f"Vs sealed {float(selected_row['Vs L']):.2f} L · "
                f"Vp ported {float(selected_row['Vp L']):.2f} L · "
                f"Fp {float(selected_row['Fp Hz']):.1f} Hz"
            )
        elif row_load_type == "Bandpass 6th order":
            st.caption(
                f"Vr rear {float(selected_row['Vr L']):.2f} L / "
                f"Fr {float(selected_row['Fr Hz']):.1f} Hz · "
                f"Vp front {float(selected_row['Vp L']):.2f} L / "
                f"Fp {float(selected_row['Fp Hz']):.1f} Hz"
            )
        elif row_load_type == "Sealed":
            st.caption(
                f"Vb {float(selected_row['Vb L']):.2f} L · "
                f"Fc {float(selected_row['Fc Hz']):.1f} Hz · "
                f"Qtc {float(selected_row['Qtc']):.3f}"
            )
        if st.button("Apply candidate to design", type="primary", use_container_width=True):
            st.session_state["batch_pending_result"] = {
                "row": selected_row,
                "load_type": row_load_type,
            }
            st.rerun()
    _render_driver_library(filtered_preset_names)


@st.cache_data(show_spinner="Simulating T/S tolerance band...")
def _tolerance_band_cached(
    ts: _dccav.DriverTS,
    load_type: str,
    box,
    freq: np.ndarray,
    voltage_v: float,
    series_r_ohm: float,
    tolerance: float,
) -> _dccav.ToleranceBand:
    return _dccav.monte_carlo_response_band(
        ts, load_type=load_type, box=box, freq_hz=freq,
        voltage_v=voltage_v, series_r_ohm=series_r_ohm, tolerance=tolerance,
    )


@st.fragment
def _render_response_tab(
    current_ts: _dccav.DriverTS,
    load_type: str,
    box,
    result: _dccav.SimulationResult,
    thresholds: dict[int, float],
    freq: np.ndarray,
    sim_voltage: float,
    sim_series_r: float,
) -> None:
    chart_sig = _chart_signature()
    compare_loads_on = bool(st.session_state.get("plot_compare_loads", False))

    # --- 1. Compute state needed for charts ---
    cursor_rows = _cursor_rows(result, thresholds)

    compare_series = None
    if compare_loads_on:
        comp_vtot, comp_series = _topology_comparison_series(
            current_ts, load_type, box, freq, sim_voltage, sim_series_r)
        if comp_series:
            compare_series = comp_series

    band = None
    if st.session_state.get("plot_tolerance_band", False) and not compare_series:
        tolerance = float(st.session_state.get("plot_tolerance_pct", 15.0)) / 100.0
        try:
            tolerance_load_type = (
                "Passive radiator"
                if load_type == "Bass reflex" and _reflex_uses_passive_radiator()
                else load_type
            )
            band = _tolerance_band_cached(
                current_ts, tolerance_load_type, box, freq,
                sim_voltage, sim_series_r, tolerance)
        except Exception:
            logger.exception("Tolerance band computation failed")

    full_window = (
        max(1, int(np.ceil(float(freq[0])))),
        max(2, int(np.floor(float(freq[-1])))),
    )
    if full_window[1] <= full_window[0]:
        full_window = (full_window[0], full_window[0] + 1)
    raw_window = st.session_state.get("plot_response_window_hz", full_window)
    try:
        raw_tuple = tuple(raw_window)
        raw_low, raw_high = map(int, raw_tuple)
    except (TypeError, ValueError):
        raw_tuple = full_window
        raw_low, raw_high = full_window
    normalized_window = (
        min(max(raw_low, full_window[0]), full_window[1] - 1),
        max(min(raw_high, full_window[1]), full_window[0] + 1),
    )
    if normalized_window[0] >= normalized_window[1]:
        normalized_window = full_window
    if raw_tuple != normalized_window:
        st.session_state["plot_response_window_hz"] = normalized_window

    frequency_window = [float(normalized_window[0]), float(normalized_window[1])]

    # --- 2. Render Charts ---
    if compare_series or _response_series(result):
        current_series = compare_series if compare_series else _response_series(result)
        available_traces = list(current_series.keys())
        # Filter session state to only valid traces
        saved_traces = st.session_state.get("plot_response_traces", ["Total"])
        selected_traces = [t for t in saved_traces if t in available_traces]
        if not selected_traces and available_traces:
            selected_traces = [available_traces[0]]

        st.altair_chart(
            _plot_response(
                result, cursor_rows, compare_series, band,
                frequency_window=frequency_window,
                show_legend=False,
                default_visible=selected_traces,
            ),
            width="stretch",
            key=f"response_chart_{chart_sig}",
        )
        st.caption(
            "Use the frequency slider below to zoom; click the chart to place a point marker "
            "and double-click to clear it."
        )
    else:
        st.caption("Response pens off.")

    st.divider()

    # --- 3. Render Analysis Options & Actions ---
    st.pills(
        "Traces",
        available_traces if (compare_series or _response_series(result)) else ["Total"],
        selection_mode="multi",
        default=selected_traces if (compare_series or _response_series(result)) else ["Total"],
        key="plot_response_traces",
        label_visibility="collapsed",
    )
    
    pinned_state = _pinned_responses()
    num_cols = 5 if pinned_state else 4
    ctrl_cols = st.columns(num_cols)
    
    with ctrl_cols[0]:
        st.toggle("Compare loads", key="plot_compare_loads")
    with ctrl_cols[1]:
        st.toggle(
            "Tolerance band", key="plot_tolerance_band", disabled=compare_loads_on,
            help="Monte Carlo 5-95th percentile spread from T/S tolerances.",
        )
    with ctrl_cols[2]:
        if st.button(
            "Pin response",
            use_container_width=True,
            disabled=len(pinned_state) >= _MAX_PINNED_RESPONSES,
            help=f"Keep up to {_MAX_PINNED_RESPONSES} response traces while changing load or box.",
        ):
            st.session_state["pinned_responses"] = [
                *pinned_state,
                _pinned_response_snapshot(load_type, box, result),
            ]
            st.rerun()

    if pinned_state:
        with ctrl_cols[4]:
            if st.button("Clear all pins", use_container_width=True):
                _clear_pinned_responses()
                st.rerun()
        with ctrl_cols[5]:
            st.button(
                "Reset zoom",
                key="plot_response_reset_zoom",
                use_container_width=True,
                disabled=tuple(st.session_state.get("plot_response_window_hz", full_window)) == full_window,
                on_click=_reset_response_zoom,
                args=(full_window,),
            )
    else:
        with ctrl_cols[4]:
            st.button(
                "Reset zoom",
                key="plot_response_reset_zoom",
                use_container_width=True,
                disabled=tuple(st.session_state.get("plot_response_window_hz", full_window)) == full_window,
                on_click=_reset_response_zoom,
                args=(full_window,),
            )
    
    if st.session_state.get("plot_tolerance_band", False) and not compare_series:
        st.number_input(
            "T/S tolerance (%)", min_value=5.0, max_value=30.0, step=1.0,
            key="plot_tolerance_pct",
        )
        if band is not None:
            st.caption(f"±{float(st.session_state.get('plot_tolerance_pct', 15.0)):.0f}% MC, {band.runs} runs.")
        else:
            st.caption("Unavailable for current params.")
    
    if compare_loads_on:
        if compare_series:
            st.caption(f"Comparing total response at ~{comp_vtot:.1f} L. Other pens suspended.")
        else:
            st.caption("No comparison load available.")

    # --- 4. Render Zoom Slider ---
    st.slider(
        "Chart zoom (Hz)",
        min_value=full_window[0],
        max_value=full_window[1],
        step=1,
        key="plot_response_window_hz",
        label_visibility="collapsed",
        help="Move either handle to zoom the chart. This only changes the plot window, "
             "not the simulation frequency range set in the sidebar.",
    )

    # --- 5. Render Captions and Pinned List ---
    # Captions removed to save vertical space!

    if pinned_state:
        visible_pin_count = sum(
            bool(pin.get("visible", True)) for pin in pinned_state)
        st.caption(
            f"Pinned responses: {len(pinned_state)}/{_MAX_PINNED_RESPONSES} · "
            f"{visible_pin_count} visible · dashed colored traces"
        )
        with st.expander("Manage pinned responses"):
            for index, pinned in enumerate(pinned_state):
                is_visible = bool(pinned.get("visible", True))
                label_col, visibility_col, remove_col = st.columns([5, 1, 1])
                with label_col:
                    visibility_text = "visible" if is_visible else "hidden"
                    st.caption(
                        f"{index + 1}. {pinned.get('label', 'Pinned response')} · "
                        f"{visibility_text}"
                    )
                with visibility_col:
                    if st.button(
                        "Hide" if is_visible else "Show",
                        key=f"toggle_pinned_response_{index}",
                        help=(
                            f"Hide pinned simulation {index + 1} without clearing it"
                            if is_visible
                            else f"Show pinned simulation {index + 1} on every chart"
                        ),
                        use_container_width=True,
                    ):
                        _set_pinned_response_visible(index, not is_visible)
                        st.rerun()
                with remove_col:
                    if st.button(
                        "Clear",
                        key=f"remove_pinned_response_{index}",
                        help=f"Clear pinned simulation {index + 1}",
                        use_container_width=True,
                    ):
                        _remove_pinned_response(index)
                        st.rerun()


def _render_ports_tab(
    result: _dccav.SimulationResult,
    port_geometry_rows: list[dict],
    load_type: str,
    passive_radiator: bool = False,
) -> None:
    chart_sig = _chart_signature()
    if load_type not in {"DCCAV", "Bass reflex", "Bandpass 4th order", "Bandpass 6th order"}:
        st.caption("The current load type has no ports.")
        return
    if passive_radiator:
        st.checkbox("Passive radiator", key="plot_port_lower")
    elif load_type == "Bandpass 6th order":
        p1, p2 = st.columns(2)
        with p1:
            st.checkbox("Rear port", key="plot_port_upper")
        with p2:
            st.checkbox("Front port", key="plot_port_lower")
    else:
        st.checkbox("Vent volume velocity", key="plot_port_lower")
    st.subheader(
        "Radiator Volume Velocity"
        if passive_radiator
        else "Port Volume Velocity"
    )
    if _port_series(result):
        st.altair_chart(_plot_ports(result), use_container_width=True, key=f"ports_chart_{chart_sig}")
    else:
        st.caption("Port pens off.")

    st.subheader("Duct sizing")
    if load_type == "DCCAV":
        p1, p2 = st.columns(2)
        with p1:
            st.number_input(
                "Upper port diameter (cm, 0 = off)", min_value=0.0, max_value=60.0,
                step=0.5, key="box_port_d_h_cm")
        with p2:
            st.number_input(
                "Lower port diameter (cm, 0 = off)", min_value=0.0, max_value=60.0,
                step=0.5, key="box_port_d_l_cm")
        st.caption(
            "Auto strategies recalculate both diameters from tuning, air speed and "
            "the displacement minimum-area golden rule. "
            "Duct lengths use the Helmholtz relation: the upper port counts "
            "two flanged ends, the lower vent one flanged and one free end; "
            "air-speed warnings use the ~5% of c guideline."
        )
    elif load_type == "Bandpass 4th order":
        st.number_input(
            "Front vent diameter (cm, 0 = off)", min_value=0.0,
            max_value=60.0, step=0.5, key="bandpass4_port_d_cm")
        st.caption(
            "Auto strategies recalculate the vent from tuning, air speed and "
            "the displacement minimum-area golden rule. "
            "Only the front-chamber vent radiates externally; length uses "
            "one flanged and one free end."
        )
    elif load_type == "Bandpass 6th order":
        p1, p2 = st.columns(2)
        with p1:
            st.number_input(
                "Rear vent diam (cm, 0 = off)", min_value=0.0,
                max_value=60.0, step=0.5, key="bandpass6_port_d_r_cm")
        with p2:
            st.number_input(
                "Front vent diam (cm, 0 = off)", min_value=0.0,
                max_value=60.0, step=0.5, key="bandpass6_port_d_p_cm")
        st.caption(
            "Auto strategies recalculate both vents from tuning, air speed and "
            "the displacement minimum-area golden rule. "
            "Both vents use one flanged and one free end."
        )
    elif load_type == "Bass reflex" and not passive_radiator:
        st.number_input(
            "Vent diameter (cm, 0 = off)", min_value=0.0,
            max_value=60.0, step=0.5, key="reflex_port_d_cm")
        st.caption(
            "Auto strategies size the vent from tuning, air speed and "
            "the displacement minimum-area rule."
        )
    elif passive_radiator:
        st.caption("The passive radiator is sized in the sidebar with area, mass and suspension.")

    if port_geometry_rows:
        if passive_radiator:
            st.subheader("Radiator Geometry")
            st.caption(
                "Equivalent diaphragm diameter and simulated radiator motion "
                f"at {float(st.session_state['sim_voltage']):.2f} V."
            )
        else:
            st.subheader("Port Geometry")
            st.caption(
                f"Circular ducts at {float(st.session_state['sim_voltage']):.2f} V; "
                f"air-speed guideline {_dccav.PORT_VELOCITY_GUIDELINE_MS:.0f} m/s (5% of c)."
            )
        st.dataframe(
            pd.DataFrame(port_geometry_rows)[list(_PORT_GEOMETRY_COLUMNS)],
            use_container_width=True,
            hide_index=True,
            column_config={
                "Diameter cm": st.column_config.NumberColumn(format="%.1f"),
                "Length cm": st.column_config.NumberColumn(format="%.1f"),
                "Peak m/s": st.column_config.NumberColumn(format="%.1f"),
                "Peak at Hz": st.column_config.NumberColumn(format="%.0f"),
            },
        )


def _csv_bytes(result: _dccav.SimulationResult) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "frequency_hz",
        "spl_total_db",
        "spl_driver_db",
        "spl_port_db",
        "excursion_mm",
        "impedance_ohm",
        "mil_w",
        "mol_db",
        "group_delay_ms",
        "upper_port_volume_velocity_m3_s",
        "lower_port_volume_velocity_m3_s",
    ])
    for row in zip(
        result.frequency_hz,
        result.spl_total_db,
        result.spl_driver_db,
        result.spl_port_db,
        result.excursion_mm,
        result.impedance_ohm,
        result.mil_w,
        result.mol_db,
        _dccav.group_delay_ms(result),
        result.port_h_velocity,
        result.port_l_velocity,
        strict=True,
    ):
        writer.writerow([f"{float(v):.8g}" for v in row])
    return buf.getvalue().encode("utf-8")


_default("driver_fs_hz", 48.14)
_default("driver_vas_l", 11.52)
_default("driver_qts", 0.362)
_default("driver_qms", 2.372)
_default("driver_re_ohm", 6.89)
_default("driver_sd_mode", "Diameter")
_default("driver_diameter_mm", 104.0)
_default("driver_sd_cm2", _dccav.sd_from_diameter(104.0))
_default("driver_le_mh", 0.421)
_default("driver_le10k_mh", 0.0)
_default("driver_xmax_mm", 3.1)
_default("driver_pe_w", 60.0)
_default("driver_mms_g", 0.0)
_default("driver_cms_mm_n", 0.0)
_default("driver_bl_tm", 0.0)
_default("driver_panel_air_load", True)
_default("driver_panel_coupling", 0.90)
_default("driver_preset_name", "KEF B110B article example")
_default("driver_config", "Single driver")
_default("preset_family_filter", "All")
_default("preset_source_filter", "All")
_default("preset_size_filter", "All")
_default("preset_class_filter", "All")
_default("preset_search", "")
_default("preset_price_enabled", False)
_default("preset_max_price", 0.0)
_default("preset_price_currency", "")
_default("loss_q_abs_h", 15.0)
_default("loss_q_abs_l", 15.0)
_default("loss_q_leak_h", 1000.0)
_default("loss_q_leak_l", 1000.0)
_default("loss_q_port_h", 15.0)
_default("loss_q_port_l", 15.0)
_default("reflex_q_abs", _DEFAULT_REFLEX_Q_ABS)
_default("reflex_q_leak", _DEFAULT_REFLEX_Q_LEAK)
_default("reflex_q_port", _DEFAULT_REFLEX_Q_PORT)
_default("reflex_custom_losses", False)
_default("reflex_port_d_cm", 5.0)
_default("reflex_resonator_type", _RESONATOR_PORT)
_default("pr_sp_cm2", 200.0)
_default("pr_fp_hz", 20.0)
_default("pr_qmp", 5.0)
_default("pr_mmp_g", 100.0)
_default("pr_xmax_mm", 0.0)
_default("pr_q_abs", 15.0)
_default("pr_q_leak", 1000.0)
_default("bandpass4_q_abs_s", 15.0)
_default("bandpass4_q_abs_p", 15.0)
_default("bandpass4_q_leak_s", 1000.0)
_default("bandpass4_q_leak_p", 1000.0)
_default("bandpass4_q_port", 15.0)
_default("bandpass4_port_d_cm", 5.0)
_default("bandpass6_q_abs_r", 15.0)
_default("bandpass6_q_abs_p", 15.0)
_default("bandpass6_q_leak_r", 1000.0)
_default("bandpass6_q_leak_p", 1000.0)
_default("bandpass6_q_port_r", 15.0)
_default("bandpass6_q_port_p", 15.0)
_default("bandpass6_port_d_r_cm", 5.0)
_default("bandpass6_port_d_p_cm", 5.0)
_default("box_port_d_h_cm", 5.0)
_default("box_port_d_l_cm", 5.0)
_default("sealed_q_abs", 15.0)
_default("sealed_q_leak", 1000.0)
_default("load_type", "DCCAV")
if st.session_state["load_type"] in ("Suspension pneumatic", "Acoustic suspension"):
    st.session_state["load_type"] = "Sealed"
elif st.session_state["load_type"] == "Passive radiator":
    # Compatibility for pre-0.5.2 sessions: PR is a resonator choice, not a load.
    st.session_state["load_type"] = "Bass reflex"
    st.session_state["reflex_resonator_type"] = _RESONATOR_PR
    if "pr_vb_l" in st.session_state:
        st.session_state["reflex_vb_l"] = float(st.session_state["pr_vb_l"])
_default("sim_f_min", 10.0)
_default("sim_f_max", 500.0)
_default("sim_points", 600)
_default("sim_voltage", 2.83)
_default("sim_series_r_ohm", 0.0)
_default("sim_auto_align", True)
_default("plot_response_traces", ["Total"])
_default("plot_port_traces", list(_PORT_TRACE_OPTIONS))
_default("plot_response_total", "Total" in st.session_state["plot_response_traces"])
_default(
    "plot_response_driver",
    "Cone" in st.session_state["plot_response_traces"]
    or "Driver" in st.session_state["plot_response_traces"],
)
_default("plot_response_lower_port", "Lower port" in st.session_state["plot_response_traces"])
_default("plot_response_mol", True)
if int(st.session_state.get("_response_defaults_version", 0) or 0) < _RESPONSE_DEFAULTS_VERSION:
    st.session_state["plot_response_mol"] = True
    st.session_state["_response_defaults_version"] = _RESPONSE_DEFAULTS_VERSION
_default("plot_response_window_hz", (10, 500))
_default("plot_show_mil", False)
_default("plot_compare_loads", False)
_default("plot_tolerance_band", False)
_default("plot_tolerance_pct", 15.0)
_default("atlas_enabled", False)
_default("atlas_metric", "F3 (Hz)")
_default("plot_port_upper", "Upper port" in st.session_state["plot_port_traces"])
_default("plot_port_lower", "Lower port" in st.session_state["plot_port_traces"])
_default("cursor_auto_markers", list(_AUTO_CURSOR_OPTIONS))
_ensure_plot_control_state()
_default("opt_align_mode", "Empirical (article)")
_default("opt_objective", "Balanced")
_default("opt_max_volume_l", 0.0)
_default("opt_target_f3_hz", 0.0)
_default("opt_max_ripple_db", 3.0)
_default("opt_excursion_ratio", 1.0)
_default("opt_max_gd_ms", 0.0)
_default("workspace_mode", "Bass Match")
_default("ui_show_advanced", False)
_ensure_finder_defaults()
if "finder_load_types" in st.session_state:
    legacy_finder_loads = list(st.session_state["finder_load_types"])
    if "Passive radiator" in legacy_finder_loads:
        st.session_state["finder_reflex_resonator_type"] = _RESONATOR_PR
        st.session_state["finder_load_types"] = list(dict.fromkeys(
            "Bass reflex" if item == "Passive radiator" else item
            for item in legacy_finder_loads
        ))
_preserve_library_filters()
_preserve_design_state()
if "box_strategy" not in st.session_state:
    if st.session_state.get("sim_auto_align", True):
        _set_box_strategy_state("Balanced")
    elif st.session_state.get("opt_align_mode") == "Optimized (goals)":
        _set_box_strategy_state(_normalize_box_strategy("Optimized"))
    else:
        _set_box_strategy_state("Manual")
else:
    # Live sessions may still carry v0.3 "Suggested"/"Optimized" values.
    _set_box_strategy_state(
        _normalize_box_strategy(st.session_state["box_strategy"]))
if (
    st.session_state.get("load_type") == "Bass reflex"
    and _reflex_uses_passive_radiator()
    and _box_strategy_is_auto()
):
    # The generic optimizer sweeps duct tuning, which is not the PR mass and
    # suspension problem. Keep the radiator controls explicitly editable.
    _set_box_strategy_state("Manual")
if "_optimizer_engine_revision" not in st.session_state:
    st.session_state["_optimizer_engine_revision"] = _OPTIMIZER_ENGINE_REVISION
_apply_pending_batch_result()
_apply_pending_atlas_point()

_share_token = st.query_params.get("d")
if _share_token and st.session_state.get("_applied_share_token") != _share_token:
    st.session_state["_applied_share_token"] = _share_token
    try:
        _snapshot_design_state()
        _share_count = _apply_loaded_params(_decode_share_payload(_share_token))
        _mark_auto_alignment_synced()
        st.toast(f"Loaded {_share_count} parameters from the shared link")
    except Exception:
        logger.exception("Invalid share link payload")
        st.warning("The shared link could not be decoded; using the current parameters.")

try:
    _seed_alignment = _dccav.suggest_alignment(_driver_from_state())
    _seed_reflex = _dccav.suggest_reflex_alignment(_driver_from_state())
    _seed_bandpass4 = _dccav.suggest_bandpass4_alignment(_driver_from_state())
    _seed_bandpass6 = _dccav.suggest_bandpass6_alignment(_driver_from_state())
    _seed_sealed = _dccav.suggest_sealed_alignment(_driver_from_state())
except Exception:
    _seed_alignment = _dccav.DccavAlignment(3.1, 162.0, 6.25, 62.0, 51.5)
    _seed_reflex = _dccav.ReflexAlignment(11.52, 48.14)
    _seed_bandpass4 = _dccav.Bandpass4Alignment(4.09, 11.52, 94.0)
    _seed_bandpass6 = _dccav.Bandpass6Alignment(4.09, 60.0, 11.52, 94.0)
    _seed_sealed = _dccav.SealedAlignment(11.52, 68.1, 0.512)
_default("box_vh_l", float(_seed_alignment.vh_l))
_default("box_fh_hz", float(_seed_alignment.fh_hz))
_default("box_vl_l", float(_seed_alignment.vl_l))
_default("box_fl_hz", float(_seed_alignment.fl_hz))
_default("reflex_vb_l", float(_seed_reflex.vb_l))
_default("reflex_fb_hz", float(_seed_reflex.fb_hz))
_default("bandpass4_vs_l", float(_seed_bandpass4.vs_l))
_default("bandpass4_vp_l", float(_seed_bandpass4.vp_l))
_default("bandpass4_fp_hz", float(_seed_bandpass4.fp_hz))
_default("bandpass6_vr_l", float(_seed_bandpass6.vr_l))
_default("bandpass6_fr_hz", float(_seed_bandpass6.fr_hz))
_default("bandpass6_vp_l", float(_seed_bandpass6.vp_l))
_default("bandpass6_fp_hz", float(_seed_bandpass6.fp_hz))
_default("sealed_vb_l", float(_seed_sealed.vb_l))
_sync_auto_alignment_if_needed()


if not _BRAND_IMAGE.exists():
    st.title("Load Forge")
st.caption(
    f"v{_VERSION} · DCCAV / bandpass 4th & 6th / reflex / PR / sealed / infinite baffle · "
    "T/S driven response model"
)

finder_library_filters_slot = st.empty()


current_ts = None
current_alignment = None
current_reflex_alignment = None
current_bandpass4_alignment = None
current_sealed_alignment = None
derived = None

with st.sidebar:
    if _BRAND_IMAGE.exists():
        st.image(str(_BRAND_IMAGE), use_container_width=True)
    _render_project_menu()
    st.divider()
    _render_workspace_tabs()
    workspace_mode = str(st.session_state.get("workspace_mode", "Bass Match"))
    
    if workspace_mode == "Bass Match":
        bm_tab1, bm_tab2, bm_tab3 = st.tabs(["Load type", "Performance", "Library Filters"])
        
        with bm_tab1:
            if "finder_load_types" not in st.session_state:
                st.session_state["finder_load_types"] = [
                    str(st.session_state.get("load_type", "DCCAV"))]
            _finder_load_set = set(st.session_state["finder_load_types"])
            new_set = _render_load_type_buttons(_finder_load_set, single_select=False)
            if new_set != _finder_load_set:
                if not new_set:
                    new_set = {"Sealed"}
                st.session_state["finder_load_types"] = sorted(
                    new_set, key=lambda x: _ALL_LOAD_TYPES.index(x))
                st.rerun()
            st.caption("Toggle the loads you want to compare. At least one must stay active.")
            _render_find_driver_target_sidebar()

        with bm_tab2:
            _render_find_driver_goal_sidebar()
            
        with bm_tab3:
            all_preset_names = _dccav.driver_preset_names()
            _render_finder_library_filters(all_preset_names)
            filtered_preset_names = _filter_driver_preset_names(
                all_preset_names,
                source=st.session_state.get("preset_source_filter", "All"),
                family=st.session_state.get("preset_family_filter", "All"),
                size=st.session_state.get("preset_size_filter", "All"),
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
                driver_class=str(st.session_state.get("preset_class_filter", "All"))
            )
            _render_find_driver_actions(filtered_preset_names)

    else:
        bd_tab1, bd_tab2, bd_tab3 = st.tabs(["Driver", "Load Selection", "Enclosure Parameters"])
        
        all_preset_names = _dccav.driver_preset_names()
        with bd_tab1:
            st.text_input("Search preset", key="preset_search", placeholder="Brand or model")
        filtered_preset_names = _filter_driver_preset_names(
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
        select_names = filtered_preset_names[:_PRESET_SELECT_MAX_OPTIONS]
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
                on_change=_on_driver_preset_change,
            )
            if preset_name != "Custom":
                try:
                    purchase = _purchase_markdown(_dccav.driver_preset_info(preset_name))
                except ValueError:
                    purchase = None
                if purchase:
                    st.markdown(purchase)
                    
            c1, c2 = st.columns(2)
            with c1:
                st.number_input("Fs (Hz)", min_value=1.0, max_value=500.0, step=_step5("driver_fs_hz", 0.1),
                                key="driver_fs_hz", on_change=_on_driver_param_change)
                st.number_input("Qts", min_value=0.05, max_value=2.0, step=_step5("driver_qts", 0.001),
                                format="%.3f", key="driver_qts", on_change=_on_driver_param_change)
                st.number_input("Re (Ω)", min_value=0.1, max_value=64.0, step=_step5("driver_re_ohm", 0.01),
                                key="driver_re_ohm", on_change=_on_driver_param_change)
            with c2:
                st.number_input("Vas (L)", min_value=0.1, max_value=1000.0, step=_step5("driver_vas_l", 0.1),
                                key="driver_vas_l", on_change=_on_driver_param_change)
                st.number_input("Qms", min_value=0.051, max_value=50.0, step=_step5("driver_qms", 0.001),
                                format="%.3f", key="driver_qms", on_change=_on_driver_param_change)
                st.number_input("Le (mH)", min_value=0.0, max_value=20.0, step=_step5("driver_le_mh", 0.001),
                                format="%.3f", key="driver_le_mh", on_change=_on_driver_param_change)

            st.radio("Piston input", ["Diameter", "Sd"], horizontal=True, key="driver_sd_mode",
                     on_change=_on_driver_param_change)
            if st.session_state.get("driver_sd_mode", "Diameter") == "Diameter":
                st.number_input("Piston diameter (mm)", min_value=10.0, max_value=1000.0,
                                step=_step5("driver_diameter_mm", 0.1), key="driver_diameter_mm",
                                on_change=_on_driver_param_change)
                st.caption(
                    f"Sd = {_dccav.sd_from_diameter(st.session_state.get('driver_diameter_mm', 100)):.1f} cm²"
                )
            else:
                st.number_input("Sd (cm²)", min_value=1.0, max_value=5000.0, step=_step5("driver_sd_cm2", 1.0),
                                key="driver_sd_cm2", on_change=_on_driver_param_change)

            st.checkbox(
                "Panel air loading",
                key="driver_panel_air_load",
                on_change=_on_driver_param_change,
                help="Enabled by default. Adds the air mass coupled to a diaphragm "
                     "mounted on a finite baffle, lowering mounted Fs and sensitivity. "
                     "Disable it for classical free-air T/S comparisons.",
            )
            if st.session_state.get("driver_panel_air_load", True):
                st.slider(
                    "Panel coupling",
                    min_value=0.0,
                    max_value=1.0,
                    step=0.01,
                    key="driver_panel_coupling",
                    on_change=_on_driver_param_change,
                    help="Fraction of the low-frequency baffled-piston air-mass "
                         "increment. 0.90 is the standard partial-baffle approximation.",
                )
                try:
                    _panel_mass_g, _panel_fs_hz = _dccav.panel_air_load_metrics(
                        _driver_from_state())
                    st.caption(
                        f"Mounted Fs {_panel_fs_hz:.2f} Hz · added air mass "
                        f"{_panel_mass_g:.3f} g"
                    )
                except (KeyError, ValueError):
                    pass

            d3, d4 = st.columns(2)
            with d3:
                st.number_input("Xmax (mm)", min_value=0.0, max_value=100.0, step=_step5("driver_xmax_mm", 0.1),
                                key="driver_xmax_mm", on_change=_on_driver_param_change)
                
                derived = None
                try:
                    derived = _dccav.complete_driver(_driver_from_state())
                except Exception:
                    pass

                lbl_mms = f"Mms (g) [calc: {derived.mms_kg*1000:.1f}]" if (derived and not st.session_state.get("driver_mms_g")) else "Mms (g)"
                step_mms = _step5("driver_mms_g", 0.01, derived.mms_kg*1000 if derived else None)
                st.number_input(lbl_mms, min_value=0.0, max_value=1000.0, step=step_mms,
                                key="driver_mms_g", on_change=_on_driver_param_change)
                
                lbl_bl = f"Bl (T·m) [calc: {derived.bl_tm:.2f}]" if (derived and not st.session_state.get("driver_bl_tm")) else "Bl (T·m)"
                step_bl = _step5("driver_bl_tm", 0.01, derived.bl_tm if derived else None)
                st.number_input(lbl_bl, min_value=0.0, max_value=100.0, step=step_bl,
                                key="driver_bl_tm", on_change=_on_driver_param_change)
            with d4:
                st.number_input("Pe (W)", min_value=0.0, max_value=5000.0, step=_step5("driver_pe_w", 1.0),
                                key="driver_pe_w", on_change=_on_driver_param_change)
                
                lbl_cms = f"Cms (mm/N) [calc: {derived.cms_m_per_n*1000:.3f}]" if (derived and not st.session_state.get("driver_cms_mm_n")) else "Cms (mm/N)"
                step_cms = _step5("driver_cms_mm_n", 0.001, derived.cms_m_per_n*1000 if derived else None)
                st.number_input(lbl_cms, min_value=0.0, max_value=100.0, step=step_cms,
                                format="%.3f", key="driver_cms_mm_n",
                                on_change=_on_driver_param_change)
                st.number_input("Le10k (mH)", min_value=0.0, max_value=20.0, step=_step5("driver_le10k_mh", 0.001),
                                format="%.3f", key="driver_le10k_mh",
                                on_change=_on_driver_param_change,
                                help="Voice coil inductance measured at 10 kHz, as "
                                     "reported alongside Le (1 kHz) on some pro-audio "
                                     "datasheets. Informational only — not used in the "
                                     "impedance/response simulation.")

        with bd_tab2:
            _load_set = {st.session_state.get("load_type", "Sealed")}
            new_set = _render_load_type_buttons(_load_set, single_select=True)
            if new_set != _load_set:
                new_lt = next(iter(new_set), "Sealed")
                st.session_state["load_type"] = new_lt
                _on_load_type_change()
                st.rerun()
            st.selectbox(
                "Driver configuration",
                list(_dccav.DRIVER_CONFIGURATIONS),
                key="driver_config",
                on_change=_auto_align_current_driver,
                help="Identical drivers sharing one enclosure. Parallel/series "
                     "sets the wiring; an isobaric pair couples two drivers "
                     "behind one radiating cone (halves Vas). The Finder always "
                     "ranks single drivers.",
            )
            if st.session_state.get("driver_config", "Single driver") != "Single driver":
                try:
                    _composite = _driver_from_state()
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
                _BOX_STRATEGIES,
                key="box_strategy",
                on_change=_on_box_strategy_change,
                disabled=st.session_state.get("load_type", "Sealed") == "Infinite baffle",
                width="stretch",
                help="One optimizer drives every goal: Max extension favors the "
                     "deepest F3, Balanced trades extension against smoothness "
                     "and practicality, Flattest favors the smoothest passband. "
                     "The box re-applies automatically when the driver, load or "
                     "constraints change. Manual unlocks volumes and tuning for "
                     "direct editing.",
            )
            # Simulate Inputs
            sim_c1, sim_c2 = st.columns(2)
            with sim_c1:
                st.number_input(
                    "Voltage (V)", min_value=0.01, max_value=200.0, step=_step5("sim_voltage", 0.01),
                    key="sim_voltage",
                )
            with sim_c2:
                st.number_input(
                    "Series R (Ω)", min_value=0.0, max_value=100.0,
                    step=_step5("sim_series_r_ohm", 0.1), key="sim_series_r_ohm",
                    help="Amplifier output + cable + crossover-coil DCR in series with the "
                         "driver. Optimizer and driver ranking evaluate at 0 Ω.",
                )
            
            try:
                current_ts = _driver_from_state()
                current_alignment = _dccav.suggest_alignment(current_ts)
                current_reflex_alignment = _dccav.suggest_reflex_alignment(current_ts)
                current_bandpass4_alignment = _dccav.suggest_bandpass4_alignment(current_ts)
                current_bandpass6_alignment = _dccav.suggest_bandpass6_alignment(current_ts)
                current_sealed_alignment = _dccav.suggest_sealed_alignment(current_ts)
                derived = _dccav.complete_driver(current_ts)
                panel_added_mass_g, panel_fs_hz = _dccav.panel_air_load_metrics(current_ts)
                load_type = st.session_state.get("load_type", "Sealed")
                box_strategy = str(st.session_state.get("box_strategy", "Balanced"))
                if (
                    box_strategy in _OPT_OBJECTIVE_LABELS
                    and st.session_state.get("_optimizer_engine_revision", 0)
                    != _OPTIMIZER_ENGINE_REVISION
                ):
                    try:
                        refreshed = _run_box_optimizer(current_ts)
                        _apply_optimized_box(refreshed.box)
                        _mark_auto_alignment_synced(current_ts)
                        st.toast("Optimized alignment refreshed with the current physics engine")
                    except ValueError as exc:
                        _apply_empirical_box_for(current_ts)
                        st.session_state["opt_last_summary"] = None
                        st.warning(f"Stored optimized box was discarded: {exc}")
                    st.session_state["_optimizer_engine_revision"] = (
                        _OPTIMIZER_ENGINE_REVISION)

                if load_type != "Infinite baffle" and box_strategy in _OPT_OBJECTIVE_LABELS:
                    st.caption(
                        "The optimizer re-applies this goal automatically when the "
                        "driver, load or constraints change."
                    )
                    auto_box_error = st.session_state.get("_auto_box_error")
                    if auto_box_error:
                        st.warning(
                            "No buildable optimized box for the current goal; the "
                            f"starter box is shown instead. ({auto_box_error})"
                        )
                    st.markdown("**Optimization constraints**")
                    st.number_input("Max total volume (L, 0 = off)", min_value=0.0, max_value=2000.0,
                                    step=1.0, key="opt_max_volume_l")
                    st.number_input("Max ripple (dB)", min_value=0.0, max_value=12.0,
                                    step=0.5, key="opt_max_ripple_db")
                    st.number_input("Excursion limit (x Xmax, 0 = off)", min_value=0.0, max_value=3.0,
                                    step=0.05, key="opt_excursion_ratio")
                    st.number_input("Target F3 (Hz, 0 = lowest)", min_value=0.0, max_value=500.0,
                                    step=1.0, key="opt_target_f3_hz")
                    st.number_input("Max group delay (ms, 0 = off)", min_value=0.0, max_value=100.0,
                                    step=1.0, key="opt_max_gd_ms")
                    current_optimizer_summary = _current_optimizer_summary(current_ts)
                    if current_optimizer_summary:
                        st.caption(current_optimizer_summary)
                        
            except Exception as exc:
                current_ts = None
                current_alignment = None
                current_reflex_alignment = None
                current_bandpass4_alignment = None
                current_bandpass6_alignment = None
                current_sealed_alignment = None
                derived = None
                st.error(f"Driver parameters are invalid - check the T/S values. ({exc})")

            if current_ts is not None:
                box_edit_disabled = st.session_state.get("box_strategy", "Balanced") != "Manual"
                if load_type == "Bass reflex":
                    _box_number_with_nudge(
                        "Vb box (L)", "reflex_vb_l", min_value=0.05, max_value=1000.0, step=0.01,
                        disabled=box_edit_disabled)
                    with st.expander("Ports", expanded=True):
                        st.selectbox(
                            "Resonator type",
                            _RESONATOR_TYPES,
                            key="reflex_resonator_type",
                            help="Choose an air vent or a passive diaphragm for the same bass-reflex load.",
                        )
                        if _reflex_uses_passive_radiator():
                            st.caption("Passive radiator resonator")
                            st.number_input(
                                "PR area Sp (cm²)", min_value=1.0, max_value=5000.0,
                                step=1.0, key="pr_sp_cm2")
                            st.number_input(
                                "PR free-air Fp (Hz)", min_value=1.0, max_value=500.0,
                                step=0.1, key="pr_fp_hz")
                            st.number_input(
                                "PR mechanical Qmp", min_value=0.5, max_value=50.0,
                                step=_step5("pr_qmp", 0.1), key="pr_qmp")
                            st.number_input(
                                "PR moving mass Mmp (g)", min_value=1.0, max_value=5000.0,
                                step=1.0, key="pr_mmp_g")
                            st.number_input(
                                "PR Xmax (mm, 0 = unknown)", min_value=0.0, max_value=50.0,
                                step=0.1, key="pr_xmax_mm")
                            active_pr = _pr_box_from_state()
                            rho_c2 = 1.18 * 344.0 ** 2
                            cab = (active_pr.vb_l / 1000.0) / rho_c2
                            pr_sp_m2 = active_pr.pr_sp_cm2 / 10_000.0
                            pr_cmp = 1.0 / (
                                (2 * np.pi * active_pr.pr_fp_hz) ** 2
                                * (active_pr.pr_mmp_g / 1000.0)
                            )
                            pr_cap = pr_cmp * pr_sp_m2 ** 2
                            f_sys = (
                                active_pr.pr_fp_hz * np.sqrt(1.0 + pr_cap / cab)
                                if cab > 0 else active_pr.pr_fp_hz
                            )
                            st.caption(f"Box + PR system tuning ~{f_sys:.1f} Hz")
                        else:
                            _box_number_with_nudge(
                                "Fb tuning (Hz)", "reflex_fb_hz", min_value=1.0,
                                max_value=1000.0, step=0.1, disabled=box_edit_disabled)
                    if _reflex_uses_passive_radiator():
                        with st.expander("Loss factors"):
                            st.number_input(
                                "Qabs box", min_value=0.2, max_value=500.0,
                                step=_step5("pr_q_abs", 0.5), key="pr_q_abs")
                            st.number_input(
                                "Qleak box", min_value=1.0, max_value=10000.0,
                                step=_step5("pr_q_leak", 10.0), key="pr_q_leak")
                    else:
                        active_reflex_losses = _reflex_box_from_state()
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
                                step=_step5("reflex_q_abs", 0.5), key="reflex_q_abs", disabled=disabled)
                            st.number_input(
                                "Qleak box", min_value=1.0, max_value=10000.0,
                                step=_step5("reflex_q_leak", 10.0), key="reflex_q_leak", disabled=disabled)
                            st.number_input(
                                "Qport", min_value=0.2, max_value=500.0,
                                step=_step5("reflex_q_port", 0.5), key="reflex_q_port", disabled=disabled)
                elif load_type == "Sealed":
                    _box_number_with_nudge(
                        "Vb sealed (L)", "sealed_vb_l", min_value=0.05, max_value=100000.0, step=0.01,
                        disabled=box_edit_disabled)
                    if current_ts is not None:
                        fc_hz, qtc = _dccav.sealed_system_metrics(current_ts, _sealed_box_from_state())
                        st.caption(f"Closed-box Fc {fc_hz:.1f} Hz · Qtc {qtc:.3f}")
                    with st.expander("Sealed loss factors"):
                        st.number_input(
                            "Qabs sealed", min_value=0.2, max_value=500.0, step=_step5("sealed_q_abs", 0.5),
                            key="sealed_q_abs")
                        st.number_input(
                            "Qleak sealed", min_value=1.0, max_value=10000.0, step=_step5("sealed_q_leak", 10.0),
                            key="sealed_q_leak")
                elif load_type == "Bandpass 4th order":
                    b1, b2 = st.columns(2)
                    with b1:
                        _box_number_with_nudge(
                            "Vs sealed rear (L)", "bandpass4_vs_l", min_value=0.05,
                            max_value=100000.0, step=0.01, disabled=box_edit_disabled)
                    with b2:
                        _box_number_with_nudge(
                            "Vp ported front (L)", "bandpass4_vp_l", min_value=0.05,
                            max_value=100000.0, step=0.01, disabled=box_edit_disabled)
                    _box_number_with_nudge(
                        "Fp front tuning (Hz)", "bandpass4_fp_hz", min_value=1.0,
                        max_value=5000.0, step=0.1, disabled=box_edit_disabled)
                    with st.expander("Bandpass loss factors"):
                        l1, l2 = st.columns(2)
                        with l1:
                            st.number_input("Qabs sealed rear", min_value=0.2, max_value=500.0,
                                            step=_step5("bandpass4_q_abs_s", 0.5), key="bandpass4_q_abs_s")
                            st.number_input("Qleak sealed rear", min_value=1.0, max_value=10000.0,
                                            step=_step5("bandpass4_q_leak_s", 10.0), key="bandpass4_q_leak_s")
                        with l2:
                            st.number_input("Qabs ported front", min_value=0.2, max_value=500.0,
                                            step=_step5("bandpass4_q_abs_p", 0.5), key="bandpass4_q_abs_p")
                            st.number_input("Qleak ported front", min_value=1.0, max_value=10000.0,
                                            step=_step5("bandpass4_q_leak_p", 10.0), key="bandpass4_q_leak_p")
                            st.number_input("Qport front", min_value=0.2, max_value=500.0,
                                            step=_step5("bandpass4_q_port", 0.5), key="bandpass4_q_port")
                elif load_type == "Bandpass 6th order":
                    b1, b2 = st.columns(2)
                    with b1:
                        _box_number_with_nudge(
                            "Vr rear ported (L)", "bandpass6_vr_l", min_value=0.05,
                            max_value=100000.0, step=0.01, disabled=box_edit_disabled)
                        _box_number_with_nudge(
                            "Fr rear tuning (Hz)", "bandpass6_fr_hz", min_value=1.0,
                            max_value=5000.0, step=0.1, disabled=box_edit_disabled)
                    with b2:
                        _box_number_with_nudge(
                            "Vp front ported (L)", "bandpass6_vp_l", min_value=0.05,
                            max_value=100000.0, step=0.01, disabled=box_edit_disabled)
                        _box_number_with_nudge(
                            "Fp front tuning (Hz)", "bandpass6_fp_hz", min_value=1.0,
                            max_value=5000.0, step=0.1, disabled=box_edit_disabled)
                    with st.expander("Bandpass loss factors"):
                        l1, l2 = st.columns(2)
                        with l1:
                            st.number_input("Qabs rear", min_value=0.2, max_value=500.0,
                                            step=_step5("bandpass6_q_abs_r", 0.5), key="bandpass6_q_abs_r")
                            st.number_input("Qleak rear", min_value=1.0, max_value=10000.0,
                                            step=_step5("bandpass6_q_leak_r", 10.0), key="bandpass6_q_leak_r")
                            st.number_input("Qport rear", min_value=0.2, max_value=500.0,
                                            step=_step5("bandpass6_q_port_r", 0.5), key="bandpass6_q_port_r")
                        with l2:
                            st.number_input("Qabs front", min_value=0.2, max_value=500.0,
                                            step=_step5("bandpass6_q_abs_p", 0.5), key="bandpass6_q_abs_p")
                            st.number_input("Qleak front", min_value=1.0, max_value=10000.0,
                                            step=_step5("bandpass6_q_leak_p", 10.0), key="bandpass6_q_leak_p")
                            st.number_input("Qport front", min_value=0.2, max_value=500.0,
                                            step=_step5("bandpass6_q_port_p", 0.5), key="bandpass6_q_port_p")
                elif load_type == "Infinite baffle":
                    st.caption("No box controls: the rear wave is assumed to be fully isolated by an infinite partition.")
                else:
                    b1, b2 = st.columns(2)
                    with b1:
                        _box_number_with_nudge(
                            "Vh upper (L)", "box_vh_l", min_value=0.05, max_value=1000.0, step=0.01,
                            disabled=box_edit_disabled)
                        _box_number_with_nudge(
                            "fh upper (Hz)", "box_fh_hz", min_value=1.0, max_value=1000.0, step=0.1,
                            disabled=box_edit_disabled)
                    with b2:
                        _box_number_with_nudge(
                            "Vl lower (L)", "box_vl_l", min_value=0.05, max_value=1000.0, step=0.01,
                            disabled=box_edit_disabled)
                        _box_number_with_nudge(
                            "fl lower (Hz)", "box_fl_hz", min_value=1.0, max_value=1000.0, step=0.1,
                            disabled=box_edit_disabled)

                    with st.expander("Loss factors"):
                        l1, l2 = st.columns(2)
                        with l1:
                            st.number_input("Qabs upper", min_value=0.2, max_value=500.0, step=_step5("loss_q_abs_h", 0.5), key="loss_q_abs_h")
                            st.number_input("Qleak upper", min_value=1.0, max_value=10000.0, step=_step5("loss_q_leak_h", 10.0), key="loss_q_leak_h")
                            st.number_input("Qport upper", min_value=0.2, max_value=500.0, step=_step5("loss_q_port_h", 0.5), key="loss_q_port_h")
                        with l2:
                            st.number_input("Qabs lower", min_value=0.2, max_value=500.0, step=_step5("loss_q_abs_l", 0.5), key="loss_q_abs_l")
                            st.number_input("Qleak lower", min_value=1.0, max_value=10000.0, step=_step5("loss_q_leak_l", 10.0), key="loss_q_leak_l")
                            st.number_input("Qport lower", min_value=0.2, max_value=500.0, step=_step5("loss_q_port_l", 0.5), key="loss_q_port_l")

                if load_type != "Infinite baffle" and box_edit_disabled:
                    st.caption("Switch Box strategy to Manual to edit volumes and tuning directly.")


if workspace_mode == "Bass Match":
    _render_find_driver_workspace(filtered_preset_names)
    st.stop()


try:
    if current_ts is None:
        raise ValueError("Driver parameters are incomplete")
    if st.session_state["sim_f_max"] <= st.session_state["sim_f_min"]:
        raise ValueError("F max must be greater than F min")
    load_type = st.session_state["load_type"]
    is_reflex_load = load_type == "Bass reflex"
    is_pr = is_reflex_load and _reflex_uses_passive_radiator()
    is_reflex = is_reflex_load and not is_pr
    is_bandpass4 = load_type == "Bandpass 4th order"
    is_bandpass6 = load_type == "Bandpass 6th order"
    is_sealed = load_type == "Sealed"
    is_infinite_baffle = load_type == "Infinite baffle"
    chart_sig = _chart_signature()
    if is_pr:
        box = _pr_box_from_state()
    elif is_reflex:
        box = _reflex_box_from_state()
    elif is_bandpass4:
        box = _bandpass4_box_from_state()
    elif is_bandpass6:
        box = _bandpass6_box_from_state()
    elif is_sealed:
        box = _sealed_box_from_state()
    elif is_infinite_baffle:
        box = None
    else:
        box = _box_from_state()
    freq = np.geomspace(
        float(st.session_state["sim_f_min"]),
        float(st.session_state["sim_f_max"]),
        int(st.session_state["sim_points"]),
    )
    sim_voltage = float(st.session_state["sim_voltage"])
    sim_series_r = float(st.session_state.get("sim_series_r_ohm", 0.0))
    if is_pr:
        result = _dccav.simulate_passive_radiator(current_ts, box, freq, sim_voltage, sim_series_r)
    elif is_reflex:
        result = _dccav.simulate_reflex(current_ts, box, freq, sim_voltage, sim_series_r)
    elif is_bandpass4:
        result = _dccav.simulate_bandpass4(current_ts, box, freq, sim_voltage, sim_series_r)
    elif is_bandpass6:
        result = _dccav.simulate_bandpass6(current_ts, box, freq, sim_voltage, sim_series_r)
    elif is_sealed:
        result = _dccav.simulate_sealed(current_ts, box, freq, sim_voltage, sim_series_r)
    elif is_infinite_baffle:
        result = _dccav.simulate_infinite_baffle(current_ts, freq, sim_voltage, sim_series_r)
    else:
        result = _dccav.simulate(current_ts, box, freq, sim_voltage, sim_series_r)
    metrics = _dccav.response_metrics(result)
    thresholds = _dccav.response_threshold_frequencies(result)
    z_peak_freqs = _dccav.impedance_peak_frequencies(result)
    model_warnings = [] if load_type != "DCCAV" else (
        _dccav.alignment_diagnostics(current_ts, box)
        + _dccav.response_sanity_warnings(current_ts, box, thresholds)
    )
    if is_bandpass4:
        model_warnings.extend(_dccav.bandpass4_diagnostics(current_ts, box, result))
    if is_bandpass6:
        model_warnings.extend(_dccav.bandpass6_diagnostics(current_ts, box, result))
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
            port_geometry_rows.append(_port_geometry_row(
                "Vent", vent_d_cm, box.vb_l, box.fb_hz, 1.43, result, "lower"))
    elif is_pr:
        pr_box = box
        pr_sp_cm2 = pr_box.pr_sp_cm2
        pr_xmax = pr_box.pr_xmax_mm
        velocity = _dccav.port_air_velocity_ms(result, pr_sp_cm2, "lower")
        peak_idx = int(np.nanargmax(velocity))
        pr_exc_peak = float(np.nanmax(np.abs(result.port_l_velocity) / (2 * np.pi * result.frequency_hz * pr_sp_cm2 / 10_000.0))) * 1000.0
        port_geometry_rows.append({
            "Port": "Passive radiator",
            "Diameter cm": float(np.sqrt(4 * pr_sp_cm2 / np.pi)),
            "Length cm": float("nan"),
            "Peak m/s": float(velocity[peak_idx]),
            "Peak at Hz": float(result.frequency_hz[peak_idx]),
            "_volume_l": float(pr_box.vb_l),
            "_fb_hz": float(pr_box.pr_fp_hz),
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
            port_geometry_rows.append(_port_geometry_row(
                "Front vent", vent_d_cm, box.vp_l, box.fp_hz, 1.43, result, "lower"))
    elif is_bandpass6:
        rear_d_cm = float(st.session_state.get("bandpass6_port_d_r_cm", 0.0))
        front_d_cm = float(st.session_state.get("bandpass6_port_d_p_cm", 0.0))
        if rear_d_cm > 0.0:
            port_geometry_rows.append(_port_geometry_row(
                "Rear vent", rear_d_cm, box.vr_l, box.fr_hz, 1.43, result, "upper"))
        if front_d_cm > 0.0:
            port_geometry_rows.append(_port_geometry_row(
                "Front vent", front_d_cm, box.vp_l, box.fp_hz, 1.43, result, "lower"))
    elif load_type == "DCCAV":
        upper_d_cm = float(st.session_state.get("box_port_d_h_cm", 0.0))
        lower_d_cm = float(st.session_state.get("box_port_d_l_cm", 0.0))
        if upper_d_cm > 0.0:
            port_geometry_rows.append(_port_geometry_row(
                "Upper port", upper_d_cm, box.vh_l, box.fh_hz, 1.64, result, "upper"))
        if lower_d_cm > 0.0:
            port_geometry_rows.append(_port_geometry_row(
                "Lower port", lower_d_cm, box.vl_l, box.fl_hz, 1.43, result, "lower"))
    for row in port_geometry_rows:
        is_pr_row = row.get("_is_pr", False)
        if not is_pr_row and row["Length cm"] <= 0.0:
            max_hz = _dccav.port_max_tuning_hz(
                row["_volume_l"], row["Diameter cm"], row["_end_correction"])
            min_d_cm = _dccav.port_min_diameter_cm(
                row["_volume_l"], row["_fb_hz"], row["_end_correction"])
            model_warnings.append(
                f"{row['Port']}: a {row['Diameter cm']:.1f} cm opening in {row['_volume_l']:.1f} L "
                f"tunes at most to ~{max_hz:.0f} Hz even with zero duct length; reaching "
                f"{row['_fb_hz']:.1f} Hz needs a diameter of at least {min_d_cm:.1f} cm."
            )
        if row["Peak m/s"] > _dccav.PORT_VELOCITY_GUIDELINE_MS:
            model_warnings.append(
                f"{row['Port']} air speed peaks at {row['Peak m/s']:.1f} m/s near "
                f"{row['Peak at Hz']:.0f} Hz at {float(st.session_state['sim_voltage']):.2f} V - above "
                f"the ~{_dccav.PORT_VELOCITY_GUIDELINE_MS:.0f} m/s (5% of c) chuffing guideline; "
                "enlarge the port or reduce drive level."
            )
        if not is_pr_row:
            golden_cm = _dccav.port_displacement_min_diameter_cm(
                current_ts, row["_fb_hz"])
            if 0.0 < row["Diameter cm"] < golden_cm:
                model_warnings.append(
                    f"{row['Port']}: {row['Diameter cm']:.1f} cm is below the minimum-area "
                    f"golden rule for this driver's displacement (needs ≥ {golden_cm:.1f} cm "
                    f"at {row['_fb_hz']:.1f} Hz); expect compression at rated excursion "
                    "regardless of the simulated drive level."
                )
        if not is_pr_row and row["Length cm"] > 0.0:
            duct_fraction = _dccav.port_volume_fraction(
                row["_volume_l"], row["_fb_hz"], row["Diameter cm"],
                row["_end_correction"])
            if duct_fraction > _dccav.PORT_MAX_VOLUME_FRACTION:
                duct_l = duct_fraction * row["_volume_l"]
                model_warnings.append(
                    f"{row['Port']}: the {row['Diameter cm']:.1f} × {row['Length cm']:.1f} cm "
                    f"duct occupies {duct_l:.2f} L = {duct_fraction:.0%} of the "
                    f"{row['_volume_l']:.1f} L chamber (reflex directive ≤ "
                    f"{_dccav.PORT_MAX_VOLUME_FRACTION:.0%}); the box is too small for "
                    "this tuning and diameter - enlarge the chamber, raise the tuning "
                    "or reduce the port."
                )
            pipe_hz = _dccav.port_pipe_resonance_hz(row["Length cm"])
            if pipe_hz < _dccav.PORT_PIPE_RESONANCE_GUARD * row["_fb_hz"]:
                model_warnings.append(
                    f"{row['Port']}: the {row['Length cm']:.1f} cm duct has its first "
                    f"pipe resonance at ~{pipe_hz:.0f} Hz, inside the working band "
                    f"(< {_dccav.PORT_PIPE_RESONANCE_GUARD:.0f}× the {row['_fb_hz']:.1f} Hz "
                    "tuning); shorten the duct with a smaller diameter or higher tuning."
                )
            max_straight_cm = _dccav.port_max_straight_length_cm(row["_volume_l"])
            if row["Length cm"] > max_straight_cm:
                model_warnings.append(
                    f"{row['Port']}: the {row['Length cm']:.1f} cm duct is longer than a "
                    f"{row['_volume_l']:.1f} L box (~{max_straight_cm:.0f} cm on a side) can "
                    "plausibly hold in a straight run; it needs an L-shaped/slot fold "
                    "(not modeled here), a bigger box, or a higher tuning."
                )

    design_name = str(st.session_state.get("driver_preset_name", "Custom"))
    design_config = str(st.session_state.get("driver_config", "Single driver"))
    if design_config != "Single driver":
        design_name = f"{design_name} ({design_config})"
    design_strategy = str(st.session_state.get("box_strategy", "Balanced"))

    st.markdown(
        f"<div style='font-weight: 700; font-size: 1.15rem; margin-top: 0; margin-bottom: 0.1rem; color: rgba(250,250,250,.95);'>"
        f"{load_type} &middot; {design_name}"
        f"</div>",
        unsafe_allow_html=True
    )
    resonator_caption = "Passive radiator &middot; " if is_pr else ""
    st.markdown(
        f"<div style='font-size: 0.8rem; color: rgba(250,250,250,.65); margin-bottom: 0.2rem;'>"
        f"{resonator_caption}{design_strategy} alignment &middot; {sim_voltage:.2f} V"
        f"</div>",
        unsafe_allow_html=True
    )

    tab_labels = ["Response", "Excursion", "Impedance"]
    if not (is_sealed or is_infinite_baffle):
        tab_labels.append("Ports")
    tab_labels.append("Group Delay")
    if not is_infinite_baffle and not is_pr:
        tab_labels.append("Atlas")
    design_tabs = dict(zip(tab_labels, st.tabs(tab_labels), strict=True))

    with design_tabs["Response"]:
        _render_response_tab(
            current_ts, load_type, box, result, thresholds, freq, sim_voltage, sim_series_r)
    with design_tabs["Excursion"]:
        st.subheader("Cone Excursion")
        xmax_mm = float(st.session_state.get("driver_xmax_mm", 0.0))
        st.altair_chart(
            _plot_excursion(result, xmax_mm),
            use_container_width=True,
            key=f"excursion_chart_{chart_sig}",
        )
        if xmax_mm > 0.0:
            st.caption(f"Dashed red line: driver Xmax = {xmax_mm:.1f} mm.")
        else:
            st.caption("Set the driver Xmax to draw the excursion limit line.")
    with design_tabs["Impedance"]:
        st.subheader("Electrical Impedance")
        st.altair_chart(_plot_impedance(result), use_container_width=True, key=f"impedance_chart_{chart_sig}")
    if "Ports" in design_tabs:
        with design_tabs["Ports"]:
            _render_ports_tab(
                result, port_geometry_rows, load_type,
                passive_radiator=is_pr,
            )
    with design_tabs["Group Delay"]:
        st.subheader("Group Delay")
        gd_limit_ms = (
            float(st.session_state.get("opt_max_gd_ms", 0.0))
            if _alignment_uses_optimizer() else 0.0
        )
        st.altair_chart(
            _plot_group_delay(result, gd_limit_ms),
            use_container_width=True,
            key=f"gd_chart_{chart_sig}",
        )
        if gd_limit_ms > 0.0:
            st.caption(f"Dashed red line: optimizer group-delay limit = {gd_limit_ms:.0f} ms.")
    if "Atlas" in design_tabs:
        with design_tabs["Atlas"]:
            _render_atlas_tab(current_ts, load_type, box, sim_voltage)

    active_load_image = _LOAD_TYPE_IMAGES.get(load_type)
    with st.container(key="active_load_summary"):
        # Left: active load schematic, Right: Dense info
        if active_load_image is not None and active_load_image.exists():
            img_col, data_col = st.columns([0.65, 5], vertical_alignment="center")
            with img_col:
                st.image(str(active_load_image), use_container_width=True)
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
                if row.get("Peak m/s", 0.0) > _dccav.PORT_VELOCITY_GUIDELINE_MS:
                    score_val -= 15
                if not row.get("_is_pr", False):
                    golden_cm = _dccav.port_displacement_min_diameter_cm(current_ts, row["_fb_hz"])
                    if 0.0 < row["Diameter cm"] < golden_cm:
                        score_val -= 10
                    if row["Length cm"] <= 0.0:
                        score_val -= 20
            if current_ts and current_ts.xmax_mm and metrics["max_excursion_mm"] > current_ts.xmax_mm:
                score_val -= 25
            score_val = max(10, min(100, score_val))

            flat_metrics = [
                ("F3", _fmt_hz(thresholds[3])),
                ("Peak LF SPL", _fmt_db(metrics["max_spl_db"])),
                ("Max exc.", f"{metrics['max_excursion_mm']:.2f} mm"),
                ("Min imp.", f"{metrics['min_impedance_ohm']:.2f} Ω"),
            ]
            if not is_infinite_baffle:
                if load_type == "Bandpass 4th order":
                    flat_metrics.append(("Box vol", f"{box.vs_l + box.vp_l:.1f} L"))
                elif load_type == "Bandpass 6th order":
                    flat_metrics.append(("Box vol", f"{box.vr_l + box.vp_l:.1f} L"))
                elif load_type == "DCCAV":
                    flat_metrics.append(("Box vol", f"{box.vh_l + box.vl_l:.1f} L"))
                else:
                    flat_metrics.append(("Box vol", f"{box.vb_l:.1f} L"))
            flat_metrics.append(("Forge Score", f"{score_val}/100"))

            if not is_infinite_baffle:
                ports = {row["Port"]: row for row in port_geometry_rows if not row.get("_is_pr", False)}
                
                def _add_port(lbl):
                    if lbl in ports:
                        pr = ports[lbl]
                        flat_metrics.extend([
                            (f"{lbl} fb", f"{pr['_fb_hz']:.1f} Hz"),
                            (f"{lbl} size", f"Ø{pr['Diameter cm']:.1f}x{pr['Length cm']:.1f}")
                        ])

                if load_type == "Bandpass 4th order":
                    flat_metrics.append(("Vs", f"{box.vs_l:.1f} L"))
                    flat_metrics.append(("Vp", f"{box.vp_l:.1f} L"))
                    _add_port("Front vent")
                elif load_type == "Bandpass 6th order":
                    flat_metrics.append(("Vr", f"{box.vr_l:.1f} L"))
                    _add_port("Rear vent")
                    flat_metrics.append(("Vp", f"{box.vp_l:.1f} L"))
                    _add_port("Front vent")
                elif load_type == "DCCAV":
                    flat_metrics.append(("Vh", f"{box.vh_l:.1f} L"))
                    _add_port("Upper port")
                    flat_metrics.append(("Vl", f"{box.vl_l:.1f} L"))
                    _add_port("Lower port")
                else:
                    _add_port("Vent")

            for i in range(0, len(flat_metrics), 4):
                cols = st.columns(4)
                for j, metric in enumerate(flat_metrics[i:i+4]):
                    cols[j].metric(metric[0], metric[1])

            # Gamification / Performance Badges
            badges = []
            if not is_infinite_baffle and not is_sealed:
                has_port_issues = any(
                    "chuffing" in w.lower() or "minimum-area" in w.lower() or "tunes at most" in w.lower()
                    for w in model_warnings
                )
                if len(port_geometry_rows) > 0 and not has_port_issues:
                    badges.append((
                        "🛡️ Safe from Chuffing",
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
                else:
                    vtot_l = box.vh_l + box.vl_l
                
                if f3_val < 30.0 and vtot_l < 35.0:
                    badges.append((
                        "🏆 Legendary Extension",
                        "rgba(0, 110, 219, 0.08)",
                        "rgba(0, 110, 219, 0.3)",
                        "#006edb"
                    ))
                elif f3_val < 40.0 and vtot_l < 50.0:
                    badges.append((
                        "🔊 Deep Bass Accord",
                        "rgba(0, 110, 219, 0.08)",
                        "rgba(0, 110, 219, 0.3)",
                        "#006edb"
                    ))
                elif f3_val < 50.0:
                    badges.append((
                        "🎵 Tight Bass",
                        "rgba(0, 110, 219, 0.08)",
                        "rgba(0, 110, 219, 0.3)",
                        "#006edb"
                    ))

            if not any("sanity" in w.lower() or "warning" in w.lower() for w in model_warnings):
                badges.append((
                    "✅ Acoustically Sane",
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
                st.markdown(
                    "".join(f'<div style="background: rgba(255, 170, 0, 0.1); border-left: 3px solid #ffaa00; padding: 0.3rem 0.6rem; font-size: 0.8rem; margin-top: 0.3rem; color: #ffbc3d;">• {w}</div>' for w in model_warnings),
                    unsafe_allow_html=True
                )

    # Warnings are now rendered inside data_col compactly

    exp_c1, exp_c2 = st.columns(2)
    with exp_c1:
        with st.expander("Design details"):
            s1, s2, s3 = st.columns(3)
            s1.metric("F6", _fmt_hz(thresholds[6]))
            s2.metric("F10", _fmt_hz(thresholds[10]))
            s3.metric("Z peaks", ", ".join(f"{f:.0f}" for f in z_peak_freqs[:3]) or "n/a")
            if is_reflex:
                a1, a2, a3, a4 = st.columns(4)
                a1.metric("Vb (active)", f"{box.vb_l:.2f} L")
                a2.metric("Fb (active)", f"{box.fb_hz:.1f} Hz")
                a3.metric("Eq sealed Fc", f"{_dccav.equivalent_sealed_fc_hz(current_ts, box):.1f} Hz")
                if current_reflex_alignment is not None:
                    a4.metric("Starter Vb=Vas", f"{current_reflex_alignment.vb_l:.2f} L")
            elif is_pr:
                a1, a2, a3, a4 = st.columns(4)
                a1.metric("Vb (active)", f"{box.vb_l:.2f} L")
                a2.metric("PR Fp", f"{box.pr_fp_hz:.1f} Hz")
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
                a6.metric("Eq sealed Fc", f"{_dccav.equivalent_sealed_fc_hz(current_ts, box):.1f} Hz")
                if current_bandpass6_alignment is not None:
                    a7.metric(
                        "Starter Vtot",
                        f"{current_bandpass6_alignment.vr_l + current_bandpass6_alignment.vp_l:.2f} L",
                    )
            elif is_sealed:
                fc_hz, qtc = _dccav.sealed_system_metrics(current_ts, box)
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
                    f"{_dccav.panel_loaded_fs_hz(current_ts):.1f} Hz",
                    help=f"Free-air Fs: {current_ts.fs_hz:.1f} Hz",
                )
                a2.metric("Infinite baffle Qts", f"{current_ts.qts:.3f}")
                a3.metric("Rear radiation", "Isolated")
            else:
                a1, a2, a3, a4, a5, a6, a7 = st.columns(7)
                a1.metric("Vh (active)", f"{box.vh_l:.2f} L")
                a2.metric("fh (active)", f"{box.fh_hz:.1f} Hz")
                a3.metric("Vl (active)", f"{box.vl_l:.2f} L")
                a4.metric("fl (active)", f"{box.fl_hz:.1f} Hz")
                a5.metric("Vtot (active)", f"{box.vh_l + box.vl_l:.2f} L")
                a6.metric("Eq sealed Fc", f"{_dccav.equivalent_sealed_fc_hz(current_ts, box):.1f} Hz")
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

                ref = _dccav.driver_reference_metrics(current_ts)
                bandwidth = _dccav.classify_driver_bandwidth(current_ts)
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
                e6.metric("Class", bandwidth.driver_class)
                if ref.ebp_hz < 50.0:
                    ebp_hint = "EBP < 50: this driver classically favours sealed or infinite-baffle loads."
                elif ref.ebp_hz > 100.0:
                    ebp_hint = "EBP > 100: this driver classically favours ported loads (bass reflex / DCCAV)."
                else:
                    ebp_hint = "EBP 50-100: this driver works in both sealed and ported loads."
                st.caption(f"{ebp_hint} Class indicators: {', '.join(bandwidth.reasons)}.")

    dl_cols = st.columns(4) if load_type == "DCCAV" else st.columns(3)
    dl_csv, dl_frd, dl_zma = dl_cols[:3]
    with dl_csv:
        st.download_button(
            "Download response CSV",
            _csv_bytes(result),
            "load_forge_response.csv",
            "text/csv",
            use_container_width=True,
        )
    with dl_frd:
        st.download_button(
            "Download FRD (response)",
            _dccav.export_frd_text(result),
            "load_forge_response.frd",
            "text/plain",
            use_container_width=True,
            help="Total response as freq/SPL/phase text for VituixCAD, XSim or REW.",
        )
    with dl_zma:
        st.download_button(
            "Download ZMA (impedance)",
            _dccav.export_zma_text(result),
            "load_forge_impedance.zma",
            "text/plain",
            use_container_width=True,
            help="Electrical impedance as freq/ohm/phase text for VituixCAD, XSim or REW.",
        )
    if load_type == "DCCAV":
        with dl_cols[3]:
            try:
                afw_text = _afw_export.generate_afw_text(_collect_params())
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
                use_container_width=True,
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
    logger.exception("Simulation failed")
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
    logger.exception("Simulation failed")
    st.error(f"Simulation failed: {exc}")
