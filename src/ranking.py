"""
Candidate-ranking rows for the `Find a driver` workspace.

Pure functions importable by worker processes: each row simulates one preset
within the requested maximum enclosure volume and reports the metrics shown by
the ranking table.
"""

from __future__ import annotations

import os

import numpy as np

try:
    from . import engine, presets
except ImportError:  # top-level import with src/ on sys.path (ui_app)
    import engine
    import presets

SPARKLINE_POINTS = 48
SPARKLINE_FLOOR_DB = -30.0


def response_sparkline(
    spl_total_db,
    points: int = SPARKLINE_POINTS,
    floor_db: float = SPARKLINE_FLOOR_DB,
) -> list[float]:
    """Downsample the total response to a peak-relative sparkline in dB."""
    spl = np.asarray(spl_total_db, dtype=float)
    finite = spl[np.isfinite(spl)]
    if not finite.size:
        return []
    rel = spl - float(np.max(finite))
    idx = np.linspace(0, len(rel) - 1, min(int(points), len(rel))).astype(int)
    return [
        float(np.clip(value, floor_db, 0.0)) if np.isfinite(value) else float(floor_db)
        for value in rel[idx]
    ]


def rank_sort_value(value: float) -> float:
    return float(value) if np.isfinite(float(value)) else float("inf")


def sort_ranked_rows(rows: list[dict]) -> list[dict]:
    """Deepest F3 first, then F6/F10 and the loudest peak as tie-breakers."""
    rows.sort(key=lambda row: (
        rank_sort_value(row["F3 Hz"]),
        rank_sort_value(row["F6 Hz"]),
        rank_sort_value(row["F10 Hz"]),
        -float(row["Peak dB"]) if np.isfinite(float(row["Peak dB"])) else 0.0,
    ))
    return rows


