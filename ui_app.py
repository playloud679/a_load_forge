"""
Load Forge — acoustic-load simulator.

Single-page Streamlit dashboard for DCCAV, bass-reflex, acoustic-suspension and
infinite-baffle loads, with response plots and derived data in the workspace.
"""

from __future__ import annotations

import csv
import hashlib
import importlib
import io
import json
import logging
import sys
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st


logger = logging.getLogger("load_forge.ui")

sys.path.insert(0, str(Path(__file__).parent / "src"))
import dccav as _dccav

importlib.reload(_dccav)


try:
    _VERSION = (Path(__file__).parent / "VERSION").read_text().strip()
except OSError:
    _VERSION = "dev"


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
    "Upper port": "#8ecaff",
    "Impedance": "#355070",
    "Excursion": "#b35c00",
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


def _collect_params() -> dict:
    out = {}
    for key, value in st.session_state.items():
        if any(key.startswith(prefix) for prefix in _PARAM_PREFIXES):
            try:
                json.dumps(value)
            except (TypeError, ValueError):
                continue
            out[key] = value
    return out


def _apply_loaded_params(data: dict) -> int:
    applied = 0
    for key, value in data.items():
        if any(key.startswith(prefix) for prefix in _PARAM_PREFIXES):
            if key == "load_type" and value == "Suspension pneumatic":
                value = "Acoustic suspension"
            st.session_state[key] = value
            applied += 1
    return applied


