"""
Candidate-ranking rows for the `Find a driver` workspace.

Pure functions importable by worker processes: each row simulates one preset
within the requested maximum enclosure volume and reports the metrics shown by
the ranking table.
"""

from __future__ import annotations

import math
import os
import threading
from collections import OrderedDict
from dataclasses import asdict, dataclass
from functools import lru_cache
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
FINDER_SPL_PREFILTER_HEADROOM_DB = 6.0

# Bounded memoization of the expensive optimizer result, keyed by the full
# driver/brief fingerprint. Rows are rebuilt on every call so callers can keep
# mutating their own copies without poisoning the cache.
_OPTIMIZED_ALIGNMENT_CACHE: OrderedDict[tuple, engine.OptimizedAlignment] = OrderedDict()
_OPTIMIZED_ALIGNMENT_CACHE_LOCK = threading.Lock()
_OPTIMIZED_ALIGNMENT_CACHE_SIZE = 512

# Optional engineering/commercial fields tracked by the data-coverage badge.
# The six essential T/S values (Fs, Vas, Qts, Qms, Re, Sd) are required by the
# catalog loaders, so they are not part of the score.
_DRIVER_COVERAGE_FIELDS = (
    ("Xmax", lambda ts, size, price: float(ts.xmax_mm) > 0.0),
    ("Pe", lambda ts, size, price: float(ts.pe_w) > 0.0),
    ("Le", lambda ts, size, price: float(ts.le_mh) > 0.0),
    ("Mms", lambda ts, size, price: ts.mms_g is not None),
    ("Bl", lambda ts, size, price: ts.bl_tm is not None),
    ("Cms", lambda ts, size, price: ts.cms_mm_per_n is not None),
    ("Le10k", lambda ts, size, price: ts.le10k_mh is not None),
    ("Size", lambda ts, size, price: size is not None and np.isfinite(float(size))),
    ("Price", lambda ts, size, price: price is not None and np.isfinite(float(price))),
)

DRIVER_COVERAGE_LABELS = tuple(label for label, _ in _DRIVER_COVERAGE_FIELDS)


