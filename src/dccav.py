"""
DCCAV acoustic-load simulator.

The first model implemented here follows the PCPaudio/G.P. Matarazzo "doppio
resonador en serie" article as a lumped acoustic circuit:

    driver -> upper volume || upper port -> lower volume || lower port

All calculations use SI units internally and expose litre/Hz/mm-friendly helpers
for the UI.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

RHO_AIR = 1.18
SPEED_OF_SOUND = 344.0
P_REF = 20e-6
EPS = 1e-30
LOUDSPEAKER_DATABASE_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "loudspeaker_database_drivers.json"
)
DRIVER_PRICES_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "driver_prices.json"
)


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
    xmax_mm: float = 0.0
    pe_w: float = 0.0
    mms_g: float | None = None
    cms_mm_per_n: float | None = None
    bl_tm: float | None = None


@dataclass(frozen=True)
class DriverPresetInfo:
    """Metadata used to filter a named driver preset in the UI."""

    name: str
    source: str
    brand: str
    model: str
    size_in: float | None = None
    price: float | None = None
    currency: str = ""
    kind: str = ""
    url: str = ""


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


@dataclass(frozen=True)
class OptimizedAlignment:
    """Optimizer result: the box plus the achieved response figures."""

    box: DccavBox | ReflexBox | SealedBox
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


def sd_from_diameter(diameter_mm: float) -> float:
    """Return piston area in cm^2 from an effective piston diameter in mm."""
    d_m = float(diameter_mm) / 1000.0
    return float(np.pi * (d_m / 2.0) ** 2 * 10_000.0)


DRIVER_PRESETS: dict[str, DriverTS] = {
    "KEF B110B article example": DriverTS(
        fs_hz=48.14,
        vas_l=11.52,
        qts=0.362,
        qms=2.372,
        re_ohm=6.89,
        sd_cm2=sd_from_diameter(104.0),
        le_mh=0.421,
        xmax_mm=3.1,
        pe_w=60.0,
    ),
    "Beyma 12CMV2": DriverTS(
        fs_hz=49.0,
        vas_l=76.0,
        qts=0.47,
        qms=3.9,
        re_ohm=6.0,
        sd_cm2=530.0,
        le_mh=1.0,
        xmax_mm=7.0,
        pe_w=320.0,
        mms_g=54.0,
        cms_mm_per_n=0.193,
        bl_tm=13.7,
    ),
    "Beyma 12G40": DriverTS(
        fs_hz=44.0,
        vas_l=81.0,
        qts=0.30,
        qms=11.6,
        re_ohm=6.0,
        sd_cm2=530.0,
        le_mh=2.1,
        xmax_mm=7.0,
        pe_w=500.0,
        mms_g=62.0,
        cms_mm_per_n=0.206,
        bl_tm=18.4,
    ),
    "Beyma 12LX60V2": DriverTS(
        fs_hz=49.0,
        vas_l=43.0,
        qts=0.38,
        qms=15.3,
        re_ohm=5.1,
        sd_cm2=550.0,
        le_mh=2.1,
        xmax_mm=9.0,
        pe_w=700.0,
        mms_g=102.0,
        cms_mm_per_n=0.099,
        bl_tm=20.0,
    ),
    "Beyma 12BR70": DriverTS(
        fs_hz=31.0,
        vas_l=142.0,
        qts=0.50,
        qms=4.44,
        re_ohm=5.6,
        sd_cm2=540.0,
        le_mh=0.8,
        xmax_mm=8.0,
        pe_w=125.0,
        mms_g=74.0,
        cms_mm_per_n=0.345,
        bl_tm=12.1,
    ),
    "Beyma 12MC500": DriverTS(
        fs_hz=57.0,
        vas_l=57.0,
        qts=0.34,
        qms=7.8,
        re_ohm=5.6,
        sd_cm2=550.0,
        le_mh=0.7,
        xmax_mm=8.0,
        pe_w=500.0,
        mms_g=59.0,
        cms_mm_per_n=0.132,
        bl_tm=18.3,
    ),
    "Beyma 12MCS500": DriverTS(
        fs_hz=57.0,
        vas_l=57.0,
        qts=0.36,
        qms=7.8,
        re_ohm=5.6,
        sd_cm2=550.0,
        le_mh=1.1,
        xmax_mm=8.0,
        pe_w=500.0,
        mms_g=59.0,
        cms_mm_per_n=0.132,
        bl_tm=17.6,
    ),
    "Beyma 12WRS400": DriverTS(
        fs_hz=42.0,
        vas_l=91.0,
        qts=0.29,
        qms=7.7,
        re_ohm=5.6,
        sd_cm2=530.0,
        le_mh=1.3,
        xmax_mm=6.3,
        pe_w=400.0,
        mms_g=63.0,
        cms_mm_per_n=0.228,
        bl_tm=17.4,
    ),
    "Beyma 12P80Nd/V2": DriverTS(
        fs_hz=47.0,
        vas_l=65.0,
        qts=0.19,
        qms=5.2,
        re_ohm=5.0,
        sd_cm2=550.0,
        le_mh=0.9,
        xmax_mm=7.5,
        pe_w=700.0,
        mms_g=74.0,
        cms_mm_per_n=0.152,
        bl_tm=23.7,
    ),
    "Beyma 12P1000/Nd": DriverTS(
        fs_hz=47.0,
        vas_l=49.0,
        qts=0.26,
        qms=7.9,
        re_ohm=5.1,
        sd_cm2=550.0,
        le_mh=2.0,
        xmax_mm=8.0,
        pe_w=900.0,
        mms_g=100.0,
        cms_mm_per_n=0.115,
        bl_tm=23.5,
    ),
    "Beyma 12LEX1000Fe": DriverTS(
        fs_hz=49.0,
        vas_l=38.4,
        qts=0.30,
        qms=3.6,
        re_ohm=5.4,
        sd_cm2=550.0,
        le_mh=1.7,
        xmax_mm=11.0,
        pe_w=1000.0,
        mms_g=118.0,
        cms_mm_per_n=0.089,
        bl_tm=24.6,
    ),
    "Beyma 12LEX1300Nd": DriverTS(
        fs_hz=45.0,
        vas_l=43.0,
        qts=0.24,
        qms=4.2,
        re_ohm=5.0,
        sd_cm2=550.0,
        le_mh=1.3,
        xmax_mm=11.0,
        pe_w=1300.0,
        mms_g=125.0,
        cms_mm_per_n=0.100,
        bl_tm=26.4,
    ),
    "Beyma 12CMV3": DriverTS(
        fs_hz=52.0,
        vas_l=85.0,
        qts=0.55,
        qms=10.6,
        re_ohm=6.1,
        sd_cm2=530.0,
        le_mh=0.89,
        xmax_mm=7.0,
        pe_w=320.0,
        mms_g=44.0,
        cms_mm_per_n=0.214,
        bl_tm=12.3,
    ),
    "Turbosound TS-12W350/8W": DriverTS(
        fs_hz=61.0,
        vas_l=19.26,
        qts=0.43,
        qms=11.37,
        re_ohm=5.5,
        sd_cm2=551.55,
        le_mh=1.6,
        xmax_mm=3.8,
        pe_w=350.0,
        mms_g=67.78,
        cms_mm_per_n=0.1,
        bl_tm=17.9,
    ),
    "Turbosound TS-15W300/8A": DriverTS(
        fs_hz=46.0,
        vas_l=130.2,
        qts=0.47,
        qms=16.6,
        re_ohm=6.5,
        sd_cm2=865.7,
        le_mh=1.2,
        xmax_mm=4.9,
        pe_w=300.0,
        mms_g=96.4,
        cms_mm_per_n=0.12,
        bl_tm=19.3,
    ),
    "Scan-Speak 30W/4558T00": DriverTS(
        fs_hz=17.0,
        vas_l=197.0,
        qts=0.32,
        qms=5.01,
        re_ohm=2.6,
        sd_cm2=466.0,
        le_mh=0.83,
        xmax_mm=12.5,
        pe_w=150.0,
        mms_g=135.0,
        cms_mm_per_n=0.65,
        bl_tm=10.5,
    ),
    "Scan-Speak 15W/4531G00": DriverTS(
        fs_hz=40.0,
        vas_l=15.8,
        qts=0.32,
        qms=4.60,
        re_ohm=3.4,
        sd_cm2=95.0,
        le_mh=0.25,
        xmax_mm=6.5,
        pe_w=60.0,
        mms_g=13.0,
        cms_mm_per_n=1.25,
        bl_tm=5.7,
    ),
    "Dayton Audio RSS315HO-4": DriverTS(
        fs_hz=26.2,
        vas_l=53.7,
        qts=0.31,
        qms=3.63,
        re_ohm=3.2,
        sd_cm2=514.7,
        le_mh=1.75,
        xmax_mm=12.3,
        pe_w=700.0,
        mms_g=251.0,
        cms_mm_per_n=0.15,
        bl_tm=20.0,
    ),
    "SB Audience BIANCO-12OB150-01": DriverTS(
        fs_hz=44.0,
        vas_l=103.8,
        qts=0.63,
        qms=6.39,
        re_ohm=7.2,
        sd_cm2=539.1,
        le_mh=1.18,
        xmax_mm=6.79,
        pe_w=150.0,
        mms_g=52.4,
        cms_mm_per_n=0.25,
        bl_tm=12.2,
    ),
    "LaVoce WSF122.02": DriverTS(
        fs_hz=50.0,
        vas_l=88.0,
        qts=0.40,
        qms=4.0,
        re_ohm=5.2,
        sd_cm2=531.0,
        le_mh=0.53,
        xmax_mm=4.3,
        pe_w=200.0,
        mms_g=44.8,
        cms_mm_per_n=0.22,
        bl_tm=12.8,
    ),
    "LaVoce WSF122.50": DriverTS(
        fs_hz=50.0,
        vas_l=72.0,
        qts=0.32,
        qms=5.5,
        re_ohm=5.5,
        sd_cm2=531.0,
        le_mh=0.76,
        xmax_mm=4.7,
        pe_w=250.0,
        mms_g=58.4,
        cms_mm_per_n=0.18,
        bl_tm=17.1,
    ),
    "Aiyima 4ohm 5w 40mm black": DriverTS(
        fs_hz=153.6,
        vas_l=0.1,
        qts=0.459,
        qms=6.015,
        re_ohm=3.56,
        sd_cm2=7.40229915,
        pe_w=5.0,
        mms_g=0.87,
        cms_mm_per_n=1.235,
        bl_tm=2.486,
    ),
    "Aiyima 6ohm 8w 56mm": DriverTS(
        fs_hz=187.6,
        vas_l=0.05,
        qts=0.56,
        qms=4.524,
        re_ohm=6.1,
        sd_cm2=8.24479576,
        pe_w=8.0,
        mms_g=1.39,
        cms_mm_per_n=0.519,
        bl_tm=3.977,
    ),
    "Aiyima 4ohm 20w 58mm": DriverTS(
        fs_hz=156.6,
        vas_l=0.18,
        qts=0.874,
        qms=3.912,
        re_ohm=3.5,
        sd_cm2=16.4029621,
        pe_w=20.0,
        mms_g=2.2,
        cms_mm_per_n=0.47,
        bl_tm=2.62,
    ),
    "Aiyima 4ohm 20w 1.75in": DriverTS(
        fs_hz=168.4,
        vas_l=0.11,
        qts=1.281,
        qms=7.916,
        re_ohm=4.08,
        sd_cm2=8.552985999,
        pe_w=20.0,
        mms_g=0.87,
        cms_mm_per_n=1.025,
        bl_tm=1.565,
    ),
    "Aiyima 4ohm 5w 40mm zinc": DriverTS(
        fs_hz=149.1,
        vas_l=0.1,
        qts=0.389,
        qms=2.739,
        re_ohm=3.0,
        sd_cm2=7.694467267,
        pe_w=5.0,
        mms_g=0.98,
        cms_mm_per_n=1.16,
        bl_tm=2.527,
    ),
    "Aiyima 4ohm 10w 40mm": DriverTS(
        fs_hz=155.6,
        vas_l=0.05,
        qts=0.48,
        qms=3.728,
        re_ohm=4.0,
        sd_cm2=7.258335667,
        pe_w=10.0,
        mms_g=1.7,
        cms_mm_per_n=0.614,
        bl_tm=3.599,
    ),
    "Aiyima 8ohm 15w 3in flat": DriverTS(
        fs_hz=152.5,
        vas_l=0.28,
        qts=0.912,
        qms=2.352,
        re_ohm=7.0,
        sd_cm2=30.48358038,
        pe_w=15.0,
        mms_g=5.14,
        cms_mm_per_n=0.212,
        bl_tm=4.993,
    ),
    "Aiyima 8ohm 4w 1in for harman": DriverTS(
        fs_hz=552.0,
        vas_l=0.01,
        qts=1.451,
        qms=3.993,
        re_ohm=6.79,
        sd_cm2=4.523893421,
        pe_w=4.0,
        mms_g=0.39,
        cms_mm_per_n=0.212,
        bl_tm=2.01,
    ),
    "Aiyima 4ohm 12w 2in": DriverTS(
        fs_hz=188.5,
        vas_l=0.1,
        qts=1.244,
        qms=5.724,
        re_ohm=3.35,
        sd_cm2=12.19220693,
        pe_w=12.0,
        mms_g=1.56,
        cms_mm_per_n=0.458,
        bl_tm=1.964,
    ),
    "Aiyima 8ohm 3w 40mm": DriverTS(
        fs_hz=239.2,
        vas_l=0.04,
        qts=3.758,
        qms=8.05,
        re_ohm=7.21,
        sd_cm2=6.6966189,
        pe_w=3.0,
        mms_g=0.65,
        cms_mm_per_n=0.683,
        bl_tm=1.002,
    ),
    "Aiyima 4ohm 3w 1in": DriverTS(
        fs_hz=478.3,
        vas_l=0.01,
        qts=0.933,
        qms=1.742,
        re_ohm=3.57,
        sd_cm2=5.027255104,
        pe_w=3.0,
        mms_g=0.61,
        cms_mm_per_n=0.182,
        bl_tm=1.823,
    ),
    "Aiyima 4ohm 3w 36mm": DriverTS(
        fs_hz=172.1,
        vas_l=0.07,
        qts=0.623,
        qms=5.192,
        re_ohm=3.68,
        sd_cm2=6.026281568,
        pe_w=3.0,
        mms_g=0.65,
        cms_mm_per_n=1.319,
        bl_tm=1.927,
    ),
    "Aiyima 4ohm 10w 53mm": DriverTS(
        fs_hz=142.6,
        vas_l=0.16,
        qts=0.43,
        qms=4.86,
        re_ohm=4.07,
        sd_cm2=12.37858191,
        pe_w=10.0,
        mms_g=1.74,
        cms_mm_per_n=0.716,
        bl_tm=3.668,
    ),
    "Aiyima 10ohm 10w 50mm": DriverTS(
        fs_hz=191.9,
        vas_l=0.1,
        qts=1.738,
        qms=5.938,
        re_ohm=9.28,
        sd_cm2=12.37858191,
        pe_w=10.0,
        mms_g=1.57,
        cms_mm_per_n=0.439,
        bl_tm=2.686,
    ),
    "Aiyima 4ohm 10w 53mm LY1124-2": DriverTS(
        fs_hz=140.7,
        vas_l=0.22,
        qts=0.534,
        qms=3.245,
        re_ohm=3.14,
        sd_cm2=13.7885287,
        pe_w=10.0,
        mms_g=1.58,
        cms_mm_per_n=0.807,
        bl_tm=2.667,
    ),
    "Aiyima 4ohm 2w 33mm": DriverTS(
        fs_hz=310.0,
        vas_l=0.02,
        qts=1.207,
        qms=5.734,
        re_ohm=3.52,
        sd_cm2=5.309291585,
        pe_w=2.0,
        mms_g=0.42,
        cms_mm_per_n=0.623,
        bl_tm=1.397,
    ),
    "Aiyima 8ohm 1w 25mm altavoz portatil": DriverTS(
        fs_hz=348.0,
        vas_l=0.01,
        qts=0.82,
        qms=3.61,
        re_ohm=7.28,
        sd_cm2=3.204738666,
        pe_w=1.0,
        mms_g=0.3,
        cms_mm_per_n=0.702,
        bl_tm=2.12,
    ),
    "Aiyima 8ohm 3w 30mm altavoz portatil": DriverTS(
        fs_hz=286.4,
        vas_l=0.02,
        qts=1.411,
        qms=6.584,
        re_ohm=7.13,
        sd_cm2=3.870756308,
        pe_w=3.0,
        mms_g=0.36,
        cms_mm_per_n=0.854,
        bl_tm=1.63,
    ),
    "Aiyima 4ohm 5w 1.5in": DriverTS(
        fs_hz=221.2,
        vas_l=0.05,
        qts=0.419,
        qms=1.693,
        re_ohm=3.47,
        sd_cm2=8.193980499,
        pe_w=5.0,
        mms_g=1.0,
        cms_mm_per_n=0.52,
        bl_tm=2.937,
    ),
    "MarkAudio CHR-70": DriverTS(
        fs_hz=65.4,
        vas_l=5.17,
        qts=0.55,
        qms=2.66,
        re_ohm=7.2,
        sd_cm2=50.2,
        le_mh=0.03244,
        xmax_mm=4.3,
        pe_w=20.0,
        mms_g=4.10,
        cms_mm_per_n=1.44,
        bl_tm=4.20,
    ),
}


_BUILT_IN_PRESET_BRANDS = (
    "Aiyima",
    "Beyma",
    "Turbosound",
    "Scan-Speak",
    "Dayton Audio",
    "SB Audience",
    "LaVoce",
    "MarkAudio",
    "KEF",
)


def _built_in_preset_brand(name: str) -> str:
    for brand in _BUILT_IN_PRESET_BRANDS:
        if name.startswith(brand):
            return brand
    return "Other"


def _driver_ts_from_mapping(values: dict) -> DriverTS:
    return DriverTS(
        fs_hz=float(values["fs_hz"]),
        vas_l=float(values["vas_l"]),
        qts=float(values["qts"]),
        qms=float(values["qms"]),
        re_ohm=float(values["re_ohm"]),
        sd_cm2=float(values["sd_cm2"]),
        le_mh=float(values.get("le_mh", 0.0)),
        xmax_mm=float(values.get("xmax_mm", 0.0)),
        pe_w=float(values.get("pe_w", 0.0)),
        mms_g=float(values["mms_g"]) if values.get("mms_g") is not None else None,
        cms_mm_per_n=(
            float(values["cms_mm_per_n"]) if values.get("cms_mm_per_n") is not None else None
        ),
        bl_tm=float(values["bl_tm"]) if values.get("bl_tm") is not None else None,
    )


def _preset_match_tokens(value: str) -> list[str]:
    return [token for token in re.split(r"[^a-z0-9]+", str(value).casefold()) if token]


def _compact_token_sequences(tokens: list[str], max_len: int = 4) -> set[str]:
    compact = set(tokens)
    for start in range(len(tokens)):
        for end in range(start + 2, min(len(tokens), start + max_len) + 1):
            compact.add("".join(tokens[start:end]))
    return compact


def _model_needs_brand(model: str) -> bool:
    compact = "".join(_preset_match_tokens(model))
    return bool(compact) and (compact.isdigit() or len(compact) <= 5)


def _record_looks_like_driver(record: dict) -> bool:
    text = " ".join(str(record.get(key, "")) for key in ("matched_name", "url")).casefold()
    accessory_patterns = (
        "surround for",
        "recone kit",
        "repair kit",
        "diaphragm for",
        "voice coil",
        "dust cap",
        "distance holder",
        "printed circuit board",
        "iron core coil",
        "air core coil",
        "capacitor",
        "fuse",
        " kit",
        "-kit",
        "crossover",
        "grill",
    )
    return not any(pattern in text for pattern in accessory_patterns)


def _price_record_matches_preset(record: dict, name: str, brand: str, model: str) -> bool:
    if not _record_looks_like_driver(record):
        return False
    if not record.get("matched_name") and not record.get("matched_brand") and not record.get("matched_mpn"):
        return True
    model_key = "".join(_preset_match_tokens(model or name.removeprefix("LSDB: ")))
    brand_key = "".join(_preset_match_tokens(brand))
    product_tokens: list[str] = []
    for key in ("matched_name", "matched_brand", "matched_mpn", "url"):
        product_tokens.extend(_preset_match_tokens(str(record.get(key, ""))))
    product_sequences = _compact_token_sequences(product_tokens)
    model_ok = bool(model_key and model_key in product_sequences)
    brand_ok = bool(not brand_key or brand_key in product_sequences)
    if _model_needs_brand(model or name) and not brand_ok:
        return False
    return model_ok or (brand_ok and bool(brand_key) and brand_key == model_key)


def _price_from_record(record: dict | None, name: str = "", brand: str = "", model: str = "") -> tuple[float | None, str, str]:
    if not isinstance(record, dict):
        return None, "", ""
    try:
        price = float(record["price"])
    except (KeyError, TypeError, ValueError):
        return None, "", ""
    if not np.isfinite(price) or price < 0:
        return None, "", ""
    if name and not _price_record_matches_preset(record, name, brand, model):
        return None, "", ""
    return price, str(record.get("currency") or ""), str(record.get("url") or "")


def _valid_price(value) -> float | None:
    if value is None:
        return None
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    return price if np.isfinite(price) and price >= 0 else None


@lru_cache(maxsize=1)
def _load_driver_price_records() -> dict[str, dict]:
    """Load optional volatile retailer prices generated into data/."""
    if not DRIVER_PRICES_PATH.exists():
        return {}
    try:
        payload = json.loads(DRIVER_PRICES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    prices = payload.get("prices", {})
    return prices if isinstance(prices, dict) else {}


def _preset_price(name: str, model: str = "", brand: str = "") -> tuple[float | None, str, str]:
    prices = _load_driver_price_records()
    for key in (name, model):
        price, currency, url = _price_from_record(prices.get(key), name, brand, model)
        if price is not None:
            return price, currency, url
    return None, "", ""


@lru_cache(maxsize=1)
def _load_loudspeaker_database_presets() -> tuple[dict[str, DriverTS], dict[str, DriverPresetInfo]]:
    """Load optional loudspeakerdatabase.com presets generated into data/."""
    if not LOUDSPEAKER_DATABASE_PATH.exists():
        return {}, {}

    payload = json.loads(LOUDSPEAKER_DATABASE_PATH.read_text(encoding="utf-8"))
    presets: dict[str, DriverTS] = {}
    info: dict[str, DriverPresetInfo] = {}
    for item in payload.get("presets", []):
        base_name = str(item["name"])
        name = base_name
        if name in DRIVER_PRESETS or name in presets:
            suffix = str(item.get("lsdb_id") or len(presets) + 1)
            name = f"{base_name} [LSDB {suffix}]"
        while name in DRIVER_PRESETS or name in presets:
            name = f"{base_name} [LSDB {len(presets) + 1}]"
        try:
            presets[name] = _driver_ts_from_mapping(item["driver"])
        except (KeyError, TypeError, ValueError):
            continue
        item_price = _valid_price(item.get("price"))
        item_currency = str(item.get("currency") or "")
        item_brand = str(item.get("brand") or "Other")
        item_model = str(item.get("model") or name.removeprefix("LSDB: "))
        enriched_price, enriched_currency, enriched_url = _preset_price(name, item_model, item_brand)
        info[name] = DriverPresetInfo(
            name=name,
            source="Loudspeaker Database",
            brand=item_brand,
            model=item_model,
            size_in=(
                float(item["size_in"])
                if item.get("size_in") is not None
                else None
            ),
            price=enriched_price if enriched_price is not None else item_price,
            currency=enriched_currency or item_currency,
            kind=str(item.get("kind") or ""),
            url=enriched_url or str(item.get("url") or ""),
        )
    return presets, info


def driver_preset_names() -> list[str]:
    """Return driver preset names in display order."""
    external, _info = _load_loudspeaker_database_presets()
    return [*DRIVER_PRESETS, *external]


def driver_preset_info(name: str) -> DriverPresetInfo:
    """Return source, brand and sizing metadata for a driver preset."""
    if name in DRIVER_PRESETS:
        brand = _built_in_preset_brand(name)
        model = name.removeprefix(brand).strip() if brand != "Other" else name
        price, currency, url = _preset_price(name, model, brand)
        return DriverPresetInfo(
            name=name,
            source="Built-in",
            brand=brand,
            model=model,
            price=price,
            currency=currency,
            url=url,
        )
    _external, info = _load_loudspeaker_database_presets()
    try:
        return info[name]
    except KeyError as exc:
        raise ValueError(f"Unknown driver preset: {name}") from exc


def get_driver_preset(name: str) -> DriverTS:
    """Return a driver preset by name."""
    if name in DRIVER_PRESETS:
        return DRIVER_PRESETS[name]
    external, _info = _load_loudspeaker_database_presets()
    try:
        return external[name]
    except KeyError as exc:
        raise ValueError(f"Unknown driver preset: {name}") from exc


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
    mms = (
        ts.mms_g / 1000.0
        if ts.mms_g is not None and ts.mms_g > 0
        else 1.0 / ((2.0 * np.pi * ts.fs_hz) ** 2 * cms)
    )
    rms = 2.0 * np.pi * ts.fs_hz * mms / ts.qms
    qes = 1.0 / (1.0 / ts.qts - 1.0 / ts.qms)
    bl = (
        ts.bl_tm
        if ts.bl_tm is not None and ts.bl_tm > 0
        else float(np.sqrt(2.0 * np.pi * ts.fs_hz * mms * ts.re_ohm / qes))
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
    fh = 1.22 * ts.fs_hz / ts.qts
    fl = 0.466 * ts.fs_hz / ts.qts
    return DccavAlignment(vh_l=vh, fh_hz=fh, vl_l=vl, fl_hz=fl, f3_hz=0.83 * fl)


def suggest_reflex_alignment(ts: DriverTS) -> ReflexAlignment:
    """Return a conservative bass-reflex starting point."""
    _require_positive("Fs", ts.fs_hz)
    _require_positive("Vas", ts.vas_l)
    return ReflexAlignment(vb_l=ts.vas_l, fb_hz=ts.fs_hz)


def sealed_system_metrics(ts: DriverTS, box: SealedBox) -> tuple[float, float]:
    """Return the classical closed-box ``(Fc, Qtc)`` pair."""
    _require_positive("Fs", ts.fs_hz)
    _require_positive("Vas", ts.vas_l)
    _require_positive("Qts", ts.qts)
    _validate_sealed_box(box)
    ratio = float(np.sqrt(1.0 + ts.vas_l / box.vb_l))
    return float(ts.fs_hz * ratio), float(ts.qts * ratio)


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
    box: DccavBox | ReflexBox | SealedBox | None = None,
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
        )
        try:
            if load_type == "Bass reflex":
                result = simulate_reflex(sample, box, freq, voltage_v, series_r_ohm)
            elif load_type == "Sealed":
                result = simulate_sealed(sample, box, freq, voltage_v, series_r_ohm)
            elif load_type == "Infinite baffle":
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


def price_extension_score(f3_hz: float, price: float) -> float:
    """Lower-is-better value score: bass extension weighted by driver price.

    ``F3 * price`` rewards drivers that are simultaneously cheap and deep.
    Missing or non-positive inputs return ``inf`` so unpriced candidates sink
    to the bottom of a value-sorted ranking.
    """
    f3 = float(f3_hz)
    value = float(price)
    if not (np.isfinite(f3) and np.isfinite(value)) or f3 <= 0.0 or value <= 0.0:
        return float("inf")
    return f3 * value


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
    end_correction: float = 1.463,
) -> float:
    """Return the physical tube length in cm of a circular port.

    Solves the Helmholtz relation `L_eff = c^2 * S / (w^2 * V)` for the
    requested chamber volume and tuning, then subtracts the end correction
    `end_correction * radius`.  The default 1.463 models one flanged plus one
    free end (a vent flush in a panel); use 1.7 for a port flanged on both
    ends, such as the DCCAV upper port joining two chambers.

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
    end_correction: float = 1.463,
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
    eta0 = 4.0 * np.pi**2 * ts.fs_hz**3 * vas_m3 / (SPEED_OF_SOUND**3 * drv.qes)
    spl_ref_db = 10.0 * np.log10(RHO_AIR * SPEED_OF_SOUND / (2.0 * np.pi * P_REF**2))
    spl_1w_db = spl_ref_db + 10.0 * np.log10(eta0)
    spl_2v83_db = spl_1w_db + 10.0 * np.log10(2.83**2 / ts.re_ohm)
    return DriverReferenceMetrics(
        eta0=float(eta0),
        spl_1w_db=float(spl_1w_db),
        spl_2v83_db=float(spl_2v83_db),
        ebp_hz=float(ts.fs_hz / drv.qes),
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
    end_correction: float = 1.463,
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


def _optimizer_metrics(
    ts: DriverTS,
    box: DccavBox | ReflexBox | SealedBox,
    freq: np.ndarray,
    voltage_v: float,
) -> dict[str, float]:
    if isinstance(box, ReflexBox):
        result = simulate_reflex(ts, box, freq, voltage_v)
        vtot = box.vb_l
        fl = box.fb_hz
    elif isinstance(box, SealedBox):
        result = simulate_sealed(ts, box, freq, voltage_v)
        vtot = box.vb_l
        fl = sealed_system_metrics(ts, box)[0]
    else:
        result = simulate(ts, box, freq, voltage_v)
        vtot = box.vh_l + box.vl_l
        fl = box.fl_hz
    thresholds = response_threshold_frequencies(result)
    f3 = thresholds[3]
    f10 = thresholds[10]
    f = result.frequency_hz
    spl = result.spl_total_db

    ripple = float("nan")
    gd_max = float("nan")
    if np.isfinite(f3):
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
        "total_volume_l": float(vtot),
        "fl_hz": float(fl),
        "sealed_fc_hz": equivalent_sealed_fc_hz(ts, box),
    }


