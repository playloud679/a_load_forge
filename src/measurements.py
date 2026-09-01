"""Real electroacoustic measurement file parser and simulation comparison engine.

Supports importing and normalizing real-world measurement curves from all major
acoustic and impedance measurement platforms:
- REW (Room EQ Wizard): SPL and Impedance text exports, .frd, .zma
- DATS v2 / v3 (Dayton Audio Test System): .zma, .frd, .txt
- ARTA / LIMP: .txt, .frd, .zma
- CLIO / CLIO Pocket (Audiomatica): .txt, .dat, .frd
- Klippel: .txt, .frd, .zma exports
- Generic FRD / ZMA: 2-column or 3-column delimited files with comment filtering
"""

from __future__ import annotations

import io
import math
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import numpy as np


@dataclass(frozen=True)
class MeasurementCurve:
    """Represents an imported acoustic frequency response or impedance curve."""

    curve_type: str  # "spl" or "impedance"
    freq: np.ndarray  # 1D array of frequency points in Hz (monotonically increasing)
    values: np.ndarray  # 1D array of magnitude values (dB SPL for spl, Ohms for impedance)
    phase: np.ndarray | None = None  # 1D array of phase angles in degrees, or None
    unit: str = "dB"  # "dB" or "Ω"
    format_name: str = "generic"  # "rew", "dats", "arta", "clio", "klippel", "frd", "zma", "generic"
    label: str = "Measured Response"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if len(self.freq) != len(self.values):
            raise ValueError(
                f"Frequency length ({len(self.freq)}) does not match values length ({len(self.values)})"
            )
        if self.phase is not None and len(self.phase) != len(self.freq):
            raise ValueError(
                f"Phase length ({len(self.phase)}) does not match frequency length ({len(self.freq)})"
            )


@dataclass(frozen=True)
class MeasurementComparison:
    """Electroacoustic delta and error metrics comparing simulation against measurement."""

    curve_type: str
    sim_freq: np.ndarray
    sim_values: np.ndarray
    meas_freq: np.ndarray
    meas_values: np.ndarray
    interp_meas_values: np.ndarray  # Measured values evaluated at sim_freq
    valid_mask: np.ndarray  # Boolean mask where overlap is valid
    rmse: float  # Root Mean Square Error in dB or Ohms
    max_abs_delta: float  # Maximum absolute difference in overlap region
    mean_delta: float  # Mean difference (sim - meas) in overlap region
    overlap_f_min: float
    overlap_f_max: float
    sim_fb_hz: float | None = None  # Tuning frequency detected in simulation (if reflex)
    meas_fb_hz: float | None = None  # Tuning frequency detected in measurement
    fb_delta_hz: float | None = None  # Delta (meas_fb - sim_fb) in Hz


_COMMENT_PREFIXES = ("#", "*", "//", ";", "/*", "!", "%")

_REW_MARKERS = ("REW", "Room EQ Wizard", "Equalizer APO", "SPL_Magnitude", "SPL_Phase")
_DATS_MARKERS = ("DATS", "Dayton Audio", "Dayton Audio Test System")
_ARTA_MARKERS = ("ARTA", "ARTALab", "LIMP", "Stepped sine")
_CLIO_MARKERS = ("CLIO", "CLIOwin", "Audiomatica", "CLIOFile")
_KLIPPEL_MARKERS = ("KLIPPEL", "Klippel", "dB-Lab", "LPM")


