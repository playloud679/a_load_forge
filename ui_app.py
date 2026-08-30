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
    _engine, _port_cad, _pricing, _presets, _ranking, _saas,
    _afw_export, _afw_compare,
):
    _reload_if_source_changed(_module)
# The facade is intentionally cheap to reload and must always rebind wildcard
# exports after any dependency may have hot-reloaded on a prior UI rerun.
importlib.reload(_acoustics)
_acoustics._load_forge_reload_mtime = Path(_acoustics.__file__).stat().st_mtime


try:
    _VERSION = (Path(__file__).parent / "VERSION").read_text().strip()
except OSError:
    _VERSION = "dev"
_BRAND_IMAGE = Path(__file__).parent / "assets" / "load_forge_header.png"
_BRAND_APP_IMAGE = Path(__file__).parent / "assets" / "load_forge_header_app.png"
_CATALOG_CRAWL_REPORT = (
    Path(__file__).parent / "data" / "autonomous_crawler_latest_report.json"
)
_CATALOG_CRAWL_PROGRESS = (
    Path(__file__).parent / "data" / "autonomous_crawler_progress.json"
)
_RETAILER_CRAWL_REPORT = (
    Path(__file__).parent / "data" / "retailer_discovery_latest_report.json"
)
_CATALOG_ADDITIONS_REPORT = (
    Path(__file__).parent / "data" / "catalog_additions_latest_report.json"
)
_LOAD_IMAGE_DIR = Path(__file__).parent / "assets" / "load_types"
_WORKSPACE_TAB_IMAGES = {
    "Bass Match": Path(__file__).parent / "assets" / "bass_match_tab.png",
    "Box Design": Path(__file__).parent / "assets" / "box_design_tab.png",
}


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


def _focused_port_flare_style(state: Any = None) -> str:
    """Resolve the flare style for the duct currently targeted in Ports."""
    values = st.session_state if state is None else state
    global_style = _clean_style_str(values.get("flared_calc_style", "both"), "both")
    target = _clean_style_str(
        values.get(
            "flared_active_target_duct",
            values.get("flared_target_duct", "All Ducts (Global)"),
        ),
        "All Ducts (Global)",
    )
    if target.startswith("All"):
        return global_style
    return _clean_style_str(
        values.get(f"flared_style_{target}", global_style), global_style
    )


_STL_SPLIT_LABELS = {
    "full": "Single piece (Full port)",
    "half": "2-piece symmetric halves (L/2 for 3D print)",
    "flange_only": "Outer Flange Coupling Only",
}


def _normalize_stl_split_mode(value: Any, default: str = "full") -> str:
    """Return the canonical STL split slug, including legacy label values."""
    cleaned = _clean_style_str(value, default)
    if cleaned in _STL_SPLIT_LABELS:
        return cleaned
    legacy_to_slug = {label: slug for slug, label in _STL_SPLIT_LABELS.items()}
    return legacy_to_slug.get(cleaned, default)


def _read_json_object(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _render_catalog_crawl_report() -> None:
    """Show staging progress/report without coupling the app to the daemon."""
    report = _read_json_object(_CATALOG_CRAWL_REPORT)
    progress = _read_json_object(_CATALOG_CRAWL_PROGRESS)
    retailer_report = _read_json_object(_RETAILER_CRAWL_REPORT)
    additions_report = _read_json_object(_CATALOG_ADDITIONS_REPORT)
    if not report and not progress and not retailer_report and not additions_report:
        return
    phase = str(progress.get("phase") or "").replace("_", " ")
    active = phase not in {"", "complete", "sleeping", "failed"}
    if not active:
        return
    label = f"Catalog crawl · {phase}"
    with st.expander(label, expanded=True):
        if progress:
            st.caption(
                f"Status: {phase or 'unknown'} · updated "
                f"{str(progress.get('updated_at') or 'n/a')[:19]}"
            )
            if active:
                progress_bits = []
                for key, title in (
                    ("brands", "brands"),
                    ("covered", "covered"),
                    ("unresolved", "unresolved"),
                    ("verified", "verified"),
                    ("targets_complete", "targets complete"),
                    ("targets_total", "targets total"),
                ):
                    if key in progress:
                        progress_bits.append(f"{title}: {progress[key]}")
                if progress_bits:
                    st.write(" · ".join(progress_bits))
        summary = report.get("registry_summary") or {}
        if summary:
            c1, c2 = st.columns(2)
            c1.metric(
                "Official coverage",
                f"{int(summary.get('covered_brand_labels', 0)):,} / "
                f"{int(summary.get('catalog_brands', 0)):,}",
            )
            c2.metric(
                "Official targets",
                f"{int(summary.get('ready_official_targets', 0)):,}",
            )
            st.caption(
                f"Aliases {int(summary.get('brand_aliases', 0)):,} · "
                f"needs discovery {int(summary.get('needs_discovery', 0)):,} · "
                f"brand cleanup {int(summary.get('needs_brand_cleanup', 0)):,}"
            )
        if report:
            state = str(report.get("publication_state") or "unknown")
            unchanged = bool(report.get("catalog_unchanged"))
            st.caption(
                f"Publication: {state}. Existing catalog "
                f"{'unchanged' if unchanged else 'changed unexpectedly'}."
            )
        if additions_report:
            st.divider()
            st.markdown("**Reviewed catalog additions**")
            added = int(additions_report.get("added", 0))
            latest_batch = int(additions_report.get("latest_batch_added", added))
            latest_visible = int(
                additions_report.get("latest_batch_visible_added", latest_batch)
            )
            final_records = int(additions_report.get("final_records", 0))
            app_visible = int(additions_report.get("app_visible_records", 0))
            latest_label = f"+{latest_batch:,} latest batch"
            if latest_visible != latest_batch:
                latest_label += f" / +{latest_visible:,} app-visible"
            st.caption(
                f"{added:,} new validated drivers published append-only "
                f"({latest_label}) · "
                f"catalog {final_records:,} · app-visible {app_visible:,}."
            )
            latest_by_brand = additions_report.get("latest_batch_by_brand") or {}
            if isinstance(latest_by_brand, dict) and latest_by_brand:
                st.caption(
                    "Latest batch: "
                    + " · ".join(
                        f"{brand} {int(count):,}"
                        for brand, count in latest_by_brand.items()
                    )
                )
            latest_visible_by_brand = (
                additions_report.get("latest_batch_visible_by_brand") or {}
            )
            if (
                isinstance(latest_visible_by_brand, dict)
                and latest_visible_by_brand
                and latest_visible_by_brand != latest_by_brand
            ):
                st.caption(
                    "Net app-visible: "
                    + " · ".join(
                        f"{brand} {int(count):,}"
                        for brand, count in latest_visible_by_brand.items()
                    )
                )
            added_names = [
                str(name)
                for name in additions_report.get(
                    "added_names_sample",
                    additions_report.get("added_names", []),
                )
                if str(name).strip()
            ]
            if added_names:
                names_count = int(
                    additions_report.get("added_names_count", len(added_names))
                )
                suffix = (
                    f" · … {names_count - len(added_names):,} more"
                    if names_count > len(added_names)
                    else ""
                )
                st.caption("Sample: " + " · ".join(added_names) + suffix)
        retailer_summary = retailer_report.get("summary") or {}
        if retailer_summary:
            st.divider()
            st.markdown(f"**Retail gaps · {retailer_report.get('source', 'source')}**")
            st.caption(
                f"{int(retailer_summary.get('observations', 0)):,} products · "
                f"{int(retailer_summary.get('exact_catalog_matches', 0)):,} exact matches · "
                f"{int(retailer_summary.get('potential_catalog_gaps', 0)):,} potential gaps · "
                f"{int(retailer_summary.get('pages_failed', 0)):,} failed pages"
            )


st.set_page_config(
    page_title=f"Load Forge v{_VERSION}",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={},
)

st.markdown(
    """
    <style>
    :root {
        --lf-bg-base: #000000;
        --lf-bg-surface: #0a0f16;
        --lf-bg-elevated: #111823;
        --lf-bg-card: rgba(255, 255, 255, 0.025);
        --lf-bg-hover: rgba(255, 255, 255, 0.05);
        --lf-accent: #10b981;
        --lf-accent-dim: rgba(16, 185, 129, 0.15);
        --lf-accent-border: rgba(16, 185, 129, 0.35);
        --lf-border-subtle: 1px solid rgba(255, 255, 255, 0.08);
        --lf-border-medium: 1px solid rgba(255, 255, 255, 0.14);
        --lf-text-main: #f3f4f6;
        --lf-text-muted: rgba(255, 255, 255, 0.55);
        --lf-text-dim: rgba(255, 255, 255, 0.38);
        --primary-color: #10b981 !important;
    }
    /* Distinct dark charcoal contrast for form & data entry controls */
    div[data-baseweb="input"],
    div[data-baseweb="select"] > div,
    div[data-baseweb="base-input"],
    .stNumberInput input,
    .stTextInput input,
    .stSelectbox div[data-baseweb="select"],
    [data-testid="stNumberInput"] div[data-baseweb="input"],
    [data-testid="stTextInput"] div[data-baseweb="input"] {
        background-color: #151a22 !important;
        border: 1px solid rgba(255, 255, 255, 0.18) !important;
        border-radius: 6px !important;
        color: #f3f4f6 !important;
    }
    div[data-baseweb="input"]:focus-within,
    div[data-baseweb="select"]:focus-within {
        border-color: #10b981 !important;
        box-shadow: 0 0 0 1px #10b981 !important;
    }
    header[data-testid="stHeader"] {
        display: none !important;
    }
    [data-stale="true"] {
        filter: none !important;
        opacity: 1 !important;
    }
    section[data-testid="stSidebar"],
    section[data-testid="stSidebar"] > div,
    section[data-testid="stSidebar"] [data-testid="stSidebarContent"],
    section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
        background: #000 !important;
    }
    html {
        scrollbar-gutter: stable;
    }
    body,
    [data-testid="stAppViewContainer"],
    section[data-testid="stMain"] {
        scrollbar-gutter: stable;
        background-color: var(--lf-bg-base) !important;
    }
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
    [data-testid="stMainBlockContainer"],
    [data-testid="stAppViewContainer"] {
        padding-top: 0.2rem !important;
        padding-bottom: 0.2rem !important;
        padding-left: 1.0rem !important;
        padding-right: 1.0rem !important;
    }
    section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
        padding-top: 0 !important;
    }
    section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
        padding-top: 0 !important;
        margin-top: -3.8rem !important;
    }
    .st-key-brand_logo {
        background: #000;
    }
    .st-key-brand_logo img {
        filter: hue-rotate(150deg) saturate(2.4) contrast(1.55) brightness(1.04);
    }
    /* Instruction bands: neutral by default, emerald for actionable selection hints. */
    [data-testid="stAlertContainer"]:has([data-testid="stAlertContentInfo"]) {
        background-color: rgba(107,114,128,.16) !important;
        border: 1px solid rgba(156,163,175,.34) !important;
        color: #e5e7eb !important;
        border-radius: 6px !important;
    }
    [data-testid="stAlertContainer"] [data-testid="stAlertContentInfo"] {
        color: inherit !important;
    }
    [class*="st-key-emerald_info_"] [data-testid="stAlertContainer"] {
        background-color: rgba(16,185,129,.13) !important;
        border: 1px solid rgba(16,185,129,.34) !important;
        color: #d1fae5 !important;
        border-radius: 6px !important;
    }
    [class*="st-key-emerald_info_"] [data-testid="stAlertContainer"] svg {
        color: #10b981 !important;
        fill: #10b981 !important;
    }
    section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h3 {
        border-top: 1px solid rgba(255,255,255,.08);
        color: rgba(255,255,255,.92);
        font-size: 0.95rem;
        font-weight: 600;
        line-height: 1.25;
        margin: .35rem 0 .2rem !important;
        padding-top: .5rem !important;
    }
    [data-testid="stExpander"] details {
        border: 1px solid rgba(255,255,255,.08) !important;
        border-radius: 6px !important;
        background: rgba(255,255,255,0.015) !important;
    }
    [data-testid="stExpander"] summary {
        font-weight: 500 !important;
        font-size: 0.85rem !important;
    }
    [data-testid="stMainBlockContainer"] [data-testid="stMarkdownContainer"] h1,
    [data-testid="stMainBlockContainer"] [data-testid="stMarkdownContainer"] h2,
    [data-testid="stMainBlockContainer"] [data-testid="stMarkdownContainer"] h3,
    [data-testid="stMainBlockContainer"] [data-testid="stMarkdownContainer"] h4 {
        padding-top: 0.35rem !important;
        padding-bottom: 0.2rem !important;
        font-weight: 600 !important;
        letter-spacing: -0.01em !important;
    }
    [data-testid="stMainBlockContainer"] [data-testid="stWidgetLabel"] {
        padding-bottom: 0.1rem !important;
        margin-top: 0.55rem !important;
    }
    [data-testid="stMainBlockContainer"] [data-testid="stWidgetLabel"] p {
        margin-bottom: 0 !important;
        font-weight: 500 !important;
        font-size: 0.85rem !important;
    }
    section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
    section[data-testid="stSidebar"] label p {
        font-size: 0.82rem !important;
        font-weight: 500 !important;
        color: rgba(255,255,255,0.85) !important;
        line-height: 1.3 !important;
        margin-bottom: 0.05rem !important;
    }
    section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {
        line-height: 1.45 !important;
        font-size: 0.75rem !important;
        color: rgba(255,255,255,0.48) !important;
    }
    section[data-testid="stSidebar"] [data-testid="stNumberInput"]
    div[data-baseweb="input"] {
        border-radius: .4rem;
        min-height: 2.35rem;
        overflow: hidden;
        border: 1px solid rgba(255, 255, 255, 0.20) !important;
        background-color: #141b27 !important;
    }
    section[data-testid="stSidebar"] [data-testid="stNumberInput"] button,
    [data-testid="stNumberInput"] button {
        align-items: center !important;
        align-self: stretch !important;
        background: #1e2638 !important;
        border-left: 1px solid rgba(255,255,255,.16) !important;
        border-radius: 0 !important;
        color: #e2e8f0 !important;
        display: flex !important;
        height: auto !important;
        justify-content: center !important;
        margin: 0 !important;
        min-width: 2.2rem !important;
        padding: 0 !important;
        transition: background-color .15s ease, color .15s ease;
    }
    section[data-testid="stSidebar"] [data-testid="stNumberInput"] button:hover:not(:disabled),
    [data-testid="stNumberInput"] button:hover:not(:disabled) {
        background: rgba(16,185,129,.25) !important;
        color: #10b981 !important;
    }
    section[data-testid="stSidebar"] [data-testid="stNumberInput"] button svg,
    [data-testid="stNumberInput"] button svg {
        height: 1.0rem !important;
        width: 1.0rem !important;
    }
    hr {
        margin-top: 0.4rem !important;
        margin-bottom: 0.4rem !important;
        border-color: rgba(255,255,255,0.12) !important;
    }

    header[data-testid="stHeader"] {
        background-color: transparent !important;
    }

    [data-testid="stCaptionContainer"] {
        color: rgba(250,250,250,.65);
    }
    /* Keep widget help available without letting long tooltips cover the UI. */
    [data-testid="stTooltipContent"],
    [role="tooltip"] {
        max-width: min(28rem, calc(100vw - 2rem)) !important;
        white-space: normal !important;
        z-index: 1000000 !important;
    }
    .st-key-finder_library_filters {
        background: #0f1520;
        border: 1px solid rgba(255,255,255,.16) !important;
        border-radius: 6px !important;
        margin-block: .25rem .55rem;
    }
    .st-key-finder_library_filters [data-testid="stVerticalBlock"] {
        gap: .55rem !important;
    }

    .st-key-active_load_summary {
        border: 1px solid rgba(255,255,255,.16) !important;
        border-radius: 6px !important;
        background: #0f1520 !important;
        padding: .45rem .6rem .45rem !important;
    }
    .st-key-finder_run_search_main div[data-testid="stButton"] button {
        background: #10b981;
        border: 1px solid #10b981;
        box-shadow: 0 .25rem 0.85rem rgba(16,185,129,.22);
        min-height: 2.8rem;
        border-radius: 6px;
        transition: filter .16s ease, transform .16s ease, box-shadow .16s ease;
    }
    .st-key-finder_run_search_main div[data-testid="stButton"] button p {
        font-size: clamp(1.02rem, 1.25vw, 1.15rem);
        font-weight: 700;
        letter-spacing: .01em;
    }
    .st-key-finder_run_search_main div[data-testid="stButton"] button:hover {
        box-shadow: 0 .4rem 1.1rem rgba(16,185,129,.32);
        filter: brightness(1.08);
        transform: translateY(-1px);
    }
    .st-key-bass_match_brief {
        padding: .45rem .65rem 1.0rem !important;
        border-radius: 8px !important;
        border: 1px solid rgba(255,255,255,0.16) !important;
        background: #0f1520 !important;
    }
    .st-key-bass_match_brief > div[data-testid="stVerticalBlock"] {
        gap: .28rem !important;
    }
    .st-key-bass_match_brief h4 {
        font-size: 0.95rem !important;
        line-height: 1.15 !important;
        margin: 0 !important;
        padding: 0 !important;
    }
    .st-key-bass_match_brief .stMetric {
        min-height: 3.1rem !important;
        padding: .22rem .42rem !important;
    }
    .st-key-bass_match_brief [data-testid="stCaptionContainer"] {
        margin: 0 !important;
    }
    .finder-constraint-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(9.75rem, 1fr));
        gap: .4rem;
        margin-top: .08rem;
    }
    .finder-constraint {
        min-width: 0;
        border: 1px solid rgba(255,255,255,.16);
        border-radius: 6px;
        padding: .4rem .55rem;
        background: #141b27;
    }
    .finder-constraint-label {
        color: #94a3b8;
        font-size: .70rem;
        font-weight: 600;
        letter-spacing: .04em;
        line-height: 1;
        text-transform: uppercase;
    }
    .finder-constraint-value {
        color: #ffffff;
        font-size: .92rem;
        font-weight: 700;
        line-height: 1.2;
        margin-top: .2rem;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }
    .st-key-finder_match_progress [role="progressbar"],
    .st-key-finder_match_progress [data-testid="stProgressBar"] > div {
        border-radius: 4px !important;
        height: .8rem !important;
        min-height: .8rem !important;
    }
    .st-key-finder_match_progress [role="progressbar"] > div {
        border-radius: inherit !important;
        height: 100% !important;
    }
    .st-key-finder_match_progress > div[data-testid="stVerticalBlock"] {
        gap: .12rem !important;
    }
    .st-key-finder_match_progress [data-testid="stCaptionContainer"] {
        color: rgba(255,255,255,.85) !important;
        font-size: .75rem !important;
        font-weight: 600 !important;
        margin: 0 !important;
    }
    .stMetric {
        border: 1px solid rgba(255,255,255,.16) !important;
        border-radius: 6px !important;
        background: #141b27 !important;
        padding: .35rem .55rem !important;
    }
    .stMetric label {
        font-size: 0.70rem !important;
        font-weight: 600 !important;
        color: #94a3b8 !important;
        margin-bottom: -0.2rem !important;
        text-transform: uppercase;
        letter-spacing: 0.03em;
    }
    .stMetric div[data-testid="stMetricValue"] {
        font-size: 1.05rem !important;
        font-weight: 700 !important;
        color: #f8fafc !important;
        line-height: 1.2 !important;
        padding-bottom: 0.1rem !important;
    }

    [data-testid="stVerticalBlockBorderWrapper"] {
        border: 1px solid rgba(255, 255, 255, 0.16) !important;
        background-color: #0d131d !important;
        border-radius: 8px !important;
    }

    /* Tabs emerald indicator & text */
    div[data-testid="stTabs"] { gap: 0 !important; }
    button[data-baseweb="tab"] {
        padding-top: 0.3rem !important;
        padding-bottom: 0.3rem !important;
        font-weight: 500 !important;
        font-size: 0.85rem !important;
        color: rgba(255, 255, 255, 0.7) !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: #10b981 !important;
        border-bottom-color: #10b981 !important;
        font-weight: 600 !important;
    }
    div[data-testid="stTabs"] div[data-baseweb="tab-highlight"],
    div[data-testid="stTabs"] div[data-baseweb="tab-border"] {
        background-color: #10b981 !important;
    }

    /* Radio buttons emerald styling (e.g. Rank by) */
    div[data-testid="stRadio"] [aria-checked="true"] > div,
    div[data-testid="stRadio"] label:has(input:checked) span,
    div[data-testid="stRadio"] div[data-baseweb="radio"]:has(input:checked) div:first-child {
        border-color: #10b981 !important;
        background-color: #10b981 !important;
    }
    div[data-testid="stRadio"] div[data-baseweb="radio"]:has(input:checked) div:first-child > div {
        background-color: #ffffff !important;
    }

    /* Multi-select and selectbox emerald theme */
    div[data-baseweb="tag"],
    span[data-baseweb="tag"],
    [data-testid="stMultiSelect"] span[data-baseweb="tag"],
    [data-testid="stMultiSelect"] div[data-baseweb="tag"],
    span[data-testid="stBaseButton-secondary"]:has(svg) {
        background-color: rgba(16, 185, 129, 0.22) !important;
        border: 1px solid rgba(16, 185, 129, 0.55) !important;
        border-radius: 4px !important;
        color: #10b981 !important;
    }
    div[data-baseweb="tag"] span,
    span[data-baseweb="tag"] span,
    [data-testid="stMultiSelect"] span[data-baseweb="tag"] span {
        color: #d1fae5 !important;
        font-weight: 600 !important;
    }
    div[data-baseweb="tag"] svg,
    span[data-baseweb="tag"] svg,
    [data-testid="stMultiSelect"] span[data-baseweb="tag"] svg {
        fill: #10b981 !important;
        color: #10b981 !important;
    }

    /* High-contrast Selectbox, Inputs & Dropdowns */
    div[data-baseweb="select"] > div {
        border: 1px solid rgba(255, 255, 255, 0.20) !important;
        background-color: #141b27 !important;
        border-radius: 6px !important;
        min-height: 2.4rem !important;
    }
    div[data-baseweb="select"] > div:hover {
        border-color: rgba(16, 185, 129, 0.65) !important;
    }
    div[data-baseweb="select"] > div:focus-within {
        border-color: #10b981 !important;
        box-shadow: 0 0 0 1px #10b981 !important;
    }
    div[data-baseweb="select"] span,
    div[data-baseweb="select"] div {
        color: #f8fafc !important;
        font-weight: 500 !important;
    }
    div[data-baseweb="select"] svg {
        fill: #94a3b8 !important;
    }
    div[data-baseweb="popover"],
    ul[data-baseweb="menu"],
    div[data-baseweb="menu"] {
        background-color: #141b27 !important;
        border: 1px solid rgba(255, 255, 255, 0.20) !important;
        border-radius: 6px !important;
        box-shadow: 0 8px 24px rgba(0,0,0,0.6) !important;
    }
    li[data-baseweb="menu-item"] {
        color: #f1f5f9 !important;
        font-weight: 500 !important;
    }
    li[data-baseweb="menu-item"]:hover,
    li[data-baseweb="menu-item"][aria-selected="true"] {
        background-color: rgba(16, 185, 129, 0.22) !important;
        color: #10b981 !important;
    }

    /* High-contrast Text & Number Inputs */
    div[data-baseweb="input"] {
        border: 1px solid rgba(255, 255, 255, 0.20) !important;
        background-color: #141b27 !important;
        border-radius: 6px !important;
        min-height: 2.4rem !important;
    }
    div[data-baseweb="input"]:hover {
        border-color: rgba(16, 185, 129, 0.65) !important;
    }
    div[data-baseweb="input"]:focus-within {
        border-color: #10b981 !important;
        box-shadow: 0 0 0 1px #10b981 !important;
    }
    div[data-baseweb="input"] input {
        color: #f8fafc !important;
        font-weight: 500 !important;
        background-color: transparent !important;
    }

    /* Quota pill badge */
    .lf-quota-pill {
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        background: rgba(255,255,255,0.03);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 4px;
        padding: 0.25rem 0.55rem;
        font-size: 0.75rem;
        color: rgba(255,255,255,0.65);
    }
    .lf-quota-pill strong {
        color: #10b981;
        font-weight: 600;
    }

    /* Data editor and table sparkline / chart stroke color override */
    [data-testid="stDataFrame"] svg path,
    [data-testid="stDataEditor"] svg path,
    div[data-testid="stTable"] svg path,
    svg.sparkline path,
    div[data-testid="stElementContainer"] svg path[stroke="#ff4b4b"],
    div[data-testid="stElementContainer"] svg path[stroke="red"] {
        stroke: #10b981 !important;
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

try:
    _SAAS_SETTINGS = _saas.SaaSSettings.from_env()
except _saas.SaaSConfigurationError as _saas_config_error:
    st.error(f"Unsafe SaaS configuration: {_saas_config_error}")
    st.stop()

_LOCAL_ACCOUNT_SESSION_KEY = "_local_saas_account"


def _remember_local_account(user: _saas.SaaSUser) -> None:
    st.session_state[_LOCAL_ACCOUNT_SESSION_KEY] = {
        "sub": user.uid,
        "email": user.email,
        "name": user.name,
        "tenant_id": user.tenant_id,
        "plan": user.plan,
    }


def _render_auth_hero_and_badges(title: str, subtitle: str) -> None:
    st.markdown(
        """
        <style>
        div[data-testid="stForm"] {
            background: rgba(18, 24, 38, 0.85) !important;
            border: 1px solid rgba(255, 255, 255, 0.12) !important;
            border-radius: 14px !important;
            padding: 1.6rem 1.8rem !important;
            box-shadow: 0 16px 40px rgba(0, 0, 0, 0.45) !important;
            backdrop-filter: blur(16px) !important;
        }
        div[data-testid="stForm"] input {
            background-color: rgba(10, 14, 23, 0.85) !important;
            border: 1px solid rgba(255, 255, 255, 0.14) !important;
            color: #f3f4f6 !important;
            border-radius: 8px !important;
        }
        div[data-testid="stForm"] input:focus {
            border-color: #10b981 !important;
            box-shadow: 0 0 0 2px rgba(16, 185, 129, 0.25) !important;
        }
        div[data-testid="stRadio"] > div {
            justify-content: center;
            background: rgba(255, 255, 255, 0.05);
            padding: 0.25rem 0.5rem;
            border-radius: 8px;
            border: 1px solid rgba(255, 255, 255, 0.08);
            margin-bottom: 0.5rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    brand_path = _BRAND_APP_IMAGE if _BRAND_APP_IMAGE.exists() else _BRAND_IMAGE
    if brand_path.exists():
        st.image(str(brand_path), width="stretch")
    else:
        st.title("Load Forge")
    st.markdown(
        f"""
        <div style="text-align: center; margin-top: 0.6rem; margin-bottom: 1.3rem;">
            <h2 style="font-size: 1.35rem; font-weight: 600; color: #f9fafb; margin: 0 0 0.35rem 0; letter-spacing: -0.01em;">{title}</h2>
            <p style="font-size: 0.875rem; color: rgba(255, 255, 255, 0.55); margin: 0; line-height: 1.45;">{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_local_account_gate(*, render_hero: bool = True) -> None:
    """Render the local registration/login form."""
    if render_hero:
        _, col_center, _ = st.columns([1, 3.2, 1])
        container = col_center
    else:
        import contextlib
        container = contextlib.nullcontext()
    with container:
        if render_hero:
            _render_auth_hero_and_badges(
                title="Sign in to Load Forge",
                subtitle="Sign in or create an account to save and manage your box designs.",
            )
        account_mode = st.radio(
            "Account",
            ("Sign in", "Create account"),
            horizontal=True,
            label_visibility="collapsed",
            key="_local_account_mode",
        )
        accounts = _saas.LocalAccountStore(_SAAS_SETTINGS.local_account_database)
        if account_mode == "Sign in":
            with st.form("local_saas_sign_in"):
                email = st.text_input(
                    "Email",
                    placeholder="name@example.com",
                    autocomplete="email",
                    key="_local_sign_in_email",
                )
                password = st.text_input(
                    "Password",
                    placeholder="••••••••••••",
                    type="password",
                    autocomplete="current-password",
                    key="_local_sign_in_password",
                )
                submitted = st.form_submit_button(
                    "Sign in",
                    type="primary",
                    width="stretch",
                )
            if submitted:
                try:
                    user = accounts.authenticate(email, password)
                except _saas.InvalidCredentialsError as exc:
                    st.error(str(exc))
                else:
                    _remember_local_account(user)
                    st.rerun()
        else:
            with st.form("local_saas_registration"):
                name = st.text_input(
                    "Name",
                    placeholder="Your Name",
                    autocomplete="name",
                    key="_local_register_name",
                )
                email = st.text_input(
                    "Email",
                    placeholder="name@example.com",
                    autocomplete="email",
                    key="_local_register_email",
                )
                password = st.text_input(
                    "Password",
                    placeholder="At least 10 characters",
                    type="password",
                    autocomplete="new-password",
                    help="Use at least 10 characters.",
                    key="_local_register_password",
                )
                confirmation = st.text_input(
                    "Confirm password",
                    placeholder="Repeat password",
                    type="password",
                    autocomplete="new-password",
                    key="_local_register_confirmation",
                )
                submitted = st.form_submit_button(
                    "Create account",
                    type="primary",
                    width="stretch",
                )
            if submitted:
                if password != confirmation:
                    st.error("Passwords do not match")
                else:
                    try:
                        user = accounts.create_account(name, email, password)
                    except (ValueError, _saas.AccountExistsError) as exc:
                        st.error(str(exc))
                    else:
                        _remember_local_account(user)
                        st.rerun()
        st.markdown(
            """
            <div style="text-align: center; margin-top: 1rem; padding-top: 0.75rem; border-top: 1px solid rgba(255,255,255,0.08); font-size: 0.75rem; color: rgba(255,255,255,0.40); line-height: 1.4;">
                Local storage · Encrypted credentials (PBKDF2) · Autosaved projects
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.stop()


def _sign_out_saas() -> None:
    if _SAAS_SETTINGS.local_accounts:
        st.session_state.pop(_LOCAL_ACCOUNT_SESSION_KEY, None)
        st.session_state.pop("_saas_projects_identity", None)
        st.session_state.pop("_saas_project_summaries", None)
        st.rerun()
    st.logout()
    st.stop()


def _resolve_saas_user() -> _saas.SaaSUser | None:
    """Resolve the authenticated user when either auth or SaaS is enabled."""
    # Finder workers re-import this module under multiprocessing spawn/forkserver
    # without a Streamlit request context. They only execute pure ranking helpers
    # and must never enter an account flow or touch project persistence.
    if multiprocessing.current_process().name != "MainProcess":
        return None
    if not _SAAS_SETTINGS.auth_required:
        return None
    if _SAAS_SETTINGS.auth_bypass:
        claims = _SAAS_SETTINGS.development_claims()
    elif _SAAS_SETTINGS.local_accounts:
        claims = st.session_state.get(_LOCAL_ACCOUNT_SESSION_KEY)
        if not isinstance(claims, dict):
            _render_local_account_gate()
    else:
        claims = st.session_state.get(_LOCAL_ACCOUNT_SESSION_KEY)
        if not isinstance(claims, dict):
            try:
                logged_in = bool(st.user.is_logged_in)
            except (AttributeError, RuntimeError):
                logged_in = False
            if not logged_in:
                _, col_center, _ = st.columns([1, 3.2, 1])
                with col_center:
                    _render_auth_hero_and_badges(
                        title="Sign in to Load Forge",
                        subtitle="Sign in to save and manage your box designs, simulations, and driver catalog.",
                    )
                    try:
                        auth_configured = "auth" in st.secrets
                    except (FileNotFoundError, RuntimeError):
                        auth_configured = False
                    if auth_configured:
                        if st.button("Sign in with Google", type="primary", width="stretch"):
                            if _SAAS_SETTINGS.oidc_provider:
                                st.login(_SAAS_SETTINGS.oidc_provider)
                            else:
                                st.login()
                        st.markdown(
                            """
                            <div style="display: flex; align-items: center; text-align: center; margin: 1.2rem 0; color: rgba(255,255,255,0.35); font-size: 0.8rem;">
                                <div style="flex: 1; border-bottom: 1px solid rgba(255,255,255,0.12);"></div>
                                <span style="padding: 0 0.8rem; text-transform: uppercase; font-size: 0.72rem; letter-spacing: 0.05em;">oppure</span>
                                <div style="flex: 1; border-bottom: 1px solid rgba(255,255,255,0.12);"></div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                    _render_local_account_gate(render_hero=False)
                    st.stop()
            claims = st.user.to_dict()

    expires_at = claims.get("exp")
    if expires_at is not None:
        try:
            expired = float(expires_at) <= time.time()
        except (TypeError, ValueError):
            expired = False
        if expired:
            st.logout()
            st.stop()
    try:
        user = _saas.user_from_claims(claims)
    except _saas.SaaSConfigurationError as exc:
        st.error(f"The identity provider returned an unusable account: {exc}")
        if st.button("Sign out", key="invalid_identity_sign_out"):
            st.logout()
        st.stop()
    if not _SAAS_SETTINGS.allows_email(user.email):
        _, col_center, _ = st.columns([1, 3.2, 1])
        with col_center:
            _render_auth_hero_and_badges(
                title="Access Restricted",
                subtitle="Your account is not authorized to access this Load Forge workspace.",
            )
            st.error("This email address is not authorized to use Load Forge.")
            st.caption(user.email or "The identity provider did not return an email.")
            if st.button("Sign out", key="unauthorized_identity_sign_out", width="stretch"):
                st.logout()
        st.stop()
    return user


_CURRENT_SAAS_USER = _resolve_saas_user()

@st.cache_resource
def _get_account_store():
    return _saas.create_account_store(_SAAS_SETTINGS)

_ACCOUNT_STORE = _get_account_store()

def _get_current_user_account() -> _saas.UserAccount | None:
    if _CURRENT_SAAS_USER is None:
        # Default local session account for demo/offline use with full trial balance
        acc = _ACCOUNT_STORE.get_or_create_account(
            uid="local-user",
            email="local@loadforge.app",
            name="Load Forge User",
            admin_emails=_SAAS_SETTINGS.allowed_emails,
        )
        if acc.credits_balance < 2500:
            acc.credits_balance = 2500
            acc.credits_monthly_quota = 2500
        return acc
    acc = _ACCOUNT_STORE.get_or_create_account(
        uid=_CURRENT_SAAS_USER.uid,
        email=_CURRENT_SAAS_USER.email,
        name=_CURRENT_SAAS_USER.name,
        admin_emails=_SAAS_SETTINGS.allowed_emails,
    )
    return acc

_PARAM_PREFIXES = (
    "driver_", "box_", "reflex_", "pr_", "bandpass4_", "bandpass6_", "sealed_", "loss_", "sim_", "opt_", "load_type"
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


def _reflex_uses_passive_radiator(*, finder: bool = False) -> bool:
    """Return whether the bass-reflex resonator is a passive diaphragm."""
    key = "finder_reflex_resonator_type" if finder else "reflex_resonator_type"
    return st.session_state.get(key, _RESONATOR_PORT) == _RESONATOR_PR


@st.cache_data(show_spinner=False)
def _load_type_card_styles(version: str = "bp8_v2") -> str:
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
            border-color: #10b981;
            box-shadow: 0 .35rem .9rem rgba(0,0,0,.25);
            filter: saturate(.9) brightness(1.02);
            opacity: 1;
            transform: translateY(-1px);
        }
        [class*="st-key-load_card_"] div[data-testid="stButton"] button[data-testid="stBaseButton-primary"] {
            border: 2px solid #10b981;
            box-shadow: 0 0 0 2px rgba(16,185,129,.20),
                        0 .35rem 1rem rgba(16,185,129,.16);
            filter: none;
            opacity: 1;
        }
        [class*="st-key-load_card_"] div[data-testid="stButton"] button[data-testid="stBaseButton-primary"]::before {
            align-items: center;
            background: #10b981;
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
            outline: 3px solid rgba(16,185,129,.72);
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


def _select_load_type_card(load_type: str, single_select: bool) -> None:
    """Apply a load-card click before Streamlit starts the next script run."""
    if single_select:
        if st.session_state.get("load_type") == load_type:
            return
        st.session_state["load_type"] = load_type
        _on_load_type_change()
        return
    selected = set(st.session_state.get("finder_load_types", []))
    if load_type in selected:
        selected.discard(load_type)
    else:
        selected.add(load_type)
    if not selected:
        selected = {"Sealed"}
    st.session_state["finder_load_types"] = sorted(
        selected, key=lambda item: _ALL_LOAD_TYPES.index(item)
    )


def _render_load_type_buttons(active_set: set[str], single_select: bool = False) -> set[str]:
    """Grid of compact load diagrams that are themselves clickable buttons.

    In single-select mode clicking a new button *replaces* the set (radio behaviour).
    In multi-select mode each click toggles the load.
    Returns the (possibly modified) set.
    """
    st.markdown(_load_type_card_styles(), unsafe_allow_html=True)
    for row_start, row_end in ((0, 3), (3, len(_ALL_LOAD_TYPES))):
        row_load_types = _ALL_LOAD_TYPES[row_start:row_end]
        row_cols = st.columns(4)
        for offset, lt in enumerate(row_load_types):
            with row_cols[offset]:
                with st.container(key=f"load_card_{_LOAD_TYPE_SLUGS[lt]}"):
                    active = lt in active_set
                    st.button(
                        _LOAD_TYPE_SHORT[lt],
                        key=f"load_btn_{lt}",
                        type="primary" if active else "secondary",
                        width="stretch",
                        on_click=_select_load_type_card,
                        args=(lt, single_select),
                    )
                    st.markdown(
                        f'<div class="load-card-label">{_LOAD_TYPE_SHORT[lt]}</div>',
                        unsafe_allow_html=True,
                    )
    return set(active_set)


@st.cache_data(show_spinner=False)
def _workspace_tab_styles() -> str:
    """Return the two full-image workspace-tab styles with embedded assets."""
    rules = [
        """
        <style>
        [class*="st-key-workspace_tab_"] div[data-testid="stButton"] button {
            background-color: transparent;
            border: 1px solid rgba(16,185,129,.46);
            border-radius: .7rem;
            height: clamp(3.5rem, 6vw, 5rem);
            min-height: 3.5rem;
            overflow: hidden;
            padding: 0;
            position: relative;
            transition: border-color .16s ease, box-shadow .16s ease,
                        transform .16s ease;
            width: 100%;
        }
        [class*="st-key-workspace_tab_"] div[data-testid="stButton"] button::before {
            background-position: center;
            background-repeat: no-repeat;
            background-size: contain;
            border-radius: calc(.7rem - 2px);
            content: "";
            filter: grayscale(18%) brightness(.72);
            inset: 0;
            pointer-events: none;
            position: absolute;
            transition: filter .16s ease;
        }
        [class*="st-key-workspace_tab_bass_match"] div[data-testid="stButton"] button p,
        [class*="st-key-workspace_tab_box_design"] div[data-testid="stButton"] button p {
            opacity: 0;
            position: relative;
            z-index: 1;
        }
        [class*="st-key-workspace_tab_"] div[data-testid="stButton"] button:hover {
            border-color: #10b981;
            transform: translateY(-1px);
        }
        [class*="st-key-workspace_tab_"] div[data-testid="stButton"] button:hover::before {
            filter: brightness(.94);
        }
        .st-key-workspace_tab_bass_match div[data-testid="stButton"] button::before {
            filter: hue-rotate(150deg) grayscale(18%) brightness(.72);
        }
        .st-key-workspace_tab_bass_match div[data-testid="stButton"] button:hover::before {
            filter: hue-rotate(150deg) brightness(.94);
        }
        .st-key-workspace_tab_box_design div[data-testid="stButton"] button::before {
            filter: hue-rotate(290deg) saturate(.88) grayscale(18%) brightness(.72);
        }
        .st-key-workspace_tab_box_design div[data-testid="stButton"] button:hover::before {
            filter: hue-rotate(290deg) saturate(.88) brightness(.94);
        }
        .st-key-workspace_tab_bass_match div[data-testid="stButton"]
        button[data-testid="stBaseButton-primary"] {
            background-color: #000000 !important;
            border: 2px solid #10b981;
            box-shadow: 0 0 0 1px rgba(16,185,129,.22), 0 0 18px rgba(16,185,129,.16);
        }
        .st-key-workspace_tab_bass_match div[data-testid="stButton"]
        button[data-testid="stBaseButton-primary"]::before {
            filter: hue-rotate(150deg);
        }
        .st-key-workspace_tab_box_design div[data-testid="stButton"]
        button[data-testid="stBaseButton-primary"] {
            background-color: #000000 !important;
            border: 2px solid #10b981;
            box-shadow: 0 0 0 1px rgba(16,185,129,.22), 0 0 18px rgba(16,185,129,.16);
        }
        .st-key-workspace_tab_box_design div[data-testid="stButton"]
        button[data-testid="stBaseButton-primary"]::before {
            filter: hue-rotate(290deg) saturate(.88);
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
            f'.st-key-workspace_tab_{slug} button::before '
            f'{{ background-image: url("data:image/png;base64,{encoded}"); }}'
        )
    rules.append("</style>")
    return "".join(rules)


def _select_workspace(workspace: str) -> None:
    """Select a workspace from one of the large visual tabs."""
    if workspace in _available_workspaces():
        st.session_state["workspace_mode"] = workspace


def _render_workspace_tabs() -> None:
    """Render image tabs while retaining the state-compatible control."""
    st.markdown(_workspace_tab_styles(), unsafe_allow_html=True)
    active = str(st.session_state.get("workspace_mode", "Bass Match"))
    workspaces = _available_workspaces()
    tab_columns = st.columns(len(workspaces), gap="small")
    for column, workspace in zip(tab_columns, workspaces, strict=True):
        slug = _WORKSPACE_TAB_SLUGS[workspace]
        with column:
            with st.container(key=f"workspace_tab_{slug}"):
                st.button(
                    _WORKSPACE_DISPLAY_LABELS[workspace],
                    key=f"workspace_tab_button_{slug}",
                    type="primary" if workspace == active else "secondary",
                    width="stretch",
                    on_click=_select_workspace,
                    args=(workspace,),
                )
    # Keep this widget in the app tree for old sessions and automated clients.
    # CSS hides it from people because the image tabs are the primary control.
    with st.container(key="workspace_compat_control"):
        st.segmented_control(
            "Workspace",
            workspaces,
            format_func=lambda value: _WORKSPACE_DISPLAY_LABELS.get(value, value),
            key="workspace_mode",
            label_visibility="collapsed",
            width="stretch",
        )


def _catalog_record_display_identity(
    record: dict,
    fallback_name: str,
) -> tuple[str, str]:
    """Return the normalized identity shown by Catalog Maintenance."""
    manufacturer = _presets._external_catalog_manufacturer(
        str(record.get("matched_brand", record.get("brand", "")))
    )
    raw_model = _presets._external_catalog_identity_model(
        record, fallback_name
    )
    part_number = _presets._external_catalog_part_number(
        manufacturer, raw_model
    )
    return manufacturer, part_number or raw_model


def _render_catalog_maintenance() -> None:
    """Administrator-only editor for the persistent driver price catalog."""
    if not _maintenance_allowed():
        st.error("Catalog Maintenance is restricted to the administrator.")
        return
    st.markdown(
        """<style>
        section[data-testid="stSidebar"] { display: none !important; }
        [data-testid="stMainBlockContainer"] { max-width: 100% !important; padding: .35rem 1rem !important; }
        [data-testid="stVerticalBlock"] { gap: .35rem !important; }
        .maintenance-heading { font-size: 1.55rem; font-weight: 700; line-height: 1.15; margin: .1rem 0 .35rem; }
        .maintenance-meta { color: #8b949e; font-size: .78rem; margin: -.05rem 0 .25rem; }
        div[data-testid="stDataEditor"] [role="row"] { min-height: 30px !important; }
        div[data-testid="stDataEditor"] { width: 100% !important; }
        </style>""",
        unsafe_allow_html=True,
    )
    catalog_paths = {
        "Proprietario": "catalog_proprietario.json",
        "LSDB": "catalog_lsdb.json",
        "VituixCAD": "catalog_vituixcad.json",
        "Speaker Box Lite": "catalog_speakerboxlite.json",
    }
    c_back, c_title = st.columns([1.5, 8.5], vertical_alignment="center")
    with c_back:
        if st.button("← Back to app", key="maintenance_back_btn"):
            st.session_state["workspace_mode"] = "Bass Match"
            st.rerun()
    with c_title:
        st.markdown('<div class="maintenance-heading">Catalog Maintenance</div>', unsafe_allow_html=True)
    notice = str(st.session_state.pop("maintenance_notice", ""))
    if notice:
        st.success(notice)
    catalog_col, search_col, save_col, duplicate_col, delete_col, backup_col, restore_col = st.columns(
        [1.25, 2.75, .8, 1.45, 1.25, 1.4, 1.15],
        gap="small",
        vertical_alignment="bottom",
    )
    with catalog_col:
        catalog_label = st.selectbox(
            "Catalog",
            tuple(catalog_paths),
            key="maintenance_catalog",
            label_visibility="collapsed",
        )
    path = Path(__file__).parent / "data" / catalog_paths[catalog_label]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        unified_catalog = isinstance(payload.get("presets"), list)
        if unified_catalog:
            prices = {
                str(item.get("name") or item.get("model") or index): item
                for index, item in enumerate(payload["presets"])
                if isinstance(item, dict)
            }
        else:
            prices = payload.setdefault("prices", {})
    except (OSError, json.JSONDecodeError) as exc:
        st.error(f"Could not load price catalog: {exc}")
        return
    with search_col:
        query = st.text_input(
            "Search",
            key="maintenance_query",
            placeholder="Search name, brand or model…",
            label_visibility="collapsed",
        )
    with save_col:
        save_clicked = st.button(
            "Save",
            type="primary",
            key="maintenance_save",
            width="stretch",
        )
    with duplicate_col:
        duplicate_clicked = st.button(
            "Duplicate selected",
            key="maintenance_duplicate",
            width="stretch",
        )
    with delete_col:
        delete_clicked = st.button(
            "Delete selected",
            key="maintenance_delete",
            width="stretch",
        )
    backup_bytes = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    with backup_col:
        st.download_button(
            "Download backup",
            data=backup_bytes,
            file_name=f"{path.stem}_backup.json",
            mime="application/json",
            key="maintenance_backup_download",
            width="stretch",
        )
    with restore_col:
        with st.popover("Restore backup", width="stretch"):
            uploaded = st.file_uploader(
                "JSON backup",
                type=["json"],
                key="maintenance_restore_upload",
            )
            if uploaded is not None and st.button(
                "Restore selected catalog",
                key="maintenance_restore_button",
                type="primary",
                width="stretch",
            ):
                try:
                    restored = json.loads(uploaded.getvalue().decode("utf-8"))
                    if not isinstance(restored, dict) or not (
                        isinstance(restored.get("prices"), dict)
                        or isinstance(restored.get("presets"), list)
                    ):
                        raise ValueError("backup must contain prices or presets")
                    path.write_text(json.dumps(restored, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                    _pricing._load_driver_price_records.cache_clear()
                    st.success("Full library restored")
                    st.rerun()
                except (UnicodeDecodeError, json.JSONDecodeError, ValueError, OSError) as exc:
                    st.error(f"Restore failed: {exc}")
    keys = [str(k) for k in prices]
    matches = [k for k in keys if not query or query.casefold() in k.casefold()]
    st.markdown(
        f'<div class="maintenance-meta">{catalog_label} · {len(prices):,} records · {len(matches):,} shown</div>',
        unsafe_allow_html=True,
    )
    if unified_catalog:
        mechanical_fields = (
            "overall_diameter_mm", "cutout_diameter_mm", "depth_mm",
            "mounting_depth_mm", "bolt_circle_mm", "mounting_hole_count",
            "mounting_hole_diameter_mm", "weight_kg",
        )
        essential_fields = (
            "overall_diameter_mm", "cutout_diameter_mm", "depth_mm", "weight_kg",
        )

        def has_positive(record: dict, field: str) -> bool:
            value = (record.get("mechanical") or {}).get(field)
            return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0

        catalog_records = list(prices.values())
        any_mechanical = sum(
            any(has_positive(record, field) for field in mechanical_fields)
            for record in catalog_records
        )
        essential_complete = sum(
            all(has_positive(record, field) for field in essential_fields)
            for record in catalog_records
        )
        fully_complete = sum(
            all(has_positive(record, field) for field in mechanical_fields)
            for record in catalog_records
        )
        metric_any, metric_essential, metric_full = st.columns(3)
        metric_any.metric("Any real mechanical data", f"{any_mechanical:,} / {len(catalog_records):,}")
        metric_essential.metric("Essential 4 complete", f"{essential_complete:,} / {len(catalog_records):,}")
        metric_full.metric("All 8 complete", f"{fully_complete:,} / {len(catalog_records):,}")
        coverage_labels = {
            "overall_diameter_mm": "overall",
            "cutout_diameter_mm": "cutout",
            "depth_mm": "depth",
            "mounting_depth_mm": "mount depth",
            "bolt_circle_mm": "bolt circle",
            "mounting_hole_count": "hole count",
            "mounting_hole_diameter_mm": "hole Ø",
            "weight_kg": "weight",
        }
        coverage = " · ".join(
            f"{coverage_labels[field]} {sum(has_positive(record, field) for record in catalog_records):,}"
            for field in mechanical_fields
        )
        st.caption(f"Verified mechanical field coverage: {coverage}")
    rows = []
    original_rows = {}
    for key in matches:
        record = dict(prices.get(key) or {})
        driver = dict(record.get("driver") or {})
        mechanical = dict(record.get("mechanical") or {})
        published = dict(record.get("published_specs") or {})
        manufacturer, part_number = _catalog_record_display_identity(
            record, key
        )
        status = str(record.get("availability", "InStock")).rsplit("/", 1)[-1]
        if status not in {"InStock", "OutOfStock", "Discontinued"}:
            status = "InStock"
        row = {"_key": key, "Name": record.get("matched_name", record.get("name", key)),
               "Brand": manufacturer, "MPN": part_number,
               "Xmax mm": float(driver.get("xmax_mm") or 0),
               "Pmax W": float(driver.get("pe_w") or 0),
               "Le mH": float(driver.get("le_mh") or 0),
               "Overall mm": mechanical.get("overall_diameter_mm"),
               "Cutout mm": mechanical.get("cutout_diameter_mm"),
               "Depth mm": mechanical.get("depth_mm"),
               "Mount depth mm": mechanical.get("mounting_depth_mm"),
               "Bolt circle mm": mechanical.get("bolt_circle_mm"),
               "Weight kg": mechanical.get("weight_kg"),
               "Znom ohm": published.get("nominal_impedance_ohm"),
               "Sensitivity dB": published.get("sensitivity_db"),
               "Voice coil mm": published.get("voice_coil_diameter_mm"),
               "Xmech mm": published.get("xmech_mm"),
               "Nominal diameter in": published.get("nominal_diameter_in"),
               "Price": float(record.get("price") or 0),
               "Currency": record.get("currency", record.get("price_currency", "EUR")), "Link": record.get("price_url") or record.get("url", ""),
               "Status": status, "Select": False}
        rows.append(row)
        original_rows[key] = row
    def compact_width(column: str, minimum: int, maximum: int) -> int:
        longest = max((len(str(row.get(column, ""))) for row in rows), default=0)
        return min(maximum, max(minimum, 22 + longest * 7))

    edited = st.data_editor(
        pd.DataFrame(rows),
        hide_index=True,
        width="stretch",
        height=860,
        disabled=[
            "_key", "Overall mm", "Cutout mm", "Depth mm", "Mount depth mm",
            "Bolt circle mm", "Weight kg", "Znom ohm", "Sensitivity dB",
            "Voice coil mm", "Xmech mm", "Nominal diameter in",
        ],
        column_config={
            "_key": None,
            "Name": None,
            "Brand": st.column_config.TextColumn(
                "Manufacturer", width=compact_width("Brand", 85, 150)
            ),
            "MPN": st.column_config.TextColumn(
                "Part number", width=compact_width("MPN", 90, 180)
            ),
            "Xmax mm": st.column_config.NumberColumn(
                "Xmax (mm)", width=92, min_value=0.0, format="%.2f"
            ),
            "Pmax W": st.column_config.NumberColumn(
                "Pmax (W)", width=92, min_value=0.0, format="%.1f"
            ),
            "Le mH": st.column_config.NumberColumn(
                "Le (mH)", width=82, min_value=0.0, format="%.3f"
            ),
            "Overall mm": st.column_config.NumberColumn("Overall Ø", width=92, format="%.1f mm"),
            "Cutout mm": st.column_config.NumberColumn("Cutout Ø", width=88, format="%.1f mm"),
            "Depth mm": st.column_config.NumberColumn("Depth", width=82, format="%.1f mm"),
            "Mount depth mm": st.column_config.NumberColumn("Mount depth", width=105, format="%.1f mm"),
            "Bolt circle mm": st.column_config.NumberColumn("Bolt circle", width=96, format="%.1f mm"),
            "Weight kg": st.column_config.NumberColumn("Weight", width=82, format="%.2f kg"),
            "Znom ohm": st.column_config.NumberColumn("Znom", width=75, format="%.1f Ω"),
            "Sensitivity dB": st.column_config.NumberColumn("Sensitivity", width=100, format="%.1f dB"),
            "Voice coil mm": st.column_config.NumberColumn("Voice coil Ø", width=100, format="%.1f mm"),
            "Xmech mm": st.column_config.NumberColumn("Xmech", width=82, format="%.2f mm"),
            "Nominal diameter in": st.column_config.NumberColumn("Nominal Ø", width=95, format='%.2f"'),
            "Price": st.column_config.NumberColumn("Price", width=82, format="%.2f"),
            "Currency": st.column_config.TextColumn("Currency", width=82),
            "Link": st.column_config.LinkColumn("Link", width=82, display_text="Open ↗"),
            "Status": st.column_config.SelectboxColumn("Status", options=["InStock", "OutOfStock", "Discontinued"], width=120),
            "Select": st.column_config.CheckboxColumn("Select", width=74),
        },
        key=f"maintenance_table_{catalog_label}_{st.session_state.get('maintenance_table_revision', 0)}",
    )
    edited_rows = edited.to_dict("records")
    selected_keys = [
        str(row.get("_key", ""))
        for row in edited_rows
        if row.get("Select") and str(row.get("_key", "")) in prices
    ]
    selection_action = duplicate_clicked or delete_clicked
    if selection_action and not selected_keys:
        st.warning("Select at least one row first.")
    elif save_clicked or selection_action:
        for row in edited_rows:
            key = str(row.get("_key", ""))
            if key not in prices:
                continue
            if not any(
                row.get(column) != original_rows[key].get(column)
                for column in (
                    "Name", "Brand", "MPN", "Xmax mm", "Pmax W", "Le mH",
                    "Price", "Currency", "Link", "Status",
                )
            ):
                continue
            driver = dict(prices[key].get("driver") or {})
            driver.update(
                xmax_mm=float(row.get("Xmax mm") or 0),
                pe_w=float(row.get("Pmax W") or 0),
                le_mh=float(row.get("Le mH") or 0),
            )
            updated = dict(price=float(row.get("Price") or 0), currency=str(row.get("Currency") or "EUR").upper(),
                           availability=str(row.get("Status") or "InStock"), matched_name=str(row.get("Name") or key),
                           matched_brand=str(row.get("Brand") or ""), matched_mpn=str(row.get("MPN") or key),
                           part_number_override=str(row.get("MPN") or key),
                           driver=driver,
                           source="Manual catalog maintenance")
            updated["price_url" if unified_catalog else "url"] = str(row.get("Link") or "")
            prices[key].update(updated)
        if delete_clicked:
            for key in selected_keys:
                prices.pop(key, None)
        elif duplicate_clicked:
            for source_key in selected_keys:
                new_key = source_key + "-copy"
                i = 2
                while new_key in prices:
                    new_key = f"{source_key}-copy-{i}"
                    i += 1
                copied = dict(prices[source_key])
                copied["matched_name"] = new_key
                if unified_catalog:
                    copied["name"] = new_key
                prices[new_key] = copied
        if unified_catalog:
            payload["presets"] = list(prices.values())
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        _pricing._load_driver_price_records.cache_clear()
        st.session_state["maintenance_table_revision"] = int(
            st.session_state.get("maintenance_table_revision", 0)
        ) + 1
        if delete_clicked:
            st.session_state["maintenance_notice"] = f"Deleted {len(selected_keys)} selected record(s)."
        elif duplicate_clicked:
            st.session_state["maintenance_notice"] = f"Duplicated {len(selected_keys)} selected record(s)."
        else:
            st.session_state["maintenance_notice"] = "Catalog saved."
        st.rerun()

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
    "Bass Match": "Bass Match",
    "Box Design": "Box Design",
    "Catalog Maintenance": "Catalog Maintenance",
    "User Management": "User Management (Admin)",
}
_WORKSPACE_TAB_SLUGS = {
    "Bass Match": "bass_match",
    "Box Design": "box_design",
    "Catalog Maintenance": "catalog_maintenance",
    "User Management": "user_management",
}

def _maintenance_allowed() -> bool:
    """Restrict catalog editing and user management to the explicitly configured administrator."""
    acc = _get_current_user_account()
    if acc and acc.is_admin:
        return True
    admin_email = str(
        os.getenv("LOAD_FORGE_ADMIN_EMAIL", "playloud79@gmail.com")
    ).strip().casefold()
    if _CURRENT_SAAS_USER is None:
        return not _SAAS_SETTINGS.enabled and bool(admin_email)
    uid = str(os.getenv("LOAD_FORGE_ADMIN_UID", "")).strip()
    return bool(
        (admin_email and str(_CURRENT_SAAS_USER.email).casefold() == admin_email)
        or (uid and str(_CURRENT_SAAS_USER.uid) == uid)
    )


_CATALOG_PATH_BY_PROVENANCE = {
    "LSDB": "catalog_lsdb.json",
    "Load Forge database": "catalog_proprietario.json",
    "VituixCAD": "catalog_vituixcad.json",
    "Speaker Box Lite": "catalog_speakerboxlite.json",
}


def _catalog_path_for_preset(preset_name: str) -> Path | None:
    """Return the editable source catalog for one external driver preset."""
    if not preset_name or preset_name == "Custom":
        return None
    try:
        provenance = _acoustics.driver_preset_provenance_category(preset_name)
    except ValueError:
        return None
    filename = _CATALOG_PATH_BY_PROVENANCE.get(provenance)
    return (
        Path(__file__).parent / "data" / filename
        if filename is not None
        else None
    )


def _driver_catalog_mapping(driver: _acoustics.DriverTS) -> dict[str, float]:
    """Serialize the editable Box Design driver fields for a catalog record."""
    return {
        "fs_hz": float(driver.fs_hz), "vas_l": float(driver.vas_l),
        "qts": float(driver.qts), "qms": float(driver.qms),
        "re_ohm": float(driver.re_ohm), "sd_cm2": float(driver.sd_cm2),
        "le_mh": float(driver.le_mh), "le10k_mh": float(driver.le10k_mh or 0.0),
        "xmax_mm": float(driver.xmax_mm), "pe_w": float(driver.pe_w),
        "mms_g": float(driver.mms_g or 0.0),
        "cms_mm_per_n": float(driver.cms_mm_per_n or 0.0),
        "bl_tm": float(driver.bl_tm or 0.0),
    }


def _update_catalog_driver_from_box_design(
    preset_name: str,
    driver: _acoustics.DriverTS,
    *,
    path: Path | None = None,
) -> str:
    """Persist the selected external preset's T/S values from Box Design."""
    target_path = path or _catalog_path_for_preset(preset_name)
    if target_path is None:
        raise ValueError("This driver is not backed by an editable catalog")
    try:
        payload = json.loads(target_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read the source catalog: {exc}") from exc
    records = payload.get("presets") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        raise ValueError("The source catalog has no editable preset records")
    selected_fields = _driver_catalog_mapping(_acoustics.get_driver_preset(preset_name))
    preset_info = _acoustics.driver_preset_info(preset_name)
    selected_brand = _presets._external_catalog_manufacturer(preset_info.brand)
    selected_part_number = _presets._external_catalog_part_number(
        selected_brand, preset_info.part_number or preset_info.model,
    )
    matching_record = None
    for record in records:
        if not isinstance(record, dict):
            continue
        if str(record.get("name", "")) == preset_name:
            matching_record = record
            break
        record_brand, record_part_number = _catalog_record_display_identity(
            record, str(record.get("name", "")),
        )
        if (
            selected_part_number
            and record_brand.casefold() == selected_brand.casefold()
            and record_part_number.casefold() == selected_part_number.casefold()
        ):
            matching_record = record
            break
        stored = record.get("driver")
        if not isinstance(stored, dict):
            continue
        try:
            matches_selected = all(
                np.isclose(float(stored.get(field, 0.0) or 0.0), value,
                           rtol=1e-9, atol=1e-9)
                for field, value in selected_fields.items()
                if field in {"fs_hz", "vas_l", "qts", "qms", "re_ohm", "sd_cm2"}
            )
        except (TypeError, ValueError):
            matches_selected = False
        if matches_selected:
            matching_record = record
            break
    if matching_record is None:
        raise ValueError("Could not find the selected driver in its source catalog")
    matching_record["driver"] = _driver_catalog_mapping(driver)
    try:
        target_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise ValueError(f"Could not update the source catalog: {exc}") from exc
    for loader in (
        _presets._load_loudspeaker_database_presets,
        _presets._load_manufacturer_presets,
        _presets._load_vituixcad_presets,
        _presets._load_speakerboxlite_presets,
        _presets._external_tiers,
        _presets.driver_preset_names,
        _presets.driver_preset_info,
        _presets.driver_preset_provenance_category,
        _presets.get_driver_preset,
    ):
        loader.cache_clear()
    return str(matching_record.get("name", preset_name))


def _available_workspaces() -> tuple[str, ...]:
    return _WORKSPACES
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
_FINDER_CTA_LABEL = "Run Bass Match"
_FINDER_RANKING_VERSION = 11
_FINDER_CONTEXT_FILTERED_POOL_VERSION = "user-inputs-v2"
_FINDER_SPL_PREFILTER_HEADROOM_DB = 6.0
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


def _is_param_key(key: str) -> bool:
    if not any(key.startswith(prefix) for prefix in _PARAM_PREFIXES):
        return False
    if "apply" in key or "button" in key or key.startswith("btn_") or "combo" in key:
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
        objective = str(st.session_state.get("opt_objective", "Max extension"))
        return objective if objective in _OPT_OBJECTIVE_LABELS else "Max extension"
    # v0.3 "Suggested" (empirical starter) and unknown values.
    return "Max extension"


def _set_box_strategy_state(strategy: str) -> None:
    """Store a strategy plus the legacy keys older .lfp files round-trip."""
    previous = str(st.session_state.get("box_strategy", "Max extension"))
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
    return str(st.session_state.get("box_strategy", "Max extension")) in _OPT_OBJECTIVE_LABELS


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


_LFP_MAX_SAVED_BATCH_RESULTS = 100


def _compact_result_row(row: dict) -> dict:
    """Omit null/NaN fields from saved rows to keep .lfp files lightweight."""
    return {
        key: value
        for key, value in row.items()
        if value is not None and not (isinstance(value, float) and not np.isfinite(value))
    }


def _collect_bass_match_project_state(
    *,
    include_results: bool = True,
) -> dict:
    state = {}
    for key in _BASS_MATCH_PROJECT_STATE_KEYS:
        if key in st.session_state:
            state[key] = _json_safe(st.session_state[key])
    bass_match = {"state": state}
    if include_results:
        defaults = {
            "batch_results": [],
            "batch_result_context": [],
            "batch_search_completed": False,
            "finder_last_run_stats": {},
        }
        for key in _BASS_MATCH_PROJECT_RESULT_KEYS:
            val = st.session_state.get(key, defaults[key])
            if key == "batch_results" and isinstance(val, list):
                val = [
                    _compact_result_row(row)
                    for row in val[:_LFP_MAX_SAVED_BATCH_RESULTS]
                    if isinstance(row, dict)
                ]
            bass_match[key] = _json_safe(val)
    return bass_match


def _build_lfp_project(
    project: dict | None = None,
    *,
    include_results: bool = True,
) -> dict:
    """Build the complete portable project, including Bass Match state."""
    name = str(
        (project or {}).get("name")
        or st.session_state.get("project_name", "Untitled project")
    ).strip() or "Untitled project"
    now = datetime.now(UTC).isoformat()
    project_meta = {
        "id": f"lfp_{uuid.uuid4().hex}",
        "name": name,
        "created_at": now,
        "updated_at": now,
    }
    return {
        "_load_forge_meta": {
            "version": _VERSION,
            "format": _LFP_FORMAT_VERSION,
            "kind": "project",
        },
        "project": _json_safe(project_meta),
        "parameters": _json_safe(_collect_params()),
        "bass_match": _collect_bass_match_project_state(
            include_results=include_results
        ),
    }


def _bass_match_results_signature() -> str:
    """Hash heavy Finder output once, then reuse it across UI reruns."""
    cached = st.session_state.get("_bass_match_results_signature")
    if isinstance(cached, str) and cached:
        return cached
    result_payload = {
        key: _json_safe(st.session_state.get(key, default))
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
        if key in _BASS_MATCH_PROJECT_STATE_KEYS:
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
    if context is not None and not isinstance(context, (list, tuple)):
        raise TypeError("LFP Bass Match result context must be a list")
    restored_context = list(context or ())
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
            _is_param_key(key)
            or key in _BASS_MATCH_PROJECT_STATE_KEYS
            or key in _BASS_MATCH_PROJECT_RESULT_KEYS
            or key in _PROJECT_TRANSIENT_STATE_KEYS
            or str(key).startswith(_PROJECT_TRANSIENT_STATE_PREFIXES)
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
    if "box_strategy" not in data:
        if st.session_state.get("sim_auto_align", True):
            strategy = "Max extension"
        elif st.session_state.get("opt_align_mode") == "Optimized (goals)":
            strategy = _normalize_box_strategy("Optimized")
        else:
            strategy = "Manual"
    else:
        strategy = _normalize_box_strategy(st.session_state.get("box_strategy", "Max extension"))
    _set_box_strategy_state(strategy)
    if strategy in _OPT_OBJECTIVE_LABELS:
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


def _render_authenticated_account_controls(user: _saas.SaaSUser) -> None:
    """Show the signed-in identity in the sidebar."""
    acc = _get_current_user_account()
    if acc is None:
        return
    entitlements = _saas.effective_entitlements(user, _SAAS_SETTINGS)
    if entitlements.promotion == "open_beta":
        tier_label = "Open Beta · full access"
    else:
        tier_label = f"{user.plan.capitalize()} plan"
    st.markdown(f"**Account** · *{acc.plan.upper()}*")
    st.caption(f"{user.name or user.email} · {tier_label}")
    if user.email and user.email != (user.name or ""):
        st.caption(user.email)
    st.markdown(
        f"💳 **{acc.credits_balance:,}** / {acc.credits_monthly_quota:,} credits"
    )
    st.caption(f"Monthly refill: {acc.quota_reset_at.strftime('%d %b %Y')}")
    account_col, logout_col = st.columns([3, 2])
    with account_col:
        st.caption(f"Total simulated: {acc.total_simulations_run:,}")
    with logout_col:
        if not _SAAS_SETTINGS.auth_bypass and st.button(
            "Sign out",
            key="saas_sign_out",
            width="stretch",
        ):
            _sign_out_saas()
    st.divider()


def _project_download_filename(name: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", str(name).strip()).strip("._")
    return f"{stem or 'load_forge_project'}.lfp"


def _render_project_menu() -> None:
    """Render project file actions (.lfp import/export, reset, and share link)."""
    project_name = str(
        st.session_state.get("project_name", "Untitled project")
    ).strip() or "Untitled project"
    project_expander = st.expander(
        f"Project · {project_name}",
        expanded=bool(st.session_state.get("_project_menu_auto_open")),
        key="project_menu_expander",
        on_change="rerun",
    )
    if not project_expander.open:
        return
    with project_expander:
        if _CURRENT_SAAS_USER is not None:
            _render_authenticated_account_controls(_CURRENT_SAAS_USER)

        name_revision = int(st.session_state.get("_project_name_revision", 0))
        name_input = st.text_input(
            "Project name",
            value=project_name,
            key=f"project_name_input_{name_revision}",
            max_chars=80,
            help="Name used when exporting the .lfp project file",
        )
        if name_input.strip() and name_input.strip() != project_name:
            st.session_state["project_name"] = name_input.strip()
            project_name = name_input.strip()

        payload = _build_lfp_project({"name": project_name}, include_results=True)
        lfp_data = json.dumps(payload, indent=2, allow_nan=False).encode("utf-8")
        st.download_button(
            "Download .lfp",
            lfp_data,
            _project_download_filename(project_name),
            "application/json",
            width="stretch",
            key="project_download_lfp_btn",
            help="Save the current design, box parameters, and Bass Match state to your computer.",
        )

        upload_revision = int(st.session_state.get("_project_upload_revision", 0))
        upload = st.file_uploader(
            "Open .lfp project or CRW driver",
            type=["lfp", "json", "crw"],
            key=f"_project_upload_{upload_revision}",
            help="Load a previously saved .lfp project file or CRW driver.",
        )
        if upload is not None:
            try:
                if upload.name.casefold().endswith(".crw"):
                    crw = _afw_compare.parse_crw_text(upload.getvalue().decode("latin-1"))
                    _snapshot_design_state()
                    driver = _acoustics.DriverTS(
                        fs_hz=crw.fs_hz, vas_l=crw.vas_l, qts=crw.qts,
                        qms=crw.qms, re_ohm=crw.re_ohm, sd_cm2=crw.sd_cm2,
                        le_mh=crw.le_10khz_mh, xmax_mm=crw.xmax_mm, pe_w=crw.pe_w,
                    )
                    _apply_driver_preset(driver)
                    st.session_state["driver_preset_name"] = "Custom driver"
                    st.session_state["_project_upload_revision"] = upload_revision + 1
                    st.toast(f"Loaded CRW driver: {crw.name}")
                    st.rerun()
                payload = json.loads(upload.getvalue().decode("utf-8"))
                _snapshot_design_state()
                count = _apply_lfp_project(payload)
                if isinstance(payload.get("project"), dict) and payload["project"].get("name"):
                    st.session_state["project_name"] = str(payload["project"]["name"]).strip()
                elif upload.name:
                    st.session_state["project_name"] = Path(upload.name).stem
                st.session_state["_project_name_revision"] = name_revision + 1
                st.session_state["_project_upload_revision"] = upload_revision + 1
                st.toast(f"Loaded project · {count} parameters")
                st.rerun()
            except Exception as exc:
                logger.exception("Could not parse uploaded project")
                st.error(f"Could not load project: {exc}")

        if st.session_state.get("_design_state_backup"):
            if st.button(
                "Restore previous design",
                key="project_restore_previous_design",
                width="stretch",
                help="Undo the last preset or shared-link load and restore the previous parameters.",
            ):
                _restore_design_state()
                st.toast("Previous design restored")
                st.rerun()

        if st.button(
            "New / Reset design",
            key="project_reset_design_btn",
            width="stretch",
            help="Reset all parameters and return to the default design.",
        ):
            _clear_active_project_state()
            _reset_finder_defaults()
            st.session_state["project_name"] = "Untitled project"
            st.session_state["_project_name_revision"] = name_revision + 1
            st.toast("Reset to default design")
            st.rerun()

        if st.button(
            "Share via URL",
            key="project_share_url",
            width="stretch",
            help="Encodes the current design into the page URL and shows the link below, ready to copy.",
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
                width="stretch",
            ):
                st.session_state["_applied_share_token"] = None
                st.query_params.pop("d", None)
                st.rerun()


def _snapshot_revision(snapshot: dict) -> str:
    """Return a compact persistent identity for a potentially large snapshot."""
    revision = str(snapshot.get("_revision", ""))
    if not revision:
        revision = uuid.uuid4().hex
        snapshot["_revision"] = revision
    return revision


def _chart_signature() -> str:
    prefixes = (
        "driver_", "box_", "reflex_", "sealed_", "loss_", "sim_", "plot_", "cursor_",
        "load_type", "pinned_",
    )
    data = {}
    for key, value in st.session_state.items():
        if not any(key.startswith(prefix) for prefix in prefixes):
            continue
        if key == "pinned_response" and "pinned_responses" in st.session_state:
            continue
        if key == "pinned_responses" and isinstance(value, list):
            data[key] = [
                (
                    _snapshot_revision(pin),
                    str(pin.get("label", "")),
                    str(pin.get("color", "")),
                    bool(pin.get("visible", True)),
                )
                for pin in value
                if isinstance(pin, dict)
            ]
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
        q_abs=float(st.session_state["reflex_q_abs"]) if use_custom_losses else _DEFAULT_REFLEX_Q_ABS,
        q_leak=float(st.session_state["reflex_q_leak"]) if use_custom_losses else _DEFAULT_REFLEX_Q_LEAK,
        q_port=float(st.session_state["reflex_q_port"]) if use_custom_losses else _DEFAULT_REFLEX_Q_PORT,
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
    for key, value in _FINDER_DEFAULTS.items():
        st.session_state[key] = value
    st.session_state["_finder_defaults_version"] = _FINDER_DEFAULTS_VERSION
    st.session_state.pop("batch_results", None)
    st.session_state.pop("batch_result_context", None)
    st.session_state.pop("batch_search_completed", None)
    st.session_state.pop("finder_last_run_stats", None)
    st.session_state.pop("_restored_bass_match_controls_signature", None)
    _invalidate_bass_match_results_signature()


def _ensure_finder_defaults() -> None:
    """Migrate stale Finder widgets without pre-seeding implicit UI minima."""
    # Desired F3 was retired from Bass Match: it behaved as a soft optimizer
    # preference rather than a reliable ranking constraint.
    st.session_state.pop("finder_target_f3_hz", None)
    # Every usable ranked candidate is now shown; old 1–200 display caps must
    # not survive in live sessions or restored projects.
    st.session_state.pop("finder_result_count", None)
    if st.session_state.get("_finder_defaults_version") != _FINDER_DEFAULTS_VERSION:
        # Retired v3 widgets: the scan now always covers the whole filtered
        # library and every candidate goes through the optimizer.
        for key in (
            *_FINDER_DEFAULTS,
            "finder_candidate_limit",
            "finder_result_count",
            "finder_use_optimizer",
            "finder_target_f3_hz",
        ):
            st.session_state.pop(key, None)
        st.session_state["_finder_defaults_version"] = _FINDER_DEFAULTS_VERSION
        st.session_state.pop("batch_results", None)
        st.session_state.pop("batch_result_context", None)
        st.session_state.pop("batch_search_completed", None)
        st.session_state.pop("finder_last_run_stats", None)
        st.session_state.pop("_restored_bass_match_controls_signature", None)
        _invalidate_bass_match_results_signature()
    else:
        # Keep conditionally rendered Finder values alive while Design is open.
        for key in _FINDER_DEFAULTS:
            if key in st.session_state:
                st.session_state[key] = st.session_state[key]


def _ensure_price_currency_default() -> None:
    """Migrate existing sessions to the EUR price display default once."""
    if st.session_state.get("_price_currency_defaults_version") != _PRICE_CURRENCY_DEFAULTS_VERSION:
        st.session_state["preset_price_currency"] = "EUR"
        st.session_state["_price_currency_defaults_version"] = _PRICE_CURRENCY_DEFAULTS_VERSION


def _preserve_design_state() -> None:
    """Keep design widget values alive while the Finder workspace is open.

    Streamlit drops widget-bound state for keyed widgets that skip a rerun:
    without this, one trip through Find a driver silently resets voltage,
    manual box values and T/S edits back to their defaults or widget minima.
    """
    for key in list(st.session_state):
        if _is_param_key(key):
            st.session_state[key] = st.session_state[key]
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


def _apply_alignment(alignment: _acoustics.DccavAlignment):
    st.session_state["box_vh_l"] = float(alignment.vh_l)
    st.session_state["box_fh_hz"] = float(alignment.fh_hz)
    st.session_state["box_vl_l"] = float(alignment.vl_l)
    st.session_state["box_fl_hz"] = float(alignment.fl_hz)


def _apply_reflex_alignment(alignment: _acoustics.ReflexAlignment):
    st.session_state["reflex_vb_l"] = float(alignment.vb_l)
    st.session_state["reflex_fb_hz"] = float(alignment.fb_hz)


def _apply_sealed_alignment(alignment: _acoustics.SealedAlignment):
    st.session_state["sealed_vb_l"] = float(alignment.vb_l)


def _apply_bandpass4_alignment(alignment: _acoustics.Bandpass4Alignment):
    st.session_state["bandpass4_vs_l"] = float(alignment.vs_l)
    st.session_state["bandpass4_vp_l"] = float(alignment.vp_l)
    st.session_state["bandpass4_fp_hz"] = float(alignment.fp_hz)


def _apply_bandpass6_alignment(alignment: _acoustics.Bandpass6Alignment):
    st.session_state["bandpass6_vr_l"] = float(alignment.vr_l)
    st.session_state["bandpass6_fr_hz"] = float(alignment.fr_hz)
    st.session_state["bandpass6_vp_l"] = float(alignment.vp_l)
    st.session_state["bandpass6_fp_hz"] = float(alignment.fp_hz)


def _design_objective_label() -> str:
    strategy = str(st.session_state.get("box_strategy", "Max extension"))
    if strategy in _OPT_OBJECTIVE_LABELS:
        return strategy
    fallback = str(st.session_state.get("opt_objective", "Max extension"))
    return fallback if fallback in _OPT_OBJECTIVE_LABELS else "Max extension"


def _optimizer_goals_from_state() -> _acoustics.OptimizationGoals:
    return _acoustics.OptimizationGoals(
        objective=_OPT_OBJECTIVE_LABELS[_design_objective_label()],
        max_total_volume_l=float(st.session_state.get("opt_max_volume_l", 0.0)) or None,
        target_f3_hz=float(st.session_state.get("opt_target_f3_hz", 0.0)) or None,
        max_ripple_db=float(st.session_state.get("opt_max_ripple_db", 3.0)),
        max_excursion_ratio=float(st.session_state.get("opt_excursion_ratio", 1.0)),
        max_group_delay_ms=float(st.session_state.get("opt_max_gd_ms", 0.0)) or None,
        ripple_max_freq_hz=float(st.session_state.get("opt_max_ripple_freq_hz", 0.0)) or None,
    )


def _alignment_uses_optimizer() -> bool:
    return (
        st.session_state.get("load_type", "DCCAV") != "Infinite baffle"
        and _box_strategy_is_auto()
    )


def _apply_bandpass8_alignment(alignment: _acoustics.Bandpass8Alignment) -> None:
    st.session_state["bp8_v1_l"] = float(alignment.v1_l)
    st.session_state["bp8_f1_hz"] = float(alignment.f1_hz)
    st.session_state["bp8_v2_l"] = float(alignment.v2_l)
    st.session_state["bp8_f2_hz"] = float(alignment.f2_hz)
    st.session_state["bp8_v3_l"] = float(alignment.v3_l)
    st.session_state["bp8_f3_hz"] = float(alignment.f3_hz)


def _apply_optimized_box(
    box: _acoustics.DccavBox | _acoustics.ReflexBox | _acoustics.Bandpass4Box | _acoustics.Bandpass6Box | _acoustics.Bandpass8Box | _acoustics.SealedBox,
):
    if isinstance(box, _acoustics.ReflexBox):
        st.session_state["reflex_vb_l"] = float(box.vb_l)
        st.session_state["reflex_fb_hz"] = float(box.fb_hz)
    elif isinstance(box, _acoustics.SealedBox):
        st.session_state["sealed_vb_l"] = float(box.vb_l)
    elif isinstance(box, _acoustics.Bandpass4Box):
        st.session_state["bandpass4_vs_l"] = float(box.vs_l)
        st.session_state["bandpass4_vp_l"] = float(box.vp_l)
        st.session_state["bandpass4_fp_hz"] = float(box.fp_hz)
    elif isinstance(box, _acoustics.Bandpass6Box):
        st.session_state["bandpass6_vr_l"] = float(box.vr_l)
        st.session_state["bandpass6_fr_hz"] = float(box.fr_hz)
        st.session_state["bandpass6_vp_l"] = float(box.vp_l)
        st.session_state["bandpass6_fp_hz"] = float(box.fp_hz)
    elif isinstance(box, _acoustics.Bandpass8Box):
        st.session_state["bp8_v1_l"] = float(box.v1_l)
        st.session_state["bp8_f1_hz"] = float(box.f1_hz)
        st.session_state["bp8_v2_l"] = float(box.v2_l)
        st.session_state["bp8_f2_hz"] = float(box.f2_hz)
        st.session_state["bp8_v3_l"] = float(box.v3_l)
        st.session_state["bp8_f3_hz"] = float(box.f3_hz)
    else:
        st.session_state["box_vh_l"] = float(box.vh_l)
        st.session_state["box_fh_hz"] = float(box.fh_hz)
        st.session_state["box_vl_l"] = float(box.vl_l)
        st.session_state["box_fl_hz"] = float(box.fl_hz)


def _optimized_port_diameter_cm(
    driver: _acoustics.DriverTS,
    result: _acoustics.SimulationResult,
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
        _acoustics.port_min_diameter_cm(volume_l, tuning_hz, end_correction),
        _acoustics.port_displacement_min_diameter_cm(driver, tuning_hz),
        _acoustics.rated_velocity_diameter_cm(
            driver, result, voltage_v,
            volume_velocity),
    )
    sized_cm = _acoustics.port_diameter_for_load(
        volume_l, tuning_hz, end_correction, floor_cm)
    maximum_cm = float(_acoustics.OPTIMIZER_MAX_PORT_DIAMETER_CM)
    if sized_cm is not None:
        diameter_cm = sized_cm
    else:
        diameter_cm = np.ceil(max(1.0, floor_cm) * 2.0) / 2.0
    return float(min(max(1.0, diameter_cm), maximum_cm))


def _apply_optimized_port_geometry(
    driver: _acoustics.DriverTS,
    box: _acoustics.DccavBox | _acoustics.ReflexBox | _acoustics.Bandpass4Box | _acoustics.Bandpass6Box | _acoustics.Bandpass8Box | _acoustics.SealedBox,
) -> None:
    """Replace stale preset diameters with geometry for the optimized box."""
    if isinstance(box, _acoustics.SealedBox):
        return
    if isinstance(box, _acoustics.ReflexBox) and _reflex_uses_passive_radiator():
        return
    freq = np.geomspace(
        min(10.0, driver.fs_hz / 4.0), max(400.0, 4.0 * driver.fs_hz), 240)
    voltage_v = float(st.session_state.get("sim_voltage", 2.83))
    if isinstance(box, _acoustics.ReflexBox):
        result = _acoustics.simulate_reflex(driver, box, freq, voltage_v)
        st.session_state["reflex_port_d_cm"] = _optimized_port_diameter_cm(
            driver, result, box.vb_l, box.fb_hz, 1.43, "lower")
    elif isinstance(box, _acoustics.Bandpass4Box):
        result = _acoustics.simulate_bandpass4(driver, box, freq, voltage_v)
        st.session_state["bandpass4_port_d_cm"] = _optimized_port_diameter_cm(
            driver, result, box.vp_l, box.fp_hz, 1.43, "lower")
    elif isinstance(box, _acoustics.Bandpass6Box):
        result = _acoustics.simulate_bandpass6(driver, box, freq, voltage_v)
        st.session_state["bandpass6_port_d_r_cm"] = _optimized_port_diameter_cm(
            driver, result, box.vr_l, box.fr_hz, 1.43, "upper")
        st.session_state["bandpass6_port_d_p_cm"] = _optimized_port_diameter_cm(
            driver, result, box.vp_l, box.fp_hz, 1.43, "lower")
    elif isinstance(box, _acoustics.Bandpass8Box):
        result = _acoustics.simulate_bandpass8(driver, box, freq, voltage_v)
        st.session_state["bp8_dp1_cm"] = _optimized_port_diameter_cm(
            driver, result, box.v1_l, box.f1_hz, 1.43, "lower")
        st.session_state["bp8_dp2_cm"] = _optimized_port_diameter_cm(
            driver, result, box.v2_l, box.f2_hz, 1.43, "lower")
        st.session_state["bp8_dp3_cm"] = _optimized_port_diameter_cm(
            driver, result, box.v3_l, box.f3_hz, 1.43, "upper")
    else:
        result = _acoustics.simulate(driver, box, freq, voltage_v)
        st.session_state["box_port_d_h_cm"] = _optimized_port_diameter_cm(
            driver, result, box.vh_l, box.fh_hz, 1.64, "upper")
        st.session_state["box_port_d_l_cm"] = _optimized_port_diameter_cm(
            driver, result, box.vl_l, box.fl_hz, 1.43, "lower")


def _optimized_summary(optimized: _acoustics.OptimizedAlignment) -> str:
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
    box: _acoustics.DccavBox | _acoustics.ReflexBox | _acoustics.Bandpass4Box | _acoustics.Bandpass6Box | _acoustics.Bandpass8Box | _acoustics.SealedBox,
) -> tuple:
    if isinstance(box, _acoustics.ReflexBox):
        return ("reflex", box.vb_l, box.fb_hz, box.q_abs, box.q_leak, box.q_port)
    if isinstance(box, _acoustics.SealedBox):
        return ("sealed", box.vb_l, box.q_abs, box.q_leak)
    if isinstance(box, _acoustics.Bandpass4Box):
        return (
            "bandpass4", box.vs_l, box.vp_l, box.fp_hz,
            box.q_abs_s, box.q_abs_p, box.q_leak_s, box.q_leak_p, box.q_port,
        )
    if isinstance(box, _acoustics.Bandpass6Box):
        return (
            "bandpass6", box.vr_l, box.fr_hz, box.vp_l, box.fp_hz,
            box.q_abs_r, box.q_abs_p, box.q_leak_r, box.q_leak_p,
            box.q_port_r, box.q_port_p,
        )
    if isinstance(box, _acoustics.Bandpass8Box):
        return (
            "bandpass8", box.v1_l, box.f1_hz, box.v2_l, box.f2_hz, box.v3_l, box.f3_hz,
            box.q_abs_1, box.q_abs_2, box.q_abs_3,
            box.q_leak_1, box.q_leak_2, box.q_leak_3,
            box.q_port_1, box.q_port_2, box.q_port_3,
        )
    return (
        "dccav", box.vh_l, box.fh_hz, box.vl_l, box.fl_hz,
        box.q_abs_h, box.q_abs_l, box.q_leak_h, box.q_leak_l,
        box.q_port_h, box.q_port_l,
    )


def _optimizer_result_context(
    driver: _acoustics.DriverTS,
    load_type: str,
    box: _acoustics.DccavBox | _acoustics.ReflexBox | _acoustics.Bandpass4Box | _acoustics.Bandpass6Box | _acoustics.Bandpass8Box | _acoustics.SealedBox,
) -> tuple:
    goals = _optimizer_goals_from_state()
    return (
        load_type,
        driver,
        goals,
        round(float(st.session_state.get("sim_voltage", 2.83)), 9),
        _optimizer_box_signature(box),
    )


def _current_optimizer_summary(driver: _acoustics.DriverTS) -> str | None:
    load_type = st.session_state.get("load_type", "DCCAV")
    if load_type == "Bass reflex":
        box = _reflex_box_from_state()
    elif load_type == "Sealed":
        box = _sealed_box_from_state()
    elif load_type == "Bandpass 4th order":
        box = _bandpass4_box_from_state()
    elif load_type == "Bandpass 6th order":
        box = _bandpass6_box_from_state()
    elif load_type == "Bandpass 8th order":
        box = _bandpass8_box_from_state()
    elif load_type == "DCCAV":
        box = _box_from_state()
    else:
        return None
    context = _optimizer_result_context(driver, load_type, box)
    if st.session_state.get("_opt_last_context") != context:
        return None
    return st.session_state.get("opt_last_summary")


def _run_box_optimizer(driver: _acoustics.DriverTS) -> _acoustics.OptimizedAlignment:
    load_type = st.session_state.get("load_type", "DCCAV")
    if load_type == "Bass reflex":
        template = _reflex_box_from_state()
    elif load_type == "Sealed":
        template = _sealed_box_from_state()
    elif load_type == "Bandpass 4th order":
        template = _bandpass4_box_from_state()
    elif load_type == "Bandpass 6th order":
        template = _bandpass6_box_from_state()
    elif load_type == "Bandpass 8th order":
        template = _bandpass8_box_from_state()
    elif load_type == "Infinite baffle":
        raise ValueError("Infinite baffle has no box to optimize")
    else:
        template = _box_from_state()
    optimized = _acoustics.optimize_alignment(
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


def _apply_suggested_box_for(driver: _acoustics.DriverTS):
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


def _apply_empirical_box_for(driver: _acoustics.DriverTS) -> None:
    """Apply the lightweight starter regardless of the selected strategy."""
    load_type = st.session_state.get("load_type", "DCCAV")
    if load_type == "Bass reflex":
        _apply_reflex_alignment(_acoustics.suggest_reflex_alignment(driver))
    elif load_type == "Sealed":
        _apply_sealed_alignment(_acoustics.suggest_sealed_alignment(driver))
    elif load_type == "Bandpass 4th order":
        _apply_bandpass4_alignment(_acoustics.suggest_bandpass4_alignment(driver))
    elif load_type == "Bandpass 6th order":
        _apply_bandpass6_alignment(_acoustics.suggest_bandpass6_alignment(driver))
    elif load_type == "Bandpass 8th order":
        _apply_bandpass8_alignment(_acoustics.suggest_bandpass8_alignment(driver))
    elif load_type == "DCCAV":
        _apply_alignment(_acoustics.suggest_alignment(driver))


def _on_box_strategy_change() -> None:
    strategy = str(st.session_state.get("box_strategy", "Max extension"))
    previous = str(st.session_state.get("_previous_box_strategy", "Max extension"))
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


def _alignment_warning(ts: _acoustics.DriverTS, box: _acoustics.DccavBox) -> str | None:
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
        return _acoustics.driver_preset_info(name).brand
    except ValueError:
        return "Other"


def _driver_preset_identity_fields(name: str) -> tuple[str, str]:
    """Return the normalized manufacturer and part number shown at runtime."""
    try:
        info = _acoustics.driver_preset_info(name)
    except ValueError:
        return "Other", name
    manufacturer = info.brand.strip() or "Other"
    part_number = info.part_number.strip() or info.model.strip() or name
    return manufacturer, part_number


def _driver_preset_display_label(name: str) -> str:
    """Format a catalog key without exposing its source-decorated raw name."""
    manufacturer, part_number = _driver_preset_identity_fields(name)
    if manufacturer.casefold() == part_number.casefold():
        return manufacturer
    return f"{manufacturer} — {part_number}"


def _driver_preset_source(name: str) -> str:
    try:
        return _acoustics.driver_preset_provenance_category(name)
    except ValueError:
        return "Load Forge database"


def _render_driver_mechanical_drawing(
    mechanical: _presets.MechanicalDimensions | None,
) -> None:
    """Render a compact, mobile-safe front/side driver envelope drawing."""
    if mechanical is None:
        st.caption("Mechanical dimensions not published for this driver.")
        return
    values = {
        "Overall Ø": mechanical.overall_diameter_mm,
        "Cutout Ø": mechanical.cutout_diameter_mm,
        "Depth": mechanical.depth_mm,
        "Bolt circle": mechanical.bolt_circle_mm,
        "Weight": mechanical.weight_kg,
    }
    shown = {label: value for label, value in values.items() if value is not None}
    if not shown:
        st.caption("Mechanical dimensions not published for this driver.")
        return
    metrics = st.columns(min(3, len(shown)))
    for column, (label, value) in zip(metrics * ((len(shown) + 2) // 3), shown.items()):
        unit = "kg" if label == "Weight" else "mm"
        column.metric(label, f"{value:.1f} {unit}")
    overall = mechanical.overall_diameter_mm or 100.0
    cutout = mechanical.cutout_diameter_mm or overall * 0.85
    scale = 150.0 / max(overall, 1.0)
    outer_r = overall * scale / 2.0
    inner_r = cutout * scale / 2.0
    st.markdown(
        f'''<div style="max-width:360px;margin:.6rem auto 0;text-align:center">
        <svg viewBox="0 0 360 210" width="100%" role="img" aria-label="Driver mechanical drawing">
          <rect x="1" y="1" width="358" height="208" rx="10" fill="#080b10" stroke="#26313d"/>
          <circle cx="105" cy="105" r="{outer_r:.1f}" fill="#151c25" stroke="#10b981" stroke-width="3"/>
          <circle cx="105" cy="105" r="{inner_r:.1f}" fill="#080b10" stroke="#f2c14e" stroke-width="2" stroke-dasharray="5 4"/>
          <line x1="{105-outer_r:.1f}" y1="180" x2="{105+outer_r:.1f}" y2="180" stroke="#b8c2cc"/>
          <text x="105" y="198" fill="#b8c2cc" text-anchor="middle" font-size="12">overall Ø / cutout Ø</text>
          <rect x="220" y="55" width="70" height="100" rx="4" fill="#151c25" stroke="#10b981" stroke-width="3"/>
          <line x1="305" y1="55" x2="305" y2="155" stroke="#f2c14e"/>
          <text x="310" y="110" fill="#b8c2cc" font-size="12" transform="rotate(90 310 110)">depth</text>
        </svg></div>''',
        unsafe_allow_html=True,
    )


def _driver_preset_exact_source(name: str) -> str:
    try:
        return _acoustics.driver_preset_info(name).source
    except ValueError:
        return "Built-in"


def _driver_class_label(value: str) -> str:
    """Return the compact class label shown throughout the UI."""
    return _PRESET_CLASS_FILTER_ALIASES.get(str(value), str(value))


def _driver_preset_price(name: str) -> float | None:
    try:
        return _acoustics.driver_preset_info(name).price
    except ValueError:
        return None


def _driver_preset_currency(name: str) -> str:
    try:
        return _acoustics.driver_preset_info(name).currency
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


@lru_cache(maxsize=8)
def _all_preset_price_currencies() -> list[str]:
    return sorted(
        {
            _driver_preset_currency(name)
            for name in _acoustics.driver_preset_names()
            if _driver_preset_price(name) is not None and _driver_preset_currency(name)
        }
    )


def _preset_price_currencies(names: list[str]) -> list[str]:
    all_names = _acoustics.driver_preset_names()
    if len(names) == len(all_names):
        return _all_preset_price_currencies()
    return sorted(
        {
            _driver_preset_currency(name)
            for name in names
            if _driver_preset_price(name) is not None and _driver_preset_currency(name)
        }
    )


@lru_cache(maxsize=16)
def _all_preset_price_values(currency: str | None = None) -> list[float]:
    values = []
    rates = _current_exchange_rates()[0] if currency else None
    for name in _acoustics.driver_preset_names():
        price = (
            _normalized_preset_price(name, currency, rates)
            if currency
            else _driver_preset_price(name)
        )
        if price is not None and np.isfinite(float(price)):
            values.append(float(price))
    return values


def _preset_price_values(names: list[str], currency: str | None = None) -> list[float]:
    all_names = _acoustics.driver_preset_names()
    if len(names) == len(all_names):
        return _all_preset_price_values(currency)
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


def _purchase_markdown(info: _acoustics.DriverPresetInfo) -> str | None:
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
        info = _acoustics.driver_preset_info(name)
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
        driver = _acoustics.get_driver_preset(name)
    except ValueError:
        return "Other"
    piston_diameter_mm = float(np.sqrt(driver.sd_cm2 / 10_000.0 * 4.0 / np.pi) * 1000.0)
    piston_inches = piston_diameter_mm / 25.4
    return _size_bucket(piston_inches)


@lru_cache(maxsize=8)
def _all_available_preset_families() -> list[str]:
    names = _acoustics.driver_preset_names()
    present = {_driver_preset_family(name) for name in names}
    ordered = [family for family in _PRESET_FAMILY_ORDER if family == "All" or family in present]
    extras = sorted(present.difference(ordered), key=str.casefold)
    return [*ordered, *extras]


def _available_preset_families(names: list[str]) -> list[str]:
    all_names = _acoustics.driver_preset_names()
    if len(names) == len(all_names):
        return _all_available_preset_families()
    present = {_driver_preset_family(name) for name in names}
    ordered = [family for family in _PRESET_FAMILY_ORDER if family == "All" or family in present]
    extras = sorted(present.difference(ordered), key=str.casefold)
    return [*ordered, *extras]


def _set_filter_group_from_all(all_key: str, item_keys: tuple[str, ...]) -> None:
    """Apply the All checkbox value to every concrete option in a group."""
    selected = bool(st.session_state.get(all_key, False))
    for item_key in item_keys:
        st.session_state[item_key] = selected


def _sync_filter_group_all(all_key: str, item_keys: tuple[str, ...]) -> None:
    """Turn All on only when every concrete option is selected."""
    st.session_state[all_key] = bool(item_keys) and all(
        bool(st.session_state.get(item_key, False))
        for item_key in item_keys
    )


def _sync_filter_multiselect(
    filter_key: str,
    widget_key: str,
    synced_key: str,
) -> None:
    """Store a compact multiselect as the existing project filter format."""
    selected = [str(value) for value in st.session_state.get(widget_key, [])]
    aggregate = selected or ["All"]
    st.session_state[filter_key] = aggregate
    st.session_state[synced_key] = tuple(aggregate)


def _render_finder_library_filters(all_preset_names: list[str]) -> None:
    """Render Finder library filters."""
    st.text_input(
        "Search preset",
        key="preset_search",
        placeholder="Manufacturer or part number",
    )
    filter_options = (
        ("preset_source_filter", "Provenance", list(_PRESET_SOURCE_FILTERS)),
        (
            "preset_family_filter",
            "Manufacturer",
            _available_preset_families(all_preset_names),
        ),
        ("preset_size_filter", "Size", list(_PRESET_SIZE_FILTERS)),
        ("preset_class_filter", "Class", list(_PRESET_CLASS_FILTERS)),
    )
    for key, label, options in filter_options:
        raw_current = st.session_state.get(key, ["All"])
        current = [raw_current] if isinstance(raw_current, str) else list(raw_current)
        if key == "preset_source_filter":
            current = [
                _PRESET_SOURCE_FILTER_ALIASES.get(str(option), str(option))
                for option in current
            ]
        elif key == "preset_class_filter":
            current = [
                _PRESET_CLASS_FILTER_ALIASES.get(str(option), str(option))
                for option in current
            ]
        concrete_options = [option for option in options if option != "All"]
        selected = (
            []
            if not current or "All" in current or _PRESET_FILTER_NONE in current
            else [option for option in current if option in concrete_options]
        )
        widget_key = f"{key}__select_v5"
        synced_key = f"{widget_key}__aggregate"
        requested_state = tuple(selected or ["All"])
        if st.session_state.get(synced_key) != requested_state:
            st.session_state[widget_key] = selected
            st.session_state[synced_key] = requested_state
        selected = st.multiselect(
            label,
            concrete_options,
            key=widget_key,
            placeholder="All",
            on_change=_sync_filter_multiselect,
            args=(key, widget_key, synced_key),
            help="Leave empty to include every option.",
        )
        aggregate = [str(value) for value in selected] or ["All"]
        st.session_state[key] = aggregate
        st.session_state[synced_key] = tuple(aggregate)

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
    source: str | list[str],
    family: str | list[str],
    size: str | list[str],
    search: str,
    max_price: float | None = None,
    max_price_currency: str | None = None,
    selected: str | None = None,
    driver_class: str | list[str] = "All",
    max_mms_g: float | None = None,
    max_le_mh: float | None = None,
) -> list[str]:
    def selected_values(value: str | list[str]) -> set[str]:
        values = {str(item) for item in ([value] if isinstance(value, str) else value)}
        return set() if not values or "All" in values else values

    source_values = {
        _PRESET_SOURCE_FILTER_ALIASES.get(value, value)
        for value in selected_values(source)
    }
    family_values = selected_values(family)
    size_values = selected_values(size)
    class_values = {
        _PRESET_CLASS_ENGINE_VALUES.get(value, value)
        for value in selected_values(driver_class)
    }
    query = search.strip().casefold()
    # The default view has no active filters.  Avoid touching every preset's
    # metadata on the first Streamlit run; names remain server-side and the
    # visible table is capped/paginated later.
    if not (
        source_values or family_values or size_values or class_values or query
        or max_price is not None or max_mms_g is not None or max_le_mh is not None
    ):
        return list(names)
    rates = _current_exchange_rates()[0] if max_price is not None else None
    filtered = []
    for name in names:
        if source_values and _driver_preset_source(name) not in source_values:
            continue
        if family_values and _driver_preset_family(name) not in family_values:
            continue
        if size_values and _driver_preset_size(name) not in size_values:
            continue
        if class_values and _driver_preset_class(name) not in class_values:
            continue
        if query:
            manufacturer, part_number = _driver_preset_identity_fields(name)
            searchable = " ".join((name, manufacturer, part_number)).casefold()
            if query not in searchable:
                continue
        if max_mms_g is not None or max_le_mh is not None:
            try:
                driver = _acoustics.get_driver_preset(name)
            except Exception:
                continue
            if max_mms_g is not None:
                mms_g = driver.mms_g
                if (
                    mms_g is None
                    or not np.isfinite(float(mms_g))
                    or float(mms_g) <= 0.0
                    or float(mms_g) > float(max_mms_g)
                ):
                    continue
            if max_le_mh is not None:
                le_mh = driver.le_mh
                if (
                    not np.isfinite(float(le_mh))
                    or float(le_mh) <= 0.0
                    or float(le_mh) > float(max_le_mh)
                ):
                    continue
        if max_price is not None:
            price = _normalized_preset_price(name, str(max_price_currency or ""), rates)
            if price is None or float(price) > float(max_price):
                continue
        filtered.append(name)
    if selected and selected != "Custom" and selected in names and selected not in filtered:
        filtered.insert(0, selected)
    return filtered


def _sync_finder_library_selection(filtered_preset_names: list[str]) -> None:
    """Drop table row selections that belong to a previous filtered pool."""
    state = st.session_state.get("finder_driver_library_table")
    if not isinstance(state, dict):
        return
    shown_count = min(len(filtered_preset_names), _LIBRARY_TABLE_MAX_ROWS)
    selection = state.get("selection")
    if not isinstance(selection, dict):
        return
    rows = selection.get("rows", [])
    valid_rows = [
        row for row in rows
        if isinstance(row, int) and 0 <= row < shown_count
    ]
    if valid_rows != rows:
        state["selection"] = {**selection, "rows": valid_rows}
        st.session_state["finder_driver_library_table"] = state


def _driver_preset_class(name: str) -> str:
    # functools.cache would restart cold on every Streamlit rerun (this whole
    # script is re-executed, redefining the function); the session_state dict
    # survives reruns so the 10k-preset catalog is classified once per session.
    class_cache = st.session_state.setdefault("_driver_class_cache", {})
    cached = class_cache.get(name)
    if cached is None:
        try:
            cached = _acoustics.classify_driver_bandwidth(
                _acoustics.get_driver_preset(name)).driver_class
        except Exception:
            cached = "Woofer"
        class_cache[name] = cached
    return cached


def _apply_driver_preset(driver: _acoustics.DriverTS):
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


def _auto_alignment_signature(driver: _acoustics.DriverTS | None = None) -> tuple:
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


def _mark_auto_alignment_synced(driver: _acoustics.DriverTS | None = None):
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


def _initialize_alignment_defaults() -> None:
    """Seed enclosure fields once instead of recomputing five alignments per click."""
    default_groups = (
        (
            ("box_vh_l", "vh_l"), ("box_fh_hz", "fh_hz"),
            ("box_vl_l", "vl_l"), ("box_fl_hz", "fl_hz"),
            _acoustics.suggest_alignment,
            _acoustics.DccavAlignment(3.1, 162.0, 6.25, 62.0, 51.5),
        ),
        (
            ("reflex_vb_l", "vb_l"), ("reflex_fb_hz", "fb_hz"),
            _acoustics.suggest_reflex_alignment,
            _acoustics.ReflexAlignment(11.52, 48.14),
        ),
        (
            ("bandpass4_vs_l", "vs_l"), ("bandpass4_vp_l", "vp_l"),
            ("bandpass4_fp_hz", "fp_hz"),
            _acoustics.suggest_bandpass4_alignment,
            _acoustics.Bandpass4Alignment(4.09, 11.52, 94.0),
        ),
        (
            ("bandpass6_vr_l", "vr_l"), ("bandpass6_fr_hz", "fr_hz"),
            ("bandpass6_vp_l", "vp_l"), ("bandpass6_fp_hz", "fp_hz"),
            _acoustics.suggest_bandpass6_alignment,
            _acoustics.Bandpass6Alignment(4.09, 60.0, 11.52, 94.0),
        ),
        (
            ("sealed_vb_l", "vb_l"),
            _acoustics.suggest_sealed_alignment,
            _acoustics.SealedAlignment(11.52, 68.1, 0.512),
        ),
    )
    if all(
        state_key in st.session_state
        for group in default_groups
        for item in group[:-2]
        for state_key in (item[0],)
    ):
        return
    try:
        driver = _driver_from_state()
    except Exception:
        driver = None
    for group in default_groups:
        fields, suggest, fallback = group[:-2], group[-2], group[-1]
        if all(state_key in st.session_state for state_key, _attr in fields):
            continue
        try:
            alignment = suggest(driver) if driver is not None else fallback
        except Exception:
            alignment = fallback
        for state_key, attr in fields:
            _default(state_key, float(getattr(alignment, attr)))


def _on_driver_preset_change():
    preset_name = st.session_state.get("driver_preset_name", "Custom")
    if preset_name == "Custom":
        st.session_state.pop("_admin_catalog_source_preset", None)
        return
    try:
        _apply_driver_preset(_acoustics.get_driver_preset(preset_name))
        st.session_state["_admin_catalog_source_preset"] = preset_name
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
    # Keep the source identity for the administrator's explicit catalog-save
    # action even though edited parameters make this a Custom design.
    current_preset = str(st.session_state.get("driver_preset_name", "Custom"))
    if current_preset != "Custom":
        st.session_state["_admin_catalog_source_preset"] = current_preset
    st.session_state["driver_preset_name"] = "Custom"
    _auto_align_current_driver()


def _on_load_type_change():
    _auto_align_current_driver()


def _on_pr_preset_change():
    """Apply a catalogued passive radiator to the editable PR fields."""
    name = str(st.session_state.get("pr_preset_name", "Custom"))
    if name == "Custom":
        return
    pr = _acoustics.get_passive_radiator_preset(name)
    for key, value in (
        ("pr_sp_cm2", pr.sp_cm2),
        ("pr_fp_hz", pr.fp_hz),
        ("pr_qmp", pr.qmp),
        ("pr_mmp_g", pr.mmp_g),
        ("pr_xmax_mm", pr.xmax_mm),
        ("pr_added_mass_g", 0.0),
    ):
        st.session_state[key] = value


def _apply_pr_combo(name: str, count: int, added_mass_g: float) -> None:
    """Apply a matched plausible PR combination to Box Design."""
    pr = _acoustics.get_passive_radiator_preset(name)
    st.session_state["pr_preset_name"] = name
    st.session_state["pr_sp_cm2"] = float(pr.sp_cm2 * count)
    st.session_state["pr_fp_hz"] = float(pr.fp_hz)
    st.session_state["pr_qmp"] = float(pr.qmp)
    st.session_state["pr_mmp_g"] = float(pr.mmp_g * count)
    st.session_state["pr_xmax_mm"] = float(pr.xmax_mm)
    st.session_state["pr_added_mass_g"] = float(added_mass_g * count)


def _series_frame(result: _acoustics.SimulationResult, series: dict[str, np.ndarray]) -> pd.DataFrame:
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
    return pd.DataFrame(rows, columns=("frequency_hz", "series", "value"))


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


def _active_design_comparison_color() -> str | None:
    """Return the active design's permanent comparison color, when present."""
    active_id = str(st.session_state.get("design_comparison_active_id", ""))
    tabs = st.session_state.get("design_comparison_tabs", [])
    if not active_id or not isinstance(tabs, list):
        return None
    for index, tab in enumerate(tabs):
        if not isinstance(tab, dict) or str(tab.get("id", "")) != active_id:
            continue
        return str(
            tab.get("color")
            or _DESIGN_COMPARISON_TRACE_COLORS[
                index % len(_DESIGN_COMPARISON_TRACE_COLORS)
            ]
        )
    return None


def _active_design_visible() -> bool:
    """Return whether the active comparison or standalone design is plotted."""
    tabs = st.session_state.get("design_comparison_tabs", [])
    if not isinstance(tabs, list) or not tabs:
        return bool(st.session_state.get("standalone_design_visible", True))
    active_id = str(st.session_state.get(
        "design_comparison_active_id",
        tabs[0].get("id", "") if isinstance(tabs[0], dict) else "",
    ))
    for tab in tabs:
        if isinstance(tab, dict) and str(tab.get("id", "")) == active_id:
            return bool(tab.get("visible", True))
    return True


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
    color_overrides: dict[str, str] | None = None,
) -> alt.Chart:
    if not legend and default_visible is not None:
        data = data[data["series"].isin(default_visible)]
    
    series_names = list(dict.fromkeys(data["series"].tolist()))
    color_overrides = color_overrides or {}
    color_scale = alt.Scale(
        domain=series_names,
        range=[
            color_overrides.get(
                name,
                _TRACE_COLORS.get(name, "#7cc7ff"),
            )
            for name in series_names
        ],
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


def _response_series(result: _acoustics.SimulationResult) -> dict[str, np.ndarray]:
    series = {}
    load_type = st.session_state.get("load_type", "DCCAV")
    series["Total"] = result.spl_total_db
    series["Cone"] = result.spl_driver_db
    if load_type in {
        "DCCAV", "Bass reflex", "Bandpass 4th order", "Bandpass 6th order", "Bandpass 8th order",
    }:
        if load_type == "Bass reflex" and _reflex_uses_passive_radiator():
            label = "Passive radiator"
        elif load_type == "Bandpass 8th order":
            label = "Port 3"
        else:
            label = "Vent" if load_type in {"Bass reflex", "Bandpass 4th order"} else "Lower port"
        series[label] = result.spl_port_db
    if not st.session_state.get("plot_compare_loads", False):
        # Keep the MIL/MOL buttons always visible as an affordance; with Pe=0
        # both curves are NaN so the chart layers simply stay empty instead of
        # plotting a bogus excursion-only MIL (see _plot_response/_limit_curves).
        series["MOL"] = result.mol_db
        series["MIL"] = result.mil_w
    return series


def _response_tuning_markers() -> list[tuple[str, float]]:
    """Return the active enclosure tuning frequencies for the response plot."""
    load_type = str(st.session_state.get("load_type", "DCCAV"))
    if load_type == "Bass reflex":
        if _reflex_uses_passive_radiator():
            return [("PR tuning", _acoustics.passive_radiator_effective_fp_hz(_pr_box_from_state()))]
        return [("Reflex tuning", float(st.session_state["reflex_fb_hz"]))]
    if load_type == "Bandpass 4th order":
        return [("Front tuning", float(st.session_state["bandpass4_fp_hz"]))]
    if load_type == "Bandpass 6th order":
        return [
            ("Rear tuning", float(st.session_state["bandpass6_fr_hz"])),
            ("Front tuning", float(st.session_state["bandpass6_fp_hz"])),
        ]
    if load_type == "Bandpass 8th order":
        return [
            ("F1 (Front)", float(st.session_state["bp8_f1_hz"])),
            ("F2 (Rear)", float(st.session_state["bp8_f2_hz"])),
            ("F3 (Radiating)", float(st.session_state["bp8_f3_hz"])),
        ]
    if load_type == "DCCAV":
        return [
            ("Upper tuning", float(st.session_state["box_fh_hz"])),
            ("Lower tuning", float(st.session_state["box_fl_hz"])),
        ]
    return []


def _tuning_marker_layer(
    frequency_window: list[float] | None,
) -> alt.Chart | None:
    """Draw labelled vertical rules for tuning frequencies in the visible window."""
    rows = []
    for label, frequency_hz in _response_tuning_markers():
        if not np.isfinite(frequency_hz) or frequency_hz <= 0.0:
            continue
        if frequency_window and not (
            float(frequency_window[0]) <= frequency_hz <= float(frequency_window[1])
        ):
            continue
        rows.append({"frequency_hz": frequency_hz, "label": label})
    if not rows:
        return None
    data = pd.DataFrame(rows)
    rules = alt.Chart(data).mark_rule(
        color="#f2c14e", strokeDash=[5, 4], strokeWidth=1.6,
    ).encode(
        x=alt.X("frequency_hz:Q", scale=_log_frequency_scale(frequency_window)),
        tooltip=[
            alt.Tooltip("label:N", title="Tuning"),
            alt.Tooltip("frequency_hz:Q", title="Hz", format=".1f"),
        ],
    )
    labels = alt.Chart(data).mark_text(
        color="#f2c14e", angle=90, align="left", baseline="middle", dx=5,
    ).encode(
        x=alt.X("frequency_hz:Q", scale=_log_frequency_scale(frequency_window)),
        y=alt.value(12),
        text="label:N",
    )
    return rules + labels


def _response_y_domain(
    result: _acoustics.SimulationResult,
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


def _port_series(
    result: _acoustics.SimulationResult,
    mode: str = "volume_velocity",
) -> dict[str, np.ndarray]:
    series = {}
    load_type = st.session_state.get("load_type", "DCCAV")
    if load_type not in {"DCCAV", "Bass reflex", "Bandpass 4th order", "Bandpass 6th order", "Bandpass 8th order"}:
        return series

    def _to_air_velocity(u_arr: np.ndarray, d_cm: float, port_key: str) -> np.ndarray:
        if d_cm <= 0.0:
            return np.zeros_like(u_arr, dtype=float)
        area_cm2 = np.pi * (d_cm / 2.0) ** 2
        return _acoustics.port_air_velocity_ms(
            result, area_cm2, port_key, at_mol=(mode == "air_velocity_mol")
        )

    if load_type == "Bandpass 8th order":
        if st.session_state.get("plot_port_p1", True):
            if mode == "volume_velocity":
                series["Port 1 (Front)"] = result.port_l_velocity
            else:
                d1 = float(st.session_state.get("bp8_dp1_cm", 0.0))
                series["Port 1 (Front)"] = _to_air_velocity(result.port_l_velocity, d1, "lower")
        if st.session_state.get("plot_port_lower", True):
            if mode == "volume_velocity":
                series["Port 3 (Radiating)"] = result.port_h_velocity
            else:
                d3 = float(st.session_state.get("bp8_dp3_cm", 0.0))
                series["Port 3 (Radiating)"] = _to_air_velocity(result.port_h_velocity, d3, "upper")
        return series
    if st.session_state.get("plot_port_upper", True) and load_type in ("DCCAV", "Bandpass 6th order"):
        label = "Upper port" if load_type == "DCCAV" else "Rear port"
        if mode == "volume_velocity":
            series[label] = result.port_h_velocity
        else:
            d_up = float(st.session_state.get("box_port_d_h_cm" if load_type == "DCCAV" else "bandpass6_port_d_r_cm", 0.0))
            series[label] = _to_air_velocity(result.port_h_velocity, d_up, "upper")
    if st.session_state.get("plot_port_lower", True):
        is_pr = load_type == "Bass reflex" and _reflex_uses_passive_radiator()
        if is_pr:
            label = "Passive radiator"
        else:
            label = "Vent" if load_type in {"Bass reflex", "Bandpass 4th order"} else "Lower port"
        if mode == "volume_velocity":
            series[label] = result.port_l_velocity
        else:
            if is_pr:
                pr_sp_cm2 = float(st.session_state.get("pr_sp_cm2", 0.0))
                if pr_sp_cm2 > 0.0:
                    series[label] = _acoustics.port_air_velocity_ms(
                        result, pr_sp_cm2, "lower", at_mol=(mode == "air_velocity_mol")
                    )
                else:
                    series[label] = np.zeros_like(result.port_l_velocity, dtype=float)
            else:
                if load_type == "DCCAV":
                    d_low = float(st.session_state.get("box_port_d_l_cm", 0.0))
                elif load_type == "Bandpass 4th order":
                    d_low = float(st.session_state.get("bandpass4_port_d_cm", 0.0))
                elif load_type == "Bandpass 6th order":
                    d_low = float(st.session_state.get("bandpass6_port_d_p_cm", 0.0))
                else:
                    d_low = float(st.session_state.get("reflex_port_d_cm", 0.0))
                series[label] = _to_air_velocity(result.port_l_velocity, d_low, "lower")
    return series


def _cursor_rows(
    result: _acoustics.SimulationResult,
    thresholds: dict[int, float],
    max_freq_hz: float | None = None,
) -> list[dict]:
    rows = []
    auto_markers = set(st.session_state.get("cursor_auto_markers", _AUTO_CURSOR_OPTIONS))
    for key, label in ((3, "F3"), (6, "F6"), (10, "F10")):
        freq_val = thresholds.get(key, float("nan"))
        if label in auto_markers and np.isfinite(freq_val):
            if max_freq_hz is None or max_freq_hz <= 0 or freq_val <= float(max_freq_hz) + 1e-6:
                rows.append(_cursor_row(result, label, freq_val))
    return rows


def _marker_display_label(row: dict, show_mol: bool) -> str:
    """Keep automatic threshold labels compact; details remain in tooltips."""
    label = f"{row['label']} · {float(row['frequency_hz']):.1f} Hz"
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
        label_row["label_y_db"] = top - span * (0.04 + lane * 0.065)
        out.append(label_row)
    return out


def _cursor_row(result: _acoustics.SimulationResult, label: str, frequency_hz: float) -> dict:
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
            range=["#ffd166", "#f77f00", "#10b981"],
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
        fontSize=12,
        fontWeight=600,
        stroke="#0b1018",
        strokeWidth=3,
        strokeOpacity=0.85,
    ).encode(
        x=alt.value(14),
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
        fontSize=12,
        fontWeight=600,
    ).encode(
        x=alt.value(14),
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
    result: _acoustics.SimulationResult,
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
    # Do not inherit the point's y encoding: a rule with y=spl_total_db starts
    # at the curve instead of spanning the complete plot height.
    rule = alt.Chart(marker_data).encode(
        x=alt.X("frequency_hz:Q", scale=_log_frequency_scale(x_domain)),
    ).mark_rule(color="#06d6a0", strokeWidth=2.0).transform_filter(click_marker)
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
    band: _acoustics.ToleranceBand,
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
    design_color = _active_design_comparison_color()
    return alt.Chart(data).mark_area(
        opacity=0.22,
        color=design_color or _TRACE_COLORS["Total"],
        clip=True,
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
    result: _acoustics.SimulationResult,
    cursor_rows: list[dict],
    series_override: dict[str, np.ndarray] | None = None,
    band: _acoustics.ToleranceBand | None = None,
    frequency_window: list[float] | None = None,
    show_legend: bool = False,
    default_visible: list[str] | None = None,
) -> alt.Chart:
    series = dict(series_override if series_override else _response_series(result))
    mil_w_data = series.pop("MIL", None)
    active_design_visible = _active_design_visible()
    visible_response_traces = (
        set(default_visible) if default_visible is not None else None
    )
    mil_overlaid = False
    
    db_series_to_plot = series if series else {"Total": result.spl_total_db}
    
    data = _series_frame(
        result,
        db_series_to_plot if active_design_visible else {},
    )
    y_domain = _response_y_domain(result, db_series_to_plot, frequency_window)
    y_domain = _expand_y_domain_for_pins(
        y_domain,
        frequency_window,
        visible_response_traces,
    )
    if active_design_visible and band is not None and y_domain is not None:
        finite_upper = np.asarray(band.upper_db, dtype=float)
        finite_upper = finite_upper[np.isfinite(finite_upper)]
        if finite_upper.size:
            y_domain[1] = max(y_domain[1], float(np.max(finite_upper)) + 2.0)
    chart = _line_chart(
        data,
        "LF pressure estimate (dB)",
        height=420,
        legend=show_legend,
        x_domain=frequency_window,
        y_domain=y_domain,
        y_axis=_response_amplitude_axis(),
        default_visible=default_visible,
        color_overrides=(
            {"Total": active_color}
            if (active_color := _active_design_comparison_color())
            else None
        ),
    )
    
    if (
        mil_w_data is not None
        and (default_visible is None or "MIL" in default_visible)
        and np.any(np.isfinite(mil_w_data))
    ):
        mil_data = _series_frame(
            result,
            {"MIL": mil_w_data} if active_design_visible else {},
        ).rename(columns={"value": "mil_value"})
        finite_mil = mil_w_data[np.isfinite(mil_w_data)]
        mil_max = float(np.max(finite_mil))
        pinned_mil_data, _ = _pinned_metric_frame("mil_w")
        if not pinned_mil_data.empty:
            mil_max = max(mil_max, float(pinned_mil_data["value"].max()))
        mil_y_domain = [0.0, max(1.0, mil_max * 1.05)]
        
        mil_chart = _line_chart(
            mil_data,
            "Max input power (W)",
            height=420,
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
        pinned_mil = _pinned_metric_layer(
            "mil_w",
            "Max input power (W)",
            ".3f",
            x_domain=frequency_window,
            y_domain=mil_y_domain,
            y_axis=alt.Axis(
                orient="right",
                titleColor=_TRACE_COLORS.get("MIL", "#e0aaff"),
                labelColor=_TRACE_COLORS.get("MIL", "#e0aaff"),
            ),
            show_legend=show_legend,
        )
        if pinned_mil is not None:
            mil_chart = (mil_chart + pinned_mil).resolve_scale(
                color="independent",
                strokeDash="independent",
            )
        chart = alt.layer(chart, mil_chart).resolve_scale(y="independent")
        mil_overlaid = True

    if active_design_visible and band is not None:
        band_area = _band_layer(band, y_domain, frequency_window)
        if band_area is not None:
            chart = band_area + chart
    show_mol = "MOL" in series
    if active_design_visible:
        if st.session_state.get("plot_show_tuning_markers", True):
            tuning_markers = _tuning_marker_layer(frequency_window)
            if tuning_markers is not None:
                chart = chart + tuning_markers
        chart = chart + _click_marker_layer(
            result, frequency_window, y_domain, show_mol=show_mol
        )
    pinned = _pinned_layer(
        frequency_window,
        y_domain,
        show_legend=show_legend,
        selected_traces=visible_response_traces,
    )
    if pinned is not None:
        chart = chart + pinned
    cursors = _cursor_layer(
        cursor_rows, y_domain, frequency_window, show_mol=show_mol, show_legend=show_legend
    )
    if cursors is not None:
        chart = chart + cursors
    if pinned is not None or cursors is not None:
        resolve_kwargs = dict(color="independent", strokeDash="independent")
        if mil_overlaid:
            # Keep the MIL watts curve on its own right-axis scale; without
            # this, the final resolve would collapse MIL onto the SPL axis
            # and squish the dB traces out of their intended domain.
            resolve_kwargs["y"] = "independent"
        return chart.resolve_scale(**resolve_kwargs)
    return chart


def _plot_excursion(result: _acoustics.SimulationResult, xmax_mm: float) -> alt.Chart:
    active_design_visible = _active_design_visible()
    data = _series_frame(
        result,
        {"Excursion": result.excursion_mm} if active_design_visible else {},
    )
    active_color = _active_design_comparison_color()
    chart = _line_chart(
        data,
        "Excursion (mm)",
        height=285,
        legend=False,
        color_overrides=(
            {"Excursion": active_color} if active_color else None
        ),
    )
    if active_design_visible and xmax_mm > 0:
        xmax_rule = alt.Chart(pd.DataFrame({"xmax_mm": [float(xmax_mm)]})).mark_rule(
            color="#10b981",
            strokeDash=[6, 4],
        ).encode(y="xmax_mm:Q")
        chart = chart + xmax_rule
    pinned = _pinned_metric_layer("excursion_mm", "Excursion (mm)", ".3f")
    if pinned is not None:
        chart = (chart + pinned).resolve_scale(
            color="independent", strokeDash="independent")
    return chart


def _plot_impedance(result: _acoustics.SimulationResult) -> alt.Chart:
    data = _series_frame(
        result,
        {"Impedance": result.impedance_ohm}
        if _active_design_visible()
        else {},
    )
    active_color = _active_design_comparison_color()
    chart = _line_chart(
        data,
        "Impedance (Ω)",
        height=285,
        legend=False,
        color_overrides=(
            {"Impedance": active_color} if active_color else None
        ),
    )
    pinned = _pinned_metric_layer("impedance_ohm", "Impedance (Ω)", ".3f")
    if pinned is not None:
        chart = (chart + pinned).resolve_scale(
            color="independent", strokeDash="independent")
    return chart


def _plot_mil(result: _acoustics.SimulationResult) -> alt.Chart:
    mil_w_data = result.mil_w
    data = _series_frame(
        result,
        {"MIL": mil_w_data} if _active_design_visible() else {},
    ).rename(columns={"value": "mil_value"})
    finite_mil = mil_w_data[np.isfinite(mil_w_data)]
    mil_max = float(np.max(finite_mil)) if finite_mil.size else 1.0
    mil_y_domain = [0.0, max(1.0, mil_max * 1.05)]
    active_color = _active_design_comparison_color()
    chart = _line_chart(
        data,
        "Max input power (W)",
        height=240,
        legend=False,
        y_domain=mil_y_domain,
        y_field="mil_value",
        color_overrides={"MIL": active_color} if active_color else None,
    )
    pinned = _pinned_metric_layer("mil_w", "Max input power (W)", ".3f")
    if pinned is not None:
        chart = (chart + pinned).resolve_scale(
            color="independent", strokeDash="independent")
    return chart


def _pin_label(
    load_type: str,
    box,
    preset: str | None = None,
    config: str | None = None,
) -> str:
    preset = str(
        preset
        if preset is not None
        else st.session_state.get("driver_preset_name", "Custom")
    )
    config = str(
        config
        if config is not None
        else st.session_state.get("driver_config", "Single driver")
    )
    if config != "Single driver":
        preset = f"{preset} ({config})"
    if load_type == "Bass reflex":
        if isinstance(box, _acoustics.PassiveRadiatorBox):
            box_txt = (
                f"Vb {box.vb_l:.1f} L · PR Fp "
                f"{_acoustics.passive_radiator_effective_fp_hz(box):.1f} Hz"
            )
        else:
            box_txt = f"Vb {box.vb_l:.1f} L · Fb {box.fb_hz:.1f} Hz"
    elif load_type == "Bandpass 4th order":
        box_txt = f"Vs {box.vs_l:.1f} L / Vp {box.vp_l:.1f} L · Fp {box.fp_hz:.1f} Hz"
    elif load_type == "Bandpass 6th order":
        box_txt = f"Vr {box.vr_l:.1f} L / Vp {box.vp_l:.1f} L · Fr {box.fr_hz:.1f} Hz / Fp {box.fp_hz:.1f} Hz"
    elif load_type == "Bandpass 8th order":
        box_txt = f"V1 {box.v1_l:.1f} L / V2 {box.v2_l:.1f} L / V3 {box.v3_l:.1f} L · F1 {box.f1_hz:.0f} / F2 {box.f2_hz:.0f} / F3 {box.f3_hz:.0f} Hz"
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
        _snapshot_revision(pin)
    return valid_pins


def _pinned_response_snapshot(
    load_type: str,
    box,
    result: _acoustics.SimulationResult,
    *,
    label: str | None = None,
    color: str | None = None,
) -> dict:
    """Capture every comparable curve independently of later UI changes."""
    response_traces = {
        "Total": [float(v) for v in result.spl_total_db],
        "Cone": [float(v) for v in result.spl_driver_db],
        "MOL": [float(v) for v in result.mol_db],
    }
    if load_type == "DCCAV":
        response_traces["Lower port"] = [
            float(v) for v in result.spl_port_db
        ]
        port_traces = {
            "Upper port": [float(v) for v in result.port_h_velocity],
            "Lower port": [float(v) for v in result.port_l_velocity],
        }
    elif load_type == "Bandpass 6th order":
        response_traces["Lower port"] = [
            float(v) for v in result.spl_port_db
        ]
        port_traces = {
            "Rear port": [float(v) for v in result.port_h_velocity],
            "Front port": [float(v) for v in result.port_l_velocity],
        }
    elif load_type == "Bandpass 8th order":
        response_traces["Port 3"] = [
            float(v) for v in result.spl_port_db
        ]
        port_traces = {
            "Port 3 (Radiating)": [float(v) for v in result.port_h_velocity],
            "Port 1 (Front)": [float(v) for v in result.port_l_velocity],
        }
    elif load_type in {"Bass reflex", "Bandpass 4th order"}:
        port_label = (
            "Passive radiator"
            if isinstance(box, _acoustics.PassiveRadiatorBox)
            else "Vent"
        )
        response_traces[port_label] = [
            float(v) for v in result.spl_port_db
        ]
        port_traces = {
            port_label: [float(v) for v in result.port_l_velocity],
        }
    else:
        port_traces = {}
    snapshot = {
        "_revision": uuid.uuid4().hex,
        "label": label or _pin_label(load_type, box),
        "load_type": load_type,
        "visible": True,
        "frequency_hz": [float(v) for v in result.frequency_hz],
        "spl_total_db": [float(v) for v in result.spl_total_db],
        "response_traces": response_traces,
        "excursion_mm": [float(v) for v in result.excursion_mm],
        "impedance_ohm": [float(v) for v in result.impedance_ohm],
        "mil_w": [float(v) for v in result.mil_w],
        "group_delay_ms": [float(v) for v in _acoustics.group_delay_ms(result)],
        "port_traces": port_traces,
    }
    if color:
        snapshot["color"] = str(color)
    return snapshot


def _update_active_design_comparison(
    load_type: str,
    box,
    result: _acoustics.SimulationResult,
    simulation_signature: str | None = None,
) -> list[dict]:
    """Persist the active editable tab and expose every inactive tab as overlays."""
    tabs = _design_comparison_tabs()
    if not tabs:
        return []
    active_id = str(
        st.session_state.get("design_comparison_active_id", tabs[0]["id"])
    )
    for tab_index, tab in enumerate(tabs):
        if str(tab["id"]) != active_id:
            continue
        current_preset = str(st.session_state.get(
            "driver_preset_name", "Custom"
        ))
        stable_preset = str(tab.get("driver_preset_name", ""))
        display_preset = str(tab.get("display_driver_name", ""))
        parameters = _json_safe(_collect_params())
        driver_signature = _design_driver_parameter_signature(parameters)
        if current_preset != "Custom":
            stable_preset = current_preset
            display_preset = current_preset
            tab["preset_recovery_signature"] = driver_signature
        elif tab.get("preset_recovery_signature") != driver_signature:
            recovered_preset = _recover_design_tab_preset(parameters)
            tab["preset_recovery_signature"] = driver_signature
            if recovered_preset != "Custom":
                stable_preset = recovered_preset
                if not display_preset or display_preset == "Custom":
                    display_preset = recovered_preset
        tab["driver_preset_name"] = stable_preset or "Custom"
        tab["display_driver_name"] = display_preset or stable_preset or "Custom"
        tab["load_type"] = load_type
        tab["visible"] = bool(tab.get("visible", True))
        if stable_preset and stable_preset != "Custom":
            parameters["driver_preset_name"] = stable_preset
        tab["parameters"] = parameters
        tab["label"] = _design_comparison_tab_label(
            tab_index + 1,
            load_type,
            preset=tab["display_driver_name"],
            config=str(parameters.get("driver_config", "Single driver")),
        )
        snapshot = tab.get("snapshot")
        snapshot_is_current = (
            simulation_signature is not None
            and tab.get("simulation_signature") == simulation_signature
            and isinstance(snapshot, dict)
        )
        if not snapshot_is_current:
            snapshot = _pinned_response_snapshot(
                load_type,
                box,
                result,
                label=str(tab.get("label", "Editable design")),
                color=str(tab.get("color", "")) or None,
            )
            tab["snapshot"] = snapshot
            if simulation_signature is not None:
                tab["simulation_signature"] = simulation_signature
        snapshot["label"] = str(tab.get("label", "Editable design"))
        snapshot["color"] = str(tab.get("color", ""))
        snapshot["visible"] = tab["visible"]
        break
    st.session_state["design_comparison_tabs"] = tabs
    st.session_state["design_comparison_loaded_id"] = active_id
    st.session_state["pinned_responses"] = [
        dict(tab["snapshot"])
        for tab in tabs
        if str(tab["id"]) != active_id
        and isinstance(tab.get("snapshot"), dict)
    ]
    return tabs


def _duplicate_active_design_comparison(
    load_type: str,
    box,
    result: _acoustics.SimulationResult,
) -> str:
    """Create an independently editable variant tab from the active design."""
    tabs = _update_active_design_comparison(load_type, box, result)
    if not tabs:
        original_id = f"design_{uuid.uuid4().hex}"
        original_label = _design_comparison_tab_label(1, load_type)
        original_snapshot = _pinned_response_snapshot(
            load_type,
            box,
            result,
            label=original_label,
            color=_DESIGN_COMPARISON_TRACE_COLORS[0],
        )
        tabs = [{
            "id": original_id,
            "label": original_label,
            "color": _DESIGN_COMPARISON_TRACE_COLORS[0],
            "driver_preset_name": str(st.session_state.get(
                "driver_preset_name", "Custom"
            )),
            "display_driver_name": str(st.session_state.get(
                "driver_preset_name", "Custom"
            )),
            "load_type": load_type,
            "visible": True,
            "parameters": _json_safe(_collect_params()),
            "snapshot": original_snapshot,
        }]
        st.session_state["design_comparison_tabs"] = tabs
        st.session_state["design_comparison_active_id"] = original_id
        st.session_state["design_comparison_loaded_id"] = original_id
    active_id = str(st.session_state["design_comparison_active_id"])
    return _duplicate_design_comparison_tab(active_id)


def _duplicate_design_comparison_tab(tab_id: str) -> str:
    """Clone one stored editable tab and activate the independent copy."""
    tabs = _design_comparison_tabs()
    if len(tabs) >= _MAX_COMPARISON_DESIGNS:
        return ""
    source = next(
        item for item in tabs if str(item["id"]) == str(tab_id)
    )
    copy_id = f"design_{uuid.uuid4().hex}"
    source_params = dict(source.get("parameters", {}))
    copy_label = _design_comparison_tab_label(
        len(tabs) + 1,
        str(source_params.get("load_type", st.session_state.get(
            "load_type", "Design"
        ))),
        preset=str(source_params.get(
            "driver_preset_name",
            st.session_state.get("driver_preset_name", "Custom"),
        )),
        config=str(source_params.get(
            "driver_config",
            st.session_state.get("driver_config", "Single driver"),
        )),
    )
    copied_snapshot = dict(source.get("snapshot", {}))
    copied_snapshot["label"] = copy_label
    tabs.append({
        "id": copy_id,
        "label": copy_label,
        "color": _DESIGN_COMPARISON_TRACE_COLORS[
            len(tabs) % len(_DESIGN_COMPARISON_TRACE_COLORS)
        ],
        "driver_preset_name": str(source.get(
            "driver_preset_name",
            source_params.get("driver_preset_name", "Custom"),
        )),
        "display_driver_name": str(source.get(
            "display_driver_name",
            source.get(
                "driver_preset_name",
                source_params.get("driver_preset_name", "Custom"),
            ),
        )),
        "load_type": str(source.get(
            "load_type", source_params.get("load_type", "Design")
        )),
        "visible": True,
        "parameters": _json_safe(dict(source.get("parameters", {}))),
        "snapshot": copied_snapshot,
        "simulation_signature": source.get("simulation_signature"),
    })
    tabs[-1]["snapshot"]["color"] = tabs[-1]["color"]
    tabs[-1]["snapshot"]["visible"] = True
    st.session_state["design_comparison_tabs"] = tabs
    st.session_state["design_comparison_active_id"] = copy_id
    return copy_label


def _duplicate_standalone_design_from_click(
    load_type: str,
    box,
    result: _acoustics.SimulationResult,
) -> None:
    """Create comparison state in the button callback, before the rerun."""
    copy_name = _duplicate_active_design_comparison(load_type, box, result)
    if copy_name:
        st.session_state["_design_tab_action_toast"] = (
            f"Created editable tab: {copy_name}"
        )


def _duplicate_design_tab_from_click(tab_id: str) -> None:
    copy_name = _duplicate_design_comparison_tab(tab_id)
    if copy_name:
        st.session_state["_design_tab_action_toast"] = (
            f"Created editable tab: {copy_name}"
        )


def _delete_active_design_comparison_tab() -> None:
    """Delete the active editable tab; the last design remains standalone."""
    tabs = _design_comparison_tabs()
    if not tabs:
        return
    if len(tabs) == 1:
        _end_design_comparison()
        return
    active_id = str(st.session_state.get("design_comparison_active_id", ""))
    remaining = [item for item in tabs if str(item["id"]) != active_id]
    st.session_state["design_comparison_tabs"] = remaining
    st.session_state["design_comparison_active_id"] = str(remaining[0]["id"])


def _delete_design_comparison_tab(tab_id: str) -> None:
    """Delete a specific editable tab without disturbing another active tab."""
    tabs = _design_comparison_tabs()
    if not tabs:
        return
    if len(tabs) == 1:
        _end_design_comparison()
        return
    remaining = [item for item in tabs if str(item["id"]) != str(tab_id)]
    st.session_state["design_comparison_tabs"] = remaining
    if str(st.session_state.get("design_comparison_active_id", "")) == str(tab_id):
        st.session_state["design_comparison_active_id"] = str(remaining[0]["id"])


def _toggle_design_tab_visible(tab_id: str) -> None:
    """Toggle one design curve without deleting its editable state."""
    if str(tab_id) == "standalone":
        st.session_state["standalone_design_visible"] = not bool(
            st.session_state.get("standalone_design_visible", True)
        )
        return
    tabs = _design_comparison_tabs()
    for tab in tabs:
        if str(tab.get("id", "")) != str(tab_id):
            continue
        visible = not bool(tab.get("visible", True))
        tab["visible"] = visible
        snapshot = tab.get("snapshot")
        if isinstance(snapshot, dict):
            snapshot["visible"] = visible
        break
    st.session_state["design_comparison_tabs"] = tabs


def _end_design_comparison() -> None:
    for key in (
        "design_comparison_tabs",
        "design_comparison_active_id",
        "design_comparison_loaded_id",
    ):
        st.session_state.pop(key, None)
    st.session_state["pinned_responses"] = []


def _design_comparison_tab_colors(
    tabs: list[dict],
) -> dict[str, str]:
    """Return the permanent curve color assigned to each editable design."""
    return {
        str(tab["id"]): str(
            tab.get("color")
            or _DESIGN_COMPARISON_TRACE_COLORS[
                index % len(_DESIGN_COMPARISON_TRACE_COLORS)
            ]
        )
        for index, tab in enumerate(tabs)
    }


def _design_comparison_tab_label(
    number: int,
    load_type: str,
    preset: str | None = None,
    config: str | None = None,
) -> str:
    """Return a compact tab title split into manufacturer, part number,
    load type and driver configuration; alignment details live in results."""
    preset_name = str(
        preset
        if preset is not None
        else st.session_state.get("driver_preset_name", "Custom")
    )
    driver_config = str(
        config
        if config is not None
        else st.session_state.get("driver_config", "Single driver")
    )
    if preset_name == "Custom":
        return f"{number} · {load_type} · {driver_config}"
    manufacturer, part_number = _driver_preset_identity_fields(preset_name)
    return (
        f"{number} · {manufacturer} · {part_number} · "
        f"{load_type} · {driver_config}"
    )


def _design_tab_label_driver(label: str) -> str:
    """Extract a non-Custom driver name from compact and legacy tab labels."""
    parts = [part.strip() for part in str(label).split(" · ")]
    if parts and parts[0].isdigit():
        parts = parts[1:]
    # New compact format: <manufacturer> · <part n.> · <load type> · <config>
    if len(parts) >= 3 and parts[2] in _ALL_LOAD_TYPES:
        candidate = f"{parts[0]} {parts[1]}"
    elif len(parts) >= 2 and parts[0] in _ALL_LOAD_TYPES:
        return ""
    elif len(parts) >= 2 and parts[0].startswith("Variant of "):
        candidate = parts[1]
    elif parts:
        candidate = parts[0]
    else:
        return ""
    return "" if candidate == "Custom" else candidate


def _recover_design_tab_preset(parameters: dict) -> str:
    """Recover a preset name from unchanged T/S values in a legacy tab."""
    for name in _acoustics.driver_preset_names():
        if _design_tab_parameters_match_preset(parameters, name):
            return str(name)
    return "Custom"


def _design_driver_parameter_signature(parameters: dict) -> tuple:
    """Compact identity used to avoid rescanning the catalog on UI clicks."""
    return tuple(
        parameters.get(key)
        for key in (
            "driver_fs_hz",
            "driver_vas_l",
            "driver_qts",
            "driver_qms",
            "driver_re_ohm",
            "driver_sd_cm2",
            "driver_le_mh",
            "driver_xmax_mm",
            "driver_pe_w",
        )
    )


def _design_tab_parameters_match_preset(
    parameters: dict,
    preset_name: str,
) -> bool:
    """Return whether saved driver fields still exactly match one preset."""
    field_map = (
        ("driver_fs_hz", "fs_hz", True),
        ("driver_vas_l", "vas_l", True),
        ("driver_qts", "qts", True),
        ("driver_qms", "qms", True),
        ("driver_re_ohm", "re_ohm", True),
        ("driver_sd_cm2", "sd_cm2", False),
        ("driver_le_mh", "le_mh", False),
        ("driver_xmax_mm", "xmax_mm", False),
        ("driver_pe_w", "pe_w", False),
    )
    if (
        not preset_name
        or preset_name == "Custom"
        or not all(
            state_key in parameters
            for state_key, _driver_field, required in field_map
            if required
        )
    ):
        return False
    try:
        driver = _acoustics.get_driver_preset(preset_name)
    except (TypeError, ValueError):
        return False
    for state_key, driver_field, _required in field_map:
        if state_key not in parameters:
            continue
        try:
            actual = float(parameters[state_key])
            expected = float(getattr(driver, driver_field))
        except (TypeError, ValueError):
            return False
        if not np.isclose(actual, expected, rtol=1e-7, atol=1e-7):
            return False
    return True


def _design_crw_download(tab: dict) -> tuple[bytes, str, str | None]:
    """Build the CRW download for one stored design tab."""
    parameters = tab.get("parameters")
    if tab.get("id") == "standalone":
        parameters = _collect_params()
    if not isinstance(parameters, dict):
        return b"", "load_forge_driver.crw", "This design has no saved parameters."
    try:
        text = _afw_export.generate_crw_text(parameters)
    except Exception as exc:
        return b"", "load_forge_driver.crw", str(exc)
    driver_name = str(
        tab.get("display_driver_name")
        or tab.get("driver_preset_name")
        or "driver"
    )
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", driver_name).strip("._")
    return text.encode("latin-1"), f"{stem or 'load_forge_driver'}.crw", None


def _design_crw_parameters(tab: dict) -> dict:
    parameters = tab.get("parameters")
    if tab.get("id") == "standalone":
        parameters = _collect_params()
    return parameters if isinstance(parameters, dict) else {}


def _design_crw_signature(tab: dict) -> str:
    encoded = json.dumps(
        _design_crw_parameters(tab),
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _prepare_design_crw_download(tab: dict) -> None:
    data, filename, error = _design_crw_download(tab)
    st.session_state["_design_crw_ready"] = {
        "tab_id": str(tab.get("id", "")),
        "signature": _design_crw_signature(tab),
        "data": data,
        "filename": filename,
        "error": error,
    }


def _render_editable_design_tabs(
    tabs: list[dict],
    load_type: str,
    box,
    result: _acoustics.SimulationResult,
) -> None:
    """Render compact editable tabs with actions embedded in the active tab."""
    action_toast = st.session_state.pop("_design_tab_action_toast", None)
    if action_toast:
        st.toast(str(action_toast))
    standalone = not tabs
    if standalone:
        tabs = [{
            "id": "standalone",
            "label": _design_comparison_tab_label(1, load_type),
            "color": _DESIGN_COMPARISON_TRACE_COLORS[0],
            "visible": bool(st.session_state.get(
                "standalone_design_visible", True
            )),
        }]
    active_id = str(st.session_state.get(
        "design_comparison_active_id",
        tabs[0]["id"],
    ))
    if standalone:
        active_id = "standalone"
    tab_colors = _design_comparison_tab_colors(tabs)
    tab_styles = []
    for tab in tabs:
        tab_id = str(tab["id"])
        color = tab_colors[tab_id]
        is_active = tab_id == active_id
        is_visible = bool(tab.get("visible", True))
        tab_styles.append(
            f"""
            .st-key-design_tab_shell_{tab_id} {{
                background: linear-gradient(
                    180deg, {color}{'4d' if is_active else '1f'}, {color}0d
                ) !important;
                border: {'2px' if is_active else '1px'} solid {color} !important;
                border-radius: .5rem !important;
                box-shadow: inset 0 -4px 0 {color} !important;
                padding: .12rem .18rem .28rem !important;
                position: relative !important;
            }}
            .st-key-design_tab_shell_{tab_id} [data-testid="stVerticalBlock"] {{
                gap: 0 !important;
            }}
            .st-key-design_comparison_tab_{tab_id} button {{
                background: transparent !important;
                border: 0 !important;
                box-shadow: none !important;
                font-weight: {'700' if is_active else '500'} !important;
                gap: .45rem !important;
                height: auto !important;
                justify-content: flex-start !important;
                min-height: 2rem !important;
                min-width: 0 !important;
                opacity: {'1' if is_visible else '.55'} !important;
                padding: .25rem {'5.95rem' if standalone else '7.8rem'} .25rem .35rem !important;
                width: 100% !important;
            }}
            .st-key-design_comparison_tab_{tab_id} button::before {{
                content: "";
                width: .62rem;
                height: .62rem;
                flex: 0 0 .62rem;
                border-radius: 999px;
                background: {color if is_visible else 'transparent'};
                border: {'0' if is_visible else f'2px solid {color}'};
                box-shadow: 0 0 0 2px rgba(15, 17, 23, .9);
            }}
            .st-key-design_comparison_tab_{tab_id} button p {{
                display: block !important;
                min-width: 0 !important;
                text-align: left !important;
                white-space: normal !important;
                line-height: 1.15 !important;
                word-break: break-word !important;
            }}
            .st-key-duplicate_design_tab_{tab_id},
            .st-key-toggle_design_tab_{tab_id},
            .st-key-delete_design_tab_{tab_id} {{
                position: absolute !important;
                top: .12rem !important;
                width: 1.8rem !important;
                z-index: 2 !important;
            }}
            .st-key-duplicate_design_tab_{tab_id} {{
                right: {'2.04rem' if standalone else '3.9rem'} !important;
            }}
            .st-key-toggle_design_tab_{tab_id} {{
                right: {'3.9rem' if standalone else '5.76rem'} !important;
            }}
            .st-key-delete_design_tab_{tab_id} {{
                right: {'2.04rem' if standalone else '2.04rem'} !important;
            }}
            .st-key-download_crw_tab_{tab_id} {{
                position: absolute !important;
                top: .12rem !important;
                right: .18rem !important;
                width: 1.8rem !important;
                z-index: 2 !important;
            }}
            .st-key-prepare_crw_tab_{tab_id} {{
                position: absolute !important;
                top: .12rem !important;
                right: .18rem !important;
                width: 1.8rem !important;
                z-index: 2 !important;
            }}
            .st-key-duplicate_design_tab_{tab_id} button,
            .st-key-toggle_design_tab_{tab_id} button,
            .st-key-delete_design_tab_{tab_id} button,
            .st-key-download_crw_tab_{tab_id} button,
            .st-key-prepare_crw_tab_{tab_id} button {{
                background: transparent !important;
                border: 0 !important;
                box-shadow: none !important;
                min-height: 2rem !important;
                min-width: 1.8rem !important;
                padding: 0 !important;
            }}
            .st-key-duplicate_design_tab_{tab_id} button p,
            .st-key-toggle_design_tab_{tab_id} button p,
            .st-key-delete_design_tab_{tab_id} button p,
            .st-key-download_crw_tab_{tab_id} button p,
            .st-key-prepare_crw_tab_{tab_id} button p {{
                display: none !important;
            }}
            """
        )
    st.markdown(
        f"<style>{''.join(tab_styles)}</style>",
        unsafe_allow_html=True,
    )
    for start in range(0, len(tabs), 4):
        row = tabs[start:start + 4]
        columns = st.columns(len(row))
        for column, tab in zip(columns, row, strict=True):
            tab_id = str(tab["id"])
            label = str(tab.get("label", "Design"))
            is_visible = bool(tab.get("visible", True))
            with column:
                with st.container(key=f"design_tab_shell_{tab_id}"):
                    is_active = tab_id == active_id
                    st.button(
                        label,
                        key=f"design_comparison_tab_{tab_id}",
                        type="primary" if is_active else "secondary",
                        width="stretch",
                        on_click=(
                            None if standalone
                            else _request_design_comparison_tab
                        ),
                        args=(() if standalone else (tab_id,)),
                    )
                    st.button(
                        "Duplicate design",
                        icon=":material/content_copy:",
                        key=f"duplicate_design_tab_{tab_id}",
                        disabled=len(tabs) >= _MAX_COMPARISON_DESIGNS,
                        on_click=(
                            _duplicate_standalone_design_from_click
                            if standalone
                            else _duplicate_design_tab_from_click
                        ),
                        args=(
                            (load_type, box, result)
                            if standalone
                            else (tab_id,)
                        ),
                    )
                    st.button(
                        "Hide design" if is_visible else "Show design",
                        icon=(
                            ":material/visibility:"
                            if is_visible
                            else ":material/visibility_off:"
                        ),
                        key=f"toggle_design_tab_{tab_id}",
                        on_click=_toggle_design_tab_visible,
                        args=(tab_id,),
                    )
                    crw_signature = _design_crw_signature(tab)
                    crw_ready = st.session_state.get("_design_crw_ready", {})
                    ready_for_tab = (
                        isinstance(crw_ready, dict)
                        and str(crw_ready.get("tab_id", "")) == tab_id
                        and str(crw_ready.get("signature", "")) == crw_signature
                    )
                    if ready_for_tab:
                        st.download_button(
                            "Download CRW driver",
                            data=crw_ready.get("data", b""),
                            file_name=str(
                                crw_ready.get("filename", "load_forge_driver.crw")
                            ),
                            mime="application/octet-stream",
                            icon=":material/download:",
                            key=f"download_crw_tab_{tab_id}",
                            disabled=crw_ready.get("error") is not None,
                            help=(
                                crw_ready.get("error")
                                or "Download the CRW file for this design"
                            ),
                        )
                    else:
                        st.button(
                            "Prepare CRW download",
                            icon=":material/download:",
                            key=f"prepare_crw_tab_{tab_id}",
                            on_click=_prepare_design_crw_download,
                            args=(tab,),
                            help="Prepare the CRW file for this design",
                        )
                    if not standalone:
                        st.button(
                            "Delete design",
                            icon=":material/close:",
                            key=f"delete_design_tab_{tab_id}",
                            on_click=_delete_design_comparison_tab,
                            args=(tab_id,),
                        )


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


def _pinned_metric_frame(
    value_key: str,
    selected_traces: set[str] | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Flatten one stored metric across valid pins and preserve legend order."""
    frames = []
    labels = []
    pinned_responses = _pinned_responses()
    visible_pins = [pin for pin in pinned_responses if pin.get("visible", True)]
    trace_budget = (
        4
        if value_key == "response_traces"
        else 2
        if value_key == "port_traces"
        else 1
    )
    rows_per_pin = max(
        1,
        _MAX_PINNED_CHART_ROWS // max(1, len(visible_pins) * trace_budget),
    )
    for index, pinned in enumerate(pinned_responses):
        if not pinned.get("visible", True):
            continue
        frequencies = np.asarray(pinned.get("frequency_hz", []), dtype=float)
        trace_label = f"{index + 1} · {pinned.get('label', 'Pinned response')}"
        trace_color = str(
            pinned.get("color")
            or _PIN_TRACE_COLORS[index % len(_PIN_TRACE_COLORS)]
        )
        stored = pinned.get(value_key, {})
        if value_key == "response_traces" and not isinstance(stored, dict):
            stored = {}
        if value_key == "response_traces" and not stored:
            stored = {"Total": pinned.get("spl_total_db", [])}
        stored_traces = stored if isinstance(stored, dict) else {"Pinned": stored}
        pin_has_data = False
        for series_name, stored_values in stored_traces.items():
            series_name = str(series_name)
            if selected_traces is not None:
                selected = series_name in selected_traces
                if series_name in _RESONATOR_RESPONSE_TRACES:
                    selected = selected or bool(
                        selected_traces & _RESONATOR_RESPONSE_TRACES
                    )
                if not selected:
                    continue
            values = np.asarray(stored_values, dtype=float)
            count = min(frequencies.size, values.size)
            if not count:
                continue
            data = pd.DataFrame({
                "frequency_hz": frequencies[:count],
                "value": values[:count],
                "label": trace_label,
                "trace": series_name,
                "color": trace_color,
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
            columns=("frequency_hz", "value", "label", "trace", "color")
        ), []
    return pd.concat(frames, ignore_index=True), labels


def _pinned_response_frame(
    selected_traces: set[str] | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Return every selected response pen across the comparison designs."""
    return _pinned_metric_frame("response_traces", selected_traces)


def _expand_y_domain_for_pins(
    y_domain: list[float] | None,
    frequency_window: list[float] | None,
    selected_traces: set[str] | None = None,
) -> list[float] | None:
    """Keep every pinned trace visible in the selected response window."""
    if y_domain is None:
        return None
    data, _ = _pinned_response_frame(selected_traces)
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
    selected_traces: set[str] | None = None,
) -> alt.Chart | None:
    data, labels = _pinned_metric_frame(value_key, selected_traces)
    if data.empty:
        return None
    traces = list(dict.fromkeys(data["trace"].tolist()))
    colors_by_label = (
        data[["label", "color"]]
        .drop_duplicates(subset=["label"])
        .set_index("label")["color"]
        .to_dict()
    )
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
                    colors_by_label.get(
                        label,
                        _PIN_TRACE_COLORS[index % len(_PIN_TRACE_COLORS)],
                    )
                    for index, label in enumerate(labels)
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
    selected_traces: set[str] | None = None,
) -> alt.Chart | None:
    return _pinned_metric_layer(
        "response_traces",
        "LF pressure estimate (dB)",
        ".3f",
        x_domain,
        y_domain,
        _response_amplitude_axis(),
        show_legend=show_legend,
        selected_traces=selected_traces,
    )


@st.cache_data(show_spinner=False, max_entries=32)
def _topology_comparison_series(
    ts: _acoustics.DriverTS,
    load_type: str,
    box,
    freq: np.ndarray,
    voltage_v: float,
    series_r_ohm: float,
    engine_revision: tuple[float | None, ...] = (),
) -> tuple[float, dict[str, np.ndarray]]:
    """Simulate the loads at a shared total volume for the overlay chart.

    The active load keeps its exact box; the other topologies use their
    standard starters constrained to the same total volume.  Infinite baffle
    has no volume, so when it is active the comparison volume falls back to
    the driver's Vas.
    """
    del engine_revision  # Cache invalidation key for hot-reloaded solver code.
    if load_type in {"Bass reflex", "Sealed"}:
        vtot = float(box.vb_l)
    elif load_type == "Bandpass 4th order":
        vtot = float(box.vs_l + box.vp_l)
    elif load_type == "Bandpass 6th order":
        vtot = float(box.vr_l + box.vp_l)
    elif load_type == "Bandpass 8th order":
        vtot = float(box.v1_l + box.v2_l + box.v3_l)
    elif load_type == "Infinite baffle":
        vtot = float(ts.vas_l)
    else:
        vtot = float(box.vh_l + box.vl_l)
    series: dict[str, np.ndarray] = {}
    try:
        d_box = box if load_type == "DCCAV" else _batch_dccav_box(ts, vtot)
        series["DCCAV"] = _acoustics.simulate(ts, d_box, freq, voltage_v, series_r_ohm).spl_total_db
    except Exception:
        logger.exception("Comparison DCCAV simulation failed")
    try:
        bp_start = _acoustics.suggest_bandpass4_alignment(ts)
        bp_box = box if load_type == "Bandpass 4th order" else _acoustics.design_space_box(
            ts, "Bandpass 4th order", vtot, bp_start.fp_hz)
        series["Bandpass 4th order"] = _acoustics.simulate_bandpass4(
            ts, bp_box, freq, voltage_v, series_r_ohm).spl_total_db
    except Exception:
        logger.exception("Comparison bandpass simulation failed")
    try:
        bp6_start = _acoustics.suggest_bandpass6_alignment(ts)
        bp6_box = box if load_type == "Bandpass 6th order" else _acoustics.design_space_box(
            ts, "Bandpass 6th order", vtot, bp6_start.fp_hz)
        series["Bandpass 6th order"] = _acoustics.simulate_bandpass6(
            ts, bp6_box, freq, voltage_v, series_r_ohm).spl_total_db
    except Exception:
        logger.exception("Comparison bandpass6 simulation failed")
    try:
        bp8_start = _acoustics.suggest_bandpass8_alignment(ts)
        bp8_box = box if load_type == "Bandpass 8th order" else _acoustics.design_space_box(
            ts, "Bandpass 8th order", vtot, bp8_start.f3_hz)
        series["Bandpass 8th order"] = _acoustics.simulate_bandpass8(
            ts, bp8_box, freq, voltage_v, series_r_ohm).spl_total_db
    except Exception:
        logger.exception("Comparison bandpass8 simulation failed")
    try:
        if load_type == "Bass reflex" and isinstance(box, _acoustics.PassiveRadiatorBox):
            series["Bass reflex"] = _acoustics.simulate_passive_radiator(
                ts, box, freq, voltage_v, series_r_ohm).spl_total_db
        else:
            r_box = box if load_type == "Bass reflex" else _acoustics.ReflexBox(
                vb_l=vtot, fb_hz=_acoustics.suggest_reflex_alignment(ts).fb_hz)
            series["Bass reflex"] = _acoustics.simulate_reflex(
                ts, r_box, freq, voltage_v, series_r_ohm).spl_total_db
    except Exception:
        logger.exception("Comparison reflex simulation failed")
    try:
        s_box = box if load_type == "Sealed" else _acoustics.SealedBox(vb_l=vtot)
        series["Sealed"] = _acoustics.simulate_sealed(
            ts, s_box, freq, voltage_v, series_r_ohm).spl_total_db
    except Exception:
        logger.exception("Comparison sealed simulation failed")
    try:
        series["Infinite baffle"] = _acoustics.simulate_infinite_baffle(
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
    result: _acoustics.SimulationResult,
    port: str,
) -> dict:
    area_cm2 = np.pi * (diameter_cm / 2.0) ** 2
    velocity = _acoustics.port_air_velocity_ms(result, area_cm2, port)
    peak_idx = int(np.nanargmax(velocity))
    velocity_mol = _acoustics.port_air_velocity_ms(result, area_cm2, port, at_mol=True)
    peak_mol_idx = int(np.nanargmax(velocity_mol))
    return {
        "Port": label,
        "Diameter cm": float(diameter_cm),
        "Length cm": _acoustics.port_length_cm(volume_l, fb_hz, diameter_cm, end_correction),
        "Peak m/s": float(velocity[peak_idx]),
        "Peak m/s (MOL)": float(velocity_mol[peak_mol_idx]),
        "Peak at Hz": float(result.frequency_hz[peak_idx]),
        "_volume_l": float(volume_l),
        "_fb_hz": float(fb_hz),
        "_end_correction": float(end_correction),
    }


_PORT_GEOMETRY_COLUMNS = ("Port", "Diameter cm", "Length cm", "Peak m/s", "Peak m/s (MOL)", "Peak at Hz")


def _plot_group_delay(result: _acoustics.SimulationResult, limit_ms: float = 0.0) -> alt.Chart:
    active_design_visible = _active_design_visible()
    data = _series_frame(
        result,
        {"Group delay": _acoustics.group_delay_ms(result)}
        if active_design_visible
        else {},
    )
    active_color = _active_design_comparison_color()
    chart = _line_chart(
        data,
        "Group delay (ms)",
        height=240,
        legend=False,
        color_overrides=(
            {"Group delay": active_color} if active_color else None
        ),
    )
    if active_design_visible and limit_ms > 0.0:
        limit_rule = alt.Chart(pd.DataFrame({"limit_ms": [float(limit_ms)]})).mark_rule(
            color="#10b981",
            strokeDash=[6, 4],
        ).encode(y="limit_ms:Q")
        chart = chart + limit_rule
    pinned = _pinned_metric_layer("group_delay_ms", "Group delay (ms)", ".3f")
    if pinned is not None:
        chart = (chart + pinned).resolve_scale(
            color="independent", strokeDash="independent")
    return chart


def _plot_ports(
    result: _acoustics.SimulationResult,
    mode: str = "air_velocity_mol",
) -> alt.Chart:
    series = _port_series(result, mode=mode)
    if not series:
        raise ValueError("No port traces selected")
    data = _series_frame(
        result,
        series if _active_design_visible() else {},
    )
    if mode == "volume_velocity":
        y_title = "Volume velocity (m³/s)"
        tooltip_format = ".6f"
    elif mode == "air_velocity_mol":
        y_title = "Air velocity at MOL (m/s)"
        tooltip_format = ".1f"
    else:
        y_title = "Air velocity (m/s)"
        tooltip_format = ".1f"
    chart = _line_chart(data, y_title, height=320)
    if mode in {"air_velocity_mol", "air_velocity_sim"}:
        active_style = _focused_port_flare_style()
        guideline_specs = [
            ("none", "Straight", "#ef4444", "rgba(239, 68, 68, 0.35)"),
            ("one", "Single flare", "#f59e0b", "rgba(245, 158, 11, 0.35)"),
            ("both", "Aeroport", "#10b981", "rgba(16, 185, 129, 0.35)"),
            ("hourglass", "Hourglass", "#06b6d4", "rgba(6, 182, 212, 0.35)"),
        ]
        active_style_key = "one" if active_style == "one_end" else active_style
        g_limits = [
            _acoustics.port_chuffing_limit_ms(style)
            for style, _, _, _ in guideline_specs
        ]
        g_labels = [
            f"{label} limit ({limit:.1f} m/s)"
            for (_, label, _, _), limit in zip(guideline_specs, g_limits)
        ]
        g_colors = [
            active_color if style == active_style_key else muted_color
            for style, _, active_color, muted_color in guideline_specs
        ]
        guidelines_df = pd.DataFrame({
            "limit": g_limits,
            "label": g_labels,
            "color": g_colors,
        })
        guideline_rule = alt.Chart(guidelines_df).mark_rule(
            strokeDash=[6, 4],
            strokeWidth=1.5,
        ).encode(
            y="limit:Q",
            color=alt.Color("color:N", scale=None),
        )
        chart = chart + guideline_rule
    pinned = _pinned_metric_layer(
        "port_traces", y_title, tooltip_format)
    if pinned is not None:
        chart = (chart + pinned).resolve_scale(
            color="independent", strokeDash="independent")
    return chart


def _rank_value(value: float) -> float:
    return _acoustics.rank_sort_value(value)


def _batch_dccav_box(ts: _acoustics.DriverTS, total_volume_l: float) -> _acoustics.DccavBox:
    """Starter-shaped DCCAV box constrained to an exact total volume."""
    return _acoustics.design_space_box(
        ts, "DCCAV", float(total_volume_l), _acoustics.suggest_alignment(ts).fl_hz)


@st.cache_data(show_spinner=False)
def _batch_rank_presets(
    # Cache busted to reflect JSON DB fixes 3
    preset_names: tuple[str, ...],
    load_type: str,
    max_volume_l: float,
    voltage_v: float,
    f_min_hz: float,
    f_max_hz: float,
    points: int,
    candidate_limit: int,
    goals: _acoustics.OptimizationGoals | None = None,
    driver_configuration: str = "Single driver",
    ranking_version: int = _FINDER_RANKING_VERSION,
) -> list[dict]:
    if ranking_version != _FINDER_RANKING_VERSION:
        raise ValueError("Unsupported Finder ranking revision")
    rows: list[dict] = []
    for name in preset_names[:int(candidate_limit)]:
        row = _acoustics.rank_preset_row(
            name, load_type, float(max_volume_l), float(voltage_v),
            float(f_min_hz), float(f_max_hz), int(points), goals,
            driver_configuration,
        )
        if row is not None:
            rows.append(row)
    return _acoustics.sort_ranked_rows(rows)


def _is_streamlit_community_cloud(app_path: Path | None = None) -> bool:
    """Recognize Community Cloud's checkout convention."""
    resolved_path = (app_path or Path(__file__)).resolve()
    return resolved_path.is_relative_to(Path("/mount/src"))


def _finder_executor_backend(app_path: Path | None = None) -> str:
    """Keep Finder workers in the live Streamlit process.

    Python's process backends re-import ``ui_app.py`` outside Streamlit and
    can retain a different optimizer module than the active Box Design. NumPy
    releases the GIL for the heavy solver operations, so shared-memory threads
    retain useful parallelism without allowing two engine revisions to coexist.
    """
    return "thread"


def _finder_worker_limit(app_path: Path | None = None) -> int:
    """Bound duplicated catalog memory on Streamlit Community Cloud."""
    return 4 if _is_streamlit_community_cloud(app_path) else 8


def _finder_pool_fingerprint(workers: int) -> tuple:
    """Identity of the code+data the Finder workers hold in memory."""
    paths = [
        Path(module.__file__)
        for module in (_engine, _presets, _pricing, _ranking, _acoustics)
    ]
    paths.extend([
        _presets.MANUFACTURER_DATABASE_PATH,
        _presets.LOUDSPEAKER_DATABASE_PATH,
        _presets.ZTZ_AUDIO_DATABASE_PATH,
        _pricing.DRIVER_PRICES_PATH,
    ])
    mtimes = tuple(
        path.stat().st_mtime if path.exists() else None for path in paths
    )
    return (
        _FINDER_RANKING_VERSION,
        _ranking.FINDER_WORKER_PROTOCOL_REVISION,
        _engine.OPTIMIZER_ENGINE_REVISION,
        _finder_executor_backend(),
        workers,
        *mtimes,
    )


def _finder_worker_pool(
    workers: int,
) -> ProcessPoolExecutor | ThreadPoolExecutor:
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

    def thread_fallback() -> ThreadPoolExecutor:
        fallback = ThreadPoolExecutor(max_workers=workers)
        for _ in range(workers):
            fallback.submit(_presets.driver_preset_names)
        _ranking._finder_shared_pool = fallback
        _ranking._finder_shared_pool_key = key
        _ranking._finder_shared_pool_backend = "thread"
        return fallback

    # Cloud Run stays on shared-memory threads because its CPU/memory profile
    # is explicitly tuned for them.
    if _finder_executor_backend() == "thread":
        return thread_fallback()
    # forkserver: no re-import of the caller's __main__ in the workers (the
    # spawn method would re-execute entrypoint scripts) and no fork of a
    # thread-filled Streamlit process.
    mp_context = multiprocessing.get_context(
        "forkserver" if "forkserver" in multiprocessing.get_all_start_methods()
        else "spawn"
    )
    pool = None
    try:
        pool = ProcessPoolExecutor(
            max_workers=workers,
            mp_context=mp_context,
        )
        warmups = [
            pool.submit(_ranking.finder_worker_ready)
            for _ in range(workers)
        ]
        # A persistent forkserver can create a brand-new pool whose children
        # still inherit an old engine module. Verify the semantic revisions,
        # not only process startup/file mtimes, before accepting any rows.
        expected_revisions = (
            _ranking.FINDER_WORKER_PROTOCOL_REVISION,
            _engine.OPTIMIZER_ENGINE_REVISION,
        )
        deadline = time.monotonic() + 10.0
        for future in warmups:
            ready = future.result(
                timeout=max(0.01, deadline - time.monotonic())
            )
            if not (
                isinstance(ready, tuple)
                and len(ready) == 3
                and tuple(ready[1:]) == expected_revisions
            ):
                raise RuntimeError(
                    "Finder worker loaded a stale ranking or optimizer engine"
                )
    except Exception:
        if pool is not None:
            pool.shutdown(wait=False, cancel_futures=True)
        logger.warning(
            "Finder process startup failed; using shared-memory threads",
            exc_info=True,
        )
        return thread_fallback()
    _ranking._finder_shared_pool = pool
    _ranking._finder_shared_pool_key = key
    _ranking._finder_shared_pool_backend = "process"
    if not getattr(_ranking, "_finder_pool_atexit_registered", False):
        atexit.register(_drop_finder_worker_pool)
        _ranking._finder_pool_atexit_registered = True
    return pool


def _drop_finder_worker_pool() -> None:
    pool = getattr(_ranking, "_finder_shared_pool", None)
    _ranking._finder_shared_pool = None
    _ranking._finder_shared_pool_key = None
    _ranking._finder_shared_pool_backend = None
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
    goals: _acoustics.OptimizationGoals | None,
    progress_widget: object | None = None,
    progress_text_widget: object | None = None,
    completed_offset: int = 0,
    progress_total: int | None = None,
    driver_configuration: str = "Single driver",
    search_profile: str = _ranking.SEARCH_PROFILE_STANDARD,
) -> list[dict]:
    """Rank candidates across worker processes with a real progress bar."""
    names = list(preset_names)[:int(candidate_limit)]
    total = max(len(names), 1)
    overall_total = max(int(progress_total or total), 1)
    workers = max(1, min(os.cpu_count() or 2, _finder_worker_limit()))
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
        # Resolve names in the parent, whose catalog is already loaded. Worker
        # processes receive only compact T/S + display metadata payloads and
        # therefore never duplicate the full external catalog in Cloud RAM.
        candidates = [_ranking.ranking_candidate(name) for name in names]
        # Small chunks keep the ordered map streaming: with large chunks the
        # first result (and the progress bar) stalls until a whole chunk of
        # hundreds of simulations completes, which reads as a hung start.
        results = pool.map(
            _ranking.rank_candidate_row,
            candidates,
            [load_type] * len(names),
            [float(max_volume_l)] * len(names),
            [float(voltage_v)] * len(names),
            [float(f_min_hz)] * len(names),
            [float(f_max_hz)] * len(names),
            [int(points)] * len(names),
            [goals] * len(names),
            [driver_configuration] * len(names),
            [search_profile] * len(names),
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
            driver_configuration, search_profile,
        )
    finally:
        if owns_progress:
            progress.empty()
            if progress_text_widget is not None:
                progress_text_widget.empty()
    return _acoustics.sort_ranked_rows(rows)


def _batch_rank_presets_with_progress(
    preset_names: tuple[str, ...],
    load_type: str,
    max_volume_l: float,
    voltage_v: float,
    f_min_hz: float,
    f_max_hz: float,
    points: int,
    candidate_limit: int,
    goals: _acoustics.OptimizationGoals | None,
    progress: object,
    progress_text: object | None,
    completed_offset: int,
    progress_total: int,
    driver_configuration: str = "Single driver",
    search_profile: str = _ranking.SEARCH_PROFILE_STANDARD,
) -> list[dict]:
    """Serial ranking path that reports real per-candidate progress."""
    names = list(preset_names)[:int(candidate_limit)]
    overall_total = max(int(progress_total), 1)
    rows: list[dict] = []
    for done, name in enumerate(names, start=1):
        row = _acoustics.rank_preset_row(
            name, load_type, float(max_volume_l), float(voltage_v),
            float(f_min_hz), float(f_max_hz), int(points), goals,
            driver_configuration, search_profile,
        )
        if row is not None:
            rows.append(row)
        current = completed_offset + done
        if done % max(1, overall_total // 20) == 0 or done == len(names):
            progress.progress(min(current / overall_total, 1.0))
            if progress_text is not None:
                progress_text.caption(f"Matching {current}/{overall_total} simulations · {load_type}")
    return _acoustics.sort_ranked_rows(rows)


def _finder_row_driver(row: dict) -> _acoustics.DriverTS:
    """Return the exact base driver used to calculate a Finder row."""
    payload = row.get("_driver_ts")
    if isinstance(payload, dict):
        fields = _acoustics.DriverTS.__dataclass_fields__
        try:
            return _acoustics.DriverTS(**{
                name: payload[name]
                for name in fields
                if name in payload
            })
        except (TypeError, ValueError):
            logger.warning("Invalid Finder driver snapshot; using live preset")
    return _acoustics.get_driver_preset(str(row["Driver"]))


def _finder_row_box_params(row: dict) -> dict:
    """Return the complete physical box snapshot saved by Finder."""
    payload = row.get("_box_params")
    return dict(payload) if isinstance(payload, dict) else {}


def _finder_box_value(row: dict, key: str, default):
    return _finder_row_box_params(row).get(key, default)


def _apply_batch_result(row: dict, load_type: str) -> None:
    if load_type in ("Suspension pneumatic", "Acoustic suspension"):
        load_type = "Sealed"
    legacy_pr = load_type == "Passive radiator"
    if legacy_pr:
        load_type = "Bass reflex"
    name = str(row["Driver"])
    driver = _finder_row_driver(row)
    driver_configuration = str(
        row.get("Driver configuration", "Single driver")
    )
    configured_driver = _acoustics.apply_driver_configuration(
        driver,
        driver_configuration,
    )
    st.session_state["load_type"] = load_type
    st.session_state["driver_preset_name"] = name
    st.session_state["driver_config"] = driver_configuration
    _apply_driver_preset(driver)
    st.session_state["driver_panel_air_load"] = bool(driver.panel_air_load)
    st.session_state["driver_panel_coupling"] = float(driver.panel_coupling)
    _use_manual_box_strategy()
    st.session_state["workspace_mode"] = "Box Design"
    st.session_state["opt_max_ripple_freq_hz"] = float(st.session_state.get("finder_max_ripple_freq_hz", 0.0) or 0.0)
    if load_type == "Bass reflex":
        st.session_state["reflex_vb_l"] = float(row["Vb L"])
        resonator = str(row.get(
            "Resonator", _RESONATOR_PR if legacy_pr else _RESONATOR_PORT))
        st.session_state["reflex_resonator_type"] = resonator
        if resonator == _RESONATOR_PR:
            pr = _acoustics.suggest_pr_alignment(configured_driver)
            st.session_state["pr_sp_cm2"] = float(pr.pr_sp_cm2)
            st.session_state["pr_fp_hz"] = float(pr.pr_fp_hz)
            st.session_state["pr_qmp"] = float(pr.pr_qmp)
            st.session_state["pr_mmp_g"] = float(pr.pr_mmp_g)
            st.session_state["pr_xmax_mm"] = float(pr.pr_xmax_mm)
            st.session_state["pr_q_abs"] = float(_finder_box_value(row, "q_abs", 15.0))
            st.session_state["pr_q_leak"] = float(_finder_box_value(row, "q_leak", 1000.0))
        else:
            st.session_state["reflex_fb_hz"] = float(row["Fb Hz"])
            st.session_state["reflex_q_abs"] = float(_finder_box_value(row, "q_abs", _DEFAULT_REFLEX_Q_ABS))
            st.session_state["reflex_q_leak"] = float(_finder_box_value(row, "q_leak", _DEFAULT_REFLEX_Q_LEAK))
            st.session_state["reflex_q_port"] = float(_finder_box_value(row, "q_port", _DEFAULT_REFLEX_Q_PORT))
            st.session_state["reflex_custom_losses"] = True
    elif load_type == "Bandpass 4th order":
        st.session_state["bandpass4_vs_l"] = float(row["Vs L"])
        st.session_state["bandpass4_vp_l"] = float(row["Vp L"])
        st.session_state["bandpass4_fp_hz"] = float(row["Fp Hz"])
        for key in ("q_abs_s", "q_abs_p", "q_leak_s", "q_leak_p", "q_port"):
            if key in _finder_row_box_params(row):
                st.session_state[f"bandpass4_{key}"] = float(_finder_box_value(row, key, 0.0))
    elif load_type == "Bandpass 6th order":
        st.session_state["bandpass6_vr_l"] = float(row["Vr L"])
        st.session_state["bandpass6_fr_hz"] = float(row["Fr Hz"])
        st.session_state["bandpass6_vp_l"] = float(row["Vp L"])
        st.session_state["bandpass6_fp_hz"] = float(row["Fp Hz"])
        for key in ("q_abs_r", "q_abs_p", "q_leak_r", "q_leak_p", "q_port_r", "q_port_p"):
            if key in _finder_row_box_params(row):
                st.session_state[f"bandpass6_{key}"] = float(_finder_box_value(row, key, 0.0))
    elif load_type == "Bandpass 8th order":
        st.session_state["bp8_v1_l"] = float(row["V1 L"])
        st.session_state["bp8_f1_hz"] = float(row["f1 Hz"])
        st.session_state["bp8_v2_l"] = float(row["V2 L"])
        st.session_state["bp8_f2_hz"] = float(row["f2 Hz"])
        st.session_state["bp8_v3_l"] = float(row["V3 L"])
        st.session_state["bp8_f3_hz"] = float(row["f3 Hz"])
        for key in ("q_abs_1", "q_abs_2", "q_abs_3", "q_leak_1", "q_leak_2", "q_leak_3", "q_port_1", "q_port_2", "q_port_3"):
            if key in _finder_row_box_params(row):
                st.session_state[f"bp8_{key}"] = float(_finder_box_value(row, key, 0.0))
    elif load_type == "Sealed":
        st.session_state["sealed_vb_l"] = float(row["Vb L"])
        st.session_state["sealed_q_abs"] = float(_finder_box_value(row, "q_abs", 15.0))
        st.session_state["sealed_q_leak"] = float(_finder_box_value(row, "q_leak", 1000.0))
    elif load_type == "DCCAV":
        st.session_state["box_vh_l"] = float(row["Vh L"])
        st.session_state["box_fh_hz"] = float(row["fh Hz"])
        st.session_state["box_vl_l"] = float(row["Vl L"])
        st.session_state["box_fl_hz"] = float(row["fl Hz"])
        for key in ("q_abs_h", "q_abs_l", "q_leak_h", "q_leak_l", "q_port_h", "q_port_l"):
            if key in _finder_row_box_params(row):
                st.session_state[f"loss_{key}"] = float(_finder_box_value(row, key, 0.0))
    if load_type == "Bass reflex" and not _reflex_uses_passive_radiator():
        optimized_box = _reflex_box_from_state()
    elif load_type == "Bandpass 4th order":
        optimized_box = _bandpass4_box_from_state()
    elif load_type == "Bandpass 6th order":
        optimized_box = _bandpass6_box_from_state()
    elif load_type == "Bandpass 8th order":
        optimized_box = _bandpass8_box_from_state()
    elif load_type == "DCCAV":
        optimized_box = _box_from_state()
    else:
        optimized_box = None
    if optimized_box is not None:
        _apply_optimized_port_geometry(driver, optimized_box)
    _mark_auto_alignment_synced(driver)


def _finder_result_snapshot(
    row: dict,
    load_type: str,
    frequency_hz: np.ndarray,
    voltage_v: float,
) -> dict:
    """Simulate one ranked Finder row as a reusable Box Design comparison."""
    if load_type in ("Suspension pneumatic", "Acoustic suspension"):
        load_type = "Sealed"
    legacy_pr = load_type == "Passive radiator"
    if legacy_pr:
        load_type = "Bass reflex"
    resonator = str(
        row.get("Resonator", _RESONATOR_PR if legacy_pr else _RESONATOR_PORT)
    )
    name = str(row["Driver"])
    configuration = str(
        row.get("Driver configuration", "Single driver")
    )
    driver = _acoustics.apply_driver_configuration(
        _finder_row_driver(row),
        configuration,
    )
    if load_type == "Bass reflex" and resonator == _RESONATOR_PR:
        suggested = _acoustics.suggest_pr_alignment(driver)
        box = _acoustics.PassiveRadiatorBox(
            vb_l=float(row["Vb L"]),
            pr_sp_cm2=float(suggested.pr_sp_cm2),
            pr_fp_hz=float(suggested.pr_fp_hz),
            pr_qmp=float(suggested.pr_qmp),
            pr_mmp_g=float(suggested.pr_mmp_g),
            pr_xmax_mm=float(suggested.pr_xmax_mm),
            q_abs=float(_finder_box_value(row, "q_abs", 15.0)),
            q_leak=float(_finder_box_value(row, "q_leak", 1000.0)),
        )
        result = _acoustics.simulate_passive_radiator(
            driver, box, frequency_hz, voltage_v
        )
    elif load_type == "Bass reflex":
        box = _acoustics.ReflexBox(
            vb_l=float(row["Vb L"]),
            fb_hz=float(row["Fb Hz"]),
            q_abs=float(_finder_box_value(row, "q_abs", _DEFAULT_REFLEX_Q_ABS)),
            q_leak=float(_finder_box_value(row, "q_leak", _DEFAULT_REFLEX_Q_LEAK)),
            q_port=float(_finder_box_value(row, "q_port", _DEFAULT_REFLEX_Q_PORT)),
        )
        result = _acoustics.simulate_reflex(
            driver, box, frequency_hz, voltage_v
        )
    elif load_type == "Bandpass 4th order":
        box = _acoustics.Bandpass4Box(
            vs_l=float(row["Vs L"]),
            vp_l=float(row["Vp L"]),
            fp_hz=float(row["Fp Hz"]),
            q_abs_s=float(_finder_box_value(row, "q_abs_s", 15.0)),
            q_abs_p=float(_finder_box_value(row, "q_abs_p", 15.0)),
            q_leak_s=float(_finder_box_value(row, "q_leak_s", 1000.0)),
            q_leak_p=float(_finder_box_value(row, "q_leak_p", 1000.0)),
            q_port=float(_finder_box_value(row, "q_port", 15.0)),
        )
        result = _acoustics.simulate_bandpass4(
            driver, box, frequency_hz, voltage_v
        )
    elif load_type == "Bandpass 6th order":
        box = _acoustics.Bandpass6Box(
            vr_l=float(row["Vr L"]),
            fr_hz=float(row["Fr Hz"]),
            vp_l=float(row["Vp L"]),
            fp_hz=float(row["Fp Hz"]),
            q_abs_r=float(_finder_box_value(row, "q_abs_r", 15.0)),
            q_abs_p=float(_finder_box_value(row, "q_abs_p", 15.0)),
            q_leak_r=float(_finder_box_value(row, "q_leak_r", 1000.0)),
            q_leak_p=float(_finder_box_value(row, "q_leak_p", 1000.0)),
            q_port_r=float(_finder_box_value(row, "q_port_r", 15.0)),
            q_port_p=float(_finder_box_value(row, "q_port_p", 15.0)),
        )
        result = _acoustics.simulate_bandpass6(
            driver, box, frequency_hz, voltage_v
        )
    elif load_type == "Bandpass 8th order":
        box = _acoustics.Bandpass8Box(
            v1_l=float(row["V1 L"]),
            f1_hz=float(row["f1 Hz"]),
            v2_l=float(row["V2 L"]),
            f2_hz=float(row["f2 Hz"]),
            v3_l=float(row["V3 L"]),
            f3_hz=float(row["f3 Hz"]),
            q_abs_1=float(_finder_box_value(row, "q_abs_1", 15.0)),
            q_abs_2=float(_finder_box_value(row, "q_abs_2", 15.0)),
            q_abs_3=float(_finder_box_value(row, "q_abs_3", 15.0)),
            q_leak_1=float(_finder_box_value(row, "q_leak_1", 1000.0)),
            q_leak_2=float(_finder_box_value(row, "q_leak_2", 1000.0)),
            q_leak_3=float(_finder_box_value(row, "q_leak_3", 1000.0)),
            q_port_1=float(_finder_box_value(row, "q_port_1", 15.0)),
            q_port_2=float(_finder_box_value(row, "q_port_2", 15.0)),
            q_port_3=float(_finder_box_value(row, "q_port_3", 15.0)),
        )
        result = _acoustics.simulate_bandpass8(
            driver, box, frequency_hz, voltage_v
        )
    elif load_type == "Sealed":
        box = _acoustics.SealedBox(
            vb_l=float(row["Vb L"]),
            q_abs=float(_finder_box_value(row, "q_abs", 15.0)),
            q_leak=float(_finder_box_value(row, "q_leak", 1000.0)),
        )
        result = _acoustics.simulate_sealed(
            driver, box, frequency_hz, voltage_v
        )
    elif load_type == "Infinite baffle":
        box = None
        result = _acoustics.simulate_infinite_baffle(
            driver, frequency_hz, voltage_v
        )
    else:
        load_type = "DCCAV"
        box = _acoustics.DccavBox(
            vh_l=float(row["Vh L"]),
            fh_hz=float(row["fh Hz"]),
            vl_l=float(row["Vl L"]),
            fl_hz=float(row["fl Hz"]),
            q_abs_h=float(_finder_box_value(row, "q_abs_h", 15.0)),
            q_abs_l=float(_finder_box_value(row, "q_abs_l", 15.0)),
            q_leak_h=float(_finder_box_value(row, "q_leak_h", 1000.0)),
            q_leak_l=float(_finder_box_value(row, "q_leak_l", 1000.0)),
            q_port_h=float(_finder_box_value(row, "q_port_h", 15.0)),
            q_port_l=float(_finder_box_value(row, "q_port_l", 15.0)),
        )
        result = _acoustics.simulate(driver, box, frequency_hz, voltage_v)
    return _pinned_response_snapshot(
        load_type,
        box,
        result,
        label=_pin_label(
            load_type,
            box,
            preset=name,
            config=configuration,
        ),
    )


def _apply_pending_batch_result() -> None:
    pending = st.session_state.pop("batch_pending_result", None)
    if not pending:
        return
    existing_tabs = _design_comparison_tabs()
    added = _add_finder_designs_to_comparison(
        [{
            "row": pending["row"],
            "load_type": str(pending["load_type"]),
        }],
        float(pending.get(
            "voltage_v",
            st.session_state.get("finder_voltage", 2.83),
        )),
    )
    if added:
        action = "Added" if existing_tabs else "Opened"
        st.toast(f"{action} {added[0]['label']} in Box Design")
    else:
        st.toast(
            f"Box Design already has {_MAX_COMPARISON_DESIGNS} designs"
        )


def _add_finder_designs_to_comparison(
    designs: list[dict],
    voltage_v: float,
) -> list[dict]:
    """Append Finder matches as editable tabs without replacing open designs."""
    comparison_tabs = _design_comparison_tabs()
    available = max(0, _MAX_COMPARISON_DESIGNS - len(comparison_tabs))
    if available <= 0:
        return []
    frequency_hz = np.geomspace(
        float(st.session_state["sim_f_min"]),
        float(st.session_state["sim_f_max"]),
        int(st.session_state["sim_points"]),
    )
    added_tabs = []
    for design in designs[:available]:
        row = design["row"]
        load_type = str(design["load_type"])
        _apply_batch_result(row, load_type)
        st.session_state["sim_voltage"] = float(voltage_v)
        st.session_state["sim_series_r_ohm"] = 0.0
        tab_number = len(comparison_tabs) + 1
        tab_id = f"design_{uuid.uuid4().hex}"
        label = _design_comparison_tab_label(
            tab_number,
            load_type,
            preset=str(row["Driver"]),
            config=str(row.get("Driver configuration", "Single driver")),
        )
        color = _DESIGN_COMPARISON_TRACE_COLORS[
            len(comparison_tabs) % len(_DESIGN_COMPARISON_TRACE_COLORS)
        ]
        snapshot = _finder_result_snapshot(
            row,
            load_type,
            frequency_hz,
            float(voltage_v),
        )
        snapshot["label"] = label
        snapshot["color"] = color
        new_tab = {
            "id": tab_id,
            "label": label,
            "color": color,
            "driver_preset_name": str(row["Driver"]),
            "display_driver_name": str(row["Driver"]),
            "load_type": load_type,
            "visible": True,
            "parameters": _json_safe(_collect_params()),
            "snapshot": snapshot,
        }
        comparison_tabs.append(new_tab)
        added_tabs.append(new_tab)
    if not added_tabs:
        return []
    active = added_tabs[0]
    _apply_loaded_params(dict(active["parameters"]))
    st.session_state["design_comparison_tabs"] = comparison_tabs
    st.session_state["design_comparison_active_id"] = active["id"]
    st.session_state["design_comparison_loaded_id"] = active["id"]
    st.session_state["pinned_responses"] = [
        dict(item["snapshot"])
        for item in comparison_tabs
        if str(item["id"]) != str(active["id"])
        and isinstance(item.get("snapshot"), dict)
    ]
    st.session_state["plot_compare_loads"] = False
    st.session_state["workspace_mode"] = "Box Design"
    return added_tabs


def _apply_pending_batch_comparison() -> None:
    pending = st.session_state.pop("batch_pending_comparison", None)
    if not isinstance(pending, dict):
        return
    designs = pending.get("designs", [])
    if not isinstance(designs, list) or len(designs) < 2:
        return
    voltage_v = float(pending.get("voltage_v", 2.83))
    existing_count = len(_design_comparison_tabs())
    added = _add_finder_designs_to_comparison(designs, voltage_v)
    action = "Added" if existing_count else "Created"
    st.toast(f"{action} {len(added)} editable Box Design tabs")


def _design_comparison_tabs() -> list[dict]:
    tabs = st.session_state.get("design_comparison_tabs", [])
    if not isinstance(tabs, list):
        tabs = []
    valid_tabs = [
        item
        for item in tabs
        if isinstance(item, dict) and item.get("id")
    ]
    changed = len(valid_tabs) != len(tabs)
    for index, tab in enumerate(valid_tabs):
        snapshot = tab.get("snapshot")
        if isinstance(snapshot, dict) and not snapshot.get("_revision"):
            _snapshot_revision(snapshot)
            changed = True
        visible = bool(
            tab.get(
                "visible",
                snapshot.get("visible", True)
                if isinstance(snapshot, dict)
                else True,
            )
        )
        if tab.get("visible") is not visible:
            tab["visible"] = visible
            changed = True
        if (
            isinstance(snapshot, dict)
            and snapshot.get("visible") is not visible
        ):
            snapshot["visible"] = visible
            changed = True
        color = _DESIGN_COMPARISON_TRACE_COLORS[
            index % len(_DESIGN_COMPARISON_TRACE_COLORS)
        ]
        if str(tab.get("color", "")) != color:
            tab["color"] = color
            changed = True
        if (
            isinstance(snapshot, dict)
            and str(snapshot.get("color", "")) != color
        ):
            snapshot["color"] = color
            changed = True
        parameters = tab.get("parameters")
        if isinstance(parameters, dict) and parameters.get("load_type"):
            stable_preset = str(
                tab.get("driver_preset_name")
                or parameters.get("driver_preset_name", "Custom")
            )
            display_preset = str(
                tab.get("display_driver_name")
                or _design_tab_label_driver(str(tab.get("label", "")))
                or stable_preset
            )
            driver_signature = _design_driver_parameter_signature(parameters)
            if (
                stable_preset == "Custom"
                and tab.get("preset_recovery_signature") != driver_signature
            ):
                stable_preset = _recover_design_tab_preset(parameters)
                tab["preset_recovery_signature"] = driver_signature
                changed = True
                if stable_preset != "Custom":
                    parameters["driver_preset_name"] = stable_preset
                    if not display_preset or display_preset == "Custom":
                        display_preset = stable_preset
            stable_load_type = str(
                tab.get("load_type") or parameters["load_type"]
            )
            if tab.get("driver_preset_name") != stable_preset:
                tab["driver_preset_name"] = stable_preset
                changed = True
            if tab.get("display_driver_name") != display_preset:
                tab["display_driver_name"] = display_preset
                changed = True
            if tab.get("load_type") != stable_load_type:
                tab["load_type"] = stable_load_type
                changed = True
            compact_label = _design_comparison_tab_label(
                index + 1,
                stable_load_type,
                preset=display_preset,
                config=str(parameters.get("driver_config", "Single driver")),
            )
            if str(tab.get("label", "")) != compact_label:
                tab["label"] = compact_label
                if isinstance(snapshot, dict):
                    snapshot["label"] = compact_label
                changed = True
    if changed:
        st.session_state["design_comparison_tabs"] = valid_tabs
    return valid_tabs


def _request_design_comparison_tab(tab_id: str) -> None:
    st.session_state["design_comparison_active_id"] = str(tab_id)


def _sync_active_design_comparison_tab() -> None:
    """Save the previous editable tab and load the newly selected design."""
    tabs = _design_comparison_tabs()
    if not tabs:
        return
    tab_by_id = {str(item["id"]): item for item in tabs}
    requested_id = str(
        st.session_state.get(
            "design_comparison_active_id",
            tabs[0]["id"],
        )
    )
    if requested_id not in tab_by_id:
        requested_id = str(tabs[0]["id"])
        st.session_state["design_comparison_active_id"] = requested_id
    loaded_id = str(
        st.session_state.get("design_comparison_loaded_id", requested_id)
    )
    if loaded_id == requested_id:
        return
    if loaded_id in tab_by_id:
        previous = tab_by_id[loaded_id]
        previous_parameters = _json_safe(_collect_params())
        stable_previous_preset = str(previous.get("driver_preset_name", ""))
        driver_signature = _design_driver_parameter_signature(
            previous_parameters
        )
        if (
            previous.get("preset_recovery_signature") != driver_signature
            and not _design_tab_parameters_match_preset(
                previous_parameters, stable_previous_preset
            )
        ):
            stable_previous_preset = _recover_design_tab_preset(
                previous_parameters
            )
            previous["driver_preset_name"] = stable_previous_preset
        previous["preset_recovery_signature"] = driver_signature
        if stable_previous_preset != "Custom":
            previous_parameters["driver_preset_name"] = stable_previous_preset
        previous["parameters"] = previous_parameters
    requested = tab_by_id[requested_id]
    _apply_loaded_params(dict(requested.get("parameters", {})))
    stable_requested_preset = str(requested.get("driver_preset_name", ""))
    if stable_requested_preset:
        st.session_state["driver_preset_name"] = stable_requested_preset
    # A tab already contains its saved enclosure. Mark that exact driver/load
    # state as synchronized so selecting or deleting a sibling never launches
    # the optimizer again and overwrites the stored design.
    _mark_auto_alignment_synced()
    st.session_state["design_comparison_loaded_id"] = requested_id
    st.session_state["workspace_mode"] = "Box Design"
    st.session_state["design_comparison_tabs"] = tabs


def _apply_library_driver(name: str) -> None:
    """Load one library preset into the current simulation workspace."""
    _end_design_comparison()
    driver = _acoustics.get_driver_preset(name)
    st.session_state["driver_preset_name"] = name
    st.session_state["driver_config"] = "Single driver"
    _apply_driver_preset(driver)
    if _box_strategy_is_auto():
        _apply_suggested_box_for(driver)
        _mark_auto_alignment_synced(driver)
    st.session_state["workspace_mode"] = "Box Design"


def _apply_library_pr(name: str) -> None:
    """Load one passive radiator preset into the current simulation workspace."""
    _end_design_comparison()
    pr = _acoustics.get_passive_radiator_preset(name)
    st.session_state["workspace_mode"] = "Box Design"
    st.session_state["load_type"] = "Bass reflex"
    st.session_state["reflex_resonator_type"] = "Passive radiator"
    st.session_state["pr_preset_name"] = name
    st.session_state["pr_sp_cm2"] = pr.sp_cm2
    st.session_state["pr_fp_hz"] = pr.fp_hz
    st.session_state["pr_qmp"] = pr.qmp
    st.session_state["pr_mmp_g"] = pr.mmp_g
    st.session_state["pr_xmax_mm"] = pr.xmax_mm
    st.session_state["pr_added_mass_g"] = 0.0


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
        elif load_type == "Bandpass 8th order":
            template = _bandpass8_box_from_state()
        elif load_type == "Sealed":
            template = _sealed_box_from_state()
        else:
            template = _box_from_state()
        box = _acoustics.design_space_box(
            driver, load_type, float(pending["x"]), float(pending["y"]), template)
    except Exception:
        logger.exception("Could not apply the atlas point")
        return
    _use_manual_box_strategy()
    _apply_optimized_box(box)
    _mark_auto_alignment_synced(driver)
    st.toast("Applied the atlas box to the design (Manual strategy)")


def _queue_atlas_point(load_type: str, x: float, y: float) -> None:
    """Queue an Atlas box change before Streamlit reruns the full design."""
    st.session_state["atlas_pending_point"] = {
        "load_type": load_type,
        "x": float(x),
        "y": float(y),
    }


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
    if load_type == "Bandpass 8th order":
        return (
            box.q_abs_1, box.q_abs_2, box.q_abs_3,
            box.q_leak_1, box.q_leak_2, box.q_leak_3,
            box.q_port_1, box.q_port_2, box.q_port_3,
        )
    if load_type == "Sealed":
        return (box.q_abs, box.q_leak)
    return (
        box.q_abs_h, box.q_abs_l, box.q_leak_h, box.q_leak_l,
        box.q_port_h, box.q_port_l,
    )


@st.cache_data(show_spinner="Mapping the design space...")
def _design_space_cached(
    ts: _acoustics.DriverTS, load_type: str, losses: tuple, voltage_v: float,
) -> _acoustics.DesignSpaceMap:
    # The map only reads loss factors from the template; geometry is swept.
    if load_type == "Bass reflex":
        template = _acoustics.ReflexBox(
            vb_l=ts.vas_l, fb_hz=ts.fs_hz,
            q_abs=losses[0], q_leak=losses[1], q_port=losses[2])
    elif load_type == "Sealed":
        template = _acoustics.SealedBox(vb_l=ts.vas_l, q_abs=losses[0], q_leak=losses[1])
    elif load_type == "Bandpass 4th order":
        template = _acoustics.Bandpass4Box(
            vs_l=1.0, vp_l=1.0, fp_hz=80.0,
            q_abs_s=losses[0], q_abs_p=losses[1],
            q_leak_s=losses[2], q_leak_p=losses[3], q_port=losses[4])
    elif load_type == "Bandpass 6th order":
        template = _acoustics.Bandpass6Box(
            vr_l=1.0, fr_hz=60.0, vp_l=1.0, fp_hz=80.0,
            q_abs_r=losses[0], q_abs_p=losses[1],
            q_leak_r=losses[2], q_leak_p=losses[3],
            q_port_r=losses[4], q_port_p=losses[5])
    elif load_type == "Bandpass 8th order":
        template = _acoustics.Bandpass8Box(
            v1_l=1.0, f1_hz=100.0, v2_l=1.0, f2_hz=35.0, v3_l=1.0, f3_hz=60.0,
            q_abs_1=losses[0], q_abs_2=losses[1], q_abs_3=losses[2],
            q_leak_1=losses[3], q_leak_2=losses[4], q_leak_3=losses[5],
            q_port_1=losses[6], q_port_2=losses[7], q_port_3=losses[8])
    else:
        template = _acoustics.DccavBox(
            vh_l=1.0, fh_hz=100.0, vl_l=1.0, fl_hz=50.0,
            q_abs_h=losses[0], q_abs_l=losses[1],
            q_leak_h=losses[2], q_leak_l=losses[3],
            q_port_h=losses[4], q_port_l=losses[5])
    return _acoustics.design_space_map(
        ts, load_type=load_type, box_template=template, voltage_v=voltage_v)


def _atlas_frame(space: _acoustics.DesignSpaceMap) -> pd.DataFrame:
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
        chart, width="stretch", key="atlas_chart", on_select="rerun")
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
    st.button(
        "Apply selected box",
        type="primary",
        width="stretch",
        on_click=_queue_atlas_point,
        args=(load_type, x_sel, y_sel),
    )


def _finder_price_currency(df: pd.DataFrame) -> str:
    """Currency used for value ranking: sidebar choice, else the most common."""
    priced = df[df["Price"].notna() & df["Currency"].astype(bool)]
    if priced.empty:
        return ""
    currencies = priced["Currency"].astype(str)
    sidebar = str(st.session_state.get("preset_price_currency", "EUR"))
    if sidebar and (currencies == sidebar).any():
        return sidebar
    return str(currencies.mode().iloc[0])


def _value_sorted_frame(df: pd.DataFrame, currency: str) -> pd.DataFrame:
    """Sort by F3 × price in one currency; rows without it keep F3 order below."""
    scored = df.copy()
    scored["Value"] = [
        _acoustics.price_extension_score(
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


def _finder_optimizer_goals_from_state() -> _acoustics.OptimizationGoals:
    return _acoustics.OptimizationGoals(
        objective=_OPT_OBJECTIVE_LABELS[
            st.session_state.get("finder_objective", "Max extension")
        ],
        max_total_volume_l=float(st.session_state.get("finder_volume_l", 0.0)) or None,
        max_ripple_db=float(st.session_state.get("finder_max_ripple_db", 3.0)),
        max_excursion_ratio=float(st.session_state.get("finder_excursion_ratio", 1.0)),
        max_group_delay_ms=float(st.session_state.get("finder_max_gd_ms", 0.0)) or None,
        min_spl_db=float(st.session_state.get("finder_min_spl_db", 0.0)) or None,
        ripple_max_freq_hz=float(st.session_state.get("finder_max_ripple_freq_hz", 0.0)) or None,
    )


def _finder_load_context() -> tuple[list[str], bool]:
    """Return active Finder loads and whether infinite baffle is the only one."""
    finder_load_types = list(st.session_state.get("finder_load_types", []))
    if not finder_load_types:
        finder_load_types = [str(st.session_state.get("load_type", "DCCAV"))]
    return finder_load_types, finder_load_types == ["Infinite baffle"]


def _finder_result_context_signature(_preset_names: list[str]) -> str:
    """Identify user inputs that can change a Bass Match result set.

    The live catalog and price-file mtimes are deliberately excluded: their
    background refresh must not make a completed result table disappear while
    the user selects a row. A later Run Bass Match always reads fresh data.
    """
    finder_load_types, _ = _finder_load_context()
    context = {
        "ranking_version": _FINDER_RANKING_VERSION,
        "load_types": finder_load_types,
        "volume_l": float(_finder_value("finder_volume_l")),
        "driver_configuration": str(
            _finder_value("finder_driver_configuration")
        ),
        "objective": str(_finder_value("finder_objective")),
        "search_profile": str(_finder_value("finder_search_profile")),
        "reflex_resonator_type": str(
            _finder_value("finder_reflex_resonator_type")
        ),
        "voltage_v": float(_finder_value("finder_voltage")),
        "max_ripple_db": float(_finder_value("finder_max_ripple_db")),
        "max_excursion_ratio": float(
            _finder_value("finder_excursion_ratio")
        ),
        "max_group_delay_ms": float(_finder_value("finder_max_gd_ms")),
        "min_spl_db": float(_finder_value("finder_min_spl_db")),
        "min_mol_f3_db": float(_finder_value("finder_min_mol_f3_db")),
        "max_f3_hz": float(_finder_value("finder_max_f3_hz")),
        "max_mms_g": float(_finder_value("finder_max_mms_g")),
        "max_le_mh": float(_finder_value("finder_max_le_mh")),
        "f_min_hz": float(_finder_value("finder_f_min")),
        "f_max_hz": float(_finder_value("finder_f_max")),
        "points": int(_finder_value("finder_points")),
        "preset_search": str(st.session_state.get("preset_search", "")),
        "preset_source_filter": _json_safe(
            st.session_state.get("preset_source_filter", ["All"])
        ),
        "preset_family_filter": _json_safe(
            st.session_state.get("preset_family_filter", ["All"])
        ),
        "preset_size_filter": _json_safe(
            st.session_state.get("preset_size_filter", ["All"])
        ),
        "preset_class_filter": _json_safe(
            st.session_state.get("preset_class_filter", ["All"])
        ),
        "preset_price_enabled": bool(
            st.session_state.get("preset_price_enabled", False)
        ),
        "preset_max_price": float(
            st.session_state.get("preset_max_price", 0.0) or 0.0
        ),
        "preset_price_currency": str(
            st.session_state.get("preset_price_currency", "EUR")
        ),
    }
    encoded = json.dumps(
        context,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _finder_controls_signature() -> str:
    """Identify Finder controls without ephemeral table-row selection state."""
    context = {
        key: _json_safe(st.session_state.get(key, default))
        for key, default in _FINDER_DEFAULTS.items()
    }
    for key, default in {
        "finder_load_types": [],
        "preset_search": "",
        "preset_source_filter": ["All"],
        "preset_family_filter": ["All"],
        "preset_size_filter": ["All"],
        "preset_class_filter": ["All"],
        "preset_price_enabled": False,
        "preset_max_price": 0.0,
        "preset_price_currency": "EUR",
    }.items():
        context[key] = _json_safe(st.session_state.get(key, default))
    encoded = json.dumps(
        context,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _filter_finder_performance_rows(
    rows: list[dict],
    min_spl_db: float,
    min_mol_f3_db: float,
    max_f3_hz: float,
    max_ripple_db: float = 0.0,
) -> list[dict]:
    """Apply Finder's hard output constraints to simulated candidate rows."""
    filtered = rows
    if min_spl_db > 0.0:
        filtered = [
            row for row in filtered
            if np.isfinite(float(row.get("Peak dB", np.nan)))
            and float(row["Peak dB"]) >= min_spl_db
        ]
    if min_mol_f3_db > 0.0:
        filtered = [
            row for row in filtered
            if np.isfinite(float(row.get("MOL @ F3 dB", np.nan)))
            and float(row["MOL @ F3 dB"]) >= min_mol_f3_db
        ]
    if max_f3_hz > 0.0:
        filtered = [
            row for row in filtered
            if np.isfinite(float(row.get("F3 Hz", np.nan)))
            and float(row["F3 Hz"]) <= max_f3_hz
        ]
    if max_ripple_db > 0.0:
        filtered = [
            row for row in filtered
            if not np.isfinite(float(row.get("Ripple dB", np.nan)))
            or float(row["Ripple dB"]) <= max_ripple_db + 1e-6
        ]
    return filtered


def _finder_candidate_precheck(
    ts: _acoustics.DriverTS,
    load_type: str,
    voltage_v: float,
    min_spl_db: float,
    max_ripple_db: float,
    max_f3_hz: float = 0.0,
    min_mol_f3_db: float = 0.0,
    max_volume_l: float = 0.0,
    fast_prefilter: bool = True,
) -> str | None:
    """Return why a candidate can be rejected before enclosure simulation."""
    if load_type not in {"Sealed", "Infinite baffle"} and ts.xmax_mm <= 0.0:
        return "missing Xmax"
    if min_spl_db > 0.0:
        reference = _acoustics.driver_reference_metrics(ts)
        drive_spl_db = reference.spl_2v83_db + 20.0 * np.log10(
            float(voltage_v) / 2.83
        )
        enclosure_headroom_db = (
            1.0
            if load_type == "Infinite baffle"
            else max(_FINDER_SPL_PREFILTER_HEADROOM_DB, float(max_ripple_db))
        )
        if drive_spl_db + enclosure_headroom_db < float(min_spl_db):
            return "reference SPL"

    if fast_prefilter:
        loaded_fs = _acoustics.panel_loaded_fs_hz(ts)
        # Analytical maximum F3 feasibility check:
        # A sealed or infinite baffle box can never produce an F3 lower than ~0.65 * Fs.
        # A vented / bandpass / DCCAV box cannot credibly reach an F3 lower than Fs / 2.5
        # under realistic damping and volume bounds without extreme response anomalies.
        if max_f3_hz > 0.0:
            if load_type in {"Sealed", "Infinite baffle"}:
                if float(max_f3_hz) < loaded_fs * 0.65:
                    return "F3 infeasible"
            elif loaded_fs > float(max_f3_hz) * 2.5:
                return "F3 infeasible"

        # Analytical MOL @ F3 feasibility check (Maximum acoustic volume displacement):
        # Maximum excursion-limited low-frequency pressure from cone displacement Vd = Sd * Xmax.
        # Half-space acoustic pressure at 1 m from volume displacement Vd at frequency f:
        # P_rms = (2 * pi * f^2 * rho * Vd) / sqrt(2).
        # We allow a generous +12 dB headroom for Helmholtz / quarter-wave resonance reinforcement.
        if min_mol_f3_db > 0.0 and max_f3_hz > 0.0 and ts.xmax_mm > 0.0 and ts.pe_w > 0.0:
            sd_m2 = ts.sd_cm2 / 10000.0
            xmax_m = ts.xmax_mm / 1000.0
            vd_m3 = sd_m2 * xmax_m
            if vd_m3 > 0.0:
                f_eval = float(max_f3_hz)
                p_rms = (2.0 * np.pi * (f_eval**2) * 1.2041 * vd_m3) / 1.41421356
                spl_excursion_cone = 20.0 * np.log10(max(p_rms, 1e-12) / 20e-6)
                headroom_db = 12.0 if load_type != "Infinite baffle" else 0.0
                if spl_excursion_cone + headroom_db < float(min_mol_f3_db):
                    return "MOL infeasible"

    return None


@cache
def _finder_driver_identity(name: str) -> tuple[str, str, str]:
    """Return one physical brand/model/impedance identity across catalogs."""
    try:
        info = _acoustics.driver_preset_info(name)
        ts = _acoustics.get_driver_preset(name)
        return _presets._external_catalog_identity(
            info.brand or "Other",
            info.part_number or info.model or name,
            ts,
            impedance_text=info.model,
        )
    except Exception:
        normalized = re.sub(r"[^a-z0-9]+", "", name.casefold())
        return "unknown", normalized, ""


@lru_cache(maxsize=32768)
def _finder_preset_preference(name: str) -> tuple[int, int, float, str]:
    """Prefer Load Forge provenance, then an available lower price."""
    try:
        info = _acoustics.driver_preset_info(name)
        category = _acoustics.driver_preset_provenance_category(name)
        price = float(info.price) if info.price is not None else float("inf")
    except Exception:
        category = "Other"
        price = float("inf")
    source_priority = {
        "Load Forge database": 0,
        "LSDB": 1,
        "VituixCAD": 2,
        "Speaker Box Lite": 3,
    }.get(category, 4)
    return (
        source_priority,
        0 if np.isfinite(price) else 1,
        price,
        name.casefold(),
    )


@lru_cache(maxsize=128)
def _deduplicate_finder_preset_names_tuple(
    preset_names: tuple[str, ...],
) -> tuple[tuple[str, ...], int]:
    """Choose one preferred catalog record for each physical driver."""
    chosen: dict[tuple[str, str, str], str] = {}
    for name in preset_names:
        identity = _finder_driver_identity(name)
        previous = chosen.get(identity)
        if (
            previous is None
            or _finder_preset_preference(name)
            < _finder_preset_preference(previous)
        ):
            chosen[identity] = name
    unique_names = tuple(chosen.values())
    return unique_names, len(preset_names) - len(unique_names)


def _deduplicate_finder_preset_names(
    preset_names: list[str],
) -> tuple[list[str], int]:
    """Choose one preferred catalog record for each physical driver."""
    unique_tuple, duplicate_count = _deduplicate_finder_preset_names_tuple(
        tuple(preset_names)
    )
    return list(unique_tuple), duplicate_count


def _deduplicate_finder_result_rows(
    rows: list[dict],
) -> tuple[list[dict], int]:
    """Keep one preferred catalog result per physical driver, load topology and resonator."""
    unique_rows: list[dict] = []
    seen: set[tuple[tuple[str, str, str], str, str]] = set()
    for row in rows:
        identity = _finder_driver_identity(str(row.get("Driver", "")))
        load_type = str(row.get("Load", ""))
        resonator = str(row.get("Resonator", ""))
        key = (identity, load_type, resonator)
        if key in seen:
            continue
        seen.add(key)
        unique_rows.append(row)
    return unique_rows, len(rows) - len(unique_rows)


@lru_cache(maxsize=128)
def _prefilter_finder_candidate_pools(
    preset_names: tuple[str, ...],
    load_types: tuple[str, ...],
    voltage_v: float,
    min_spl_db: float,
    max_ripple_db: float,
    max_f3_hz: float,
    min_mol_f3_db: float,
    max_volume_l: float,
    fast_prefilter: bool,
    driver_configuration: str,
    pool_fingerprint: tuple,
) -> tuple[tuple[tuple[str, tuple[str, ...]], ...], dict[str, int]]:
    """Build per-load candidate pools using only pre-simulation information."""
    del pool_fingerprint  # Cache key only: invalidates when code/catalog changes.
    pools = {load_type: [] for load_type in load_types}
    rejected_by_reason = {
        "reference SPL": 0,
        "missing Xmax": 0,
        "invalid T/S": 0,
        "F3 infeasible": 0,
        "MOL infeasible": 0,
    }
    eligible_drivers: set[str] = set()
    for name in preset_names:
        try:
            ts = _acoustics.apply_driver_configuration(
                _acoustics.get_driver_preset(name),
                driver_configuration,
            )
        except Exception:
            rejected_by_reason["invalid T/S"] += len(load_types)
            continue
        for load_type in load_types:
            try:
                reason = _finder_candidate_precheck(
                    ts,
                    load_type,
                    voltage_v,
                    min_spl_db,
                    max_ripple_db,
                    max_f3_hz=max_f3_hz,
                    min_mol_f3_db=min_mol_f3_db,
                    max_volume_l=max_volume_l,
                    fast_prefilter=fast_prefilter,
                )
            except Exception:
                reason = "invalid T/S"
            if reason is not None:
                rejected_by_reason[reason] = rejected_by_reason.get(reason, 0) + 1
                continue
            pools[load_type].append(name)
            eligible_drivers.add(name)
    pool_rows = tuple(
        (load_type, tuple(pools[load_type]))
        for load_type in load_types
    )
    total_simulations = len(preset_names) * len(load_types)
    eligible_simulations = sum(len(names) for names in pools.values())
    return pool_rows, {
        "input_drivers": len(preset_names),
        "eligible_drivers": len(eligible_drivers),
        "total_simulations": total_simulations,
        "eligible_simulations": eligible_simulations,
        "rejected_simulations": total_simulations - eligible_simulations,
        "rejected_spl": rejected_by_reason.get("reference SPL", 0),
        "rejected_xmax": rejected_by_reason.get("missing Xmax", 0),
        "rejected_invalid": rejected_by_reason.get("invalid T/S", 0),
        "rejected_f3": rejected_by_reason.get("F3 infeasible", 0),
        "rejected_mol": rejected_by_reason.get("MOL infeasible", 0),
    }


def _finder_prefilter(
    preset_names: list[str],
) -> tuple[dict[str, list[str]], dict[str, int]]:
    """Return current per-load pools and their pre-simulation counts."""
    finder_load_types, _ = _finder_load_context()
    unique_names, duplicate_rows = _deduplicate_finder_preset_names(
        preset_names
    )
    pool_rows, stats = _prefilter_finder_candidate_pools(
        tuple(unique_names),
        tuple(finder_load_types),
        float(_finder_value("finder_voltage")),
        float(st.session_state.get("finder_min_spl_db", 0.0) or 0.0),
        float(st.session_state.get("finder_max_ripple_db", 0.0) or 0.0),
        float(st.session_state.get("finder_max_f3_hz", 0.0) or 0.0),
        float(st.session_state.get("finder_min_mol_f3_db", 0.0) or 0.0),
        float(_finder_value("finder_volume_l")),
        bool(st.session_state.get("finder_fast_prefilter", True)),
        str(_finder_value("finder_driver_configuration")),
        _finder_pool_fingerprint(1),
    )
    duplicate_simulations = duplicate_rows * len(finder_load_types)
    stats = {
        **stats,
        "input_drivers": len(preset_names),
        "unique_drivers": len(unique_names),
        "duplicate_rows": duplicate_rows,
        "total_simulations": (
            stats["total_simulations"] + duplicate_simulations
        ),
        "rejected_simulations": (
            stats["rejected_simulations"] + duplicate_simulations
        ),
        "duplicate_simulations": duplicate_simulations,
    }
    return {
        load_type: list(names)
        for load_type, names in pool_rows
    }, stats


def _render_find_driver_target_sidebar() -> None:
    """Render the enclosure conditions used for every Finder candidate."""
    finder_load_types, only_infinite_baffle = _finder_load_context()
    _finder_selectbox(
        "Driver configuration",
        list(_acoustics.DRIVER_CONFIGURATIONS),
        key="finder_driver_configuration",
        help="Rank every candidate as one driver; a 2–8-driver series, "
             "parallel or mixed array; or an isobaric array up to 16 total drivers.",
    )
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


def _run_find_driver_search(
    filtered_preset_names: list[str],
    context_preset_names: list[str] | None = None,
) -> None:
    """Rank the filtered candidates from the current Finder sidebar state."""
    price_enabled = bool(st.session_state.get("preset_price_enabled", False))
    price_currency = str(st.session_state.get("preset_price_currency", "EUR"))
    max_price = float(st.session_state.get("preset_max_price", 0.0) or 0.0)
    finder_load_types = list(st.session_state.get("finder_load_types", []))
    if not finder_load_types:
        finder_load_types = [str(st.session_state.get("load_type", "DCCAV"))]
    finder_volume_l = float(_finder_value("finder_volume_l"))
    finder_driver_configuration = str(
        _finder_value("finder_driver_configuration")
    )
    candidate_pools, prefilter_stats = _finder_prefilter(
        filtered_preset_names
    )
    scan_count = len(filtered_preset_names)
    eligible_total = prefilter_stats["eligible_simulations"]
    progress_total = max(eligible_total, 1)
    t_start = time.perf_counter()
    with st.container(key="finder_match_progress"):
        progress = st.progress(0.0)
        progress_text = st.empty()
        progress_text.caption(
            f"Bass Match · 0/{eligible_total} simulations"
            f" · {prefilter_stats['rejected_simulations']} skipped a priori"
        )
    st.session_state.pop("_finder_match_completion", None)
    all_rows: list[dict] = []
    load_run_stats: dict[str, dict[str, int]] = {}
    completed_offset = 0
    for lt in finder_load_types:
        load_preset_names = candidate_pools.get(lt, [])
        load_scan_count = len(load_preset_names)
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
            tuple(load_preset_names),
            ranking_load_type,
            finder_volume_l,
            float(_finder_value("finder_voltage")),
            float(_finder_value("finder_f_min")),
            float(_finder_value("finder_f_max")),
            min(int(_finder_value("finder_points")), 80)
            if os.getenv("K_SERVICE") else int(_finder_value("finder_points")),
            load_scan_count,
        )
        finder_search_profile = str(_finder_value("finder_search_profile"))
        if load_scan_count > 8:
            batch_rows = _batch_rank_presets_parallel(
                *rank_args,
                goals,
                progress,
                progress_text,
                completed_offset,
                progress_total,
                finder_driver_configuration,
                finder_search_profile,
            )
            # A worker can hold a stale external-catalog module after a
            # Streamlit reload. If the whole pool returns no rows, retry this
            # load serially in the current process before reporting failure.
            if not batch_rows and load_scan_count:
                batch_rows = _batch_rank_presets_with_progress(
                    tuple(load_preset_names),
                    ranking_load_type,
                    finder_volume_l,
                    float(_finder_value("finder_voltage")),
                    float(_finder_value("finder_f_min")),
                    float(_finder_value("finder_f_max")),
                    int(_finder_value("finder_points")),
                    load_scan_count,
                    goals,
                    progress,
                    progress_text,
                    completed_offset,
                    progress_total,
                    finder_driver_configuration,
                    finder_search_profile,
                )
        else:
            batch_rows = _batch_rank_presets_with_progress(
                *rank_args,
                goals,
                progress,
                progress_text,
                completed_offset,
                progress_total,
                finder_driver_configuration,
                finder_search_profile,
            )
        load_run_stats[lt] = {
            "attempted": load_scan_count,
            "usable": len(batch_rows),
        }
        if lt == "Bass reflex":
            for row in batch_rows:
                row["_load_type"] = "Bass reflex"
                row["Resonator"] = _RESONATOR_PR if uses_pr else _RESONATOR_PORT
        all_rows.extend(batch_rows)
        completed_offset += load_scan_count
    min_spl_db = float(st.session_state.get("finder_min_spl_db", 0.0) or 0.0)
    min_mol_f3_db = float(
        st.session_state.get("finder_min_mol_f3_db", 0.0) or 0.0
    )
    max_f3_hz = float(
        st.session_state.get("finder_max_f3_hz", 0.0) or 0.0
    )
    max_ripple_db = float(
        st.session_state.get("finder_max_ripple_db", 0.0) or 0.0
    )
    all_rows = _filter_finder_performance_rows(
        all_rows, min_spl_db, min_mol_f3_db, max_f3_hz, max_ripple_db
    )
    # Apply the active price constraint to the final ranked rows as well as
    # to the library pool.  This keeps stale/cached simulations from leaking
    # unpriced drivers (or drivers above the limit) into the results table
    # after the user changes the maximum price.
    rates = _current_exchange_rates()[0]
    filtered_rows = []
    for row in all_rows:
        driver_name = str(row.get("Driver", ""))
        display_currency = price_currency or _driver_preset_currency(driver_name)
        normalized_price = _normalized_preset_price(
            driver_name, display_currency, rates
        )
        has_price = (
            normalized_price is not None
            and np.isfinite(float(normalized_price))
        )
        if price_enabled and (
            not has_price or float(normalized_price) > max_price
        ):
            continue
        # Keep table/export consistent with the catalog whenever a price is
        # available, independently of whether the max-price filter is on.
        if has_price:
            row["Price"] = float(normalized_price)
            row["Currency"] = display_currency
        filtered_rows.append(row)
    all_rows = filtered_rows
    all_rows = _acoustics.sort_ranked_rows(all_rows)
    all_rows, collapsed_result_rows = _deduplicate_finder_result_rows(
        all_rows
    )
    t_end = time.perf_counter()
    elapsed_s = t_end - t_start
    elapsed_ms_per_simulation = (
        (elapsed_s * 1000) / eligible_total
        if eligible_total > 0
        else 0.0
    )
    unique_driver_total = int(prefilter_stats["unique_drivers"])
    elapsed_ms_per_driver = (
        (elapsed_s * 1000) / unique_driver_total
        if unique_driver_total > 0
        else 0.0
    )
    simulations_per_second = (
        eligible_total / elapsed_s if elapsed_s > 0.0 else 0.0
    )
    completion_text = (
        f"Bass Match complete · {eligible_total} simulations after pre-filtering "
        f"{prefilter_stats['rejected_simulations']} · "
        f"{len(all_rows)} unique drivers · "
        f"{collapsed_result_rows} alternate load rows collapsed · "
        f"Elapsed: {elapsed_s:.1f} s "
        f"({elapsed_ms_per_simulation:.1f} ms/simulation)"
    )
    progress.progress(1.0)
    progress_text.empty()
    progress.empty()
    st.session_state["_finder_match_completion"] = completion_text
    st.session_state["batch_results"] = all_rows
    st.session_state["batch_search_completed"] = True
    evals_per_candidate = _ranking.finder_optimizer_evaluation_limit(profile=finder_search_profile)
    # Each candidate undergoes full compass evaluations + narrow F3 refinement passes + finalist adaptive grid verification
    refine_mult = 1.25 if evals_per_candidate >= 30 else 1.0
    actual_acoustic_simulations = int(eligible_total * evals_per_candidate * refine_mult)

    st.session_state["finder_last_run_stats"] = {
        "elapsed_s": elapsed_s,
        "milliseconds_per_simulation": elapsed_ms_per_simulation,
        "milliseconds_per_driver": elapsed_ms_per_driver,
        "simulations_per_second": simulations_per_second,
        "simulations": eligible_total,
        "actual_acoustic_simulations": actual_acoustic_simulations,
        "evaluations_per_driver": evals_per_candidate,
        "search_profile": finder_search_profile,
        "unique_drivers": unique_driver_total,
        "skipped_a_priori": int(prefilter_stats["rejected_simulations"]),
        "loads": load_run_stats,
        "completed_at": datetime.now(UTC).isoformat(),
    }
    st.session_state["batch_result_context"] = (
        tuple(finder_load_types),
        finder_volume_l,
        scan_count,
        bool(_finder_optimizer_goals_from_state()),
        str(st.session_state.get("finder_objective", "Max extension")),
        str(st.session_state.get("finder_reflex_resonator_type", _RESONATOR_PORT)),
        min_spl_db,
        min_mol_f3_db,
        float(st.session_state.get("finder_max_mms_g", 0.0) or 0.0),
        float(st.session_state.get("finder_max_le_mh", 0.0) or 0.0),
        _FINDER_RANKING_VERSION,
        prefilter_stats["eligible_simulations"],
        prefilter_stats["total_simulations"],
        prefilter_stats["rejected_simulations"],
        collapsed_result_rows,
        _finder_result_context_signature(
            context_preset_names
            if context_preset_names is not None
            else filtered_preset_names
        ),
        _FINDER_CONTEXT_FILTERED_POOL_VERSION,
    )
    st.session_state.pop("_restored_bass_match_controls_signature", None)
    _invalidate_bass_match_results_signature()


def _render_find_driver_goal_sidebar() -> None:
    """Render Finder objective and constraints as the second workflow step."""
    finder_load_types, only_infinite_baffle = _finder_load_context()
    only_passive_radiator = (
        finder_load_types == ["Bass reflex"]
        and _reflex_uses_passive_radiator(finder=True)
    )
    _finder_number_input(
        "Maximum F3 (Hz, 0 = off)",
        min_value=0.0,
        max_value=500.0,
        step=1.0,
        key="finder_max_f3_hz",
        help="Exclude simulated designs whose F3 is above this hard limit; "
             "0 disables the constraint.",
    )
    _finder_number_input(
        "Minimum MOL at F3 (dB, 0 = off)",
        min_value=0.0,
        max_value=150.0,
        step=0.5,
        key="finder_min_mol_f3_db",
        help="Require the excursion/thermal limited maximum output at the "
             "candidate's F3 to reach this level; 0 disables.",
    )
    if only_infinite_baffle:
        st.caption(
            "Infinite baffle has no enclosure to optimize; candidates are "
            "ranked on their free-air response."
        )
    else:
        _finder_number_input(
            "Minimum SPL (dB, 0 = off)", min_value=0.0, max_value=150.0,
            step=0.5, key="finder_min_spl_db",
            help="Require at least this simulated peak SPL at the comparison "
                 "voltage. A conservative reference-sensitivity check first "
                 "removes candidates that cannot plausibly reach it; the final "
                 "hard check uses the simulated response. 0 disables.",
        )
        if only_passive_radiator:
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
                "Allowed response ripple (dB)", min_value=0.0, max_value=12.0,
                step=0.5, key="finder_max_ripple_db",
                help="Maximum peak-to-valley variation in the evaluated low-frequency passband.",
            )
            _finder_number_input(
                "Ripple frequency ceiling (Hz, 0 = off)", min_value=0.0, max_value=500.0,
                step=5.0, key="finder_max_ripple_freq_hz",
                help="Ignore response variation above this frequency (e.g. 70-100 Hz for subwoofers). "
                     "Uses sparse sampling above this ceiling for faster search. 0 evaluates the full passband.",
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
    with st.expander("Advanced driver filters"):
        _finder_number_input(
            "Maximum Mms (g, 0 = off)",
            min_value=0.0,
            max_value=2000.0,
            step=1.0,
            key="finder_max_mms_g",
            help="Keep only drivers whose published moving mass Mms is no "
                 "greater than this value. Candidates without Mms are excluded "
                 "while the limit is active; 0 disables.",
        )
        _finder_number_input(
            "Maximum Le (mH, 0 = off)",
            min_value=0.0,
            max_value=20.0,
            step=0.01,
            format="%.3f",
            key="finder_max_le_mh",
            help="Keep only drivers whose published nominal/1 kHz voice-coil "
                 "inductance is no greater than this value. Le10k is not "
                 "substituted; candidates without Le are excluded while the "
                 "limit is active. 0 disables.",
        )
        st.checkbox(
            "⚡ Fast T/S pre-screening",
            key="finder_fast_prefilter",
            help="Analytically exclude drivers that cannot physically achieve the requested F3 or MOL before running full enclosure simulations, accelerating search speed by up to 10×.",
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
    "Mms g": ".1f", "Le10k mH": ".2f",
}


def _finder_total_volume_l(row: dict | pd.Series) -> float:
    """Return one comparable enclosure-volume value for a Finder result."""
    load_type = str(row.get("Load", row.get("_load_type", "")))

    def finite_value(name: str) -> float:
        try:
            value = float(row.get(name, np.nan))
        except (TypeError, ValueError):
            return float("nan")
        return value if np.isfinite(value) else float("nan")

    if load_type in {"Bass reflex", "Sealed"}:
        return finite_value("Vb L")
    if load_type == "Bandpass 4th order":
        values = (finite_value("Vs L"), finite_value("Vp L"))
    elif load_type == "Bandpass 6th order":
        values = (finite_value("Vr L"), finite_value("Vp L"))
    elif load_type == "Bandpass 8th order":
        values = (finite_value("V1 L"), finite_value("V2 L"), finite_value("V3 L"))
    elif load_type == "DCCAV":
        values = (finite_value("Vh L"), finite_value("Vl L"))
    else:
        return float("nan")
    return float(sum(values)) if all(np.isfinite(values)) else float("nan")


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


def _refresh_finder_result_catalog_metadata(rows: object) -> list[dict]:
    """Fill metadata gaps in saved Finder rows from the current catalog.

    Finder results are persisted in projects and Streamlit session state, so
    rows calculated before a catalog-metadata fix can outlive the code that
    produced them.  Refreshing nominal size is safe without re-simulating: it
    is display/filter metadata and does not enter the acoustic solver.
    """
    if not isinstance(rows, (list, tuple)):
        return []
    refreshed: list[dict] = []
    for saved in rows:
        if not isinstance(saved, dict):
            continue
        row = dict(saved)
        if _table_value_missing(row.get("Size in")):
            try:
                size_in = _acoustics.driver_preset_info(
                    str(row.get("Driver", ""))
                ).size_in
            except ValueError:
                size_in = None
            if size_in is not None:
                row["Size in"] = float(size_in)
        refreshed.append(row)
    return refreshed


@st.cache_data(show_spinner=False)
def _driver_library_frame(
    # Cache busted to reflect nominal-size preservation in imported catalogs.
    preset_names: tuple[str, ...],
    target_currency: str = "",
    exchange_rates: tuple[tuple[str, float], ...] = (),
) -> pd.DataFrame:
    """Build the complete filtered driver library table once per filter set."""
    rates = dict(exchange_rates)
    rows = []
    for name in preset_names:
        try:
            info = _acoustics.driver_preset_info(name)
            ts_p = _acoustics.get_driver_preset(name)
            ref = _acoustics.driver_reference_metrics(ts_p)
            price = (
                _pricing.convert_price(
                    info.price, info.currency, target_currency, rates
                )
                if target_currency
                else info.price
            )
            rows.append({
                "Driver": name,
                "Manufacturer": info.brand,
                "Part number": info.part_number or info.model or name,
                "Nominal in": info.size_in,
                "Sd cm²": ts_p.sd_cm2,
                "Effective Ø in": (
                    np.sqrt(4.0 * ts_p.sd_cm2 / np.pi) / 2.54
                ),
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
                "Category": _driver_preset_source(name),
                "Source": info.source,
            })
        except Exception:
            manufacturer, part_number = _driver_preset_identity_fields(name)
            rows.append({
                "Driver": name,
                "Manufacturer": manufacturer,
                "Part number": part_number,
            })
    library_columns = [
        "Driver", "Manufacturer", "Part number", "Nominal in", "Sd cm²",
        "Effective Ø in",
        "Fs Hz", "Qts", "Vas L", "SPL dB",
        "Price", "Currency", "Category", "Source",
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


def _selected_library_preset_names(
    filtered_preset_names: list[str],
) -> list[str]:
    """Return the currently selected rows from the visible candidate pool."""
    shown_names = filtered_preset_names[:_LIBRARY_TABLE_MAX_ROWS]
    table_state = st.session_state.get("finder_driver_library_table")
    if not isinstance(table_state, dict):
        return []
    selected_rows = table_state.get("selection", {}).get("rows", [])
    return [
        shown_names[index]
        for index in selected_rows
        if isinstance(index, int) and 0 <= index < len(shown_names)
    ]


def _finder_filter_summary(
    key: str,
    aliases: dict[str, str] | None = None,
) -> str:
    """Return a compact, truthful summary for one library filter group."""
    raw_value = st.session_state.get(key, ["All"])
    values = [raw_value] if isinstance(raw_value, str) else list(raw_value)
    if not values or "All" in values:
        return "Any"
    if _PRESET_FILTER_NONE in values:
        return "None"
    normalized = [
        (aliases or {}).get(str(value), str(value))
        for value in values
    ]
    if len(normalized) <= 2:
        return " + ".join(normalized)
    return f"{len(normalized)} selected"


def _finder_brief_constraints(
    selected_preset_count: int,
) -> list[tuple[str, str]]:
    """Expose every operative Bass Match input in the compact main brief."""
    finder_load_types, only_infinite_baffle = _finder_load_context()
    uses_reflex = "Bass reflex" in finder_load_types
    uses_pr = uses_reflex and _reflex_uses_passive_radiator(finder=True)
    only_pr = finder_load_types == ["Bass reflex"] and uses_pr
    optimizer_applies = not only_infinite_baffle and not only_pr

    display_loads = [
        "Reflex (PR)" if item == "Bass reflex" and uses_pr else item
        for item in finder_load_types
    ]
    load_summary = (
        " + ".join(display_loads)
        if len(display_loads) <= 2
        else f"{len(display_loads)} selected"
    )

    def upper_limit(key: str, unit: str, *, off_at_zero: bool = True) -> str:
        value = float(_finder_value(key))
        if off_at_zero and value <= 0.0:
            return "Off"
        return f"≤ {value:g} {unit}"

    def lower_limit(key: str, unit: str) -> str:
        value = float(_finder_value(key))
        return "Off" if value <= 0.0 else f"≥ {value:g} {unit}"

    search_query = str(st.session_state.get("preset_search", "")).strip()
    price_enabled = bool(st.session_state.get("preset_price_enabled", False))
    price_currency = str(st.session_state.get("preset_price_currency", "EUR"))
    max_price = float(st.session_state.get("preset_max_price", 0.0) or 0.0)
    objective = str(_finder_value("finder_objective"))
    if not optimizer_applies:
        objective = "N/A"
    elif uses_pr:
        objective = f"{objective} · PR starter"

    constraints = [
        ("Loads", load_summary),
        ("Configuration", str(_finder_value("finder_driver_configuration"))),
        (
            "Resonator",
            str(_finder_value("finder_reflex_resonator_type"))
            if uses_reflex else "N/A",
        ),
        (
            "Maximum box",
            "N/A" if only_infinite_baffle
            else upper_limit("finder_volume_l", "L", off_at_zero=False),
        ),
        ("Voltage", f"{float(_finder_value('finder_voltage')):g} V"),
        ("Optimization", objective),
        ("Minimum SPL", lower_limit("finder_min_spl_db", "dB")),
        ("Minimum MOL @ F3", lower_limit("finder_min_mol_f3_db", "dB")),
        ("Maximum F3", upper_limit("finder_max_f3_hz", "Hz")),
        (
            "Maximum ripple",
            upper_limit("finder_max_ripple_db", "dB", off_at_zero=False)
            if optimizer_applies else "N/A",
        ),
        (
            "Maximum excursion",
            upper_limit("finder_excursion_ratio", "× Xmax")
            if optimizer_applies else "N/A",
        ),
        (
            "Maximum delay",
            upper_limit("finder_max_gd_ms", "ms")
            if optimizer_applies else "N/A",
        ),
        ("Maximum Mms", upper_limit("finder_max_mms_g", "g")),
        ("Maximum Le", upper_limit("finder_max_le_mh", "mH")),
        ("Search", search_query or "Any"),
        (
            "Provenance",
            _finder_filter_summary(
                "preset_source_filter",
                _PRESET_SOURCE_FILTER_ALIASES,
            ),
        ),
        ("Manufacturer", _finder_filter_summary("preset_family_filter")),
        ("Size", _finder_filter_summary("preset_size_filter")),
        (
            "Class",
            _finder_filter_summary(
                "preset_class_filter",
                _PRESET_CLASS_FILTER_ALIASES,
            ),
        ),
        (
            "Maximum price",
            f"≤ {max_price:g} {price_currency}".strip()
            if price_enabled else "Off",
        ),
        (
            "Evaluation range",
            f"{float(_finder_value('finder_f_min')):g}–"
            f"{float(_finder_value('finder_f_max')):g} Hz",
        ),
        ("Profile", str(_finder_value("finder_search_profile"))),
        ("Resolution", f"{int(_finder_value('finder_points'))} points"),
        ("Results shown", "All usable"),
        (
            "Candidate pool",
            f"{selected_preset_count} selected"
            if selected_preset_count else "All filtered",
        ),
    ]
    return constraints


def _render_finder_constraint_grid(
    constraints: list[tuple[str, str]],
) -> None:
    cards = "".join(
        "<div class='finder-constraint' "
        f"title='{html.escape(label)}: {html.escape(value)}'>"
        f"<div class='finder-constraint-label'>{html.escape(label)}</div>"
        f"<div class='finder-constraint-value'>{html.escape(value)}</div>"
        "</div>"
        for label, value in constraints
    )
    st.markdown(
        f"<div class='finder-constraint-grid'>{cards}</div>",
        unsafe_allow_html=True,
    )


def _render_finder_run_statistics() -> None:
    """Keep the last measured Bass Match throughput visible and persistent."""
    stats = st.session_state.get("finder_last_run_stats")
    if not isinstance(stats, dict) or not stats:
        return
    try:
        elapsed_s = float(stats.get("elapsed_s", 0.0))
        ms_per_driver = float(stats.get("milliseconds_per_driver", 0.0))
        simulations_per_second = float(
            stats.get("simulations_per_second", 0.0)
        )
        unique_drivers = int(stats.get("unique_drivers", 0))
        simulations = int(stats.get("simulations", 0))
        actual_sims = int(stats.get("actual_acoustic_simulations", 0))
        evals_per_drv = int(stats.get("evaluations_per_driver", 60))
        profile_name = str(stats.get("search_profile", "Standard"))
    except (TypeError, ValueError):
        return

    actual_str = f" · **{actual_sims:,}** physical simulations ({evals_per_drv} evals/drv · *{profile_name}*)" if actual_sims > 0 else ""
    credit_mult = _ranking.search_profile_credit_multiplier(profile_name)
    credits_consumed = simulations * credit_mult
    st.markdown(
        "**Last calculation** · "
        f"{elapsed_s:.2f} s total · "
        f"{ms_per_driver:.1f} ms/driver · "
        f"**{credits_consumed:,} credits consumed** ({simulations:,} candidates · {credit_mult}× {profile_name})"
        f"{actual_str}"
    )


def _render_bass_match_hero(
    filtered_preset_names: list[str],
) -> list[str]:
    """Render the Finder promise, live brief and single primary action."""
    selected_preset_names = _selected_library_preset_names(
        filtered_preset_names
    )
    match_preset_names = (
        selected_preset_names
        if selected_preset_names
        else filtered_preset_names
    )
    candidate_pools, prefilter_stats = _finder_prefilter(
        match_preset_names
    )
    prequalified_names = {
        name
        for names in candidate_pools.values()
        for name in names
    }
    constraints = _finder_brief_constraints(len(selected_preset_names))

    acc = _get_current_user_account()
    is_admin = bool(acc.is_admin) if acc else False
    credits_balance = acc.credits_balance if acc else 2500
    credits_quota = acc.credits_monthly_quota if acc else 2500

    finder_search_profile = str(_finder_value("finder_search_profile"))
    credit_mult = _ranking.search_profile_credit_multiplier(finder_search_profile)
    run_credits = int(prefilter_stats["eligible_simulations"] * credit_mult)
    # Enforce strict blocking only in SaaS mode for non-admin accounts
    enforce_credits = _SAAS_SETTINGS.enabled and _CURRENT_SAAS_USER is not None and not is_admin
    has_enough_credits = (not enforce_credits) or (credits_balance >= run_credits or run_credits == 0)

    run_requested = False
    with st.container(border=True, key="bass_match_brief"):
        h_col1, h_col2 = st.columns([2.5, 1.5], vertical_alignment="center")
        with h_col1:
            st.markdown("#### Bass Match · Your bass brief")
        with h_col2:
            st.markdown(
                "<div style='text-align: right;'><span class='lf-quota-pill'>"
                f"Credits available: <strong>{credits_balance:,} / {credits_quota:,}</strong>"
                f" · This run: <strong>{run_credits:,} credits</strong>"
                f" <small>({prefilter_stats['eligible_simulations']:,} drv · {credit_mult}× {finder_search_profile})</small>"
                "</span></div>",
                unsafe_allow_html=True,
            )
        b1, b2, b3, b4 = st.columns(
            [1.2, 1.2, 1.2, 1.2],
            vertical_alignment="center",
        )
        b1.metric(
            "Pre-qualified",
            f"{len(prequalified_names):,} / "
            f"{prefilter_stats['unique_drivers']:,}",
            help="Drivers that pass cheap pre-simulation checks for at least "
            "one active load.",
        )
        b2.metric(
            "Ready simulations",
            f"{prefilter_stats['eligible_simulations']:,}",
        )
        b3.metric(
            "Skipped a priori",
            f"{prefilter_stats['rejected_simulations']:,}",
        )
        b4.metric(
            "Duplicates removed",
            f"{prefilter_stats['duplicate_rows']:,}",
        )
        _render_finder_constraint_grid(constraints)
        if match_preset_names and not prequalified_names:
            st.warning(
                "No driver passes the pre-simulation checks. Lower Minimum "
                "SPL, change the driver configuration or relax the library filters."
            )
        if not has_enough_credits:
            st.error(
                f"⚠️ Insufficient credits: this scan requires **{run_credits:,} credits**, but your balance is **{credits_balance:,} credits**. "
                "Refine your filters, choose fewer drivers, or upgrade your plan."
            )
    _render_finder_run_statistics()
    run_requested = st.button(
        _FINDER_CTA_LABEL,
        type="primary",
        width="stretch",
        disabled=_finder_search_blocked(filtered_preset_names) or not has_enough_credits,
        key="finder_run_search_main",
    )
    if run_requested:
        if acc and run_credits > 0:
            _ACCOUNT_STORE.deduct_credits(acc.email or acc.uid, run_credits)
        _run_find_driver_search(match_preset_names, filtered_preset_names)
    return match_preset_names


@st.cache_data(show_spinner=False)
def _passive_radiator_library_frame(search: str = "") -> pd.DataFrame:
    rows = []
    for name in _acoustics.passive_radiator_preset_names():
        pr = _acoustics.get_passive_radiator_preset(name)
        if search:
            query = search.casefold().strip()
            if (
                query not in pr.name.casefold()
                and query not in pr.brand.casefold()
                and query not in pr.model.casefold()
            ):
                continue
        rows.append({
            "Radiator": pr.name,
            "Brand": pr.brand,
            "Model": pr.model,
            "Sp cm²": pr.sp_cm2,
            "Fp Hz": pr.fp_hz,
            "Qmp": pr.qmp,
            "Mmp g": pr.mmp_g,
            "Xmax mm": pr.xmax_mm,
            "Source": pr.source,
            "URL": pr.url,
        })
    columns = [
        "Radiator", "Brand", "Model", "Sp cm²", "Fp Hz", "Qmp", "Mmp g", "Xmax mm", "Source", "URL",
    ]
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows)


def _render_passive_radiator_library() -> None:
    """Render the catalog of passive radiators in a selectable table."""
    st.caption(
        "Select one passive radiator to apply it directly to Box Design (Bass reflex + PR resonator)."
    )
    search_val = st.text_input(
        "Filter passive radiators",
        key="finder_pr_library_search",
        placeholder="Search brand or model (Dayton, SB Acoustics, PURIFI, SEAS, ...)",
    )
    pr_df = _passive_radiator_library_frame(search_val)
    st.caption(f"{len(pr_df)} passive radiators available in the catalog.")
    table_state = st.dataframe(
        pr_df,
        width="stretch",
        height=680,
        hide_index=True,
        key="finder_pr_library_table",
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "Radiator": None,
            "Sp cm²": st.column_config.NumberColumn("Sp (cm²)", format="%.1f"),
            "Fp Hz": st.column_config.NumberColumn("Fp (Hz)", format="%.1f"),
            "Qmp": st.column_config.NumberColumn("Qmp", format="%.2f"),
            "Mmp g": st.column_config.NumberColumn("Mmp (g)", format="%.1f"),
            "Xmax mm": st.column_config.NumberColumn("Xmax (mm)", format="%.1f"),
            "URL": st.column_config.LinkColumn("Product Link"),
        },
    )
    selected_rows = getattr(table_state.selection, "rows", []) if table_state else []
    if not selected_rows:
        with st.container(key="emerald_info_pr_library_selection"):
            st.info("Select a passive radiator row to apply it to Box Design.")
        return

    selected_index = int(selected_rows[0])
    if not 0 <= selected_index < len(pr_df):
        return
    selected_name = str(pr_df.iloc[selected_index]["Radiator"])
    st.button(
        f"Apply {selected_name} to Box Design",
        type="primary",
        width="stretch",
        key="finder_use_library_pr",
        on_click=_apply_library_pr,
        args=(selected_name,),
    )


def _render_driver_library(filtered_preset_names: list[str]) -> None:
    """Render every filtered driver in a scrollable, selectable library."""
    cat_mode = st.radio(
        "Library Catalog",
        ["Loudspeaker Drivers", f"Passive Radiators ({len(_acoustics.passive_radiator_preset_names())})"],
        horizontal=True,
        key="finder_library_catalog_tab",
    )
    if cat_mode and "Passive Radiators" in cat_mode:
        _render_passive_radiator_library()
        return

    st.caption(
        "Select one driver to open it directly in Box Design, or select "
        "several to limit the next Bass Match run."
    )

    # Re-serializing the full 10k-row catalog to the browser on every rerun
    # (each row selection or widget change) costs seconds of frontend time;
    # cap the table and let search/filters narrow the rest.
    shown_names = filtered_preset_names[:_LIBRARY_TABLE_MAX_ROWS]

    if not filtered_preset_names:
        st.warning("No drivers match the current search and filters.")
        st.button(
            "Reset candidate filters",
            type="primary",
            width="stretch",
            key="finder_reset_candidate_filters",
            on_click=_reset_candidate_filters,
            help="Clear search, catalog, price, Mms and Le filters.",
        )
        return

    if len(shown_names) < len(filtered_preset_names):
        st.caption(
            f"{len(filtered_preset_names)} presets match the current filters · "
            f"showing the first {len(shown_names)}. Use search or Library "
            "filters to narrow the list."
        )
    else:
        st.caption(
            f"{len(filtered_preset_names)} drivers match the current filters. "
            "Scroll the table to browse the complete list."
        )
    price_currency = str(st.session_state.get("preset_price_currency", "EUR"))
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
        width="stretch",
        height=720,
        hide_index=True,
        key="finder_driver_library_table",
        on_select="rerun",
        selection_mode="multi-row",
        column_config={
            "Driver": None,
            "Nominal in": st.column_config.NumberColumn("Nominal Ø (in)", format="%.1f"),
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
        with st.container(key="emerald_info_library_selection"):
            st.info(
                "No pool limit selected. Bass Match will evaluate every driver "
                "allowed by the Library filters."
            )
        return
        
    if len(selected_rows) > 1:
        with st.container(key="emerald_info_library_multi_selection"):
            st.info(
                f"{len(selected_rows)} drivers selected. Run Bass Match above "
                "to rank only this pool."
            )
        return
        
    selected_index = int(selected_rows[0])
    if not 0 <= selected_index < len(library_df):
        return
    selected_name = str(library_df.iloc[selected_index]["Driver"])
    st.button(
        f"Open {_driver_preset_display_label(selected_name)} in Box Design",
        type="primary",
        width="stretch",
        key="finder_use_library_driver",
        on_click=_apply_library_driver,
        args=(selected_name,),
    )


def _render_candidate_pool(filtered_preset_names: list[str]) -> None:
    """Keep raw catalog browsing secondary to the Bass Match workflow."""
    selected_count = len(
        _selected_library_preset_names(filtered_preset_names)
    )
    pool_suffix = (
        f"{selected_count} selected"
        if selected_count
        else f"{len(filtered_preset_names):,} available"
    )
    pool_expander = st.expander(
        f"Candidate pool · {pool_suffix}",
        expanded=not filtered_preset_names,
        key="finder_candidate_pool_expander",
        on_change="rerun",
    )
    # A collapsed expander normally still executes and serializes its entire
    # body. The library can contain 500 visible rows, so only build/send it
    # after the user explicitly opens the pool.
    if pool_expander.open:
        with pool_expander:
            _render_driver_library(filtered_preset_names)


def _queue_finder_design_selection(
    selected_designs: list[dict],
    voltage_v: float,
) -> None:
    """Queue Finder selection before the rerun so Box Design opens directly."""
    if len(selected_designs) == 1:
        selected = selected_designs[0]
        st.session_state["batch_pending_result"] = {
            "row": selected["row"],
            "load_type": selected["load_type"],
            "voltage_v": float(voltage_v),
        }
    elif selected_designs:
        st.session_state["batch_pending_comparison"] = {
            "designs": selected_designs,
            "voltage_v": float(voltage_v),
        }


def _render_find_driver_workspace(filtered_preset_names: list[str]) -> None:
    """Render Finder results and candidate application, separate from inputs."""
    load_type = str(st.session_state.get("load_type", "DCCAV"))
    _render_bass_match_hero(filtered_preset_names)

    match_completion = st.session_state.pop("_finder_match_completion", None)
    if match_completion:
        st.toast(str(match_completion), icon="✅")

    finder_volume_l = float(st.session_state.get("finder_volume_l", 0.0))
    # Old/restored sessions can contain an empty load list even though the
    # Finder falls back to the active design load for both its brief and run.
    # Compare against that same effective load context, or every successful
    # fallback run is immediately hidden as an input change.
    finder_loads = tuple(_finder_load_context()[0])
    finder_resonator = str(st.session_state.get(
        "finder_reflex_resonator_type", _RESONATOR_PORT))
    batch_rows = st.session_state.get("batch_results", [])
    context = st.session_state.get("batch_result_context", ())
    current_min_spl_db = float(
        st.session_state.get("finder_min_spl_db", 0.0) or 0.0)
    current_min_mol_f3_db = float(
        st.session_state.get("finder_min_mol_f3_db", 0.0) or 0.0)
    current_max_f3_hz = float(
        st.session_state.get("finder_max_f3_hz", 0.0) or 0.0)
    current_max_mms_g = float(
        st.session_state.get("finder_max_mms_g", 0.0) or 0.0)
    current_max_le_mh = float(
        st.session_state.get("finder_max_le_mh", 0.0) or 0.0)
    current_signature = _finder_result_context_signature(filtered_preset_names)
    if batch_rows and len(context) >= 11 and (
        len(context) <= 16
        or str(context[16]) != _FINDER_CONTEXT_FILTERED_POOL_VERSION
    ):
        # Replace legacy candidate-selection and short-lived control-only
        # signatures with the stable filtered-pool context. This keeps saved
        # projects and live pre-fix sessions usable across the source reload.
        legacy_context = list(context[:15])
        try:
            legacy_scan_count = max(0, int(legacy_context[2]))
        except (TypeError, ValueError):
            legacy_scan_count = len(batch_rows)
        legacy_stat_defaults = {
            11: legacy_scan_count,
            12: legacy_scan_count,
            13: 0,
            14: 0,
        }
        for index, default in legacy_stat_defaults.items():
            if len(legacy_context) <= index:
                legacy_context.append(default)
                continue
            try:
                legacy_context[index] = int(legacy_context[index])
            except (TypeError, ValueError):
                # Also repairs sessions normalized by the short-lived buggy
                # migration, where the pool signature occupied index 11.
                legacy_context[index] = default
        context = (
            *legacy_context,
            current_signature,
            _FINDER_CONTEXT_FILTERED_POOL_VERSION,
        )
        st.session_state["batch_result_context"] = context
    current_controls_signature = _finder_controls_signature()
    restored_controls_signature = str(st.session_state.get(
        "_restored_bass_match_controls_signature",
        "",
    ))
    if batch_rows and restored_controls_signature == "pending":
        restored_controls_signature = current_controls_signature
        st.session_state["_restored_bass_match_controls_signature"] = (
            restored_controls_signature
        )
    restored_results_match = bool(batch_rows) and (
        restored_controls_signature == current_controls_signature
    )
    context_matches = not (
        len(context) < 2
        or tuple(context[:2]) != (finder_loads, finder_volume_l)
        or (len(context) > 5 and str(context[5]) != finder_resonator)
        or (len(context) > 6 and float(context[6]) != current_min_spl_db)
        or (len(context) <= 6 and current_min_spl_db > 0.0)
        or (len(context) > 7 and float(context[7]) != current_min_mol_f3_db)
        or (len(context) <= 7 and current_min_mol_f3_db > 0.0)
        or (len(context) > 8 and float(context[8]) != current_max_mms_g)
        or (len(context) <= 8 and current_max_mms_g > 0.0)
        or (len(context) > 9 and float(context[9]) != current_max_le_mh)
        or (len(context) <= 9 and current_max_le_mh > 0.0)
        or len(context) <= 10
        or int(context[10]) != _FINDER_RANKING_VERSION
        or (
            len(context) > 15
            and str(context[15]) != current_signature
            and not restored_results_match
        )
    )
    if not context_matches:
        batch_rows = []
    if not batch_rows:
        if context and not context_matches:
            st.info(
                "Bass Match inputs changed. Run Bass Match again to update "
                "the results."
            )
        if st.session_state.get("batch_search_completed", False) and context_matches:
            st.subheader("No Bass Match result")
            if current_max_f3_hz > 0.0:
                st.warning(
                    f"No candidate reached an F3 at or below "
                    f"{current_max_f3_hz:.1f} Hz with the current enclosure "
                    "and filters. Raise Maximum F3 or relax the other constraints."
                )
            elif current_min_spl_db > 0.0:
                st.warning(
                    f"No candidate reached the minimum SPL of "
                    f"{current_min_spl_db:.1f} dB with the current enclosure, "
                    "voltage and filters. Lower Minimum SPL or raise the comparison voltage."
                )
            elif current_min_mol_f3_db > 0.0:
                st.warning(
                    f"No candidate reached the minimum MOL at F3 of "
                    f"{current_min_mol_f3_db:.1f} dB with the current enclosure, "
                    "voltage and filters. Lower Minimum MOL at F3 or relax the filters."
                )
            else:
                run_stats = st.session_state.get("finder_last_run_stats", {})
                load_stats = run_stats.get("loads", {})
                dccav_stats = load_stats.get("DCCAV", {})
                reflex_stats = load_stats.get("Bass reflex", {})
                load_summary = ", ".join(
                    f"{load}: {stats.get('usable', 0)}/{stats.get('attempted', 0)}"
                    for load, stats in load_stats.items()
                )
                if load_summary and all(
                    stats.get("usable", 0) == 0
                    for stats in load_stats.values()
                ):
                    st.warning(
                        "Nessun carico ha prodotto un risultato utilizzabile "
                        f"({load_summary}). Controlla il driver configuration, "
                        "il volume massimo e i vincoli del progetto."
                    )
                elif (
                    dccav_stats.get("attempted", 0) > 0
                    and dccav_stats.get("usable", 0) == 0
                    and reflex_stats.get("usable", 0) > 0
                ):
                    st.warning(
                        "DCCAV non ha trovato un allineamento costruibile per "
                        f"nessuna delle {dccav_stats['attempted']} candidate entro "
                        f"{finder_volume_l:.0f} L; il Bass reflex invece è fattibile. "
                        "Prova solo Bass reflex, aumenta il volume massimo o rilassa "
                        "i vincoli di ripple/porta."
                    )
                elif dccav_stats.get("attempted", 0) > 0 and dccav_stats.get("usable", 0) == 0:
                    st.warning(
                        "Le candidate DCCAV sono state valutate, ma nessuna ha "
                        f"prodotto un allineamento costruibile entro {finder_volume_l:.0f} L. "
                        "Aumenta il volume massimo o rilassa i vincoli di progetto."
                    )
                elif load_summary:
                    st.warning(
                        "Nessun risultato dopo il filtro prestazionale. "
                        f"Esiti per carico: {load_summary}. "
                        "Riduci i vincoli SPL/MOL/F3 oppure riesegui Bass Match."
                    )
                else:
                    st.warning(
                        "No usable candidate satisfies the current enclosure and constraints."
                    )
        _render_candidate_pool(filtered_preset_names)
        return

    batch_rows = _refresh_finder_result_catalog_metadata(batch_rows)
    st.session_state["batch_results"] = batch_rows

    selection_cta = st.empty()
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
    objective = str(context[4]) if len(context) > 4 else str(st.session_state.get("finder_objective", "Max extension"))
    volume_summary = (
        "" if finder_loads == ("Infinite baffle",)
        else f" · ≤ {finder_volume_l:.1f} L"
    )
    st.caption(
        f"{len(batch_rows)} usable matches · "
        + (
            f"{int(context[11])}/{int(context[12])} simulations after pre-filter · "
            if len(context) > 12
            else f"{context[2]} scanned presets · "
        )
        + f"{load_summary}{volume_summary} · {objective}"
    )
    full_df = pd.DataFrame(batch_rows)
    if "_load_type" in full_df.columns:
        full_df = full_df.rename(columns={"_load_type": "Load"})
    if "Manufacturer" in full_df.columns:
        manufacturer_counts = (
            full_df["Manufacturer"].astype(str).value_counts().sort_index()
        )
        st.caption(
            "Risultati per marca: "
            + " · ".join(
                f"{manufacturer} {int(count)}"
                for manufacturer, count in manufacturer_counts.items()
            )
        )
    full_df["Vtot L"] = full_df.apply(
        _finder_total_volume_l, axis=1
    )
    for name, default in (
        ("Load", ""), ("Price", np.nan), ("Currency", ""), ("Buy", ""),
        ("Ripple dB", np.nan), ("Response", None), ("Class", ""),
        ("Size in", np.nan), ("Sd cm²", np.nan),
        ("Resonator", ""), ("Mms g", np.nan), ("Le10k mH", np.nan),
        ("MOL @ F3 dB", np.nan),
    ):
        if name not in full_df.columns:
            full_df[name] = default

    selected_price_currency = str(
        st.session_state.get("preset_price_currency", "EUR")
    )
    if selected_price_currency:
        full_df = _normalize_price_frame(full_df, selected_price_currency)
    full_df["Class"] = full_df["Class"].map(_driver_class_label)

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
    batch_df = full_df
    identities = batch_df["Driver"].map(_driver_preset_identity_fields)
    batch_df["Manufacturer"] = identities.map(lambda value: value[0])
    batch_df["Part number"] = identities.map(lambda value: value[1])

    # Keep the compact Finder layout stable: identity/load, enclosure and
    # commercial metadata first, followed by the performance metrics.
    columns = ["Driver", "Manufacturer", "Part number", "Load"]
    if batch_df["Resonator"].fillna("").astype(bool).any():
        columns.append("Resonator")
    if batch_df["Size in"].notna().any():
        columns.append("Size in")
    if batch_df["Vtot L"].notna().any():
        columns.append("Vtot L")
    if batch_df["Price"].notna().any():
        columns.append("Price")
        columns.append("Currency")
        if "Value" in batch_df.columns and batch_df["Value"].notna().any():
            columns.append("Value")
    if batch_df["Buy"].fillna("").astype(bool).any():
        columns.append("Buy")
    columns.extend(["F3 Hz", "MOL @ F3 dB", "Peak dB"])
    if batch_df["Response"].map(lambda v: bool(v) if isinstance(v, list) else False).any():
        columns.append("Response")
    columns.append("Min ohm")
    if batch_df["Mms g"].notna().any():
        columns.append("Mms g")
    if batch_df["Le10k mH"].notna().any():
        columns.append("Le10k mH")

    display_df = _clean_display_table_frame(batch_df[columns])
    columns = list(display_df.columns)
    table_state = st.dataframe(
        display_df,
        # Let Streamlit measure each column from its content instead of
        # distributing the parent width across every column. Users can still
        # resize interactively, but the initial layout is already compact.
        width="content",
        height=420,
        hide_index=True,
        key=f"batch_results_table_{'value' if 'Value' in columns else 'f3'}",
        on_select="rerun",
        selection_mode="multi-row",
        column_config={
            "Driver": None,
            "Manufacturer": st.column_config.TextColumn("Mfr"),
            "Part number": st.column_config.TextColumn("Part #"),
            "F3 Hz": st.column_config.NumberColumn(format="%.1f"),
            "MOL @ F3 dB": st.column_config.NumberColumn(
                "MOL",
                format="%.1f",
                help="Maximum excursion/thermal limited output interpolated at F3.",
            ),
            "Peak dB": st.column_config.NumberColumn(format="%.1f"),
            "Price": st.column_config.NumberColumn(format="%.2f"),
            "Currency": st.column_config.TextColumn("CUR"),
            "Value": st.column_config.NumberColumn(
                "Value (F3 × price)", format="%.0f",
                help="Lower is better: cheapest path to deep bass.",
            ),
            "Min ohm": st.column_config.NumberColumn("Min Z", format="%.2f"),
            "Mms g": st.column_config.NumberColumn(format="%.1f"),
            "Le10k mH": st.column_config.NumberColumn(format="%.3f"),
            "Size in": st.column_config.NumberColumn(
                "Size (in)", format="%.1f"
            ),
            "Vtot L": st.column_config.NumberColumn(
                "Vtot (L)", format="%.2f"
            ),
            "Buy": st.column_config.LinkColumn(display_text="Buy"),
            "Response": st.column_config.LineChartColumn(
                "Response (rel dB)", y_min=_acoustics.SPARKLINE_FLOOR_DB, y_max=0.0,
            ),
        },
    )
    csv_columns = [
        name for name in columns if name not in {"Driver", "Response"}
    ]
    st.download_button(
        "Download candidate CSV",
        batch_df[csv_columns].to_csv(index=False).encode("utf-8"),
        "load_forge_candidates.csv",
        "text/csv",
        width="stretch",
    )

    selected_rows = getattr(table_state.selection, "rows", []) if table_state else []
    selected_indices = [
        int(index)
        for index in selected_rows
        if 0 <= int(index) < len(batch_df)
    ]
    selected_designs = [
        {
            "row": batch_df.iloc[index].to_dict(),
            "load_type": str(
                batch_df.iloc[index].get("Load", load_type)
            ),
        }
        for index in selected_indices
    ]
    comparison_count = len(selected_designs)
    too_many = comparison_count > _MAX_COMPARISON_DESIGNS
    cta_label = (
        f"Compare {comparison_count} designs in Box Design"
        if comparison_count > 1
        else "Open this design in Box Design"
    )
    cta_disabled = (
        not selected_designs
        or too_many
    )
    with selection_cta.container():
        st.button(
            cta_label,
            type="secondary" if not selected_designs else "primary",
            width="stretch",
            key="finder_open_selected_design",
            disabled=cta_disabled,
            on_click=_queue_finder_design_selection,
            args=(selected_designs, float(_finder_value("finder_voltage"))),
        )

    if not selected_indices:
        with st.container(key="emerald_info_candidate_selection"):
            st.caption(
                "Select one match to preview it, or select 2–8 matches to "
                "compare them in Box Design."
            )
        _render_candidate_pool(filtered_preset_names)
        return
    if len(selected_indices) > 1:
        with st.container(border=True):
            st.markdown(
                f"#### Design comparison · {comparison_count} selected"
            )
            st.caption(
                "Every selected match becomes an independently editable Box "
                "Design tab. Switch tabs to change its driver, load or box; "
                "all tabs stay overlaid at the same voltage."
            )
            if too_many:
                st.warning(
                    f"Select at most {_MAX_COMPARISON_DESIGNS} designs."
                )
        _render_candidate_pool(filtered_preset_names)
        return

    selected_index = selected_indices[0]
    selected_row = batch_df.iloc[selected_index].to_dict()
    row_load_type = str(selected_row.get("Load", load_type))
    with st.container(border=True):
        st.markdown(
            "#### Match preview · "
            f"{_driver_preset_display_label(str(selected_row['Driver']))} · "
            f"{row_load_type}"
        )
        p1, p2, p3, p4 = st.columns(4)
        p1.metric("F3", f"{float(selected_row['F3 Hz']):.1f} Hz")
        mol_at_f3 = float(selected_row.get("MOL @ F3 dB", np.nan))
        p2.metric(
            "MOL @ F3",
            f"{mol_at_f3:.1f} dB" if np.isfinite(mol_at_f3) else "—",
        )
        p3.metric("Peak LF SPL", f"{float(selected_row['Peak dB']):.1f} dB")
        p4.metric("Min impedance", f"{float(selected_row['Min ohm']):.2f} Ω")
        total_volume_l = _finder_total_volume_l(selected_row)
        if np.isfinite(total_volume_l):
            st.caption(f"Vtot {total_volume_l:.2f} L")
        elif row_load_type == "Infinite baffle":
            st.caption("Infinite baffle · no enclosure volume")
    _render_candidate_pool(filtered_preset_names)


@st.cache_data(show_spinner="Simulating T/S tolerance band...")
def _tolerance_band_cached(
    ts: _acoustics.DriverTS,
    load_type: str,
    box,
    freq: np.ndarray,
    voltage_v: float,
    series_r_ohm: float,
    tolerance: float,
) -> _acoustics.ToleranceBand:
    return _acoustics.monte_carlo_response_band(
        ts, load_type=load_type, box=box, freq_hz=freq,
        voltage_v=voltage_v, series_r_ohm=series_r_ohm, tolerance=tolerance,
    )


def _simulation_engine_revision() -> tuple[float | None, ...]:
    """Invalidate design results automatically when the solver source changes."""
    revisions = []
    for module in (_engine, _acoustics):
        try:
            revisions.append(Path(module.__file__).stat().st_mtime)
        except OSError:
            revisions.append(None)
    return tuple(revisions)


@st.cache_data(show_spinner=False, max_entries=128)
def _simulate_design_cached(
    engine_revision: tuple[float | None, ...],
    ts: _acoustics.DriverTS,
    load_type: str,
    box,
    f_min_hz: float,
    f_max_hz: float,
    points: int,
    voltage_v: float,
    series_r_ohm: float,
) -> tuple[
    _acoustics.SimulationResult,
    dict[str, float],
    dict[int, float],
    list[float],
]:
    """Cache the solver and its base metrics across UI-only reruns."""
    del engine_revision  # It is part of the cache key only.
    freq = np.geomspace(float(f_min_hz), float(f_max_hz), int(points))
    if load_type == "Bass reflex" and isinstance(
        box, _acoustics.PassiveRadiatorBox
    ):
        result = _acoustics.simulate_passive_radiator(
            ts, box, freq, voltage_v, series_r_ohm
        )
    elif load_type == "Bass reflex":
        result = _acoustics.simulate_reflex(
            ts, box, freq, voltage_v, series_r_ohm
        )
    elif load_type == "Bandpass 4th order":
        result = _acoustics.simulate_bandpass4(
            ts, box, freq, voltage_v, series_r_ohm
        )
    elif load_type == "Bandpass 6th order":
        result = _acoustics.simulate_bandpass6(
            ts, box, freq, voltage_v, series_r_ohm
        )
    elif load_type == "Bandpass 8th order":
        result = _acoustics.simulate_bandpass8(
            ts, box, freq, voltage_v, series_r_ohm
        )
    elif load_type == "Sealed":
        result = _acoustics.simulate_sealed(
            ts, box, freq, voltage_v, series_r_ohm
        )
    elif load_type == "Infinite baffle":
        result = _acoustics.simulate_infinite_baffle(
            ts, freq, voltage_v, series_r_ohm
        )
    else:
        result = _acoustics.simulate(ts, box, freq, voltage_v, series_r_ohm)
    ripple_max_freq = float(st.session_state.get("opt_max_ripple_freq_hz", 0.0)) or None
    return (
        result,
        _acoustics.response_metrics(result, ripple_max_freq_hz=ripple_max_freq),
        _acoustics.response_threshold_frequencies(result, f_max_hz=ripple_max_freq),
        _acoustics.impedance_peak_frequencies(result),
    )


def _design_simulation_signature(
    engine_revision: tuple[float | None, ...],
    ts: _acoustics.DriverTS,
    load_type: str,
    box,
    f_min_hz: float,
    f_max_hz: float,
    points: int,
    voltage_v: float,
    series_r_ohm: float,
    ripple_max_freq_hz: float = 0.0,
) -> str:
    payload = repr((
        engine_revision, ts, load_type, box, float(f_min_hz),
        float(f_max_hz), int(points), float(voltage_v),
        float(series_r_ohm), float(ripple_max_freq_hz),
    )).encode("utf-8")
    return hashlib.sha1(payload).hexdigest()[:16]


@st.fragment
def _render_response_tab(
    current_ts: _acoustics.DriverTS,
    load_type: str,
    box,
    result: _acoustics.SimulationResult,
    thresholds: dict[int, float],
    freq: np.ndarray,
    sim_voltage: float,
    sim_series_r: float,
) -> None:
    compare_loads_on = bool(st.session_state.get("plot_compare_loads", False))

    # --- 1. Compute state needed for charts ---
    ripple_max_freq = float(st.session_state.get("opt_max_ripple_freq_hz", 0.0)) or None
    cursor_rows = _cursor_rows(result, thresholds, max_freq_hz=ripple_max_freq)

    compare_series = None
    if compare_loads_on:
        comp_vtot, comp_series = _topology_comparison_series(
            current_ts,
            load_type,
            box,
            freq,
            sim_voltage,
            sim_series_r,
            _simulation_engine_revision(),
        )
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
        if saved_traces != selected_traces:
            st.session_state["plot_response_traces"] = selected_traces

        st.altair_chart(
            _plot_response(
                result, cursor_rows, compare_series, band,
                frequency_window=frequency_window,
                show_legend=False,
                default_visible=selected_traces,
            ),
            width="stretch",
            # Preserve the mounted Vega view while parameters and project
            # autosave state change. A content-derived key remounts the chart
            # and briefly removes the page scrollbar, creating a resize loop.
            key="response_chart",
        )
        st.caption(
            "Use the frequency slider below to zoom; click the chart to place a point marker "
            "and double-click to clear it."
        )
    else:
        st.caption("Response pens off.")


    # --- 3. Render Analysis Options & Actions ---
    pinned_state = _pinned_responses()
    comparison_tabs = _design_comparison_tabs()
    comparison_mode = bool(comparison_tabs)
    col_widths = (
        [2.8, 1.3, 1.4, 1.3, 1.3, 1.1, 1.0]
        if pinned_state
        else [2.8, 1.3, 1.4, 1.3, 1.3, 1.0]
    )
    ctrl_cols = st.columns(col_widths, vertical_alignment="center", gap="small")
    
    with ctrl_cols[0]:
        st.pills(
            "Traces",
            available_traces if (compare_series or _response_series(result)) else ["Total"],
            selection_mode="multi",
            key="plot_response_traces",
            label_visibility="collapsed",
        )
    with ctrl_cols[1]:
        st.toggle("Compare loads", key="plot_compare_loads")
    with ctrl_cols[2]:
        st.toggle(
            "Tolerance band", key="plot_tolerance_band", disabled=compare_loads_on,
            help="Monte Carlo 5-95th percentile spread from T/S tolerances.",
        )
    with ctrl_cols[3]:
        st.toggle(
            "Tuning markers",
            key="plot_show_tuning_markers",
            help="Show or hide vertical markers at the active enclosure tuning frequencies.",
        )
    with ctrl_cols[4]:
        if st.button(
            "Pin response",
            width="stretch",
            disabled=(
                len(pinned_state) >= _MAX_PINNED_RESPONSES
                or comparison_mode
            ),
            help=(
                f"Keep up to {_MAX_PINNED_RESPONSES} response traces while "
                "changing driver, load or box. Editable design tabs already "
                "manage their own overlays."
            ),
        ):
            st.session_state["pinned_responses"] = [
                *pinned_state,
                _pinned_response_snapshot(load_type, box, result),
            ]
            st.rerun()

    if pinned_state and not comparison_mode:
        with ctrl_cols[5]:
            if st.button("Clear all pins", width="stretch"):
                _clear_pinned_responses()
                st.rerun()
        with ctrl_cols[6]:
            st.button(
                "Reset zoom",
                key="plot_response_reset_zoom",
                width="stretch",
                disabled=tuple(st.session_state.get("plot_response_window_hz", full_window)) == full_window,
                on_click=_reset_response_zoom,
                args=(full_window,),
            )
    elif pinned_state:
        with ctrl_cols[5]:
            st.button(
                "Tabs active",
                width="stretch",
                disabled=True,
            )
        with ctrl_cols[6]:
            st.button(
                "Reset zoom",
                key="plot_response_reset_zoom",
                width="stretch",
                disabled=tuple(st.session_state.get("plot_response_window_hz", full_window)) == full_window,
                on_click=_reset_response_zoom,
                args=(full_window,),
            )
    else:
        with ctrl_cols[5]:
            st.button(
                "Reset zoom",
                key="plot_response_reset_zoom",
                width="stretch",
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
    if load_type == "Bass reflex":
        resonator = "passive radiator" if _reflex_uses_passive_radiator() else "vent"
        st.caption(
            "Bass-reflex total response is the vector sum of the exposed cone "
            f"front radiation and the {resonator}. The model is low-frequency only; "
            "it does not include baffle step, breakup, room gain or crossover behaviour."
        )
    elif load_type == "Bandpass 4th order":
        st.caption(
            "Fourth-order bandpass total response is the front vent only: the cone is "
            "enclosed between a sealed rear chamber and a ported front chamber. The "
            "cone trace shows internal motion and is not an additional radiating source."
        )
    elif load_type == "Bandpass 6th order":
        st.caption(
            "Sixth-order bandpass total response is the polarity-correct vector difference "
            "of both vents: the cone is enclosed between two ported chambers. The cone trace "
            "shows internal motion and is not an additional radiating source."
        )
    elif load_type == "Bandpass 8th order":
        st.caption(
            "Triple-chamber eighth-order bandpass total response radiates exclusively through Port 3 (common plenum chamber). "
            "Chamber 1 and Chamber 2 ports exhaust internally into Chamber 3. "
            "Driver excursion exhibits three distinct displacement notches corresponding to the chamber tunings."
        )
    elif load_type == "Sealed":
        st.caption(
            "Sealed-box response is the exposed cone front with the rear wave enclosed. "
            "The model includes closed-box compliance and losses, but not room gain or baffle step."
        )
    elif load_type == "Infinite baffle":
        st.caption(
            "Infinite-baffle response is the exposed cone front with perfect rear-wave isolation. "
            "Finite-panel diffraction, rear leakage, room gain and baffle step are not included."
        )
    else:
        st.caption(
            "DCCAV total response is the vector sum of the exposed cone front "
            "radiation and the lower port. The load model is low-frequency only; "
            "it is not an electrical crossover or breakup/directivity predictor."
        )

    if comparison_mode:
        st.caption(
            f"Editable comparison: {len(comparison_tabs)}/"
            f"{_MAX_COMPARISON_DESIGNS} tabs · inactive designs use dashed "
            "colored traces."
        )
    elif pinned_state:
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
                        width="stretch",
                    ):
                        _set_pinned_response_visible(index, not is_visible)
                        st.rerun()
                with remove_col:
                    if st.button(
                        "Clear",
                        key=f"remove_pinned_response_{index}",
                        help=f"Clear pinned simulation {index + 1}",
                        width="stretch",
                    ):
                        _remove_pinned_response(index)
                        st.rerun()


def _render_ports_tab(
    result: _acoustics.SimulationResult,
    port_geometry_rows: list[dict],
    load_type: str,
    driver: _acoustics.DriverTS | None = None,
    box: any = None,
    passive_radiator: bool = False,
) -> None:
    import streamlit.components.v1 as _st_components

    chart_sig = _chart_signature()
    if load_type not in {"DCCAV", "Bass reflex", "Bandpass 4th order", "Bandpass 6th order", "Bandpass 8th order"}:
        st.caption("The current load type has no ports.")
        return

    valid_ports = [r for r in port_geometry_rows if not r.get("_is_pr", False) and r.get("Diameter cm", 0.0) > 0]
    
    # Target duct options: All Ducts + specific ports
    if len(valid_ports) > 1:
        target_options = ["All Ducts (Global)"] + [r["Port"] for r in valid_ports]
    elif len(valid_ports) == 1:
        target_options = [valid_ports[0]["Port"]]
    else:
        target_options = ["Vent"]

    curr_target = st.session_state.get("flared_target_duct", target_options[0])
    if curr_target not in target_options:
        curr_target = target_options[0]
    # A single-port load has no target radio, so keep an explicit active target
    # for chart/KPI style resolution instead of inheriting a stale global or
    # DCCAV selection from an earlier design.
    st.session_state["flared_active_target_duct"] = curr_target

    # Compute flared dimensions for all valid ports in advance with per-port style support
    display_rows = []
    total_duct_vol_l = 0.0
    max_peak_mol = 0.0
    max_peak_sim = 0.0
    peak_hz = 0.0

    for r in port_geometry_rows:
        if r.get("_is_pr", False) or r.get("Diameter cm", 0.0) <= 0:
            display_rows.append(r)
            continue
        p_name = r["Port"]
        p_style = _clean_style_str(st.session_state.get(f"flared_style_{p_name}", st.session_state.get("flared_calc_style", "both")), "both")
        p_rad = float(st.session_state.get(f"flared_radius_{p_name}", st.session_state.get("flared_calc_radius_cm", 2.5)))
        fdims = _acoustics.flared_port_dimensions_cm(
            volume_l=r.get("_volume_l", 20.0),
            fb_hz=r.get("_fb_hz", 40.0),
            diameter_cm=r["Diameter cm"],
            flare_radius_cm=p_rad,
            flare_style=p_style,
        )
        row_copy = dict(r)
        row_copy["Flare Profile"] = p_style.capitalize() if p_style != "both" else "Double Flared"
        row_copy["Straight Cut cm"] = fdims["straight_length_cm"]
        row_copy["Overall Length cm"] = fdims["overall_length_cm"]
        row_copy["Mouth Ø cm"] = fdims["outer_diameter_cm"]
        row_copy["Duct Vol (L)"] = fdims["volume_displacement_l"]
        display_rows.append(row_copy)
        total_duct_vol_l += fdims["volume_displacement_l"]

        peak_mol = float(r.get("Peak m/s (MOL)", 0.0))
        peak_sim = float(r.get("Peak m/s", 0.0))
        if peak_mol > max_peak_mol:
            max_peak_mol = peak_mol
            peak_hz = float(r.get("Peak at Hz", 0.0))
        if peak_sim > max_peak_sim:
            max_peak_sim = peak_sim

    # Active flare limit for status bar
    active_style = _focused_port_flare_style()
    flare_limit_ms = _acoustics.port_chuffing_limit_ms(active_style)
    port_plot_mode_raw = st.session_state.get("port_plot_display_mode", "air_velocity_mol")
    port_plot_mode = _clean_style_str(port_plot_mode_raw, "air_velocity_mol")

    # 1. Top Acoustic Health Monitor (KPI Status Bar)
    with st.container(border=True):
        if passive_radiator:
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Load Mode", "Passive Radiator", "Acoustic Mass")
            k2.metric("Radiator Air Velocity", f"{max_peak_sim:.1f} m/s", f"@ {float(st.session_state.get('sim_voltage', 2.83)):.2f} V")
            k3.metric("Peak Excursion", "Configured in Sidebar", "T/S Mass & Area")
            k4.metric("Chuffing Risk", "None (Piston)", "No duct turbulence")
        else:
            k1, k2, k3, k4 = st.columns(4)
            if not valid_ports:
                status_text = "No Vent Configured"
                status_delta = "Set diameter > 0"
                delta_color = "off"
            elif max_peak_mol <= flare_limit_ms * 0.75:
                status_text = "✓ Air Flow Safe"
                headroom = flare_limit_ms - max_peak_mol
                status_delta = f"+{headroom:.1f} m/s margin"
                delta_color = "normal"
            elif max_peak_mol <= flare_limit_ms:
                status_text = "⚠ Compression Risk"
                headroom = flare_limit_ms - max_peak_mol
                status_delta = f"Only {headroom:.1f} m/s margin"
                delta_color = "off"
            else:
                status_text = "✖ High Chuffing Risk"
                excess = max_peak_mol - flare_limit_ms
                status_delta = f"+{excess:.1f} m/s over limit"
                delta_color = "inverse"

            k1.metric("Acoustic Chuffing Status", status_text, status_delta, delta_color=delta_color)
            k2.metric("Peak Air Speed (MOL)", f"{max_peak_mol:.1f} m/s", f"at {peak_hz:.0f} Hz" if peak_hz > 0 else None)
            flare_name = {
                "both": "Aeroport",
                "one": "Single flare",
                "one_end": "Single flare",
                "hourglass": "Hourglass",
                "none": "Cylindrical",
            }.get(active_style, "Aeroport")
            k3.metric("Chuffing Guideline Limit", f"{flare_limit_ms:.1f} m/s", f"{flare_name} guideline")
            k4.metric("Total Duct Displacement", f"{total_duct_vol_l:.2f} L", f"{len(valid_ports)} active duct{'s' if len(valid_ports) != 1 else ''}")

    # 2. Main Workbench Layout (2 Columns: Left Cockpit, Right Analysis & CAD)
    col_left, col_right = st.columns([1.15, 1.85], gap="medium")

    with col_left:
        # Card A: Duct Focus, Flare Profile & Auto-Optimizer
        with st.container(border=True):
            st.markdown("##### ⚙️ Active Duct Focus & Auto-Optimizer")
            
            if len(valid_ports) > 1:
                target_duct = st.radio(
                    "Target Duct to Configure (Single-Click)",
                    target_options,
                    index=target_options.index(curr_target),
                    horizontal=True,
                    key="flared_target_duct",
                    help="Select which duct to configure independently (Internal inter-chamber vs External radiating) or choose All Ducts.",
                )
            elif len(valid_ports) == 1:
                target_duct = valid_ports[0]["Port"]
            else:
                target_duct = "Vent"

            # Context badge
            if "Internal" in target_duct:
                st.info("🔒 **Internal Inter-Chamber Duct**: Couples internal cavities (k=1.64). Flanged on both ends inside cabinet.", icon="🔒")
            elif "External" in target_duct or "Vent" in target_duct:
                st.info("📢 **External Radiating Vent**: Radiates acoustic energy into listening room (k=1.43). Critical for chuffing prevention.", icon="📢")
            elif target_duct.startswith("All"):
                st.caption("🌐 **Configuring all ducts simultaneously**: Changes to flare profile, radius and auto-optimization will apply across all active ducts.")

            # Dynamic session key mapping
            if target_duct.startswith("All"):
                style_key = "flared_calc_style"
                rad_key = "flared_calc_radius_cm"
                curr_style = _clean_style_str(st.session_state.get(style_key, "both"), "both")
                curr_rad = float(st.session_state.get(rad_key, 2.5))
            else:
                style_key = f"flared_style_{target_duct}"
                rad_key = f"flared_radius_{target_duct}"
                curr_style = _clean_style_str(st.session_state.get(style_key, st.session_state.get("flared_calc_style", "both")), "both")
                curr_rad = float(st.session_state.get(rad_key, st.session_state.get("flared_calc_radius_cm", 2.5)))

            style_options = ["both", "hourglass", "one", "none"]
            style_labels = {
                "both": "🌐 Double flared (Aeroport)",
                "hourglass": "⏳ Hourglass continuous (Clessidra)",
                "one": "📯 Single flared (Outer mouth)",
                "none": "📏 Straight pipe (Cylindrical)",
            }
            s_idx = style_options.index(curr_style) if curr_style in style_options else 0

            duct_focus_label = (
                "Global"
                if target_duct.startswith("All")
                else target_duct.split(" (")[0]
            )
            flare_style_raw = st.radio(
                f"Flare profile ({duct_focus_label})",
                style_options,
                index=s_idx,
                format_func=lambda x: style_labels.get(x, str(x)),
                key=style_key,
            )
            flare_style = _clean_style_str(flare_style_raw, "both")

            if target_duct.startswith("All"):
                for r in valid_ports:
                    pk = f"flared_style_{r['Port']}"
                    if pk != style_key:
                        st.session_state[pk] = flare_style

            if flare_style != "none":
                flare_rad_cm = st.number_input(
                    f"Flare radius R (cm per side · {duct_focus_label})",
                    min_value=0.5,
                    max_value=10.0,
                    value=curr_rad,
                    step=0.5,
                    key=rad_key,
                    help=(
                        "Radial rounding on each side of the duct. The mouth "
                        "diameter is throat diameter + 2 × R."
                    ),
                )
                st.caption(
                    "Mouth Ø = throat Ø + 2 × R (the radius is applied on both sides)."
                )
                if target_duct.startswith("All"):
                    for r in valid_ports:
                        rk = f"flared_radius_{r['Port']}"
                        if rk != rad_key:
                            st.session_state[rk] = flare_rad_cm
            else:
                flare_rad_cm = 2.5

            policy_options = ["studio_mol", "balanced_pro", "compact"]
            policy_labels = {
                "studio_mol": "🎯 Studio / Hi-Fi (Zero chuffing at MOL)",
                "balanced_pro": "⚡ Balanced / Pro (AES guideline)",
                "compact": "🗜️ Compact Box (Min duct volume)",
            }
            curr_pol = _clean_style_str(st.session_state.get("port_auto_policy", "studio_mol"), "studio_mol")
            p_idx = policy_options.index(curr_pol) if curr_pol in policy_options else 0

            opt_policy_raw = st.radio(
                "Auto-sizing directive / policy",
                policy_options,
                index=p_idx,
                format_func=lambda x: policy_labels.get(x, str(x)),
                key="port_auto_policy",
                on_change=_mark_session_flag,
                args=("_port_optimizer_policy_changed",),
            )
            opt_policy = _clean_style_str(opt_policy_raw, "studio_mol")
            optimizer_target_ms = _acoustics.port_optimizer_target_velocity_ms(
                flare_style, opt_policy
            )
            optimizer_limit_ms = _acoustics.port_chuffing_limit_ms(flare_style)
            optimizer_fraction = int(round(
                100.0 * optimizer_target_ms / optimizer_limit_ms
            ))
            st.caption(
                f"Optimizer target: **{optimizer_target_ms:.1f} m/s** "
                f"({optimizer_fraction}% of the {flare_style.replace('_', ' ')} "
                f"limit {optimizer_limit_ms:.1f} m/s)."
            )

            btn_label = f"⚡ Auto-optimize {duct_focus_label}" if not target_duct.startswith("All") else "⚡ Auto-optimize All Ducts"
            clicked = st.button(btn_label, use_container_width=True, help="Automatically size the selected duct(s) based on driver MOL velocity, chamber volume, and constraints.")

            current_opt_state = (load_type, target_duct, opt_policy, flare_style, flare_rad_cm)
            last_opt_state = st.session_state.get("_last_opt_state")
            policy_changed = bool(
                st.session_state.pop("_port_optimizer_policy_changed", False)
            )
            should_run_opt = (
                clicked
                or policy_changed
                or (last_opt_state is not None and last_opt_state != current_opt_state)
            )

            optimizer_feedback = st.session_state.get("_port_optimizer_feedback")
            if optimizer_feedback:
                feedback_text = str(optimizer_feedback.get("text", ""))
                if optimizer_feedback.get("compromised"):
                    st.warning(feedback_text, icon="⚠️")
                else:
                    st.success(feedback_text, icon="✅")

            if should_run_opt:
                st.session_state["_last_opt_state"] = current_opt_state
                voltage_v = float(st.session_state.get("sim_voltage", 2.83))
                optimized_results = []

                def _opt_single(p_name, vol, f_hz, end_c, u_vel, p_slot, key_name):
                    p_st = _clean_style_str(
                        st.session_state.get(f"flared_style_{p_name}", flare_style),
                        flare_style,
                    )
                    p_rd = float(st.session_state.get(f"flared_radius_{p_name}", flare_rad_cm))
                    res_opt = _acoustics.auto_optimize_port_diameter_cm(
                        ts=driver,
                        result=result,
                        volume_l=vol,
                        tuning_hz=f_hz,
                        end_correction=end_c,
                        volume_velocity=u_vel,
                        sim_voltage_v=voltage_v,
                        policy=opt_policy,
                        flare_style=p_st,
                        flare_radius_cm=p_rd,
                        port_name=p_slot,
                    )
                    st.session_state[key_name] = res_opt["diameter_cm"]
                    optimized_results.append((p_name, res_opt))
                    return res_opt

                if load_type == "Bass reflex":
                    opt_res = _opt_single("Vent (External)", box.vb_l, box.fb_hz, 1.43, result.port_l_velocity, "lower", "reflex_port_d_cm")
                    st.toast(f"⚡ Vent Auto-Optimized: Ø {opt_res['diameter_cm']:.1f} cm ({opt_res['status_note']})", icon="⚡")
                elif load_type == "DCCAV":
                    if target_duct.startswith("All") or "Upper" in target_duct:
                        o_up = _opt_single("Upper port (Internal inter-chamber)", box.vh_l, box.fh_hz, 1.64, result.port_h_velocity, "upper", "box_port_d_h_cm")
                        if not target_duct.startswith("All"):
                            st.toast(f"⚡ Upper Port (Internal) Optimized: Ø {o_up['diameter_cm']:.1f} cm", icon="⚡")
                    if target_duct.startswith("All") or "Lower" in target_duct:
                        o_low = _opt_single("Lower port (External radiating)", box.vl_l, box.fl_hz, 1.43, result.port_l_velocity, "lower", "box_port_d_l_cm")
                        if not target_duct.startswith("All"):
                            st.toast(f"⚡ Lower Port (External) Optimized: Ø {o_low['diameter_cm']:.1f} cm", icon="⚡")
                    if target_duct.startswith("All"):
                        st.toast(f"⚡ DCCAV All Ports Optimized: Upper Ø {o_up['diameter_cm']:.1f} cm, Lower Ø {o_low['diameter_cm']:.1f} cm", icon="⚡")
                elif load_type == "Bandpass 4th order":
                    opt_bp4 = _opt_single("Front vent (External)", box.vp_l, box.fp_hz, 1.43, result.port_l_velocity, "lower", "bandpass4_port_d_cm")
                    st.toast(f"⚡ Front Vent Optimized: Ø {opt_bp4['diameter_cm']:.1f} cm", icon="⚡")
                elif load_type == "Bandpass 6th order":
                    if target_duct.startswith("All") or "Rear" in target_duct:
                        o_r = _opt_single("Rear vent (External)", box.vr_l, box.fr_hz, 1.43, result.port_h_velocity, "upper", "bandpass6_port_d_r_cm")
                        if not target_duct.startswith("All"):
                            st.toast(f"⚡ Rear Vent Optimized: Ø {o_r['diameter_cm']:.1f} cm", icon="⚡")
                    if target_duct.startswith("All") or "Front" in target_duct:
                        o_p = _opt_single("Front vent (External)", box.vp_l, box.fp_hz, 1.43, result.port_l_velocity, "lower", "bandpass6_port_d_p_cm")
                        if not target_duct.startswith("All"):
                            st.toast(f"⚡ Front Vent Optimized: Ø {o_p['diameter_cm']:.1f} cm", icon="⚡")
                    if target_duct.startswith("All"):
                        st.toast(f"⚡ BP6 All Vents Optimized: Rear Ø {o_r['diameter_cm']:.1f} cm, Front Ø {o_p['diameter_cm']:.1f} cm", icon="⚡")
                elif load_type == "Bandpass 8th order":
                    if target_duct.startswith("All") or "Port 1" in target_duct:
                        o1 = _opt_single("Port 1 (Internal -> C3)", box.v1_l, box.f1_hz, 1.43, result.port_l_velocity, "lower", "bp8_dp1_cm")
                        if not target_duct.startswith("All"):
                            st.toast(f"⚡ Port 1 (Internal) Optimized: Ø {o1['diameter_cm']:.1f} cm", icon="⚡")
                    if target_duct.startswith("All") or "Port 2" in target_duct:
                        o2 = _opt_single("Port 2 (Internal -> C3)", box.v2_l, box.f2_hz, 1.43, result.port_l_velocity, "lower", "bp8_dp2_cm")
                        if not target_duct.startswith("All"):
                            st.toast(f"⚡ Port 2 (Internal) Optimized: Ø {o2['diameter_cm']:.1f} cm", icon="⚡")
                    if target_duct.startswith("All") or "Port 3" in target_duct:
                        o3 = _opt_single("Port 3 (External radiating)", box.v3_l, box.f3_hz, 1.43, result.port_h_velocity, "upper", "bp8_dp3_cm")
                        if not target_duct.startswith("All"):
                            st.toast(f"⚡ Port 3 (External) Optimized: Ø {o3['diameter_cm']:.1f} cm", icon="⚡")
                    if target_duct.startswith("All"):
                        st.toast(f"⚡ BP8 All Ports Optimized", icon="⚡")
                if optimized_results:
                    result_parts = [
                        (
                            f"{name.split(' (')[0]}: Ø {item['diameter_cm']:.1f} cm, "
                            f"peak {item['mol_velocity_peak_ms']:.1f} m/s"
                        )
                        for name, item in optimized_results
                    ]
                    compromised_notes = [
                        str(item["status_note"])
                        for _, item in optimized_results
                        if str(item.get("status_note", "")).startswith("Compromised:")
                    ]
                    policy_name = {
                        "studio_mol": "Studio / Hi-Fi",
                        "balanced_pro": "Balanced / Pro",
                        "compact": "Compact",
                    }.get(opt_policy, opt_policy)
                    feedback_text = (
                        f"{policy_name} applied · "
                        + " · ".join(result_parts)
                        + f" · target {optimizer_target_ms:.1f} m/s."
                    )
                    if compromised_notes:
                        feedback_text += " " + " ".join(compromised_notes)
                    st.session_state["_port_optimizer_feedback"] = {
                        "text": feedback_text,
                        "compromised": bool(compromised_notes),
                    }
                st.rerun()
            elif last_opt_state is None:
                st.session_state["_last_opt_state"] = current_opt_state

        # Card B: Manual Duct Dimensions
        with st.container(border=True):
            st.markdown("##### 📐 Duct Diameters & Chamber Ports")
            if load_type == "DCCAV":
                p1, p2 = st.columns(2)
                with p1:
                    st.number_input(
                        "Upper port Ø (cm) · 🔒 Internal", min_value=0.0, max_value=60.0,
                        step=0.5, key="box_port_d_h_cm", help="Internal inter-chamber port (flanged both ends, k=1.64)")
                with p2:
                    st.number_input(
                        "Lower port Ø (cm) · 📢 External", min_value=0.0, max_value=60.0,
                        step=0.5, key="box_port_d_l_cm", help="External radiating port (flanged one end, k=1.43)")
                st.caption(
                    "🔒 Upper port connects the two internal cavities (k=1.64); "
                    "📢 Lower port exhausts outside the enclosure (k=1.43)."
                )
            elif load_type == "Bandpass 4th order":
                st.number_input(
                    "Front vent diameter (cm) · 📢 External", min_value=0.0,
                    max_value=60.0, step=0.5, key="bandpass4_port_d_cm")
                st.caption("Front-chamber vent radiating externally (one flanged, one free end, k=1.43).")
            elif load_type == "Bandpass 6th order":
                p1, p2 = st.columns(2)
                with p1:
                    st.number_input(
                        "Rear vent Ø (cm) · 📢 External", min_value=0.0,
                        max_value=60.0, step=0.5, key="bandpass6_port_d_r_cm")
                with p2:
                    st.number_input(
                        "Front vent Ø (cm) · 📢 External", min_value=0.0,
                        max_value=60.0, step=0.5, key="bandpass6_port_d_p_cm")
                st.caption("Rear and front vents radiating externally (k=1.43).")
            elif load_type == "Bandpass 8th order":
                p1, p2, p3 = st.columns(3)
                with p1:
                    st.number_input(
                        "Port 1 Ø (cm) · 🔒 Internal", min_value=0.0,
                        max_value=60.0, step=0.5, key="bp8_dp1_cm")
                with p2:
                    st.number_input(
                        "Port 2 Ø (cm) · 🔒 Internal", min_value=0.0,
                        max_value=60.0, step=0.5, key="bp8_dp2_cm")
                with p3:
                    st.number_input(
                        "Port 3 Ø (cm) · 📢 External", min_value=0.0,
                        max_value=60.0, step=0.5, key="bp8_dp3_cm")
                st.caption("Port 1 & 2 exhaust internally into Chamber 3; Port 3 radiates externally.")
            elif load_type == "Bass reflex" and not passive_radiator:
                st.number_input(
                    "Vent diameter (cm) · 📢 External", min_value=0.0,
                    max_value=60.0, step=0.5, key="reflex_port_d_cm")
                st.caption("Conventional enclosure vent (one flanged, one free end, k=1.43).")
            elif passive_radiator:
                st.caption("The passive radiator is sized in the sidebar with area, mass and suspension.")

        # Card C: Chart Display Controls
        with st.container(border=True):
            st.markdown("##### 📊 Chart Pens & Display Metric")
            plot_options = ["air_velocity_mol", "air_velocity_sim", "volume_velocity"]
            plot_labels = {
                "air_velocity_mol": "Air velocity at MOL (m/s)",
                "air_velocity_sim": "Air velocity at drive level (m/s)",
                "volume_velocity": "Volume velocity (m³/s)",
            }
            curr_pm = _clean_style_str(st.session_state.get("port_plot_display_mode", "air_velocity_mol"), "air_velocity_mol")
            pm_idx = plot_options.index(curr_pm) if curr_pm in plot_options else 0
            port_plot_mode_raw = st.radio(
                "Port chart metric",
                plot_options,
                index=pm_idx,
                format_func=lambda opt: plot_labels.get(opt, str(opt)),
                horizontal=False,
                key="port_plot_display_mode",
            )
            port_plot_mode = _clean_style_str(port_plot_mode_raw, "air_velocity_mol")

            if passive_radiator:
                st.checkbox("Passive radiator pen", key="plot_port_lower")
            elif load_type == "Bandpass 6th order":
                p1, p2 = st.columns(2)
                with p1:
                    st.checkbox("Rear port pen", key="plot_port_upper")
                with p2:
                    st.checkbox("Front port pen", key="plot_port_lower")
            elif load_type == "Bandpass 8th order":
                p1, p2, p3 = st.columns(3)
                with p1:
                    st.checkbox("Port 1", key="plot_port_p1")
                with p2:
                    st.checkbox("Port 2", key="plot_port_p2")
                with p3:
                    st.checkbox("Port 3", key="plot_port_lower")
            else:
                st.checkbox("Vent volume / velocity pen", key="plot_port_lower")

    with col_right:
        # Card D: Chart Analysis
        with st.container(border=True):
            chart_title = (
                "Radiator Velocity"
                if passive_radiator
                else ("Port Air Velocity vs Chuffing Limit (MOL)" if port_plot_mode == "air_velocity_mol" else ("Port Air Velocity (Drive Level)" if port_plot_mode == "air_velocity_sim" else "Port Volume Velocity"))
            )
            st.markdown(f"##### 📈 {chart_title}")
            if _port_series(result, mode=port_plot_mode):
                st.altair_chart(_plot_ports(result, mode=port_plot_mode), width="stretch", key=f"ports_chart_{chart_sig}")
            else:
                st.caption("Port pens off.")

        # Card E: Blueprint CAD Drawing & Physical Specs
        if passive_radiator:
            with st.container(border=True):
                st.markdown("##### 📐 Radiator Geometry & Motion")
                st.caption(
                    "Equivalent diaphragm diameter and simulated radiator motion "
                    f"at {float(st.session_state.get('sim_voltage', 2.83)):.2f} V and at MOL."
                )
                st.dataframe(
                    pd.DataFrame(port_geometry_rows)[list(_PORT_GEOMETRY_COLUMNS)],
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "Diameter cm": st.column_config.NumberColumn(format="%.1f"),
                        "Length cm": st.column_config.NumberColumn(format="%.1f"),
                        "Peak m/s": st.column_config.NumberColumn(format="%.1f"),
                        "Peak m/s (MOL)": st.column_config.NumberColumn(format="%.1f"),
                        "Peak at Hz": st.column_config.NumberColumn(format="%.0f"),
                    },
                )
            if driver is not None and getattr(box, "vb_l", 0.0) > 0:
                with st.container(border=True):
                    st.markdown("##### 🎯 Plausible Catalog PR Combos")
                    ref_fb = float(_acoustics.suggest_reflex_alignment(driver).fb_hz)
                    pr_matches = _acoustics.plausible_passive_radiators(driver, box.vb_l, ref_fb)
                    if pr_matches:
                        st.caption(
                            f"{len(pr_matches)} plausible catalog configurations matched to driver "
                            f"(Sd = {driver.sd_cm2:.1f} cm², Vb = {box.vb_l:.1f} L, target Fb ≈ {ref_fb:.1f} Hz)."
                        )
                        match_rows = []
                        for m in pr_matches:
                            match_rows.append({
                                "Configuration": f"{m.pr_count}x {m.preset_name}",
                                "Brand": m.brand,
                                "Sp total cm²": m.sp_total_cm2,
                                "Sp/Sd Ratio": m.area_ratio,
                                "Vd Headroom": m.vd_ratio,
                                "Added Mass / PR (g)": m.added_mass_g,
                                "Fp eff. (Hz)": m.effective_fp_hz,
                                "Rating": m.quality_rating,
                            })
                        st.dataframe(
                            pd.DataFrame(match_rows),
                            width="stretch",
                            hide_index=True,
                            column_config={
                                "Sp total cm²": st.column_config.NumberColumn(format="%.1f"),
                                "Sp/Sd Ratio": st.column_config.NumberColumn(format="%.2f"),
                                "Vd Headroom": st.column_config.NumberColumn(format="%.1f"),
                                "Added Mass / PR (g)": st.column_config.NumberColumn(format="%.1f"),
                                "Fp eff. (Hz)": st.column_config.NumberColumn(format="%.1f"),
                            },
                        )
        else:
            if valid_ports:
                with st.container(border=True):
                    st.markdown("##### 🛠️ Duct Blueprint & Physical Cut Specs")
                    
                    # Synchronize Blueprint duct with target_duct
                    if len(valid_ports) > 1:
                        if target_duct.startswith("All"):
                            blueprint_options = [r["Port"] for r in valid_ports]
                            blueprint_state_key = "flared_blueprint_focus_duct"
                            blueprint_widget_key = "flared_calc_port_sel"
                            saved_blueprint_focus = str(st.session_state.get(
                                blueprint_state_key,
                                st.session_state.get(
                                    blueprint_widget_key, blueprint_options[0]
                                ),
                            ))
                            if saved_blueprint_focus not in blueprint_options:
                                saved_blueprint_focus = blueprint_options[0]

                            # Streamlit can drop the value of a later radio
                            # when an earlier flare-profile radio triggers the
                            # rerun. Rehydrate the widget from durable state
                            # before instantiation so its visual selection and
                            # the row used for the drawing remain identical.
                            st.session_state[blueprint_widget_key] = (
                                saved_blueprint_focus
                            )
                            bp_port_name = st.radio(
                                "Blueprint Focus Duct (Single-Click)",
                                blueprint_options,
                                horizontal=True,
                                key=blueprint_widget_key,
                                on_change=_persist_widget_selection,
                                args=(blueprint_widget_key, blueprint_state_key),
                                help="Click any duct to inspect blueprint CAD geometry and physical fabrication dimensions.",
                            )
                            st.session_state[blueprint_state_key] = bp_port_name
                        else:
                            bp_port_name = target_duct
                            st.session_state["flared_blueprint_focus_duct"] = (
                                bp_port_name
                            )
                            st.caption(f"Inspecting active target: **{bp_port_name}**")
                        sel_row = next((r for r in valid_ports if r["Port"] == bp_port_name), valid_ports[0])
                    else:
                        sel_row = valid_ports[0]

                    sel_p_name = sel_row["Port"]
                    sel_p_style = _clean_style_str(st.session_state.get(f"flared_style_{sel_p_name}", st.session_state.get("flared_calc_style", "both")), "both")
                    sel_p_rad = float(st.session_state.get(f"flared_radius_{sel_p_name}", st.session_state.get("flared_calc_radius_cm", 2.5)))

                    fdims_sel = _acoustics.flared_port_dimensions_cm(
                        volume_l=sel_row.get("_volume_l", 20.0),
                        fb_hz=sel_row.get("_fb_hz", 40.0),
                        diameter_cm=sel_row["Diameter cm"],
                        flare_radius_cm=sel_p_rad,
                        flare_style=sel_p_style,
                    )

                    # 3D & In-Scale CAD Parameters (stored per port in session_state)
                    d_throat_mm = float(sel_row["Diameter cm"] * 10.0)
                    d_mouth_mm = float(fdims_sel["outer_diameter_cm"] * 10.0)
                    length_mm = float(fdims_sel["overall_length_cm"] * 10.0)
                    flare_rad_mm = float(sel_p_rad * 10.0)
                    display_length_mm = int(np.floor(length_mm + 0.5))
                    display_half_length_mm = display_length_mm / 2.0

                    cad_wall_mm = float(st.session_state.get(f"stl_wall_{sel_p_name}", 4.0))
                    cad_has_flange = bool(st.session_state.get(f"stl_has_flange_{sel_p_name}", True))
                    cad_flange_th_mm = float(st.session_state.get(f"stl_flange_th_{sel_p_name}", 6.0))
                    cad_flange_d_mm = float(st.session_state.get(f"stl_flange_d_{sel_p_name}", d_mouth_mm + 26.0))
                    cad_bolt_cnt = int(st.session_state.get(f"stl_bolt_cnt_{sel_p_name}", 4))
                    cad_bolt_d_mm = float(st.session_state.get(f"stl_bolt_d_{sel_p_name}", 4.2))
                    cad_bolt_pcd_mm = float(st.session_state.get(f"stl_bolt_pcd_{sel_p_name}", (d_mouth_mm + cad_flange_d_mm) / 2.0))

                    # 1:1 In-Scale Physical CAD Blueprint (SVG)
                    svg_content = _port_cad.generate_port_svg_cad(
                        d_throat_mm=d_throat_mm,
                        d_mouth_mm=d_mouth_mm,
                        length_mm=length_mm,
                        flare_style=sel_p_style,
                        flare_radius_mm=flare_rad_mm,
                        wall_thickness_mm=cad_wall_mm,
                        has_flange=cad_has_flange,
                        flange_diameter_mm=cad_flange_d_mm,
                        flange_thickness_mm=cad_flange_th_mm,
                        bolt_count=cad_bolt_cnt,
                        bolt_diameter_mm=cad_bolt_d_mm,
                        bolt_pcd_mm=cad_bolt_pcd_mm,
                        svg_width=720,
                        svg_height=240,
                    )

                    html_wrap = (
                        '<div style="display:flex; justify-content:center; align-items:center; width:100%; height:250px; '
                        'background:rgba(255,255,255,0.02); border-radius:8px; '
                        'border:1px solid rgba(255,255,255,0.08); overflow:hidden;">'
                        f'{svg_content}'
                        '</div>'
                    )
                    _st_components.html(html_wrap, height=260)

                    m1, m2, m3, m4 = st.columns(4)
                    if sel_p_style == "hourglass":
                        m1.metric("Fabrication", "2x Flared Halves", f"L/2 = {display_half_length_mm:.1f} mm")
                        m2.metric("Overall Length", f"{display_length_mm} mm", "Flange-to-Flange")
                        m3.metric("Flared Mouths Ø", f"{fdims_sel['outer_diameter_cm']:.1f} cm", f"Flare R: {sel_p_rad:.1f} cm")
                        m4.metric("Center Throat Ø", f"{sel_row['Diameter cm']:.1f} cm", "Min Restriction")
                    else:
                        m1.metric("Straight Cut", f"{fdims_sel['straight_length_cm']:.1f} cm", "Standard tube")
                        m2.metric("Overall Length", f"{display_length_mm} mm", "Flange-to-Flange")
                        m3.metric("Mouth Ø", f"{fdims_sel['outer_diameter_cm']:.1f} cm", f"Flare R: {sel_p_rad:.1f} cm")
                        m4.metric("Duct Volume", f"{fdims_sel['volume_displacement_l']:.2f} L", "Displacement")

                    st.caption(
                        f"Selected **{sel_row['Port']}** (Ø {sel_row['Diameter cm']:.1f} cm) with {sel_p_style.replace('_', ' ')}: "
                        f"Recommended threshold **{fdims_sel['chuffing_limit_ms']:.1f} m/s** · Current Peak MOL: **{sel_row['Peak m/s (MOL)']:.1f} m/s**."
                    )

                    # 3D CAD & STL Export (3D Printing / CNC Machining)
                    with st.expander(f"🛠️ 3D CAD & STL Mesh Generator for {sel_row['Port']} (3D Printing & CNC)", expanded=True):
                        st.caption("Customize 3D printable manifold mesh with wall thickness, mounting flange and bolt hole pattern.")
                        
                        p_col1, p_col2, p_col3, p_col4 = st.columns(4)
                        with p_col1:
                            wall_mm_val = st.slider(
                                "Wall Thickness (mm)",
                                min_value=2.0,
                                max_value=12.0,
                                value=cad_wall_mm,
                                step=0.5,
                                key=f"stl_wall_{sel_p_name}",
                                help="Solid tube wall thickness for 3D printing and mechanical rigidity.",
                            )
                        with p_col2:
                            has_flange_val = st.checkbox(
                                "Mounting Flange",
                                value=cad_has_flange,
                                key=f"stl_has_flange_{sel_p_name}",
                                help="Add an integrated baffle-mounting flange with screw holes.",
                            )
                        with p_col3:
                            flange_th_val = st.slider(
                                "Flange Thickness (mm)",
                                min_value=3.0,
                                max_value=20.0,
                                value=cad_flange_th_mm,
                                step=1.0,
                                key=f"stl_flange_th_{sel_p_name}",
                                disabled=not has_flange_val,
                            )
                        with p_col4:
                            min_flange_d = float(d_mouth_mm + 10.0)
                            flange_d_val = st.number_input(
                                "Flange Outer Ø (mm)",
                                min_value=min_flange_d,
                                max_value=float(d_mouth_mm + 150.0),
                                value=max(min_flange_d, cad_flange_d_mm),
                                step=2.0,
                                key=f"stl_flange_d_{sel_p_name}",
                                disabled=not has_flange_val,
                            )

                        h_col1, h_col2, h_col3, h_col4 = st.columns(4)
                        with h_col1:
                            bolt_cnt_val = st.selectbox(
                                "Screw Holes",
                                [0, 2, 3, 4, 6, 8],
                                index=[0, 2, 3, 4, 6, 8].index(cad_bolt_cnt) if cad_bolt_cnt in [0, 2, 3, 4, 6, 8] else 3,
                                key=f"stl_bolt_cnt_{sel_p_name}",
                                disabled=not has_flange_val,
                            )
                        with h_col2:
                            bolt_d_val = st.number_input(
                                "Screw Hole Ø (mm)",
                                min_value=2.0,
                                max_value=12.0,
                                value=cad_bolt_d_mm,
                                step=0.2,
                                key=f"stl_bolt_d_{sel_p_name}",
                                disabled=(not has_flange_val or bolt_cnt_val == 0),
                            )
                        with h_col3:
                            min_pcd = float(d_mouth_mm + bolt_d_val + 2.0)
                            max_pcd = float(flange_d_val - bolt_d_val - 2.0)
                            default_pcd = max(min_pcd, min(max_pcd, (d_mouth_mm + flange_d_val) / 2.0))
                            bolt_pcd_val = st.number_input(
                                "Bolt Circle PCD (mm)",
                                min_value=min_pcd,
                                max_value=max(min_pcd, max_pcd),
                                value=default_pcd,
                                step=1.0,
                                key=f"stl_bolt_pcd_{sel_p_name}",
                                disabled=(not has_flange_val or bolt_cnt_val == 0),
                            )
                        with h_col4:
                            split_options = list(_STL_SPLIT_LABELS)
                            default_split = (
                                "half" if sel_p_style == "hourglass" else "full"
                            )
                            split_key = f"stl_split_{sel_p_name}"
                            # Older sessions stored the human-readable label.
                            # Canonical slugs make the visible selection exactly
                            # the value passed to mesh generation and download.
                            normalized_split = _normalize_stl_split_mode(
                                st.session_state.get(split_key, default_split),
                                default_split,
                            )
                            if st.session_state.get(split_key) != normalized_split:
                                st.session_state[split_key] = normalized_split
                            split_mode_code = st.selectbox(
                                "Split Mode",
                                split_options,
                                format_func=lambda slug: _STL_SPLIT_LABELS[slug],
                                key=split_key,
                                help="2-piece symmetric halves print flat on bed with 0 supports.",
                            )

                        # Generate Binary STL
                        stl_bytes = _port_cad.generate_parametric_port_stl(
                            d_throat_mm=d_throat_mm,
                            d_mouth_mm=d_mouth_mm,
                            length_mm=length_mm,
                            flare_style=sel_p_style,
                            flare_radius_mm=flare_rad_mm,
                            wall_thickness_mm=wall_mm_val,
                            has_flange=has_flange_val,
                            flange_diameter_mm=flange_d_val,
                            flange_thickness_mm=flange_th_val,
                            bolt_count=bolt_cnt_val,
                            bolt_diameter_mm=bolt_d_val,
                            bolt_pcd_mm=bolt_pcd_val,
                            split_mode=split_mode_code,
                            rings=72,
                            n_pts=100,
                        )

                        clean_p_slug = sel_p_name.lower().replace(" ", "_").replace("(", "").replace(")", "")
                        file_name_stl = f"port_{clean_p_slug}_{sel_p_style}_{split_mode_code}.stl"

                        st.download_button(
                            label=f"⬇️ Download Watertight 3D Mesh ({file_name_stl} · {len(stl_bytes)/1024:.1f} KB)",
                            data=stl_bytes,
                            file_name=file_name_stl,
                            mime="model/stl",
                            key=f"download_stl_{clean_p_slug}_{sel_p_style}_{split_mode_code}",
                            use_container_width=True,
                            type="primary",
                        )
                        st.caption("✨ Ready for direct import into Bambu Studio, OrcaSlicer, PrusaSlicer, Cura, or FreeCAD/Fusion 360.")
            else:
                st.info("No active port diameters configured (set Ø > 0 cm to view CAD blueprint).")

    # 3. Full-width Cut Sheet & Manufacturing Table
    if not passive_radiator and valid_ports:
        with st.container(border=True):
            st.markdown("##### 📋 Manufacturing Cut Sheet & Port Specifications")
            cols_to_show = [
                "Port", "Flare Profile", "Diameter cm", "Straight Cut cm", "Overall Length cm",
                "Mouth Ø cm", "Duct Vol (L)", "Peak m/s", "Peak m/s (MOL)", "Peak at Hz"
            ]
            st.dataframe(
                pd.DataFrame(display_rows)[cols_to_show],
                width="stretch",
                hide_index=True,
                column_config={
                    "Diameter cm": st.column_config.NumberColumn(format="%.1f"),
                    "Straight Cut cm": st.column_config.NumberColumn(format="%.1f"),
                    "Overall Length cm": st.column_config.NumberColumn(format="%.1f"),
                    "Mouth Ø cm": st.column_config.NumberColumn(format="%.1f"),
                    "Duct Vol (L)": st.column_config.NumberColumn(format="%.2f"),
                    "Peak m/s": st.column_config.NumberColumn(format="%.1f"),
                    "Peak m/s (MOL)": st.column_config.NumberColumn(format="%.1f"),
                    "Peak at Hz": st.column_config.NumberColumn(format="%.0f"),
                },
            )


def _csv_bytes(result: _acoustics.SimulationResult) -> bytes:
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
        _acoustics.group_delay_ms(result),
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
_default("driver_sd_cm2", _acoustics.sd_from_diameter(104.0))
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
_default("preset_family_filter", ["All"])
_default("preset_source_filter", ["All"])
_default("preset_size_filter", ["All"])
_default("preset_class_filter", ["All"])
_default("preset_search", "")
_default("preset_price_enabled", False)
_default("preset_max_price", 0.0)
_default("preset_price_currency", "EUR")
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
_default("pr_preset_name", "Custom")
_default("pr_sp_cm2", 200.0)
_default("pr_fp_hz", 20.0)
_default("pr_qmp", 5.0)
_default("pr_mmp_g", 100.0)
_default("pr_added_mass_g", 0.0)
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
_default("bp8_v1_l", 10.0)
_default("bp8_f1_hz", 100.0)
_default("bp8_dp1_cm", 5.0)
_default("bp8_lp1_cm", 10.0)
_default("bp8_v2_l", 30.0)
_default("bp8_f2_hz", 35.0)
_default("bp8_dp2_cm", 5.0)
_default("bp8_lp2_cm", 10.0)
_default("bp8_v3_l", 40.0)
_default("bp8_f3_hz", 60.0)
_default("bp8_dp3_cm", 7.0)
_default("bp8_lp3_cm", 12.0)
_default("bp8_q_abs_1", 15.0)
_default("bp8_q_abs_2", 15.0)
_default("bp8_q_abs_3", 15.0)
_default("bp8_q_leak_1", 1000.0)
_default("bp8_q_leak_2", 1000.0)
_default("bp8_q_leak_3", 1000.0)
_default("bp8_q_port_1", 15.0)
_default("bp8_q_port_2", 15.0)
_default("bp8_q_port_3", 15.0)
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
_default("plot_show_tuning_markers", True)
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
_default("opt_max_ripple_freq_hz", 0.0)
_default("opt_excursion_ratio", 1.0)
_default("opt_max_gd_ms", 0.0)
_default("workspace_mode", "Bass Match")
_default("ui_show_advanced", False)
_ensure_finder_defaults()
_ensure_price_currency_default()
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
        _set_box_strategy_state("Max extension")
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
_apply_pending_batch_comparison()
_sync_active_design_comparison_tab()
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

_initialize_alignment_defaults()
_sync_auto_alignment_if_needed()

finder_library_filters_slot = st.empty()


current_ts = None
current_alignment = None
current_reflex_alignment = None
current_bandpass4_alignment = None
current_bandpass6_alignment = None
current_sealed_alignment = None
derived = None

with st.sidebar:
    if _BRAND_IMAGE.exists():
        with st.container(key="brand_logo"):
            st.image(str(_BRAND_IMAGE), width="stretch")
        st.markdown(
            f"<div style='text-align: right; color: rgba(255,255,255,0.4); font-size: 0.75rem; margin-top: -0.5rem; margin-bottom: 1rem;'>v{_VERSION}</div>", 
            unsafe_allow_html=True
        )
    else:
        st.title("Load Forge")
        st.caption(f"v{_VERSION}")
    _render_project_menu()
    _render_workspace_tabs()
    workspace_mode = str(st.session_state.get("workspace_mode", "Bass Match"))
    
    if workspace_mode == "Bass Match":
        bm_tab1, bm_tab2, bm_tab3 = st.tabs(
            ["Load type", "Performance filters", "Library filters"],
            key="bass_match_sidebar_tab",
        )
        
        with bm_tab1:
            if "finder_load_types" not in st.session_state:
                st.session_state["finder_load_types"] = [
                    str(st.session_state.get("load_type", "DCCAV"))]
            _finder_load_set = set(st.session_state["finder_load_types"])
            _render_load_type_buttons(_finder_load_set, single_select=False)
            st.caption("Toggle the loads you want to compare. At least one must stay active.")
            _render_find_driver_target_sidebar()
            with st.expander("Advanced evaluation"):
                _finder_selectbox(
                    "Search profile",
                    list(_ranking.SEARCH_PROFILES.keys()),
                    key="finder_search_profile",
                    help="Standard (1 credit/driver): 60 evaluations per candidate with adaptive spectral verification. Deep (2 credits/driver): 120 evaluations per candidate for maximum exploration depth.",
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
                    "Simulation resolution (points)", min_value=80, max_value=1000,
                    step=20, key="finder_points",
                )
                st.button(
                    "Reset Finder defaults",
                    key="finder_reset_defaults",
                    on_click=_reset_finder_defaults,
                    width="stretch",
                    help="Restore the practical quick-scan profile without changing the active design.",
                )
        with bm_tab2:
            _render_find_driver_goal_sidebar()

        all_preset_names = _acoustics.driver_preset_names()
        with bm_tab3:
            _render_finder_library_filters(all_preset_names)

        def _live_or_aggregate_filter(key: str):
            live = st.session_state.get(f"{key}__select_v5")
            aggregate = st.session_state.get(key, ["All"])
            # Empty live multiselect means All only when no restored/project
            # aggregate carries a concrete selection.
            return live if live else aggregate

        filtered_preset_names = _filter_driver_preset_names(
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
        _sync_finder_library_selection(filtered_preset_names)
        if bm_tab3.open:
            with bm_tab3:
                _render_find_driver_actions(filtered_preset_names)

    else:
        bd_tab1, bd_tab2, bd_tab3 = st.tabs(["Driver", "Load Selection", "Enclosure Parameters"])
        
        all_preset_names = _acoustics.driver_preset_names()
        with bd_tab1:
            st.text_input(
                "Search preset",
                key="preset_search",
                placeholder="Manufacturer or part number",
            )
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
                format_func=lambda value: (
                    value if value == "Custom"
                    else _driver_preset_display_label(value)
                ),
            )
            if preset_name != "Custom":
                try:
                    preset_info = _acoustics.driver_preset_info(preset_name)
                    purchase = _purchase_markdown(preset_info)
                    preset_driver = _acoustics.get_driver_preset(preset_name)
                except ValueError:
                    purchase = None
                    preset_info = None
                    preset_driver = None
                if purchase:
                    st.markdown(purchase)
                if preset_info is not None and preset_driver is not None:
                    manufacturer, part_number = _driver_preset_identity_fields(
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
                        _render_driver_mechanical_drawing(preset_info.mechanical)
                    
            catalog_source_preset = (
                preset_name if preset_name != "Custom"
                else str(st.session_state.get("_admin_catalog_source_preset", ""))
            )
            if (
                _maintenance_allowed()
                and _catalog_path_for_preset(catalog_source_preset)
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
                        saved_name = _update_catalog_driver_from_box_design(
                            catalog_source_preset, _driver_from_state(),
                        )
                    except ValueError as exc:
                        st.error(f"Could not update catalog T/S: {exc}")
                    else:
                        st.session_state["driver_preset_name"] = catalog_source_preset
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

            p_col1, p_col2 = st.columns([1, 1], vertical_alignment="bottom")
            with p_col1:
                st.radio("Piston mode", ["Diameter", "Sd"], horizontal=True, key="driver_sd_mode",
                         on_change=_on_driver_param_change, label_visibility="collapsed")
            with p_col2:
                if st.session_state.get("driver_sd_mode", "Diameter") == "Diameter":
                    st.number_input("Piston diameter (mm)", min_value=10.0, max_value=1000.0,
                                    step=_step5("driver_diameter_mm", 0.1), key="driver_diameter_mm",
                                    on_change=_on_driver_param_change)
                else:
                    st.number_input("Sd (cm²)", min_value=1.0, max_value=5000.0, step=_step5("driver_sd_cm2", 1.0),
                                    key="driver_sd_cm2", on_change=_on_driver_param_change)

            if st.session_state.get("driver_sd_mode", "Diameter") == "Diameter":
                st.caption(f"Sd = {_acoustics.sd_from_diameter(st.session_state.get('driver_diameter_mm', 100)):.1f} cm²")

            c_col1, c_col2 = st.columns([1.2, 1.8], vertical_alignment="center")
            with c_col1:
                st.checkbox(
                    "Panel air loading",
                    key="driver_panel_air_load",
                    on_change=_on_driver_param_change,
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
                        on_change=_on_driver_param_change,
                        help="Fraction of the low-frequency baffled-piston air-mass increment.",
                        label_visibility="collapsed"
                    )
            
            if st.session_state.get("driver_panel_air_load", True):
                try:
                    _panel_mass_g, _panel_fs_hz = _acoustics.panel_air_load_metrics(_driver_from_state())
                    st.caption(f"Mounted Fs {_panel_fs_hz:.2f} Hz · added air mass {_panel_mass_g:.3f} g")
                except (KeyError, ValueError):
                    pass

            output_col1, output_col2 = st.columns(2)
            with output_col1:
                st.number_input("Xmax (mm)", min_value=0.0, max_value=100.0, step=_step5("driver_xmax_mm", 0.1),
                                key="driver_xmax_mm", on_change=_on_driver_param_change)
            with output_col2:
                st.number_input("Pe (W)", min_value=0.0, max_value=5000.0, step=_step5("driver_pe_w", 1.0),
                                key="driver_pe_w", on_change=_on_driver_param_change)

            derived = None
            try:
                derived = _acoustics.complete_driver(_driver_from_state())
            except Exception:
                pass

            with st.expander("Advanced driver parameters"):
                d3, d4 = st.columns(2)
                with d3:
                    lbl_mms = f"Mms (g) [calc: {derived.mms_kg*1000:.1f}]" if (derived and not st.session_state.get("driver_mms_g")) else "Mms (g)"
                    step_mms = _step5("driver_mms_g", 0.01, derived.mms_kg*1000 if derived else None)
                    st.number_input(lbl_mms, min_value=0.0, max_value=1000.0, step=step_mms,
                                    key="driver_mms_g", on_change=_on_driver_param_change)

                    lbl_bl = f"Bl (T·m) [calc: {derived.bl_tm:.2f}]" if (derived and not st.session_state.get("driver_bl_tm")) else "Bl (T·m)"
                    step_bl = _step5("driver_bl_tm", 0.01, derived.bl_tm if derived else None)
                    st.number_input(lbl_bl, min_value=0.0, max_value=100.0, step=step_bl,
                                    key="driver_bl_tm", on_change=_on_driver_param_change)
                with d4:
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
            _render_load_type_buttons(_load_set, single_select=True)
            st.selectbox(
                "Driver configuration",
                list(_acoustics.DRIVER_CONFIGURATIONS),
                key="driver_config",
                on_change=_auto_align_current_driver,
                help="Identical drivers sharing one enclosure: series, parallel "
                     "or mixed arrays up to eight drivers, or isobaric arrays "
                     "up to 16 total drivers. Each isobaric pair contributes one "
                     "radiating piston and half one driver's Vas.",
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
                            "No optimized box satisfies the current goal; the "
                            f"starter box is shown instead. ({auto_box_error})"
                        )
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
                    current_optimizer_summary = _current_optimizer_summary(current_ts)
                    if current_optimizer_summary:
                        st.caption(current_optimizer_summary)
                        
            except Exception as exc:
                logger.exception("Driver parameter setup failed")
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
                            st.selectbox(
                                "Passive radiator preset",
                                ["Custom", *_acoustics.passive_radiator_preset_names()],
                                key="pr_preset_name",
                                on_change=_on_pr_preset_change,
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
                                step=_step5("pr_qmp", 0.1), key="pr_qmp")
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
                            active_pr = _pr_box_from_state()
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
                                        f"🎯 Plausible PR Matches ({len(plausible_combos)})",
                                        expanded=False,
                                    ):
                                        st.caption(
                                            f"Catalog combinations for "
                                            f"{current_ts.sd_cm2:.0f} cm² driver in {active_pr.vb_l:.1f} L (target ~{target_tuning:.1f} Hz)."
                                        )
                                        for c in plausible_combos[:8]:
                                            badge = "🟢 Optimal" if c.quality_rating == "Optimal" else ("🟡 Good" if c.quality_rating == "Good" else "⚪ Acceptable")
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
                                                    on_click=_apply_pr_combo,
                                                    args=(c.preset_name, c.pr_count, c.added_mass_g),
                                                    help=f"Tune box to {target_tuning:.1f} Hz using {c.pr_count}x {c.preset_name} (+{c.added_mass_g:.1f}g added mass).",
                                                )
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
                        fc_hz, qtc = _acoustics.sealed_system_metrics(current_ts, _sealed_box_from_state())
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
                elif load_type == "Bandpass 8th order":
                    b1, b2, b3 = st.columns(3)
                    with b1:
                        _box_number_with_nudge(
                            "V1 front (L)", "bp8_v1_l", min_value=0.05,
                            max_value=100000.0, step=0.01, disabled=box_edit_disabled)
                        _box_number_with_nudge(
                            "F1 tuning (Hz)", "bp8_f1_hz", min_value=1.0,
                            max_value=5000.0, step=0.1, disabled=box_edit_disabled)
                    with b2:
                        _box_number_with_nudge(
                            "V2 rear (L)", "bp8_v2_l", min_value=0.05,
                            max_value=100000.0, step=0.01, disabled=box_edit_disabled)
                        _box_number_with_nudge(
                            "F2 tuning (Hz)", "bp8_f2_hz", min_value=1.0,
                            max_value=5000.0, step=0.1, disabled=box_edit_disabled)
                    with b3:
                        _box_number_with_nudge(
                            "V3 plenum (L)", "bp8_v3_l", min_value=0.05,
                            max_value=100000.0, step=0.01, disabled=box_edit_disabled)
                        _box_number_with_nudge(
                            "F3 tuning (Hz)", "bp8_f3_hz", min_value=1.0,
                            max_value=5000.0, step=0.1, disabled=box_edit_disabled)
                    with st.expander("Bandpass loss factors"):
                        l1, l2, l3 = st.columns(3)
                        with l1:
                            st.number_input("Qabs 1", min_value=0.2, max_value=500.0,
                                            step=_step5("bp8_q_abs_1", 0.5), key="bp8_q_abs_1")
                            st.number_input("Qleak 1", min_value=1.0, max_value=10000.0,
                                            step=_step5("bp8_q_leak_1", 10.0), key="bp8_q_leak_1")
                            st.number_input("Qport 1", min_value=0.2, max_value=500.0,
                                            step=_step5("bp8_q_port_1", 0.5), key="bp8_q_port_1")
                        with l2:
                            st.number_input("Qabs 2", min_value=0.2, max_value=500.0,
                                            step=_step5("bp8_q_abs_2", 0.5), key="bp8_q_abs_2")
                            st.number_input("Qleak 2", min_value=1.0, max_value=10000.0,
                                            step=_step5("bp8_q_leak_2", 10.0), key="bp8_q_leak_2")
                            st.number_input("Qport 2", min_value=0.2, max_value=500.0,
                                            step=_step5("bp8_q_port_2", 0.5), key="bp8_q_port_2")
                        with l3:
                            st.number_input("Qabs 3", min_value=0.2, max_value=500.0,
                                            step=_step5("bp8_q_abs_3", 0.5), key="bp8_q_abs_3")
                            st.number_input("Qleak 3", min_value=1.0, max_value=10000.0,
                                            step=_step5("bp8_q_leak_3", 10.0), key="bp8_q_leak_3")
                            st.number_input("Qport 3", min_value=0.2, max_value=500.0,
                                            step=_step5("bp8_q_port_3", 0.5), key="bp8_q_port_3")
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

    _render_catalog_crawl_report()

    if _maintenance_allowed():
        st.markdown("---")
        with st.expander("🛠️ Admin Tools", expanded=False):
            st.caption("Administrator Console")
            st.link_button(
                "📦 Catalog Maintenance ↗",
                "/?maintenance=1",
                use_container_width=True,
                help="Open Catalog Maintenance in a new tab.",
            )
            st.link_button(
                "👥 User Management ↗",
                "/?admin_users=1",
                use_container_width=True,
                help="Open User Management & Credits Console in a new tab.",
            )


def _render_user_management() -> None:
    """Admin-only dashboard to view users, credit balances, change plans and adjust credits."""
    c_back, c_title = st.columns([1.5, 8.5], vertical_alignment="center")
    with c_back:
        if st.button("← Back to app", key="user_mgmt_back_btn"):
            st.session_state["workspace_mode"] = "Bass Match"
            st.rerun()
    with c_title:
        st.markdown("### 👥 User & Credits Management")
    st.caption("Administrator console · Real-time Firestore users & credit balances")

    accounts = _ACCOUNT_STORE.list_all_accounts()
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
                admin_badge = " 👑 *(Admin)*" if acc.is_admin else ""
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
                        _ACCOUNT_STORE.update_plan(acc.email or acc.uid, new_plan)
                        st.success(f"Plan updated to {new_plan}")
                        st.rerun()
            with col_credits:
                st.markdown(f"💳 **{acc.credits_balance:,}** / {acc.credits_monthly_quota:,}")
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
                        _ACCOUNT_STORE.adjust_credits(acc.email or acc.uid, delta)
                        st.success(f"Adjusted by {delta:+d} credits")
                        st.rerun()


_maintenance_requested = str(st.query_params.get("maintenance", "")) == "1"
if _maintenance_requested:
    _render_catalog_maintenance()
    st.stop()

_admin_users_requested = str(st.query_params.get("admin_users", "")) == "1"
if _admin_users_requested:
    _render_user_management()
    st.stop()

if workspace_mode == "Catalog Maintenance":
    _render_catalog_maintenance()
    st.stop()

if workspace_mode == "User Management":
    _render_user_management()
    st.stop()

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
    is_bandpass8 = load_type == "Bandpass 8th order"
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
    elif is_bandpass8:
        box = _bandpass8_box_from_state()
    elif is_sealed:
        box = _sealed_box_from_state()
    elif is_infinite_baffle:
        box = None
    else:
        box = _box_from_state()
    sim_f_min = float(st.session_state["sim_f_min"])
    sim_f_max = float(st.session_state["sim_f_max"])
    sim_points = int(st.session_state["sim_points"])
    sim_voltage = float(st.session_state["sim_voltage"])
    sim_series_r = float(st.session_state.get("sim_series_r_ohm", 0.0))
    engine_revision = _simulation_engine_revision()
    result, metrics, thresholds, z_peak_freqs = _simulate_design_cached(
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
    simulation_signature = _design_simulation_signature(
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
            port_geometry_rows.append(_port_geometry_row(
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
            port_geometry_rows.append(_port_geometry_row(
                "Front vent (External)", vent_d_cm, box.vp_l, box.fp_hz, 1.43, result, "lower"))
    elif is_bandpass6:
        rear_d_cm = float(st.session_state.get("bandpass6_port_d_r_cm", 0.0))
        front_d_cm = float(st.session_state.get("bandpass6_port_d_p_cm", 0.0))
        if rear_d_cm > 0.0:
            port_geometry_rows.append(_port_geometry_row(
                "Rear vent (External)", rear_d_cm, box.vr_l, box.fr_hz, 1.43, result, "upper"))
        if front_d_cm > 0.0:
            port_geometry_rows.append(_port_geometry_row(
                "Front vent (External)", front_d_cm, box.vp_l, box.fp_hz, 1.43, result, "lower"))
    elif is_bandpass8:
        p1_d_cm = float(st.session_state.get("bp8_dp1_cm", 0.0))
        p2_d_cm = float(st.session_state.get("bp8_dp2_cm", 0.0))
        p3_d_cm = float(st.session_state.get("bp8_dp3_cm", 0.0))
        if p1_d_cm > 0.0:
            port_geometry_rows.append(_port_geometry_row(
                "Port 1 (Internal -> C3)", p1_d_cm, box.v1_l, box.f1_hz, 1.43, result, "lower"))
        if p2_d_cm > 0.0:
            port_geometry_rows.append(_port_geometry_row(
                "Port 2 (Internal -> C3)", p2_d_cm, box.v2_l, box.f2_hz, 1.43, result, "lower"))
        if p3_d_cm > 0.0:
            port_geometry_rows.append(_port_geometry_row(
                "Port 3 (External radiating)", p3_d_cm, box.v3_l, box.f3_hz, 1.43, result, "upper"))
    elif load_type == "DCCAV":
        upper_d_cm = float(st.session_state.get("box_port_d_h_cm", 0.0))
        lower_d_cm = float(st.session_state.get("box_port_d_l_cm", 0.0))
        if upper_d_cm > 0.0:
            port_geometry_rows.append(_port_geometry_row(
                "Upper port (Internal inter-chamber)", upper_d_cm, box.vh_l, box.fh_hz, 1.64, result, "upper"))
        if lower_d_cm > 0.0:
            port_geometry_rows.append(_port_geometry_row(
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

    comparison_tabs = _update_active_design_comparison(
        load_type,
        box,
        result,
        simulation_signature,
    )
    _render_editable_design_tabs(
        comparison_tabs,
        load_type,
        box,
        result,
    )

    tab_labels = ["Response", "Excursion", "Impedance"]
    if not (is_sealed or is_infinite_baffle):
        tab_labels.append("Ports")
    tab_labels.append("Group Delay")
    if not is_infinite_baffle and not is_pr:
        tab_labels.append("Atlas")
    design_tabs = dict(zip(
        tab_labels,
        st.tabs(
            tab_labels,
            key="design_analysis_tab",
            on_change="rerun",
        ),
        strict=True,
    ))

    # Stateful tabs expose which panel is open. Hidden Streamlit tabs execute
    # by default, which previously rebuilt five charts and the Atlas controls
    # after every unrelated click. Render only the selected analysis panel.
    if design_tabs["Response"].open:
        with design_tabs["Response"]:
            _render_response_tab(
                current_ts, load_type, box, result, thresholds, freq,
                sim_voltage, sim_series_r,
            )
    elif design_tabs["Excursion"].open:
        with design_tabs["Excursion"]:
            st.subheader("Cone Excursion")
            xmax_mm = float(st.session_state.get("driver_xmax_mm", 0.0))
            st.altair_chart(
                _plot_excursion(result, xmax_mm),
                width="stretch",
                key=f"excursion_chart_{chart_sig}",
            )
            if xmax_mm > 0.0:
                st.caption(f"Dashed emerald line: driver Xmax = {xmax_mm:.1f} mm.")
            else:
                st.caption("Set the driver Xmax to draw the excursion limit line.")
    elif design_tabs["Impedance"].open:
        with design_tabs["Impedance"]:
            st.subheader("Electrical Impedance")
            st.altair_chart(
                _plot_impedance(result),
                width="stretch",
                key=f"impedance_chart_{chart_sig}",
            )
    elif "Ports" in design_tabs and design_tabs["Ports"].open:
        with design_tabs["Ports"]:
            _render_ports_tab(
                result, port_geometry_rows, load_type,
                driver=current_ts, box=box,
                passive_radiator=is_pr,
            )
    elif design_tabs["Group Delay"].open:
        with design_tabs["Group Delay"]:
            st.subheader("Group Delay")
            gd_limit_ms = (
                float(st.session_state.get("opt_max_gd_ms", 0.0))
                if _alignment_uses_optimizer() else 0.0
            )
            st.altair_chart(
                _plot_group_delay(result, gd_limit_ms),
                width="stretch",
                key=f"gd_chart_{chart_sig}",
            )
            if gd_limit_ms > 0.0:
                st.caption(
                    "Dashed emerald line: optimizer group-delay limit = "
                    f"{gd_limit_ms:.0f} ms."
                )
    elif "Atlas" in design_tabs and design_tabs["Atlas"].open:
        with design_tabs["Atlas"]:
            _render_atlas_tab(current_ts, load_type, box, sim_voltage)

    active_load_image = _LOAD_TYPE_IMAGES.get(load_type)
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
                ("F3", _fmt_hz(thresholds[3])),
                ("Peak LF SPL", _fmt_db(metrics["max_spl_db"])),
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
                        "Heuristic design-health indicator. It starts at 100 "
                        "and deducts points for model warnings, excursion "
                        "violations and impractical port geometry."
                        if metric[0] == "Forge Score"
                        else None
                    )
                    cols[j].metric(metric[0], metric[1], help=metric_help)

            # Gamification / Performance Badges
            badges = []
            if not is_infinite_baffle and not is_sealed:
                has_port_issues = any(
                    "chuffing" in w.lower() or "minimum-area" in w.lower() or "tunes at most" in w.lower()
                    for w in model_warnings
                )
                if len(port_geometry_rows) > 0 and not has_port_issues:
                    badges.append((
                        "🛡️ Port speed within guideline",
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
                        "🏆 F3 below 30 Hz",
                        "rgba(0, 110, 219, 0.08)",
                        "rgba(0, 110, 219, 0.3)",
                        "#006edb"
                    ))
                elif f3_val < 40.0 and vtot_l < 50.0:
                    badges.append((
                        "🔊 F3 below 40 Hz",
                        "rgba(0, 110, 219, 0.08)",
                        "rgba(0, 110, 219, 0.3)",
                        "#006edb"
                    ))
                elif f3_val < 50.0:
                    badges.append((
                        "🎵 F3 below 50 Hz",
                        "rgba(0, 110, 219, 0.08)",
                        "rgba(0, 110, 219, 0.3)",
                        "#006edb"
                    ))

            if not any("sanity" in w.lower() or "warning" in w.lower() for w in model_warnings):
                badges.append((
                    "✅ Model checks passed",
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
            s1.metric("F6", _fmt_hz(thresholds[6]))
            s2.metric("F10", _fmt_hz(thresholds[10]))
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
                e6.metric("Class", _driver_class_label(bandwidth.driver_class))
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
                _csv_bytes(result),
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