def candidate_precheck(
    ts: engine.DriverTS,
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
        reference = engine.driver_reference_metrics(ts)
        drive_spl_db = reference.spl_2v83_db + 20.0 * np.log10(
            float(voltage_v) / 2.83
        )
        enclosure_headroom_db = (
            1.0
            if load_type == "Infinite baffle"
            else max(FINDER_SPL_PREFILTER_HEADROOM_DB, float(max_ripple_db))
        )
        if drive_spl_db + enclosure_headroom_db < float(min_spl_db):
            return "reference SPL"

    if fast_prefilter:
        loaded_fs = engine.panel_loaded_fs_hz(ts)
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


@lru_cache(maxsize=128)
def prefilter_finder_candidate_pools(
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
    pool_fingerprint: tuple = (),
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
            ts = engine.apply_driver_configuration(
                presets.get_driver_preset(name),
                driver_configuration,
            )
        except Exception:
            rejected_by_reason["invalid T/S"] += len(load_types)
            continue
        for load_type in load_types:
            try:
                reason = candidate_precheck(
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


def _optimizer_brief_key(
    ts: engine.DriverTS,
    goals: engine.OptimizationGoals,
    load_type: str,
    voltage_v: float,
    frequency_points: int,
    refine_f3_points: int,
    search_profile: str,
) -> tuple:
    """Fingerprint a complete optimizer brief for the result cache."""
    return (
        engine.OPTIMIZER_ENGINE_REVISION,
        load_type,
        search_profile,
        float(voltage_v),
        int(frequency_points),
        int(refine_f3_points),
        float(goals.max_total_volume_l) if goals.max_total_volume_l is not None else None,
        goals.objective,
        float(goals.target_f3_hz) if goals.target_f3_hz is not None else None,
        float(goals.max_ripple_db),
        float(goals.max_excursion_ratio),
        float(goals.max_group_delay_ms) if goals.max_group_delay_ms is not None else None,
        float(goals.min_spl_db) if goals.min_spl_db is not None else None,
        float(goals.ripple_max_freq_hz) if goals.ripple_max_freq_hz is not None else None,
        *(getattr(ts, field) for field in ts.__dataclass_fields__),
    )


def _cached_optimized_alignment(key: tuple, factory) -> engine.OptimizedAlignment:
    """Return a memoized optimizer result, computing it on the first miss."""
    with _OPTIMIZED_ALIGNMENT_CACHE_LOCK:
        cached = _OPTIMIZED_ALIGNMENT_CACHE.get(key)
        if cached is not None:
            _OPTIMIZED_ALIGNMENT_CACHE.move_to_end(key)
            return cached
    optimized = factory()
    with _OPTIMIZED_ALIGNMENT_CACHE_LOCK:
        _OPTIMIZED_ALIGNMENT_CACHE[key] = optimized
        _OPTIMIZED_ALIGNMENT_CACHE.move_to_end(key)
        while len(_OPTIMIZED_ALIGNMENT_CACHE) > _OPTIMIZED_ALIGNMENT_CACHE_SIZE:
            _OPTIMIZED_ALIGNMENT_CACHE.popitem(last=False)
    return optimized


def invalidate_ranking_caches() -> None:
    """Clear cached ranking and candidate pool lookups."""
    prefilter_finder_candidate_pools.cache_clear()
    with _OPTIMIZED_ALIGNMENT_CACHE_LOCK:
        _OPTIMIZED_ALIGNMENT_CACHE.clear()


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


def driver_data_coverage(
    ts: engine.DriverTS,
    size_in: float | None = None,
    price: float | None = None,
) -> dict:
    """Return the optional-parameter coverage for one driver.

    ``score`` is the percentage of optional engineering/commercial fields that
    are present, ``missing`` lists the absent labels and ``status`` is the
    display bucket (Complete / Partial / Incomplete). Missing fields are never
    invented: callers keep the existing fallbacks and use the badge to warn the
    user about what the ranking could not verify.
    """
    missing = tuple(
        label
        for label, present in _DRIVER_COVERAGE_FIELDS
        if not present(ts, size_in, price)
    )
    total = len(_DRIVER_COVERAGE_FIELDS)
    score = int(round(100.0 * (total - len(missing)) / total))
    if not missing:
        status = "Complete"
    elif score >= 55:
        status = "Partial"
    else:
        status = "Incomplete"
    return {"score": score, "missing": missing, "status": status}


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

# Free optimizer axes per lumped topology, mirroring the coordinate vectors in
# engine.optimize_alignment.  Loads without a box search (infinite baffle,
# passive radiator starter) are absent on purpose.
_LOAD_TYPE_SEARCH_AXES = {
    "Sealed": 1,
    "Bass reflex": 2,
    "Bandpass 4th order": 3,
    "Bandpass 6th order": 4,
    "DCCAV": 4,
    "Bandpass 8th order": 6,
}

SEARCH_PROFILES = {
    SEARCH_PROFILE_STANDARD: {
        # Legacy flat budget, used when the load type is unknown.
        "max_evaluations": 60,
        "evaluations_per_axis": 20,
        "evaluations_overhead": 10,
        "min_evaluations": 24,
        "evaluations_cap": 120,
        "coarse_points": 30,
        "refine_f3_points": 20,
        "credit_multiplier": 1,
    },
    SEARCH_PROFILE_DEEP: {
        "max_evaluations": 120,
        "evaluations_per_axis": 40,
        "evaluations_overhead": 20,
        "min_evaluations": 48,
        "evaluations_cap": 240,
        "coarse_points": 30,
        "refine_f3_points": 20,
        "credit_multiplier": 2,
    },
}


def search_profile_credit_multiplier(profile: str = SEARCH_PROFILE_STANDARD) -> int:
    """Return the credit cost multiplier for this search profile (Standard: 1, Deep: 2)."""
    spec = SEARCH_PROFILES.get(profile, SEARCH_PROFILES[SEARCH_PROFILE_STANDARD])
    return int(spec.get("credit_multiplier", 1))


def finder_optimizer_axis_count(load_type: str | None) -> int | None:
    """Return the number of free optimizer axes for a load, or None if unswept."""
    if not load_type:
        return None
    canonical = (
        "Sealed"
        if load_type in ("Suspension pneumatic", "Acoustic suspension")
        else load_type
    )
    return _LOAD_TYPE_SEARCH_AXES.get(canonical)


def finder_optimizer_evaluation_limit(
    module_path: Path | None = None,
    profile: str = SEARCH_PROFILE_STANDARD,
    load_type: str | None = None,
) -> int:
    """Return the per-driver optimizer budget for the active profile and load.

    The budget scales with the number of free optimizer axes (Sealed 1 ...
    Bandpass 8th order 6) instead of using one flat value for every topology:
    ``overhead + per_axis * axes``, clamped to the profile floor and cap.
    Without a known load type the historical flat profile budget is returned.
    ``module_path`` is accepted for API compatibility and ignored.
    """
    spec = SEARCH_PROFILES.get(profile, SEARCH_PROFILES[SEARCH_PROFILE_STANDARD])
    axes = finder_optimizer_axis_count(load_type)
    if axes is None:
        return int(spec["max_evaluations"])
    budget = int(spec["evaluations_overhead"]) + int(spec["evaluations_per_axis"]) * int(axes)
    return int(min(max(budget, int(spec["min_evaluations"])), int(spec["evaluations_cap"])))


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
        coverage = driver_data_coverage(ts, candidate.size_in, candidate.price)
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
            brief_key = _optimizer_brief_key(
                ts, batch_goals, load_type, float(voltage_v),
                frequency_points, refine_f3_points, search_profile,
            )
            optimized = _cached_optimized_alignment(
                brief_key,
                lambda: engine.optimize_alignment(
                    ts,
                    batch_goals,
                    load_type=load_type,
                    voltage_v=float(voltage_v),
                    max_evaluations=finder_optimizer_evaluation_limit(
                        profile=search_profile, load_type=load_type),
                    frequency_points=frequency_points,
                    refine_f3_points=refine_f3_points,
                ),
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
            "Data": coverage["status"],
            "Data %": coverage["score"],
            "_data_missing": coverage["missing"],
            "Response": response_sparkline(result.spl_total_db),
            "_load_type": load_type,
            **box_values,
        }
    except Exception:
        return None
