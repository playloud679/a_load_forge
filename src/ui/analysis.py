"""Response/excursion/impedance/ports charts, design comparison and CSV export."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import uuid
from pathlib import Path

import altair as alt
import generate_afw_dccav as _afw_export
import numpy as np
import pandas as pd
import streamlit as st

import acoustics as _acoustics
import engine as _engine
import port_cad as _port_cad

from . import catalog as _catalog
from . import constants as _constants
from . import finder as _finder
from . import optimizer as _optimizer
from . import projects as _projects
from . import runtime as _runtime
from . import state as _state
from . import styles as _styles


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
        if key in {"plot_response_window_hz", "plot_response_reset_zoom", "box_design_sidebar_tab"}:
            continue
        try:
            json.dumps(value)
        except (TypeError, ValueError):
            continue
        data[key] = value
    payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha1(payload).hexdigest()[:12]

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
            or _constants._DESIGN_COMPARISON_TRACE_COLORS[
                index % len(_constants._DESIGN_COMPARISON_TRACE_COLORS)
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
                _constants._TRACE_COLORS.get(name, "#7cc7ff"),
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
        if load_type == "Bass reflex" and _state._reflex_uses_passive_radiator():
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
        if _state._reflex_uses_passive_radiator():
            return [("PR tuning", _acoustics.passive_radiator_effective_fp_hz(_state._pr_box_from_state()))]
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
        is_pr = load_type == "Bass reflex" and _state._reflex_uses_passive_radiator()
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
    auto_markers = set(st.session_state.get("cursor_auto_markers", _constants._AUTO_CURSOR_OPTIONS))
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
        color=design_color or _constants._TRACE_COLORS["Total"],
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
                titleColor=_constants._TRACE_COLORS.get("MIL", "#e0aaff"),
                labelColor=_constants._TRACE_COLORS.get("MIL", "#e0aaff")
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
                titleColor=_constants._TRACE_COLORS.get("MIL", "#e0aaff"),
                labelColor=_constants._TRACE_COLORS.get("MIL", "#e0aaff"),
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
        parameters = _state._json_safe(_state._collect_params())
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
            color=_constants._DESIGN_COMPARISON_TRACE_COLORS[0],
        )
        tabs = [{
            "id": original_id,
            "label": original_label,
            "color": _constants._DESIGN_COMPARISON_TRACE_COLORS[0],
            "driver_preset_name": str(st.session_state.get(
                "driver_preset_name", "Custom"
            )),
            "display_driver_name": str(st.session_state.get(
                "driver_preset_name", "Custom"
            )),
            "load_type": load_type,
            "visible": True,
            "parameters": _state._json_safe(_state._collect_params()),
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
    if len(tabs) >= _constants._MAX_COMPARISON_DESIGNS:
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
        "color": _constants._DESIGN_COMPARISON_TRACE_COLORS[
            len(tabs) % len(_constants._DESIGN_COMPARISON_TRACE_COLORS)
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
        "parameters": _state._json_safe(dict(source.get("parameters", {}))),
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
            or _constants._DESIGN_COMPARISON_TRACE_COLORS[
                index % len(_constants._DESIGN_COMPARISON_TRACE_COLORS)
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
    manufacturer, part_number = _catalog._driver_preset_identity_fields(preset_name)
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
    if len(parts) >= 3 and parts[2] in _constants._ALL_LOAD_TYPES:
        candidate = f"{parts[0]} {parts[1]}"
    elif len(parts) >= 2 and parts[0] in _constants._ALL_LOAD_TYPES:
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
    for name in _catalog._available_driver_preset_names():
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
        parameters = _state._collect_params()
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
        parameters = _state._collect_params()
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
            "color": _constants._DESIGN_COMPARISON_TRACE_COLORS[0],
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
                        disabled=len(tabs) >= _constants._MAX_COMPARISON_DESIGNS,
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
        _constants._MAX_PINNED_CHART_ROWS // max(1, len(visible_pins) * trace_budget),
    )
    for index, pinned in enumerate(pinned_responses):
        if not pinned.get("visible", True):
            continue
        frequencies = np.asarray(pinned.get("frequency_hz", []), dtype=float)
        trace_label = f"{index + 1} · {pinned.get('label', 'Pinned response')}"
        trace_color = str(
            pinned.get("color")
            or _constants._PIN_TRACE_COLORS[index % len(_constants._PIN_TRACE_COLORS)]
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
                if series_name in _constants._RESONATOR_RESPONSE_TRACES:
                    selected = selected or bool(
                        selected_traces & _constants._RESONATOR_RESPONSE_TRACES
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
                        _constants._PIN_TRACE_COLORS[index % len(_constants._PIN_TRACE_COLORS)],
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
        d_box = box if load_type == "DCCAV" else _finder._batch_dccav_box(ts, vtot)
        series["DCCAV"] = _acoustics.simulate(ts, d_box, freq, voltage_v, series_r_ohm).spl_total_db
    except Exception:
        _runtime.logger.exception("Comparison DCCAV simulation failed")
    try:
        bp_start = _acoustics.suggest_bandpass4_alignment(ts)
        bp_box = box if load_type == "Bandpass 4th order" else _acoustics.design_space_box(
            ts, "Bandpass 4th order", vtot, bp_start.fp_hz)
        series["Bandpass 4th order"] = _acoustics.simulate_bandpass4(
            ts, bp_box, freq, voltage_v, series_r_ohm).spl_total_db
    except Exception:
        _runtime.logger.exception("Comparison bandpass simulation failed")
    try:
        bp6_start = _acoustics.suggest_bandpass6_alignment(ts)
        bp6_box = box if load_type == "Bandpass 6th order" else _acoustics.design_space_box(
            ts, "Bandpass 6th order", vtot, bp6_start.fp_hz)
        series["Bandpass 6th order"] = _acoustics.simulate_bandpass6(
            ts, bp6_box, freq, voltage_v, series_r_ohm).spl_total_db
    except Exception:
        _runtime.logger.exception("Comparison bandpass6 simulation failed")
    try:
        bp8_start = _acoustics.suggest_bandpass8_alignment(ts)
        bp8_box = box if load_type == "Bandpass 8th order" else _acoustics.design_space_box(
            ts, "Bandpass 8th order", vtot, bp8_start.f3_hz)
        series["Bandpass 8th order"] = _acoustics.simulate_bandpass8(
            ts, bp8_box, freq, voltage_v, series_r_ohm).spl_total_db
    except Exception:
        _runtime.logger.exception("Comparison bandpass8 simulation failed")
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
        _runtime.logger.exception("Comparison reflex simulation failed")
    try:
        s_box = box if load_type == "Sealed" else _acoustics.SealedBox(vb_l=vtot)
        series["Sealed"] = _acoustics.simulate_sealed(
            ts, s_box, freq, voltage_v, series_r_ohm).spl_total_db
    except Exception:
        _runtime.logger.exception("Comparison sealed simulation failed")
    try:
        series["Infinite baffle"] = _acoustics.simulate_infinite_baffle(
            ts, freq, voltage_v, series_r_ohm).spl_total_db
    except Exception:
        _runtime.logger.exception("Comparison infinite-baffle simulation failed")
    return vtot, series

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
        active_style = _styles._focused_port_flare_style()
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
            for (_, label, _, _), limit in zip(guideline_specs, g_limits, strict=False)
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
        color = _constants._DESIGN_COMPARISON_TRACE_COLORS[
            index % len(_constants._DESIGN_COMPARISON_TRACE_COLORS)
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
        previous_parameters = _state._json_safe(_state._collect_params())
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
    _projects._apply_loaded_params(dict(requested.get("parameters", {})))
    stable_requested_preset = str(requested.get("driver_preset_name", ""))
    if stable_requested_preset:
        st.session_state["driver_preset_name"] = stable_requested_preset
    # A tab already contains its saved enclosure. Mark that exact driver/load
    # state as synchronized so selecting or deleting a sibling never launches
    # the optimizer again and overwrites the stored design.
    _finder._mark_auto_alignment_synced()
    st.session_state["design_comparison_loaded_id"] = requested_id
    st.session_state["workspace_mode"] = "Box Design"
    st.session_state["design_comparison_tabs"] = tabs

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
                if load_type == "Bass reflex" and _state._reflex_uses_passive_radiator()
                else load_type
            )
            band = _tolerance_band_cached(
                current_ts, tolerance_load_type, box, freq,
                sim_voltage, sim_series_r, tolerance)
        except Exception:
            _runtime.logger.exception("Tolerance band computation failed")

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

        # Keep one fully serialized chart per session. Unrelated clicks reuse
        # it; physics, overlays, visibility, markers and zoom all invalidate it.
        _pinned_responses()  # Normalize legacy/empty pins before hashing.
        chart_key = (
            Path(__file__).stat().st_mtime_ns,
            _simulation_engine_revision(), repr(current_ts), repr(box), load_type,
            _chart_signature(), tuple(frequency_window), tuple(selected_traces),
            ripple_max_freq,
            st.session_state.get("standalone_design_visible", True),
            st.session_state.get("design_comparison_active_id"),
            tuple(
                (tab.get("id"), tab.get("label"), tab.get("color"),
                 tab.get("visible", True), _snapshot_revision(tab["snapshot"]))
                for tab in _design_comparison_tabs()
                if isinstance(tab.get("snapshot"), dict)
            ),
        )
        cached_chart = st.session_state.get("_response_spec_cache")
        if cached_chart is None or cached_chart[0] != chart_key:
            spec = _plot_response(
                result, cursor_rows, compare_series, band,
                frequency_window=frequency_window,
                show_legend=False,
                default_visible=selected_traces,
            ).to_dict()
            cached_chart = (chart_key, spec)
            st.session_state["_response_spec_cache"] = cached_chart
        st.vega_lite_chart(
            spec=cached_chart[1],
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
                len(pinned_state) >= _constants._MAX_PINNED_RESPONSES
                or comparison_mode
            ),
            help=(
                f"Keep up to {_constants._MAX_PINNED_RESPONSES} response traces while "
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
                on_click=_state._reset_response_zoom,
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
                on_click=_state._reset_response_zoom,
                args=(full_window,),
            )
    else:
        with ctrl_cols[5]:
            st.button(
                "Reset zoom",
                key="plot_response_reset_zoom",
                width="stretch",
                disabled=tuple(st.session_state.get("plot_response_window_hz", full_window)) == full_window,
                on_click=_state._reset_response_zoom,
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
        resonator = "passive radiator" if _state._reflex_uses_passive_radiator() else "vent"
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
            f"{_constants._MAX_COMPARISON_DESIGNS} tabs · inactive designs use dashed "
            "colored traces."
        )
    elif pinned_state:
        visible_pin_count = sum(
            bool(pin.get("visible", True)) for pin in pinned_state)
        st.caption(
            f"Pinned responses: {len(pinned_state)}/{_constants._MAX_PINNED_RESPONSES} · "
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
        p_style = _state._clean_style_str(st.session_state.get(f"flared_style_{p_name}", st.session_state.get("flared_calc_style", "both")), "both")
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
    active_style = _styles._focused_port_flare_style()
    flare_limit_ms = _acoustics.port_chuffing_limit_ms(active_style)
    port_plot_mode_raw = st.session_state.get("port_plot_display_mode", "air_velocity_mol")
    port_plot_mode = _state._clean_style_str(port_plot_mode_raw, "air_velocity_mol")

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
                status_text = "Air Flow Safe"
                headroom = flare_limit_ms - max_peak_mol
                status_delta = f"+{headroom:.1f} m/s margin"
                delta_color = "normal"
            elif max_peak_mol <= flare_limit_ms:
                status_text = "Compression Risk"
                headroom = flare_limit_ms - max_peak_mol
                status_delta = f"Only {headroom:.1f} m/s margin"
                delta_color = "off"
            else:
                status_text = "High Chuffing Risk"
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
            st.markdown("##### Active Duct Focus & Auto-Optimizer")
            
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
                st.info("**Internal Inter-Chamber Duct**: Couples internal cavities (k=1.64). Flanged on both ends inside cabinet.")
            elif "External" in target_duct or "Vent" in target_duct:
                st.info("**External Radiating Vent**: Radiates acoustic energy into listening room (k=1.43). Critical for chuffing prevention.")
            elif target_duct.startswith("All"):
                st.caption("**Configuring all ducts simultaneously**: Changes to flare profile, radius and auto-optimization will apply across all active ducts.")

            # Dynamic session key mapping
            if target_duct.startswith("All"):
                style_key = "flared_calc_style"
                rad_key = "flared_calc_radius_cm"
                curr_style = _state._clean_style_str(st.session_state.get(style_key, "both"), "both")
                curr_rad = float(st.session_state.get(rad_key, 2.5))
            else:
                style_key = f"flared_style_{target_duct}"
                rad_key = f"flared_radius_{target_duct}"
                curr_style = _state._clean_style_str(st.session_state.get(style_key, st.session_state.get("flared_calc_style", "both")), "both")
                curr_rad = float(st.session_state.get(rad_key, st.session_state.get("flared_calc_radius_cm", 2.5)))

            style_options = ["both", "hourglass", "one", "none"]
            style_labels = {
                "both": "Double flared (Aeroport)",
                "hourglass": "Hourglass continuous (Clessidra)",
                "one": "Single flared (Outer mouth)",
                "none": "Straight pipe (Cylindrical)",
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
            flare_style = _state._clean_style_str(flare_style_raw, "both")

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
                "studio_mol": "Studio / Hi-Fi (Zero chuffing at MOL)",
                "balanced_pro": "Balanced / Pro (AES guideline)",
                "compact": "Compact Box (Min duct volume)",
            }
            curr_pol = _state._clean_style_str(st.session_state.get("port_auto_policy", "studio_mol"), "studio_mol")
            p_idx = policy_options.index(curr_pol) if curr_pol in policy_options else 0

            opt_policy_raw = st.radio(
                "Auto-sizing directive / policy",
                policy_options,
                index=p_idx,
                format_func=lambda x: policy_labels.get(x, str(x)),
                key="port_auto_policy",
                on_change=_state._mark_session_flag,
                args=("_port_optimizer_policy_changed",),
            )
            opt_policy = _state._clean_style_str(opt_policy_raw, "studio_mol")
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

            btn_label = f"Auto-optimize {duct_focus_label}" if not target_duct.startswith("All") else "Auto-optimize All Ducts"
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
                    st.warning(feedback_text)
                else:
                    st.success(feedback_text)

            if should_run_opt:
                st.session_state["_last_opt_state"] = current_opt_state
                voltage_v = float(st.session_state.get("sim_voltage", 2.83))
                optimized_results = []

                def _opt_single(p_name, vol, f_hz, end_c, u_vel, p_slot, key_name):
                    p_st = _state._clean_style_str(
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
                    st.toast(f"Vent Auto-Optimized: Ø {opt_res['diameter_cm']:.1f} cm ({opt_res['status_note']})")
                elif load_type == "DCCAV":
                    if target_duct.startswith("All") or "Upper" in target_duct:
                        o_up = _opt_single("Upper port (Internal inter-chamber)", box.vh_l, box.fh_hz, 1.64, result.port_h_velocity, "upper", "box_port_d_h_cm")
                        if not target_duct.startswith("All"):
                            st.toast(f"Upper Port (Internal) Optimized: Ø {o_up['diameter_cm']:.1f} cm")
                    if target_duct.startswith("All") or "Lower" in target_duct:
                        o_low = _opt_single("Lower port (External radiating)", box.vl_l, box.fl_hz, 1.43, result.port_l_velocity, "lower", "box_port_d_l_cm")
                        if not target_duct.startswith("All"):
                            st.toast(f"Lower Port (External) Optimized: Ø {o_low['diameter_cm']:.1f} cm")
                    if target_duct.startswith("All"):
                        st.toast(f"DCCAV All Ports Optimized: Upper Ø {o_up['diameter_cm']:.1f} cm, Lower Ø {o_low['diameter_cm']:.1f} cm")
                elif load_type == "Bandpass 4th order":
                    opt_bp4 = _opt_single("Front vent (External)", box.vp_l, box.fp_hz, 1.43, result.port_l_velocity, "lower", "bandpass4_port_d_cm")
                    st.toast(f"Front Vent Optimized: Ø {opt_bp4['diameter_cm']:.1f} cm")
                elif load_type == "Bandpass 6th order":
                    if target_duct.startswith("All") or "Rear" in target_duct:
                        o_r = _opt_single("Rear vent (External)", box.vr_l, box.fr_hz, 1.43, result.port_h_velocity, "upper", "bandpass6_port_d_r_cm")
                        if not target_duct.startswith("All"):
                            st.toast(f"Rear Vent Optimized: Ø {o_r['diameter_cm']:.1f} cm")
                    if target_duct.startswith("All") or "Front" in target_duct:
                        o_p = _opt_single("Front vent (External)", box.vp_l, box.fp_hz, 1.43, result.port_l_velocity, "lower", "bandpass6_port_d_p_cm")
                        if not target_duct.startswith("All"):
                            st.toast(f"Front Vent Optimized: Ø {o_p['diameter_cm']:.1f} cm")
                    if target_duct.startswith("All"):
                        st.toast(f"BP6 All Vents Optimized: Rear Ø {o_r['diameter_cm']:.1f} cm, Front Ø {o_p['diameter_cm']:.1f} cm")
                elif load_type == "Bandpass 8th order":
                    if target_duct.startswith("All") or "Port 1" in target_duct:
                        o1 = _opt_single("Port 1 (Internal -> C3)", box.v1_l, box.f1_hz, 1.43, result.port_l_velocity, "lower", "bp8_dp1_cm")
                        if not target_duct.startswith("All"):
                            st.toast(f"Port 1 (Internal) Optimized: Ø {o1['diameter_cm']:.1f} cm")
                    if target_duct.startswith("All") or "Port 2" in target_duct:
                        o2 = _opt_single("Port 2 (Internal -> C3)", box.v2_l, box.f2_hz, 1.43, result.port_l_velocity, "lower", "bp8_dp2_cm")
                        if not target_duct.startswith("All"):
                            st.toast(f"Port 2 (Internal) Optimized: Ø {o2['diameter_cm']:.1f} cm")
                    if target_duct.startswith("All") or "Port 3" in target_duct:
                        o3 = _opt_single("Port 3 (External radiating)", box.v3_l, box.f3_hz, 1.43, result.port_h_velocity, "upper", "bp8_dp3_cm")
                        if not target_duct.startswith("All"):
                            st.toast(f"Port 3 (External) Optimized: Ø {o3['diameter_cm']:.1f} cm")
                    if target_duct.startswith("All"):
                        st.toast("BP8 All Ports Optimized")
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
                # The port geometry rows are rebuilt by the full script run, so
                # this action needs an app-scope rerun even though it sits in a
                # fragment; pin/zoom actions can stay fragment-scoped.
                st.rerun(scope="app")
            elif last_opt_state is None:
                st.session_state["_last_opt_state"] = current_opt_state

        # Card B: Manual Duct Dimensions
        with st.container(border=True):
            st.markdown("##### Duct Diameters & Chamber Ports")
            if load_type == "DCCAV":
                p1, p2 = st.columns(2)
                with p1:
                    st.number_input(
                        "Upper port Ø (cm) · Internal", min_value=0.0, max_value=60.0,
                        step=0.5, key="box_port_d_h_cm", help="Internal inter-chamber port (flanged both ends, k=1.64)")
                with p2:
                    st.number_input(
                        "Lower port Ø (cm) · External", min_value=0.0, max_value=60.0,
                        step=0.5, key="box_port_d_l_cm", help="External radiating port (flanged one end, k=1.43)")
                st.caption(
                    "Upper port connects the two internal cavities (k=1.64); "
                    "Lower port exhausts outside the enclosure (k=1.43)."
                )
            elif load_type == "Bandpass 4th order":
                st.number_input(
                    "Front vent diameter (cm) · External", min_value=0.0,
                    max_value=60.0, step=0.5, key="bandpass4_port_d_cm")
                st.caption("Front-chamber vent radiating externally (one flanged, one free end, k=1.43).")
            elif load_type == "Bandpass 6th order":
                p1, p2 = st.columns(2)
                with p1:
                    st.number_input(
                        "Rear vent Ø (cm) · External", min_value=0.0,
                        max_value=60.0, step=0.5, key="bandpass6_port_d_r_cm")
                with p2:
                    st.number_input(
                        "Front vent Ø (cm) · External", min_value=0.0,
                        max_value=60.0, step=0.5, key="bandpass6_port_d_p_cm")
                st.caption("Rear and front vents radiating externally (k=1.43).")
            elif load_type == "Bandpass 8th order":
                p1, p2, p3 = st.columns(3)
                with p1:
                    st.number_input(
                        "Port 1 Ø (cm) · Internal", min_value=0.0,
                        max_value=60.0, step=0.5, key="bp8_dp1_cm")
                with p2:
                    st.number_input(
                        "Port 2 Ø (cm) · Internal", min_value=0.0,
                        max_value=60.0, step=0.5, key="bp8_dp2_cm")
                with p3:
                    st.number_input(
                        "Port 3 Ø (cm) · External", min_value=0.0,
                        max_value=60.0, step=0.5, key="bp8_dp3_cm")
                st.caption("Port 1 & 2 exhaust internally into Chamber 3; Port 3 radiates externally.")
            elif load_type == "Bass reflex" and not passive_radiator:
                st.number_input(
                    "Vent diameter (cm) · External", min_value=0.0,
                    max_value=60.0, step=0.5, key="reflex_port_d_cm")
                st.caption("Conventional enclosure vent (one flanged, one free end, k=1.43).")
            elif passive_radiator:
                st.caption("The passive radiator is sized in the sidebar with area, mass and suspension.")

        # Card C: Chart Display Controls
        with st.container(border=True):
            st.markdown("##### Chart Pens & Display Metric")
            plot_options = ["air_velocity_mol", "air_velocity_sim", "volume_velocity"]
            plot_labels = {
                "air_velocity_mol": "Air velocity at MOL (m/s)",
                "air_velocity_sim": "Air velocity at drive level (m/s)",
                "volume_velocity": "Volume velocity (m³/s)",
            }
            curr_pm = _state._clean_style_str(st.session_state.get("port_plot_display_mode", "air_velocity_mol"), "air_velocity_mol")
            pm_idx = plot_options.index(curr_pm) if curr_pm in plot_options else 0
            port_plot_mode_raw = st.radio(
                "Port chart metric",
                plot_options,
                index=pm_idx,
                format_func=lambda opt: plot_labels.get(opt, str(opt)),
                horizontal=False,
                key="port_plot_display_mode",
            )
            port_plot_mode = _state._clean_style_str(port_plot_mode_raw, "air_velocity_mol")

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
            st.markdown(f"##### {chart_title}")
            if _port_series(result, mode=port_plot_mode):
                st.altair_chart(_plot_ports(result, mode=port_plot_mode), width="stretch", key=f"ports_chart_{chart_sig}")
            else:
                st.caption("Port pens off.")

        # Card E: Blueprint CAD Drawing & Physical Specs
        if passive_radiator:
            with st.container(border=True):
                st.markdown("##### Radiator Geometry & Motion")
                st.caption(
                    "Equivalent diaphragm diameter and simulated radiator motion "
                    f"at {float(st.session_state.get('sim_voltage', 2.83)):.2f} V and at MOL."
                )
                st.dataframe(
                    pd.DataFrame(port_geometry_rows)[list(_constants._PORT_GEOMETRY_COLUMNS)],
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
                    st.markdown("##### Plausible Catalog PR Combos")
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
                    st.markdown("##### Duct Blueprint & Physical Cut Specs")
                    
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
                                on_change=_state._persist_widget_selection,
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
                    sel_p_style = _state._clean_style_str(st.session_state.get(f"flared_style_{sel_p_name}", st.session_state.get("flared_calc_style", "both")), "both")
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
                    with st.expander(f"3D CAD & STL Mesh Generator for {sel_row['Port']} (3D Printing & CNC)", expanded=True):
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
                            split_options = list(_constants._STL_SPLIT_LABELS)
                            default_split = (
                                "half" if sel_p_style == "hourglass" else "full"
                            )
                            split_key = f"stl_split_{sel_p_name}"
                            # Older sessions stored the human-readable label.
                            # Canonical slugs make the visible selection exactly
                            # the value passed to mesh generation and download.
                            normalized_split = _state._normalize_stl_split_mode(
                                st.session_state.get(split_key, default_split),
                                default_split,
                            )
                            if st.session_state.get(split_key) != normalized_split:
                                st.session_state[split_key] = normalized_split
                            split_mode_code = st.selectbox(
                                "Split Mode",
                                split_options,
                                format_func=lambda slug: _constants._STL_SPLIT_LABELS[slug],
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
                            label=f"Download Watertight 3D Mesh ({file_name_stl} · {len(stl_bytes)/1024:.1f} KB)",
                            data=stl_bytes,
                            file_name=file_name_stl,
                            mime="model/stl",
                            key=f"download_stl_{clean_p_slug}_{sel_p_style}_{split_mode_code}",
                            use_container_width=True,
                            type="primary",
                        )
                        st.caption("Ready for direct import into Bambu Studio, OrcaSlicer, PrusaSlicer, Cura, or FreeCAD/Fusion 360.")
            else:
                st.info("No active port diameters configured (set Ø > 0 cm to view CAD blueprint).")

    # 3. Full-width Cut Sheet & Manufacturing Table
    if not passive_radiator and valid_ports:
        with st.container(border=True):
            st.markdown("##### Manufacturing Cut Sheet & Port Specifications")
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

@st.fragment
def _render_design_analysis_tabs(
    current_ts,
    load_type,
    box,
    result,
    thresholds,
    freq,
    sim_voltage,
    sim_series_r,
    port_geometry_rows,
    is_pr,
    is_sealed,
    is_infinite_baffle,
    chart_sig,
) -> None:
    """Render the design analysis tabs.

    A tab change reruns only this fragment, so switching Response, Excursion,
    Impedance, Ports, Group Delay or Atlas keeps the main page scroll still.
    """
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
                if _optimizer._alignment_uses_optimizer() else 0.0
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
            _finder._render_atlas_tab(current_ts, load_type, box, sim_voltage)