def _chart_signature() -> str:
    prefixes = (
        "driver_", "box_", "reflex_", "sealed_", "loss_", "sim_", "plot_", "cursor_", "load_type"
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
    elif load_type == "Acoustic suspension":
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
    elif load_type == "Acoustic suspension":
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
    elif load_type == "Acoustic suspension":
        _apply_sealed_alignment(_dccav.suggest_sealed_alignment(driver))
    elif load_type == "Infinite baffle":
        return
    else:
        _apply_alignment(_dccav.suggest_alignment(driver))


def _reset_reflex_losses():
    st.session_state["reflex_q_abs"] = _DEFAULT_REFLEX_Q_ABS
    st.session_state["reflex_q_leak"] = _DEFAULT_REFLEX_Q_LEAK
    st.session_state["reflex_q_port"] = _DEFAULT_REFLEX_Q_PORT
    st.session_state["reflex_custom_losses"] = False


def _nudge_state(key: str, factor: float):
    value = float(st.session_state.get(key, 0.0) or 0.0)
    st.session_state[key] = max(value * factor, 1e-9)


def _box_number_with_nudge(
    label: str,
    key: str,
    *,
    min_value: float,
    max_value: float,
    step: float,
):
    n1, n2, n3 = st.columns([5, 1, 1])
    with n1:
        st.number_input(label, min_value=min_value, max_value=max_value, step=step, key=key)
    with n2:
        st.button("-3%", key=f"{key}_minus_3", on_click=_nudge_state, args=(key, 0.97),
                  use_container_width=True)
    with n3:
        st.button("+3%", key=f"{key}_plus_3", on_click=_nudge_state, args=(key, 1.03),
                  use_container_width=True)


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
        driver = _dccav.get_driver_preset(preset_name)
        _apply_driver_preset(driver)
        if st.session_state.get("sim_auto_align", True):
            _apply_suggested_box_for(driver)
            _mark_auto_alignment_synced(driver)
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
        for freq, value in zip(result.frequency_hz, values):
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
    top = float(np.max(finite)) + 5.0
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
            alt.Tooltip("impedance_ohm:Q", title="Ohm", format=".2f"),
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


def _plot_response(result: _dccav.SimulationResult, cursor_rows: list[dict]) -> alt.Chart:
    series = _response_series(result)
    if not series:
        raise ValueError("No response traces selected")
    data = _series_frame(result, series)
    y_domain = _response_y_domain(result, series)
    chart = _line_chart(
        data,
        "LF pressure estimate (dB)",
        height=760,
        y_domain=y_domain,
    )
    chart = chart + _click_marker_layer(result)
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
    return _line_chart(data, "Impedance (ohm)", height=285, legend=False)


def _plot_mil(result: _dccav.SimulationResult) -> alt.Chart:
    data = _series_frame(result, {"MIL": result.mil_w})
    return _line_chart(data, "Max input power (W)", height=240, legend=False)


def _plot_ports(result: _dccav.SimulationResult) -> alt.Chart:
    series = _port_series(result)
    if not series:
        raise ValueError("No port traces selected")
    data = _series_frame(result, series)
    return _line_chart(data, "Volume velocity (m3/s)", height=320)


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
    if load_type == "Suspension pneumatic":
        load_type = "Acoustic suspension"
    freq = np.geomspace(float(f_min_hz), float(f_max_hz), int(points))
    batch_goals = None
    if goals is not None and load_type != "Infinite baffle":
        # Batch compares drivers at the exact requested enclosure volume.
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
            elif load_type == "Acoustic suspension":
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
            elif load_type == "Acoustic suspension":
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
    if load_type == "Suspension pneumatic":
        load_type = "Acoustic suspension"
    name = str(row["Driver"])
    driver = _dccav.get_driver_preset(name)
    st.session_state["load_type"] = load_type
    st.session_state["driver_preset_name"] = name
    _apply_driver_preset(driver)
    st.session_state["sim_auto_align"] = False
    if load_type == "Bass reflex":
        st.session_state["reflex_vb_l"] = float(row["Vb L"])
        st.session_state["reflex_fb_hz"] = float(row["Fb Hz"])
    elif load_type == "Acoustic suspension":
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
        result.port_h_velocity,
        result.port_l_velocity,
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
_default("preset_family_filter", "All")
_default("preset_source_filter", "All")
_default("preset_size_filter", "All")
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
_default("sealed_q_abs", 15.0)
_default("sealed_q_leak", 1000.0)
_default("load_type", "DCCAV")
if st.session_state["load_type"] == "Suspension pneumatic":
    st.session_state["load_type"] = "Acoustic suspension"
_default("sim_f_min", 10.0)
_default("sim_f_max", 500.0)
_default("sim_points", 600)
_default("sim_voltage", 2.83)
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
_default("plot_port_upper", "Upper port" in st.session_state["plot_port_traces"])
_default("plot_port_lower", "Lower port" in st.session_state["plot_port_traces"])
_default("plot_show_excursion", True)
_default("plot_show_impedance", True)
_default("plot_show_ports", True)
_default("cursor_auto_f3", True)
_default("cursor_auto_f6", True)
_default("cursor_auto_f10", True)
_default("cursor_manual_enabled", False)
_default("cursor_manual_1_hz", 50.0)
_default("cursor_manual_2_hz", 100.0)
_default("batch_volume_l", 50.0)
_default("batch_candidate_limit", 800)
_default("batch_result_count", 25)
_default("batch_points", 260)
_default("batch_use_optimizer", True)
_default("opt_align_mode", "Empirical (article)")
_default("opt_objective", "Balanced")
_default("opt_max_volume_l", 0.0)
_default("opt_target_f3_hz", 0.0)
_default("opt_max_ripple_db", 3.0)
_default("opt_excursion_ratio", 1.0)
_default("opt_max_gd_ms", 0.0)
_apply_pending_batch_result()

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


st.title("Load Forge")
st.caption(
    f"v{_VERSION} · DCCAV / bass reflex / acoustic suspension / infinite baffle · "
    "T/S driven response model"
)

save_col, load_col = st.columns([1, 1])
with save_col:
    preset = {"_load_forge_meta": {"version": _VERSION, "format": 1}, **_collect_params()}
    st.download_button(
        "Save preset",
        json.dumps(preset, indent=2).encode("utf-8"),
        "load_forge.lfp",
        "application/json",
        use_container_width=True,
    )
with load_col:
    upload = st.file_uploader("Load preset", type=["lfp", "json"], label_visibility="collapsed")
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


with st.sidebar:
    st.subheader("Driver T/S")
    st.radio(
        "Load type",
        ["DCCAV", "Bass reflex", "Acoustic suspension", "Infinite baffle"],
        horizontal=True,
        key="load_type",
        on_change=_on_load_type_change,
    )
    all_preset_names = _dccav.driver_preset_names()
    f0, f1, f2 = st.columns([1, 1, 1])
    with f0:
        st.selectbox("Source", _PRESET_SOURCE_FILTERS, key="preset_source_filter")
    with f1:
        st.selectbox(
            "Brand",
            _available_preset_families(all_preset_names),
            key="preset_family_filter",
        )
    with f2:
        st.selectbox("Size", _PRESET_SIZE_FILTERS, key="preset_size_filter")
    st.text_input("Search preset", key="preset_search")
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
        selected=st.session_state.get("driver_preset_name"),
    )
    current_preset = st.session_state.get("driver_preset_name", "Custom")
    preset_options = ["Custom", *filtered_preset_names]
    if current_preset not in preset_options:
        st.session_state["driver_preset_name"] = "Custom"
        current_preset = "Custom"
    st.caption(f"{len(filtered_preset_names)} / {len(all_preset_names)} presets")
    preset_name = st.selectbox(
        "Driver preset",
        preset_options,
        index=preset_options.index(current_preset),
        key="driver_preset_name",
        on_change=_on_driver_preset_change,
    )
    st.checkbox("Auto-align box from T/S", key="sim_auto_align")
    st.radio(
        "Alignment mode",
        ["Empirical (article)", "Optimized (goals)"],
        horizontal=True,
        key="opt_align_mode",
        disabled=st.session_state["load_type"] == "Infinite baffle",
    )
    if preset_name != "Custom":
        st.caption("Preset values are applied immediately.")
        try:
            purchase = _purchase_markdown(_dccav.driver_preset_info(preset_name))
        except ValueError:
            purchase = None
        if purchase:
            st.markdown(purchase)

    c1, c2 = st.columns(2)
    with c1:
        st.number_input("Fs (Hz)", min_value=1.0, max_value=500.0, step=0.1,
                        key="driver_fs_hz", on_change=_on_driver_param_change)
        st.number_input("Qts", min_value=0.05, max_value=2.0, step=0.001,
                        format="%.3f", key="driver_qts", on_change=_on_driver_param_change)
        st.number_input("Re (ohm)", min_value=0.1, max_value=64.0, step=0.01,
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
        st.caption(f"Sd = {_dccav.sd_from_diameter(st.session_state['driver_diameter_mm']):.1f} cm2")
    else:
        st.number_input("Sd (cm2)", min_value=1.0, max_value=5000.0, step=1.0,
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
        st.number_input("Bl (T m)", min_value=0.0, max_value=100.0, step=0.01,
                        key="driver_bl_tm", on_change=_on_driver_param_change)

    try:
        current_ts = _driver_from_state()
        current_alignment = _dccav.suggest_alignment(current_ts)
        current_reflex_alignment = _dccav.suggest_reflex_alignment(current_ts)
        current_sealed_alignment = _dccav.suggest_sealed_alignment(current_ts)
        derived = _dccav.complete_driver(current_ts)
        load_type = st.session_state["load_type"]
        if load_type == "Bass reflex":
            st.subheader("Bass Reflex Alignment")
            st.caption(
                f"Starting point (Vb=Vas, Fb=Fs): Vb {current_reflex_alignment.vb_l:.2f} L / "
                f"Fb {current_reflex_alignment.fb_hz:.1f} Hz"
            )
            apply_label = (
                "Apply optimized box" if _alignment_uses_optimizer() else "Apply suggested reflex"
            )
            if st.button(apply_label, use_container_width=True, key="apply_box_reflex"):
                _apply_suggested_box_for(current_ts)
                _mark_auto_alignment_synced(current_ts)
                st.rerun()
        elif load_type == "Acoustic suspension":
            st.subheader("Acoustic Suspension Alignment")
            st.caption(
                f"Qtc starter: Vb {current_sealed_alignment.vb_l:.2f} L · "
                f"Fc {current_sealed_alignment.fc_hz:.1f} Hz · "
                f"Qtc {current_sealed_alignment.qtc:.3f}"
            )
            apply_label = "Apply optimized box" if _alignment_uses_optimizer() else "Apply sealed starter"
            if st.button(apply_label, use_container_width=True, key="apply_box_sealed"):
                _apply_suggested_box_for(current_ts)
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
            apply_label = (
                "Apply optimized box" if _alignment_uses_optimizer() else "Apply suggested alignment"
            )
            if st.button(apply_label, use_container_width=True, key="apply_box_dccav"):
                _apply_suggested_box_for(current_ts)
                _mark_auto_alignment_synced(current_ts)
                st.rerun()
        if load_type != "Infinite baffle":
            with st.expander("Optimizer goals", expanded=_alignment_uses_optimizer()):
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
                if st.button("Optimize box now", use_container_width=True):
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
        st.error(str(exc))

    if st.session_state["load_type"] == "Bass reflex":
        _box_number_with_nudge(
            "Vb box (L)", "reflex_vb_l", min_value=0.05, max_value=1000.0, step=0.01)
        _box_number_with_nudge(
            "Fb tuning (Hz)", "reflex_fb_hz", min_value=1.0, max_value=1000.0, step=0.1)
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
    elif st.session_state["load_type"] == "Acoustic suspension":
        _box_number_with_nudge(
            "Vb sealed (L)", "sealed_vb_l", min_value=0.05, max_value=100000.0, step=0.01)
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
                "Vh upper (L)", "box_vh_l", min_value=0.05, max_value=1000.0, step=0.01)
            _box_number_with_nudge(
                "fh upper (Hz)", "box_fh_hz", min_value=1.0, max_value=1000.0, step=0.1)
        with b2:
            _box_number_with_nudge(
                "Vl lower (L)", "box_vl_l", min_value=0.05, max_value=1000.0, step=0.01)
            _box_number_with_nudge(
                "fl lower (Hz)", "box_fl_hz", min_value=1.0, max_value=1000.0, step=0.1)

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

    st.subheader("Simulation")
    s1, s2 = st.columns(2)
    with s1:
        st.number_input("F min (Hz)", min_value=1.0, max_value=1000.0, step=1.0, key="sim_f_min")
        st.number_input("Points", min_value=80, max_value=4000, step=20, key="sim_points")
    with s2:
        st.number_input("F max (Hz)", min_value=10.0, max_value=5000.0, step=10.0, key="sim_f_max")
        st.number_input("Voltage (V)", min_value=0.01, max_value=200.0, step=0.01, key="sim_voltage")


try:
    if current_ts is None:
        raise ValueError("Driver parameters are incomplete")
    if st.session_state["sim_f_max"] <= st.session_state["sim_f_min"]:
        raise ValueError("F max must be greater than F min")
    load_type = st.session_state["load_type"]
    is_reflex = load_type == "Bass reflex"
    is_sealed = load_type == "Acoustic suspension"
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
    if is_reflex:
        result = _dccav.simulate_reflex(current_ts, box, freq, float(st.session_state["sim_voltage"]))
    elif is_sealed:
        result = _dccav.simulate_sealed(current_ts, box, freq, float(st.session_state["sim_voltage"]))
    elif is_infinite_baffle:
        result = _dccav.simulate_infinite_baffle(current_ts, freq, float(st.session_state["sim_voltage"]))
    else:
        result = _dccav.simulate(current_ts, box, freq, float(st.session_state["sim_voltage"]))
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
    cursor_rows = _cursor_rows(result, thresholds)

    m1, m2, m3, m4, m5, m6, m7 = st.columns(7)
    m1.metric("Peak LF SPL", _fmt_db(metrics["max_spl_db"]))
    m2.metric("F3", _fmt_hz(thresholds[3]))
    m3.metric("F6", _fmt_hz(thresholds[6]))
    m4.metric("F10", _fmt_hz(thresholds[10]))
    m5.metric("Max excursion", f"{metrics['max_excursion_mm']:.2f} mm")
    m6.metric("Min impedance", f"{metrics['min_impedance_ohm']:.2f} ohm")
    m7.metric("Z peaks", ", ".join(f"{f:.0f}" for f in z_peak_freqs[:3]) or "n/a")

    for warning in model_warnings:
        st.warning(warning)

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

    st.subheader("Plot Tools")
    has_ports = load_type in {"DCCAV", "Bass reflex"}
    r1, r2, r3, r4, r5, r6, r7, r8, r9, r10 = st.columns(10)
    with r1:
        st.checkbox("Total", key="plot_response_total")
    with r2:
        st.checkbox("Cone", key="plot_response_driver")
    with r3:
        st.checkbox("Lower port", key="plot_response_lower_port", disabled=not has_ports)
    with r4:
        st.checkbox("MOL", key="plot_response_mol")
    with r5:
        st.checkbox("MIL", key="plot_show_mil")
    with r6:
        st.checkbox("Upper port", key="plot_port_upper", disabled=load_type != "DCCAV")
    with r7:
        st.checkbox("Lower port V", key="plot_port_lower", disabled=not has_ports)
    with r8:
        st.checkbox("Exc.", key="plot_show_excursion")
    with r9:
        st.checkbox("Z", key="plot_show_impedance")
    with r10:
        st.checkbox("Ports", key="plot_show_ports", disabled=not has_ports)

    c0, c1, c2, c3, c4, c5 = st.columns([1.1, 1, 1, 1, 1.2, 1.2])
    with c0:
        st.toggle("Manual", key="cursor_manual_enabled")
    with c1:
        st.checkbox("F3", key="cursor_auto_f3")
    with c2:
        st.checkbox("F6", key="cursor_auto_f6")
    with c3:
        st.checkbox("F10", key="cursor_auto_f10")
    with c4:
        st.number_input(
            "M1 (Hz)",
            min_value=1.0,
            max_value=5000.0,
            step=1.0,
            key="cursor_manual_1_hz",
        )
    with c5:
        st.number_input(
            "M2 (Hz)",
            min_value=1.0,
            max_value=5000.0,
            step=1.0,
            key="cursor_manual_2_hz",
        )

    with st.expander("Batch LF Finder"):
        st.caption(
            "Ranks the currently filtered presets in the selected load type. "
            "Every candidate uses the exact requested volume: DCCAV splits it between Vh/Vl, "
            "while bass reflex and acoustic suspension use it as Vb. Infinite baffle ignores volume."
        )
        max_batch_candidates = max(len(filtered_preset_names), 1)
        if int(st.session_state["batch_candidate_limit"]) > max_batch_candidates:
            st.session_state["batch_candidate_limit"] = max_batch_candidates
        b0, b1, b2, b3 = st.columns([1, 1, 1, 1])
        with b0:
            st.number_input(
                "Box volume (L)",
                min_value=0.1,
                max_value=2000.0,
                step=1.0,
                key="batch_volume_l",
                disabled=is_infinite_baffle,
            )
        with b1:
            st.number_input(
                "Scan presets",
                min_value=1,
                max_value=max_batch_candidates,
                step=50,
                key="batch_candidate_limit",
            )
        with b2:
            st.number_input(
                "Results",
                min_value=1,
                max_value=200,
                step=5,
                key="batch_result_count",
            )
        with b3:
            st.number_input(
                "Batch points",
                min_value=80,
                max_value=1000,
                step=20,
                key="batch_points",
            )
        scan_count = min(int(st.session_state["batch_candidate_limit"]), len(filtered_preset_names))
        st.checkbox(
            "Optimize each driver box (Optimizer goals, fixed batch volume)",
            key="batch_use_optimizer",
            disabled=is_infinite_baffle,
        )
        if st.button("Find lowest drivers", use_container_width=True, disabled=not filtered_preset_names):
            batch_goals = (
                _optimizer_goals_from_state()
                if st.session_state.get("batch_use_optimizer", True) and not is_infinite_baffle
                else None
            )
            spinner_text = (
                f"Optimizing {scan_count} presets" if batch_goals is not None
                else f"Scanning {scan_count} presets"
            )
            with st.spinner(spinner_text):
                batch_rows = _batch_rank_presets(
                    tuple(filtered_preset_names),
                    st.session_state["load_type"],
                    float(st.session_state["batch_volume_l"]),
                    float(st.session_state["sim_voltage"]),
                    float(st.session_state["sim_f_min"]),
                    float(st.session_state["sim_f_max"]),
                    int(st.session_state["batch_points"]),
                    scan_count,
                    goals=batch_goals,
                )
            st.session_state["batch_results"] = batch_rows
            st.session_state["batch_result_context"] = (
                st.session_state["load_type"],
                float(st.session_state["batch_volume_l"]),
                scan_count,
            )
        batch_rows = st.session_state.get("batch_results", [])
        if batch_rows:
            context = st.session_state.get("batch_result_context", ("", 0.0, 0))
            result_load_type = str(context[0] or st.session_state["load_type"])
            st.caption(f"{len(batch_rows)} usable candidates from {context[2]} scanned presets")
            batch_df = pd.DataFrame(batch_rows).head(int(st.session_state["batch_result_count"]))
            if "Price" not in batch_df.columns:
                batch_df["Price"] = np.nan
            if "Currency" not in batch_df.columns:
                batch_df["Currency"] = ""
            if "Buy" not in batch_df.columns:
                batch_df["Buy"] = ""
            if "Ripple dB" not in batch_df.columns:
                batch_df["Ripple dB"] = np.nan
            columns = [
                "Driver", "Brand", "Size in", "F3 Hz", "F6 Hz", "F10 Hz",
                "Peak dB", "Max excursion mm", "Min ohm",
            ]
            if batch_df["Ripple dB"].notna().any():
                columns.insert(columns.index("Peak dB") + 1, "Ripple dB")
            if batch_df["Price"].notna().any():
                columns.insert(3, "Price")
                columns.insert(4, "Currency")
            if result_load_type == "Bass reflex":
                columns += ["Vb L", "Fb Hz"]
            elif result_load_type == "Acoustic suspension":
                columns += ["Vb L", "Fc Hz", "Qtc"]
            elif result_load_type == "Infinite baffle":
                columns += ["Fc Hz", "Qtc"]
            else:
                columns += ["Vh L", "fh Hz", "Vl L", "fl Hz"]
            if batch_df["Buy"].fillna("").astype(bool).any():
                columns.append("Buy")
            table_state = st.dataframe(
                batch_df[columns],
                width="stretch",
                hide_index=True,
                key="batch_results_table",
                on_select="rerun",
                selection_mode="single-row",
                column_config={
                    "F3 Hz": st.column_config.NumberColumn(format="%.1f"),
                    "F6 Hz": st.column_config.NumberColumn(format="%.1f"),
                    "F10 Hz": st.column_config.NumberColumn(format="%.1f"),
                    "Peak dB": st.column_config.NumberColumn(format="%.1f"),
                    "Ripple dB": st.column_config.NumberColumn(format="%.1f"),
                    "Price": st.column_config.NumberColumn(format="%.2f"),
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
                },
            )
            selected_rows = getattr(table_state.selection, "rows", []) if table_state else []
            if selected_rows:
                selected_index = int(selected_rows[0])
                if 0 <= selected_index < len(batch_df):
                    selected_row = batch_df.iloc[selected_index].to_dict()
                    selection_key = (
                        result_load_type,
                        str(selected_row["Driver"]),
                        float(context[1] or st.session_state["batch_volume_l"]),
                        selected_index,
                    )
                    if st.session_state.get("batch_applied_selection") != selection_key:
                        st.session_state["batch_applied_selection"] = selection_key
                        st.session_state["batch_pending_result"] = {
                            "row": selected_row,
                            "load_type": result_load_type,
                        }
                        st.rerun()
        elif filtered_preset_names:
            st.caption(f"Ready to scan {scan_count} of {len(filtered_preset_names)} filtered presets.")
        else:
            st.caption("No presets match the current filters.")

    st.subheader("LF Load Response")
    if is_reflex:
        st.caption(
            "Bass-reflex total response is the vector sum of the exposed cone "
            "front radiation and the vent. The model is low-frequency only; "
            "it does not include baffle step, breakup, room gain or crossover behaviour."
        )
    elif is_sealed:
        st.caption(
            "Acoustic-suspension response is the exposed cone front with the rear wave enclosed. "
            "The model includes closed-box compliance and losses, but not room gain or baffle step."
        )
    elif is_infinite_baffle:
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
    if _response_series(result):
        st.altair_chart(_plot_response(result, cursor_rows), width="stretch", key=f"response_chart_{chart_sig}")
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
            "impedance_ohm": "Ohm",
            "excursion_mm": "Excursion mm",
        })
        st.dataframe(
            cursor_table[["Cursor", "Mode", "Hz", "Total dB", "Ohm", "Excursion mm"]],
            width="stretch",
            hide_index=True,
        )

    if st.session_state.get("plot_show_excursion", True) or st.session_state.get("plot_show_impedance", True):
        c1, c2 = st.columns(2)
        with c1:
            if st.session_state.get("plot_show_excursion", True):
                st.subheader("Cone Excursion")
                st.altair_chart(
                    _plot_excursion(result, float(st.session_state.get("driver_xmax_mm", 0.0))),
                    width="stretch",
                    key=f"excursion_chart_{chart_sig}",
                )
        with c2:
            if st.session_state.get("plot_show_impedance", True):
                st.subheader("Electrical Impedance")
                st.altair_chart(_plot_impedance(result), width="stretch", key=f"impedance_chart_{chart_sig}")

    if st.session_state.get("plot_show_ports", True) and has_ports:
        st.subheader("Port Volume Velocity")
        if _port_series(result):
            st.altair_chart(_plot_ports(result), width="stretch", key=f"ports_chart_{chart_sig}")
        else:
            st.caption("Port pens off.")

    if derived is not None:
        d1, d2, d3, d4, d5 = st.columns(5)
        d1.metric("Qes", f"{derived.qes:.3f}")
        d2.metric("Bl", f"{derived.bl_tm:.2f} T m")
        d3.metric("Mms", f"{derived.mms_kg * 1000.0:.2f} g")
        d4.metric("Cms", f"{derived.cms_m_per_n * 1000.0:.3f} mm/N")
        d5.metric("Sd", f"{derived.sd_m2 * 10000.0:.1f} cm2")

    st.download_button(
        "Download response CSV",
        _csv_bytes(result),
        "load_forge_response.csv",
        "text/csv",
        use_container_width=True,
    )

except Exception as exc:
    logger.exception("Simulation failed")
    st.error(f"Simulation failed: {exc}")
