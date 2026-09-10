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
            display: none !important;
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
