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

- ``driver_at - 490``: AFW load code (``6`` for DCAAV/DCCAV)
- ``driver_at - 230`` .. ``+25``: the 26-value chamber/tuning block, shared
  byte-for-byte with BP4/BP6 (only the circuit topology differs):
  ``[Vh_m3, Fh_hz, virtual_volume_factor, q_abs_h, q_leak_h,
    Vl_m3, Fl_hz, virtual_volume_factor, q_abs_l, q_leak_l,
    1, 1, <port geometry, unmapped>, ..., q_port_h(@14), ...,
    q_port_l(@25), <port geometry, unmapped>]``
  Fields at offsets 10-13 and 15-24 look like derived port geometry (AFW's
  own computed diameter/length/area terms) whose exact semantics are not
  reverse-engineered here — they are copied verbatim from the template and
  will not match this project's actual port dimensions. Only the fields
  Load Forge's own T/S/box model unambiguously determines are overwritten.
- ``driver_at``: CRW curve title line
- ``driver_at + 1`` .. ``+ 1005``: 201 points x 5 values, copied verbatim
  from the template (not recomputed) — same "ideal projection, not a real
  curve" caveat the original 9 examples' README already states.
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import compare_afw_sealed as afw  # noqa: E402

DEFAULT_TEMPLATE = ROOT / "examples" / "afw_bass_match_9" / "09_fostex_fe126_dcaav.afw"


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


def generate_afw_text(lfp: dict, template_path: Path = DEFAULT_TEMPLATE, title: str | None = None) -> str:
    """Build the AFW project text in memory (no filesystem output side effect)."""
    if lfp.get("load_type") != "DCCAV":
        raise ValueError(f"load_type={lfp.get('load_type')!r}, expected DCCAV")

    lines = template_path.read_text(encoding="latin-1").splitlines()
    driver_at, _template_driver = afw._find_driver_block(lines)

    code_at = driver_at - 490
    if int(afw._number(lines[code_at])) != 6:
        raise ValueError(f"{template_path} is not an AFW load-code-6 (DCAAV) template")

    block_at = driver_at - 230
    box = {
        0: float(lfp["box_vh_l"]) / 1000.0,
        1: float(lfp["box_fh_hz"]),
        3: float(lfp.get("loss_q_abs_h", 15.0)),
        4: float(lfp.get("loss_q_leak_h", 1000.0)),
        5: float(lfp["box_vl_l"]) / 1000.0,
        6: float(lfp["box_fl_hz"]),
        8: float(lfp.get("loss_q_abs_l", 15.0)),
        9: float(lfp.get("loss_q_leak_l", 1000.0)),
        14: float(lfp.get("loss_q_port_h", 15.0)),
        25: float(lfp.get("loss_q_port_l", 15.0)),
    }
    for offset, value in box.items():
        lines[block_at + offset] = f" {value:.8g}"

    driver_name = str(lfp.get("driver_preset_name") or "Custom driver")
    # AFW project text is Latin-1 (ISO-8859-1); the omega ohm sign and other
    # characters outside that codepage can't round-trip, so ASCII-fold them.
    ascii_name = driver_name.replace("Ω", "Ohm").encode("latin-1", "replace").decode("latin-1")
    lines[driver_at] = title or f"Load Forge Bass Match - DCCAV - {ascii_name}"

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
        "Port geometry fields (offsets 10-13, 15-24 of the chamber block) are "
        "copied from the template unchanged and do NOT reflect this project's "
        "actual port dimensions -- re-tune ports manually inside AFW if that "
        "detail matters for your comparison."
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
