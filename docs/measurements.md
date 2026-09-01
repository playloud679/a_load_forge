# Real Measurements & Simulation Validation (`src/measurements.py`)

## Overview

The `src/measurements.py` module provides robust multi-format electroacoustic measurement parsers and real-time comparison analytics. It enables Load Forge users and published projects to import raw real-world measurement curves, compare them directly against lumped-parameter matrix simulations, and quantify design fidelity with objective error metrics.

## Supported Measurement Formats

| Format | Source Software / Hardware | Typical Extensions | Supported Curve Types | Notes |
|---|---|---|---|---|
| **REW** | Room EQ Wizard | `.txt`, `.frd`, `.zma`, `.mdat` text | SPL (dB), Impedance ($\Omega$), Phase | Auto-detects `# REW`, column headers, and tabular formats |
| **DATS** | Dayton Audio Test System (v2 / v3) | `.zma`, `.frd`, `.txt` | Impedance ($\Omega$), SPL (dB) | Reads `Data:` block, handles resistance & reactance columns |
| **ARTA / LIMP** | ARTA Audio Measurement | `.txt`, `.frd`, `.zma` | SPL (dB), Impedance ($\Omega$), Phase | Handles semicolon delimiters and European decimal commas |
| **CLIO** | Audiomatica CLIO / CLIO Pocket | `.txt`, `.dat`, `.frd` | SPL (dB), Impedance ($\Omega$) | Strips CLIO metadata, replaces `,` with `.`, cleans headers |
| **Klippel** | Klippel Measurement System | `.txt`, `.frd`, `.zma` | SPL (dB), Impedance ($\Omega$) | Parses exported multi-column tabular measurement files |
| **Generic FRD / ZMA** | Industry Standard Text Files | `.frd`, `.zma`, `.txt`, `.csv` | 2-column or 3-column response | Automatically strips `#`, `//`, `*`, `;`, `!` comment lines |

## Core Data Structures

### `MeasurementCurve`

```python
@dataclass(frozen=True)
class MeasurementCurve:
    curve_type: str                  # "spl" or "impedance"
    freq: np.ndarray                 # 1D array of frequencies (Hz), sorted monotonically
    values: np.ndarray               # 1D array of magnitude (dB SPL or Ohms)
    phase: np.ndarray | None = None  # 1D array of phase angles (degrees), or None
    unit: str = "dB"                 # "dB" or "Ω"
    format_name: str = "generic"     # "rew", "dats", "arta", "clio", "klippel", "frd", "zma", "generic"
    label: str = "Measured Response" # User-facing curve label
    metadata: dict[str, Any]         # Extracted instrument details, notes, timestamps
```

### `MeasurementComparison`

```python
@dataclass(frozen=True)
class MeasurementComparison:
    curve_type: str
    sim_freq: np.ndarray
    sim_values: np.ndarray
    meas_freq: np.ndarray
    meas_values: np.ndarray
    interp_meas_values: np.ndarray   # Measured curve evaluated on simulation frequency grid
    valid_mask: np.ndarray           # Overlap mask where both traces are valid
    rmse: float                      # Root Mean Square Error in dB or Ohms
    max_abs_delta: float             # Maximum absolute difference in overlap region
    mean_delta: float                # Mean bias offset (sim - meas)
    overlap_f_min: float             # Low-frequency cutoff of valid comparison
    overlap_f_max: float             # High-frequency ceiling of valid comparison
    sim_fb_hz: float | None          # Tuning dip detected in simulation
    meas_fb_hz: float | None         # Tuning dip detected in physical measurement
    fb_delta_hz: float | None        # Tuning frequency delta (meas_fb - sim_fb) in Hz
```

## API Functions

### `parse_measurement_file(content, filename="", default_type="spl", label=None) -> MeasurementCurve`
Parses raw file string or bytes, detects format and delimiter conventions, normalizes European decimal commas, removes comment headers, ensures monotonic frequency ordering, and deduplicates identical frequency bins.

### `compare_simulation_to_measurement(sim_freq, sim_values, meas, freq_min=10.0, freq_max=500.0) -> MeasurementComparison`
Interpolates measurement values linearly in $\log_{10}(f)$ space onto the simulation grid. Calculates RMSE, peak absolute delta, mean offset, and automated port resonance saddle detection for vented alignments.

### `serialize_measurement(meas, max_points=400) -> dict` / `deserialize_measurement(data) -> MeasurementCurve`
Downsamples logarithmically and formats measurement curves into JSON-safe dictionaries for compact `.lfp` project files and Firestore cloud persistence.
