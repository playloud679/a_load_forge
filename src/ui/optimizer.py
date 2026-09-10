"""Alignment/box optimizer helpers and alternative renderers."""

from __future__ import annotations

import numpy as np
import streamlit as st

import acoustics as _acoustics

from . import constants as _constants
from . import finder as _finder
from . import runtime as _runtime
from . import state as _state


def _design_objective_label() -> str:
    strategy = str(st.session_state.get("box_strategy", "Max extension"))
    if strategy in _constants._OPT_OBJECTIVE_LABELS:
        return strategy
    fallback = str(st.session_state.get("opt_objective", "Max extension"))
    return fallback if fallback in _constants._OPT_OBJECTIVE_LABELS else "Max extension"

def _optimizer_goals_from_state() -> _acoustics.OptimizationGoals:
    return _acoustics.OptimizationGoals(
        objective=_constants._OPT_OBJECTIVE_LABELS[_design_objective_label()],
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
        and _state._box_strategy_is_auto()
    )

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
    if isinstance(box, _acoustics.ReflexBox) and _state._reflex_uses_passive_radiator():
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

def _optimizer_context_box():
    """Return the active load type and the box currently shown in the sidebar."""
    load_type = st.session_state.get("load_type", "DCCAV")
    if load_type == "Bass reflex":
        return load_type, _state._reflex_box_from_state()
    if load_type == "Sealed":
        return load_type, _state._sealed_box_from_state()
    if load_type == "Bandpass 4th order":
        return load_type, _state._bandpass4_box_from_state()
    if load_type == "Bandpass 6th order":
        return load_type, _state._bandpass6_box_from_state()
    if load_type == "Bandpass 8th order":
        return load_type, _state._bandpass8_box_from_state()
    if load_type == "DCCAV":
        return load_type, _state._box_from_state()
    return load_type, None

def _current_optimizer_summary(driver: _acoustics.DriverTS) -> str | None:
    load_type, box = _optimizer_context_box()
    if box is None:
        return None
    context = _optimizer_result_context(driver, load_type, box)
    if st.session_state.get("_opt_last_context") != context:
        return None
    return st.session_state.get("opt_last_summary")

def _current_optimizer_alternatives(driver: _acoustics.DriverTS) -> tuple:
    load_type, box = _optimizer_context_box()
    if box is None:
        return ()
    context = _optimizer_result_context(driver, load_type, box)
    if st.session_state.get("_opt_last_context") != context:
        return ()
    return tuple(st.session_state.get("_opt_last_alternatives") or ())

def _render_optimizer_alternatives(driver: _acoustics.DriverTS) -> None:
    """Offer the runner-up boxes from the last optimizer run with one-click apply."""
    alternatives = _current_optimizer_alternatives(driver)
    if not alternatives:
        return
    with st.expander("Explore alternatives"):
        st.caption(
            "Runner-up buildable alignments from the same deterministic search. "
            "Scores are relative to the active goal; physical metrics are shown "
            "for every candidate."
        )
        for index, alternative in enumerate(alternatives):
            st.markdown(
                f"**Alternative {index + 1}** · score {alternative.score:.1f} · "
                f"F3 {alternative.f3_hz:.1f} Hz · "
                f"Vtot {alternative.total_volume_l:.1f} L · "
                f"ripple {alternative.ripple_db:.2f} dB · "
                f"excursion {alternative.excursion_ratio:.2f}× Xmax"
            )
            if st.button(
                "Apply this box",
                key=f"opt_alt_apply_{index}",
                width="stretch",
            ):
                load_type = st.session_state.get("load_type", "DCCAV")
                _apply_optimized_box(alternative.box)
                _apply_optimized_port_geometry(driver, alternative.box)
                st.session_state["opt_last_summary"] = (
                    f"Applied alternative {index + 1}: "
                    f"F3 {alternative.f3_hz:.1f} Hz · "
                    f"Vtot {alternative.total_volume_l:.1f} L · "
                    f"score {alternative.score:.1f}"
                )
                st.session_state["_opt_last_context"] = _optimizer_result_context(
                    driver, load_type, alternative.box,
                )

def _run_box_optimizer(driver: _acoustics.DriverTS) -> _acoustics.OptimizedAlignment:
    load_type = st.session_state.get("load_type", "DCCAV")
    if load_type == "Bass reflex":
        template = _state._reflex_box_from_state()
    elif load_type == "Sealed":
        template = _state._sealed_box_from_state()
    elif load_type == "Bandpass 4th order":
        template = _state._bandpass4_box_from_state()
    elif load_type == "Bandpass 6th order":
        template = _state._bandpass6_box_from_state()
    elif load_type == "Bandpass 8th order":
        template = _state._bandpass8_box_from_state()
    elif load_type == "Infinite baffle":
        raise ValueError("Infinite baffle has no box to optimize")
    else:
        template = _state._box_from_state()
    optimized = _acoustics.optimize_alignment(
        driver,
        _optimizer_goals_from_state(),
        load_type=load_type,
        box_template=template,
        voltage_v=float(st.session_state.get("sim_voltage", 2.83)),
    )
    _apply_optimized_port_geometry(driver, optimized.box)
    st.session_state["opt_last_summary"] = _optimized_summary(optimized)
    st.session_state["_opt_last_alternatives"] = tuple(optimized.alternatives)
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
        _finder._apply_reflex_alignment(_acoustics.suggest_reflex_alignment(driver))
    elif load_type == "Sealed":
        _finder._apply_sealed_alignment(_acoustics.suggest_sealed_alignment(driver))
    elif load_type == "Bandpass 4th order":
        _finder._apply_bandpass4_alignment(_acoustics.suggest_bandpass4_alignment(driver))
    elif load_type == "Bandpass 6th order":
        _finder._apply_bandpass6_alignment(_acoustics.suggest_bandpass6_alignment(driver))
    elif load_type == "Bandpass 8th order":
        _finder._apply_bandpass8_alignment(_acoustics.suggest_bandpass8_alignment(driver))
    elif load_type == "DCCAV":
        _finder._apply_alignment(_acoustics.suggest_alignment(driver))

def _on_box_strategy_change() -> None:
    strategy = str(st.session_state.get("box_strategy", "Max extension"))
    previous = str(st.session_state.get("_previous_box_strategy", "Max extension"))
    load_type = str(st.session_state.get("load_type", "DCCAV"))
    _state._set_box_strategy_state(strategy)
    if previous == "Manual" and strategy in _constants._OPT_OBJECTIVE_LABELS:
        # Remember the user's hand-tuned box before the optimizer overwrites it.
        _state._snapshot_manual_box(load_type)
    elif previous in _constants._OPT_OBJECTIVE_LABELS and strategy == "Manual":
        # Returning to Manual: bring back the last hand-tuned values.
        _state._restore_manual_box(load_type)
    if strategy in _constants._OPT_OBJECTIVE_LABELS:
        try:
            driver = _state._driver_from_state()
            _apply_suggested_box_for(driver)
            _finder._mark_auto_alignment_synced(driver)
        except Exception:
            _runtime.logger.exception("Could not apply the selected box strategy")

def _use_manual_box_strategy() -> None:
    _state._set_box_strategy_state("Manual")

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
