#!/usr/bin/env python3
"""Generate an AFW v2 DCCAV/DCAAV project from a Load Forge ``.lfp`` design.

This is the write-side counterpart to ``tools/compare_afw_sealed.py``, which
only reads sealed/BP4/BP6 projects and explicitly rejects AFW load code 6
(``doppio reflex parallelo`` / DCAAV, Load Forge's DCCAV). AFW itself never
exposes an export format Load Forge could target directly, so this tool
works the other way: it takes one of the existing hand-verified DCAAV
projects in ``examples/afw_bass_match_9/`` as a byte-level template and
substitutes the new driver's T/S set and this project's chamber
volumes/tunings/loss-Q values into the exact same field positions.

Byte layout (found by locating the embedded 201-point CRW driver block and
walking backward, the same technique ``compare_afw_sealed.py`` uses for
sealed/BP4/BP6 — confirmed identical for the DCAAV files in
``examples/afw_bass_match_9/``):

- ``driver_at - 490``: AFW load code (``6`` for DCAAV/DCCAV). Verified to
  vary correctly across all 9 example templates (1=sealed, 3=BP4, 4=BP6,
  6=DCAAV), unlike the chamber block below.
- ``len(lines) - 90`` .. ``+ 17``: the real 18-value "Caricamento in doppio
  carico asimmetrico a vista" dialog block, a FIXED offset from the end of
  the file (confirmed identical across all 9 example templates AND an
  independent file re-saved by the real AUDIO per Windows software — this
  AFW format pads every project to a constant total line count regardless
  of driver/via count, so this anchor is more reliable than any offset
  relative to ``driver_at``):
  ``[Vh_m3, Fh_hz, virtual_volume_factor_h, q_leak_h ("Q box"),
    q_abs_h ("Q coibente"), Vl_m3, Fl_hz, virtual_volume_factor_l,
    q_leak_l ("Q box"), q_abs_l ("Q coibente"), condotti_h (port count,
    always 1), diam_h_m, lunghezza_h_m, q_port_h ("Qp"), condotti_l
    (always 1), diam_l_m, lunghezza_l_m, q_port_l ("Qp")]``
  Ground truth for every field above was confirmed digit-for-digit against
  the real software's own "Caricamento" dialog screenshots (Vh 2.06 L @
  273.3 Hz, port 7.3 cm x 3 cm Qp 189.3 / Vl 4.15 L @ 104.8 Hz, port 2.9 cm
  x 3 cm Qp 51.9) using ``09_fostex_fe126_dcaav.afw`` re-opened and re-saved
  in the real software as a probe. There is a SECOND, superficially similar
  10-value block at ``driver_at - 230`` (the previous version of this tool
  wrote there) that the real software's dialog does NOT read — its values
  differ from the dialog's actual display and it is followed by unrelated
  crossover-filter coefficients, not port geometry; do not use it.
  ``virtual_volume_factor`` ("Coeff. correttivo volume") is always written
  as ``1.0`` — Load Forge's own Vh/Vl are already the net acoustic volume
  AFW calls "virtual", so there is no separate physical/virtual split to
  express. "Q box" vs "Q coibente" is a best-effort label match (box/leakage
  losses vs lining/absorption losses respectively) rather than an
  independently reverse-engineered formula — the values are close enough in
  magnitude to Load Forge's own ``q_leak``/``q_abs`` defaults to support
  this pairing, but treat it with the same caution as any single-example
  mapping.
- ``driver_at``: CRW curve title line
- ``driver_at + 1`` .. ``+ 1005``: 201 points x 5 values generated from the
  current driver's Load Forge infinite-baffle response (frequency, SPL,
  acoustic phase, impedance and impedance phase). AFW then applies its own
  DCCAV loading to this driver curve.
- ``driver_at + 1006`` .. ``+ 1016``: the 11 trailing T/S values
  ``[re_ohm, fs_hz, qms, qes, vas_m3, le_h, le_exponent, le_phase_factor,
    xmax_m, pe_w, sd_m2]``
- ``driver_at - 3044`` / ``driver_at - 3043``: transducer Larghezza/Altezza
  (width/height, metres). AFW's own "Definizione trasduttore" dialog does
  NOT read ``sd_m2`` from the tail block above to display Sd -- it
  recomputes Sd from these two independent shape fields
  (``pi * (Larghezza / 2) * (Altezza / 2)``), since AFW also supports oval
  drivers where width and height differ. Both reference templates leave
  them at a near-circular ~9 cm default (``0.09`` / ``0.095``) regardless of
  the real driver's Sd (confirmed identical across the Dayton UM12 and
  Fostex FE126 examples, whose real Sd values differ 7x). This tool only
  builds round drivers, so both fields get the same diameter implied by
  this project's own ``driver_sd_cm2`` -- otherwise leaving Altezza at its
  template default would silently make the shape oval instead of circular.
- ``driver_at - 3039``: "Nome Trasduttore" short name field, also left at
  the template's generic ``FE126ris`` default in both references.

Usage:
    .venv/bin/python tools/generate_afw_dccav.py path/to/design.lfp \\
        --template examples/afw_bass_match_9/09_fostex_fe126_dcaav.afw \\
        --output out.afw
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))
import compare_afw_sealed as afw  # noqa: E402
import engine as _engine  # noqa: E402

DEFAULT_TEMPLATE = ROOT / "examples" / "afw_bass_match_9" / "09_fostex_fe126_dcaav.afw"
# Fixed distance from the end of the file to the 18-value chamber/port block;
# see the module docstring for how this was confirmed.
_CHAMBER_BLOCK_FROM_END = 90


def _lfp_driver_ts(lfp: dict) -> dict:
    qts = float(lfp["driver_qts"])
    qms = float(lfp["driver_qms"])
    if qms <= qts:
        raise ValueError("driver_qms must exceed driver_qts to derive Qes")
    qes = qts * qms / (qms - qts)
    return {
        "re_ohm": float(lfp["driver_re_ohm"]),
        "fs_hz": float(lfp["driver_fs_hz"]),
        "qms": qms,
        "qes": qes,
        "vas_m3": float(lfp["driver_vas_l"]) / 1000.0,
        "le_h": float(lfp.get("driver_le_mh", 0.0)) / 1000.0,
        "le_exponent": 0.0,
        "le_phase_factor": 0.0,
        "xmax_m": float(lfp.get("driver_xmax_mm", 0.0)) / 1000.0,
        "pe_w": float(lfp.get("driver_pe_w", 0.0)),
        "sd_m2": float(lfp["driver_sd_cm2"]) / 10_000.0,
    }


def _crw_curve_values(lfp: dict) -> list[tuple[float, float, float, float, float]]:
    """Generate AFW's five CRW columns from the current driver simulation."""
    ts = _engine.DriverTS(
        fs_hz=float(lfp["driver_fs_hz"]), vas_l=float(lfp["driver_vas_l"]),
        qts=float(lfp["driver_qts"]), qms=float(lfp["driver_qms"]),
        re_ohm=float(lfp["driver_re_ohm"]), sd_cm2=float(lfp["driver_sd_cm2"]),
        le_mh=float(lfp.get("driver_le_mh", 0.0)),
        xmax_mm=float(lfp.get("driver_xmax_mm", 0.0)),
        pe_w=float(lfp.get("driver_pe_w", 0.0)),
    )
    frequency = np.geomspace(2.0, 200_000.0, 201)
    result = _engine.simulate_infinite_baffle(ts, frequency, voltage_v=2.83)
    phase = _engine.response_phase_deg(result)
    zphase = np.asarray(result.impedance_phase_deg, dtype=float)
    return list(zip(
        frequency, result.spl_total_db, phase, result.impedance_ohm, zphase,
        strict=True,
    ))


