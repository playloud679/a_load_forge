"""
Horn Generator — pure 2-D profile math  +  shared 3-D mesh engine.

Profiles (return z_array, r_array only):
  tractrix  — z(r) = a·arcosh(a/r) − √(a²−r²);  stops at 90°
  lecleach  — isophase expansion with native roll-back to 180°
  iwata     — axisymmetric Iwata area expansion → radius

Mesh engine (profile-agnostic):
  generate_3d_mesh_from_profile(z, r, thickness)
    → calculates normals, offsets by thickness, revolves, caps, exports STL

Usage:
    python -m src.profile_generator --throat 10 --mouth 50 --output h.stl
    python -m src.profile_generator --throat 10 --fc 800  --output h.stl
    python -m src.profile_generator --throat 20 --mouth 100 --length 80 \
        --profile iwata --output h.stl
"""

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
from stl import mesh

_src = str(Path(__file__).resolve().parent)
if _src not in sys.path:
    sys.path.insert(0, _src)

from _constants import SOUND_SPEED
import _utils

logger = logging.getLogger(__name__)


# ======================================================================
#  CLI
# ======================================================================

def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Horn .stl generator")
    p.add_argument("--throat", type=float, required=True)
    p.add_argument("--mouth", type=float, default=None,
                   help="Mouth diameter (tractrix only)")
    p.add_argument("--fc", type=float, default=None,
                   help="Cutoff frequency in Hz (lecleach / iwata)")
    p.add_argument("--length", type=float, default=None,
                   help="Axial length in mm (iwata)")
    p.add_argument("--profile", choices=["auto", "tractrix", "lecleach", "iwata"],
                   default="auto")
    p.add_argument("--thickness", type=float, default=4.0)
    p.add_argument("--segments", type=int, default=300)
    p.add_argument("--rings", type=int, default=64)
    p.add_argument("--output", type=str, required=True)
    return p.parse_args(args)


# ======================================================================
#  2-D profile mathematics  —  return (z_array, r_array) only
# ======================================================================

# ---- Tractrix (FROZEN — do not modify) --------------------------------

def get_tractrix(throat: float, mouth: float, n: int
                 ) -> tuple[np.ndarray, np.ndarray]:
    """
    Pure tractrix curve  (Z, R) from throat (z=0) to mouth.

        z(r) = a·arcosh(a/r) − √(a²−r²)

    The curve stops exactly when the tangent is horizontal (90° from Z-axis).
    """
    rt = throat / 2.0
    a  = mouth / 2.0
    r  = np.linspace(rt, a, n)
    raw = a * np.arccosh(a / np.maximum(r, 1e-12)) - np.sqrt(
        np.maximum(a * a - r * r, 0.0)
    )
    z = raw[0] - raw
    return z, r


# ---- Le Cléac'h --------------------------------------------------------

from scipy.integrate import solve_ivp


def get_lecleach(throat: float, fc: float, n: int
                 ) -> tuple[np.ndarray, np.ndarray]:
    """
    Le Cléac'h profile via exact isophase wavefront ODE integration (solve_ivp).

    ODE system:
        d/ds (r, z) = (sin(α), cos(α))
        cos(α) = 2πr² / (S_t · exp(m·s)) − 1

    Terminates when the roll-back reaches the target 160° angle.
    """
    rt = throat / 2.0
    m = 4.0 * np.pi * fc / SOUND_SPEED
    S_t = np.pi * rt ** 2
    target_cos = np.cos(np.radians(160))

    def _ode(s, y):
        r, z = y
        S = S_t * np.exp(m * s)
        ca = (2.0 * np.pi * r**2) / S - 1.0
        ca = max(-1.0, min(1.0, ca))
        sa = np.sqrt(1.0 - ca**2)
        return [sa, ca]

    def _event(s, y):
        r, z = y
        S = S_t * np.exp(m * s)
        ca = (2.0 * np.pi * r**2) / S - 1.0
        ca = max(-1.0, min(1.0, ca))
        return ca - target_cos  # zero crossing when ca == target_cos
    _event.terminal = True
    _event.direction = -1  # trigger when ca DECREASES through target

    # s_max: arc-length estimate based on exponential expansion
    # 20 doublings of area → s_max = 20 * ln(2) / m
    s_max = 20.0 * np.log(2.0) / max(m, 1e-9)
    sol = solve_ivp(_ode, (0, min(s_max, 5000.0)), [rt, 0.0],
                    method='RK45', events=_event, max_step=0.5,
                    rtol=1e-9, atol=1e-9)

    s_arr = sol.t
    r_arr, z_arr = sol.y

    # Resample to exactly n points
    if len(s_arr) > 1:
        s_new = np.linspace(0, s_arr[-1], n)
        r = np.interp(s_new, s_arr, r_arr)
        z = np.interp(s_new, s_arr, z_arr)
    else:
        r = np.full(n, rt)
        z = np.zeros(n)

    return z, r


