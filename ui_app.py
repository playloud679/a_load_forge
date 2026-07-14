"""
Load Forge — acoustic-load simulator.

Single-page Streamlit dashboard for DCCAV, bass-reflex, acoustic-suspension and
infinite-baffle loads, with response plots and derived data in the workspace.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import importlib
import io
import json
import logging
import sys
import zlib
from functools import cache
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

logger = logging.getLogger("load_forge.ui")

sys.path.insert(0, str(Path(__file__).parent / "src"))
import dccav as _dccav
import engine as _engine
import presets as _presets
import pricing as _pricing

# Reload dependencies before the facade so it rebinds to the fresh modules.
for _module in (_engine, _pricing, _presets, _dccav):
    importlib.reload(_module)


try:
    _VERSION = (Path(__file__).parent / "VERSION").read_text().strip()
except OSError:
    _VERSION = "dev"
_BRAND_IMAGE = Path(__file__).parent / "assets" / "load_forge_header.png"


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
    .stMetric { border: 1px solid rgba(127,127,127,.22); padding: .75rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


_PARAM_PREFIXES = (
    "driver_", "box_", "reflex_", "sealed_", "loss_", "sim_", "opt_", "load_type"
)
_RESPONSE_TRACE_OPTIONS = ("Total", "Cone", "Lower port")
_PORT_TRACE_OPTIONS = ("Upper port", "Lower port")
_DEFAULT_REFLEX_Q_ABS = 15.0
_DEFAULT_REFLEX_Q_LEAK = 1000.0
_DEFAULT_REFLEX_Q_PORT = 15.0
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
    "Mini <= 2 in",
    "Small 2-6 in",
    "8-10 in",
    "12 in",
    "15 in+",
)
_PRESET_SOURCE_FILTERS = ("All", "Built-in", "Loudspeaker Database")
_PRESET_CLASS_FILTERS = ("All", *_dccav.DRIVER_CLASSES)
_WORKSPACES = ("Find a driver", "Design a box")
_BOX_STRATEGIES = ("Suggested", "Optimized", "Manual")
_FINDER_RANK_F3 = "Deepest bass (F3)"
_FINDER_RANK_VALUE = "Best value (F3 × price)"
_FINDER_RANK_MODES = (_FINDER_RANK_F3, _FINDER_RANK_VALUE)
_FINDER_DEFAULTS_VERSION = 3
_FINDER_DEFAULTS = {
    "finder_rank_mode": _FINDER_RANK_F3,
    "finder_volume_l": 40.0,
    "finder_objective": "Balanced",
    "finder_voltage": 2.83,
    "finder_use_optimizer": False,
    "finder_target_f3_hz": 0.0,
    "finder_max_ripple_db": 3.0,
    "finder_excursion_ratio": 1.0,
    "finder_max_gd_ms": 30.0,
    "finder_f_min": 10.0,
    "finder_f_max": 300.0,
    "finder_candidate_limit": 500,
    "finder_result_count": 20,
    "finder_points": 240,
}


_NUDGE_KEY_SUFFIXES = ("_minus_3", "_plus_3")


def _is_param_key(key: str) -> bool:
    if not any(key.startswith(prefix) for prefix in _PARAM_PREFIXES):
        return False
    # Nudge-button keys share the box_/reflex_/sealed_ prefixes but are
    # widget-event state: they cannot be assigned back via session_state.
    return not key.endswith(_NUDGE_KEY_SUFFIXES)


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
    applied = 0
    for key, value in data.items():
        if _is_param_key(key):
            if key == "load_type" and value in ("Suspension pneumatic", "Acoustic suspension"):
                value = "Sealed"
            st.session_state[key] = value
            applied += 1
    # v0.2 presets used two overlapping controls for the same decision.
    # Preserve those files while exposing one clear box strategy in the UI.
    if "box_strategy" not in data:
        if st.session_state.get("sim_auto_align", True):
            st.session_state["box_strategy"] = "Suggested"
        elif st.session_state.get("opt_align_mode") == "Optimized (goals)":
            st.session_state["box_strategy"] = "Optimized"
        else:
            st.session_state["box_strategy"] = "Manual"
    else:
        strategy = str(st.session_state.get("box_strategy", "Suggested"))
        st.session_state["sim_auto_align"] = strategy == "Suggested"
        st.session_state["opt_align_mode"] = (
            "Optimized (goals)" if strategy == "Optimized" else "Empirical (article)"
        )
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


def _chart_signature() -> str:
    prefixes = (
        "driver_", "box_", "reflex_", "sealed_", "loss_", "sim_", "plot_", "cursor_",
        "load_type", "pinned_",
    )
    data = {}
    for key, value in st.session_state.items():
        if not any(key.startswith(prefix) for prefix in prefixes):
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
        xmax_mm=float(st.session_state.get("driver_xmax_mm", 0.0)),
        pe_w=float(st.session_state.get("driver_pe_w", 0.0)),
        mms_g=_optional_positive("driver_mms_g"),
        cms_mm_per_n=_optional_positive("driver_cms_mm_n"),
        bl_tm=_optional_positive("driver_bl_tm"),
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


def _sealed_box_from_state() -> _dccav.SealedBox:
    return _dccav.SealedBox(
        vb_l=float(st.session_state["sealed_vb_l"]),
        q_abs=float(st.session_state["sealed_q_abs"]),
        q_leak=float(st.session_state["sealed_q_leak"]),
    )


def _optional_positive(key: str) -> float | None:
    value = float(st.session_state.get(key, 0.0) or 0.0)
    return value if value > 0 else None


def _default(key: str, value):
    st.session_state.setdefault(key, value)


def _reset_finder_defaults() -> None:
    """Restore a practical, quick first-pass driver search."""
    for key, value in _FINDER_DEFAULTS.items():
        st.session_state[key] = value
    st.session_state["_finder_defaults_version"] = _FINDER_DEFAULTS_VERSION
    st.session_state.pop("batch_results", None)
    st.session_state.pop("batch_result_context", None)


def _ensure_finder_defaults() -> None:
    """Migrate stale Finder widgets without pre-seeding implicit UI minima."""
    if st.session_state.get("_finder_defaults_version") != _FINDER_DEFAULTS_VERSION:
        for key in _FINDER_DEFAULTS:
            st.session_state.pop(key, None)
        st.session_state["_finder_defaults_version"] = _FINDER_DEFAULTS_VERSION
        st.session_state.pop("batch_results", None)
        st.session_state.pop("batch_result_context", None)
    else:
        # Keep conditionally rendered Finder values alive while Design is open.
        for key in _FINDER_DEFAULTS:
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


def _finder_checkbox(label: str, key: str, **kwargs):
    """Render the intended initial boolean without overriding later edits."""
    if key not in st.session_state:
        kwargs["value"] = bool(_FINDER_DEFAULTS[key])
    return st.checkbox(label, key=key, **kwargs)


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


_OPT_OBJECTIVE_LABELS = {
    "Max extension": "extension",
    "Balanced": "balanced",
    "Flattest": "flat",
}


def _optimizer_goals_from_state() -> _dccav.OptimizationGoals:
    return _dccav.OptimizationGoals(
        objective=_OPT_OBJECTIVE_LABELS[st.session_state.get("opt_objective", "Balanced")],
        max_total_volume_l=float(st.session_state.get("opt_max_volume_l", 0.0)) or None,
        target_f3_hz=float(st.session_state.get("opt_target_f3_hz", 0.0)) or None,
        max_ripple_db=float(st.session_state.get("opt_max_ripple_db", 3.0)),
        max_excursion_ratio=float(st.session_state.get("opt_excursion_ratio", 1.0)),
        max_group_delay_ms=float(st.session_state.get("opt_max_gd_ms", 0.0)) or None,
    )


def _alignment_uses_optimizer() -> bool:
    return (
        st.session_state.get("load_type", "DCCAV") != "Infinite baffle"
        and st.session_state.get("opt_align_mode", "Empirical (article)") == "Optimized (goals)"
    )


def _apply_optimized_box(box: _dccav.DccavBox | _dccav.ReflexBox | _dccav.SealedBox):
    if isinstance(box, _dccav.ReflexBox):
        st.session_state["reflex_vb_l"] = float(box.vb_l)
        st.session_state["reflex_fb_hz"] = float(box.fb_hz)
    elif isinstance(box, _dccav.SealedBox):
        st.session_state["sealed_vb_l"] = float(box.vb_l)
    else:
        st.session_state["box_vh_l"] = float(box.vh_l)
        st.session_state["box_fh_hz"] = float(box.fh_hz)
        st.session_state["box_vl_l"] = float(box.vl_l)
        st.session_state["box_fl_hz"] = float(box.fl_hz)


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
    box: _dccav.DccavBox | _dccav.ReflexBox | _dccav.SealedBox,
) -> tuple:
    if isinstance(box, _dccav.ReflexBox):
        return ("reflex", box.vb_l, box.fb_hz, box.q_abs, box.q_leak, box.q_port)
    if isinstance(box, _dccav.SealedBox):
        return ("sealed", box.vb_l, box.q_abs, box.q_leak)
    return (
        "dccav", box.vh_l, box.fh_hz, box.vl_l, box.fl_hz,
        box.q_abs_h, box.q_abs_l, box.q_leak_h, box.q_leak_l,
        box.q_port_h, box.q_port_l,
    )


def _optimizer_result_context(
    driver: _dccav.DriverTS,
    load_type: str,
    box: _dccav.DccavBox | _dccav.ReflexBox | _dccav.SealedBox,
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
    st.session_state["opt_last_summary"] = _optimized_summary(optimized)
    st.session_state["_opt_last_context"] = _optimizer_result_context(
        driver, load_type, optimized.box,
    )
    return optimized


def _apply_suggested_box_for(driver: _dccav.DriverTS):
    """Apply the alignment the current mode suggests (empirical or optimized)."""
    if _alignment_uses_optimizer():
        _apply_optimized_box(_run_box_optimizer(driver).box)
        return
    load_type = st.session_state.get("load_type", "DCCAV")
    if load_type == "Bass reflex":
        _apply_reflex_alignment(_dccav.suggest_reflex_alignment(driver))
    elif load_type == "Sealed":
        _apply_sealed_alignment(_dccav.suggest_sealed_alignment(driver))
    elif load_type == "Infinite baffle":
        return
    else:
        _apply_alignment(_dccav.suggest_alignment(driver))


def _apply_empirical_box_for(driver: _dccav.DriverTS) -> None:
    """Apply the lightweight starter regardless of the selected strategy."""
    load_type = st.session_state.get("load_type", "DCCAV")
    if load_type == "Bass reflex":
        _apply_reflex_alignment(_dccav.suggest_reflex_alignment(driver))
    elif load_type == "Sealed":
        _apply_sealed_alignment(_dccav.suggest_sealed_alignment(driver))
    elif load_type == "DCCAV":
        _apply_alignment(_dccav.suggest_alignment(driver))


def _on_box_strategy_change() -> None:
    strategy = str(st.session_state.get("box_strategy", "Suggested"))
    st.session_state["sim_auto_align"] = strategy == "Suggested"
    st.session_state["opt_align_mode"] = (
        "Optimized (goals)" if strategy == "Optimized" else "Empirical (article)"
    )
    if strategy == "Suggested":
        try:
            driver = _driver_from_state()
            _apply_empirical_box_for(driver)
            _mark_auto_alignment_synced(driver)
        except Exception:
            logger.exception("Could not apply the suggested box strategy")


def _use_manual_box_strategy() -> None:
    st.session_state["box_strategy"] = "Manual"
    st.session_state["sim_auto_align"] = False
    st.session_state["opt_align_mode"] = "Empirical (article)"


def _reset_reflex_losses():
    st.session_state["reflex_q_abs"] = _DEFAULT_REFLEX_Q_ABS
    st.session_state["reflex_q_leak"] = _DEFAULT_REFLEX_Q_LEAK
    st.session_state["reflex_q_port"] = _DEFAULT_REFLEX_Q_PORT
    st.session_state["reflex_custom_losses"] = False


def _nudge_state(key: str, factor: float, min_value: float, max_value: float):
    # Clamp to the widget bounds: a value outside [min, max] makes Streamlit
    # drop the widget state and silently reset the input to its minimum.
    value = float(st.session_state.get(key, 0.0) or 0.0)
    st.session_state[key] = float(np.clip(value * factor, min_value, max_value))


def _box_number_with_nudge(
    label: str,
    key: str,
    *,
    min_value: float,
    max_value: float,
    step: float,
    disabled: bool = False,
):
    n1, n2, n3 = st.columns([5, 1, 1])
    with n1:
        st.number_input(
            label, min_value=min_value, max_value=max_value, step=step, key=key,
            disabled=disabled,
        )
    with n2:
        st.button(
            "-3%", key=f"{key}_minus_3", on_click=_nudge_state,
            args=(key, 0.97, min_value, max_value),
            use_container_width=True, disabled=disabled,
        )
    with n3:
        st.button(
            "+3%", key=f"{key}_plus_3", on_click=_nudge_state,
            args=(key, 1.03, min_value, max_value),
            use_container_width=True, disabled=disabled,
        )


def _alignment_warning(ts: _dccav.DriverTS, alignment: _dccav.DccavAlignment) -> str | None:
    v_total = alignment.vh_l + alignment.vl_l
    if ts.sd_cm2 >= 500.0 and v_total < 25.0:
        return (
            f"Very small 12 in alignment: Vh+Vl = {v_total:.1f} L. "
            "This is only the empirical small-signal result from Qts^2*Vas; "
            "it ignores port displacement, air velocity, compression and max-SPL limits."
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
        return _dccav.driver_preset_info(name).source
    except ValueError:
        return "Built-in"


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
    for name in names:
        price = _driver_preset_price(name)
        if (
            price is not None
            and np.isfinite(float(price))
            and (currency is None or _driver_preset_currency(name) == currency)
        ):
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
    if size_in <= 2.0:
        return "Mini <= 2 in"
    if size_in <= 6.5:
        return "Small 2-6 in"
    if size_in <= 10.5:
        return "8-10 in"
    if size_in <= 13.5:
        return "12 in"
    return "15 in+"


def _driver_preset_size(name: str) -> str:
    try:
        info = _dccav.driver_preset_info(name)
        if info.size_in is not None:
            return _size_bucket(info.size_in)
    except ValueError:
        pass
    lower = name.lower()
    if lower.startswith("turbosound ts-15"):
        return "15 in+"
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
    if piston_inches <= 2.0:
        return "Mini <= 2 in"
    if piston_inches <= 6.5:
        return "Small 2-6 in"
    if piston_inches <= 10.5:
        return "8-10 in"
    if piston_inches <= 13.5:
        return "12 in"
    return "15 in+"


def _available_preset_families(names: list[str]) -> list[str]:
    present = {_driver_preset_family(name) for name in names}
    ordered = [family for family in _PRESET_FAMILY_ORDER if family == "All" or family in present]
    extras = sorted(present.difference(ordered), key=str.casefold)
    return [*ordered, *extras]


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
        price = _driver_preset_price(name)
        if (
            max_price is not None
            and max_price_currency
            and _driver_preset_currency(name) != max_price_currency
        ):
            continue
        if max_price is not None and price is not None and float(price) > float(max_price):
            continue
        if max_price is not None and price is None:
            continue
        filtered.append(name)
    if selected and selected != "Custom" and selected in names and selected not in filtered:
        filtered.insert(0, selected)
    return filtered


@cache
def _driver_preset_class(name: str) -> str:
    try:
        return _dccav.classify_driver_bandwidth(_dccav.get_driver_preset(name)).driver_class
    except Exception:
        return "Woofer"


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
    st.session_state["driver_xmax_mm"] = float(driver.xmax_mm)
    st.session_state["driver_pe_w"] = float(driver.pe_w)
    st.session_state["driver_mms_g"] = float(driver.mms_g or 0.0)
    st.session_state["driver_cms_mm_n"] = float(driver.cms_mm_per_n or 0.0)
    st.session_state["driver_bl_tm"] = float(driver.bl_tm or 0.0)


def _auto_align_current_driver():
    if not st.session_state.get("sim_auto_align", True):
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
    )


def _mark_auto_alignment_synced(driver: _dccav.DriverTS | None = None):
    try:
        st.session_state["_auto_align_signature"] = _auto_alignment_signature(driver)
    except Exception:
        pass


def _sync_auto_alignment_if_needed():
    if not st.session_state.get("sim_auto_align", True):
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
        if st.session_state.get("sim_auto_align", True):
            _apply_suggested_box_for(composite)
            _mark_auto_alignment_synced(composite)
    except Exception:
        logger.exception("Could not apply driver preset")


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


def _line_chart(
    data: pd.DataFrame,
    y_title: str,
    *,
    height: int,
    legend: bool = True,
    y_domain: list[float] | None = None,
) -> alt.Chart:
    series_names = list(dict.fromkeys(data["series"].tolist()))
    color_scale = alt.Scale(
        domain=series_names,
        range=[_TRACE_COLORS.get(name, "#7cc7ff") for name in series_names],
    )
    color = alt.Color(
        "series:N",
        title=None,
        legend=None if not legend else alt.Legend(title=None),
        scale=color_scale,
    )
    return alt.Chart(data).mark_line(point=False, clip=True, strokeWidth=2.2).encode(
        x=alt.X(
            "frequency_hz:Q",
            title="Frequency (Hz)",
            scale=alt.Scale(type="log", nice=False),
            axis=alt.Axis(format="~g"),
        ),
        y=alt.Y(
            "value:Q",
            title=y_title,
            scale=alt.Scale(domain=y_domain, nice=False) if y_domain else alt.Undefined,
        ),
        color=color,
        tooltip=[
            alt.Tooltip("frequency_hz:Q", title="Hz", format=".2f"),
            alt.Tooltip("series:N", title="Trace"),
            alt.Tooltip("value:Q", title=y_title, format=".3f"),
        ],
    ).properties(height=height)


def _response_series(result: _dccav.SimulationResult) -> dict[str, np.ndarray]:
    series = {}
    load_type = st.session_state.get("load_type", "DCCAV")
    if st.session_state.get("plot_response_total", True):
        series["Total"] = result.spl_total_db
    if st.session_state.get("plot_response_driver", True):
        series["Cone"] = result.spl_driver_db
    if st.session_state.get("plot_response_lower_port", True) and load_type in {"DCCAV", "Bass reflex"}:
        label = "Vent" if load_type == "Bass reflex" else "Lower port"
        series[label] = result.spl_port_db
    if st.session_state.get("plot_response_mol", False):
        series["MOL"] = result.mol_db
    return series


def _response_y_domain(result: _dccav.SimulationResult, series: dict[str, np.ndarray]) -> list[float] | None:
    total = np.asarray(result.spl_total_db, dtype=float)
    finite = total[np.isfinite(total)]
    if not finite.size:
        return None
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
    if load_type not in {"DCCAV", "Bass reflex"}:
        return series
    if st.session_state.get("plot_port_upper", True) and load_type == "DCCAV":
        series["Upper port"] = result.port_h_velocity
    if st.session_state.get("plot_port_lower", True):
        label = "Vent" if load_type == "Bass reflex" else "Lower port"
        series[label] = result.port_l_velocity
    return series


def _cursor_rows(result: _dccav.SimulationResult, thresholds: dict[int, float]) -> list[dict]:
    rows = []
    if st.session_state.get("cursor_auto_f3", True) and np.isfinite(thresholds[3]):
        rows.append(_cursor_row(result, "F3", thresholds[3], "auto"))
    if st.session_state.get("cursor_auto_f6", True) and np.isfinite(thresholds[6]):
        rows.append(_cursor_row(result, "F6", thresholds[6], "auto"))
    if st.session_state.get("cursor_auto_f10", True) and np.isfinite(thresholds[10]):
        rows.append(_cursor_row(result, "F10", thresholds[10], "auto"))
    if st.session_state.get("cursor_manual_enabled", False):
        rows.append(_cursor_row(result, "M1", float(st.session_state["cursor_manual_1_hz"]), "manual"))
        rows.append(_cursor_row(result, "M2", float(st.session_state["cursor_manual_2_hz"]), "manual"))
    return rows


def _cursor_label_rows(rows: list[dict], y_domain: list[float] | None) -> list[dict]:
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
        label_row["label_y_db"] = top - span * (0.06 + lane * 0.055)
        out.append(label_row)
    return out


def _cursor_row(result: _dccav.SimulationResult, label: str, frequency_hz: float, mode: str) -> dict:
    f = float(np.clip(frequency_hz, result.frequency_hz[0], result.frequency_hz[-1]))
    spl_total_db = _interp(result.frequency_hz, result.spl_total_db, f)
    return {
        "label": label,
        "display_label": f"{label} {f:.1f} Hz {spl_total_db:.1f} dB",
        "mode": mode,
        "frequency_hz": f,
        "spl_total_db": spl_total_db,
        "impedance_ohm": _interp(result.frequency_hz, result.impedance_ohm, f),
        "excursion_mm": _interp(result.frequency_hz, result.excursion_mm, f),
    }


def _interp(x: np.ndarray, y: np.ndarray, value: float) -> float:
    return float(np.interp(float(value), np.asarray(x, dtype=float), np.asarray(y, dtype=float)))


def _cursor_layer(rows: list[dict], y_domain: list[float] | None = None) -> alt.LayerChart | None:
    if not rows:
        return None
    data = pd.DataFrame(_cursor_label_rows(rows, y_domain))
    color = alt.Color(
        "label:N",
        title="Cursor",
        scale=alt.Scale(
            domain=["F3", "F6", "F10", "M1", "M2"],
            range=["#ffd166", "#f77f00", "#d62828", "#06d6a0", "#48cae4"],
        ),
    )
    rules = alt.Chart(data).mark_rule(strokeWidth=1.5).encode(
        x="frequency_hz:Q",
        color=color,
        strokeDash=alt.StrokeDash("mode:N", title=None),
        tooltip=[
            alt.Tooltip("label:N", title="Cursor"),
            alt.Tooltip("display_label:N", title="Marker"),
            alt.Tooltip("frequency_hz:Q", title="Hz", format=".2f"),
            alt.Tooltip("spl_total_db:Q", title="Total dB", format=".2f"),
            alt.Tooltip("impedance_ohm:Q", title="Ω", format=".2f"),
            alt.Tooltip("excursion_mm:Q", title="mm", format=".3f"),
        ],
    )
    labels = alt.Chart(data).mark_text(
        align="left",
        baseline="top",
        fontSize=19,
        fontWeight="bold",
        stroke="#0b1018",
        strokeWidth=3,
        strokeOpacity=0.85,
    ).encode(
        x=alt.value(22),
        y=alt.Y("label_y_db:Q", axis=None),
        text="display_label:N",
        color=color,
    )
    labels_fill = alt.Chart(data).mark_text(
        align="left",
        baseline="top",
        fontSize=19,
        fontWeight="bold",
    ).encode(
        x=alt.value(22),
        y=alt.Y("label_y_db:Q", axis=None),
        text="display_label:N",
        color=color,
    )
    return rules + labels + labels_fill


def _click_marker_layer(result: _dccav.SimulationResult) -> alt.LayerChart:
    marker_data = pd.DataFrame({
        "frequency_hz": result.frequency_hz.astype(float),
        "spl_total_db": result.spl_total_db.astype(float),
    })
    marker_data = marker_data[np.isfinite(marker_data["frequency_hz"]) & np.isfinite(marker_data["spl_total_db"])]
    marker_data["display_label"] = marker_data.apply(
        lambda row: f"Click {row['frequency_hz']:.1f} Hz {row['spl_total_db']:.1f} dB",
        axis=1,
    )
    click_marker = alt.selection_point(
        name="click_marker",
        fields=["frequency_hz"],
        nearest=True,
        on="click",
        clear="dblclick",
        empty=False,
    )
    base = alt.Chart(marker_data).encode(
        x=alt.X("frequency_hz:Q", scale=alt.Scale(type="log", nice=False)),
        y=alt.Y("spl_total_db:Q"),
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


def _band_layer(band: _dccav.ToleranceBand, y_domain: list[float] | None) -> alt.Chart | None:
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
        x=alt.X("frequency_hz:Q", scale=alt.Scale(type="log", nice=False)),
        y=alt.Y("lower_db:Q", scale=y_scale, title=None),
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
) -> alt.Chart:
    series = series_override if series_override else _response_series(result)
    if not series:
        raise ValueError("No response traces selected")
    data = _series_frame(result, series)
    y_domain = _response_y_domain(result, series)
    if band is not None and y_domain is not None:
        finite_upper = np.asarray(band.upper_db, dtype=float)
        finite_upper = finite_upper[np.isfinite(finite_upper)]
        if finite_upper.size:
            y_domain[1] = max(y_domain[1], float(np.max(finite_upper)) + 2.0)
    chart = _line_chart(
        data,
        "LF pressure estimate (dB)",
        height=760,
        y_domain=y_domain,
    )
    if band is not None:
        band_area = _band_layer(band, y_domain)
        if band_area is not None:
            chart = band_area + chart
    chart = chart + _click_marker_layer(result)
    pinned = _pinned_layer()
    if pinned is not None:
        chart = chart + pinned
    cursors = _cursor_layer(cursor_rows, y_domain)
    if cursors is None:
        return chart
    return (chart + cursors).resolve_scale(color="independent", strokeDash="independent")


def _plot_excursion(result: _dccav.SimulationResult, xmax_mm: float) -> alt.Chart:
    data = _series_frame(result, {"Excursion": result.excursion_mm})
    chart = _line_chart(data, "Excursion (mm)", height=285, legend=False)
    if xmax_mm > 0:
        xmax_rule = alt.Chart(pd.DataFrame({"xmax_mm": [float(xmax_mm)]})).mark_rule(
            color="#9b2226",
            strokeDash=[6, 4],
        ).encode(y="xmax_mm:Q")
        chart = chart + xmax_rule
    return chart


def _plot_impedance(result: _dccav.SimulationResult) -> alt.Chart:
    data = _series_frame(result, {"Impedance": result.impedance_ohm})
    return _line_chart(data, "Impedance (Ω)", height=285, legend=False)


def _plot_mil(result: _dccav.SimulationResult) -> alt.Chart:
    data = _series_frame(result, {"MIL": result.mil_w})
    return _line_chart(data, "Max input power (W)", height=240, legend=False)


def _pin_label(load_type: str, box) -> str:
    preset = str(st.session_state.get("driver_preset_name", "Custom"))
    config = str(st.session_state.get("driver_config", "Single driver"))
    if config != "Single driver":
        preset = f"{preset} ({config})"
    if load_type == "Bass reflex":
        box_txt = f"Vb {box.vb_l:.1f} L · Fb {box.fb_hz:.1f} Hz"
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


def _pinned_layer() -> alt.Chart | None:
    pinned = st.session_state.get("pinned_response")
    if not pinned:
        return None
    data = pd.DataFrame({
        "frequency_hz": pinned["frequency_hz"],
        "value": pinned["spl_total_db"],
    })
    data = data[np.isfinite(data["frequency_hz"]) & np.isfinite(data["value"])]
    if data.empty:
        return None
    data["label"] = pinned["label"]
    return alt.Chart(data).mark_line(
        strokeDash=[6, 4], strokeWidth=1.8, color="#9aa0a6", clip=True,
    ).encode(
        x=alt.X("frequency_hz:Q", scale=alt.Scale(type="log", nice=False)),
        y="value:Q",
        tooltip=[
            alt.Tooltip("frequency_hz:Q", title="Hz", format=".2f"),
            alt.Tooltip("label:N", title="Pinned"),
            alt.Tooltip("value:Q", title="Pinned dB", format=".3f"),
        ],
    )


def _topology_comparison_series(
    ts: _dccav.DriverTS,
    load_type: str,
    box,
    freq: np.ndarray,
    voltage_v: float,
    series_r_ohm: float,
) -> tuple[float, dict[str, np.ndarray]]:
    """Simulate the four loads at a shared total volume for the overlay chart.

    The active load keeps its exact box; the other topologies use their
    standard starters constrained to the same total volume.  Infinite baffle
    has no volume, so when it is active the comparison volume falls back to
    the driver's Vas.
    """
    if load_type in {"Bass reflex", "Sealed"}:
        vtot = float(box.vb_l)
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
    return chart


def _plot_ports(result: _dccav.SimulationResult) -> alt.Chart:
    series = _port_series(result)
    if not series:
        raise ValueError("No port traces selected")
    data = _series_frame(result, series)
    return _line_chart(data, "Volume velocity (m³/s)", height=320)


def _rank_value(value: float) -> float:
    return float(value) if np.isfinite(float(value)) else float("inf")


def _batch_dccav_box(ts: _dccav.DriverTS, total_volume_l: float) -> _dccav.DccavBox:
    alignment = _dccav.suggest_alignment(ts)
    suggested_total = max(float(alignment.vh_l + alignment.vl_l), 1e-9)
    vh_ratio = float(np.clip(alignment.vh_l / suggested_total, 0.05, 0.95))
    vh_l = max(float(total_volume_l) * vh_ratio, 0.05)
    vl_l = max(float(total_volume_l) - vh_l, 0.05)
    if vh_l + vl_l > float(total_volume_l) and float(total_volume_l) >= 0.1:
        scale = float(total_volume_l) / (vh_l + vl_l)
        vh_l *= scale
        vl_l *= scale
    return _dccav.DccavBox(vh_l=vh_l, fh_hz=alignment.fh_hz, vl_l=vl_l, fl_hz=alignment.fl_hz)


_BATCH_SPARK_POINTS = 48
_BATCH_SPARK_FLOOR_DB = -30.0


def _batch_sparkline(spl_total_db: np.ndarray) -> list[float]:
    """Downsample the total response to a peak-relative sparkline in dB."""
    spl = np.asarray(spl_total_db, dtype=float)
    finite = spl[np.isfinite(spl)]
    if not finite.size:
        return []
    rel = spl - float(np.max(finite))
    idx = np.linspace(0, len(rel) - 1, min(_BATCH_SPARK_POINTS, len(rel))).astype(int)
    return [
        float(np.clip(value, _BATCH_SPARK_FLOOR_DB, 0.0))
        if np.isfinite(value) else _BATCH_SPARK_FLOOR_DB
        for value in rel[idx]
    ]


@st.cache_data(show_spinner=False)
def _batch_rank_presets(
    preset_names: tuple[str, ...],
    load_type: str,
    target_volume_l: float,
    voltage_v: float,
    f_min_hz: float,
    f_max_hz: float,
    points: int,
    candidate_limit: int,
    goals: _dccav.OptimizationGoals | None = None,
) -> list[dict]:
    if load_type in ("Suspension pneumatic", "Acoustic suspension"):
        load_type = "Sealed"
    freq = np.geomspace(float(f_min_hz), float(f_max_hz), int(points))
    batch_goals = None
    if goals is not None and load_type != "Infinite baffle":
        # Driver ranking compares candidates at the exact requested enclosure volume.
        batch_goals = _dccav.OptimizationGoals(
            objective=goals.objective,
            max_total_volume_l=float(target_volume_l),
            target_f3_hz=goals.target_f3_hz,
            max_ripple_db=goals.max_ripple_db,
            max_excursion_ratio=goals.max_excursion_ratio,
            max_group_delay_ms=goals.max_group_delay_ms,
        )
    rows: list[dict] = []
    for name in preset_names[:int(candidate_limit)]:
        try:
            ts = _dccav.get_driver_preset(name)
            info = _dccav.driver_preset_info(name)
            driver_class = _dccav.classify_driver_bandwidth(ts).driver_class
            ripple_db = np.nan
            if batch_goals is not None:
                optimized = _dccav.optimize_alignment(
                    ts,
                    batch_goals,
                    load_type=load_type,
                    voltage_v=float(voltage_v),
                    max_evaluations=140,
                    fixed_total_volume_l=float(target_volume_l),
                )
                box = optimized.box
                ripple_db = float(optimized.ripple_db)
            elif load_type == "Bass reflex":
                alignment = _dccav.suggest_reflex_alignment(ts)
                box = _dccav.ReflexBox(vb_l=float(target_volume_l), fb_hz=alignment.fb_hz)
            elif load_type == "Sealed":
                box = _dccav.SealedBox(vb_l=float(target_volume_l))
            elif load_type == "Infinite baffle":
                box = None
            else:
                box = _batch_dccav_box(ts, float(target_volume_l))
            if load_type == "Bass reflex":
                result = _dccav.simulate_reflex(ts, box, freq, float(voltage_v))
                box_values = {
                    "Vb L": box.vb_l,
                    "Fb Hz": box.fb_hz,
                    "Vh L": np.nan,
                    "fh Hz": np.nan,
                    "Vl L": np.nan,
                    "fl Hz": np.nan,
                    "Fc Hz": np.nan,
                    "Qtc": np.nan,
                }
            elif load_type == "Sealed":
                result = _dccav.simulate_sealed(ts, box, freq, float(voltage_v))
                fc_hz, qtc = _dccav.sealed_system_metrics(ts, box)
                box_values = {
                    "Vb L": box.vb_l,
                    "Fb Hz": np.nan,
                    "Vh L": np.nan,
                    "fh Hz": np.nan,
                    "Vl L": np.nan,
                    "fl Hz": np.nan,
                    "Fc Hz": fc_hz,
                    "Qtc": qtc,
                }
            elif load_type == "Infinite baffle":
                result = _dccav.simulate_infinite_baffle(ts, freq, float(voltage_v))
                box_values = {
                    "Vb L": np.nan,
                    "Fb Hz": np.nan,
                    "Vh L": np.nan,
                    "fh Hz": np.nan,
                    "Vl L": np.nan,
                    "fl Hz": np.nan,
                    "Fc Hz": ts.fs_hz,
                    "Qtc": ts.qts,
                }
            else:
                result = _dccav.simulate(ts, box, freq, float(voltage_v))
                box_values = {
                    "Vb L": np.nan,
                    "Fb Hz": np.nan,
                    "Vh L": box.vh_l,
                    "fh Hz": box.fh_hz,
                    "Vl L": box.vl_l,
                    "fl Hz": box.fl_hz,
                    "Fc Hz": np.nan,
                    "Qtc": np.nan,
                }
            thresholds = _dccav.response_threshold_frequencies(result)
            rows.append({
                "Driver": name,
                "Source": info.source,
                "Brand": info.brand or "Other",
                "Class": driver_class,
                "Size in": info.size_in if info.size_in is not None else np.nan,
                "Price": info.price if info.price is not None else np.nan,
                "Currency": info.currency,
                "Buy": info.url or "",
                "F3 Hz": thresholds[3],
                "F6 Hz": thresholds[6],
                "F10 Hz": thresholds[10],
                "Peak dB": float(np.nanmax(result.spl_total_db)),
                "Ripple dB": ripple_db,
                "Max excursion mm": float(np.nanmax(result.excursion_mm)),
                "Min ohm": float(np.nanmin(result.impedance_ohm)),
                "Response": _batch_sparkline(result.spl_total_db),
                **box_values,
            })
        except Exception:
            continue
    rows.sort(key=lambda row: (
        _rank_value(row["F3 Hz"]),
        _rank_value(row["F6 Hz"]),
        _rank_value(row["F10 Hz"]),
        -float(row["Peak dB"]) if np.isfinite(float(row["Peak dB"])) else 0.0,
    ))
    return rows


def _apply_batch_result(row: dict, load_type: str) -> None:
    if load_type in ("Suspension pneumatic", "Acoustic suspension"):
        load_type = "Sealed"
    name = str(row["Driver"])
    driver = _dccav.get_driver_preset(name)
    st.session_state["load_type"] = load_type
    st.session_state["driver_preset_name"] = name
    # Candidates are ranked as single drivers; the applied box matches that.
    st.session_state["driver_config"] = "Single driver"
    _apply_driver_preset(driver)
    _use_manual_box_strategy()
    st.session_state["workspace_mode"] = "Design a box"
    if load_type == "Bass reflex":
        st.session_state["reflex_vb_l"] = float(row["Vb L"])
        st.session_state["reflex_fb_hz"] = float(row["Fb Hz"])
    elif load_type == "Sealed":
        st.session_state["sealed_vb_l"] = float(row["Vb L"])
    elif load_type == "DCCAV":
        st.session_state["box_vh_l"] = float(row["Vh L"])
        st.session_state["box_fh_hz"] = float(row["fh Hz"])
        st.session_state["box_vl_l"] = float(row["Vl L"])
        st.session_state["box_fl_hz"] = float(row["fl Hz"])
    _mark_auto_alignment_synced(driver)


def _apply_pending_batch_result() -> None:
    pending = st.session_state.pop("batch_pending_result", None)
    if not pending:
        return
    _apply_batch_result(pending["row"], str(pending["load_type"]))
    st.toast(f"Applied {pending['row']['Driver']} to the design")


def _apply_pending_atlas_point() -> None:
    pending = st.session_state.pop("atlas_pending_point", None)
    if not pending:
        return
    load_type = str(pending["load_type"])
    try:
        driver = _driver_from_state()
        if load_type == "Bass reflex":
            template = _reflex_box_from_state()
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
    )


def _render_find_driver_workspace(filtered_preset_names: list[str]) -> None:
    """Render the goal-first catalog workflow, separate from box editing."""
    load_type = str(st.session_state.get("load_type", "DCCAV"))
    is_infinite_baffle = load_type == "Infinite baffle"

    st.subheader("Find a driver")
    st.caption(
        "Set the available enclosure and rank only the catalog candidates selected by "
        "the sidebar filters. Selecting a row previews it; the current design changes "
        "only after Apply candidate to design."
    )

    with st.container(border=True):
        header_col, reset_col = st.columns([4, 1])
        with header_col:
            st.markdown("##### Search constraints")
        with reset_col:
            st.button(
                "Reset defaults",
                key="finder_reset_defaults",
                on_click=_reset_finder_defaults,
                use_container_width=True,
                help="40 L, 2.83 V, deepest available F3, 3 dB ripple, 1× Xmax, 10-300 Hz.",
            )
        c1, c2, c3 = st.columns(3)
        with c1:
            _finder_number_input(
                "Comparison volume (L)",
                min_value=0.1,
                max_value=2000.0,
                step=1.0,
                key="finder_volume_l",
                disabled=is_infinite_baffle,
                help="Exact Vh+Vl for DCCAV or Vb for reflex/sealed candidates.",
            )
        with c2:
            _finder_selectbox(
                "Ranking goal", list(_OPT_OBJECTIVE_LABELS), key="finder_objective",
                help="Balanced trades bass extension against response smoothness and box practicality.",
            )
        with c3:
            _finder_number_input(
                "Comparison voltage (V)", min_value=0.01, max_value=200.0,
                step=0.01, key="finder_voltage",
                help="All candidates are compared at the same input voltage; 2.83 V is the standard reference.",
            )

        use_optimizer = _finder_checkbox(
            "Optimize each candidate at the comparison volume",
            key="finder_use_optimizer",
            disabled=is_infinite_baffle,
            help="Slower. Start with the quick scan, then enable this to refine a filtered shortlist.",
        )
        goals_inactive = is_infinite_baffle or not bool(use_optimizer)
        with st.expander("Advanced ranking constraints"):
            st.caption(
                "F3, ripple, excursion and group-delay limits act only when each "
                "candidate is optimized; the evaluation range always applies."
            )
            a1, a2 = st.columns(2)
            with a1:
                _finder_number_input(
                    "Desired bass extension F3 (Hz, 0 = deepest)", min_value=0.0, max_value=500.0,
                    step=1.0, key="finder_target_f3_hz", disabled=goals_inactive,
                    help="Desired -3 dB cutoff. Lower values ask for deeper bass; enter 0 for no target.",
                )
                _finder_number_input(
                    "Allowed response ripple (dB)", min_value=0.0, max_value=12.0,
                    step=0.5, key="finder_max_ripple_db", disabled=goals_inactive,
                    help="Maximum peak-to-valley variation in the evaluated low-frequency passband.",
                )
                _finder_number_input(
                    "Maximum excursion (× driver Xmax)", min_value=0.0, max_value=3.0,
                    step=0.05, key="finder_excursion_ratio", disabled=goals_inactive,
                    help="1.0 means the simulated cone travel must stay within the driver's published Xmax; 0 disables it.",
                )
            with a2:
                _finder_number_input(
                    "Maximum group delay (ms)", min_value=0.0, max_value=100.0,
                    step=1.0, key="finder_max_gd_ms", disabled=goals_inactive,
                    help="Maximum allowed low-frequency group delay; 0 disables this constraint.",
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

        max_batch_candidates = max(len(filtered_preset_names), 1)
        if int(st.session_state.get(
            "finder_candidate_limit", _FINDER_DEFAULTS["finder_candidate_limit"]
        )) > max_batch_candidates:
            st.session_state["finder_candidate_limit"] = max_batch_candidates
        b1, b2, b3 = st.columns(3)
        with b1:
            _finder_number_input(
                "Drivers to evaluate", min_value=1, max_value=max_batch_candidates,
                step=50, key="finder_candidate_limit",
            )
        with b2:
            _finder_number_input(
                "Top results to show", min_value=1, max_value=200,
                step=5, key="finder_result_count",
            )
        with b3:
            _finder_number_input(
                "Simulation resolution (points)", min_value=80, max_value=1000,
                step=20, key="finder_points",
            )

    finder_volume_l = float(st.session_state.get("finder_volume_l", 0.0))
    scan_count = min(int(_finder_value("finder_candidate_limit")), len(filtered_preset_names))
    batch_blocked = (
        not filtered_preset_names
        or float(_finder_value("finder_f_max")) <= float(_finder_value("finder_f_min"))
        or (not is_infinite_baffle and finder_volume_l <= 0.0)
    )
    st.caption(
        f"{len(filtered_preset_names)} matching presets · {load_type}"
        + ("" if is_infinite_baffle else f" · {finder_volume_l:.1f} L")
    )
    if st.button(
        "Rank candidates", type="primary", use_container_width=True, disabled=batch_blocked,
    ):
        goals = (
            _finder_optimizer_goals_from_state()
            if st.session_state.get("finder_use_optimizer", False) and not is_infinite_baffle
            else None
        )
        spinner_text = (
            f"Optimizing {scan_count} candidates" if goals is not None
            else f"Scanning {scan_count} candidates"
        )
        with st.spinner(spinner_text):
            batch_rows = _batch_rank_presets(
                tuple(filtered_preset_names),
                load_type,
                finder_volume_l,
                float(_finder_value("finder_voltage")),
                float(_finder_value("finder_f_min")),
                float(_finder_value("finder_f_max")),
                int(_finder_value("finder_points")),
                scan_count,
                goals=goals,
            )
        st.session_state["batch_results"] = batch_rows
        st.session_state["batch_result_context"] = (
            load_type,
            finder_volume_l,
            scan_count,
            bool(goals),
            str(st.session_state.get("finder_objective", "Balanced")),
        )

    batch_rows = st.session_state.get("batch_results", [])
    context = st.session_state.get("batch_result_context", ())
    if len(context) < 2 or tuple(context[:2]) != (load_type, finder_volume_l):
        batch_rows = []
    if not batch_rows:
        if filtered_preset_names:
            st.info("Set the constraints, then rank candidates. Your current design is preserved.")
        else:
            st.warning("No presets match the current library filters.")
        return

    st.caption(f"{len(batch_rows)} usable candidates from {context[2]} scanned presets")
    full_df = pd.DataFrame(batch_rows)
    for name, default in (
        ("Price", np.nan), ("Currency", ""), ("Buy", ""),
        ("Ripple dB", np.nan), ("Response", None), ("Class", ""),
    ):
        if name not in full_df.columns:
            full_df[name] = default

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
        "Driver", "Brand", "Size in", "F3 Hz", "F6 Hz", "F10 Hz",
        "Peak dB", "Max excursion mm", "Min ohm",
    ]
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
    if load_type == "Bass reflex":
        columns += ["Vb L", "Fb Hz"]
    elif load_type == "Sealed":
        columns += ["Vb L", "Fc Hz", "Qtc"]
    elif load_type == "Infinite baffle":
        columns += ["Fc Hz", "Qtc"]
    else:
        columns += ["Vh L", "fh Hz", "Vl L", "fl Hz"]
    if batch_df["Buy"].fillna("").astype(bool).any():
        columns.append("Buy")

    table_state = st.dataframe(
        batch_df[columns],
        width="stretch",
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
            "Vb L": st.column_config.NumberColumn(format="%.2f"),
            "Fb Hz": st.column_config.NumberColumn(format="%.1f"),
            "Fc Hz": st.column_config.NumberColumn(format="%.1f"),
            "Qtc": st.column_config.NumberColumn(format="%.3f"),
            "Vh L": st.column_config.NumberColumn(format="%.2f"),
            "fh Hz": st.column_config.NumberColumn(format="%.1f"),
            "Vl L": st.column_config.NumberColumn(format="%.2f"),
            "fl Hz": st.column_config.NumberColumn(format="%.1f"),
            "Buy": st.column_config.LinkColumn(display_text="Buy"),
            "Response": st.column_config.LineChartColumn(
                "Response (rel dB)", y_min=_BATCH_SPARK_FLOOR_DB, y_max=0.0,
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
        return
    selected_index = int(selected_rows[0])
    if not 0 <= selected_index < len(batch_df):
        return
    selected_row = batch_df.iloc[selected_index].to_dict()
    with st.container(border=True):
        st.markdown(f"#### Candidate preview · {selected_row['Driver']}")
        p1, p2, p3, p4 = st.columns(4)
        p1.metric("F3", f"{float(selected_row['F3 Hz']):.1f} Hz")
        p2.metric("Peak LF SPL", f"{float(selected_row['Peak dB']):.1f} dB")
        p3.metric("Max excursion", f"{float(selected_row['Max excursion mm']):.2f} mm")
        p4.metric("Min impedance", f"{float(selected_row['Min ohm']):.2f} Ω")
        if load_type == "DCCAV":
            st.caption(
                f"Vh {float(selected_row['Vh L']):.2f} L / "
                f"{float(selected_row['fh Hz']):.1f} Hz · "
                f"Vl {float(selected_row['Vl L']):.2f} L / "
                f"{float(selected_row['fl Hz']):.1f} Hz"
            )
        elif load_type == "Bass reflex":
            st.caption(
                f"Vb {float(selected_row['Vb L']):.2f} L · "
                f"Fb {float(selected_row['Fb Hz']):.1f} Hz"
            )
        elif load_type == "Sealed":
            st.caption(
                f"Vb {float(selected_row['Vb L']):.2f} L · "
                f"Fc {float(selected_row['Fc Hz']):.1f} Hz · "
                f"Qtc {float(selected_row['Qtc']):.3f}"
            )
        if st.button("Apply candidate to design", type="primary", use_container_width=True):
            st.session_state["batch_pending_result"] = {
                "row": selected_row,
                "load_type": load_type,
            }
            st.rerun()


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
    has_ports = load_type in {"DCCAV", "Bass reflex"}
    compare_loads_on = bool(st.session_state.get("plot_compare_loads", False))
    r1, r2, r3, r4, r5 = st.columns(5)
    with r1:
        st.checkbox("Total", key="plot_response_total", disabled=compare_loads_on)
    with r2:
        st.checkbox("Cone", key="plot_response_driver", disabled=compare_loads_on)
    with r3:
        st.checkbox(
            "Lower port", key="plot_response_lower_port",
            disabled=not has_ports or compare_loads_on,
        )
    with r4:
        st.checkbox(
            "MOL", key="plot_response_mol", disabled=compare_loads_on,
            help="Maximum Output Level: the highest SPL the driver can reach within "
                 "Xmax and Pe at each frequency. Needs Xmax or Pe.",
        )
    with r5:
        st.checkbox(
            "MIL chart", key="plot_show_mil",
            help="Maximum Input Level: the input-power ceiling within Xmax and Pe, "
                 "drawn as a separate chart below the response.",
        )

    c0, c1, c2, c3 = st.columns([1.1, 1, 1, 1])
    with c0:
        st.toggle("Manual", key="cursor_manual_enabled")
    with c1:
        st.checkbox("F3", key="cursor_auto_f3")
    with c2:
        st.checkbox("F6", key="cursor_auto_f6")
    with c3:
        st.checkbox("F10", key="cursor_auto_f10")
    if st.session_state.get("cursor_manual_enabled", False):
        c4, c5 = st.columns(2)
        with c4:
            st.number_input(
                "M1 (Hz)", min_value=1.0, max_value=5000.0,
                step=1.0, key="cursor_manual_1_hz",
            )
        with c5:
            st.number_input(
                "M2 (Hz)", min_value=1.0, max_value=5000.0,
                step=1.0, key="cursor_manual_2_hz",
            )

    cursor_rows = _cursor_rows(result, thresholds)

    if load_type == "Bass reflex":
        st.caption(
            "Bass-reflex total response is the vector sum of the exposed cone "
            "front radiation and the vent. The model is low-frequency only; "
            "it does not include baffle step, breakup, room gain or crossover behaviour."
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
    pin_col, clear_col, compare_col, band_col, pin_info = st.columns([1, 1, 1, 1, 1.4])
    with compare_col:
        st.toggle("Compare loads", key="plot_compare_loads")
    with band_col:
        st.toggle(
            "Tolerance band", key="plot_tolerance_band", disabled=compare_loads_on,
            help="Monte Carlo spread of the driver T/S (Fs, Vas, Qts, Qms): "
                 "shaded 5-95th percentile band of the total response with "
                 "the current box kept fixed.",
        )
    with pin_col:
        if st.button("Pin response", use_container_width=True):
            st.session_state["pinned_response"] = {
                "label": _pin_label(load_type, box),
                "frequency_hz": [float(v) for v in result.frequency_hz],
                "spl_total_db": [float(v) for v in result.spl_total_db],
            }
            st.rerun()
    with clear_col:
        if st.button(
            "Clear pin",
            use_container_width=True,
            disabled=not st.session_state.get("pinned_response"),
        ):
            st.session_state["pinned_response"] = None
            st.rerun()
    pinned_state = st.session_state.get("pinned_response")
    if pinned_state:
        with pin_info:
            st.caption(f"Pinned (dashed grey): {pinned_state['label']}")

    compare_series = None
    if st.session_state.get("plot_compare_loads", False):
        comp_vtot, comp_series = _topology_comparison_series(
            current_ts, load_type, box, freq, sim_voltage, sim_series_r)
        if comp_series:
            compare_series = comp_series
            st.caption(
                f"Comparing the total response of the four loads at ~{comp_vtot:.1f} L. "
                f"The active load ({load_type}) uses its exact box; the others use their "
                "standard starter alignments at the same total volume. Infinite baffle "
                "ignores volume. Trace pens are suspended while comparing."
            )
        else:
            st.caption("No comparison load could be simulated; showing the normal traces.")

    band = None
    if st.session_state.get("plot_tolerance_band", False) and not compare_series:
        st.number_input(
            "T/S tolerance (%)", min_value=5.0, max_value=30.0, step=1.0,
            key="plot_tolerance_pct",
        )
        tolerance = float(st.session_state.get("plot_tolerance_pct", 15.0)) / 100.0
        try:
            band = _tolerance_band_cached(
                current_ts, load_type, box, freq, sim_voltage, sim_series_r, tolerance)
            st.caption(
                f"Shaded band: ±{tolerance * 100.0:.0f}% Monte Carlo on "
                f"Fs/Vas/Qts/Qms, {band.runs} runs, 5-95th percentile."
            )
        except Exception:
            logger.exception("Tolerance band computation failed")
            st.caption("Tolerance band unavailable for the current parameters.")

    if compare_series or _response_series(result):
        st.altair_chart(
            _plot_response(result, cursor_rows, compare_series, band),
            width="stretch",
            key=f"response_chart_{chart_sig}",
        )
        st.caption("Click the chart to place a point marker; double-click to clear it.")
    else:
        st.caption("Response pens off.")

    if st.session_state.get("plot_show_mil", False):
        if np.all(np.isnan(result.mil_w)):
            st.caption("MIL unavailable: set Xmax or Pe for this driver.")
        else:
            st.subheader("MIL")
            st.altair_chart(_plot_mil(result), width="stretch", key=f"mil_chart_{chart_sig}")

    if cursor_rows:
        cursor_table = pd.DataFrame(cursor_rows).rename(columns={
            "label": "Cursor",
            "display_label": "Marker",
            "mode": "Mode",
            "frequency_hz": "Hz",
            "spl_total_db": "Total dB",
            "impedance_ohm": "Ω",
            "excursion_mm": "Excursion mm",
        })
        st.dataframe(
            cursor_table[["Cursor", "Mode", "Hz", "Total dB", "Ω", "Excursion mm"]],
            width="stretch",
            hide_index=True,
        )


@st.fragment
def _render_ports_tab(
    result: _dccav.SimulationResult,
    port_geometry_rows: list[dict],
    load_type: str,
) -> None:
    chart_sig = _chart_signature()
    if load_type not in {"DCCAV", "Bass reflex"}:
        st.caption("The current load type has no ports.")
        return
    p1, p2 = st.columns(2)
    with p1:
        st.checkbox("Upper port", key="plot_port_upper", disabled=load_type != "DCCAV")
    with p2:
        st.checkbox("Lower port V", key="plot_port_lower")
    st.subheader("Port Volume Velocity")
    if _port_series(result):
        st.altair_chart(_plot_ports(result), width="stretch", key=f"ports_chart_{chart_sig}")
    else:
        st.caption("Port pens off.")

    if port_geometry_rows:
        st.subheader("Port Geometry")
        st.caption(
            f"Circular ducts at {float(st.session_state['sim_voltage']):.2f} V; "
            f"air-speed guideline {_dccav.PORT_VELOCITY_GUIDELINE_MS:.0f} m/s (5% of c)."
        )
        st.dataframe(
            pd.DataFrame(port_geometry_rows)[list(_PORT_GEOMETRY_COLUMNS)],
            width="stretch",
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
_default("driver_xmax_mm", 3.1)
_default("driver_pe_w", 60.0)
_default("driver_mms_g", 0.0)
_default("driver_cms_mm_n", 0.0)
_default("driver_bl_tm", 0.0)
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
_default("box_port_d_h_cm", 5.0)
_default("box_port_d_l_cm", 5.0)
_default("sealed_q_abs", 15.0)
_default("sealed_q_leak", 1000.0)
_default("load_type", "Sealed")
if st.session_state["load_type"] in ("Suspension pneumatic", "Acoustic suspension"):
    st.session_state["load_type"] = "Sealed"
_default("sim_f_min", 10.0)
_default("sim_f_max", 500.0)
_default("sim_points", 600)
_default("sim_voltage", 2.83)
_default("sim_series_r_ohm", 0.0)
_default("sim_auto_align", True)
_default("plot_response_traces", list(_RESPONSE_TRACE_OPTIONS))
_default("plot_port_traces", list(_PORT_TRACE_OPTIONS))
_default("plot_response_total", "Total" in st.session_state["plot_response_traces"])
_default(
    "plot_response_driver",
    "Cone" in st.session_state["plot_response_traces"]
    or "Driver" in st.session_state["plot_response_traces"],
)
_default("plot_response_lower_port", "Lower port" in st.session_state["plot_response_traces"])
_default("plot_response_mol", False)
_default("plot_show_mil", False)
_default("plot_compare_loads", False)
_default("plot_tolerance_band", False)
_default("plot_tolerance_pct", 15.0)
_default("atlas_enabled", False)
_default("atlas_metric", "F3 (Hz)")
_default("plot_port_upper", "Upper port" in st.session_state["plot_port_traces"])
_default("plot_port_lower", "Lower port" in st.session_state["plot_port_traces"])
_default("cursor_auto_f3", True)
_default("cursor_auto_f6", True)
_default("cursor_auto_f10", True)
_default("cursor_manual_enabled", False)
_default("cursor_manual_1_hz", 50.0)
_default("cursor_manual_2_hz", 100.0)
_default("opt_align_mode", "Empirical (article)")
_default("opt_objective", "Balanced")
_default("opt_max_volume_l", 0.0)
_default("opt_target_f3_hz", 0.0)
_default("opt_max_ripple_db", 3.0)
_default("opt_excursion_ratio", 1.0)
_default("opt_max_gd_ms", 0.0)
_default("workspace_mode", "Find a driver")
_default("ui_show_advanced", False)
_ensure_finder_defaults()
if "box_strategy" not in st.session_state:
    if st.session_state.get("sim_auto_align", True):
        st.session_state["box_strategy"] = "Suggested"
    elif st.session_state.get("opt_align_mode") == "Optimized (goals)":
        st.session_state["box_strategy"] = "Optimized"
    else:
        st.session_state["box_strategy"] = "Manual"
_apply_pending_batch_result()
_apply_pending_atlas_point()

_share_token = st.query_params.get("d")
if _share_token and st.session_state.get("_applied_share_token") != _share_token:
    st.session_state["_applied_share_token"] = _share_token
    try:
        _share_count = _apply_loaded_params(_decode_share_payload(_share_token))
        _mark_auto_alignment_synced()
        st.toast(f"Loaded {_share_count} parameters from the shared link")
    except Exception:
        logger.exception("Invalid share link payload")
        st.warning("The shared link could not be decoded; using the current parameters.")

try:
    _seed_alignment = _dccav.suggest_alignment(_driver_from_state())
    _seed_reflex = _dccav.suggest_reflex_alignment(_driver_from_state())
    _seed_sealed = _dccav.suggest_sealed_alignment(_driver_from_state())
except Exception:
    _seed_alignment = _dccav.DccavAlignment(3.1, 162.0, 6.25, 62.0, 51.5)
    _seed_reflex = _dccav.ReflexAlignment(11.52, 48.14)
    _seed_sealed = _dccav.SealedAlignment(11.52, 68.1, 0.512)
_default("box_vh_l", float(_seed_alignment.vh_l))
_default("box_fh_hz", float(_seed_alignment.fh_hz))
_default("box_vl_l", float(_seed_alignment.vl_l))
_default("box_fl_hz", float(_seed_alignment.fl_hz))
_default("reflex_vb_l", float(_seed_reflex.vb_l))
_default("reflex_fb_hz", float(_seed_reflex.fb_hz))
_default("sealed_vb_l", float(_seed_sealed.vb_l))
_sync_auto_alignment_if_needed()


if _BRAND_IMAGE.exists():
    st.image(str(_BRAND_IMAGE), width="stretch")
else:
    st.title("Load Forge")
st.caption(
    f"v{_VERSION} · DCCAV / bass reflex / acoustic suspension / infinite baffle · "
    "T/S driven response model"
)

workspace_col, project_col = st.columns([4, 1])
with workspace_col:
    st.segmented_control(
        "Workspace",
        _WORKSPACES,
        key="workspace_mode",
        label_visibility="collapsed",
        width="stretch",
    )
with project_col:
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
            use_container_width=True,
            help="Encodes the current design into the page URL and shows the "
                 "link below, ready to copy.",
        ):
            _token = _encode_share_payload()
            st.session_state["_applied_share_token"] = _token
            st.query_params["d"] = _token
            st.toast("Share link ready - copy it below")
        _active_share_token = st.query_params.get("d")
        if _active_share_token:
            st.code(_share_link_url(str(_active_share_token)), language=None)
            if st.button("Clear share link", use_container_width=True):
                st.session_state["_applied_share_token"] = None
                st.query_params.pop("d", None)
                st.rerun()
        upload = st.file_uploader("Load preset", type=["lfp", "json"])
        if upload is not None:
            try:
                payload = json.loads(upload.getvalue().decode("utf-8"))
                payload.pop("_load_forge_meta", None)
                count = _apply_loaded_params(payload)
                st.toast(f"Loaded {count} parameters")
                st.rerun()
            except Exception as exc:
                logger.exception("Invalid preset")
                st.error(f"Invalid preset: {exc}")


current_ts = None
current_alignment = None
current_reflex_alignment = None
current_sealed_alignment = None
derived = None

with st.sidebar:
    workspace_mode = str(st.session_state.get("workspace_mode", "Design a box"))
    st.subheader("1 · Driver" if workspace_mode == "Design a box" else "Candidate library")
    st.selectbox(
        "Load type",
        ["Infinite baffle", "Sealed", "Bass reflex", "DCCAV"],
        key="load_type",
        on_change=_on_load_type_change,
        help="Acoustic load simulated in the Design workspace and used to rank "
             "Find-a-driver candidates.",
    )
    all_preset_names = _dccav.driver_preset_names()
    st.text_input("Search preset", key="preset_search", placeholder="Brand or model")
    with st.expander("Library filters", expanded=workspace_mode == "Find a driver"):
        f0, f1 = st.columns(2)
        with f0:
            st.selectbox("Source", _PRESET_SOURCE_FILTERS, key="preset_source_filter")
            st.selectbox("Size", _PRESET_SIZE_FILTERS, key="preset_size_filter")
        with f1:
            st.selectbox(
                "Brand",
                _available_preset_families(all_preset_names),
                key="preset_family_filter",
            )
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
            preset_prices = _preset_price_values(all_preset_names, price_currency)
            price_max_available = max(preset_prices)
            if st.session_state["preset_max_price"] <= 0.0:
                st.session_state["preset_max_price"] = float(price_max_available)
            st.session_state["preset_max_price"] = min(
                float(price_max_available),
                max(0.0, float(st.session_state["preset_max_price"])),
            )
            st.checkbox("Filter by max price", key="preset_price_enabled")
            st.number_input(
                f"Max price ({price_currency})",
                min_value=0.0,
                max_value=float(price_max_available),
                step=1.0,
                key="preset_max_price",
                disabled=not st.session_state["preset_price_enabled"],
            )
        else:
            st.session_state["preset_price_enabled"] = False
            st.checkbox("Filter by max price", key="preset_price_enabled", disabled=True)
            st.caption("Price unavailable in the current preset dataset.")
    filtered_preset_names = _filter_driver_preset_names(
        all_preset_names,
        source=st.session_state["preset_source_filter"],
        family=st.session_state["preset_family_filter"],
        size=st.session_state["preset_size_filter"],
        search=st.session_state["preset_search"],
        max_price=(
            float(st.session_state["preset_max_price"])
            if st.session_state.get("preset_price_enabled", False)
            else None
        ),
        max_price_currency=(
            str(st.session_state["preset_price_currency"])
            if st.session_state.get("preset_price_enabled", False)
            else None
        ),
        selected=(
            st.session_state.get("driver_preset_name")
            if workspace_mode == "Design a box"
            else None
        ),
        driver_class=str(st.session_state.get("preset_class_filter", "All")),
    )
    if workspace_mode == "Design a box":
        current_preset = st.session_state.get("driver_preset_name", "Custom")
        preset_options = ["Custom", *filtered_preset_names]
        if current_preset not in preset_options:
            st.session_state["driver_preset_name"] = "Custom"
            current_preset = "Custom"
        st.caption(f"{len(filtered_preset_names)} / {len(all_preset_names)} presets")
        preset_name = st.selectbox(
            "Driver preset",
            preset_options,
            key="driver_preset_name",
            on_change=_on_driver_preset_change,
        )
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
        st.subheader("2 · Load & box")
        st.segmented_control(
            "Box strategy",
            _BOX_STRATEGIES,
            key="box_strategy",
            on_change=_on_box_strategy_change,
            disabled=st.session_state["load_type"] == "Infinite baffle",
            width="stretch",
            help="Suggested applies the empirical starter box and re-applies it "
                 "automatically when the driver or load changes. Optimized "
                 "derives the box from the optimizer goals. Manual unlocks "
                 "volumes and tuning for direct editing.",
        )
        if preset_name != "Custom":
            st.caption("Preset values are applied immediately.")
            try:
                purchase = _purchase_markdown(_dccav.driver_preset_info(preset_name))
            except ValueError:
                purchase = None
            if purchase:
                st.markdown(purchase)

        with st.expander("Driver T/S values", expanded=preset_name == "Custom"):
            c1, c2 = st.columns(2)
            with c1:
                st.number_input("Fs (Hz)", min_value=1.0, max_value=500.0, step=0.1,
                                key="driver_fs_hz", on_change=_on_driver_param_change)
                st.number_input("Qts", min_value=0.05, max_value=2.0, step=0.001,
                                format="%.3f", key="driver_qts", on_change=_on_driver_param_change)
                st.number_input("Re (Ω)", min_value=0.1, max_value=64.0, step=0.01,
                                key="driver_re_ohm", on_change=_on_driver_param_change)
            with c2:
                st.number_input("Vas (L)", min_value=0.1, max_value=1000.0, step=0.1,
                                key="driver_vas_l", on_change=_on_driver_param_change)
                st.number_input("Qms", min_value=0.051, max_value=50.0, step=0.001,
                                format="%.3f", key="driver_qms", on_change=_on_driver_param_change)
                st.number_input("Le (mH)", min_value=0.0, max_value=20.0, step=0.001,
                                format="%.3f", key="driver_le_mh", on_change=_on_driver_param_change)

            st.radio("Piston input", ["Diameter", "Sd"], horizontal=True, key="driver_sd_mode",
                     on_change=_on_driver_param_change)
            if st.session_state["driver_sd_mode"] == "Diameter":
                st.number_input("Piston diameter (mm)", min_value=10.0, max_value=1000.0,
                                step=0.1, key="driver_diameter_mm",
                                on_change=_on_driver_param_change)
                st.caption(
                    f"Sd = {_dccav.sd_from_diameter(st.session_state['driver_diameter_mm']):.1f} cm²"
                )
            else:
                st.number_input("Sd (cm²)", min_value=1.0, max_value=5000.0, step=1.0,
                                key="driver_sd_cm2", on_change=_on_driver_param_change)

            d3, d4 = st.columns(2)
            with d3:
                st.number_input("Xmax (mm)", min_value=0.0, max_value=100.0, step=0.1,
                                key="driver_xmax_mm", on_change=_on_driver_param_change)
            with d4:
                st.number_input("Pe (W)", min_value=0.0, max_value=5000.0, step=1.0,
                                key="driver_pe_w", on_change=_on_driver_param_change)

            with st.expander("Measured optional parameters"):
                st.number_input("Mms (g)", min_value=0.0, max_value=1000.0, step=0.01,
                                key="driver_mms_g", on_change=_on_driver_param_change)
                st.number_input("Cms (mm/N)", min_value=0.0, max_value=100.0, step=0.001,
                                format="%.3f", key="driver_cms_mm_n",
                                on_change=_on_driver_param_change)
                st.number_input("Bl (T·m)", min_value=0.0, max_value=100.0, step=0.01,
                                key="driver_bl_tm", on_change=_on_driver_param_change)

        try:
            current_ts = _driver_from_state()
            current_alignment = _dccav.suggest_alignment(current_ts)
            current_reflex_alignment = _dccav.suggest_reflex_alignment(current_ts)
            current_sealed_alignment = _dccav.suggest_sealed_alignment(current_ts)
            derived = _dccav.complete_driver(current_ts)
            load_type = st.session_state["load_type"]
            box_strategy = str(st.session_state.get("box_strategy", "Suggested"))
            if load_type == "Bass reflex":
                st.subheader("Bass Reflex Alignment")
                st.caption(
                    f"Starting point (Vb=Vas, Fb=Fs): Vb {current_reflex_alignment.vb_l:.2f} L / "
                    f"Fb {current_reflex_alignment.fb_hz:.1f} Hz"
                )
                if box_strategy == "Manual" and st.button(
                    "Reset to suggested reflex", use_container_width=True, key="apply_box_reflex"
                ):
                    _apply_empirical_box_for(current_ts)
                    _mark_auto_alignment_synced(current_ts)
                    st.rerun()
            elif load_type == "Sealed":
                st.subheader("Sealed Alignment")
                st.caption(
                    f"Qtc starter: Vb {current_sealed_alignment.vb_l:.2f} L · "
                    f"Fc {current_sealed_alignment.fc_hz:.1f} Hz · "
                    f"Qtc {current_sealed_alignment.qtc:.3f}"
                )
                if box_strategy == "Manual" and st.button(
                    "Reset to sealed starter", use_container_width=True, key="apply_box_sealed"
                ):
                    _apply_empirical_box_for(current_ts)
                    _mark_auto_alignment_synced(current_ts)
                    st.rerun()
            elif load_type == "Infinite baffle":
                st.subheader("Infinite Baffle")
                st.caption(
                    f"No enclosure or tuning: free-air Fs {current_ts.fs_hz:.1f} Hz · "
                    f"Qts {current_ts.qts:.3f}. Rear radiation is assumed fully isolated."
                )
            else:
                st.subheader("DCCAV Alignment")
                st.caption(
                    f"Suggested: Vh {current_alignment.vh_l:.2f} L / {current_alignment.fh_hz:.1f} Hz · "
                    f"Vl {current_alignment.vl_l:.2f} L / {current_alignment.fl_hz:.1f} Hz · "
                    f"Vtot {current_alignment.vh_l + current_alignment.vl_l:.2f} L"
                )
                alignment_warning = _alignment_warning(current_ts, current_alignment)
                if alignment_warning:
                    st.warning(alignment_warning)
                if box_strategy == "Manual" and st.button(
                    "Reset to suggested alignment", use_container_width=True, key="apply_box_dccav"
                ):
                    _apply_empirical_box_for(current_ts)
                    _mark_auto_alignment_synced(current_ts)
                    st.rerun()
            if load_type != "Infinite baffle" and box_strategy == "Suggested":
                st.caption("Suggested strategy is active: driver or load changes update the box automatically.")
            if load_type != "Infinite baffle" and box_strategy == "Optimized":
                with st.container(border=True):
                    st.markdown("##### Optimizer goals")
                    st.selectbox("Goal", list(_OPT_OBJECTIVE_LABELS), key="opt_objective")
                    g1, g2 = st.columns(2)
                    with g1:
                        st.number_input("Max total volume (L, 0 = off)", min_value=0.0, max_value=2000.0,
                                        step=1.0, key="opt_max_volume_l")
                        st.number_input("Max ripple (dB)", min_value=0.0, max_value=12.0,
                                        step=0.5, key="opt_max_ripple_db")
                        st.number_input("Excursion limit (x Xmax, 0 = off)", min_value=0.0, max_value=3.0,
                                        step=0.05, key="opt_excursion_ratio")
                    with g2:
                        st.number_input("Target F3 (Hz, 0 = lowest)", min_value=0.0, max_value=500.0,
                                        step=1.0, key="opt_target_f3_hz")
                        st.number_input("Max group delay (ms, 0 = off)", min_value=0.0, max_value=100.0,
                                        step=1.0, key="opt_max_gd_ms")
                    if st.button("Run optimizer and apply", type="primary", use_container_width=True):
                        with st.spinner("Optimizing box..."):
                            optimized = _run_box_optimizer(current_ts)
                        _apply_optimized_box(optimized.box)
                        _mark_auto_alignment_synced(current_ts)
                        st.rerun()
                    current_optimizer_summary = _current_optimizer_summary(current_ts)
                    if current_optimizer_summary:
                        st.caption(current_optimizer_summary)
        except Exception as exc:
            current_ts = None
            current_alignment = None
            current_reflex_alignment = None
            current_sealed_alignment = None
            derived = None
            st.error(f"Driver parameters are invalid - check the T/S values. ({exc})")

        box_edit_disabled = st.session_state.get("box_strategy", "Suggested") != "Manual"
        if st.session_state["load_type"] == "Bass reflex":
            _box_number_with_nudge(
                "Vb box (L)", "reflex_vb_l", min_value=0.05, max_value=1000.0, step=0.01,
                disabled=box_edit_disabled)
            _box_number_with_nudge(
                "Fb tuning (Hz)", "reflex_fb_hz", min_value=1.0, max_value=1000.0, step=0.1,
                disabled=box_edit_disabled)
            active_reflex_losses = _reflex_box_from_state()
            loss_mode = "custom" if st.session_state.get("reflex_custom_losses", False) else "normal"
            st.caption(
                f"Reflex losses ({loss_mode}): "
                f"Qabs {active_reflex_losses.q_abs:.1f} / "
                f"Qport {active_reflex_losses.q_port:.1f} / "
                f"Qleak {active_reflex_losses.q_leak:.0f}"
            )
            st.button("Reset reflex losses", on_click=_reset_reflex_losses, use_container_width=True)
            with st.expander("Loss factors"):
                st.checkbox("Custom reflex losses", key="reflex_custom_losses")
                disabled = not st.session_state.get("reflex_custom_losses", False)
                st.number_input(
                    "Qabs box", min_value=0.2, max_value=500.0, step=0.5,
                    key="reflex_q_abs", disabled=disabled)
                st.number_input(
                    "Qleak box", min_value=1.0, max_value=10000.0, step=10.0,
                    key="reflex_q_leak", disabled=disabled)
                st.number_input(
                    "Qport", min_value=0.2, max_value=500.0, step=0.5,
                    key="reflex_q_port", disabled=disabled)
            with st.expander("Port geometry"):
                st.number_input(
                    "Vent diameter (cm, 0 = off)", min_value=0.0, max_value=60.0,
                    step=0.5, key="reflex_port_d_cm")
                st.caption(
                    "Duct length uses the Helmholtz relation with one flanged and "
                    "one free end; air-speed warnings use the ~5% of c guideline."
                )
        elif st.session_state["load_type"] == "Sealed":
            _box_number_with_nudge(
                "Vb sealed (L)", "sealed_vb_l", min_value=0.05, max_value=100000.0, step=0.01,
                disabled=box_edit_disabled)
            if current_ts is not None:
                fc_hz, qtc = _dccav.sealed_system_metrics(current_ts, _sealed_box_from_state())
                st.caption(f"Closed-box Fc {fc_hz:.1f} Hz · Qtc {qtc:.3f}")
            with st.expander("Sealed loss factors"):
                st.number_input(
                    "Qabs sealed", min_value=0.2, max_value=500.0, step=0.5,
                    key="sealed_q_abs")
                st.number_input(
                    "Qleak sealed", min_value=1.0, max_value=10000.0, step=10.0,
                    key="sealed_q_leak")
        elif st.session_state["load_type"] == "Infinite baffle":
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
                    st.number_input("Qabs upper", min_value=0.2, max_value=500.0, step=0.5, key="loss_q_abs_h")
                    st.number_input("Qleak upper", min_value=1.0, max_value=10000.0, step=10.0, key="loss_q_leak_h")
                    st.number_input("Qport upper", min_value=0.2, max_value=500.0, step=0.5, key="loss_q_port_h")
                with l2:
                    st.number_input("Qabs lower", min_value=0.2, max_value=500.0, step=0.5, key="loss_q_abs_l")
                    st.number_input("Qleak lower", min_value=1.0, max_value=10000.0, step=10.0, key="loss_q_leak_l")
                    st.number_input("Qport lower", min_value=0.2, max_value=500.0, step=0.5, key="loss_q_port_l")

            with st.expander("Port geometry"):
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
                    "Duct lengths use the Helmholtz relation: the upper port counts "
                    "two flanged ends, the lower vent one flanged and one free end; "
                    "air-speed warnings use the ~5% of c guideline."
                )

        if st.session_state["load_type"] != "Infinite baffle" and box_edit_disabled:
            st.caption("Switch Box strategy to Manual to edit volumes and tuning directly.")

        st.subheader("3 · Drive")
        st.number_input(
            "Voltage (V)", min_value=0.01, max_value=200.0, step=0.01,
            key="sim_voltage",
        )
        st.toggle("Advanced controls", key="ui_show_advanced")
        if st.session_state.get("ui_show_advanced", False):
            with st.container(border=True):
                s1, s2 = st.columns(2)
                with s1:
                    st.number_input(
                        "F min (Hz)", min_value=1.0, max_value=1000.0,
                        step=1.0, key="sim_f_min",
                    )
                    st.number_input(
                        "Points", min_value=80, max_value=4000,
                        step=20, key="sim_points",
                    )
                with s2:
                    st.number_input(
                        "F max (Hz)", min_value=10.0, max_value=5000.0,
                        step=10.0, key="sim_f_max",
                    )
                    st.number_input(
                        "Series R (Ω)", min_value=0.0, max_value=100.0,
                        step=0.1, key="sim_series_r_ohm",
                        help="Amplifier output + cable + crossover-coil DCR in series with the "
                             "driver. Optimizer and driver ranking evaluate at 0 Ω.",
                    )


if st.session_state.get("workspace_mode") == "Find a driver":
    _render_find_driver_workspace(filtered_preset_names)
    st.stop()


try:
    if current_ts is None:
        raise ValueError("Driver parameters are incomplete")
    if st.session_state["sim_f_max"] <= st.session_state["sim_f_min"]:
        raise ValueError("F max must be greater than F min")
    load_type = st.session_state["load_type"]
    is_reflex = load_type == "Bass reflex"
    is_sealed = load_type == "Sealed"
    is_infinite_baffle = load_type == "Infinite baffle"
    chart_sig = _chart_signature()
    if is_reflex:
        box = _reflex_box_from_state()
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
    if is_reflex:
        result = _dccav.simulate_reflex(current_ts, box, freq, sim_voltage, sim_series_r)
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
    if is_reflex and len(z_peak_freqs) < 2:
        model_warnings.append(
            "Bass reflex should show two impedance peaks in the simulated range; "
            f"currently found {len(z_peak_freqs)}. "
            f"Check F min/F max, Vb, Fb and reflex losses "
            f"(Qabs={box.q_abs:.1f}, Qport={box.q_port:.1f}, Qleak={box.q_leak:.0f}). "
            "Low Qabs/Qport values overdamp the vent resonance; use Reset reflex losses "
            "for a normal starter alignment."
        )
    port_geometry_rows = []
    if is_reflex:
        vent_d_cm = float(st.session_state.get("reflex_port_d_cm", 0.0))
        if vent_d_cm > 0.0:
            port_geometry_rows.append(_port_geometry_row(
                "Vent", vent_d_cm, box.vb_l, box.fb_hz, 1.463, result, "lower"))
    elif load_type == "DCCAV":
        upper_d_cm = float(st.session_state.get("box_port_d_h_cm", 0.0))
        lower_d_cm = float(st.session_state.get("box_port_d_l_cm", 0.0))
        if upper_d_cm > 0.0:
            port_geometry_rows.append(_port_geometry_row(
                "Upper port", upper_d_cm, box.vh_l, box.fh_hz, 1.7, result, "upper"))
        if lower_d_cm > 0.0:
            port_geometry_rows.append(_port_geometry_row(
                "Lower port", lower_d_cm, box.vl_l, box.fl_hz, 1.463, result, "lower"))
    for row in port_geometry_rows:
        if row["Length cm"] <= 0.0:
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
    design_name = str(st.session_state.get("driver_preset_name", "Custom"))
    design_config = str(st.session_state.get("driver_config", "Single driver"))
    if design_config != "Single driver":
        design_name = f"{design_name} ({design_config})"
    design_strategy = str(st.session_state.get("box_strategy", "Suggested"))
    st.caption(f"{design_name} · {load_type} · {design_strategy} · {sim_voltage:.2f} V")
    if is_infinite_baffle:
        m1, m2, m3, m4 = st.columns(4)
        m5 = None
    else:
        m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("F3", _fmt_hz(thresholds[3]))
    m2.metric("Peak LF SPL", _fmt_db(metrics["max_spl_db"]))
    m3.metric("Max excursion", f"{metrics['max_excursion_mm']:.2f} mm")
    m4.metric("Min impedance", f"{metrics['min_impedance_ohm']:.2f} Ω")
    if m5 is not None:
        vtot_l = box.vb_l if (is_reflex or is_sealed) else box.vh_l + box.vl_l
        m5.metric("Box volume", f"{vtot_l:.1f} L")

    for warning in model_warnings:
        st.warning(warning)

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
            a1.metric("Infinite baffle Fs", f"{current_ts.fs_hz:.1f} Hz")
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

    (
        tab_response,
        tab_excursion,
        tab_impedance,
        tab_ports,
        tab_gd,
        tab_atlas,
    ) = st.tabs(["Response", "Excursion", "Impedance", "Ports", "Group Delay", "Atlas"])

    with tab_response:
        _render_response_tab(
            current_ts, load_type, box, result, thresholds, freq, sim_voltage, sim_series_r)
    with tab_excursion:
        st.subheader("Cone Excursion")
        xmax_mm = float(st.session_state.get("driver_xmax_mm", 0.0))
        st.altair_chart(
            _plot_excursion(result, xmax_mm),
            width="stretch",
            key=f"excursion_chart_{chart_sig}",
        )
        if xmax_mm > 0.0:
            st.caption(f"Dashed red line: driver Xmax = {xmax_mm:.1f} mm.")
        else:
            st.caption("Set the driver Xmax to draw the excursion limit line.")
    with tab_impedance:
        st.subheader("Electrical Impedance")
        st.altair_chart(_plot_impedance(result), width="stretch", key=f"impedance_chart_{chart_sig}")
    with tab_ports:
        _render_ports_tab(result, port_geometry_rows, load_type)
    with tab_gd:
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
            st.caption(f"Dashed red line: optimizer group-delay limit = {gd_limit_ms:.0f} ms.")
    with tab_atlas:
        _render_atlas_tab(current_ts, load_type, box, sim_voltage)

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

    dl_csv, dl_frd, dl_zma = st.columns(3)
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

except Exception as exc:
    logger.exception("Simulation failed")
    st.error(f"Simulation failed: {exc}")