def _write_crw_curve(lines: list[str], driver_at: int, lfp: dict) -> None:
    for index, values in enumerate(_crw_curve_values(lfp)):
        start = driver_at + 1 + index * 5
        for offset, value in enumerate(values):
            lines[start + offset] = f" {float(value):.8g}"


def generate_afw_text(lfp: dict, template_path: Path = DEFAULT_TEMPLATE, title: str | None = None) -> str:
    """Build the AFW project text in memory (no filesystem output side effect)."""
    if lfp.get("load_type") != "DCCAV":
        raise ValueError(f"load_type={lfp.get('load_type')!r}, expected DCCAV")

    lines = template_path.read_text(encoding="latin-1").splitlines()
    driver_at, _template_driver = afw._find_driver_block(lines)

    code_at = driver_at - 490
    if int(afw._number(lines[code_at])) != 6:
        raise ValueError(f"{template_path} is not an AFW load-code-6 (DCAAV) template")

    vh_l = float(lfp["box_vh_l"])
    fh_hz = float(lfp["box_fh_hz"])
    vl_l = float(lfp["box_vl_l"])
    fl_hz = float(lfp["box_fl_hz"])
    port_d_h_cm = float(lfp.get("box_port_d_h_cm", 5.0))
    port_d_l_cm = float(lfp.get("box_port_d_l_cm", 5.0))
    # Upper DCCAV port is flanged on both ends (joins two internal chambers,
    # per engine.port_length_cm's own docstring); lower port is flanged on
    # one end, free on the other (opens to the outside).
    port_len_h_cm = _engine.port_length_cm(vh_l, fh_hz, port_d_h_cm, end_correction=1.64)
    port_len_l_cm = _engine.port_length_cm(vl_l, fl_hz, port_d_l_cm, end_correction=1.43)

    block_at = len(lines) - _CHAMBER_BLOCK_FROM_END
    box = {
        0: vh_l / 1000.0,
        1: fh_hz,
        2: 1.0,
        3: float(lfp.get("loss_q_leak_h", 1000.0)),
        4: float(lfp.get("loss_q_abs_h", 15.0)),
        5: vl_l / 1000.0,
        6: fl_hz,
        7: 1.0,
        8: float(lfp.get("loss_q_leak_l", 1000.0)),
        9: float(lfp.get("loss_q_abs_l", 15.0)),
        10: 1,
        11: port_d_h_cm / 100.0,
        12: max(port_len_h_cm, 0.0) / 100.0,
        13: float(lfp.get("loss_q_port_h", 15.0)),
        14: 1,
        15: port_d_l_cm / 100.0,
        16: max(port_len_l_cm, 0.0) / 100.0,
        17: float(lfp.get("loss_q_port_l", 15.0)),
    }
    for offset, value in box.items():
        lines[block_at + offset] = f" {value:.8g}"

    driver_name = str(lfp.get("driver_preset_name") or "Custom driver")
    # AFW project text is Latin-1 (ISO-8859-1); the omega ohm sign and other
    # characters outside that codepage can't round-trip, so ASCII-fold them.
    ascii_name = driver_name.replace("Ω", "Ohm").encode("latin-1", "replace").decode("latin-1")
    lines[driver_at] = title or f"Load Forge Bass Match - DCCAV - {ascii_name}"
    _write_crw_curve(lines, driver_at, lfp)

    # AFW's "Definizione trasduttore" dialog does NOT read Sd from the T/S
    # tail block below -- it displays Sd = pi * (Larghezza / 2) * (Altezza / 2),
    # computed from two independent transducer *shape* fields (AFW supports
    # oval drivers, so width and height are not tied together). Both
    # reference templates leave them at a near-circular ~9 cm default
    # (0.09 m / 0.095 m) regardless of the actual driver (confirmed
    # empirically: diffing 08_dayton_um12_dcaav.afw against
    # 09_fostex_fe126_dcaav.afw shows zero differing lines in this region
    # even though their real Sd values differ by 7x). This tool only builds
    # round drivers, so both fields are set to the same diameter implied by
    # this driver's own Sd -- otherwise leaving Altezza at its template
    # default would silently make the shape oval instead of circular.
    width_at = driver_at - 3044
    height_at = driver_at - 3043
    short_name_at = driver_at - 3039  # "Nome Trasduttore" short name field
    sd_cm2 = float(lfp["driver_sd_cm2"])
    diameter_m = 2.0 * math.sqrt(sd_cm2 / math.pi) / 100.0
    lines[width_at] = f" {diameter_m:.8g}"
    lines[height_at] = f" {diameter_m:.8g}"
    lines[short_name_at] = ascii_name[:40] or "Custom"

    ts = _lfp_driver_ts(lfp)
    tail_at = driver_at + 1 + 201 * 5
    tail_order = (
        "re_ohm", "fs_hz", "qms", "qes", "vas_m3", "le_h",
        "le_exponent", "le_phase_factor", "xmax_m", "pe_w", "sd_m2",
    )
    for i, key in enumerate(tail_order):
        lines[tail_at + i] = f" {ts[key]:.8g}"

    return "\r\n".join(lines) + "\r\n"