def _score_alignment(metrics: dict[str, float], goals: OptimizationGoals, ts: DriverTS, is_dccav: bool) -> float:
    f3 = metrics["f3_hz"]
    if not np.isfinite(f3):
        return 1e6
    weights = _OBJECTIVE_WEIGHTS[goals.objective]
    ripple = metrics["ripple_db"]
    score = weights["f3"] * (max(f3, goals.target_f3_hz) if goals.target_f3_hz else f3) / ts.fs_hz
    if np.isfinite(ripple):
        score += weights["ripple"] * ripple / 6.0
        if goals.max_ripple_db and goals.max_ripple_db > 0 and ripple > goals.max_ripple_db:
            score += 2.0 * (ripple - goals.max_ripple_db)
    if goals.target_f3_hz and f3 > goals.target_f3_hz:
        score += 0.5 * (f3 - goals.target_f3_hz) / goals.target_f3_hz
    exc_ratio = metrics["excursion_ratio"]
    if goals.max_excursion_ratio and goals.max_excursion_ratio > 0 and np.isfinite(exc_ratio):
        if exc_ratio > goals.max_excursion_ratio:
            score += 4.0 * (exc_ratio - goals.max_excursion_ratio)
    gd = metrics["group_delay_ms"]
    if goals.max_group_delay_ms and np.isfinite(gd) and gd > goals.max_group_delay_ms:
        score += 1.0 * (gd / goals.max_group_delay_ms - 1.0)
    if goals.max_total_volume_l and metrics["total_volume_l"] > goals.max_total_volume_l:
        score += 20.0 * (metrics["total_volume_l"] / goals.max_total_volume_l - 1.0)
    # Keep the optimizer inside the same credibility region flagged by
    # response_sanity_warnings so it cannot chase fake loss-free extension.
    if is_dccav and f3 < 0.65 * metrics["fl_hz"]:
        score += 5.0
    if f3 < 0.50 * metrics["sealed_fc_hz"]:
        score += 5.0
    # Size regularizer so equal-scoring boxes prefer the smaller build; once a
    # requested F3 target is met, extra litres stop buying score elsewhere, so
    # push harder toward the compact solution.
    target_met = bool(goals.target_f3_hz) and f3 <= goals.target_f3_hz
    score += (0.15 if target_met else 0.02) * metrics["total_volume_l"] / max(ts.vas_l, EPS)
    return float(score)


