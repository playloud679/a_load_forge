"""
Load Forge — acoustic-load simulator.

Single-page Streamlit dashboard: T/S parameters and DCCAV box controls in the
sidebar, response plots and derived data in the main workspace.
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


_PARAM_PREFIXES = ("driver_", "box_", "reflex_", "loss_", "sim_")
_RESPONSE_TRACE_OPTIONS = ("Total", "Cone", "Lower port")
_PORT_TRACE_OPTIONS = ("Upper port", "Lower port")
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
            st.session_state[key] = value
            applied += 1
    return applied


def _chart_signature() -> str:
    prefixes = ("driver_", "box_", "reflex_", "loss_", "sim_", "plot_", "cursor_", "load_type")
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
    return _dccav.ReflexBox(
        vb_l=float(st.session_state["reflex_vb_l"]),
        fb_hz=float(st.session_state["reflex_fb_hz"]),
        q_abs=float(st.session_state["reflex_q_abs"]),
        q_leak=float(st.session_state["reflex_q_leak"]),
        q_port=float(st.session_state["reflex_q_port"]),
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
        if st.session_state.get("load_type", "DCCAV") == "Bass reflex":
            _apply_reflex_alignment(_dccav.suggest_reflex_alignment(driver))
        else:
            _apply_alignment(_dccav.suggest_alignment(driver))
        _mark_auto_alignment_synced(driver)
    except Exception:
        pass


def _auto_alignment_signature(driver: _dccav.DriverTS | None = None) -> tuple:
    driver = driver or _driver_from_state()
    return (
        st.session_state.get("load_type", "DCCAV"),
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
        if st.session_state.get("load_type", "DCCAV") == "Bass reflex":
            _apply_reflex_alignment(_dccav.suggest_reflex_alignment(driver))
        else:
            _apply_alignment(_dccav.suggest_alignment(driver))
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
            if st.session_state.get("load_type", "DCCAV") == "Bass reflex":
                _apply_reflex_alignment(_dccav.suggest_reflex_alignment(driver))
            else:
                _apply_alignment(_dccav.suggest_alignment(driver))
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
        rows.extend({
            "frequency_hz": float(freq),
            "series": name,
            "value": float(value),
        } for freq, value in zip(result.frequency_hz, values))
    return pd.DataFrame(rows)


def _line_chart(
    data: pd.DataFrame,
    y_title: str,
    *,
    height: int,
    legend: bool = True,
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
    return alt.Chart(data).mark_line(point=False).encode(
        x=alt.X(
            "frequency_hz:Q",
            title="Frequency (Hz)",
            scale=alt.Scale(type="log", nice=False),
            axis=alt.Axis(format="~g"),
        ),
        y=alt.Y("value:Q", title=y_title),
        color=color,
        tooltip=[
            alt.Tooltip("frequency_hz:Q", title="Hz", format=".2f"),
            alt.Tooltip("series:N", title="Trace"),
            alt.Tooltip("value:Q", title=y_title, format=".3f"),
        ],
    ).properties(height=height)


def _response_series(result: _dccav.SimulationResult) -> dict[str, np.ndarray]:
    series = {}
    if st.session_state.get("plot_response_total", True):
        series["Total"] = result.spl_total_db
    if st.session_state.get("plot_response_driver", True):
        series["Cone"] = result.spl_driver_db
    if st.session_state.get("plot_response_lower_port", True):
        label = "Vent" if st.session_state.get("load_type") == "Bass reflex" else "Lower port"
        series[label] = result.spl_port_db
    if st.session_state.get("plot_response_mol", False):
        series["MOL"] = result.mol_db
    return series


def _port_series(result: _dccav.SimulationResult) -> dict[str, np.ndarray]:
    series = {}
    if st.session_state.get("plot_port_upper", True) and st.session_state.get("load_type") != "Bass reflex":
        series["Upper port"] = result.port_h_velocity
    if st.session_state.get("plot_port_lower", True):
        label = "Vent" if st.session_state.get("load_type") == "Bass reflex" else "Lower port"
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
    _place_cursor_labels_above_response(result, rows)
    return rows


def _place_cursor_labels_above_response(result: _dccav.SimulationResult, rows: list[dict]) -> None:
    if not rows:
        return
    selected = _response_series(result)
    arrays = [
        np.asarray(values, dtype=float)
        for values in selected.values()
        if np.asarray(values, dtype=float).size
    ]
    finite_chunks = [values[np.isfinite(values)] for values in arrays]
    finite = np.concatenate(finite_chunks) if finite_chunks else np.array([])
    top_db = float(np.max(finite)) if finite.size else float(np.nanmax(result.spl_total_db))
    f_min = float(result.frequency_hz[0])
    f_max = float(result.frequency_hz[-1])
    label_x_hz = float(np.clip(f_min * 1.08, f_min, f_max))
    lane_gap_db = 6.0
    for lane, row in enumerate(rows):
        row["label_x_hz"] = label_x_hz
        row["label_y_db"] = top_db + 3.0 + lane_gap_db * (len(rows) - lane - 1)


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


def _cursor_layer(rows: list[dict]) -> alt.LayerChart | None:
    if not rows:
        return None
    data = pd.DataFrame(rows)
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
        baseline="bottom",
        dx=5,
        dy=-6,
        fontSize=18,
        fontWeight="bold",
    ).encode(
        x="label_x_hz:Q",
        y="label_y_db:Q",
        text="display_label:N",
        color=color,
    )
    return rules + labels


def _plot_response(result: _dccav.SimulationResult, cursor_rows: list[dict]) -> alt.Chart:
    series = _response_series(result)
    if not series:
        raise ValueError("No response traces selected")
    data = _series_frame(result, series)
    chart = _line_chart(data, "LF pressure estimate (dB)", height=520)
    cursors = _cursor_layer(cursor_rows)
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
_default("loss_q_abs_h", 15.0)
_default("loss_q_abs_l", 15.0)
_default("loss_q_leak_h", 1000.0)
_default("loss_q_leak_l", 1000.0)
_default("loss_q_port_h", 15.0)
_default("loss_q_port_l", 15.0)
_default("reflex_q_abs", 15.0)
_default("reflex_q_leak", 1000.0)
_default("reflex_q_port", 15.0)
_default("load_type", "DCCAV")
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

try:
    _seed_alignment = _dccav.suggest_alignment(_driver_from_state())
    _seed_reflex = _dccav.suggest_reflex_alignment(_driver_from_state())
except Exception:
    _seed_alignment = _dccav.DccavAlignment(3.1, 162.0, 6.25, 62.0, 51.5)
    _seed_reflex = _dccav.ReflexAlignment(11.52, 48.14)
_default("box_vh_l", float(_seed_alignment.vh_l))
_default("box_fh_hz", float(_seed_alignment.fh_hz))
_default("box_vl_l", float(_seed_alignment.vl_l))
_default("box_fl_hz", float(_seed_alignment.fl_hz))
_default("reflex_vb_l", float(_seed_reflex.vb_l))
_default("reflex_fb_hz", float(_seed_reflex.fb_hz))
_sync_auto_alignment_if_needed()


st.title("Load Forge")
st.caption(f"v{_VERSION} · DCCAV / bass-reflex acoustic-load simulator · T/S driven response model")

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
        ["DCCAV", "Bass reflex"],
        horizontal=True,
        key="load_type",
        on_change=_on_load_type_change,
    )
    preset_name = st.selectbox(
        "Driver preset",
        ["Custom", *_dccav.driver_preset_names()],
        index=0,
        key="driver_preset_name",
        on_change=_on_driver_preset_change,
    )
    st.checkbox("Auto-align box from T/S", key="sim_auto_align")
    if preset_name != "Custom":
        st.caption("Preset values are applied immediately.")

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
        derived = _dccav.complete_driver(current_ts)
        if st.session_state["load_type"] == "Bass reflex":
            st.subheader("Bass Reflex Alignment")
            st.caption(
                f"Suggested: Vb {current_reflex_alignment.vb_l:.2f} L / "
                f"Fb {current_reflex_alignment.fb_hz:.1f} Hz"
            )
            if st.button("Apply suggested reflex", use_container_width=True):
                _apply_reflex_alignment(current_reflex_alignment)
                st.rerun()
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
            if st.button("Apply suggested alignment", use_container_width=True):
                _apply_alignment(current_alignment)
                st.rerun()
    except Exception as exc:
        current_ts = None
        current_alignment = None
        current_reflex_alignment = None
        derived = None
        st.error(str(exc))

    if st.session_state["load_type"] == "Bass reflex":
        _box_number_with_nudge(
            "Vb box (L)", "reflex_vb_l", min_value=0.05, max_value=1000.0, step=0.01)
        _box_number_with_nudge(
            "Fb tuning (Hz)", "reflex_fb_hz", min_value=1.0, max_value=1000.0, step=0.1)
        with st.expander("Loss factors"):
            st.number_input("Qabs box", min_value=0.2, max_value=500.0, step=0.5, key="reflex_q_abs")
            st.number_input("Qleak box", min_value=1.0, max_value=10000.0, step=10.0, key="reflex_q_leak")
            st.number_input("Qport", min_value=0.2, max_value=500.0, step=0.5, key="reflex_q_port")
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
    is_reflex = st.session_state["load_type"] == "Bass reflex"
    chart_sig = _chart_signature()
    box = _reflex_box_from_state() if is_reflex else _box_from_state()
    freq = np.geomspace(
        float(st.session_state["sim_f_min"]),
        float(st.session_state["sim_f_max"]),
        int(st.session_state["sim_points"]),
    )
    if is_reflex:
        result = _dccav.simulate_reflex(current_ts, box, freq, float(st.session_state["sim_voltage"]))
    else:
        result = _dccav.simulate(current_ts, box, freq, float(st.session_state["sim_voltage"]))
    metrics = _dccav.response_metrics(result)
    thresholds = _dccav.response_threshold_frequencies(result)
    z_peak_freqs = _dccav.impedance_peak_frequencies(result)
    model_warnings = [] if is_reflex else (
        _dccav.alignment_diagnostics(current_ts, box)
        + _dccav.response_sanity_warnings(current_ts, box, thresholds)
    )
    if is_reflex and len(z_peak_freqs) < 2:
        model_warnings.append(
            "Bass reflex should show two impedance peaks in the simulated range; "
            "widen F min/F max or check Vb, Fb and loss factors."
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

    if is_reflex and current_reflex_alignment is not None:
        a1, a2, a3 = st.columns(3)
        a1.metric("Suggested Vb", f"{current_reflex_alignment.vb_l:.2f} L")
        a2.metric("Suggested Fb", f"{current_reflex_alignment.fb_hz:.1f} Hz")
        a3.metric("Eq sealed Fc", f"{_dccav.equivalent_sealed_fc_hz(current_ts, box):.1f} Hz")
    elif current_alignment is not None:
        a1, a2, a3, a4, a5, a6 = st.columns(6)
        a1.metric("Suggested Vh", f"{current_alignment.vh_l:.2f} L")
        a2.metric("Suggested fh", f"{current_alignment.fh_hz:.1f} Hz")
        a3.metric("Suggested Vl", f"{current_alignment.vl_l:.2f} L")
        a4.metric("Suggested fl", f"{current_alignment.fl_hz:.1f} Hz")
        a5.metric("Suggested Vtot", f"{current_alignment.vh_l + current_alignment.vl_l:.2f} L")
        a6.metric("Article F3", f"{current_alignment.f3_hz:.1f} Hz")

    st.subheader("Plot Tools")
    r1, r2, r3, r4, r5, r6, r7, r8, r9, r10 = st.columns(10)
    with r1:
        st.checkbox("Total", key="plot_response_total")
    with r2:
        st.checkbox("Cone", key="plot_response_driver")
    with r3:
        st.checkbox("Lower port", key="plot_response_lower_port")
    with r4:
        st.checkbox("MOL", key="plot_response_mol")
    with r5:
        st.checkbox("MIL", key="plot_show_mil")
    with r6:
        st.checkbox("Upper port", key="plot_port_upper")
    with r7:
        st.checkbox("Lower port V", key="plot_port_lower")
    with r8:
        st.checkbox("Exc.", key="plot_show_excursion")
    with r9:
        st.checkbox("Z", key="plot_show_impedance")
    with r10:
        st.checkbox("Ports", key="plot_show_ports")

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

    st.subheader("LF Load Response")
    if is_reflex:
        st.caption(
            "Bass-reflex total response is the vector sum of the exposed cone "
            "front radiation and the vent. The model is low-frequency only; "
            "it does not include baffle step, breakup, room gain or crossover behaviour."
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

    if st.session_state.get("plot_show_ports", True):
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
