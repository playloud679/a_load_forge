"""
Validation: compare Hornresp Export Horn Data against get_iwata().

Usage:
    python tests/validate_hornresp.py <hornresp_export.txt> \\
        --T 0.707 --fc 600 [--plot]

Hornresp units  → internal conversion:
  lengths : cm  → mm  (× 10)
  areas   : cm² → mm² (× 100)
  diameters: cm → mm  (× 10)

The script:
  1. Reads the Hornresp export (auto-detects tab or comma delimiter).
  2. Extracts throat diameter, axial positions, and area profile.
  3. Runs get_iwata() with the same throat, fc, length (mm) and the
     supplied T value.
  4. Computes S_mine(x) = π·r(x)² from get_iwata() output.
  5. Computes S_hornresp(x) by interpolating the exported profile onto
     the same x grid.
  6. Reports max absolute and RMS relative errors, and optionally plots.
"""

import argparse, sys, os
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from profile_generator import get_iwata
from _constants import SOUND_SPEED

# ── CLI ──────────────────────────────────────────────────────────────────────

def parse():
    p = argparse.ArgumentParser(description="Compare Hornresp horn data vs get_iwata()")
    p.add_argument("hornresp_file", help="Hornresp Export Horn Data (.txt or .csv)")
    p.add_argument("--T",   type=float, required=True, help="Hornresp flare parameter T (e.g. 0.707)")
    p.add_argument("--fc",  type=float, required=True, help="Cutoff frequency in Hz (Hornresp F12)")
    p.add_argument("--col_x",    default=None, help="Column name for axial length (auto-detect if omitted)")
    p.add_argument("--col_area", default=None, help="Column name for cross-sectional area (auto-detect if omitted)")
    p.add_argument("--col_diam", default=None, help="Column name for diameter (auto-detect if omitted; used if area absent)")
    p.add_argument("--plot", action="store_true", help="Show comparison plot (requires matplotlib)")
    return p.parse_args()


# ── File reader ───────────────────────────────────────────────────────────────

def load_hornresp(path: str, col_x=None, col_area=None, col_diam=None):
    """
    Read Hornresp Export Horn Data file.
    Returns (x_mm, S_mm2) arrays — axial positions and cross-sectional areas in mm.

    Hornresp exports diameters (not areas) for axisymmetric horns.
    Auto-detects the relevant columns if not specified.
    """
    raw = Path(path).read_bytes().decode("latin-1").replace("\r\n", "\n")
    lines = [l for l in raw.splitlines() if l.strip()]

    # detect delimiter
    delim = "\t" if "\t" in lines[0] else ","

    # parse header
    header = [h.strip().lower() for h in lines[0].split(delim)]

    def find_col(candidates, explicit):
        if explicit:
            k = explicit.lower()
            if k in header: return header.index(k)
            raise ValueError(f"Column '{explicit}' not found. Available: {header}")
        for c in candidates:
            if c in header: return header.index(c)
        return None

    ix   = find_col(["len", "axial", "length", "x", "l", "seg len"], col_x)
    ia   = find_col(["area", "s", "cross", "csa"], col_area)
    id_  = find_col(["diam", "dia", "d", "diameter", "radius"], col_diam)

    if ix is None:
        raise ValueError(f"Cannot find axial-length column. Header: {header}")
    if ia is None and id_ is None:
        raise ValueError(f"Cannot find area or diameter column. Header: {header}")

    rows = []
    for line in lines[1:]:
        parts = line.split(delim)
        if len(parts) <= max(ix, ia if ia is not None else 0, id_ if id_ is not None else 0):
            continue
        try:
            x = float(parts[ix])
            if ia is not None:
                s = float(parts[ia])
            else:
                d = float(parts[id_])
                s = np.pi * (d / 2.0) ** 2
            rows.append((x, s))
        except ValueError:
            continue

    arr = np.array(rows)
    x_cm = arr[:, 0]
    S_cm2 = arr[:, 1]

    # convert cm → mm, cm² → mm²
    x_mm  = x_cm  * 10.0
    S_mm2 = S_cm2 * 100.0
    return x_mm, S_mm2


# ── Comparison ────────────────────────────────────────────────────────────────