_DEFAULT_GOALS = OptimizationGoals()


def optimize_alignment(
    ts: DriverTS,
    goals: OptimizationGoals = _DEFAULT_GOALS,
    load_type: str = "DCCAV",
    box_template: DccavBox | ReflexBox | SealedBox | None = None,
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
    freq = np.geomspace(min(10.0, ts.fs_hz / 4.0), max(400.0, 4.0 * ts.fs_hz), 160)
    if load_type not in {"DCCAV", "Bass reflex", "Sealed"}:
        if load_type == "Infinite baffle":
            raise ValueError("Infinite baffle has no box parameters to optimize")
        raise ValueError(f"Unknown load type: {load_type}")
    is_reflex = load_type == "Bass reflex"
    is_sealed = load_type == "Sealed"
    is_dccav = load_type == "DCCAV"
    cap = goals.max_total_volume_l
    minimum_volume_l = 0.10 if is_dccav else 0.05
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

    if is_reflex:
        start = suggest_reflex_alignment(ts)
        vb0, fb0 = start.vb_l, start.fb_hz
        if fixed_total_volume_l is not None:
            vb0 = float(fixed_total_volume_l)
        elif cap and vb0 > cap:
            vb0 = 0.95 * cap
        template = box_template if isinstance(box_template, ReflexBox) else ReflexBox(vb_l=vb0, fb_hz=fb0)

        def build(p: np.ndarray) -> ReflexBox:
            vb, fb = np.exp(p)
            if fixed_total_volume_l is not None:
                vb = float(fixed_total_volume_l)
            elif cap is not None:
                vb = min(float(vb), float(cap))
            return ReflexBox(
                vb_l=float(vb), fb_hz=float(fb),
                q_abs=template.q_abs, q_leak=template.q_leak, q_port=template.q_port,
            )

        p0 = np.log([vb0, fb0])
        lower = np.log([max(0.05, vb0 / 8.0), max(5.0, fb0 / 3.0)])
        upper = np.log([vb0 * 8.0, fb0 * 2.5])
    elif is_sealed:
        start = suggest_sealed_alignment(ts)
        vb0 = start.vb_l
        if fixed_total_volume_l is not None:
            vb0 = float(fixed_total_volume_l)
        elif cap and vb0 > cap:
            vb0 = 0.95 * cap
        template = box_template if isinstance(box_template, SealedBox) else SealedBox(vb_l=vb0)

        def build(p: np.ndarray) -> SealedBox:
            vb = float(np.exp(p[0]))
            if fixed_total_volume_l is not None:
                vb = float(fixed_total_volume_l)
            elif cap is not None:
                vb = min(vb, float(cap))
            return SealedBox(vb_l=vb, q_abs=template.q_abs, q_leak=template.q_leak)

        p0 = np.log([vb0])
        lower = np.log([max(0.05, vb0 / 12.0)])
        upper = np.log([vb0 * 12.0])
    else:
        start = suggest_alignment(ts)
        vh0, vl0, fl0 = start.vh_l, start.vl_l, start.fl_hz
        # The fh/fl ratio stays in a band around the article's 2.6 so the load
        # keeps its double-resonator character instead of degenerating into a
        # single reflex volume with an extreme upper tuning.
        ratio0 = float(np.clip(start.fh_hz / start.fl_hz, 1.2, 4.5))
        if fixed_total_volume_l is not None:
            scale = float(fixed_total_volume_l) / (vh0 + vl0)
            vh0 *= scale
            vl0 *= scale
        elif cap and vh0 + vl0 > cap:
            scale = 0.98 * cap / (vh0 + vl0)
            vh0 *= scale
            vl0 *= scale
        template = box_template if isinstance(box_template, DccavBox) else DccavBox(
            vh_l=vh0, fh_hz=fl0 * ratio0, vl_l=vl0, fl_hz=fl0
        )

        def build(p: np.ndarray) -> DccavBox:
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
                q_abs_h=template.q_abs_h, q_abs_l=template.q_abs_l,
                q_leak_h=template.q_leak_h, q_leak_l=template.q_leak_l,
                q_port_h=template.q_port_h, q_port_l=template.q_port_l,
            )

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
        return box, metrics, _score_alignment(metrics, goals, ts, is_dccav)

    best_p = np.clip(p0, lower, upper)
    best_box, best_metrics, best_score = evaluate(best_p)
    if best_metrics is None:
        raise ValueError("The starting alignment could not be simulated")

    step = 0.4
    while step >= 0.02 and evaluations < max_evaluations:
        improved = False
        for axis in range(len(best_p)):
            for sign in (1.0, -1.0):
                if evaluations >= max_evaluations:
                    break
                candidate = best_p.copy()
                candidate[axis] += sign * step
                candidate = np.clip(candidate, lower, upper)
                if np.allclose(candidate, best_p):
                    continue
                box, metrics, score = evaluate(candidate)
                if metrics is not None and score < best_score - 1e-9:
                    best_p, best_box, best_metrics, best_score = candidate, box, metrics, score
                    improved = True
        if not improved:
            step *= 0.5

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