# ---- Iwata (axisymmetric) -----------------------------------------------

def get_iwata(throat: float, fc: float, length: float, n: int
              ) -> tuple[np.ndarray, np.ndarray]:
    """
    Axisymmetric Iwata (Salmon / Hyperbolic-Exponential) horn.

        S(x) = S_t · (cosh(x/x₀) + T · sinh(x/x₀))²
        R(x) = √(S(x)/π)

    Constants:
        T  = 0.707  (Iwata flare parameter)
        x₀ = c / (2π·fc)   (reference scaling length from cutoff Fc)

    The mouth radius at x = length is determined by fc and T.
    Returns (z, r) — same interface as get_tractrix.
    """
    rt = throat / 2.0
    T  = 0.707
    x0 = SOUND_SPEED / (2.0 * np.pi * fc)

    x = np.linspace(0, length, n)
    ch = np.cosh(x / x0)
    sh = np.sinh(x / x0)
    s = np.pi * rt * rt * (ch + T * sh) ** 2
    r = np.sqrt(s / np.pi)
    return x, r


# ======================================================================
#  3-D mesh engine  —  universal, profile-agnostic
# ======================================================================

def generate_3d_mesh_from_profile(
    z_i: np.ndarray,
    r_i: np.ndarray,
    thickness: float = 4.0,
    rings: int = 64,
    output_path: str | None = None,
) -> mesh.Mesh:
    """
    Take ANY valid 2-D profile (z_i, r_i) and produce a watertight STL
    with uniform *thickness* wall applied along the mathematical normal.

    Steps:
      1. Compute unit normals via finite-difference gradient.
      2. Offset inner profile by *thickness* along normal → outer profile.
      3. Revolve both profiles about Z; cap top and bottom annuli.
      4. Shift so the lowest vertex sits at Z = 0.
      5. Save to *output_path* and return the Mesh.
    """
    n_pts = len(z_i)

    # ---- 1. Normals -------------------------------------------------------
    nml = _utils.compute_profile_normals(z_i, r_i)

    # ---- 2. Outer profile -------------------------------------------------
    z_o = z_i + nml[:, 0] * thickness
    r_o = r_i + nml[:, 1] * thickness
    z_o -= z_o[0]                     # flat bottom: outer throat = inner throat = 0
    theta = np.linspace(0, 2 * np.pi, rings, endpoint=False)
    ct, st = np.cos(theta), np.sin(theta)

    V_o = np.zeros((n_pts, rings, 3))
    V_o[:, :, 0] = r_o[:, np.newaxis] * ct[np.newaxis, :]
    V_o[:, :, 1] = r_o[:, np.newaxis] * st[np.newaxis, :]
    V_o[:, :, 2] = z_o[:, np.newaxis]

    V_i = np.zeros((n_pts, rings, 3))
    V_i[:, :, 0] = r_i[:, np.newaxis] * ct[np.newaxis, :]
    V_i[:, :, 1] = r_i[:, np.newaxis] * st[np.newaxis, :]
    V_i[:, :, 2] = z_i[:, np.newaxis]

    I = np.arange(n_pts - 1)[:, np.newaxis]
    J = np.arange(rings)[np.newaxis, :]
    JJ = (J + 1) % rings

    # Outer wall
    a_o = V_o[I, J]
    b_o = V_o[I + 1, J]
    c_o = V_o[I + 1, JJ]
    d_o = V_o[I, JJ]

    tri_o_1 = np.stack([a_o, d_o, b_o], axis=-2).reshape(-1, 3, 3)
    tri_o_2 = np.stack([b_o, d_o, c_o], axis=-2).reshape(-1, 3, 3)

    # Inner wall
    a_i = V_i[I, J]
    b_i = V_i[I + 1, J]
    c_i = V_i[I + 1, JJ]
    d_i = V_i[I, JJ]

    tri_i_1 = np.stack([a_i, b_i, d_i], axis=-2).reshape(-1, 3, 3)
    tri_i_2 = np.stack([b_i, c_i, d_i], axis=-2).reshape(-1, 3, 3)

    # Bottom annulus
    a_b = V_i[0, J]
    b_b = V_o[0, J]
    c_b = V_o[0, JJ]
    d_b = V_i[0, JJ]

    tri_b_1 = np.stack([a_b, d_b, c_b], axis=-2).reshape(-1, 3, 3)
    tri_b_2 = np.stack([a_b, c_b, b_b], axis=-2).reshape(-1, 3, 3)

    # Top annulus
    a_t = V_i[-1, J]
    b_t = V_o[-1, J]
    c_t = V_o[-1, JJ]
    d_t = V_i[-1, JJ]

    tri_t_1 = np.stack([a_t, b_t, c_t], axis=-2).reshape(-1, 3, 3)
    tri_t_2 = np.stack([a_t, c_t, d_t], axis=-2).reshape(-1, 3, 3)

    # Concatenate all triangles
    all_vectors = np.concatenate([
        tri_o_1, tri_o_2,
        tri_i_1, tri_i_2,
        tri_b_1, tri_b_2,
        tri_t_1, tri_t_2
    ], axis=0)

    n_tri = 4 * n_pts * rings
    data = np.zeros(n_tri, dtype=mesh.Mesh.dtype)
    data["vectors"] = all_vectors

    m_obj = mesh.Mesh(data)

    # ---- 4. Fix inverted normals (negative volume) ------------------------
    _utils.ensure_positive_volume(m_obj)

    # ---- 5. Save ----------------------------------------------------------
    if output_path:
        m_obj.save(output_path)
        logger.info("Exported: %s  (%d triangles)", output_path, n_tri)

    return m_obj