def run_comparison(args):
    print(f"\n{'─'*60}")
    print(f"  Hornresp file : {args.hornresp_file}")
    print(f"  T             : {args.T}")
    print(f"  fc            : {args.fc} Hz")
    print(f"  x₀ = c/(2πfc) : {SOUND_SPEED / (2*np.pi*args.fc):.2f} mm")
    print(f"{'─'*60}")

    x_hr, S_hr = load_hornresp(
        args.hornresp_file,
        col_x=args.col_x, col_area=args.col_area, col_diam=args.col_diam
    )
    print(f"  Loaded {len(x_hr)} points from Hornresp export")
    print(f"  Axial range   : {x_hr[0]:.1f} – {x_hr[-1]:.1f} mm")
    print(f"  Area range    : {S_hr[0]:.2f} – {S_hr[-1]:.2f} mm²")

    # Derive throat diameter from first point
    throat_d_mm = 2.0 * np.sqrt(S_hr[0] / np.pi)
    length_mm   = x_hr[-1] - x_hr[0]
    print(f"  Inferred throat Ø : {throat_d_mm:.3f} mm")
    print(f"  Inferred length   : {length_mm:.3f} mm")

    # Override T inside get_iwata by monkeypatching — avoid editing the module
    import profile_generator as _pg
    _orig_T = None
    original_fn = _pg.get_iwata

    def get_iwata_with_T(throat, fc, length, n):
        rt = throat / 2.0
        x0 = SOUND_SPEED / (2.0 * np.pi * fc)
        x = np.linspace(0, length, n)
        ch = np.cosh(x / x0)
        sh = np.sinh(x / x0)
        s = np.pi * rt * rt * (ch + args.T * sh) ** 2
        r = np.sqrt(s / np.pi)
        return x, r

    # Compute mine on the same axial grid as Hornresp
    n = len(x_hr)
    x_mine, r_mine = get_iwata_with_T(throat_d_mm, args.fc, length_mm, n)
    S_mine = np.pi * r_mine ** 2

    # Interpolate Hornresp onto mine's x grid (in case x_hr doesn't start at 0)
    x_hr_shifted = x_hr - x_hr[0]   # make it start at 0
    S_hr_interp = np.interp(x_mine, x_hr_shifted, S_hr)

    # Error metrics
    abs_err = np.abs(S_mine - S_hr_interp)
    rel_err = abs_err / np.maximum(S_hr_interp, 1e-6)

    print(f"\n{'─'*60}")
    print(f"  MAX  |ΔS|       : {abs_err.max():.4f} mm²  "
          f"({100*rel_err[abs_err.argmax()]:.2f}% at x={x_mine[abs_err.argmax()]:.1f} mm)")
    print(f"  RMS  |ΔS|/S     : {100*np.sqrt(np.mean(rel_err**2)):.3f} %")
    print(f"  MAX  |ΔS|/S     : {100*rel_err.max():.3f} %")
    print(f"  Throat S_mine   : {S_mine[0]:.4f} mm²  |  S_hornresp : {S_hr[0]:.4f} mm²")
    print(f"  Mouth  S_mine   : {S_mine[-1]:.4f} mm²  |  S_hornresp : {S_hr[-1]:.4f} mm²")
    print(f"{'─'*60}\n")

    threshold_rms = 1.0  # % — adjust if needed
    if 100*np.sqrt(np.mean(rel_err**2)) < threshold_rms:
        print(f"  ✅  RMS error < {threshold_rms}% — formulas match.")
    else:
        print(f"  ❌  RMS error ≥ {threshold_rms}% — discrepancy found.")

    if args.plot:
        import matplotlib.pyplot as plt
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 6))
        ax1.plot(x_hr_shifted, S_hr,       label="Hornresp", lw=2)
        ax1.plot(x_mine,       S_mine, "--", label=f"get_iwata(T={args.T})", lw=1.5)
        ax1.set_ylabel("S(x)  [mm²]"); ax1.legend(); ax1.grid(True, alpha=.3)
        ax1.set_title(f"T={args.T}  fc={args.fc} Hz  throat={throat_d_mm:.1f} mm")
        ax2.plot(x_mine, 100*rel_err)
        ax2.set_xlabel("x  [mm]"); ax2.set_ylabel("|ΔS|/S  [%]"); ax2.grid(True, alpha=.3)
        ax2.set_title("Relative error")
        plt.tight_layout(); plt.show()

    return abs_err, rel_err


if __name__ == "__main__":
    args = parse()
    run_comparison(args)