def _detect_format_and_clean_lines(text: str) -> tuple[str, list[str], dict[str, Any]]:
    """Detect measurement format from text headers and return clean data lines."""
    lines = [line.strip() for line in text.splitlines()]
    header_lines = [l for l in lines if l and any(l.startswith(p) for p in _COMMENT_PREFIXES)]
    header_text = (" ".join(header_lines) + " " + text[:1500]).casefold()

    format_name = "generic"
    meta: dict[str, Any] = {}

    if any(m.casefold() in header_text for m in _REW_MARKERS) or "frequency (hz)" in header_text:
        format_name = "rew"
        meta["source"] = "Room EQ Wizard (REW)"
    elif any(m.casefold() in header_text for m in _DATS_MARKERS):
        format_name = "dats"
        meta["source"] = "Dayton Audio Test System (DATS)"
    elif any(m.casefold() in header_text for m in _ARTA_MARKERS):
        format_name = "arta"
        meta["source"] = "ARTA / LIMP"
    elif any(m.casefold() in header_text for m in _CLIO_MARKERS):
        format_name = "clio"
        meta["source"] = "Audiomatica CLIO"
    elif any(m.casefold() in header_text for m in _KLIPPEL_MARKERS):
        format_name = "klippel"
        meta["source"] = "Klippel Measurement System"

    # Extract any title/notes in header
    for hl in header_lines:
        clean = hl.lstrip("#*//;!% ").strip()
        if clean and not any(clean.lower().startswith(k) for k in ("freq", "data", "date", "time")):
            if "notes" not in meta:
                meta["notes"] = clean

    # Strip comments and empty lines for numeric parsing
    data_lines = [
        line for line in lines
        if line and not any(line.startswith(p) for p in _COMMENT_PREFIXES)
    ]
    return format_name, data_lines, meta


def parse_measurement_file(
    content: str | bytes,
    filename: str = "",
    default_type: str = "spl",
    label: str | None = None,
) -> MeasurementCurve:
    """Parse real measurement curves from REW, DATS, ARTA, CLIO, Klippel, or generic FRD/ZMA.

    Args:
        content: Raw file string or bytes.
        filename: Optional filename to assist curve type and format detection.
        default_type: Default curve type ("spl" or "impedance") if not detectable.
        label: Custom display label for the curve.

    Returns:
        MeasurementCurve dataclass with normalized frequencies and values.
    """
    if isinstance(content, bytes):
        for enc in ("utf-8", "utf-8-sig", "latin-1", "cp1252", "utf-16"):
            try:
                text = content.decode(enc)
                break
            except (UnicodeDecodeError, LookupError):
                continue
        else:
            text = content.decode("utf-8", errors="replace")
    else:
        text = str(content)

    format_name, data_lines, meta = _detect_format_and_clean_lines(text)

    # Detect curve type from filename or format
    fn_lower = filename.lower()
    if fn_lower.endswith(".zma") or "impedance" in fn_lower or "zma" in fn_lower or "z_" in fn_lower:
        curve_type = "impedance"
    elif fn_lower.endswith(".frd") or "spl" in fn_lower or "frd" in fn_lower or "fr_" in fn_lower:
        curve_type = "spl"
    elif "impedance" in text[:300].lower() or "ohm" in text[:300].lower():
        curve_type = "impedance"
    else:
        curve_type = default_type.lower()

    if not label:
        if filename:
            label = re.sub(r"\.(frd|zma|txt|csv|dat|mdat)$", "", filename, flags=re.IGNORECASE)
        else:
            label = "Measured " + ("Impedance" if curve_type == "impedance" else "SPL")

    freq_list: list[float] = []
    val_list: list[float] = []
    phase_list: list[float] = []
    has_phase = False

    for raw_line in data_lines:
        line = raw_line.strip()
        if not line:
            continue

        # Handle comma as decimal separator in Italian/European exports (e.g. 40,5 85,2)
        # Semicolon or tab or whitespace delimiter
        if ";" in line:
            parts = [p.strip().replace(",", ".") for p in line.split(";") if p.strip()]
        elif "\t" in line:
            parts = [p.strip().replace(",", ".") for p in line.split("\t") if p.strip()]
        elif "," in line and line.count(",") >= 2 and not re.search(r"\d,\d", line):
            # Comma separated columns (standard CSV)
            parts = [p.strip() for p in line.split(",") if p.strip()]
        else:
            # Whitespace separated columns, with potential decimal comma if single comma per number
            parts = [p.strip().replace(",", ".") for p in line.split() if p.strip()]

        if len(parts) < 2:
            continue

        try:
            f_val = float(parts[0])
            v_val = float(parts[1])
            if f_val <= 0.0 or not math.isfinite(f_val) or not math.isfinite(v_val):
                continue

            freq_list.append(f_val)
            val_list.append(v_val)

            if len(parts) >= 3:
                try:
                    p_val = float(parts[2])
                    if math.isfinite(p_val):
                        phase_list.append(p_val)
                        has_phase = True
                    else:
                        phase_list.append(0.0)
                except ValueError:
                    phase_list.append(0.0)
            else:
                phase_list.append(0.0)
        except ValueError:
            # Skip non-numeric header/summary lines
            continue

    if not freq_list:
        raise ValueError(
            f"No valid numeric measurement data could be parsed from {filename or 'file'}"
        )

    # Sort monotonically by frequency
    f_arr = np.array(freq_list, dtype=float)
    v_arr = np.array(val_list, dtype=float)
    p_arr = np.array(phase_list, dtype=float) if has_phase else None

    sort_idx = np.argsort(f_arr)
    f_arr = f_arr[sort_idx]
    v_arr = v_arr[sort_idx]
    if p_arr is not None:
        p_arr = p_arr[sort_idx]

    # Deduplicate exact duplicate frequencies by taking mean value
    unique_f, u_idx = np.unique(f_arr, return_index=True)
    if len(unique_f) < len(f_arr):
        f_arr = unique_f
        v_arr = v_arr[u_idx]
        if p_arr is not None:
            p_arr = p_arr[u_idx]

    unit = "Ω" if curve_type == "impedance" else "dB"

    return MeasurementCurve(
        curve_type=curve_type,
        freq=f_arr,
        values=v_arr,
        phase=p_arr,
        unit=unit,
        format_name=format_name,
        label=label,
        metadata=meta,
    )


