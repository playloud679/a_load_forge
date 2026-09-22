"""Global CSS and load-type/workspace card styling."""

from __future__ import annotations

import base64
from typing import Any

import streamlit as st

from . import constants as _constants
from . import state as _state

GLOBAL_CSS = """
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
        background: transparent !important;
        pointer-events: none !important;
    }
    [data-testid="stToolbar"] { visibility: hidden; }
    [data-testid="stExpandSidebarButton"] {
        pointer-events: auto !important;
        visibility: visible;
    }
    [data-stale="true"] {
        filter: none !important;
        opacity: 1 !important;
    }
    section[data-testid="stSidebar"],
    section[data-testid="stSidebar"] > div {
        background: #000 !important;
        width: 24.5rem !important;
        min-width: 24.5rem !important;
    }
    section[data-testid="stSidebar"] [data-testid="stSidebarContent"],
    section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
        background: #000 !important;
        width: 24.5rem !important;
        min-width: 24.5rem !important;
    }
    section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
        gap: 0.35rem !important;
    }
    html {
        scrollbar-gutter: stable;
        font-size: 16px !important;
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
        text-rendering: optimizeLegibility;
    }
    body,
    [data-testid="stAppViewContainer"],
    section[data-testid="stMain"] {
        scrollbar-gutter: stable;
        background-color: var(--lf-bg-base) !important;
        font-size: 1rem !important;
        color: #f3f4f6 !important;
    }
    [data-testid="stMain"] [data-testid="stVerticalBlock"] {
        gap: 0.45rem !important;
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
    [data-testid="stMainBlockContainer"] {
        padding-top: 0.25rem !important;
        padding-bottom: 0.25rem !important;
        padding-left: 1.25rem !important;
        padding-right: 1.25rem !important;
        max-width: 100% !important;
    }
    section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
        padding-top: 0 !important;
        padding-left: 0.8rem !important;
        padding-right: 0.8rem !important;
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
        padding-bottom: 0.05rem !important;
        margin-top: 0.35rem !important;
    }
    [data-testid="stMainBlockContainer"] [data-testid="stWidgetLabel"] p {
        margin-bottom: 0 !important;
        font-weight: 550 !important;
        font-size: 0.94rem !important;
        color: #f1f5f9 !important;
    }
    section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
    section[data-testid="stSidebar"] label p {
        font-size: 0.90rem !important;
        font-weight: 550 !important;
        color: #f1f5f9 !important;
        line-height: 1.35 !important;
        margin-bottom: 0.05rem !important;
    }
    section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p,
    [data-testid="stCaptionContainer"] p {
        line-height: 1.4 !important;
        font-size: 0.85rem !important;
        color: rgba(255,255,255,0.72) !important;
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
        margin-top: 0.25rem !important;
        margin-bottom: 0.25rem !important;
        border-color: rgba(255,255,255,0.12) !important;
    }

    header[data-testid="stHeader"] {
        background-color: transparent !important;
        pointer-events: none !important;
    }

    [data-testid="stCaptionContainer"] {
        color: rgba(250,250,250,.72);
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
        margin-block: .20rem .45rem;
    }
    .st-key-finder_library_filters [data-testid="stVerticalBlock"] {
        gap: .40rem !important;
    }

    /* Sidebar Search Brief & Segmented Tabs */
    .st-key-sidebar_brief_header_container {
        margin-top: 0.10rem;
        margin-bottom: 0.15rem;
    }
    .st-key-sidebar_brief_header_container .st-key-ui_show_advanced {
        display: flex !important;
        justify-content: flex-end !important;
    }
    .st-key-sidebar_brief_header_container .st-key-ui_show_advanced label,
    .st-key-sidebar_brief_header_container .st-key-ui_show_advanced label p,
    .st-key-sidebar_brief_header_container .st-key-ui_show_advanced div[data-testid="stWidgetLabel"] {
        font-size: 0.86rem !important;
        font-weight: 600 !important;
        color: #cbd5e1 !important;
        white-space: nowrap !important;
        margin: 0 !important;
    }
    .sidebar-brief-header {
        margin-top: 0.10rem;
        margin-bottom: 0.10rem;
    }
    .sidebar-brief-title {
        font-size: 0.92rem;
        font-weight: 700;
        letter-spacing: 0.01em;
        text-transform: none;
        color: #f8fafc;
        white-space: nowrap !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stTabs"] {
        margin-top: 0.15rem !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stTabs"] div[role="tablist"] {
        background: rgba(255, 255, 255, 0.04) !important;
        border: 1px solid rgba(255, 255, 255, 0.10) !important;
        border-radius: 8px !important;
        padding: 3px !important;
        gap: 3px !important;
        display: flex !important;
        width: 100% !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stTabs"] button[role="tab"] {
        flex: 1 1 0% !important;
        text-align: center !important;
        padding: 0.35rem 0.25rem !important;
        border-radius: 6px !important;
        font-size: 0.88rem !important;
        font-weight: 600 !important;
        letter-spacing: 0.01em !important;
        color: rgba(255, 255, 255, 0.70) !important;
        border: none !important;
        background: transparent !important;
        transition: all 0.15s ease !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stTabs"] button[role="tab"]:hover {
        color: #f8fafc !important;
        background: rgba(255, 255, 255, 0.08) !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
        color: #10b981 !important;
        background: #141b27 !important;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3), inset 0 0 0 1px rgba(16, 185, 129, 0.25) !important;
    }
    .sidebar-section-title {
        font-size: 0.88rem !important;
        font-weight: 700 !important;
        letter-spacing: 0.01em !important;
        text-transform: none !important;
        color: #e2e8f0 !important;
        margin: 0.35rem 0 0.15rem 0 !important;
        padding-bottom: 0.12rem !important;
        border-bottom: 1px solid rgba(255, 255, 255, 0.08) !important;
    }
    .sidebar-brief-summary-card {
        background: #141b27;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 8px;
        padding: 0.45rem 0.65rem;
        margin-top: 0.40rem;
        margin-bottom: 0.25rem;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25);
    }
    .sidebar-brief-header-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 0.15rem;
    }
    .sidebar-brief-tag {
        font-size: 0.84rem;
        font-weight: 600;
        letter-spacing: 0.01em;
        text-transform: none;
        color: #cbd5e1;
    }
    .sidebar-brief-count {
        font-size: 0.94rem;
        font-weight: 700;
        color: #f8fafc;
    }
    .st-key-finder_run_search_sidebar div[data-testid="stButton"] button[kind="primary"] {
        background: linear-gradient(135deg, #10b981 0%, #059669 100%) !important;
        border: 1px solid #10b981 !important;
        box-shadow: 0 3px 10px rgba(16, 185, 129, 0.25) !important;
        min-height: 2.6rem !important;
        border-radius: 6px !important;
        transition: filter .16s ease, transform .16s ease, box-shadow .16s ease !important;
    }
    .st-key-finder_run_search_sidebar div[data-testid="stButton"] button p {
        font-size: 0.95rem !important;
        font-weight: 700 !important;
        letter-spacing: .02em !important;
        color: #ffffff !important;
    }
    .st-key-finder_run_search_sidebar div[data-testid="stButton"] button:hover {
        box-shadow: 0 5px 14px rgba(16, 185, 129, 0.38) !important;
        filter: brightness(1.08) !important;
        transform: translateY(-1px) !important;
    }

    .st-key-temp_bass_match_page div[data-testid="stTabs"] div[role="tablist"],
    .st-key-temp_bass_match_page div[data-baseweb="tab-list"] {
        display: none !important;
    }
    .st-key-temp_bass_match_page div[data-testid="stTabs"] {
        gap: 0 !important;
        border: none !important;
        padding: 0 !important;
        margin: 0 !important;
    }

    /* Bass Match Hero Brief (Phase D) */
    .st-key-bass_match_brief {
        background: #0d121a !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 8px !important;
        padding: 0.65rem 1.0rem 0.55rem 1.0rem !important;
        margin-bottom: 0.45rem !important;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.22) !important;
    }
    .bass-match-hero-header {
        display: flex;
        flex-direction: column;
        gap: 0.15rem;
    }
    .bass-match-hero-title {
        font-size: 1.18rem;
        font-weight: 700;
        color: #f8fafc;
        letter-spacing: -0.01em;
    }
    .bass-match-hero-subtitle {
        font-size: 0.88rem;
        color: #94a3b8;
        margin-bottom: 0.45rem;
    }
    .bass-match-brief-summary {
        display: flex;
        flex-direction: column;
        gap: 0.15rem;
        margin-bottom: 0.35rem;
    }
    .bass-match-spec-line-primary {
        font-size: 1.10rem;
        font-weight: 600;
        color: #10b981;
        letter-spacing: 0.01em;
    }
    .bass-match-spec-line-secondary {
        font-size: 0.92rem;
        font-weight: 500;
        color: #cbd5e1;
    }
    .bass-match-readiness-row {
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        font-size: 0.88rem;
        color: #94a3b8;
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.06);
        border-radius: 5px;
        padding: 0.25rem 0.55rem;
        width: fit-content;
        margin-top: 0.25rem;
        margin-bottom: 0.35rem;
    }
    .bass-match-readiness-sep {
        color: rgba(255, 255, 255, 0.25);
    }

    .st-key-active_load_summary {
        border: 1px solid rgba(255,255,255,.16) !important;
        border-radius: 6px !important;
        background: #0f1520 !important;
        padding: .45rem .6rem .45rem !important;
    }
    .st-key-finder_run_search_main div[data-testid="stButton"] button[kind="primary"] {
        background: #10b981 !important;
        border: 1px solid #10b981 !important;
        box-shadow: 0 .25rem 0.85rem rgba(16,185,129,.22) !important;
        min-height: 2.85rem !important;
        border-radius: 6px !important;
        margin-top: 0.35rem !important;
        transition: filter .16s ease, transform .16s ease, box-shadow .16s ease !important;
    }
    .st-key-finder_run_search_main div[data-testid="stButton"] button p {
        font-size: clamp(1.02rem, 1.25vw, 1.15rem) !important;
        font-weight: 700 !important;
        letter-spacing: .02em !important;
        color: #ffffff !important;
    }
    .st-key-finder_run_search_main div[data-testid="stButton"] button:hover {
        box-shadow: 0 .4rem 1.2rem rgba(16,185,129,.35) !important;
        filter: brightness(1.08) !important;
        transform: translateY(-1px) !important;
    }
    .st-key-bass_match_brief > div[data-testid="stVerticalBlock"] {
        gap: .25rem !important;
    }
    .st-key-bass_match_brief h4 {
        font-size: 1.08rem !important;
        font-weight: 700 !important;
        color: #f8fafc !important;
        letter-spacing: -0.01em !important;
        line-height: 1.2 !important;
        margin: 0 !important;
        padding: 0 !important;
    }
    .st-key-bass_match_brief .stMetric {
        min-height: 2.75rem !important;
        padding: .25rem .45rem !important;
        background: rgba(255, 255, 255, 0.025) !important;
        border: 1px solid rgba(255, 255, 255, 0.06) !important;
        border-radius: 6px !important;
    }
    .st-key-bass_match_brief .stMetric [data-testid="stMetricLabel"] p {
        font-size: 0.82rem !important;
        font-weight: 600 !important;
        text-transform: none !important;
        letter-spacing: 0.02em !important;
        color: #94a3b8 !important;
        font-family: ui-monospace, SFMono-Regular, monospace !important;
    }
    .st-key-bass_match_brief .stMetric [data-testid="stMetricValue"] {
        font-size: 1.28rem !important;
        font-weight: 700 !important;
        color: #f8fafc !important;
        font-family: ui-monospace, SFMono-Regular, monospace !important;
    }
    .st-key-bass_match_brief [data-testid="stCaptionContainer"] {
        margin: 0 !important;
    }
    .st-key-bass_match_brief [data-testid="stCaptionContainer"] p {
        font-size: 0.85rem !important;
        color: #94a3b8 !important;
        line-height: 1.3 !important;
    }
    .st-key-bass_match_brief [data-testid="stExpander"] {
        border: 1px solid rgba(255, 255, 255, 0.06) !important;
        border-radius: 6px !important;
        background: rgba(0, 0, 0, 0.12) !important;
        margin-top: 0.15rem !important;
    }
    .finder-constraint-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(9.5rem, 1fr));
        gap: .30rem;
        margin-top: .10rem;
        margin-bottom: .20rem;
        padding: .30rem;
        background: rgba(0, 0, 0, 0.18);
        border-radius: 6px;
        border: 1px solid rgba(255, 255, 255, 0.06);
    }
    .finder-constraint {
        min-width: 0;
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 4px;
        padding: .28rem .45rem;
        background: rgba(255, 255, 255, 0.02);
        transition: background .15s ease, border-color .15s ease;
    }
    .finder-constraint:hover {
        background: rgba(255, 255, 255, 0.04);
        border-color: rgba(255, 255, 255, 0.1);
    }
    .finder-constraint-label {
        color: #94a3b8;
        font-size: .80rem;
        font-weight: 600;
        letter-spacing: .02em;
        line-height: 1;
        text-transform: none;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }
    .finder-constraint-value {
        color: #f1f5f9;
        font-size: .96rem;
        font-weight: 600;
        line-height: 1.25;
        margin-top: .12rem;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        font-family: ui-sans-serif, system-ui, sans-serif;
    }
    .st-key-finder_candidate_pool_expander {
        margin-top: 0.6rem !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 6px !important;
        background: #0d131d !important;
    }
    .st-key-finder_candidate_pool_expander summary {
        font-size: 0.85rem !important;
        font-weight: 600 !important;
        color: #94a3b8 !important;
        padding: 0.45rem 0.75rem !important;
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
        padding: .28rem .50rem !important;
    }
    .stMetric label,
    .stMetric [data-testid="stMetricLabel"] p {
        font-size: 0.82rem !important;
        font-weight: 600 !important;
        color: #94a3b8 !important;
        margin-bottom: -0.15rem !important;
        text-transform: none;
        letter-spacing: 0.02em;
    }
    .stMetric div[data-testid="stMetricValue"] {
        font-size: 1.18rem !important;
        font-weight: 700 !important;
        color: #f8fafc !important;
        line-height: 1.2 !important;
        padding-bottom: 0.05rem !important;
    }

    [data-testid="stVerticalBlockBorderWrapper"] {
        border: 1px solid rgba(255, 255, 255, 0.16) !important;
        background-color: #0d131d !important;
        border-radius: 8px !important;
    }

    /* Tabs emerald indicator & text */
    div[data-testid="stTabs"] { gap: 0 !important; }
    button[data-baseweb="tab"] {
        padding-top: 0.25rem !important;
        padding-bottom: 0.25rem !important;
        font-weight: 600 !important;
        font-size: 0.95rem !important;
        color: rgba(255, 255, 255, 0.72) !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: #10b981 !important;
        border-bottom-color: #10b981 !important;
        font-weight: 700 !important;
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

    /* Multi-select and selectbox restrained theme */
    div[data-baseweb="tag"],
    span[data-baseweb="tag"],
    [data-testid="stMultiSelect"] span[data-baseweb="tag"],
    [data-testid="stMultiSelect"] div[data-baseweb="tag"],
    span[data-testid="stBaseButton-secondary"]:has(svg) {
        background-color: rgba(255, 255, 255, 0.05) !important;
        border: 1px solid rgba(255, 255, 255, 0.14) !important;
        border-radius: 4px !important;
        color: #e2e8f0 !important;
    }
    div[data-baseweb="tag"]:hover,
    span[data-baseweb="tag"]:hover,
    [data-testid="stMultiSelect"] span[data-baseweb="tag"]:hover {
        background-color: rgba(255, 255, 255, 0.08) !important;
        border-color: rgba(255, 255, 255, 0.25) !important;
    }
    div[data-baseweb="tag"] span,
    span[data-baseweb="tag"] span,
    [data-testid="stMultiSelect"] span[data-baseweb="tag"] span {
        color: #e2e8f0 !important;
        font-weight: 500 !important;
    }
    div[data-baseweb="tag"] svg,
    span[data-baseweb="tag"] svg,
    [data-testid="stMultiSelect"] span[data-baseweb="tag"] svg {
        fill: #94a3b8 !important;
        color: #94a3b8 !important;
    }

    /* High-contrast Selectbox, Inputs & Dropdowns */
    div[data-baseweb="select"] > div {
        border: 1px solid rgba(255, 255, 255, 0.20) !important;
        background-color: #141b27 !important;
        border-radius: 6px !important;
        min-height: 2.4rem !important;
    }
    div[data-baseweb="select"] > div:hover {
        border-color: rgba(255, 255, 255, 0.32) !important;
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
    li[data-baseweb="menu-item"]:hover {
        background-color: rgba(255, 255, 255, 0.08) !important;
        color: #f8fafc !important;
    }
    li[data-baseweb="menu-item"][aria-selected="true"] {
        background-color: rgba(16, 185, 129, 0.16) !important;
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
        border-color: rgba(255, 255, 255, 0.32) !important;
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
    .lf-run-stats {
        margin: .5rem 0 .35rem 0;
        padding: .65rem .8rem .7rem;
        border: 1px solid rgba(16,185,129,.35);
        border-radius: 8px;
        background: linear-gradient(180deg, rgba(16,185,129,.10), rgba(16,185,129,.03));
    }
    .lf-run-stats-head {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        gap: .75rem;
        font-size: .92rem;
        color: #d1fae5;
    }
    .lf-run-stats-profile {
        color: #9ca3af;
        font-weight: 500;
        font-size: .78rem;
    }
    .lf-run-stats-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: .55rem;
        margin-top: .5rem;
    }
    .lf-run-stat {
        display: flex;
        flex-direction: column;
        padding: .45rem .55rem;
        border: 1px solid rgba(255,255,255,.10);
        border-radius: 7px;
        background: rgba(15,21,32,.85);
    }
    .lf-run-stat-value {
        font-size: 1.28rem;
        font-weight: 800;
        line-height: 1.15;
        color: #10b981;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace !important;
    }
    .lf-run-stat-label {
        font-size: .72rem;
        text-transform: none;
        letter-spacing: .03em;
        color: #e5e7eb;
    }
    .lf-run-stat-sub {
        margin-top: .1rem;
        font-size: .72rem;
        color: #9ca3af;
    }
    .lf-run-stats-loads {
        margin-top: .5rem;
        font-size: .78rem;
        color: #d1d5db;
    }
    @media (max-width: 900px) {
        .lf-run-stats-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    .st-key-bass_match_result_actions {
        background: rgba(15, 23, 42, 0.7) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 8px !important;
        padding: 0.35rem 0.65rem !important;
        margin-bottom: 0.35rem !important;
    }
    .st-key-bass_match_result_actions div[data-testid="stButton"] button {
        min-height: 2.4rem;
        border-radius: 6px;
        font-weight: 700;
        font-size: 0.98rem;
        letter-spacing: 0.01em;
        transition: all 0.16s ease !important;
    }
    .st-key-bass_match_result_actions div[data-testid="stButton"] button:not(:disabled) {
        background: #10b981 !important;
        border-color: #10b981 !important;
        color: #fff !important;
        box-shadow: 0 2px 10px rgba(16, 185, 129, 0.3) !important;
    }
    .st-key-bass_match_result_actions div[data-testid="stButton"] button:not(:disabled):hover {
        filter: brightness(1.08) !important;
        box-shadow: 0 4px 14px rgba(16, 185, 129, 0.45) !important;
        transform: translateY(-1px) !important;
    }
    .st-key-bass_match_result_actions div[data-testid="stButton"] button::after {
        content: " →";
    }
    .st-key-bass_match_result_actions div[data-testid="stCaptionContainer"] p {
        font-size: 0.86rem !important;
        color: #94a3b8 !important;
        margin: 0 !important;
        line-height: 1.35 !important;
    }

    .bass-match-results-summary {
        display: flex;
        flex-direction: column;
        gap: 0.15rem;
        padding: 0.1rem 0;
    }
    .bass-match-results-summary-primary {
        font-size: 1.02rem;
        font-weight: 600;
        color: #e2e8f0;
        letter-spacing: -0.01em;
        line-height: 1.3;
    }
    .bass-match-results-match-count {
        color: #10b981;
        font-weight: 700;
    }
    .bass-match-results-summary-meta {
        font-size: 0.84rem;
        color: #94a3b8;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        letter-spacing: 0.01em;
    }

    .st-key-finder_edit_search_btn div[data-testid="stButton"] button {
        min-height: 2.05rem !important;
        height: 2.05rem !important;
        padding: 0.15rem 0.65rem !important;
        font-size: 0.85rem !important;
        font-weight: 600 !important;
        border-radius: 5px !important;
        background: rgba(255, 255, 255, 0.04) !important;
        border: 1px solid rgba(255, 255, 255, 0.12) !important;
        color: #cbd5e1 !important;
        transition: all 0.15s ease !important;
    }
    .st-key-finder_edit_search_btn div[data-testid="stButton"] button:hover {
        background: rgba(255, 255, 255, 0.08) !important;
        border-color: rgba(255, 255, 255, 0.22) !important;
        color: #ffffff !important;
    }

    .st-key-finder_match_preview_card,
    .st-key-finder_comparison_preview_card {
        background: #0d131f !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 8px !important;
        padding: 0.65rem 0.85rem !important;
        margin-top: 0.5rem !important;
    }
    .st-key-finder_match_preview_card h4,
    .st-key-finder_comparison_preview_card h4 {
        font-size: 1.02rem !important;
        font-weight: 700 !important;
        color: #f8fafc !important;
        margin-bottom: 0.2rem !important;
    }
    .st-key-finder_match_preview_card .stMetric,
    .st-key-finder_comparison_preview_card .stMetric {
        background: rgba(255, 255, 255, 0.025) !important;
        border: 1px solid rgba(255, 255, 255, 0.06) !important;
        border-radius: 6px !important;
        padding: 0.28rem 0.5rem !important;
    }
    .st-key-finder_match_preview_card .stMetric [data-testid="stMetricValue"],
    .st-key-finder_comparison_preview_card .stMetric [data-testid="stMetricValue"] {
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace !important;
        font-size: 1.22rem !important;
        font-weight: 700 !important;
        color: #f8fafc !important;
    }
    .st-key-finder_match_preview_card .stMetric [data-testid="stMetricLabel"] p,
    .st-key-finder_comparison_preview_card .stMetric [data-testid="stMetricLabel"] p {
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace !important;
        font-size: 0.80rem !important;
        font-weight: 600 !important;
        text-transform: none !important;
        letter-spacing: 0.02em !important;
        color: #94a3b8 !important;
    }
    [data-testid="stDataFrame"] {
        border: 1px solid rgba(255, 255, 255, 0.09) !important;
        border-radius: 6px !important;
    }
    [data-testid="stDataFrame"] div[role="gridcell"],
    [data-testid="stDataFrame"] div[role="columnheader"] {
        font-size: 0.92rem !important;
    }
    div[data-testid="stDownloadButton"] button {
        min-height: 2.1rem !important;
        height: 2.1rem !important;
        padding: 0.15rem 0.75rem !important;
        font-size: 0.85rem !important;
        font-weight: 600 !important;
        border-radius: 5px !important;
        background: rgba(255, 255, 255, 0.04) !important;
        border: 1px solid rgba(255, 255, 255, 0.12) !important;
        color: #cbd5e1 !important;
        transition: all 0.15s ease !important;
    }
    div[data-testid="stDownloadButton"] button:hover {
        background: rgba(255, 255, 255, 0.08) !important;
        border-color: rgba(255, 255, 255, 0.22) !important;
        color: #ffffff !important;
    }
    </style>
    """


