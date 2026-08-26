"""
Candidate-ranking rows for the `Find a driver` workspace.

Pure functions importable by worker processes: each row simulates one preset
within the requested maximum enclosure volume and reports the metrics shown by
the ranking table.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

try:
    from . import engine, presets
except ImportError:  # top-level import with src/ on sys.path (ui_app)
    import engine  # type: ignore[no-redef]
    import presets  # type: ignore[no-redef]

SPARKLINE_POINTS = 48
SPARKLINE_FLOOR_DB = -30.0
FINDER_WORKER_PROTOCOL_REVISION = 2


@dataclass(frozen=True)
class RankingCandidate:
    """Compact driver data sent to Finder worker processes."""

    name: str
    ts: engine.DriverTS
    source: str
    brand: str
    size_in: float | None
    price: float | None
    currency: str
    url: str


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


def finder_worker_ready() -> tuple[int, int, int]:
    """Return PID plus ranking/engine revisions loaded by this worker."""
    return (
        os.getpid(),
        FINDER_WORKER_PROTOCOL_REVISION,
        engine.OPTIMIZER_ENGINE_REVISION,
    )


SEARCH_PROFILE_STANDARD = "Standard"
SEARCH_PROFILE_DEEP = "Deep"

SEARCH_PROFILES = {
    SEARCH_PROFILE_STANDARD: {
        "max_evaluations": 60,
        "coarse_points": 30,
        "refine_f3_points": 20,
        "credit_multiplier": 1,
    },
    SEARCH_PROFILE_DEEP: {
        "max_evaluations": 120,
        "coarse_points": 30,
        "refine_f3_points": 20,
        "credit_multiplier": 2,
    },
}


def search_profile_credit_multiplier(profile: str = SEARCH_PROFILE_STANDARD) -> int:
    """Return the credit cost multiplier for this search profile (Standard: 1, Deep: 2)."""
    spec = SEARCH_PROFILES.get(profile, SEARCH_PROFILES[SEARCH_PROFILE_STANDARD])
    return int(spec.get("credit_multiplier", 1))


def finder_optimizer_evaluation_limit(
    module_path: Path | None = None,
    profile: str = SEARCH_PROFILE_STANDARD,
) -> int:
    """Return the per-driver optimizer budget based on the active search profile."""
    spec = SEARCH_PROFILES.get(profile, SEARCH_PROFILES[SEARCH_PROFILE_STANDARD])
    limit = int(spec["max_evaluations"])
    if os.getenv("K_SERVICE"):
        return min(limit, 24)
    return limit


def finder_optimizer_frequency_plan(
    module_path: Path | None = None,
    profile: str = SEARCH_PROFILE_STANDARD,
) -> tuple[int, int]:
    """Return broad/refinement frequency counts for Finder runs based on search profile."""
    spec = SEARCH_PROFILES.get(profile, SEARCH_PROFILES[SEARCH_PROFILE_STANDARD])
    return (
        int(spec["coarse_points"]),
        int(spec["refine_f3_points"]),
    )


def ranking_candidate(name: str) -> RankingCandidate:
    """Resolve one named preset into the compact worker payload."""
    info = presets.driver_preset_info(name)
    return RankingCandidate(
        name=name,
        ts=presets.get_driver_preset(name),
        source=info.source,
        brand=info.brand or "Other",
        size_in=info.size_in,
        price=info.price,
        currency=info.currency,
        url=info.url or "",
    )


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
    driver_configuration: str = "Single driver",
    search_profile: str = SEARCH_PROFILE_STANDARD,
) -> dict | None:
    """Build one ranking-table row for a single or composite driver."""
    try:
        candidate = ranking_candidate(name)
    except Exception:
        return None
    return rank_candidate_row(
        candidate, load_type, max_volume_l, voltage_v, f_min_hz, f_max_hz,
        points, goals, driver_configuration, search_profile,
    )


def rank_candidate_row(
    candidate: RankingCandidate,
    load_type: str,
    max_volume_l: float,
    voltage_v: float,
    f_min_hz: float,
    f_max_hz: float,
    points: int,
    goals: engine.OptimizationGoals | None = None,
    driver_configuration: str = "Single driver",
    search_profile: str = SEARCH_PROFILE_STANDARD,
) -> dict | None:
    """Build one row from a compact payload without loading worker catalogs."""
    name = candidate.name
    if load_type in ("Suspension pneumatic", "Acoustic suspension"):
        load_type = "Sealed"
    f_min = float(f_min_hz)
    f_max = float(f_max_hz)
    if (
        goals is not None
        and goals.ripple_max_freq_hz is not None
        and float(goals.ripple_max_freq_hz) > f_min
        and float(goals.ripple_max_freq_hz) < f_max
    ):
        freq = engine.segmented_frequency_grid(
            f_min, float(goals.ripple_max_freq_hz), f_max,
            dense_points=int(points), sparse_points=9,
        )
    else:
        freq = np.geomspace(f_min, f_max, int(points))
    try:
        ts = engine.apply_driver_configuration(
            candidate.ts, driver_configuration
        )
        if load_type not in ("Sealed", "Infinite baffle") and ts.xmax_mm <= 0:
            return None
        driver_class = engine.classify_driver_bandwidth(ts).driver_class
        ripple_db = float("nan")
        box: (
            engine.DccavBox
            | engine.ReflexBox
            | engine.PassiveRadiatorBox
            | engine.Bandpass4Box
            | engine.Bandpass6Box
            | engine.Bandpass8Box
            | engine.SealedBox
            | None
        )
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
                ripple_max_freq_hz=goals.ripple_max_freq_hz,
            )
            frequency_points, refine_f3_points = finder_optimizer_frequency_plan(profile=search_profile)
            optimized = engine.optimize_alignment(
                ts,
                batch_goals,
                load_type=load_type,
                voltage_v=float(voltage_v),
                max_evaluations=finder_optimizer_evaluation_limit(profile=search_profile),
                frequency_points=frequency_points,
                refine_f3_points=refine_f3_points,
            )
            box = optimized.box
            ripple_db = float(optimized.ripple_db)
        elif load_type == "Bass reflex":
            reflex_alignment = engine.suggest_reflex_alignment(ts)
            box = engine.ReflexBox(
                vb_l=min(float(reflex_alignment.vb_l), float(max_volume_l)),
                fb_hz=reflex_alignment.fb_hz,
            )
        elif load_type == "Passive radiator":
            pr_alignment = engine.suggest_pr_alignment(ts)
            box = engine.PassiveRadiatorBox(
                vb_l=min(float(pr_alignment.vb_l), float(max_volume_l)),
                pr_sp_cm2=pr_alignment.pr_sp_cm2,
                pr_fp_hz=pr_alignment.pr_fp_hz,
                pr_qmp=pr_alignment.pr_qmp,
                pr_mmp_g=pr_alignment.pr_mmp_g,
                pr_xmax_mm=pr_alignment.pr_xmax_mm,
            )
        elif load_type == "Sealed":
            sealed_alignment = engine.suggest_sealed_alignment(ts)
            box = engine.SealedBox(
                vb_l=min(float(sealed_alignment.vb_l), float(max_volume_l)))
        elif load_type == "Bandpass 4th order":
            bp4_start = engine.suggest_bandpass4_alignment(ts)
            starter_volume_l = float(bp4_start.vs_l + bp4_start.vp_l)
            box = engine.design_space_box(
                ts, load_type, min(starter_volume_l, float(max_volume_l)), bp4_start.fp_hz)
        elif load_type == "Bandpass 6th order":
            bp6_start = engine.suggest_bandpass6_alignment(ts)
            starter_volume_l = float(bp6_start.vr_l + bp6_start.vp_l)
            box = engine.design_space_box(
                ts, load_type, min(starter_volume_l, float(max_volume_l)), bp6_start.fp_hz)
        elif load_type == "Bandpass 8th order":
            bp8_start = engine.suggest_bandpass8_alignment(ts)
            starter_volume_l = float(bp8_start.v1_l + bp8_start.v2_l + bp8_start.v3_l)
            box = engine.design_space_box(
                ts, load_type, min(starter_volume_l, float(max_volume_l)), bp8_start.f3_hz)
        elif load_type == "Infinite baffle":
            box = None
        else:
            dccav_start = engine.suggest_alignment(ts)
            starter_volume_l = float(dccav_start.vh_l + dccav_start.vl_l)
            box = engine.design_space_box(
                ts, "DCCAV", min(starter_volume_l, float(max_volume_l)),
                dccav_start.fl_hz,
            )
        if isinstance(box, engine.ReflexBox):
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
                "V1 L": np.nan,
                "f1 Hz": np.nan,
                "V2 L": np.nan,
                "f2 Hz": np.nan,
                "V3 L": np.nan,
                "f3 Hz": np.nan,
            }
        elif isinstance(box, engine.PassiveRadiatorBox):
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
                "V1 L": np.nan,
                "f1 Hz": np.nan,
                "V2 L": np.nan,
                "f2 Hz": np.nan,
                "V3 L": np.nan,
                "f3 Hz": np.nan,
            }
        elif isinstance(box, engine.SealedBox):
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
                "V1 L": np.nan,
                "f1 Hz": np.nan,
                "V2 L": np.nan,
                "f2 Hz": np.nan,
                "V3 L": np.nan,
                "f3 Hz": np.nan,
            }
        elif isinstance(box, engine.Bandpass4Box):
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
                "V1 L": np.nan,
                "f1 Hz": np.nan,
                "V2 L": np.nan,
                "f2 Hz": np.nan,
                "V3 L": np.nan,
                "f3 Hz": np.nan,
            }
        elif isinstance(box, engine.Bandpass6Box):
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
                "V1 L": np.nan,
                "f1 Hz": np.nan,
                "V2 L": np.nan,
                "f2 Hz": np.nan,
                "V3 L": np.nan,
                "f3 Hz": np.nan,
            }
        elif isinstance(box, engine.Bandpass8Box):
            result = engine.simulate_bandpass8(ts, box, freq, float(voltage_v))
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
                "Vp L": np.nan,
                "Fp Hz": np.nan,
                "Vr L": np.nan,
                "Fr Hz": np.nan,
                "V1 L": box.v1_l,
                "f1 Hz": box.f1_hz,
                "V2 L": box.v2_l,
                "f2 Hz": box.f2_hz,
                "V3 L": box.v3_l,
                "f3 Hz": box.f3_hz,
            }
        elif box is None:
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
                "V1 L": np.nan,
                "f1 Hz": np.nan,
                "V2 L": np.nan,
                "f2 Hz": np.nan,
                "V3 L": np.nan,
                "f3 Hz": np.nan,
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
                "V1 L": np.nan,
                "f1 Hz": np.nan,
                "V2 L": np.nan,
                "f2 Hz": np.nan,
                "V3 L": np.nan,
                "f3 Hz": np.nan,
            }
        thresholds = engine.response_threshold_frequencies(result)
        f3_hz = float(thresholds[3])
        if goals is not None:
            ripple_db = engine.passband_ripple_db(
                result, box, goals.ripple_max_freq_hz)
            if (
                goals.max_ripple_db
                and goals.max_ripple_db > 0
                and (
                    not np.isfinite(ripple_db)
                    or ripple_db > goals.max_ripple_db + 1e-9
                )
            ):
                return None
        mol_frequency = np.asarray(result.frequency_hz, dtype=float)
        mol_db = np.asarray(result.mol_db, dtype=float)
        finite_mol = np.isfinite(mol_frequency) & np.isfinite(mol_db)
        mol_at_f3_db = (
            float(np.interp(f3_hz, mol_frequency[finite_mol], mol_db[finite_mol]))
            if np.isfinite(f3_hz) and np.any(finite_mol)
            else float("nan")
        )
        box_snapshot = asdict(box) if box is not None else None
        return {
            "Driver": name,
            "_driver_ts": asdict(candidate.ts),
            "_box_type": type(box).__name__ if box is not None else None,
            "_box_params": box_snapshot,
            "Driver configuration": driver_configuration,
            "Source": candidate.source,
            "Brand": candidate.brand,
            "Class": driver_class,
            "Size in": candidate.size_in if candidate.size_in is not None else np.nan,
            "Sd cm²": ts.sd_cm2,
            "Price": candidate.price if candidate.price is not None else np.nan,
            "Currency": candidate.currency,
            "Buy": candidate.url,
            "Mms g": ts.mms_g if ts.mms_g is not None else np.nan,
            "Le10k mH": ts.le10k_mh if ts.le10k_mh is not None else np.nan,
            "F3 Hz": f3_hz,
            "F6 Hz": thresholds[6],
            "F10 Hz": thresholds[10],
            "MOL @ F3 dB": mol_at_f3_db,
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