def compare_simulation_to_measurement(
    sim_freq: np.ndarray,
    sim_values: np.ndarray,
    meas: MeasurementCurve,
    freq_min: float = 10.0,
    freq_max: float = 500.0,
) -> MeasurementComparison:
    """Compare simulation curve against an imported measurement on common frequency grid.

    Calculates:
    - Overlap evaluation grid
    - Root Mean Square Error (RMSE)
    - Peak absolute delta
    - Mean bias delta
    - Tuning frequency offset (for impedance reflex dips)
    """
    sim_f = np.asarray(sim_freq, dtype=float)
    sim_v = np.asarray(sim_values, dtype=float)
    meas_f = np.asarray(meas.freq, dtype=float)
    meas_v = np.asarray(meas.values, dtype=float)

    f_min = max(float(np.min(sim_f)), float(np.min(meas_f)), freq_min)
    f_max = min(float(np.max(sim_f)), float(np.max(meas_f)), freq_max)

    if f_min >= f_max:
        # Fallback to full measurement overlap
        f_min = max(float(np.min(sim_f)), float(np.min(meas_f)))
        f_max = min(float(np.max(sim_f)), float(np.max(meas_f)))

    # Interpolate measurement linearly in log10(frequency) space
    log_meas_f = np.log10(meas_f)
    log_sim_f = np.log10(sim_f)

    interp_meas_v = np.interp(log_sim_f, log_meas_f, meas_v)
    valid_mask = (sim_f >= f_min) & (sim_f <= f_max) & np.isfinite(sim_v) & np.isfinite(interp_meas_v)

    if np.any(valid_mask):
        diff = sim_v[valid_mask] - interp_meas_v[valid_mask]
        rmse = float(np.sqrt(np.mean(diff ** 2)))
        max_abs = float(np.max(np.abs(diff)))
        mean_d = float(np.mean(diff))
    else:
        rmse = 0.0
        max_abs = 0.0
        mean_d = 0.0

    # Tuning resonance detection for impedance curves (saddle minimum between twin peaks)
    sim_fb = None
    meas_fb = None
    fb_delta = None

    if meas.curve_type == "impedance":
        sim_fb = _detect_impedance_tuning_min(sim_f, sim_v, 20.0, 120.0)
        meas_fb = _detect_impedance_tuning_min(meas_f, meas_v, 20.0, 120.0)
        if sim_fb is not None and meas_fb is not None:
            fb_delta = meas_fb - sim_fb

    return MeasurementComparison(
        curve_type=meas.curve_type,
        sim_freq=sim_f,
        sim_values=sim_v,
        meas_freq=meas_f,
        meas_values=meas_v,
        interp_meas_values=interp_meas_v,
        valid_mask=valid_mask,
        rmse=rmse,
        max_abs_delta=max_abs,
        mean_delta=mean_d,
        overlap_f_min=f_min,
        overlap_f_max=f_max,
        sim_fb_hz=sim_fb,
        meas_fb_hz=meas_fb,
        fb_delta_hz=fb_delta,
    )


