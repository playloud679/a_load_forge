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
from functools import lru_cache
from dataclasses import dataclass
from pathlib import Path

import numpy as np


RHO_AIR = 1.18
SPEED_OF_SOUND = 344.0
P_REF = 20e-6
EPS = 1e-30
LOUDSPEAKER_DATABASE_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "loudspeaker_database_drivers.json"
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
        info[name] = DriverPresetInfo(
            name=name,
            source="Loudspeaker Database",
            brand=str(item.get("brand") or "Other"),
            model=str(item.get("model") or name.removeprefix("LSDB: ")),
            size_in=(
                float(item["size_in"])
                if item.get("size_in") is not None
                else None
            ),
            kind=str(item.get("kind") or ""),
            url=str(item.get("url") or ""),
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
        return DriverPresetInfo(
            name=name,
            source="Built-in",
            brand=brand,
            model=name.removeprefix(brand).strip() if brand != "Other" else name,
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


def simulate(
    ts: DriverTS,
    box: DccavBox,
    freq_hz: np.ndarray | None = None,
    voltage_v: float = 2.83,
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

    z_as = drv.rat + jw * drv.mas + 1.0 / (jw * drv.cas)
    z_ab_h = _box_impedance(box.vh_l, box.fh_hz, box.q_abs_h, box.q_leak_h, w)
    z_ab_l = _box_impedance(box.vl_l, box.fl_hz, box.q_abs_l, box.q_leak_l, w)
    z_ap_h = _port_impedance(box.vh_l, box.fh_hz, box.q_port_h, w)
    z_ap_l = _port_impedance(box.vl_l, box.fl_hz, box.q_port_l, w)

    p_source = voltage_v * drv.bl_tm / (ts.re_ohm * drv.sd_m2)
    ya = 1.0 / z_as
    yab_h = 1.0 / z_ab_h
    yab_l = 1.0 / z_ab_l
    yap_h = 1.0 / z_ap_h
    yap_l = 1.0 / z_ap_l
    i_source = p_source / z_as

    node_a = np.empty_like(f, dtype=complex)
    node_b = np.empty_like(f, dtype=complex)
    for idx in range(len(f)):
        a = np.array(
            [
                [ya[idx] + yab_h[idx] + yap_h[idx], -yap_h[idx]],
                [-yap_h[idx], yap_h[idx] + yab_l[idx] + yap_l[idx]],
            ],
            dtype=complex,
        )
        b = np.array([i_source[idx], 0.0j], dtype=complex)
        node_a[idx], node_b[idx] = np.linalg.solve(a, b)

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
    mil_w, mol_db = _limit_curves(ts, voltage_v, spl_total, excursion)

    z_mech = drv.rms_n_s_m + jw * drv.mms_kg + 1.0 / (jw * drv.cms_m_per_n)
    z_load = _parallel(z_ab_h, z_ap_h + _parallel(z_ab_l, z_ap_l)) * drv.sd_m2**2
    z_e = ts.re_ohm + jw * (ts.le_mh / 1000.0) + drv.bl_tm**2 / (z_mech + z_load)

    return SimulationResult(
        frequency_hz=f,
        spl_total_db=spl_total,
        spl_driver_db=spl_driver,
        spl_port_db=spl_port,
        excursion_mm=excursion,
        impedance_ohm=np.abs(z_e),
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

    z_as = drv.rat + jw * drv.mas + 1.0 / (jw * drv.cas)
    z_ab = _box_impedance(box.vb_l, box.fb_hz, box.q_abs, box.q_leak, w)
    z_ap = _port_impedance(box.vb_l, box.fb_hz, box.q_port, w)

    p_source = voltage_v * drv.bl_tm / (ts.re_ohm * drv.sd_m2)
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
    mil_w, mol_db = _limit_curves(ts, voltage_v, spl_total, excursion)

    z_mech = drv.rms_n_s_m + jw * drv.mms_kg + 1.0 / (jw * drv.cms_m_per_n)
    z_load = _parallel(z_ab, z_ap) * drv.sd_m2**2
    z_e = ts.re_ohm + jw * (ts.le_mh / 1000.0) + drv.bl_tm**2 / (z_mech + z_load)

    return SimulationResult(
        frequency_hz=f,
        spl_total_db=spl_total,
        spl_driver_db=spl_driver,
        spl_port_db=spl_port,
        excursion_mm=excursion,
        impedance_ohm=np.abs(z_e),
        port_h_velocity=np.zeros_like(f),
        port_l_velocity=np.abs(u_port),
        mil_w=mil_w,
        mol_db=mol_db,
        driver_volume_velocity=u_front_driver,
        port_volume_velocity=u_port,
    )


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


def equivalent_sealed_fc_hz(ts: DriverTS, box: DccavBox | ReflexBox) -> float:
    """Return the closed-box Fc for the same total chamber volume."""
    _require_positive("Fs", ts.fs_hz)
    _require_positive("Vas", ts.vas_l)
    if isinstance(box, ReflexBox):
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
) -> tuple[np.ndarray, np.ndarray]:
    limits: list[np.ndarray] = []
    shape = np.asarray(spl_total_db, dtype=float).shape
    if ts.xmax_mm > 0:
        excursion = np.maximum(np.asarray(excursion_mm, dtype=float), EPS)
        limits.append(float(voltage_v) * ts.xmax_mm / excursion)
    if ts.pe_w > 0:
        limits.append(np.full(shape, np.sqrt(ts.pe_w * ts.re_ohm), dtype=float))

    if not limits:
        nan = np.full(shape, np.nan, dtype=float)
        return nan, nan

    mil_v = np.minimum.reduce(limits)
    mil_w = mil_v**2 / ts.re_ohm
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


def _require_positive(name: str, value: float) -> None:
    if not np.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be positive")