# ======================================================================
#  Dispatch
# ======================================================================

def resolve_profile(args: argparse.Namespace) -> str:
    if args.profile != "auto":
        return args.profile
    if args.length is not None and args.fc is not None:
        return "iwata"
    if args.fc is not None:
        return "lecleach"
    if args.mouth is not None:
        return "tractrix"
    raise ValueError("Specify --mouth, --fc, or --length")


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO)

    try:
        name = resolve_profile(args)

        # --- 2-D profile ---------------------------------------------------
        if name == "tractrix":
            if args.mouth is None:
                raise ValueError("--mouth required for tractrix")
            logger.info("Tractrix: throat=%s  mouth=%s", args.throat, args.mouth)
            z, r = get_tractrix(args.throat, args.mouth, args.segments)
            fc = SOUND_SPEED / (np.pi * args.mouth)
            logger.info("Length: %.1f mm  Fc: %.0f Hz  (tangent horizontal)", z[-1], fc)

        elif name == "lecleach":
            if args.fc is None:
                raise ValueError("--fc required for Le Cléac'h")
            logger.info("Le Cléac'h: throat=%s  Fc=%s Hz", args.throat, args.fc)
            z, r = get_lecleach(args.throat, args.fc, args.segments)
            logger.info("Mouth ø: %.1f mm  Length: %.1f mm  Fc: %.0f Hz  (roll-back 180°)",
                        r.max() * 2, z.max(), args.fc)

        elif name == "iwata":
            if args.fc is None or args.length is None:
                raise ValueError("--fc and --length required for iwata")
            logger.info("Iwata: throat=%s  Fc=%s  length=%s",
                        args.throat, args.fc, args.length)
            z, r = get_iwata(args.throat, args.fc, args.length, args.segments)
            logger.info("Mouth ø: %.1f mm  (Salmon T=0.707, x₀=c/2π·fc=%.0fmm)",
                        r.max() * 2, SOUND_SPEED / (2.0 * np.pi * args.fc))

        else:
            raise ValueError(f"Unknown profile: {name}")

        # --- 3-D mesh (shared engine) --------------------------------------
        generate_3d_mesh_from_profile(
            z, r,
            thickness=args.thickness,
            rings=args.rings,
            output_path=args.output,
        )

    except Exception as exc:
        logger.exception("Generation failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