def _detect_impedance_tuning_min(
    freq: np.ndarray,
    z_ohms: np.ndarray,
    f_search_min: float = 20.0,
    f_search_max: float = 120.0,
) -> float | None:
    """Detect the port tuning dip (Fb) in a reflex/DCCAV twin-peak impedance curve."""
    mask = (freq >= f_search_min) & (freq <= f_search_max)
    if not np.any(mask) or np.count_nonzero(mask) < 5:
        return None

    sub_f = freq[mask]
    sub_z = z_ohms[mask]

    # Find internal local maxima (peaks)
    peaks = []
    for i in range(1, len(sub_z) - 1):
        if sub_z[i] > sub_z[i - 1] and sub_z[i] > sub_z[i + 1]:
            peaks.append(i)

    if len(peaks) >= 2:
        sorted_peaks = sorted(peaks, key=lambda i: sub_z[i], reverse=True)[:2]
        p1, p2 = sorted(sorted_peaks)
        if p2 - p1 > 1:
            saddle_idx = p1 + int(np.argmin(sub_z[p1:p2 + 1]))
            return float(sub_f[saddle_idx])

    # Fallback: search for internal local minimum
    minima = []
    for i in range(1, len(sub_z) - 1):
        if sub_z[i] < sub_z[i - 1] and sub_z[i] < sub_z[i + 1]:
            minima.append(i)
    if minima:
        best_min = min(minima, key=lambda i: sub_z[i])
        return float(sub_f[best_min])

    return None


def serialize_measurement(meas: MeasurementCurve, max_points: int = 400) -> dict[str, Any]:
    """Serialize a MeasurementCurve into a compact JSON-compatible dictionary."""
    f = meas.freq
    v = meas.values
    p = meas.phase

    # Downsample logarithmically if curve contains too many points for storage
    if len(f) > max_points:
        idx = np.round(np.linspace(0, len(f) - 1, max_points)).astype(int)
        idx = np.unique(idx)
        f = f[idx]
        v = v[idx]
        if p is not None:
            p = p[idx]

    return {
        "curve_type": meas.curve_type,
        "label": meas.label,
        "format_name": meas.format_name,
        "unit": meas.unit,
        "freq": [round(float(x), 3) for x in f],
        "values": [round(float(x), 3) for x in v],
        "phase": [round(float(x), 2) for x in p] if p is not None else None,
        "metadata": meas.metadata,
    }


def deserialize_measurement(data: Mapping[str, Any]) -> MeasurementCurve:
    """Reconstruct a MeasurementCurve from a JSON dictionary."""
    freq = np.array(data.get("freq", []), dtype=float)
    values = np.array(data.get("values", []), dtype=float)
    phase_data = data.get("phase")
    phase = np.array(phase_data, dtype=float) if phase_data is not None else None

    return MeasurementCurve(
        curve_type=str(data.get("curve_type", "spl")),
        freq=freq,
        values=values,
        phase=phase,
        unit=str(data.get("unit", "dB")),
        format_name=str(data.get("format_name", "generic")),
        label=str(data.get("label", "Measured Response")),
        metadata=dict(data.get("metadata", {})),
    )