def generate_crw_text(lfp: dict, template_path: Path = DEFAULT_TEMPLATE, title: str | None = None) -> str:
    """Build a standalone CRW file with the current driver's T/S values."""
    lines = template_path.read_text(encoding="latin-1").splitlines()
    driver_at, _template_driver = afw._find_driver_block(lines)
    ts = _lfp_driver_ts(lfp)
    ascii_name = str(lfp.get("driver_preset_name") or "Custom driver").replace("Ω", "Ohm")
    lines[driver_at] = title or f"Load Forge - {ascii_name}"
    _write_crw_curve(lines, driver_at, lfp)
    params_at = driver_at + 1 + 201 * 5
    values = (
        ts["re_ohm"], ts["fs_hz"], ts["qms"], ts["qes"], ts["vas_m3"],
        ts["le_h"], ts["le_exponent"], ts["le_phase_factor"], ts["xmax_m"],
        ts["pe_w"], ts["sd_m2"],
    )
    for offset, value in enumerate(values):
        lines[params_at + offset] = f" {value:.8g}"
    return "\r\n".join(lines[driver_at:params_at + len(values)]) + "\r\n"


def generate(lfp_path: Path, template_path: Path, output_path: Path, title: str | None) -> None:
    lfp = json.loads(lfp_path.read_text(encoding="utf-8"))
    text = generate_afw_text(lfp, template_path, title)
    output_path.write_text(text, encoding="latin-1")
    line_count = text.count("\r\n")
    print(f"wrote {output_path} ({line_count} lines) from {template_path.name}")
    print(
        f"driver: {lfp.get('driver_preset_name') or 'Custom driver'} | "
        f"Vh={float(lfp['box_vh_l']):.2f} L @ {float(lfp['box_fh_hz']):.1f} Hz | "
        f"Vl={float(lfp['box_vl_l']):.2f} L @ {float(lfp['box_fl_hz']):.1f} Hz"
    )
    print(
        "Port diameter/length are now written from this project's own "
        "box_port_d_h_cm/box_port_d_l_cm and engine.port_length_cm(); "
        "single-port (Condotti=1) per chamber, matching Load Forge's own "
        "DCCAV port model."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lfp", type=Path, help="Load Forge .lfp design file (DCCAV)")
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--title", default=None, help="Override the embedded project title line")
    args = parser.parse_args()
    generate(args.lfp, args.template, args.output, args.title)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