def equivalent_sealed_fc_hz(ts: DriverTS, box: DccavBox | ReflexBox | SealedBox) -> float:
    """Return the closed-box Fc for the same total chamber volume."""
    _require_positive("Fs", ts.fs_hz)
    _require_positive("Vas", ts.vas_l)
    if isinstance(box, SealedBox):
        _validate_sealed_box(box)
        v_total = box.vb_l
    elif isinstance(box, ReflexBox):
        _validate_reflex_box(box)
        v_total = box.vb_l
    else:
        _validate_box(box)
        v_total = box.vh_l + box.vl_l
    return float(ts.fs_hz * np.sqrt(1.0 + ts.vas_l / v_total))


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
    limits: list[np.ndarray] = []
    shape = np.asarray(spl_total_db, dtype=float).shape
    if ts.xmax_mm > 0:
        excursion = np.maximum(np.asarray(excursion_mm, dtype=float), EPS)
        limits.append(float(voltage_v) * ts.xmax_mm / excursion)
    if ts.pe_w > 0:
        thermal_v = np.sqrt(ts.pe_w * ts.re_ohm) * re_total / ts.re_ohm
        limits.append(np.full(shape, thermal_v, dtype=float))

    if not limits:
        nan = np.full(shape, np.nan, dtype=float)
        return nan, nan

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
