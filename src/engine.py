"""
Acoustic-load engine: physics, simulation, optimization and analysis.

The lumped DCCAV model follows the PCPaudio/G.P. Matarazzo "doppio resonador
en serie" article:

    driver -> upper volume || upper port -> lower volume || lower port

All calculations use SI units internally and expose litre/Hz/mm-friendly
helpers for the UI.  ``src/dccav.py`` re-exports this module's public API.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

RHO_AIR = 1.18
SPEED_OF_SOUND = 344.0
P_REF = 20e-6
EPS = 1e-30


def adaptive_frequency_grid(
    f_min_hz: float, f_max_hz: float, points: int,
    anchors: tuple[float, ...] = (),
) -> np.ndarray:
    """Build a compact log grid with extra samples around resonance anchors."""
    if f_min_hz <= 0 or f_max_hz <= f_min_hz or points < 8:
        raise ValueError("Invalid adaptive frequency-grid limits")
    valid = sorted({float(x) for x in anchors if f_min_hz < float(x) < f_max_hz})
    grid = list(np.geomspace(float(f_min_hz), float(f_max_hz), max(8, points // 2)))
    for anchor in valid:
        grid.extend(np.geomspace(max(f_min_hz, anchor / 2), min(f_max_hz, anchor * 2), max(8, points // (2 * len(valid)))))
    return np.unique(np.asarray(grid, dtype=float))


@dataclass(frozen=True)
class DriverTS:
    """Thiele/Small parameters needed by the DCCAV simulator."""

    fs_hz: float
    vas_l: float
    qts: float
    qms: float
    re_ohm: float
    sd_cm2: float
    le_mh: float = 0.0
    le10k_mh: float | None = None
    xmax_mm: float = 0.0
    pe_w: float = 0.0
    mms_g: float | None = None
    cms_mm_per_n: float | None = None
    bl_tm: float | None = None
    panel_air_load: bool = True
    panel_coupling: float = 0.90
    radiating_pistons: int = 1



@dataclass(frozen=True)
class DerivedDriver:
    """Driver values converted to SI/acoustic-domain components."""

    sd_m2: float
    vas_m3: float
    cms_m_per_n: float
    mms_kg: float
    rms_n_s_m: float
    qes: float
    bl_tm: float
    rat: float
    cas: float
    mas: float


@dataclass(frozen=True)
class DccavAlignment:
    """Empirical DCCAV alignment suggested by the PCPaudio article."""

    vh_l: float
    fh_hz: float
    vl_l: float
    fl_hz: float
    f3_hz: float


@dataclass(frozen=True)
class DccavBox:
    """Two series resonator volumes and their loss factors."""

    vh_l: float
    fh_hz: float
    vl_l: float
    fl_hz: float
    q_abs_h: float = 15.0
    q_abs_l: float = 15.0
    q_leak_h: float = 1000.0
    q_leak_l: float = 1000.0
    q_port_h: float = 15.0
    q_port_l: float = 15.0


@dataclass(frozen=True)
class ReflexAlignment:
    """Conservative one-box bass-reflex starter alignment."""

    vb_l: float
    fb_hz: float


@dataclass(frozen=True)
class ReflexBox:
    """Single vented-box volume, tuning and loss factors."""

    vb_l: float
    fb_hz: float
    q_abs: float = 15.0
    q_leak: float = 1000.0
    q_port: float = 15.0


@dataclass(frozen=True)
class Bandpass4Alignment:
    """Conservative fourth-order bandpass starter alignment."""

    vs_l: float
    vp_l: float
    fp_hz: float


@dataclass(frozen=True)
class Bandpass4Box:
    """Sealed rear chamber plus a vented front chamber."""

    vs_l: float
    vp_l: float
    fp_hz: float
    q_abs_s: float = 15.0
    q_abs_p: float = 15.0
    q_leak_s: float = 1000.0
    q_leak_p: float = 1000.0
    q_port: float = 15.0


@dataclass(frozen=True)
class Bandpass6Alignment:
    """Conservative sixth-order dual-vented bandpass starter alignment."""

    vr_l: float
    fr_hz: float
    vp_l: float
    fp_hz: float


@dataclass(frozen=True)
class Bandpass6Box:
    """Sixth-order dual-vented bandpass: ported rear + ported front chamber."""

    vr_l: float
    fr_hz: float
    vp_l: float
    fp_hz: float
    q_abs_r: float = 15.0
    q_abs_p: float = 15.0
    q_leak_r: float = 1000.0
    q_leak_p: float = 1000.0
    q_port_r: float = 15.0
    q_port_p: float = 15.0


@dataclass(frozen=True)
class PassiveRadiatorBox:
    """Vented box loaded by a passive radiator instead of a duct."""

    vb_l: float
    pr_sp_cm2: float
    pr_fp_hz: float
    pr_qmp: float = 5.0
    pr_mmp_g: float = 100.0
    pr_added_mass_g: float = 0.0
    pr_xmax_mm: float = 0.0
    q_abs: float = 15.0
    q_leak: float = 1000.0


@dataclass(frozen=True)
class SealedAlignment:
    """Classical closed-box starter alignment."""

    vb_l: float
    fc_hz: float
    qtc: float


@dataclass(frozen=True)
class SealedBox:
    """Closed-box volume and acoustic loss factors."""

    vb_l: float
    q_abs: float = 15.0
    q_leak: float = 1000.0


BoxUnion = DccavBox | ReflexBox | Bandpass4Box | Bandpass6Box | SealedBox
BoxBuilder = Callable[[np.ndarray], BoxUnion]


@dataclass(frozen=True)
class OptimizationGoals:
    """User-settable goals for :func:`optimize_alignment`.

    ``objective`` weighs extension against flatness; the remaining fields are
    optional constraints enforced through score penalties.  ``None`` (or a
    non-positive UI value mapped to ``None``) disables a constraint.
    """

    objective: str = "balanced"  # "extension" | "balanced" | "flat"
    max_total_volume_l: float | None = None
    target_f3_hz: float | None = None
    max_ripple_db: float = 3.0
    max_excursion_ratio: float = 1.0
    max_group_delay_ms: float | None = None
    min_spl_db: float | None = None


@dataclass(frozen=True)
class OptimizedAlignment:
    """Optimizer result: the box plus the achieved response figures."""

    box: DccavBox | ReflexBox | Bandpass4Box | Bandpass6Box | SealedBox
    f3_hz: float
    f10_hz: float
    ripple_db: float
    excursion_ratio: float
    group_delay_ms: float
    total_volume_l: float
    score: float
    evaluations: int


@dataclass(frozen=True)
class SimulationResult:
    """Frequency-domain response arrays returned by :func:`simulate`."""

    frequency_hz: np.ndarray
    spl_total_db: np.ndarray
    spl_driver_db: np.ndarray
    spl_port_db: np.ndarray
    excursion_mm: np.ndarray
    impedance_ohm: np.ndarray
    port_h_velocity: np.ndarray
    port_l_velocity: np.ndarray
    mil_w: np.ndarray
    mol_db: np.ndarray
    driver_volume_velocity: np.ndarray
    port_volume_velocity: np.ndarray
    # Electrical impedance phase in degrees; None on results built before the
    # field existed (ZMA export then degrades to zero phase).
    impedance_phase_deg: np.ndarray | None = None


@dataclass(frozen=True)
class WaveguideSegment:
    """Uniform acoustic-waveguide section used by the 1-D line solver."""

    length_m: float
    area_cm2: float


@dataclass(frozen=True)
class TransmissionLineBox:
    """One-dimensional transmission-line enclosure.

    ``segments`` run from the driver plane to the external termination.  A
    closed termination is useful for quarter-wave lines; an open termination
    uses the piston radiation impedance of ``mouth_area_cm2``.  Loss is a
    phenomenological Q for the distributed line and is deliberately exposed
    so measured line damping can be fitted later.
    """

    segments: tuple[WaveguideSegment, ...]
    termination: str = "open"
    mouth_area_cm2: float | None = None
    line_q: float = 25.0
    direct_cone_radiation: bool = True


@dataclass(frozen=True)
class MltlBox:
    """Mass-loaded transmission line with a side vent at the line mouth."""

    segments: tuple[WaveguideSegment, ...]
    vent_area_cm2: float
    vent_length_m: float
    vent_end_correction: float = 1.43
    line_q: float = 25.0
    direct_cone_radiation: bool = True


@dataclass(frozen=True)
class HornBox:
    """Back-loaded horn represented by a tapered 1-D acoustic guide."""

    length_m: float
    throat_area_cm2: float
    mouth_area_cm2: float
    flare: str = "exponential"
    segments: int = 80
    mouth_termination: str = "open"
    line_q: float = 20.0
    direct_cone_radiation: bool = True


@dataclass(frozen=True)
class TappedHornBox:
    """Tapped horn with the driver connected between throat and mouth arms."""

    length_m: float
    throat_area_cm2: float
    mouth_area_cm2: float
    tap_position_m: float
    flare: str = "exponential"
    segments: int = 80
    line_q: float = 20.0
    direct_cone_radiation: bool = False


def sd_from_diameter(diameter_mm: float) -> float:
    """Return piston area in cm^2 from an effective piston diameter in mm."""
    d_m = float(diameter_mm) / 1000.0
    return float(np.pi * (d_m / 2.0) ** 2 * 10_000.0)


def panel_air_load_metrics(ts: DriverTS) -> tuple[float, float]:
    """Return ``(added_mass_g, panel_loaded_fs_hz)`` for the driver.

    Free-air T/S moving mass already includes the radiation load present during
    the parameter measurement.  Mounting the piston on a baffle increases the
    coupled air mass.  The low-frequency baffled-piston increment is
    ``8*rho*a^3/3``; ``panel_coupling`` represents the finite panel as a
    fraction of that limiting increment.  A value of 0.90 is the conventional
    partial-baffle approximation and reproduces the AFW FE126 validation case
    to better than 0.1% in resonance frequency.
    """
    _require_positive("Fs", ts.fs_hz)
    _require_positive("Vas", ts.vas_l)
    _require_positive("Sd", ts.sd_cm2)
    coupling = float(ts.panel_coupling)
    if not 0.0 <= coupling <= 1.0:
        raise ValueError("Panel coupling must be between 0 and 1")
    if not ts.panel_air_load or coupling == 0.0:
        return 0.0, float(ts.fs_hz)

    piston_count = int(ts.radiating_pistons)
    if piston_count < 1 or piston_count != ts.radiating_pistons:
        raise ValueError("Radiating piston count must be a positive integer")
    sd_m2 = ts.sd_cm2 / 10_000.0
    cms = (
        ts.cms_mm_per_n / 1000.0
        if ts.cms_mm_per_n is not None and ts.cms_mm_per_n > 0
        else (ts.vas_l / 1000.0) / (RHO_AIR * SPEED_OF_SOUND**2 * sd_m2**2)
    )
    mms_kg = (
        ts.mms_g / 1000.0
        if ts.mms_g is not None and ts.mms_g > 0
        else 1.0 / ((2.0 * np.pi * ts.fs_hz) ** 2 * cms)
    )
    # Separate cones each carry their own local radiation mass.  Treating a
    # pair as one large equivalent piston would overstate the a^3 term by
    # sqrt(2), even though the composite Sd and moving mass are otherwise the
    # correct representation for the shared acoustic load.
    piston_area_m2 = sd_m2 / piston_count
    piston_radius_m = float(np.sqrt(piston_area_m2 / np.pi))
    added_mass_kg = (
        piston_count * coupling * (8.0 / 3.0) * RHO_AIR * piston_radius_m**3
    )
    mass_ratio = (mms_kg + added_mass_kg) / mms_kg
    loaded_fs_hz = ts.fs_hz / float(np.sqrt(mass_ratio))
    return float(added_mass_kg * 1000.0), float(loaded_fs_hz)


def panel_loaded_fs_hz(ts: DriverTS) -> float:
    """Return the effective mounted resonance, or free-air Fs when disabled."""
    return panel_air_load_metrics(ts)[1]



def complete_driver(ts: DriverTS) -> DerivedDriver:
    """Convert a T/S set to derived mechanical and acoustic components."""
    _require_positive("Fs", ts.fs_hz)
    _require_positive("Vas", ts.vas_l)
    _require_positive("Qts", ts.qts)
    _require_positive("Qms", ts.qms)
    _require_positive("Re", ts.re_ohm)
    _require_positive("Sd", ts.sd_cm2)
    if ts.qms <= ts.qts:
        raise ValueError("Qms must be greater than Qts so Qes can be derived")

    sd_m2 = ts.sd_cm2 / 10_000.0
    vas_m3 = ts.vas_l / 1000.0
    cms = (
        ts.cms_mm_per_n / 1000.0
        if ts.cms_mm_per_n is not None and ts.cms_mm_per_n > 0
        else vas_m3 / (RHO_AIR * SPEED_OF_SOUND**2 * sd_m2**2)
    )
    free_air_mms = (
        ts.mms_g / 1000.0
        if ts.mms_g is not None and ts.mms_g > 0
        else 1.0 / ((2.0 * np.pi * ts.fs_hz) ** 2 * cms)
    )
    added_mass_g, effective_fs = panel_air_load_metrics(ts)
    mms = free_air_mms + added_mass_g / 1000.0
    rms = 2.0 * np.pi * effective_fs * mms / ts.qms
    qes = 1.0 / (1.0 / ts.qts - 1.0 / ts.qms)
    mass_ratio = mms / free_air_mms
    bl = (
        ts.bl_tm * mass_ratio**0.25
        if ts.bl_tm is not None and ts.bl_tm > 0
        else float(np.sqrt(2.0 * np.pi * effective_fs * mms * ts.re_ohm / qes))
    )

    cas = cms * sd_m2**2
    mas = mms / sd_m2**2
    rat = (rms + bl**2 / ts.re_ohm) / sd_m2**2
    return DerivedDriver(
        sd_m2=sd_m2,
        vas_m3=vas_m3,
        cms_m_per_n=float(cms),
        mms_kg=float(mms),
        rms_n_s_m=float(rms),
        qes=float(qes),
        bl_tm=float(bl),
        rat=float(rat),
        cas=float(cas),
        mas=float(mas),
    )


def _electrical_source(
    ts: DriverTS,
    drv: DerivedDriver,
    voltage_v: float,
    series_r_ohm: float,
) -> tuple[float, float, float]:
    """Return `(re_total, rat, p_source)` seen from the source terminals.

    A non-zero `series_r_ohm` (amplifier output, cable and crossover-coil DCR)
    reduces both the drive pressure and the electrical damping `Bl^2/Re`,
    raising the effective Qes/Qts of the system.
    """
    if series_r_ohm < 0:
        raise ValueError("Series resistance must be >= 0")
    re_total = ts.re_ohm + float(series_r_ohm)
    rat = (drv.rms_n_s_m + drv.bl_tm**2 / re_total) / drv.sd_m2**2
    p_source = voltage_v * drv.bl_tm / (re_total * drv.sd_m2)
    return re_total, rat, p_source


def suggest_alignment(ts: DriverTS) -> DccavAlignment:
    """Return the empirical first-pass DCCAV alignment from the article."""
    _require_positive("Fs", ts.fs_hz)
    _require_positive("Vas", ts.vas_l)
    _require_positive("Qts", ts.qts)
    vh = 2.05 * ts.qts**2 * ts.vas_l
    vl = 4.13 * ts.qts**2 * ts.vas_l
    effective_fs = panel_loaded_fs_hz(ts)
    fh = 1.22 * effective_fs / ts.qts
    fl = 0.466 * effective_fs / ts.qts
    return DccavAlignment(vh_l=vh, fh_hz=fh, vl_l=vl, fl_hz=fl, f3_hz=0.83 * fl)


def suggest_reflex_alignment(ts: DriverTS) -> ReflexAlignment:
    """Return a conservative bass-reflex starting point."""
    _require_positive("Fs", ts.fs_hz)
    _require_positive("Vas", ts.vas_l)
    return ReflexAlignment(vb_l=ts.vas_l, fb_hz=panel_loaded_fs_hz(ts))


def suggest_bandpass4_alignment(
    ts: DriverTS, target_qbp: float = 0.707,
) -> Bandpass4Alignment:
    """Return a practical symmetrical fourth-order bandpass starter.

    The closed rear chamber uses the classical target-Q relation.  The front
    chamber follows the common symmetrical-bandpass volume ``2*Qbp^2*Vas``
    and its vent is tuned to ``Fs*Qbp/Qts``.  This is a first-pass alignment,
    not a substitute for optimizing the required passband and build limits.
    """
    _require_positive("Target Qbp", target_qbp)
    _require_positive("Fs", ts.fs_hz)
    _require_positive("Vas", ts.vas_l)
    _require_positive("Qts", ts.qts)
    if target_qbp > ts.qts:
        vs_l = ts.vas_l / ((target_qbp / ts.qts) ** 2 - 1.0)
    else:
        vs_l = 4.0 * ts.vas_l
    vp_l = 2.0 * target_qbp**2 * ts.vas_l
    fp_hz = panel_loaded_fs_hz(ts) * target_qbp / ts.qts
    return Bandpass4Alignment(
        vs_l=max(0.05, float(vs_l)),
        vp_l=max(0.05, float(vp_l)),
        fp_hz=float(fp_hz),
    )


def sealed_system_metrics(ts: DriverTS, box: SealedBox) -> tuple[float, float]:
    """Return the classical closed-box ``(Fc, Qtc)`` pair."""
    _require_positive("Fs", ts.fs_hz)
    _require_positive("Vas", ts.vas_l)
    _require_positive("Qts", ts.qts)
    _validate_sealed_box(box)
    ratio = float(np.sqrt(1.0 + ts.vas_l / box.vb_l))
    return float(panel_loaded_fs_hz(ts) * ratio), float(ts.qts * ratio)


def suggest_sealed_alignment(ts: DriverTS, target_qtc: float = 0.707) -> SealedAlignment:
    """Return a closed-box starter near the requested Qtc when feasible."""
    _require_positive("Target Qtc", target_qtc)
    _require_positive("Qts", ts.qts)
    _require_positive("Vas", ts.vas_l)
    if target_qtc > ts.qts:
        denominator = (target_qtc / ts.qts) ** 2 - 1.0
        vb_l = ts.vas_l / denominator
    else:
        # A passive closed box cannot reduce Qtc below Qts.  Four Vas is a
        # practical finite approximation to an infinite enclosure.
        vb_l = 4.0 * ts.vas_l
    vb_l = max(0.05, float(vb_l))
    box = SealedBox(vb_l=float(vb_l))
    fc_hz, qtc = sealed_system_metrics(ts, box)
    return SealedAlignment(vb_l=float(vb_l), fc_hz=fc_hz, qtc=qtc)


_OBJECTIVE_WEIGHTS = {
    "extension": {"f3": 1.0, "ripple": 0.15},
    "balanced": {"f3": 0.55, "ripple": 0.55},
    "flat": {"f3": 0.2, "ripple": 1.1},
}


def group_delay_ms(result: SimulationResult) -> np.ndarray:
    """Return the total-output group delay in milliseconds."""
    u_total = result.driver_volume_velocity + result.port_volume_velocity
    w = 2.0 * np.pi * np.asarray(result.frequency_hz, dtype=float)
    phase = np.unwrap(np.angle(u_total))
    return -np.gradient(phase, w) * 1000.0


def response_phase_deg(result: SimulationResult) -> np.ndarray:
    """Return the total acoustic-output phase in degrees, wrapped to ±180.

    The far-field pressure is proportional to ``jw * (Ud + Up)``, so the
    exported phase includes the +90 degree radiation term.
    """
    u_total = result.driver_volume_velocity + result.port_volume_velocity
    w = 2.0 * np.pi * np.asarray(result.frequency_hz, dtype=float)
    return np.degrees(np.angle(1j * w * u_total))


def _export_rows_text(header: str, columns: tuple[np.ndarray, ...]) -> str:
    lines = ["* Load Forge export", f"* {header}"]
    for row in zip(*columns, strict=True):
        values = [float(value) for value in row]
        if all(np.isfinite(value) for value in values):
            lines.append("\t".join(f"{value:.4f}" for value in values))
    return "\n".join(lines) + "\n"


def export_frd_text(result: SimulationResult) -> str:
    """Format the total response as FRD text (freq, SPL dB, phase deg)."""
    return _export_rows_text(
        "freq(Hz)\tSPL(dB)\tphase(deg)",
        (
            np.asarray(result.frequency_hz, dtype=float),
            np.asarray(result.spl_total_db, dtype=float),
            response_phase_deg(result),
        ),
    )


@dataclass(frozen=True)
class ToleranceBand:
    """Percentile SPL band from Monte Carlo T/S perturbation."""

    frequency_hz: np.ndarray
    lower_db: np.ndarray
    upper_db: np.ndarray
    runs: int


def monte_carlo_response_band(
    ts: DriverTS,
    load_type: str = "DCCAV",
    box: DccavBox | ReflexBox | Bandpass4Box | Bandpass6Box | SealedBox | None = None,
    freq_hz: np.ndarray | None = None,
    voltage_v: float = 2.83,
    series_r_ohm: float = 0.0,
    tolerance: float = 0.15,
    runs: int = 120,
    seed: int = 20260714,
    percentiles: tuple[float, float] = (5.0, 95.0),
) -> ToleranceBand:
    """Simulate T/S manufacturing spread as an SPL percentile band.

    Each run multiplies Fs, Vas, Qts and Qms by independent uniform factors in
    ``[1 - tolerance, 1 + tolerance]`` and re-derives the driver; measured
    Mms/Cms/Bl overrides are dropped so the perturbed small-signal set stays
    self-consistent, and Qts is capped just below the perturbed Qms.  The
    enclosure is kept fixed: the band answers "same box, driver unit spread".
    """
    if load_type in {"Suspension pneumatic", "Acoustic suspension"}:
        load_type = "Sealed"
    if not 0.0 <= float(tolerance) < 1.0:
        raise ValueError("Tolerance must be in [0, 1)")
    if int(runs) < 2:
        raise ValueError("Monte Carlo needs at least 2 runs")
    if freq_hz is None:
        freq_hz = np.geomspace(10.0, 500.0, 240)
    freq = np.asarray(freq_hz, dtype=float)
    rng = np.random.default_rng(int(seed))
    curves: list[np.ndarray] = []
    for _ in range(int(runs)):
        f_fs, f_vas, f_qts, f_qms = rng.uniform(
            1.0 - float(tolerance), 1.0 + float(tolerance), size=4)
        qms = ts.qms * f_qms
        sample = DriverTS(
            fs_hz=ts.fs_hz * f_fs,
            vas_l=ts.vas_l * f_vas,
            qts=min(ts.qts * f_qts, qms * 0.99),
            qms=qms,
            re_ohm=ts.re_ohm,
            sd_cm2=ts.sd_cm2,
            le_mh=ts.le_mh,
            xmax_mm=ts.xmax_mm,
            pe_w=ts.pe_w,
            panel_air_load=ts.panel_air_load,
            panel_coupling=ts.panel_coupling,
            radiating_pistons=ts.radiating_pistons,
        )
        try:
            if isinstance(box, ReflexBox):
                result = simulate_reflex(sample, box, freq, voltage_v, series_r_ohm)
            elif isinstance(box, Bandpass4Box):
                result = simulate_bandpass4(sample, box, freq, voltage_v, series_r_ohm)
            elif isinstance(box, Bandpass6Box):
                result = simulate_bandpass6(sample, box, freq, voltage_v, series_r_ohm)
            elif isinstance(box, SealedBox):
                result = simulate_sealed(sample, box, freq, voltage_v, series_r_ohm)
            elif box is None:
                result = simulate_infinite_baffle(sample, freq, voltage_v, series_r_ohm)
            else:
                result = simulate(sample, box, freq, voltage_v, series_r_ohm)
        except ValueError:
            continue
        curves.append(np.asarray(result.spl_total_db, dtype=float))
    if len(curves) < max(2, int(runs) // 4):
        raise ValueError("Too few Monte Carlo runs produced a valid simulation")
    stack = np.vstack(curves)
    lower, upper = np.nanpercentile(stack, list(percentiles), axis=0)
    return ToleranceBand(
        frequency_hz=freq,
        lower_db=np.asarray(lower, dtype=float),
        upper_db=np.asarray(upper, dtype=float),
        runs=len(curves),
    )


@dataclass(frozen=True)
class DesignSpaceMap:
    """Grid of achievable F3/ripple over the box plane for one load type."""

    load_type: str
    x_label: str
    y_label: str
    x_values: np.ndarray
    y_values: np.ndarray
    f3_hz: np.ndarray
    ripple_db: np.ndarray


def _design_space_axes(
    ts: DriverTS, load_type: str, resolution: int,
) -> tuple[np.ndarray, np.ndarray, str, str]:
    n = int(resolution)
    if load_type == "Bass reflex":
        reflex_start = suggest_reflex_alignment(ts)
        return (
            np.geomspace(0.3 * reflex_start.vb_l, 3.0 * reflex_start.vb_l, n),
            np.geomspace(0.55 * reflex_start.fb_hz, 1.6 * reflex_start.fb_hz, n),
            "Vb (L)", "Fb (Hz)",
        )
    if load_type == "Sealed":
        return (
            np.geomspace(0.2 * ts.vas_l, 4.0 * ts.vas_l, n),
            np.array([0.0]),
            "Vb (L)", "",
        )
    if load_type == "Bandpass 4th order":
        bp4_start = suggest_bandpass4_alignment(ts)
        return (
            np.geomspace(0.3 * (bp4_start.vs_l + bp4_start.vp_l),
                         3.0 * (bp4_start.vs_l + bp4_start.vp_l), n),
            np.geomspace(0.55 * bp4_start.fp_hz, 1.6 * bp4_start.fp_hz, n),
            "Vtot (L)", "Fp (Hz)",
        )
    if load_type == "Bandpass 6th order":
        bp6_start = suggest_bandpass6_alignment(ts)
        return (
            np.geomspace(0.3 * (bp6_start.vr_l + bp6_start.vp_l),
                         3.0 * (bp6_start.vr_l + bp6_start.vp_l), n),
            np.geomspace(0.55 * bp6_start.fp_hz, 1.6 * bp6_start.fp_hz, n),
            "Vtot (L)", "Fp (Hz)",
        )
    dccav_start = suggest_alignment(ts)
    vtot = max(dccav_start.vh_l + dccav_start.vl_l, EPS)
    return (
        np.geomspace(0.3 * vtot, 3.0 * vtot, n),
        np.geomspace(0.55 * dccav_start.fl_hz, 1.6 * dccav_start.fl_hz, n),
        "Vtot (L)", "fl (Hz)",
    )


def design_space_box(
    ts: DriverTS,
    load_type: str,
    x: float,
    y: float,
    box_template: DccavBox | ReflexBox | Bandpass4Box | Bandpass6Box | SealedBox | None = None,
) -> DccavBox | ReflexBox | Bandpass4Box | Bandpass6Box | SealedBox:
    """Build the box for one point of the design-space plane.

    ``x``/``y`` follow the atlas axes: reflex `Vb`/`Fb`, sealed `Vb` (y is
    ignored), DCCAV total volume/`fl` with the Vh/Vl split and fh/fl ratio
    taken from the empirical starter.  Loss factors are copied from
    ``box_template`` when one of the matching type is provided.
    """
    if load_type in {"Suspension pneumatic", "Acoustic suspension"}:
        load_type = "Sealed"
    if load_type == "Bass reflex":
        reflex_t = box_template if isinstance(box_template, ReflexBox) else ReflexBox(
            vb_l=ts.vas_l, fb_hz=panel_loaded_fs_hz(ts))
        return ReflexBox(
            vb_l=float(x), fb_hz=float(y),
            q_abs=reflex_t.q_abs, q_leak=reflex_t.q_leak, q_port=reflex_t.q_port,
        )
    if load_type == "Sealed":
        sealed_t = box_template if isinstance(box_template, SealedBox) else SealedBox(
            vb_l=ts.vas_l)
        return SealedBox(vb_l=float(x), q_abs=sealed_t.q_abs, q_leak=sealed_t.q_leak)
    if load_type == "Bandpass 4th order":
        bp4_start = suggest_bandpass4_alignment(ts)
        vtot = max(bp4_start.vs_l + bp4_start.vp_l, EPS)
        vs_ratio = float(np.clip(bp4_start.vs_l / vtot, 0.05, 0.95))
        bp4_t = box_template if isinstance(box_template, Bandpass4Box) else Bandpass4Box(
            vs_l=bp4_start.vs_l, vp_l=bp4_start.vp_l, fp_hz=bp4_start.fp_hz)
        vs_l = max(float(x) * vs_ratio, 0.05)
        return Bandpass4Box(
            vs_l=vs_l, vp_l=max(float(x) - vs_l, 0.05), fp_hz=float(y),
            q_abs_s=bp4_t.q_abs_s, q_abs_p=bp4_t.q_abs_p,
            q_leak_s=bp4_t.q_leak_s, q_leak_p=bp4_t.q_leak_p, q_port=bp4_t.q_port,
        )
    if load_type == "Bandpass 6th order":
        bp6_start = suggest_bandpass6_alignment(ts)
        vtot = max(bp6_start.vr_l + bp6_start.vp_l, EPS)
        vr_ratio = float(np.clip(bp6_start.vr_l / vtot, 0.05, 0.95))
        bp6_t = box_template if isinstance(box_template, Bandpass6Box) else Bandpass6Box(
            vr_l=bp6_start.vr_l, fr_hz=bp6_start.fr_hz, vp_l=bp6_start.vp_l, fp_hz=bp6_start.fp_hz)
        vr_l = max(float(x) * vr_ratio, 0.05)
        return Bandpass6Box(
            vr_l=vr_l, fr_hz=float(y) / max(bp6_start.fr_hz, EPS) * bp6_start.fr_hz,
            vp_l=max(float(x) - vr_l, 0.05), fp_hz=float(y),
            q_abs_r=bp6_t.q_abs_r, q_abs_p=bp6_t.q_abs_p,
            q_leak_r=bp6_t.q_leak_r, q_leak_p=bp6_t.q_leak_p,
            q_port_r=bp6_t.q_port_r, q_port_p=bp6_t.q_port_p,
        )
    if load_type == "Infinite baffle":
        raise ValueError("Infinite baffle has no box parameters to map")
    dccav_start = suggest_alignment(ts)
    vtot = max(dccav_start.vh_l + dccav_start.vl_l, EPS)
    vh_ratio = float(np.clip(dccav_start.vh_l / vtot, 0.05, 0.95))
    fh_ratio = dccav_start.fh_hz / max(dccav_start.fl_hz, EPS)
    dccav_t = box_template if isinstance(box_template, DccavBox) else DccavBox(
        vh_l=dccav_start.vh_l, fh_hz=dccav_start.fh_hz, vl_l=dccav_start.vl_l, fl_hz=dccav_start.fl_hz)
    vh = max(float(x) * vh_ratio, 0.05)
    return DccavBox(
        vh_l=vh, fh_hz=float(y) * fh_ratio,
        vl_l=max(float(x) - vh, 0.05), fl_hz=float(y),
        q_abs_h=dccav_t.q_abs_h, q_abs_l=dccav_t.q_abs_l,
        q_leak_h=dccav_t.q_leak_h, q_leak_l=dccav_t.q_leak_l,
        q_port_h=dccav_t.q_port_h, q_port_l=dccav_t.q_port_l,
    )


def design_space_map(
    ts: DriverTS,
    load_type: str = "Bass reflex",
    box_template: DccavBox | ReflexBox | Bandpass4Box | Bandpass6Box | SealedBox | None = None,
    resolution: int = 15,
    voltage_v: float = 2.83,
) -> DesignSpaceMap:
    """Sweep the box plane and report F3/ripple per grid point.

    Log-spaced axes around the empirical starter: reflex `Vb` (0.3-3x) vs
    `Fb` (0.55-1.6x), DCCAV total volume vs `fl` (same spans, starter Vh/Vl
    split and fh/fl ratio), sealed a 1-D `Vb` sweep (0.2-4x Vas, collapsed y
    axis).  Like the optimizer, the map is evaluated at ``voltage_v`` with
    zero series resistance.  Infinite baffle raises ``ValueError``.
    """
    if load_type in {"Suspension pneumatic", "Acoustic suspension"}:
        load_type = "Sealed"
    if load_type == "Infinite baffle":
        raise ValueError("Infinite baffle has no box parameters to map")
    if int(resolution) < 3:
        raise ValueError("Atlas resolution must be at least 3")
    effective_fs = panel_loaded_fs_hz(ts)
    freq_min = min(10.0, effective_fs / 4.0)
    freq_max = max(400.0, 4.0 * effective_fs)
    freq = (adaptive_frequency_grid(freq_min, freq_max, 80, (effective_fs,))
            if os.getenv("K_SERVICE") else np.geomspace(freq_min, freq_max, 160))
    x_values, y_values, x_label, y_label = _design_space_axes(ts, load_type, resolution)
    f3_grid = np.full((len(y_values), len(x_values)), np.nan)
    ripple_grid = np.full_like(f3_grid, np.nan)
    for iy, y in enumerate(y_values):
        for ix, x in enumerate(x_values):
            try:
                box = design_space_box(ts, load_type, float(x), float(y), box_template)
                metrics = _optimizer_metrics(ts, box, freq, voltage_v)
            except ValueError:
                continue
            f3_grid[iy, ix] = metrics["f3_hz"]
            ripple_grid[iy, ix] = metrics["ripple_db"]
    return DesignSpaceMap(
        load_type=load_type, x_label=x_label, y_label=y_label,
        x_values=x_values, y_values=y_values,
        f3_hz=f3_grid, ripple_db=ripple_grid,
    )



def export_zma_text(result: SimulationResult) -> str:
    """Format the electrical impedance as ZMA text (freq, ohm, phase deg)."""
    magnitude = np.asarray(result.impedance_ohm, dtype=float)
    phase = (
        np.zeros_like(magnitude)
        if result.impedance_phase_deg is None
        else np.asarray(result.impedance_phase_deg, dtype=float)
    )
    return _export_rows_text(
        "freq(Hz)\timpedance(ohm)\tphase(deg)",
        (np.asarray(result.frequency_hz, dtype=float), magnitude, phase),
    )


PORT_VELOCITY_GUIDELINE_MS = 0.05 * SPEED_OF_SOUND
PORT_K_FACTOR = 1.0
# Optimized alignments must remain buildable with the geometry controls exposed
# by the UI.  A small reserve below this limit leaves enough diameter to obtain
# a positive physical duct length instead of a zero-length opening.
OPTIMIZER_MAX_PORT_DIAMETER_CM = 60.0
_OPTIMIZER_PORT_FEASIBILITY_RATIO = 0.95
_OPTIMIZER_DCCAV_F3_RATIO = 0.67


def port_air_velocity_ms(
    result: SimulationResult,
    port_area_cm2: float,
    port: str = "lower",
) -> np.ndarray:
    """Return the linear port air speed `|U|/S` in m/s for the requested port.

    `port` selects `port_l_velocity` (`"lower"`, also the reflex vent) or
    `port_h_velocity` (`"upper"`).  Speeds above `PORT_VELOCITY_GUIDELINE_MS`
    (5% of the speed of sound, ~17 m/s) commonly produce audible chuffing and
    port compression that the lumped model does not simulate.
    """
    _require_positive("port_area_cm2", port_area_cm2)
    if port == "lower":
        u = result.port_l_velocity
    elif port == "upper":
        u = result.port_h_velocity
    else:
        raise ValueError(f"port must be 'lower' or 'upper', got {port!r}")
    return np.abs(np.asarray(u)) / (float(port_area_cm2) * 1e-4)


def port_length_cm(
    volume_l: float,
    fb_hz: float,
    port_diameter_cm: float,
    end_correction: float = 1.43,
) -> float:
    """Return the physical tube length in cm of a circular port.

    Solves the Helmholtz relation `L_eff = c^2 * S / (w^2 * V)` for the
    requested chamber volume and tuning, then subtracts the end correction
    `end_correction * radius`.  The default 1.43 models one flanged (k=0.82)
    plus one free end (k=0.61); use 1.64 (k=0.82+0.82) for a port flanged
    on both ends, such as the DCCAV upper port joining two chambers.

    A non-positive return value means the opening's end corrections alone
    already exceed the required acoustic mass: the diameter is too small for
    this volume/tuning combination and must be increased.
    """
    _require_positive("volume_l", volume_l)
    _require_positive("fb_hz", fb_hz)
    _require_positive("port_diameter_cm", port_diameter_cm)
    radius_m = float(port_diameter_cm) / 200.0
    area_m2 = np.pi * radius_m**2
    w = 2.0 * np.pi * float(fb_hz)
    l_eff_m = SPEED_OF_SOUND**2 * area_m2 / (w**2 * (float(volume_l) / 1000.0))
    return float((l_eff_m - float(end_correction) * radius_m) * 100.0)


def port_max_tuning_hz(
    volume_l: float,
    port_diameter_cm: float,
    end_correction: float = 1.43,
) -> float:
    """Return the highest tuning a zero-length opening of this diameter reaches.

    With no duct at all, the port's acoustic mass is just the end corrections
    `end_correction * radius`; this is the tuning ceiling for the diameter on
    the given volume.  Requesting a higher `fb` needs a larger diameter.
    """
    _require_positive("volume_l", volume_l)
    _require_positive("port_diameter_cm", port_diameter_cm)
    radius_m = float(port_diameter_cm) / 200.0
    area_m2 = np.pi * radius_m**2
    l_eff_m = float(end_correction) * radius_m
    volume_m3 = float(volume_l) / 1000.0
    return float(
        SPEED_OF_SOUND / (2.0 * np.pi) * np.sqrt(area_m2 / (volume_m3 * l_eff_m))
    )


@dataclass(frozen=True)
class DriverReferenceMetrics:
    """Classical small-signal reference metrics derived from the T/S set."""

    eta0: float
    spl_1w_db: float
    spl_2v83_db: float
    ebp_hz: float


def driver_reference_metrics(ts: DriverTS) -> DriverReferenceMetrics:
    """Return reference efficiency, sensitivity and EBP for the driver.

    `eta0 = 4*pi^2 * Fs^3 * Vas / (c^3 * Qes)` is the half-space reference
    efficiency (fraction).  `spl_1w_db` converts it to SPL at 1 W / 1 m using
    the module's `RHO_AIR`/`SPEED_OF_SOUND`/`P_REF`; `spl_2v83_db` rescales to
    2.83 V across `Re`.  `ebp_hz = Fs / Qes` is the efficiency bandwidth
    product: below ~50 the driver favours sealed/infinite-baffle loads, above
    ~100 ported loads, in between either.
    """
    drv = complete_driver(ts)
    vas_m3 = ts.vas_l / 1000.0
    effective_fs = panel_loaded_fs_hz(ts)
    eta0 = 4.0 * np.pi**2 * effective_fs**3 * vas_m3 / (SPEED_OF_SOUND**3 * drv.qes)
    spl_ref_db = 10.0 * np.log10(RHO_AIR * SPEED_OF_SOUND / (2.0 * np.pi * P_REF**2))
    spl_1w_db = spl_ref_db + 10.0 * np.log10(eta0)
    spl_2v83_db = spl_1w_db + 10.0 * np.log10(2.83**2 / ts.re_ohm)
    return DriverReferenceMetrics(
        eta0=float(eta0),
        spl_1w_db=float(spl_1w_db),
        spl_2v83_db=float(spl_2v83_db),
        ebp_hz=float(effective_fs / drv.qes),
    )


@dataclass(frozen=True)
class DriverBandwidthClass:
    """Heuristic usable-bandwidth classification of a driver from its T/S set."""

    driver_class: str
    f_le_hz: float | None
    mass_density_g_cm2: float
    spl_1w_db: float
    reasons: tuple[str, ...]


DRIVER_CLASSES = ("Subwoofer", "Woofer", "Midbass-capable")

_driver_configurations = ["Single driver"]
_driver_configurations.extend(
    f"{count} × {wiring}"
    for count in range(2, 9)
    for wiring in ("parallel", "series")
)
_driver_configurations.extend(
    f"{series}S × {parallel}P mixed"
    for series in range(2, 9)
    for parallel in range(2, 9)
    if series * parallel <= 8
)
_driver_configurations.extend(("Isobaric pair (parallel)", "Isobaric pair (series)"))
_driver_configurations.extend(
    f"{count} × isobaric ({wiring})"
    for count in range(4, 17, 2)
    for wiring in ("parallel", "series")
)
DRIVER_CONFIGURATIONS = tuple(_driver_configurations)


def apply_driver_configuration(ts: DriverTS, configuration: str) -> DriverTS:
    """Return the composite T/S set for identical drivers sharing one box.

    The small-signal alignment parameters (Fs, Qts, Qms) are invariant for
    identical drivers; the composite scales the size-, power- and
    impedance-related fields:

    - ordinary arrays: Sd, Vas, Pe and radiating-piston count scale with the
      number of drivers; the selected series/parallel network sets Re and Le
    - isobaric arrays: every coupled pair contributes one radiating piston,
      half one driver's Vas and twice one driver's thermal power

    Measured Mms/Cms/Bl overrides are dropped so the composite set is
    re-derived self-consistently.
    """
    if configuration not in DRIVER_CONFIGURATIONS:
        raise ValueError(f"Unknown driver configuration: {configuration}")
    if configuration == "Single driver":
        return ts
    legacy_isobaric = configuration.startswith("Isobaric")
    isobaric = legacy_isobaric or "isobaric" in configuration
    if legacy_isobaric:
        driver_count = 2
    elif "mixed" in configuration:
        mixed_match = re.match(r"(\d+)S\s*×\s*(\d+)P", configuration)
        if mixed_match is None:
            raise ValueError(f"Invalid mixed configuration: {configuration}")
        series_count, parallel_count = map(int, mixed_match.groups())
        driver_count = series_count * parallel_count
    else:
        count_match = re.match(r"(\d+)\s*×", configuration)
        if count_match is None:
            raise ValueError(f"Invalid driver configuration: {configuration}")
        driver_count = int(count_match.group(1))
    if isobaric and driver_count % 2:
        raise ValueError("Isobaric configurations require an even driver count")
    if "mixed" in configuration:
        electrical_scale = series_count / parallel_count
    elif "series" in configuration:
        electrical_scale = float(driver_count)
    else:
        electrical_scale = 1.0 / float(driver_count)
    if isobaric:
        pair_count = driver_count // 2
        sd_scale = float(pair_count)
        vas_scale = float(pair_count) / 2.0
        radiating_pistons = pair_count
    else:
        sd_scale = vas_scale = float(driver_count)
        radiating_pistons = driver_count
    return DriverTS(
        fs_hz=ts.fs_hz,
        vas_l=ts.vas_l * vas_scale,
        qts=ts.qts,
        qms=ts.qms,
        re_ohm=ts.re_ohm * electrical_scale,
        sd_cm2=ts.sd_cm2 * sd_scale,
        le_mh=ts.le_mh * electrical_scale,
        xmax_mm=ts.xmax_mm,
        pe_w=ts.pe_w * driver_count,
        panel_air_load=ts.panel_air_load,
        panel_coupling=ts.panel_coupling,
        radiating_pistons=ts.radiating_pistons * radiating_pistons,
    )


def classify_driver_bandwidth(ts: DriverTS) -> DriverBandwidthClass:
    """Classify a driver as pure subwoofer, generic woofer or midbass-capable.

    The strongest available indicator is the voice-coil corner
    `f_Le = Re / (2*pi*Le)`: above it the coil inductance rolls the response
    off, so a low corner marks a sub that cannot reach the mids.  Supporting
    indicators are the moving-mass surface density `Mms/Sd`, the free-air
    resonance `Fs` and the 1 W / 1 m reference sensitivity.  Points:

    - `f_Le < 400 Hz` -> sub (weight 2); `f_Le > 800 Hz` -> midbass (weight 2)
    - `Fs <= 35 Hz` -> sub; `Fs >= 45 Hz` -> midbass
    - `Mms/Sd >= 0.30 g/cm^2` -> sub; `<= 0.15 g/cm^2` -> midbass
    - `SPL(1 W) <= 90 dB` -> sub; `>= 94 dB` -> midbass

    The verdict requires a margin of two points; otherwise the driver is a
    generic `Woofer`.  When `Le` is unknown (0), `f_le_hz` is `None` and the
    class relies on the remaining indicators.  Cone breakup and directivity
    are not part of the T/S set, so this is a catalog-screening heuristic,
    not a substitute for the manufacturer's frequency response.
    """
    drv = complete_driver(ts)
    ref = driver_reference_metrics(ts)
    f_le_hz = None
    if ts.le_mh and ts.le_mh > 0:
        f_le_hz = float(ts.re_ohm / (2.0 * np.pi * ts.le_mh / 1000.0))
    mass_density = float(drv.mms_kg * 1000.0 / ts.sd_cm2)

    sub_points = 0
    mid_points = 0
    reasons: list[str] = []
    if f_le_hz is not None:
        if f_le_hz < 400.0:
            sub_points += 2
            reasons.append(f"voice-coil corner {f_le_hz:.0f} Hz")
        elif f_le_hz > 800.0:
            mid_points += 2
            reasons.append(f"voice-coil corner {f_le_hz:.0f} Hz")
    else:
        reasons.append("Le unknown")
    if ts.fs_hz <= 35.0:
        sub_points += 1
        reasons.append(f"Fs {ts.fs_hz:.0f} Hz")
    elif ts.fs_hz >= 45.0:
        mid_points += 1
        reasons.append(f"Fs {ts.fs_hz:.0f} Hz")
    if mass_density >= 0.30:
        sub_points += 1
        reasons.append(f"heavy cone {mass_density:.2f} g/cm2")
    elif mass_density <= 0.15:
        mid_points += 1
        reasons.append(f"light cone {mass_density:.2f} g/cm2")
    if ref.spl_1w_db <= 90.0:
        sub_points += 1
        reasons.append(f"sensitivity {ref.spl_1w_db:.1f} dB/1W")
    elif ref.spl_1w_db >= 94.0:
        mid_points += 1
        reasons.append(f"sensitivity {ref.spl_1w_db:.1f} dB/1W")

    if sub_points - mid_points >= 2:
        driver_class = "Subwoofer"
    elif mid_points - sub_points >= 2:
        driver_class = "Midbass-capable"
    else:
        driver_class = "Woofer"
    return DriverBandwidthClass(
        driver_class=driver_class,
        f_le_hz=f_le_hz,
        mass_density_g_cm2=mass_density,
        spl_1w_db=float(ref.spl_1w_db),
        reasons=tuple(reasons),
    )


def port_min_diameter_cm(
    volume_l: float,
    fb_hz: float,
    end_correction: float = 1.43,
) -> float:
    """Return the smallest circular-port diameter that can reach `fb_hz`.

    Solves `c^2 * S / (w^2 * V) = end_correction * radius` for the diameter at
    which the physical duct length becomes zero; any smaller opening tunes
    below `fb_hz` even with no tube.
    """
    _require_positive("volume_l", volume_l)
    _require_positive("fb_hz", fb_hz)
    w = 2.0 * np.pi * float(fb_hz)
    radius_m = float(end_correction) * w**2 * (float(volume_l) / 1000.0) / (
        SPEED_OF_SOUND**2 * np.pi
    )
    return float(radius_m * 200.0)


PORT_MAX_VOLUME_FRACTION = 0.10
PORT_PIPE_RESONANCE_GUARD = 4.0


def port_max_straight_length_cm(volume_l: float) -> float:
    """Rough ceiling for a straight duct inside a box of this volume.

    The enclosure's internal shape isn't modeled here (only its volume), so
    this treats it as a cube: `side_cm = (volume_l * 1000) ** (1/3)`.  A duct
    longer than that cannot run in a straight line from the driver panel to
    the opposite wall without folding into an L-shaped/slot port, whose
    acoustics this model does not simulate.  A small chamber can pass the
    10% duct-volume-fraction directive while still needing a duct far longer
    than the box itself (a thin, deeply-tuned vent moves little air per
    length, so volume stays low even as length grows unboundedly) - this is
    the separate, absolute check that catches that case.  A rough guideline,
    not an exact geometric fact: a tall, narrow enclosure could fit a longer
    straight duct along its longest axis than a flat, wide one.
    """
    _require_positive("volume_l", volume_l)
    return float((float(volume_l) * 1000.0) ** (1.0 / 3.0))


def port_displacement_min_diameter_cm(ts: DriverTS, fb_hz: float) -> float:
    """Return the minimum vent diameter from the driver's maximum displacement.

    Uses the port-area gold standard ``S >= K * (2*pi*Fb*Sd*Xmax) / v_amm``
    where ``K`` is the prudence factor ``PORT_K_FACTOR`` and ``v_amm`` is the
    ``PORT_VELOCITY_GUIDELINE_MS``.  Drive-independent: protects the vent from
    compression at rated excursion even when the drive voltage is low.
    Drivers without a published Xmax return 0.0.
    """
    _require_positive("fb_hz", fb_hz)
    sd_m2 = float(ts.sd_cm2) / 10_000.0
    xmax_m = float(ts.xmax_mm) / 1_000.0
    vd_max = sd_m2 * xmax_m
    if vd_max <= 0.0:
        return 0.0
    s_port_m2 = (
        PORT_K_FACTOR * 2.0 * np.pi * float(fb_hz) * vd_max
        / PORT_VELOCITY_GUIDELINE_MS
    )
    return float(200.0 * np.sqrt(s_port_m2 / np.pi))


def port_volume_fraction(
    volume_l: float,
    fb_hz: float,
    diameter_cm: float,
    end_correction: float = 1.43,
) -> float:
    """Fraction of the chamber volume occupied by the duct itself.

    The duct is the Helmholtz cylinder `port_length_cm()` requires for the
    given tuning.  Classic reflex practice keeps this below
    `PORT_MAX_VOLUME_FRACTION` (~10%): a longer/fatter duct displaces the
    chamber it tunes and the lumped model stops being reliable.  Returns 0.0
    when the diameter cannot reach the tuning at all (negative length, flagged
    separately by the zero-length warning).
    """
    length_cm = port_length_cm(volume_l, fb_hz, diameter_cm, end_correction)
    if length_cm <= 0.0:
        return 0.0
    duct_l = np.pi * (float(diameter_cm) / 2.0) ** 2 * length_cm / 1000.0
    return float(duct_l / float(volume_l))


def port_pipe_resonance_hz(length_cm: float) -> float:
    """First half-wave (organ-pipe) resonance of the duct, `c / (2 L)`.

    Approximation on the physical length; keeping it above
    `PORT_PIPE_RESONANCE_GUARD` times the tuning keeps the duct's own
    standing wave out of the vented passband.
    """
    _require_positive("length_cm", length_cm)
    return float(SPEED_OF_SOUND / (2.0 * float(length_cm) / 100.0))


def port_velocity_diameter_cm(peak_volume_velocity_m3s: float, margin: float = 1.05) -> float:
    """Minimum port diameter keeping peak volume velocity within the guideline.

    `margin` (default 1.05, a 5% pad) keeps the applied diameter from sitting
    exactly on the `PORT_VELOCITY_GUIDELINE_MS` edge.  Shared by the optimizer
    feasibility metric and the UI's applied port sizing so both floor the
    same port at the same diameter.
    """
    area_cm2 = float(peak_volume_velocity_m3s) / PORT_VELOCITY_GUIDELINE_MS * 1e4
    return float(margin * 2.0 * np.sqrt(max(area_cm2, 0.0) / np.pi))


def rated_velocity_diameter_cm(
    ts: DriverTS,
    result: SimulationResult,
    sim_voltage_v: float,
    volume_velocity: np.ndarray,
) -> float:
    """Velocity floor at the driver's excursion limit instead of the sim voltage.

    At low simulation voltages (e.g. 2.83 V) a powerful driver barely moves,
    making the velocity floor negligible.  This helper scales the peak port
    volume velocity to the excursion-limited drive level so the port is sized
    for real-world usage.  Falls back to the raw velocity floor when the
    simulation voltage is already below 2.83 V (test / low-power paths) or
    when Xmax is unpublished.
    """
    peak_vv = float(np.nanmax(np.abs(volume_velocity)))
    if ts.xmax_mm <= 0 or sim_voltage_v < 2.83:
        return port_velocity_diameter_cm(peak_vv)
    peak_exc = float(np.nanmax(result.excursion_mm))
    if peak_exc <= 0 or peak_exc >= ts.xmax_mm:
        return port_velocity_diameter_cm(peak_vv)
    scale = ts.xmax_mm / peak_exc
    return port_velocity_diameter_cm(peak_vv * scale)


def port_diameter_for_load(
    volume_l: float,
    fb_hz: float,
    end_correction: float,
    floor_cm: float,
    max_diameter_cm: float = OPTIMIZER_MAX_PORT_DIAMETER_CM,
    target_length_cm: float = 5.0,
    grid_cm: float = 0.5,
) -> float | None:
    """Pick the diameter actually applied to one duct, honoring every directive.

    `floor_cm` bundles the mandatory minima this port must clear (the
    zero-length tuning boundary, the displacement golden rule, the 5%-of-c
    air-speed requirement): the returned diameter is never smaller.  Above
    that floor, the diameter grows toward `target_length_cm` (a fabricable
    physical tube instead of a flush hole) - but `port_length_cm()` and
    `port_volume_fraction()` both grow monotonically with diameter for
    `diameter_cm >= port_min_diameter_cm(...)`, so growing purely to reach a
    "nice" length can just as easily blow the duct past
    `PORT_MAX_VOLUME_FRACTION` of the chamber.  This function stops that
    growth at the volume-fraction cap even if the resulting duct stays
    shorter than `target_length_cm`.

    The result is snapped to `grid_cm` (the sidebar's 0.5 cm control step).
    Snapping rounds *down* whenever that stays at or above the (grid-aligned)
    floor: the duct-volume cap is a soft ceiling that rounding up would
    silently re-break, since the raw optimum can sit exactly on that
    boundary and the fraction curve is steep there.  Only when the raw
    optimum has no headroom above the floor does the mandatory floor win
    over the cap.

    Returns `None` when `floor_cm` alone already exceeds the volume-fraction
    cap: no diameter can satisfy every directive for this volume/tuning
    pair, and the box itself (not the port) needs to change.
    """
    _require_positive("volume_l", volume_l)
    _require_positive("fb_hz", fb_hz)
    floor_cm = np.ceil(max(float(floor_cm), 1.0) / grid_cm) * grid_cm
    if port_volume_fraction(
            volume_l, fb_hz, floor_cm, end_correction) > PORT_MAX_VOLUME_FRACTION:
        return None
    # Duct fraction grows monotonically with diameter above the floor:
    # bisect for the diameter where it crosses the cap.
    if port_volume_fraction(
            volume_l, fb_hz, max_diameter_cm, end_correction,
    ) <= PORT_MAX_VOLUME_FRACTION:
        fraction_cap_cm = max_diameter_cm
    else:
        low_cm, high_cm = floor_cm, max_diameter_cm
        for _ in range(40):
            mid_cm = 0.5 * (low_cm + high_cm)
            if port_volume_fraction(
                    volume_l, fb_hz, mid_cm, end_correction,
            ) <= PORT_MAX_VOLUME_FRACTION:
                low_cm = mid_cm
            else:
                high_cm = mid_cm
        fraction_cap_cm = low_cm
    if port_length_cm(
            volume_l, fb_hz, fraction_cap_cm, end_correction) < target_length_cm:
        # Even the largest fraction-compliant diameter yields a short duct;
        # that is the best available compromise.
        raw_cm = fraction_cap_cm
    else:
        # Smallest diameter in [floor_cm, fraction_cap_cm] reaching the length target.
        low_cm, high_cm = floor_cm, fraction_cap_cm
        for _ in range(40):
            mid_cm = 0.5 * (low_cm + high_cm)
            if port_length_cm(volume_l, fb_hz, mid_cm, end_correction) < target_length_cm:
                low_cm = mid_cm
            else:
                high_cm = mid_cm
        raw_cm = high_cm
    floor_rounded_cm = np.floor(raw_cm / grid_cm) * grid_cm
    if floor_rounded_cm >= floor_cm:
        return float(floor_rounded_cm)
    return float(np.ceil(raw_cm / grid_cm) * grid_cm)


def _optimizer_metrics(
    ts: DriverTS,
    box: DccavBox | ReflexBox | Bandpass4Box | Bandpass6Box | SealedBox,
    freq: np.ndarray,
    voltage_v: float,
) -> dict[str, float]:
    is_bandpass4 = isinstance(box, Bandpass4Box)
    is_bandpass6 = isinstance(box, Bandpass6Box)

    def velocity_diameter_cm(volume_velocity: np.ndarray) -> float:
        return rated_velocity_diameter_cm(ts, result, voltage_v, volume_velocity)

    def sized_port(
        volume_l: float, tuning_hz: float, end_correction: float, floor_cm: float,
    ) -> tuple[float, float, float]:
        """Diameter this port would get, its duct-volume fraction, and its
        length-vs-box-fit ratio (>1 means longer than the box can plausibly
        take in a straight run).

        Mirrors the UI's `_optimized_port_diameter_cm`: growing toward a
        fabricable ~5 cm duct never overrides the 10% duct-volume directive.
        When even the mandatory floor breaks that directive, report the floor
        itself (a normal, finite, buildable diameter) rather than `inf`: the
        smoothly-varying fraction/ratio at that floor is what should reject
        the box, via the score checks below. Collapsing this case to an
        infinite diameter would flatten the score across the whole
        infeasible region and blind the pattern search to which direction
        actually reduces the duct - exactly the plateau that stalled the
        search on tight reflex boxes.
        """
        sized_cm = port_diameter_for_load(volume_l, tuning_hz, end_correction, floor_cm)
        if sized_cm is None:
            # port_diameter_for_load rejects on the *grid-rounded* floor (the
            # diameter that would actually be built); report the fraction at
            # that same rounded value, not the raw floor, or a floor whose
            # continuous fraction looks compliant can still round up to a
            # duct that breaks the directive without the score reflecting it.
            sized_cm = np.ceil(max(float(floor_cm), 1.0) / 0.5) * 0.5
        fraction = port_volume_fraction(volume_l, tuning_hz, sized_cm, end_correction)
        length_cm = port_length_cm(volume_l, tuning_hz, sized_cm, end_correction)
        max_length_cm = port_max_straight_length_cm(volume_l)
        length_ratio = max(length_cm, 0.0) / max_length_cm
        return sized_cm, fraction, length_ratio

    if isinstance(box, ReflexBox):
        result = simulate_reflex(ts, box, freq, voltage_v)
        vtot = box.vb_l
        fl = box.fb_hz
        floor_cm = max(
            port_min_diameter_cm(box.vb_l, box.fb_hz, 1.43),
            port_displacement_min_diameter_cm(ts, box.fb_hz),
            velocity_diameter_cm(result.port_l_velocity),
        )
        required_port_diameter_cm, port_volume_fraction_max, port_length_ratio_max = sized_port(
            box.vb_l, box.fb_hz, 1.43, floor_cm)
    elif isinstance(box, Bandpass4Box):
        result = simulate_bandpass4(ts, box, freq, voltage_v)
        vtot = box.vs_l + box.vp_l
        fl = box.fp_hz
        floor_cm = max(
            port_min_diameter_cm(box.vp_l, box.fp_hz, 1.43),
            port_displacement_min_diameter_cm(ts, box.fp_hz),
            velocity_diameter_cm(result.port_l_velocity),
        )
        required_port_diameter_cm, port_volume_fraction_max, port_length_ratio_max = sized_port(
            box.vp_l, box.fp_hz, 1.43, floor_cm)
    elif isinstance(box, Bandpass6Box):
        result = simulate_bandpass6(ts, box, freq, voltage_v)
        vtot = box.vr_l + box.vp_l
        fl = min(box.fr_hz, box.fp_hz)
        rear_floor_cm = max(
            port_min_diameter_cm(box.vr_l, box.fr_hz, 1.43),
            port_displacement_min_diameter_cm(ts, box.fr_hz),
            velocity_diameter_cm(result.port_h_velocity),
        )
        front_floor_cm = max(
            port_min_diameter_cm(box.vp_l, box.fp_hz, 1.43),
            port_displacement_min_diameter_cm(ts, box.fp_hz),
            velocity_diameter_cm(result.port_l_velocity),
        )
        rear_d, rear_f, rear_lr = sized_port(box.vr_l, box.fr_hz, 1.43, rear_floor_cm)
        front_d, front_f, front_lr = sized_port(box.vp_l, box.fp_hz, 1.43, front_floor_cm)
        required_port_diameter_cm = max(rear_d, front_d)
        port_volume_fraction_max = max(rear_f, front_f)
        port_length_ratio_max = max(rear_lr, front_lr)
    elif isinstance(box, SealedBox):
        result = simulate_sealed(ts, box, freq, voltage_v)
        vtot = box.vb_l
        fl = sealed_system_metrics(ts, box)[0]
        required_port_diameter_cm = 0.0
        port_volume_fraction_max = 0.0
        port_length_ratio_max = 0.0
    else:
        result = simulate(ts, box, freq, voltage_v)
        vtot = box.vh_l + box.vl_l
        fl = box.fl_hz
        # Each port must satisfy its own minima; the duct-volume directive is
        # then checked against the chamber that hosts each duct.
        upper_floor_cm = max(
            port_min_diameter_cm(box.vh_l, box.fh_hz, 1.64),
            port_displacement_min_diameter_cm(ts, box.fh_hz),
            velocity_diameter_cm(result.port_h_velocity),
        )
        lower_floor_cm = max(
            port_min_diameter_cm(box.vl_l, box.fl_hz, 1.43),
            port_displacement_min_diameter_cm(ts, box.fl_hz),
            velocity_diameter_cm(result.port_l_velocity),
        )
        upper_diameter_cm, upper_fraction, upper_length_ratio = sized_port(
            box.vh_l, box.fh_hz, 1.64, upper_floor_cm)
        lower_diameter_cm, lower_fraction, lower_length_ratio = sized_port(
            box.vl_l, box.fl_hz, 1.43, lower_floor_cm)
        required_port_diameter_cm = max(upper_diameter_cm, lower_diameter_cm)
        port_volume_fraction_max = max(upper_fraction, lower_fraction)
        port_length_ratio_max = max(upper_length_ratio, lower_length_ratio)
    thresholds = response_threshold_frequencies(result)
    f3 = thresholds[3]
    f10 = thresholds[10]
    f = result.frequency_hz
    spl = result.spl_total_db

    ripple = float("nan")
    gd_max = float("nan")
    f_high = float("nan")
    if np.isfinite(f3):
        if is_bandpass4 or is_bandpass6:
            peak_idx = int(np.nanargmax(spl))
            f_high = _high_side_crossing(
                f[peak_idx:], spl[peak_idx:], float(spl[peak_idx]) - 3.0)
            upper = min(float(f.max()), 0.90 * f_high) if np.isfinite(f_high) else float(f.max())
        else:
            upper = min(float(f.max()), max(200.0, 2.0 * f3))
        band = (f >= 1.2 * f3) & (f <= upper)
        if np.any(band):
            ripple = float(np.nanmax(spl[band]) - np.nanmin(spl[band]))
            gd = group_delay_ms(result)
            gd_band = (f >= f3) & (f <= upper)
            gd_max = float(np.nanmax(gd[gd_band])) if np.any(gd_band) else float("nan")

    exc_ratio = float("nan")
    if ts.xmax_mm > 0:
        exc_floor = f10 if np.isfinite(f10) else (f3 if np.isfinite(f3) else float(f.min()))
        exc_band = f >= exc_floor
        if np.any(exc_band):
            exc_ratio = float(np.nanmax(result.excursion_mm[exc_band]) / ts.xmax_mm)

    return {
        "f3_hz": f3,
        "f10_hz": f10,
        "ripple_db": ripple,
        "excursion_ratio": exc_ratio,
        "group_delay_ms": gd_max,
        "f_high_hz": f_high,
        "total_volume_l": float(vtot),
        "fl_hz": float(fl),
        "max_spl_db": float(np.nanmax(spl)),
        "required_port_diameter_cm": float(required_port_diameter_cm),
        "port_volume_fraction": float(port_volume_fraction_max),
        "port_length_over_box_ratio": float(port_length_ratio_max),
        "sealed_fc_hz": equivalent_sealed_fc_hz(ts, box),
    }


def _score_alignment(
    metrics: dict[str, float], goals: OptimizationGoals, ts: DriverTS,
    is_dccav: bool, is_bandpass4: bool = False,
) -> float:
    f3 = metrics["f3_hz"]
    if not np.isfinite(f3):
        return 1e6
    # These are construction/credibility boundaries, not soft preferences.
    # Keeping them above every normal objective score prevents the search from
    # buying fake extension with an impossible port or an invalid DCCAV F3.
    port_limit_cm = (
        _OPTIMIZER_PORT_FEASIBILITY_RATIO * OPTIMIZER_MAX_PORT_DIAMETER_CM)
    required_port_diameter_cm = metrics["required_port_diameter_cm"]
    if required_port_diameter_cm > port_limit_cm:
        return 1e5 + required_port_diameter_cm / port_limit_cm
    # Reflex directive: the smallest workable duct must not displace more
    # than PORT_MAX_VOLUME_FRACTION of the chamber it tunes.
    port_fraction = metrics.get("port_volume_fraction", 0.0)
    if port_fraction > PORT_MAX_VOLUME_FRACTION:
        return 1e5 + port_fraction / PORT_MAX_VOLUME_FRACTION
    # A duct can stay a small fraction of a large chamber while still being
    # longer than fits inside it in a straight run (a thin, deep-tuned vent
    # moves little air per length, so volume stays low as length grows
    # unboundedly) - a separate, absolute check from the fraction above.
    port_length_ratio = metrics.get("port_length_over_box_ratio", 0.0)
    if port_length_ratio > 1.0:
        return 1e5 + port_length_ratio
    dccav_f3_ratio = 0.65 if goals.objective == "extension" else _OPTIMIZER_DCCAV_F3_RATIO
    if is_dccav and f3 < dccav_f3_ratio * metrics["fl_hz"]:
        return 1e5 + metrics["fl_hz"] / max(f3, EPS)
    weights = _OBJECTIVE_WEIGHTS[goals.objective]
    deepest_extension = (
        goals.objective == "extension" and not goals.target_f3_hz
    )
    # Once the hard construction/credibility boundaries above are satisfied,
    # Max extension must let lower F3 dominate advisory response penalties.
    advisory_scale = 0.01 if deepest_extension else 1.0
    ripple = metrics["ripple_db"]
    score = (
        weights["f3"]
        * (max(f3, goals.target_f3_hz) if goals.target_f3_hz else f3)
        / panel_loaded_fs_hz(ts)
    )
    if np.isfinite(ripple):
        score += weights["ripple"] * ripple / 6.0
        if goals.max_ripple_db and goals.max_ripple_db > 0 and ripple > goals.max_ripple_db:
            score += advisory_scale * 2.0 * (
                ripple - goals.max_ripple_db)
    if goals.target_f3_hz and f3 > goals.target_f3_hz:
        score += 0.5 * (f3 - goals.target_f3_hz) / goals.target_f3_hz
    exc_ratio = metrics["excursion_ratio"]
    if goals.max_excursion_ratio and goals.max_excursion_ratio > 0 and np.isfinite(exc_ratio):
        if exc_ratio > goals.max_excursion_ratio:
            score += advisory_scale * 4.0 * (
                exc_ratio - goals.max_excursion_ratio)
    gd = metrics["group_delay_ms"]
    if goals.max_group_delay_ms and np.isfinite(gd) and gd > goals.max_group_delay_ms:
        score += advisory_scale * (
            gd / goals.max_group_delay_ms - 1.0)
    if goals.max_total_volume_l and metrics["total_volume_l"] > goals.max_total_volume_l:
        score += 20.0 * (metrics["total_volume_l"] / goals.max_total_volume_l - 1.0)
    if goals.min_spl_db:
        peak_spl = metrics.get("max_spl_db", float("-inf"))
        if peak_spl < goals.min_spl_db:
            score += 4.0 * (goals.min_spl_db - peak_spl) / goals.min_spl_db
    if is_bandpass4:
        f_high = metrics["f_high_hz"]
        if not np.isfinite(f_high):
            score += 10.0
        elif f_high < 1.4 * f3:
            score += 10.0 * (1.4 * f3 / max(f_high, EPS) - 1.0)
    if f3 < 0.50 * metrics["sealed_fc_hz"]:
        score += 5.0
    # Size regularizer so equal-scoring boxes prefer the smaller build; once a
    # requested F3 target is met, extra litres stop buying score elsewhere, so
    # push harder toward the compact solution.
    target_f3 = goals.target_f3_hz
    target_met = target_f3 is not None and target_f3 > 0 and f3 <= target_f3
    size_weight = 0.15 if target_met else (0.002 if deepest_extension else 0.02)
    score += size_weight * metrics["total_volume_l"] / max(ts.vas_l, EPS)
    return float(score)


_DEFAULT_GOALS = OptimizationGoals()


def optimize_alignment(
    ts: DriverTS,
    goals: OptimizationGoals = _DEFAULT_GOALS,
    load_type: str = "DCCAV",
    box_template: DccavBox | ReflexBox | Bandpass4Box | Bandpass6Box | SealedBox | None = None,
    voltage_v: float = 2.83,
    max_evaluations: int = 260,
    fixed_total_volume_l: float | None = None,
) -> OptimizedAlignment:
    """Search box parameters that best meet the requested goals.

    The search is a bounded compass pattern search in log-space, started from
    the empirical article alignment (DCCAV), Vas/Fs reflex starting point or
    classical closed-box alignment.  Loss factors are copied from
    ``box_template`` when provided.
    """
    if goals.objective not in _OBJECTIVE_WEIGHTS:
        raise ValueError(f"Unknown optimizer objective: {goals.objective}")
    if load_type in {"Suspension pneumatic", "Acoustic suspension"}:
        # Backward compatibility with .lfp/API values written before the
        # closed-box load was renamed to the plain "Sealed" label.
        load_type = "Sealed"
    _require_positive("Voltage", voltage_v)
    effective_fs = panel_loaded_fs_hz(ts)
    freq = np.geomspace(min(10.0, effective_fs / 4.0), max(400.0, 4.0 * effective_fs), 160)
    if load_type not in {"DCCAV", "Bandpass 4th order", "Bandpass 6th order", "Bass reflex", "Sealed"}:
        if load_type == "Infinite baffle":
            raise ValueError("Infinite baffle has no box parameters to optimize")
        raise ValueError(f"Unknown load type: {load_type}")
    is_reflex = load_type == "Bass reflex"
    is_bandpass4 = load_type == "Bandpass 4th order"
    is_bandpass6 = load_type == "Bandpass 6th order"
    is_sealed = load_type == "Sealed"
    is_dccav = load_type == "DCCAV"
    cap = goals.max_total_volume_l
    minimum_volume_l = 0.10 if (is_dccav or is_bandpass4 or is_bandpass6) else 0.05
    if cap is not None:
        _require_positive("Max total volume", cap)
        if cap < minimum_volume_l:
            raise ValueError(
                f"Max total volume must be at least {minimum_volume_l:.2f} L for {load_type}"
            )
    if fixed_total_volume_l is not None:
        _require_positive("Fixed total volume", fixed_total_volume_l)
        if fixed_total_volume_l < minimum_volume_l:
            raise ValueError(
                f"Fixed total volume must be at least {minimum_volume_l:.2f} L for {load_type}"
            )
        if cap is not None and fixed_total_volume_l > cap + EPS:
            raise ValueError("Fixed total volume cannot exceed the maximum total volume")

    build: BoxBuilder

    if is_reflex:
        reflex_start = suggest_reflex_alignment(ts)
        vb0, fb0 = reflex_start.vb_l, reflex_start.fb_hz
        if fixed_total_volume_l is not None:
            vb0 = float(fixed_total_volume_l)
        elif cap and vb0 > cap:
            vb0 = 0.95 * cap
        reflex_template = box_template if isinstance(box_template, ReflexBox) else ReflexBox(vb_l=vb0, fb_hz=fb0)

        def build_reflex(p: np.ndarray) -> ReflexBox:
            vb, fb = np.exp(p)
            if fixed_total_volume_l is not None:
                vb = float(fixed_total_volume_l)
            elif cap is not None:
                vb = min(float(vb), float(cap))
            return ReflexBox(
                vb_l=float(vb), fb_hz=float(fb),
                q_abs=reflex_template.q_abs, q_leak=reflex_template.q_leak,
                q_port=reflex_template.q_port,
            )

        build = build_reflex

        p0 = np.log([vb0, fb0])
        lower = np.log([max(0.05, vb0 / 8.0), max(5.0, fb0 / 3.0)])
        upper = np.log([vb0 * 8.0, fb0 * 2.5])
    elif is_bandpass4:
        bp4_start = suggest_bandpass4_alignment(ts)
        vs0, vp0, fp0 = bp4_start.vs_l, bp4_start.vp_l, bp4_start.fp_hz
        if fixed_total_volume_l is not None:
            scale = float(fixed_total_volume_l) / (vs0 + vp0)
            vs0 *= scale
            vp0 *= scale
        elif cap and vs0 + vp0 > cap:
            scale = 0.98 * cap / (vs0 + vp0)
            vs0 *= scale
            vp0 *= scale
        bp4_template = box_template if isinstance(box_template, Bandpass4Box) else Bandpass4Box(
            vs_l=vs0, vp_l=vp0, fp_hz=fp0)

        def build_bandpass4(p: np.ndarray) -> Bandpass4Box:
            vs_l, vp_l, fp_hz = np.exp(p)
            projected_volume_l = fixed_total_volume_l
            if projected_volume_l is None and cap is not None and vs_l + vp_l > cap:
                projected_volume_l = float(cap)
            if projected_volume_l is not None:
                available = float(projected_volume_l) - 0.10
                weights = np.maximum(np.array([vs_l, vp_l]) - 0.05, 0.0)
                if float(weights.sum()) <= 0.0:
                    weights[:] = 0.5
                else:
                    weights /= float(weights.sum())
                vs_l, vp_l = 0.05 + available * weights
            return Bandpass4Box(
                vs_l=float(vs_l), vp_l=float(vp_l), fp_hz=float(fp_hz),
                q_abs_s=bp4_template.q_abs_s, q_abs_p=bp4_template.q_abs_p,
                q_leak_s=bp4_template.q_leak_s, q_leak_p=bp4_template.q_leak_p,
                q_port=bp4_template.q_port,
            )

        build = build_bandpass4

        p0 = np.log([vs0, vp0, fp0])
        lower = np.log([
            max(0.05, vs0 / 8.0), max(0.05, vp0 / 8.0), max(5.0, fp0 / 3.0)])
        upper = np.log([vs0 * 8.0, vp0 * 8.0, fp0 * 2.5])
    elif is_bandpass6:
        bp6_start = suggest_bandpass6_alignment(ts)
        vr0, fr0, vp0, fp0 = bp6_start.vr_l, bp6_start.fr_hz, bp6_start.vp_l, bp6_start.fp_hz
        if fixed_total_volume_l is not None:
            scale = float(fixed_total_volume_l) / (vr0 + vp0)
            vr0 *= scale
            vp0 *= scale
        elif cap and vr0 + vp0 > cap:
            scale = 0.98 * cap / (vr0 + vp0)
            vr0 *= scale
            vp0 *= scale
        bp6_template = box_template if isinstance(box_template, Bandpass6Box) else Bandpass6Box(
            vr_l=vr0, fr_hz=fr0, vp_l=vp0, fp_hz=fp0)

        def build_bandpass6(p: np.ndarray) -> Bandpass6Box:
            vr_l, fr_hz, vp_l, fp_hz = np.exp(p)
            projected_volume_l = fixed_total_volume_l
            if projected_volume_l is None and cap is not None and vr_l + vp_l > cap:
                projected_volume_l = float(cap)
            if projected_volume_l is not None:
                available = float(projected_volume_l) - 0.10
                weights = np.maximum(np.array([vr_l, vp_l]) - 0.05, 0.0)
                if float(weights.sum()) <= 0.0:
                    weights[:] = 0.5
                else:
                    weights /= float(weights.sum())
                vr_l, vp_l = 0.05 + available * weights
            return Bandpass6Box(
                vr_l=float(vr_l), fr_hz=float(fr_hz),
                vp_l=float(vp_l), fp_hz=float(fp_hz),
                q_abs_r=bp6_template.q_abs_r, q_abs_p=bp6_template.q_abs_p,
                q_leak_r=bp6_template.q_leak_r, q_leak_p=bp6_template.q_leak_p,
                q_port_r=bp6_template.q_port_r, q_port_p=bp6_template.q_port_p,
            )

        build = build_bandpass6

        p0 = np.log([vr0, fr0, vp0, fp0])
        lower = np.log([
            max(0.05, vr0 / 8.0), max(5.0, fr0 / 3.0),
            max(0.05, vp0 / 8.0), max(5.0, fp0 / 3.0)])
        upper = np.log([vr0 * 8.0, fr0 * 2.5, vp0 * 8.0, fp0 * 2.5])
    elif is_sealed:
        sealed_start = suggest_sealed_alignment(ts)
        vb0 = sealed_start.vb_l
        if fixed_total_volume_l is not None:
            vb0 = float(fixed_total_volume_l)
        elif cap and vb0 > cap:
            vb0 = 0.95 * cap
        sealed_template = box_template if isinstance(box_template, SealedBox) else SealedBox(vb_l=vb0)

        def build_sealed(p: np.ndarray) -> SealedBox:
            vb = float(np.exp(p[0]))
            if fixed_total_volume_l is not None:
                vb = float(fixed_total_volume_l)
            elif cap is not None:
                vb = min(vb, float(cap))
            return SealedBox(vb_l=vb, q_abs=sealed_template.q_abs, q_leak=sealed_template.q_leak)

        build = build_sealed

        p0 = np.log([vb0])
        lower = np.log([max(0.05, vb0 / 12.0)])
        upper = np.log([vb0 * 12.0])
    else:
        dccav_start = suggest_alignment(ts)
        vh0, vl0, fl0 = dccav_start.vh_l, dccav_start.vl_l, dccav_start.fl_hz
        # The fh/fl ratio stays in a band around the article's 2.6 so the load
        # keeps its double-resonator character instead of degenerating into a
        # single reflex volume with an extreme upper tuning.
        ratio0 = float(np.clip(dccav_start.fh_hz / dccav_start.fl_hz, 1.2, 4.5))
        if fixed_total_volume_l is not None:
            scale = float(fixed_total_volume_l) / (vh0 + vl0)
            vh0 *= scale
            vl0 *= scale
        elif cap and vh0 + vl0 > cap:
            scale = 0.98 * cap / (vh0 + vl0)
            vh0 *= scale
            vl0 *= scale
        dccav_template = box_template if isinstance(box_template, DccavBox) else DccavBox(
            vh_l=vh0, fh_hz=fl0 * ratio0, vl_l=vl0, fl_hz=fl0
        )

        def build_dccav(p: np.ndarray) -> DccavBox:
            vh, vl, fl, ratio = np.exp(p)
            projected_volume_l = fixed_total_volume_l
            if projected_volume_l is None and cap is not None and vh + vl > cap:
                projected_volume_l = float(cap)
            if projected_volume_l is not None:
                # Preserve both positive chamber minima while projecting every
                # candidate onto the requested total-volume boundary.
                available = float(projected_volume_l) - 0.10
                weights = np.maximum(np.array([vh, vl], dtype=float) - 0.05, 0.0)
                weight_total = float(weights.sum())
                if weight_total <= 0.0:
                    weights[:] = 0.5
                else:
                    weights /= weight_total
                vh, vl = 0.05 + available * weights
            return DccavBox(
                vh_l=float(vh), fh_hz=float(fl * ratio), vl_l=float(vl), fl_hz=float(fl),
                q_abs_h=dccav_template.q_abs_h, q_abs_l=dccav_template.q_abs_l,
                q_leak_h=dccav_template.q_leak_h, q_leak_l=dccav_template.q_leak_l,
                q_port_h=dccav_template.q_port_h, q_port_l=dccav_template.q_port_l,
            )

        build = build_dccav

        p0 = np.log([vh0, vl0, fl0, ratio0])
        lower = np.log([max(0.05, vh0 / 6.0), max(0.05, vl0 / 6.0), max(5.0, fl0 / 3.0), 1.2])
        upper = np.log([vh0 * 6.0, vl0 * 6.0, fl0 * 3.0, 4.5])

    evaluations = 0

    def evaluate(p: np.ndarray):
        nonlocal evaluations
        evaluations += 1
        box = build(np.clip(p, lower, upper))
        try:
            metrics = _optimizer_metrics(ts, box, freq, voltage_v)
        except (ValueError, FloatingPointError):
            return box, None, float("inf")
        return box, metrics, _score_alignment(
            metrics, goals, ts, is_dccav, is_bandpass4)

    def compass_search(start_p: np.ndarray):
        """One coordinate-descent run from `start_p`; a purely local method."""
        cur_p = np.clip(start_p, lower, upper)
        cur_box, cur_metrics, cur_score = evaluate(cur_p)
        if cur_metrics is None:
            return cur_p, cur_box, cur_metrics, cur_score
        step = 0.4
        while step >= 0.02 and evaluations < max_evaluations:
            improved = False
            for axis in range(len(cur_p)):
                for sign in (1.0, -1.0):
                    if evaluations >= max_evaluations:
                        break
                    candidate = cur_p.copy()
                    candidate[axis] += sign * step
                    candidate = np.clip(candidate, lower, upper)
                    if np.allclose(candidate, cur_p):
                        continue
                    box, metrics, score = evaluate(candidate)
                    if metrics is not None and score < cur_score - 1e-9:
                        cur_p, cur_box, cur_metrics, cur_score = candidate, box, metrics, score
                        improved = True
            if not improved:
                step *= 0.5
        return cur_p, cur_box, cur_metrics, cur_score

    # Untargeted DCCAV extension has a second, physically meaningful basin:
    # larger chambers at approximately the empirical tuning. Coordinate
    # descent cannot cross the compact mid-bass basin to reach it. Make that
    # the primary seed so even the Finder's short optimization budget searches
    # the correct region; keep the empirical compact seed as a fallback.
    restart_points: list[np.ndarray] = []
    primary_p = np.clip(p0, lower, upper)
    if is_dccav and goals.objective == "extension" and not goals.target_f3_hz:
        deep_p = p0.copy()
        deep_p[0] += np.log(3.0)
        deep_p[1] += np.log(3.0)
        deep_p = np.clip(deep_p, lower, upper)
        _, deep_metrics, deep_score = evaluate(deep_p)
        if deep_metrics is not None and deep_score < 1e5:
            primary_p = deep_p
            restart_points.append(np.clip(p0, lower, upper))

    _, best_box, best_metrics, best_score = compass_search(primary_p)
    if best_metrics is None:
        raise ValueError("The starting alignment could not be simulated")

    # The empirical starting point can sit in a construction-infeasible
    # neighborhood (e.g. a driver whose golden-rule/velocity port floor makes
    # every nearby box need an over-long duct) that local coordinate descent
    # can't climb out of, even though a compliant box exists elsewhere in the
    # search bounds. A handful of deterministic restarts along the search
    # box's diagonal costs little and reliably reaches those regions without
    # sacrificing reproducibility (no randomness).
    if best_score >= 1e5:
        restart_points.extend(
            lower + fraction * (upper - lower)
            for fraction in (0.75, 0.25, 0.5)
        )
    for restart_p in restart_points:
        if evaluations >= max_evaluations:
            break
        _, box, metrics, score = compass_search(restart_p)
        if metrics is not None and score < best_score:
            best_box, best_metrics, best_score = box, metrics, score

    if best_score >= 1e5:
        raise ValueError(
            "No credible alignment with buildable, low-velocity ports was found; "
            "relax the volume/response goals or reduce drive voltage"
        )

    return OptimizedAlignment(
        box=best_box,
        f3_hz=float(best_metrics["f3_hz"]),
        f10_hz=float(best_metrics["f10_hz"]),
        ripple_db=float(best_metrics["ripple_db"]),
        excursion_ratio=float(best_metrics["excursion_ratio"]),
        group_delay_ms=float(best_metrics["group_delay_ms"]),
        total_volume_l=float(best_metrics["total_volume_l"]),
        score=float(best_score),
        evaluations=evaluations,
    )


def simulate(
    ts: DriverTS,
    box: DccavBox,
    freq_hz: np.ndarray | None = None,
    voltage_v: float = 2.83,
    series_r_ohm: float = 0.0,
) -> SimulationResult:
    """Simulate DCCAV SPL, cone excursion and electrical impedance."""
    drv = complete_driver(ts)
    if freq_hz is None:
        freq_hz = np.geomspace(10.0, 500.0, 500)
    f = np.asarray(freq_hz, dtype=float)
    if np.any(f <= 0):
        raise ValueError("Frequencies must be positive")
    _require_positive("Voltage", voltage_v)
    _validate_box(box)

    w = 2.0 * np.pi * f
    jw = 1j * w

    re_total, rat, p_source = _electrical_source(ts, drv, voltage_v, series_r_ohm)
    z_as = rat + jw * drv.mas + 1.0 / (jw * drv.cas)
    z_ab_h = _box_impedance(box.vh_l, box.fh_hz, box.q_abs_h, box.q_leak_h, w)
    z_ab_l = _box_impedance(box.vl_l, box.fl_hz, box.q_abs_l, box.q_leak_l, w)
    z_ap_h = _port_impedance(box.vh_l, box.fh_hz, box.q_port_h, w)
    z_ap_l = _port_impedance(box.vl_l, box.fl_hz, box.q_port_l, w)

    ya = 1.0 / z_as
    yab_h = 1.0 / z_ab_h
    yab_l = 1.0 / z_ab_l
    yap_h = 1.0 / z_ap_h
    yap_l = 1.0 / z_ap_l
    i_source = p_source / z_as

    # Closed-form solve of the symmetric 2x2 nodal system
    # [[y11, -yph], [-yph, y22]] @ [node_a, node_b] = [i_source, 0].
    y11 = ya + yab_h + yap_h
    y22 = yap_h + yab_l + yap_l
    det = y11 * y22 - yap_h * yap_h
    node_a = i_source * y22 / det
    node_b = i_source * yap_h / det

    # The solved driver flow enters the rear DCCAV load. The exposed cone front
    # radiates with the opposite sign and is what must be summed externally.
    u_rear_driver = (p_source - node_a) / z_as
    u_front_driver = -u_rear_driver
    u_port_h = (node_a - node_b) / z_ap_h
    u_port_l = node_b / z_ap_l
    u_total = u_front_driver + u_port_l

    spl_total = _spl_from_volume_velocity(u_total, f)
    spl_driver = _spl_from_volume_velocity(u_front_driver, f)
    spl_port = _spl_from_volume_velocity(u_port_l, f)
    excursion = np.abs(u_rear_driver / (jw * drv.sd_m2)) * 1000.0
    mil_w, mol_db = _limit_curves(ts, voltage_v, spl_total, excursion, series_r_ohm)

    z_mech = drv.rms_n_s_m + jw * drv.mms_kg + 1.0 / (jw * drv.cms_m_per_n)
    z_load = _parallel(z_ab_h, z_ap_h + _parallel(z_ab_l, z_ap_l)) * drv.sd_m2**2
    z_e = re_total + jw * (ts.le_mh / 1000.0) + drv.bl_tm**2 / (z_mech + z_load)

    return SimulationResult(
        frequency_hz=f,
        spl_total_db=spl_total,
        spl_driver_db=spl_driver,
        spl_port_db=spl_port,
        excursion_mm=excursion,
        impedance_ohm=np.abs(z_e),
        impedance_phase_deg=np.degrees(np.angle(z_e)),
        port_h_velocity=np.abs(u_port_h),
        port_l_velocity=np.abs(u_port_l),
        mil_w=mil_w,
        mol_db=mol_db,
        driver_volume_velocity=u_front_driver,
        port_volume_velocity=u_port_l,
    )


def simulate_reflex(
    ts: DriverTS,
    box: ReflexBox,
    freq_hz: np.ndarray | None = None,
    voltage_v: float = 2.83,
    series_r_ohm: float = 0.0,
) -> SimulationResult:
    """Simulate a normal one-volume bass-reflex load."""
    drv = complete_driver(ts)
    if freq_hz is None:
        freq_hz = np.geomspace(10.0, 500.0, 500)
    f = np.asarray(freq_hz, dtype=float)
    if np.any(f <= 0):
        raise ValueError("Frequencies must be positive")
    _require_positive("Voltage", voltage_v)
    _validate_reflex_box(box)

    w = 2.0 * np.pi * f
    jw = 1j * w

    re_total, rat, p_source = _electrical_source(ts, drv, voltage_v, series_r_ohm)
    z_as = rat + jw * drv.mas + 1.0 / (jw * drv.cas)
    z_ab = _box_impedance(box.vb_l, box.fb_hz, box.q_abs, box.q_leak, w)
    z_ap = _port_impedance(box.vb_l, box.fb_hz, box.q_port, w)

    ya = 1.0 / z_as
    yab = 1.0 / z_ab
    yap = 1.0 / z_ap
    i_source = p_source / z_as
    node = i_source / (ya + yab + yap)

    u_rear_driver = (p_source - node) / z_as
    u_front_driver = -u_rear_driver
    u_port = node / z_ap
    u_total = u_front_driver + u_port

    spl_total = _spl_from_volume_velocity(u_total, f)
    spl_driver = _spl_from_volume_velocity(u_front_driver, f)
    spl_port = _spl_from_volume_velocity(u_port, f)
    excursion = np.abs(u_rear_driver / (jw * drv.sd_m2)) * 1000.0
    mil_w, mol_db = _limit_curves(ts, voltage_v, spl_total, excursion, series_r_ohm)

    z_mech = drv.rms_n_s_m + jw * drv.mms_kg + 1.0 / (jw * drv.cms_m_per_n)
    z_load = _parallel(z_ab, z_ap) * drv.sd_m2**2
    z_e = re_total + jw * (ts.le_mh / 1000.0) + drv.bl_tm**2 / (z_mech + z_load)

    return SimulationResult(
        frequency_hz=f,
        spl_total_db=spl_total,
        spl_driver_db=spl_driver,
        spl_port_db=spl_port,
        excursion_mm=excursion,
        impedance_ohm=np.abs(z_e),
        impedance_phase_deg=np.degrees(np.angle(z_e)),
        port_h_velocity=np.zeros_like(f),
        port_l_velocity=np.abs(u_port),
        mil_w=mil_w,
        mol_db=mol_db,
        driver_volume_velocity=u_front_driver,
        port_volume_velocity=u_port,
    )


def _pr_impedance(box: PassiveRadiatorBox, w: np.ndarray) -> np.ndarray:
    """Passive radiator acoustic impedance Rap + jw*Map + 1/(jw*Cap)."""
    sp_m2 = box.pr_sp_cm2 / 10_000.0
    mmp_kg = (box.pr_mmp_g + box.pr_added_mass_g) / 1_000.0
    fp_hz = passive_radiator_effective_fp_hz(box)
    cmp_m_per_n = 1.0 / ((2.0 * np.pi * fp_hz) ** 2 * mmp_kg)
    rmp = 2.0 * np.pi * fp_hz * mmp_kg / max(box.pr_qmp, 0.1)
    cap = cmp_m_per_n * sp_m2 ** 2
    map_ = mmp_kg / sp_m2 ** 2
    rap = rmp / sp_m2 ** 2
    return rap + 1j * w * map_ + 1.0 / (1j * w * cap)


def simulate_passive_radiator(
    ts: DriverTS,
    box: PassiveRadiatorBox,
    freq_hz: np.ndarray | None = None,
    voltage_v: float = 2.83,
    series_r_ohm: float = 0.0,
) -> SimulationResult:
    """Simulate a driver in a vented box loaded by a passive radiator."""
    drv = complete_driver(ts)
    if freq_hz is None:
        freq_hz = np.geomspace(10.0, 500.0, 500)
    f = np.asarray(freq_hz, dtype=float)
    if np.any(f <= 0):
        raise ValueError("Frequencies must be positive")
    _require_positive("Voltage", voltage_v)
    _validate_pr_box(box)

    w = 2.0 * np.pi * f
    jw = 1j * w

    re_total, rat, p_source = _electrical_source(ts, drv, voltage_v, series_r_ohm)
    z_as = rat + jw * drv.mas + 1.0 / (jw * drv.cas)
    z_ab = _box_impedance(box.vb_l, box.pr_fp_hz, box.q_abs, box.q_leak, w)
    z_pr = _pr_impedance(box, w)

    ya = 1.0 / z_as
    yab = 1.0 / z_ab
    ypr = 1.0 / z_pr
    i_source = p_source / z_as
    node = i_source / (ya + yab + ypr)

    u_rear_driver = (p_source - node) / z_as
    u_front_driver = -u_rear_driver
    u_radiator = node / z_pr
    u_total = u_front_driver + u_radiator

    spl_total = _spl_from_volume_velocity(u_total, f)
    spl_driver = _spl_from_volume_velocity(u_front_driver, f)
    spl_radiator = _spl_from_volume_velocity(u_radiator, f)
    excursion = np.abs(u_rear_driver / (jw * drv.sd_m2)) * 1000.0
    mil_w, mol_db = _limit_curves(ts, voltage_v, spl_total, excursion, series_r_ohm)

    z_mech = drv.rms_n_s_m + jw * drv.mms_kg + 1.0 / (jw * drv.cms_m_per_n)
    z_load = _parallel(z_ab, z_pr) * drv.sd_m2**2
    z_e = re_total + jw * (ts.le_mh / 1000.0) + drv.bl_tm**2 / (z_mech + z_load)

    return SimulationResult(
        frequency_hz=f,
        spl_total_db=spl_total,
        spl_driver_db=spl_driver,
        spl_port_db=spl_radiator,
        excursion_mm=excursion,
        impedance_ohm=np.abs(z_e),
        impedance_phase_deg=np.degrees(np.angle(z_e)),
        port_h_velocity=np.zeros_like(f),
        port_l_velocity=np.abs(u_radiator),
        mil_w=mil_w,
        mol_db=mol_db,
        driver_volume_velocity=u_front_driver,
        port_volume_velocity=u_radiator,
    )


def suggest_pr_alignment(ts: DriverTS, pr_box: PassiveRadiatorBox | None = None) -> PassiveRadiatorBox:
    """Suggest a PR-loaded box tuned near Fs, reusing supplied PR parameters."""
    vb_l = float(ts.vas_l)
    if pr_box is not None:
        return PassiveRadiatorBox(
            vb_l=vb_l,
            pr_sp_cm2=pr_box.pr_sp_cm2,
            pr_fp_hz=pr_box.pr_fp_hz,
            pr_qmp=pr_box.pr_qmp,
            pr_mmp_g=pr_box.pr_mmp_g,
            pr_added_mass_g=pr_box.pr_added_mass_g,
            pr_xmax_mm=pr_box.pr_xmax_mm,
        )
    return PassiveRadiatorBox(
        vb_l=vb_l, pr_sp_cm2=ts.sd_cm2, pr_fp_hz=panel_loaded_fs_hz(ts))


def _validate_pr_box(box: PassiveRadiatorBox) -> None:
    _require_positive("Vb", box.vb_l)
    _require_positive("PR Sp", box.pr_sp_cm2)
    _require_positive("PR Fp", box.pr_fp_hz)
    _require_positive("PR Qmp", box.pr_qmp)
    _require_positive("PR Mmp", box.pr_mmp_g)
    if box.pr_added_mass_g < 0.0:
        raise ValueError("PR added mass must be non-negative")


def passive_radiator_effective_fp_hz(box: PassiveRadiatorBox) -> float:
    """Return PR resonance after adding mass while keeping Cms unchanged."""
    _require_positive("PR Mmp", box.pr_mmp_g)
    if box.pr_added_mass_g < 0.0:
        raise ValueError("PR added mass must be non-negative")
    return float(box.pr_fp_hz * np.sqrt(box.pr_mmp_g / (box.pr_mmp_g + box.pr_added_mass_g)))


def suggest_bandpass6_alignment(
    ts: DriverTS, target_qbp: float = 0.707,
) -> Bandpass6Alignment:
    """Return an asymmetric sixth-order dual-vented starter alignment.

    The two ports radiate from opposite sides of the enclosed cone.  Equal
    chambers and tunings therefore cancel externally instead of forming a
    usable passband.  A practical first pass uses a rear chamber near Vas and
    a front chamber about half that size, with tunings around mounted Fs and
    twice mounted Fs respectively.  ``target_qbp`` retains the established
    volume scaling while avoiding the invalid symmetrical starter.
    """
    _require_positive("Target Qbp", target_qbp)
    vb = 2.0 * target_qbp ** 2 * ts.vas_l
    fb = panel_loaded_fs_hz(ts)
    return Bandpass6Alignment(
        vr_l=max(0.05, vb),
        fr_hz=fb,
        vp_l=max(0.05, 0.5 * vb),
        fp_hz=2.0 * fb,
    )


def simulate_bandpass6(
    ts: DriverTS,
    box: Bandpass6Box,
    freq_hz: np.ndarray | None = None,
    voltage_v: float = 2.83,
    series_r_ohm: float = 0.0,
) -> SimulationResult:
    """Simulate a sixth-order bandpass (ported rear, ported front).

    Both chambers are vented; their ports are the only external radiators.
    ``spl_driver_db`` is an internal-cone diagnostic kept for completeness.
    """
    drv = complete_driver(ts)
    if freq_hz is None:
        freq_hz = np.geomspace(10.0, 500.0, 500)
    f = np.asarray(freq_hz, dtype=float)
    if np.any(f <= 0):
        raise ValueError("Frequencies must be positive")
    _require_positive("Voltage", voltage_v)
    _validate_bandpass6_box(box)

    w = 2.0 * np.pi * f
    jw = 1j * w
    re_total, rat, p_source = _electrical_source(ts, drv, voltage_v, series_r_ohm)
    z_as = rat + jw * drv.mas + 1.0 / (jw * drv.cas)

    z_rear_box = _box_impedance(box.vr_l, box.fr_hz, box.q_abs_r, box.q_leak_r, w)
    z_rear_port = _port_impedance(box.vr_l, box.fr_hz, box.q_port_r, w)
    z_rear = _parallel(z_rear_box, z_rear_port)

    z_front_box = _box_impedance(box.vp_l, box.fp_hz, box.q_abs_p, box.q_leak_p, w)
    z_front_port = _port_impedance(box.vp_l, box.fp_hz, box.q_port_p, w)
    z_front = _parallel(z_front_box, z_front_port)

    u_cone = p_source / (z_as + z_rear + z_front)
    p_rear = u_cone * z_rear
    p_front = u_cone * z_front

    u_rear_port = p_rear / z_rear_port
    u_front_port = p_front / z_front_port
    # The ports radiate opposite sides of the diaphragm.  Their external
    # pressures therefore have opposite acoustic polarity; AFW likewise
    # predicts complete cancellation when chambers and tunings are equal.
    u_total = u_rear_port - u_front_port

    spl_total = _spl_from_volume_velocity(u_total, f)
    spl_front = _spl_from_volume_velocity(u_front_port, f)
    spl_rear = _spl_from_volume_velocity(u_rear_port, f)
    excursion = np.abs(u_cone / (jw * drv.sd_m2)) * 1000.0
    mil_w, mol_db = _limit_curves(ts, voltage_v, spl_total, excursion, series_r_ohm)

    z_mech = drv.rms_n_s_m + jw * drv.mms_kg + 1.0 / (jw * drv.cms_m_per_n)
    z_load = (z_rear + z_front) * drv.sd_m2 ** 2
    z_e = re_total + jw * (ts.le_mh / 1000.0) + drv.bl_tm ** 2 / (z_mech + z_load)

    return SimulationResult(
        frequency_hz=f,
        spl_total_db=spl_total,
        spl_driver_db=spl_front,
        spl_port_db=spl_rear,
        excursion_mm=excursion,
        impedance_ohm=np.abs(z_e),
        impedance_phase_deg=np.degrees(np.angle(z_e)),
        port_h_velocity=np.abs(u_rear_port),
        port_l_velocity=np.abs(u_front_port),
        mil_w=mil_w,
        mol_db=mol_db,
        driver_volume_velocity=u_cone,
        port_volume_velocity=u_front_port,
    )


def _validate_bandpass6_box(box: Bandpass6Box) -> None:
    _require_positive("Vr", box.vr_l)
    _require_positive("Fr", box.fr_hz)
    _require_positive("Vp", box.vp_l)
    _require_positive("Fp", box.fp_hz)


def simulate_bandpass4(
    ts: DriverTS,
    box: Bandpass4Box,
    freq_hz: np.ndarray | None = None,
    voltage_v: float = 2.83,
    series_r_ohm: float = 0.0,
) -> SimulationResult:
    """Simulate a fourth-order bandpass (sealed rear, vented front) load.

    The cone is enclosed between the two chambers, so it contributes no
    direct far-field radiation.  ``spl_driver_db`` remains an internal-cone
    diagnostic, while total response, phase and group delay come from the
    front-chamber vent alone.
    """
    drv = complete_driver(ts)
    if freq_hz is None:
        freq_hz = np.geomspace(10.0, 500.0, 500)
    f = np.asarray(freq_hz, dtype=float)
    if np.any(f <= 0):
        raise ValueError("Frequencies must be positive")
    _require_positive("Voltage", voltage_v)
    _validate_bandpass4_box(box)

    w = 2.0 * np.pi * f
    jw = 1j * w
    re_total, rat, p_source = _electrical_source(ts, drv, voltage_v, series_r_ohm)
    z_as = rat + jw * drv.mas + 1.0 / (jw * drv.cas)

    rear_fc_hz, _ = sealed_system_metrics(ts, SealedBox(vb_l=box.vs_l))
    z_rear = _box_impedance(
        box.vs_l, rear_fc_hz, box.q_abs_s, box.q_leak_s, w)
    z_front_box = _box_impedance(
        box.vp_l, box.fp_hz, box.q_abs_p, box.q_leak_p, w)
    z_port = _port_impedance(box.vp_l, box.fp_hz, box.q_port, w)
    z_front = _parallel(z_front_box, z_port)

    # The same cone volume velocity loads both sides of the enclosed driver;
    # their acoustic impedances therefore add in series at the diaphragm.
    u_cone = p_source / (z_as + z_rear + z_front)
    p_front = u_cone * z_front
    u_port = p_front / z_port
    u_radiating_cone = np.zeros_like(u_cone)

    spl_total = _spl_from_volume_velocity(u_port, f)
    spl_driver = _spl_from_volume_velocity(-u_cone, f)
    spl_port = spl_total.copy()
    excursion = np.abs(u_cone / (jw * drv.sd_m2)) * 1000.0
    mil_w, mol_db = _limit_curves(ts, voltage_v, spl_total, excursion, series_r_ohm)

    z_mech = drv.rms_n_s_m + jw * drv.mms_kg + 1.0 / (jw * drv.cms_m_per_n)
    z_load = (z_rear + z_front) * drv.sd_m2**2
    z_e = re_total + jw * (ts.le_mh / 1000.0) + drv.bl_tm**2 / (z_mech + z_load)

    return SimulationResult(
        frequency_hz=f,
        spl_total_db=spl_total,
        spl_driver_db=spl_driver,
        spl_port_db=spl_port,
        excursion_mm=excursion,
        impedance_ohm=np.abs(z_e),
        impedance_phase_deg=np.degrees(np.angle(z_e)),
        port_h_velocity=np.zeros_like(f),
        port_l_velocity=np.abs(u_port),
        mil_w=mil_w,
        mol_db=mol_db,
        driver_volume_velocity=u_radiating_cone,
        port_volume_velocity=u_port,
    )


def _unported_result(
    ts: DriverTS,
    drv: DerivedDriver,
    f: np.ndarray,
    voltage_v: float,
    u_rear_driver: np.ndarray,
    z_load: np.ndarray | complex | float,
    series_r_ohm: float = 0.0,
) -> SimulationResult:
    """Build common sealed/IB outputs from rearward cone volume velocity."""
    w = 2.0 * np.pi * f
    jw = 1j * w
    u_front_driver = -u_rear_driver
    spl_driver = _spl_from_volume_velocity(u_front_driver, f)
    excursion = np.abs(u_rear_driver / (jw * drv.sd_m2)) * 1000.0
    mil_w, mol_db = _limit_curves(ts, voltage_v, spl_driver, excursion, series_r_ohm)
    z_mech = drv.rms_n_s_m + jw * drv.mms_kg + 1.0 / (jw * drv.cms_m_per_n)
    z_e = (
        ts.re_ohm + float(series_r_ohm)
        + jw * (ts.le_mh / 1000.0) + drv.bl_tm**2 / (z_mech + z_load)
    )
    zero_real = np.zeros_like(f)
    zero_complex = np.zeros_like(f, dtype=complex)
    return SimulationResult(
        frequency_hz=f,
        spl_total_db=spl_driver.copy(),
        spl_driver_db=spl_driver,
        spl_port_db=_spl_from_volume_velocity(zero_complex, f),
        excursion_mm=excursion,
        impedance_ohm=np.abs(z_e),
        impedance_phase_deg=np.degrees(np.angle(z_e)),
        port_h_velocity=zero_real.copy(),
        port_l_velocity=zero_real.copy(),
        mil_w=mil_w,
        mol_db=mol_db,
        driver_volume_velocity=u_front_driver,
        port_volume_velocity=zero_complex,
    )


def simulate_sealed(
    ts: DriverTS,
    box: SealedBox,
    freq_hz: np.ndarray | None = None,
    voltage_v: float = 2.83,
    series_r_ohm: float = 0.0,
) -> SimulationResult:
    """Simulate a closed-box (acoustic-suspension) loudspeaker."""
    drv = complete_driver(ts)
    if freq_hz is None:
        freq_hz = np.geomspace(10.0, 500.0, 500)
    f = np.asarray(freq_hz, dtype=float)
    if np.any(f <= 0):
        raise ValueError("Frequencies must be positive")
    _require_positive("Voltage", voltage_v)
    _validate_sealed_box(box)

    w = 2.0 * np.pi * f
    jw = 1j * w
    re_total, rat, p_source = _electrical_source(ts, drv, voltage_v, series_r_ohm)
    z_as = rat + jw * drv.mas + 1.0 / (jw * drv.cas)
    fc_hz, _qtc = sealed_system_metrics(ts, box)
    z_ab = _box_impedance(box.vb_l, fc_hz, box.q_abs, box.q_leak, w)
    node = (p_source / z_as) / (1.0 / z_as + 1.0 / z_ab)
    u_rear_driver = (p_source - node) / z_as
    return _unported_result(
        ts,
        drv,
        f,
        voltage_v,
        u_rear_driver,
        z_ab * drv.sd_m2**2,
        series_r_ohm,
    )


def simulate_infinite_baffle(
    ts: DriverTS,
    freq_hz: np.ndarray | None = None,
    voltage_v: float = 2.83,
    series_r_ohm: float = 0.0,
) -> SimulationResult:
    """Simulate free-air driver motion with rear radiation fully isolated."""
    drv = complete_driver(ts)
    if freq_hz is None:
        freq_hz = np.geomspace(10.0, 500.0, 500)
    f = np.asarray(freq_hz, dtype=float)
    if np.any(f <= 0):
        raise ValueError("Frequencies must be positive")
    _require_positive("Voltage", voltage_v)
    w = 2.0 * np.pi * f
    jw = 1j * w
    re_total, rat, p_source = _electrical_source(ts, drv, voltage_v, series_r_ohm)
    z_as = rat + jw * drv.mas + 1.0 / (jw * drv.cas)
    u_rear_driver = p_source / z_as
    return _unported_result(ts, drv, f, voltage_v, u_rear_driver, 0.0, series_r_ohm)


def response_metrics(result: SimulationResult) -> dict[str, float]:
    """Compute compact response metrics for the UI and tests."""
    spl = result.spl_total_db
    thresholds = response_threshold_frequencies(result)
    return {
        "max_spl_db": float(np.nanmax(spl)),
        "f3_hz": thresholds[3],
        "max_excursion_mm": float(np.nanmax(result.excursion_mm)),
        "min_impedance_ohm": float(np.nanmin(result.impedance_ohm)),
    }


def impedance_peak_frequencies(
    result: SimulationResult,
    min_ratio_to_minimum: float = 1.2,
) -> list[float]:
    """Return local impedance peak frequencies above a minimum-relative threshold."""
    z = np.asarray(result.impedance_ohm, dtype=float)
    f = np.asarray(result.frequency_hz, dtype=float)
    if f.ndim != 1 or z.ndim != 1 or len(f) != len(z) or len(f) < 3:
        raise ValueError("Impedance arrays must be one-dimensional and aligned")
    threshold = float(np.nanmin(z)) * float(min_ratio_to_minimum)
    peaks = [
        float(f[i])
        for i in range(1, len(z) - 1)
        if z[i] > z[i - 1] and z[i] >= z[i + 1] and z[i] > threshold
    ]
    return peaks


def response_threshold_frequencies(
    result: SimulationResult,
    drops_db: tuple[int, ...] = (3, 6, 10),
    reference_band_hz: tuple[float, float] = (40.0, 200.0),
) -> dict[int, float]:
    """Return low-frequency response crossings at ref - drop dB."""
    f = np.asarray(result.frequency_hz, dtype=float)
    spl = np.asarray(result.spl_total_db, dtype=float)
    if f.ndim != 1 or spl.ndim != 1 or len(f) != len(spl) or len(f) < 2:
        raise ValueError("Response arrays must be one-dimensional and aligned")

    f_min, f_max = reference_band_hz
    band = (f >= f_min) & (f <= f_max)
    ref_values = spl[band] if np.any(band) else spl
    ref = float(np.nanmax(ref_values))
    ref_idx = int(np.nanargmax(np.where(band, spl, -np.inf))) if np.any(band) else int(np.nanargmax(spl))
    low_f = f[:ref_idx + 1]
    low_spl = spl[:ref_idx + 1]

    out: dict[int, float] = {}
    for drop in drops_db:
        target = ref - float(drop)
        out[int(drop)] = _low_side_crossing(low_f, low_spl, target)
    return out


def equivalent_sealed_fc_hz(
    ts: DriverTS, box: DccavBox | ReflexBox | Bandpass4Box | Bandpass6Box | SealedBox,
) -> float:
    """Return the closed-box Fc for the same total chamber volume."""
    _require_positive("Fs", ts.fs_hz)
    _require_positive("Vas", ts.vas_l)
    if isinstance(box, SealedBox):
        _validate_sealed_box(box)
        v_total = box.vb_l
    elif isinstance(box, ReflexBox):
        _validate_reflex_box(box)
        v_total = box.vb_l
    elif isinstance(box, Bandpass4Box):
        _validate_bandpass4_box(box)
        v_total = box.vs_l + box.vp_l
    elif isinstance(box, Bandpass6Box):
        _validate_bandpass6_box(box)
        v_total = box.vr_l + box.vp_l
    else:
        _validate_box(box)
        v_total = box.vh_l + box.vl_l
    return float(panel_loaded_fs_hz(ts) * np.sqrt(1.0 + ts.vas_l / v_total))


def alignment_diagnostics(ts: DriverTS, box: DccavBox) -> list[str]:
    """Return practical warnings for empirical DCCAV alignments."""
    _require_positive("Qts", ts.qts)
    _require_positive("Sd", ts.sd_cm2)
    _validate_box(box)
    v_total = box.vh_l + box.vl_l
    messages: list[str] = []
    if ts.qts < 0.30:
        messages.append(
            "Qts is below 0.30: the article alignment is being extrapolated "
            "toward a very small high-motor pro-driver box."
        )
    if ts.sd_cm2 >= 500.0 and v_total < 25.0:
        messages.append(
            f"Very small 12 in alignment: Vh+Vl = {v_total:.1f} L. "
            "Treat the empirical Qts^2*Vas result as a starting point only; "
            "port displacement, compression and target SPL can dominate."
        )
    return messages


def response_sanity_warnings(
    ts: DriverTS,
    box: DccavBox,
    thresholds: dict[int, float],
) -> list[str]:
    """Return warnings when F3/F6/F10 contradict the box tuning constraints."""
    _validate_box(box)
    messages: list[str] = []
    f3 = float(thresholds.get(3, np.nan))
    if not np.isfinite(f3):
        messages.append("No real low-side F3 crossing was found in the simulated frequency range.")
        return messages

    if f3 < 0.65 * box.fl_hz:
        messages.append(
            f"F3 {f3:.1f} Hz is below 0.65*fl ({0.65 * box.fl_hz:.1f} Hz); "
            "this is not credible for the selected DCCAV tuning."
        )

    sealed_fc = equivalent_sealed_fc_hz(ts, box)
    if f3 < 0.50 * sealed_fc:
        messages.append(
            f"F3 {f3:.1f} Hz is below half the equivalent sealed Fc "
            f"({sealed_fc:.1f} Hz), so the alignment is physically suspect."
        )
    return messages


def bandpass4_diagnostics(
    ts: DriverTS,
    box: Bandpass4Box,
    result: SimulationResult | None = None,
) -> list[str]:
    """Return practical build/passband warnings for a fourth-order bandpass."""
    _require_positive("Fs", ts.fs_hz)
    _validate_bandpass4_box(box)
    messages: list[str] = []
    vtot = box.vs_l + box.vp_l
    if vtot < 0.5 * ts.vas_l:
        messages.append(
            f"Box volume {vtot:.1f} L is far below the driver's Vas "
            f"({ts.vas_l:.1f} L): the air spring dominates, sensitivity "
            "collapses, and the bandpass character is lost. "
            f"The starter alignment needs at least ~{0.5 * ts.vas_l:.0f} L total."
        )
    if box.fp_hz < 0.5 * ts.fs_hz or box.fp_hz > 4.0 * ts.fs_hz:
        messages.append(
            f"Front tuning Fp {box.fp_hz:.1f} Hz is far from driver Fs "
            f"{ts.fs_hz:.1f} Hz; verify the intended passband and port geometry."
        )
    if result is not None:
        f = np.asarray(result.frequency_hz, dtype=float)
        spl = np.asarray(result.spl_total_db, dtype=float)
        if f.size >= 3 and np.any(np.isfinite(spl)):
            peak_idx = int(np.nanargmax(spl))
            target = float(spl[peak_idx]) - 3.0
            high = _high_side_crossing(f[peak_idx:], spl[peak_idx:], target)
            if not np.isfinite(high):
                messages.append(
                    "No upper -3 dB crossing was found: extend F max to verify the "
                    "bandpass high-frequency roll-off."
                )
            low = _low_side_crossing(f[:peak_idx + 1], spl[:peak_idx + 1], target)
            if np.isfinite(low) and np.isfinite(high):
                bw = high / low
                if bw > 4.0:
                    messages.append(
                        f"Passband bandwidth {bw:.1f}:1 is extremely wide — "
                        "the box volume is likely far too small for this driver. "
                        "The reported F3 is a shallow crossing, not a real bandpass corner."
                    )
            ref = driver_reference_metrics(ts)
            if float(spl[peak_idx]) < ref.spl_2v83_db - 9.0:
                messages.append(
                    f"Peak sensitivity {spl[peak_idx]:.1f} dB is "
                    f"{ref.spl_2v83_db - spl[peak_idx]:.0f} dB below the driver's "
                    f"reference ({ref.spl_2v83_db:.1f} dB at 2.83 V): the tiny box "
                    "is wasting most of the driver's output capability."
                )
    return messages


def bandpass6_diagnostics(
    ts: DriverTS,
    box: Bandpass6Box,
    result: SimulationResult | None = None,
) -> list[str]:
    """Return practical build/passband warnings for a sixth-order bandpass."""
    _require_positive("Fs", ts.fs_hz)
    _validate_bandpass6_box(box)
    messages: list[str] = []
    vtot = box.vr_l + box.vp_l
    if vtot < 0.5 * ts.vas_l:
        messages.append(
            f"Box volume {vtot:.1f} L is far below the driver's Vas "
            f"({ts.vas_l:.1f} L): the air spring dominates, sensitivity "
            "collapses, and the bandpass character is lost. "
            f"The starter alignment needs at least ~{0.5 * ts.vas_l:.0f} L total."
        )
    if box.fr_hz < 0.5 * ts.fs_hz or box.fr_hz > 4.0 * ts.fs_hz:
        messages.append(
            f"Rear tuning Fr {box.fr_hz:.1f} Hz is far from driver Fs "
            f"{ts.fs_hz:.1f} Hz; verify the intended passband and port geometry."
        )
    if box.fp_hz < 0.5 * ts.fs_hz or box.fp_hz > 4.0 * ts.fs_hz:
        messages.append(
            f"Front tuning Fp {box.fp_hz:.1f} Hz is far from driver Fs "
            f"{ts.fs_hz:.1f} Hz; verify the intended passband and port geometry."
        )
    if result is not None:
        f = np.asarray(result.frequency_hz, dtype=float)
        spl = np.asarray(result.spl_total_db, dtype=float)
        if f.size >= 3 and np.any(np.isfinite(spl)):
            peak_idx = int(np.nanargmax(spl))
            target = float(spl[peak_idx]) - 3.0
            high = _high_side_crossing(f[peak_idx:], spl[peak_idx:], target)
            if not np.isfinite(high):
                messages.append(
                    "No upper -3 dB crossing was found: extend F max to verify the "
                    "bandpass high-frequency roll-off."
                )
            low = _low_side_crossing(f[:peak_idx + 1], spl[:peak_idx + 1], target)
            if np.isfinite(low) and np.isfinite(high):
                bw = high / low
                if bw > 4.0:
                    messages.append(
                        f"Passband bandwidth {bw:.1f}:1 is extremely wide — "
                        "the box volume is likely far too small for this driver. "
                        "The reported F3 is a shallow crossing, not a real bandpass corner."
                    )
            ref = driver_reference_metrics(ts)
            if float(spl[peak_idx]) < ref.spl_2v83_db - 9.0:
                messages.append(
                    f"Peak sensitivity {spl[peak_idx]:.1f} dB is "
                    f"{ref.spl_2v83_db - spl[peak_idx]:.0f} dB below the driver's "
                    f"reference ({ref.spl_2v83_db:.1f} dB at 2.83 V): the tiny box "
                    "is wasting most of the driver's output capability."
                )
    return messages


def _low_side_crossing(f: np.ndarray, y: np.ndarray, target: float) -> float:
    diff = y - target
    crossings = np.where((diff[:-1] <= 0.0) & (diff[1:] >= 0.0))[0]
    if len(crossings):
        idx = int(crossings[0])
        x0, x1 = float(f[idx]), float(f[idx + 1])
        y0, y1 = float(y[idx]), float(y[idx + 1])
        if y1 == y0:
            return x0
        frac = (float(target) - y0) / (y1 - y0)
        return x0 + frac * (x1 - x0)
    return float("nan")


def _high_side_crossing(f: np.ndarray, y: np.ndarray, target: float) -> float:
    diff = y - target
    crossings = np.where((diff[:-1] >= 0.0) & (diff[1:] <= 0.0))[0]
    if len(crossings):
        idx = int(crossings[0])
        x0, x1 = float(f[idx]), float(f[idx + 1])
        y0, y1 = float(y[idx]), float(y[idx + 1])
        if y1 == y0:
            return x0
        return x0 + (float(target) - y0) / (y1 - y0) * (x1 - x0)
    return float("nan")


def _box_impedance(volume_l: float, fb_hz: float, q_abs: float, q_leak: float, w):
    cab = _cab(volume_l)
    rab = 1.0 / (2.0 * np.pi * fb_hz * q_abs * cab)
    ral = q_leak / (2.0 * np.pi * fb_hz * cab)
    z_series_loss = rab + 1.0 / (1j * w * cab)
    return _parallel(z_series_loss, ral)


def _port_impedance(volume_l: float, fb_hz: float, q_port: float, w):
    cab = _cab(volume_l)
    map_ = 1.0 / ((2.0 * np.pi * fb_hz) ** 2 * cab)
    rap = 1.0 / (2.0 * np.pi * fb_hz * cab * q_port)
    return rap + 1j * w * map_


def _cab(volume_l: float) -> float:
    _require_positive("Volume", volume_l)
    return (volume_l / 1000.0) / (RHO_AIR * SPEED_OF_SOUND**2)


def _parallel(a, b):
    return 1.0 / (1.0 / (a + EPS) + 1.0 / (b + EPS))


def _spl_from_volume_velocity(u, f):
    pressure = np.maximum(np.abs(u) * np.asarray(f) * RHO_AIR, EPS)
    return 20.0 * np.log10(pressure / P_REF)


def _limit_curves(
    ts: DriverTS,
    voltage_v: float,
    spl_total_db: np.ndarray,
    excursion_mm: np.ndarray,
    series_r_ohm: float = 0.0,
) -> tuple[np.ndarray, np.ndarray]:
    # Limit voltages are at the source terminals; with a series resistance the
    # thermal ceiling scales by the resistive divider (Re+Rs)/Re and the power
    # reported is the share reaching the driver's Re.
    re_total = ts.re_ohm + float(series_r_ohm)
    shape = np.asarray(spl_total_db, dtype=float).shape
    # Both MIL and MOL need a published thermal rating: MIL is a drive-limit
    # estimate that is only credible with a Pe to bound it, and MOL cannot
    # scale a curve that has no thermal ceiling. Drivers with Pe=0 therefore
    # report both curves as unavailable instead of plotting an excursion-only
    # MIL with no counterpart MOL.
    if ts.pe_w <= 0:
        nan = np.full(shape, np.nan, dtype=float)
        return nan, nan
    limits: list[np.ndarray] = []
    if ts.xmax_mm > 0:
        excursion = np.maximum(np.asarray(excursion_mm, dtype=float), EPS)
        limits.append(float(voltage_v) * ts.xmax_mm / excursion)
    thermal_v = np.sqrt(ts.pe_w * ts.re_ohm) * re_total / ts.re_ohm
    limits.append(np.full(shape, thermal_v, dtype=float))

    mil_v = np.minimum.reduce(limits)
    driver_v = mil_v * ts.re_ohm / re_total
    mil_w = driver_v**2 / ts.re_ohm
    gain_db = 20.0 * np.log10(np.maximum(mil_v, EPS) / float(voltage_v))
    mol_db = np.asarray(spl_total_db, dtype=float) + gain_db
    return mil_w, mol_db


def _validate_box(box: DccavBox) -> None:
    for name, value in (
        ("Vh", box.vh_l),
        ("Fh", box.fh_hz),
        ("Vl", box.vl_l),
        ("Fl", box.fl_hz),
        ("Qabs h", box.q_abs_h),
        ("Qabs l", box.q_abs_l),
        ("Qleak h", box.q_leak_h),
        ("Qleak l", box.q_leak_l),
        ("Qport h", box.q_port_h),
        ("Qport l", box.q_port_l),
    ):
        _require_positive(name, value)


def _validate_reflex_box(box: ReflexBox) -> None:
    for name, value in (
        ("Vb", box.vb_l),
        ("Fb", box.fb_hz),
        ("Qabs", box.q_abs),
        ("Qleak", box.q_leak),
        ("Qport", box.q_port),
    ):
        _require_positive(name, value)


def _validate_bandpass4_box(box: Bandpass4Box) -> None:
    for name, value in (
        ("Vs", box.vs_l),
        ("Vp", box.vp_l),
        ("Fp", box.fp_hz),
        ("Qabs sealed", box.q_abs_s),
        ("Qabs ported", box.q_abs_p),
        ("Qleak sealed", box.q_leak_s),
        ("Qleak ported", box.q_leak_p),
        ("Qport", box.q_port),
    ):
        _require_positive(name, value)


def _validate_sealed_box(box: SealedBox) -> None:
    for name, value in (
        ("Vb", box.vb_l),
        ("Qabs", box.q_abs),
        ("Qleak", box.q_leak),
    ):
        _require_positive(name, value)


def _require_positive(name: str, value: float) -> None:
    if not np.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be positive")


def _validate_waveguide_segments(segments: tuple[WaveguideSegment, ...]) -> None:
    if not segments:
        raise ValueError("A waveguide needs at least one segment")
    for segment in segments:
        _require_positive("Waveguide segment length", segment.length_m)
        _require_positive("Waveguide segment area", segment.area_cm2)


def _waveguide_matrix(
    segment: WaveguideSegment, omega: np.ndarray, line_q: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return the pressure/volume-velocity transfer matrix of one section."""
    _require_positive("Line Q", line_q)
    area_m2 = float(segment.area_cm2) * 1e-4
    zc = RHO_AIR * SPEED_OF_SOUND / area_m2
    k = omega / SPEED_OF_SOUND * (1.0 - 0.5j / float(line_q))
    kd = k * float(segment.length_m)
    a = np.cos(kd)
    b = 1j * zc * np.sin(kd)
    c = 1j * np.sin(kd) / zc
    d = a.copy()
    return a, b, c, d


def _waveguide_chain_impedance(
    segments: tuple[WaveguideSegment, ...], omega: np.ndarray,
    termination_z: np.ndarray, line_q: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Return input impedance and output velocity transfer for a guide."""
    _validate_waveguide_segments(segments)
    a = np.ones_like(omega, dtype=complex)
    b = np.zeros_like(omega, dtype=complex)
    c = np.zeros_like(omega, dtype=complex)
    d = np.ones_like(omega, dtype=complex)
    for segment in segments:
        sa, sb, sc, sd = _waveguide_matrix(segment, omega, line_q)
        a, b, c, d = (
            a * sa + b * sc,
            a * sb + b * sd,
            c * sa + d * sc,
            c * sb + d * sd,
        )
    denominator = c * termination_z + d
    safe_denominator = np.where(
        np.abs(denominator) > EPS, denominator, EPS + 0j)
    zin = (a * termination_z + b) / safe_denominator
    output_velocity_ratio = 1.0 / safe_denominator
    return zin, output_velocity_ratio


def _waveguide_radiation_impedance(
    omega: np.ndarray, area_cm2: float,
) -> np.ndarray:
    """Low-frequency unflanged piston radiation impedance."""
    _require_positive("Mouth area", area_cm2)
    area_m2 = float(area_cm2) * 1e-4
    radius_m = np.sqrt(area_m2 / np.pi)
    ka = omega / SPEED_OF_SOUND * radius_m
    zc = RHO_AIR * SPEED_OF_SOUND / area_m2
    return zc * (0.25 * ka**2 + 1j * 0.61 * ka)


def _waveguide_vent_impedance(
    omega: np.ndarray, area_cm2: float, length_m: float,
    end_correction: float,
) -> np.ndarray:
    _require_positive("Vent area", area_cm2)
    _require_positive("Vent length", length_m)
    radius_m = np.sqrt(float(area_cm2) * 1e-4 / np.pi)
    mass = RHO_AIR * (float(length_m) + float(end_correction) * radius_m) / (float(area_cm2) * 1e-4)
    return 1j * omega * mass


def _waveguide_segments_from_horn(box: HornBox) -> tuple[WaveguideSegment, ...]:
    _require_positive("Horn length", box.length_m)
    _require_positive("Horn throat area", box.throat_area_cm2)
    _require_positive("Horn mouth area", box.mouth_area_cm2)
    if box.mouth_area_cm2 < box.throat_area_cm2:
        raise ValueError("Horn mouth area must be at least the throat area")
    if int(box.segments) < 4:
        raise ValueError("Horn needs at least 4 sections")
    flare = str(box.flare).casefold()
    if flare not in {"conical", "exponential"}:
        raise ValueError("Horn flare must be 'conical' or 'exponential'")
    n = int(box.segments)
    edges = np.linspace(0.0, float(box.length_m), n + 1)
    ratio = float(box.mouth_area_cm2) / float(box.throat_area_cm2)
    if flare == "exponential":
        areas = float(box.throat_area_cm2) * ratio ** (edges / float(box.length_m))
    else:
        areas = float(box.throat_area_cm2) + (
            float(box.mouth_area_cm2) - float(box.throat_area_cm2)
        ) * edges / float(box.length_m)
    return tuple(
        WaveguideSegment(float(edges[i + 1] - edges[i]), float(np.sqrt(areas[i] * areas[i + 1])))
        for i in range(n)
    )


def _waveguide_result(
    ts: DriverTS, freq_hz: np.ndarray, zin: np.ndarray,
    mouth_velocity_ratio: np.ndarray, mouth_area_cm2: float,
    voltage_v: float, series_r_ohm: float,
    direct_cone_radiation: bool,
) -> SimulationResult:
    drv = complete_driver(ts)
    f = np.asarray(freq_hz, dtype=float)
    omega = 2.0 * np.pi * f
    jw = 1j * omega
    re_total, _, p_source = _electrical_source(ts, drv, voltage_v, series_r_ohm)
    z_as = drv.rms_n_s_m + jw * drv.mas + 1.0 / (jw * drv.cms_m_per_n)
    u_driver = p_source / (z_as + zin)
    u_mouth = u_driver * mouth_velocity_ratio
    u_direct = -u_driver if direct_cone_radiation else np.zeros_like(u_driver)
    spl_driver = _spl_from_volume_velocity(u_direct, f)
    spl_mouth = _spl_from_volume_velocity(u_mouth, f)
    spl_total = 20.0 * np.log10(
        np.maximum(np.abs(u_direct + u_mouth) * RHO_AIR * omega / (4.0 * np.pi * P_REF), EPS)
    )
    z_mech = drv.rms_n_s_m + jw * drv.mas + 1.0 / (jw * drv.cms_m_per_n)
    z_e = re_total + 1j * omega * (ts.le_mh / 1000.0) + drv.bl_tm**2 / (z_mech + zin * drv.sd_m2**2)
    excursion = np.abs(u_driver / (jw * drv.sd_m2)) * 1000.0
    mil_w, mol_db = _limit_curves(ts, voltage_v, spl_total, excursion, series_r_ohm)
    mouth = np.abs(u_mouth)
    return SimulationResult(
        frequency_hz=f,
        spl_total_db=spl_total,
        spl_driver_db=spl_driver,
        spl_port_db=spl_mouth,
        excursion_mm=excursion,
        impedance_ohm=np.abs(z_e),
        port_h_velocity=np.zeros_like(mouth),
        port_l_velocity=mouth,
        mil_w=mil_w,
        mol_db=mol_db,
        driver_volume_velocity=np.abs(u_driver),
        port_volume_velocity=mouth,
        impedance_phase_deg=np.angle(z_e, deg=True),
    )


def simulate_transmission_line(
    ts: DriverTS, box: TransmissionLineBox, freq_hz: np.ndarray | None = None,
    voltage_v: float = 2.83, series_r_ohm: float = 0.0,
) -> SimulationResult:
    """Simulate a uniform or stepped transmission line with a rear-loaded driver."""
    _validate_waveguide_segments(box.segments)
    if box.termination not in {"open", "closed"}:
        raise ValueError("Transmission-line termination must be 'open' or 'closed'")
    if freq_hz is None:
        freq_hz = np.geomspace(10.0, 500.0, 600)
    f = np.asarray(freq_hz, dtype=float)
    if np.any(f <= 0):
        raise ValueError("Frequencies must be positive")
    omega = 2.0 * np.pi * f
    mouth_area = box.mouth_area_cm2 or box.segments[-1].area_cm2
    termination = (
        _waveguide_radiation_impedance(omega, mouth_area)
        if box.termination == "open" else np.full(omega.shape, 1e30 + 0j, dtype=complex)
    )
    zin, ratio = _waveguide_chain_impedance(box.segments, omega, termination, box.line_q)
    return _waveguide_result(ts, f, zin, ratio, mouth_area, voltage_v, series_r_ohm, box.direct_cone_radiation)


def simulate_mltl(
    ts: DriverTS, box: MltlBox, freq_hz: np.ndarray | None = None,
    voltage_v: float = 2.83, series_r_ohm: float = 0.0,
) -> SimulationResult:
    """Simulate a mass-loaded TL with an external vent at its open end."""
    _validate_waveguide_segments(box.segments)
    if freq_hz is None:
        freq_hz = np.geomspace(10.0, 500.0, 600)
    f = np.asarray(freq_hz, dtype=float)
    if np.any(f <= 0):
        raise ValueError("Frequencies must be positive")
    omega = 2.0 * np.pi * f
    mouth_area = box.segments[-1].area_cm2
    open_z = _waveguide_radiation_impedance(omega, mouth_area)
    vent_z = _waveguide_vent_impedance(
        omega, box.vent_area_cm2, box.vent_length_m, box.vent_end_correction)
    termination = 1.0 / (1.0 / open_z + 1.0 / vent_z)
    zin, ratio = _waveguide_chain_impedance(box.segments, omega, termination, box.line_q)
    return _waveguide_result(ts, f, zin, ratio, mouth_area, voltage_v, series_r_ohm, box.direct_cone_radiation)


def simulate_quarter_wave(
    ts: DriverTS, length_m: float, area_cm2: float,
    freq_hz: np.ndarray | None = None, voltage_v: float = 2.83,
    series_r_ohm: float = 0.0, line_q: float = 25.0,
) -> SimulationResult:
    """Convenience wrapper for a closed-end quarter-wave line."""
    box = TransmissionLineBox(
        segments=(WaveguideSegment(length_m, area_cm2),),
        termination="closed", mouth_area_cm2=area_cm2, line_q=line_q,
    )
    return simulate_transmission_line(ts, box, freq_hz, voltage_v, series_r_ohm)


def simulate_back_loaded_horn(
    ts: DriverTS, box: HornBox, freq_hz: np.ndarray | None = None,
    voltage_v: float = 2.83, series_r_ohm: float = 0.0,
) -> SimulationResult:
    """Simulate the rear-loaded radiation path of a tapered horn."""
    segments = _waveguide_segments_from_horn(box)
    line = TransmissionLineBox(
        segments=segments, termination=box.mouth_termination,
        mouth_area_cm2=box.mouth_area_cm2, line_q=box.line_q,
        direct_cone_radiation=box.direct_cone_radiation,
    )
    return simulate_transmission_line(ts, line, freq_hz, voltage_v, series_r_ohm)


def simulate_tapped_horn(
    ts: DriverTS, box: TappedHornBox, freq_hz: np.ndarray | None = None,
    voltage_v: float = 2.83, series_r_ohm: float = 0.0,
) -> SimulationResult:
    """Simulate a tapped horn as two tapered branches in parallel at the tap."""
    if not 0.0 < float(box.tap_position_m) < float(box.length_m):
        raise ValueError("Tapped-horn tap position must lie inside the horn")
    if freq_hz is None:
        freq_hz = np.geomspace(10.0, 500.0, 600)
    f = np.asarray(freq_hz, dtype=float)
    if np.any(f <= 0):
        raise ValueError("Frequencies must be positive")
    full = _waveguide_segments_from_horn(HornBox(
        box.length_m, box.throat_area_cm2, box.mouth_area_cm2,
        box.flare, box.segments, "open", box.line_q, box.direct_cone_radiation))
    n_tap = max(1, min(len(full) - 1, int(round(box.tap_position_m / box.length_m * len(full)))))
    throat_segments = tuple(reversed(full[:n_tap]))
    mouth_segments = full[n_tap:]
    omega = 2.0 * np.pi * f
    z_throat, _ = _waveguide_chain_impedance(
        throat_segments, omega, np.full(omega.shape, 1e30 + 0j, dtype=complex), box.line_q)
    z_mouth, mouth_ratio = _waveguide_chain_impedance(
        mouth_segments, omega, _waveguide_radiation_impedance(omega, box.mouth_area_cm2), box.line_q)
    zin = 1.0 / (1.0 / z_throat + 1.0 / z_mouth)
    # Scale the mouth branch velocity by the tap velocity; the throat branch
    # is an internal termination and is intentionally not exported as SPL.
    return _waveguide_result(ts, f, zin, mouth_ratio * (zin / z_mouth), box.mouth_area_cm2,
                             voltage_v, series_r_ohm, box.direct_cone_radiation)