def inject_global_css() -> None:
    """Render the app-wide CSS exactly once per run."""
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


def _focused_port_flare_style(state: Any = None) -> str:
    """Resolve the flare style for the duct currently targeted in Ports."""
    values = st.session_state if state is None else state
    global_style = _state._clean_style_str(values.get("flared_calc_style", "both"), "both")
    target = _state._clean_style_str(
        values.get(
            "flared_active_target_duct",
            values.get("flared_target_duct", "All Ducts (Global)"),
        ),
        "All Ducts (Global)",
    )
    if target.startswith("All"):
        return global_style
    return _state._clean_style_str(
        values.get(f"flared_style_{target}", global_style), global_style
    )

@st.cache_data(show_spinner=False)
def _load_type_card_styles(version: str = "square_v5") -> str:
    """Return compact clickable-card CSS with the supplied diagrams embedded."""
    rules = [
        """
        <style>
        [class*="st-key-load_card_"] {
            min-height: unset;
        }
        [class*="st-key-load_card_"] div[data-testid="stButton"] {
            display: flex;
            justify-content: center;
        }
        [class*="st-key-load_card_"] div[data-testid="stButton"] button {
            background-color: #f2f2f0;
            background-position: center;
            background-repeat: no-repeat;
            background-size: 100% 100%;
            border: 1px solid rgba(255,255,255,.16);
            border-radius: .58rem;
            box-shadow: inset 0 1px 0 rgba(255,255,255,.06);
            filter: saturate(.72) brightness(.82) contrast(1.04);
            aspect-ratio: 1 / 1;
            height: auto;
            min-height: unset;
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
            color: rgba(250,250,250,.92);
            font-size: .82rem;
            font-weight: 700;
            line-height: 1.0rem;
            margin: .15rem 0 .10rem;
            min-height: 1.0rem;
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
    for load_type, image_path in _constants._LOAD_TYPE_IMAGES.items():
        if not image_path.exists():
            continue
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        slug = _constants._LOAD_TYPE_SLUGS[load_type]
        rules.append(
            f'.st-key-load_card_{slug} button '
            f'{{ background-image: url("data:image/png;base64,{encoded}"); }}'
        )
    rules.append("</style>")
    return "".join(rules)

@st.cache_data(show_spinner=False)
def _workspace_tab_styles() -> str:
    """Return the two full-image workspace-tab styles with embedded assets."""
    rules = [
        """
        <style>
        .st-key-global_app_bar {
            background: linear-gradient(180deg, rgba(20, 24, 33, 0.88) 0%, rgba(13, 17, 23, 0.96) 100%) !important;
            backdrop-filter: blur(16px) !important;
            -webkit-backdrop-filter: blur(16px) !important;
            border: 1px solid rgba(255, 255, 255, 0.09) !important;
            border-radius: 8px !important;
            padding: 0.25rem 0.60rem !important;
            margin-bottom: 0.45rem !important;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.35) !important;
        }
        .st-key-global_app_bar div[data-testid="stHorizontalBlock"] {
            align-items: center !important;
            gap: 0.45rem !important;
        }
        .st-key-global_app_bar div[data-testid="stColumn"] {
            display: flex !important;
            flex-direction: column !important;
            justify-content: center !important;
            align-items: center !important;
            min-height: 2.1rem !important;
            height: 2.1rem !important;
            padding: 0 !important;
            margin: 0 !important;
        }
        .st-key-global_app_bar div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] {
            width: 100% !important;
            margin: 0 !important;
            padding: 0 !important;
            gap: 0 !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            height: 2.1rem !important;
        }
        .st-key-global_app_bar div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] > div[data-testid="stLayoutWrapper"] {
            width: 100% !important;
            margin: 0 !important;
            padding: 0 !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            height: 2.1rem !important;
        }
        .st-key-global_app_bar div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] > div[data-testid="stLayoutWrapper"] > div[data-testid="element-container"] {
            margin: 0 !important;
            padding: 0 !important;
            width: 100% !important;
            height: 2.1rem !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
        }
        .st-key-global_app_bar div[data-testid="stPopover"] {
            width: 100% !important;
            height: 2.1rem !important;
            margin: 0 !important;
            padding: 0 !important;
        }
        .st-key-global_app_bar div[data-testid="stPopover"] > div:first-child {
            width: 100% !important;
            height: 2.1rem !important;
            margin: 0 !important;
            padding: 0 !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
        }
        .st-key-global_app_bar div[data-testid="stPopover"] > div:nth-child(2) {
            display: none !important;
        }
        .st-key-global_app_bar div[data-testid="stButton"] {
            width: 100% !important;
            height: 2.1rem !important;
            margin: 0 !important;
            padding: 0 !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
        }
        .st-key-global_app_bar button[data-testid="stPopoverButton"],
        .st-key-global_app_bar div[data-testid="stButton"] > button {
            height: 2.1rem !important;
            min-height: 2.1rem !important;
            max-height: 2.1rem !important;
            line-height: 2.1rem !important;
            box-sizing: border-box !important;
            padding: 0 0.60rem !important;
            font-size: 0.88rem !important;
            font-weight: 600 !important;
            letter-spacing: 0.015em !important;
            border-radius: 6px !important;
            background: rgba(255, 255, 255, 0.04) !important;
            border: 1px solid rgba(255, 255, 255, 0.10) !important;
            color: #cbd5e1 !important;
            transition: all 0.15s cubic-bezier(0.16, 1, 0.3, 1) !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1) !important;
            margin: 0 !important;
            width: 100% !important;
            white-space: nowrap !important;
        }
        .st-key-global_app_bar button[data-testid="stPopoverButton"] *,
        .st-key-global_app_bar div[data-testid="stButton"] > button * {
            white-space: nowrap !important;
            font-size: 0.88rem !important;
            margin: 0 !important;
        }
        .st-key-global_app_bar button[data-testid="stPopoverButton"]:hover,
        .st-key-global_app_bar div[data-testid="stButton"] > button:hover {
            background: rgba(255, 255, 255, 0.08) !important;
            border-color: rgba(255, 255, 255, 0.22) !important;
            color: #ffffff !important;
            transform: translateY(-1px) !important;
            box-shadow: 0 2px 5px rgba(0, 0, 0, 0.2) !important;
        }
        .st-key-global_app_bar button[data-testid="stPopoverButton"]:active,
        .st-key-global_app_bar div[data-testid="stButton"] > button:active {
            transform: translateY(0) !important;
            background: rgba(255, 255, 255, 0.05) !important;
        }
        .st-key-global_app_bar div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:first-child button[data-testid="stPopoverButton"] {
            font-weight: 600 !important;
            color: #f8fafc !important;
            background: rgba(255, 255, 255, 0.06) !important;
            border: 1px solid rgba(255, 255, 255, 0.14) !important;
        }
        .st-key-global_app_bar div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:first-child button[data-testid="stPopoverButton"]:hover {
            background: rgba(255, 255, 255, 0.10) !important;
            border-color: rgba(16, 185, 129, 0.4) !important;
        }
        .st-key-global_app_bar .topbar-status-badge {
            height: 2.1rem !important;
            min-height: 2.1rem !important;
            max-height: 2.1rem !important;
            line-height: 2.1rem !important;
            box-sizing: border-box !important;
            margin: 0 !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
        }
        .st-key-global_app_bar div[data-testid="stMarkdown"]:has(.topbar-status-badge),
        .st-key-global_app_bar div[data-testid="stMarkdownContainer"]:has(.topbar-status-badge),
        .st-key-global_app_bar div[data-testid="stMarkdownContainer"]:has(.topbar-status-badge) p {
            margin: 0 !important;
            padding: 0 !important;
            height: 2.1rem !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            line-height: 2.1rem !important;
        }
        .st-key-account_compat_expander {
            display: none !important;
        }
        div[data-testid="stPopoverBody"] {
            background: #0f141c !important;
            border: 1px solid rgba(255, 255, 255, 0.14) !important;
            border-radius: 8px !important;
            box-shadow: 0 12px 32px rgba(0, 0, 0, 0.6) !important;
            padding: 0.85rem !important;
        }

        /* Illustrated Workspace Mode Selectors in Sidebar */
        [class*="st-key-workspace_tab_"] div[data-testid="stButton"] button {
            background-color: #000000;
            border: 1px solid rgba(16,185,129,.46);
            border-radius: .65rem;
            height: 3.2rem;
            min-height: 3.2rem;
            overflow: hidden;
            padding: 0;
            position: relative;
            transition: border-color .16s ease, box-shadow .16s ease, transform .16s ease;
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
        .st-key-workspace_tab_bass_match div[data-testid="stButton"] button[data-testid="stBaseButton-primary"],
        .st-key-workspace_tab_bass_match div[data-testid="stButton"] button[kind="primary"] {
            background-color: #000000 !important;
            border: 2px solid #10b981 !important;
            box-shadow: 0 0 0 1px rgba(16,185,129,.22), 0 0 18px rgba(16,185,129,.25) !important;
        }
        .st-key-workspace_tab_bass_match div[data-testid="stButton"] button[data-testid="stBaseButton-primary"]::before,
        .st-key-workspace_tab_bass_match div[data-testid="stButton"] button[kind="primary"]::before {
            filter: hue-rotate(150deg) brightness(1.0) !important;
        }
        .st-key-workspace_tab_box_design div[data-testid="stButton"] button[data-testid="stBaseButton-primary"],
        .st-key-workspace_tab_box_design div[data-testid="stButton"] button[kind="primary"] {
            background-color: #000000 !important;
            border: 2px solid #10b981 !important;
            box-shadow: 0 0 0 1px rgba(16,185,129,.22), 0 0 18px rgba(16,185,129,.25) !important;
        }
        .st-key-workspace_tab_box_design div[data-testid="stButton"] button[data-testid="stBaseButton-primary"]::before,
        .st-key-workspace_tab_box_design div[data-testid="stButton"] button[kind="primary"]::before {
            filter: hue-rotate(290deg) saturate(.88) brightness(1.0) !important;
        }
        [class*="st-key-workspace_tab_"] div[data-testid="stButton"] button:focus-visible {
            outline: 3px solid rgba(255,255,255,.82);
            outline-offset: 2px;
        }
        .st-key-workspace_compat_control {
            display: none !important;
        }
        @media (max-width: 768px) {
            div[data-testid="stHorizontalBlock"]:has(.st-key-workspace_tab_bass_match) {
                flex-direction: column;
            }
            div[data-testid="stHorizontalBlock"]:has(.st-key-workspace_tab_bass_match) > div[data-testid="stColumn"] {
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
    for workspace, image_path in _constants._WORKSPACE_TAB_IMAGES.items():
        if not image_path.exists():
            continue
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        slug = _constants._WORKSPACE_TAB_SLUGS[workspace]
        rules.append(
            f'.st-key-workspace_tab_{slug} button::before '
            f'{{ background-image: url("data:image/png;base64,{encoded}"); }}'
        )
    rules.append("</style>")
    return "".join(rules)