def rank_preset_row(
    name: str,
    load_type: str,
    max_volume_l: float,
    voltage_v: float,
    f_min_hz: float,
    f_max_hz: float,
    points: int,
    goals: engine.OptimizationGoals | None = None,
) -> dict | None:
    """Build one ranking-table row; ``None`` when the preset is unusable."""
    if load_type in ("Suspension pneumatic", "Acoustic suspension"):
        load_type = "Sealed"
    freq = np.geomspace(float(f_min_hz), float(f_max_hz), int(points))
    try:
        ts = presets.get_driver_preset(name)
        if load_type not in ("Sealed", "Infinite baffle") and ts.xmax_mm <= 0:
            return None
        info = presets.driver_preset_info(name)
        driver_class = engine.classify_driver_bandwidth(ts).driver_class
        ripple_db = float("nan")
        if goals is not None and load_type != "Infinite baffle":
            # Finder volume is a ceiling: each driver keeps the best alignment
            # found at or below it instead of being projected onto the ceiling.
            batch_goals = engine.OptimizationGoals(
                objective=goals.objective,
                max_total_volume_l=float(max_volume_l),
                target_f3_hz=goals.target_f3_hz,
                max_ripple_db=goals.max_ripple_db,
                max_excursion_ratio=goals.max_excursion_ratio,
                max_group_delay_ms=goals.max_group_delay_ms,
                min_spl_db=goals.min_spl_db,
            )
            optimized = engine.optimize_alignment(
                ts,
                batch_goals,
                load_type=load_type,
                voltage_v=float(voltage_v),
                max_evaluations=24 if os.getenv("K_SERVICE") else 140,
            )
            box = optimized.box
            ripple_db = float(optimized.ripple_db)
        elif load_type == "Bass reflex":
            alignment = engine.suggest_reflex_alignment(ts)
            box = engine.ReflexBox(
                vb_l=min(float(alignment.vb_l), float(max_volume_l)),
                fb_hz=alignment.fb_hz,
            )
        elif load_type == "Passive radiator":
            alignment = engine.suggest_pr_alignment(ts)
            box = alignment  # PassiveRadiatorBox already has vb_l set
            box = engine.PassiveRadiatorBox(
                vb_l=min(float(box.vb_l), float(max_volume_l)),
                pr_sp_cm2=box.pr_sp_cm2,
                pr_fp_hz=box.pr_fp_hz,
                pr_qmp=box.pr_qmp,
                pr_mmp_g=box.pr_mmp_g,
                pr_xmax_mm=box.pr_xmax_mm,
            )
        elif load_type == "Sealed":
            alignment = engine.suggest_sealed_alignment(ts)
            box = engine.SealedBox(
                vb_l=min(float(alignment.vb_l), float(max_volume_l)))
        elif load_type == "Bandpass 4th order":
            start = engine.suggest_bandpass4_alignment(ts)
            starter_volume_l = float(start.vs_l + start.vp_l)
            box = engine.design_space_box(
                ts, load_type, min(starter_volume_l, float(max_volume_l)), start.fp_hz)
        elif load_type == "Bandpass 6th order":
            start = engine.suggest_bandpass6_alignment(ts)
            starter_volume_l = float(start.vr_l + start.vp_l)
            box = engine.design_space_box(
                ts, load_type, min(starter_volume_l, float(max_volume_l)), start.fp_hz)
        elif load_type == "Infinite baffle":
            box = None
        else:
            start = engine.suggest_alignment(ts)
            starter_volume_l = float(start.vh_l + start.vl_l)
            box = engine.design_space_box(
                ts, "DCCAV", min(starter_volume_l, float(max_volume_l)),
                start.fl_hz,
            )
        if load_type == "Bass reflex":
            result = engine.simulate_reflex(ts, box, freq, float(voltage_v))
            box_values = {
                "Vb L": box.vb_l,
                "Fb Hz": box.fb_hz,
                "Vh L": np.nan,
                "fh Hz": np.nan,
                "Vl L": np.nan,
                "fl Hz": np.nan,
                "Fc Hz": np.nan,
                "Qtc": np.nan,
                "Vs L": np.nan,
                "Vp L": np.nan,
                "Fp Hz": np.nan,
                "Vr L": np.nan,
                "Fr Hz": np.nan,
            }
        elif load_type == "Passive radiator":
            result = engine.simulate_passive_radiator(ts, box, freq, float(voltage_v))
            box_values = {
                "Vb L": box.vb_l,
                "Fb Hz": box.pr_fp_hz * np.sqrt(1 + (box.pr_sp_cm2/10000)**2 / (engine.RHO_AIR * engine.SPEED_OF_SOUND**2 * (box.vb_l/1000)) * (1/((2*np.pi*box.pr_fp_hz)**2 * box.pr_mmp_g/1000) * (box.pr_sp_cm2/10000)**2)),
                "Vh L": np.nan,
                "fh Hz": np.nan,
                "Vl L": np.nan,
                "fl Hz": np.nan,
                "Fc Hz": np.nan,
                "Qtc": np.nan,
                "Vs L": np.nan,
                "Vp L": np.nan,
                "Fp Hz": np.nan,
                "Vr L": np.nan,
                "Fr Hz": np.nan,
            }
        elif load_type == "Sealed":
            result = engine.simulate_sealed(ts, box, freq, float(voltage_v))
            fc_hz, qtc = engine.sealed_system_metrics(ts, box)
            box_values = {
                "Vb L": box.vb_l,
                "Fb Hz": np.nan,
                "Vh L": np.nan,
                "fh Hz": np.nan,
                "Vl L": np.nan,
                "fl Hz": np.nan,
                "Fc Hz": fc_hz,
                "Qtc": qtc,
                "Vs L": np.nan,
                "Vp L": np.nan,
                "Fp Hz": np.nan,
                "Vr L": np.nan,
                "Fr Hz": np.nan,
            }
        elif load_type == "Bandpass 4th order":
            result = engine.simulate_bandpass4(ts, box, freq, float(voltage_v))
            box_values = {
                "Vb L": np.nan,
                "Fb Hz": np.nan,
                "Vh L": np.nan,
                "fh Hz": np.nan,
                "Vl L": np.nan,
                "fl Hz": np.nan,
                "Fc Hz": np.nan,
                "Qtc": np.nan,
                "Vs L": box.vs_l,
                "Vp L": box.vp_l,
                "Fp Hz": box.fp_hz,
                "Vr L": np.nan,
                "Fr Hz": np.nan,
            }
        elif load_type == "Bandpass 6th order":
            result = engine.simulate_bandpass6(ts, box, freq, float(voltage_v))
            box_values = {
                "Vb L": np.nan,
                "Fb Hz": np.nan,
                "Vh L": np.nan,
                "fh Hz": np.nan,
                "Vl L": np.nan,
                "fl Hz": np.nan,
                "Fc Hz": np.nan,
                "Qtc": np.nan,
                "Vs L": np.nan,
                "Vp L": box.vp_l,
                "Fp Hz": box.fp_hz,
                "Vr L": box.vr_l,
                "Fr Hz": box.fr_hz,
            }
        elif load_type == "Infinite baffle":
            result = engine.simulate_infinite_baffle(ts, freq, float(voltage_v))
            box_values = {
                "Vb L": np.nan,
                "Fb Hz": np.nan,
                "Vh L": np.nan,
                "fh Hz": np.nan,
                "Vl L": np.nan,
                "fl Hz": np.nan,
                "Fc Hz": ts.fs_hz,
                "Qtc": ts.qts,
                "Vs L": np.nan,
                "Vp L": np.nan,
                "Fp Hz": np.nan,
                "Vr L": np.nan,
                "Fr Hz": np.nan,
            }
        else:
            result = engine.simulate(ts, box, freq, float(voltage_v))
            box_values = {
                "Vb L": np.nan,
                "Fb Hz": np.nan,
                "Vh L": box.vh_l,
                "fh Hz": box.fh_hz,
                "Vl L": box.vl_l,
                "fl Hz": box.fl_hz,
                "Fc Hz": np.nan,
                "Qtc": np.nan,
                "Vs L": np.nan,
                "Vp L": np.nan,
                "Fp Hz": np.nan,
                "Vr L": np.nan,
                "Fr Hz": np.nan,
            }
        thresholds = engine.response_threshold_frequencies(result)
        return {
            "Driver": name,
            "Source": info.source,
            "Brand": info.brand or "Other",
            "Class": driver_class,
            "Size in": info.size_in if info.size_in is not None else np.nan,
            "Price": info.price if info.price is not None else np.nan,
            "Currency": info.currency,
            "Buy": info.url or "",
            "Mms g": ts.mms_g if ts.mms_g is not None else np.nan,
            "Le10k mH": ts.le10k_mh if ts.le10k_mh is not None else np.nan,
            "F3 Hz": thresholds[3],
            "F6 Hz": thresholds[6],
            "F10 Hz": thresholds[10],
            "Peak dB": float(np.nanmax(result.spl_total_db)),
            "Ripple dB": ripple_db,
            "Max excursion mm": float(np.nanmax(result.excursion_mm)),
            "Min ohm": float(np.nanmin(result.impedance_ohm)),
            "Response": response_sparkline(result.spl_total_db),
            "_load_type": load_type,
            **box_values,
        }
    except Exception:
        return None
