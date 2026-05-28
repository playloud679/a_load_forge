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
    python -m src.01_profile_generator --throat 10 --mouth 50 --output h.stl
    python -m src.01_profile_generator --throat 10 --fc 800  --output h.stl
    python -m src.01_profile_generator --throat 20 --mouth 100 --length 80 \
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

def get_lecleach(throat: float, fc: float, n: int
                 ) -> tuple[np.ndarray, np.ndarray]:
    """
    Vero profilo Le Cléac'h generato tramite integrazione differenziale esatta
    delle traiettorie ortogonali ai fronti d'onda isofase.
    """
    rt = throat / 2.0
    # Costante di espansione (m) per tromba esponenziale
    m = 4.0 * np.pi * fc / SOUND_SPEED

    S_t = np.pi * rt ** 2

    # Angolo di roll-back target (160 gradi). Spinge il bordo indietro e all'infuori.
    target_cos_alpha = np.cos(np.radians(160))

    # Risoluzione dell'integrazione di Eulero (0.1 mm garantisce stabilità e precisione)
    ds = 0.1
    r_val = float(rt)
    z_val = 0.0
    s = 0.0

    r_list = [r_val]
    z_list = [z_val]
    s_list = [s]

    for _ in range(30000):  # Limite di sicurezza per evitare loop infiniti
        s += ds
        S_current = S_t * np.exp(m * s)

        # Calcolo dell'angolo del fronte d'onda
        cos_alpha = (2.0 * np.pi * r_val ** 2) / S_current - 1.0

        # Difesa contro errori di precisione floating-point ai limiti del dominio
        cos_alpha = max(-1.0, min(1.0, cos_alpha))
        sin_alpha = np.sqrt(1.0 - cos_alpha ** 2)

        # ODE: La parete cresce ortogonalmente al fronte d'onda
        r_val += sin_alpha * ds
        z_val += cos_alpha * ds

        r_list.append(r_val)
        z_list.append(z_val)
        s_list.append(s)

        # Termina quando il roll-back raggiunge l'angolo desiderato
        if cos_alpha <= target_cos_alpha:
            break

    # Ricampionamento lineare per garantire esattamente 'n' punti per il mesh engine
    s_arr = np.array(s_list)
    s_new = np.linspace(0, s, n)
    r = np.interp(s_new, s_arr, r_list)
    z = np.interp(s_new, s_arr, z_list)

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

    n_tri = 4 * n_pts * rings
    data = np.zeros(n_tri, dtype=mesh.Mesh.dtype)
    tri = 0

    def emit(a, b, c):
        nonlocal tri
        data["vectors"][tri] = [a, b, c]
        tri += 1

    # Outer wall
    for i in range(n_pts - 1):
        z0, z1 = z_o[i], z_o[i + 1]
        r0, r1 = r_o[i], r_o[i + 1]
        for j in range(rings):
            jj = (j + 1) % rings
            a = [r0 * ct[j],  r0 * st[j],  z0]
            b = [r1 * ct[j],  r1 * st[j],  z1]
            c = [r1 * ct[jj], r1 * st[jj], z1]
            d = [r0 * ct[jj], r0 * st[jj], z0]
            emit(a, d, b)
            emit(b, d, c)

    # Inner wall
    for i in range(n_pts - 1):
        z0, z1 = z_i[i], z_i[i + 1]
        r0, r1 = r_i[i], r_i[i + 1]
        for j in range(rings):
            jj = (j + 1) % rings
            a = [r0 * ct[j],  r0 * st[j],  z0]
            b = [r1 * ct[j],  r1 * st[j],  z1]
            c = [r1 * ct[jj], r1 * st[jj], z1]
            d = [r0 * ct[jj], r0 * st[jj], z0]
            emit(a, b, d)
            emit(b, c, d)

    # Bottom annulus
    for j in range(rings):
        jj = (j + 1) % rings
        a = [r_i[0] * ct[j],  r_i[0] * st[j],  z_i[0]]
        b = [r_o[0] * ct[j],  r_o[0] * st[j],  z_o[0]]
        c = [r_o[0] * ct[jj], r_o[0] * st[jj], z_o[0]]
        d = [r_i[0] * ct[jj], r_i[0] * st[jj], z_i[0]]
        emit(a, d, c)
        emit(a, c, b)

    # Top annulus
    for j in range(rings):
        jj = (j + 1) % rings
        a = [r_i[-1] * ct[j],  r_i[-1] * st[j],  z_i[-1]]
        b = [r_o[-1] * ct[j],  r_o[-1] * st[j],  z_o[-1]]
        c = [r_o[-1] * ct[jj], r_o[-1] * st[jj], z_o[-1]]
        d = [r_i[-1] * ct[jj], r_i[-1] * st[jj], z_i[-1]]
        emit(a, b, c)
        emit(a, c, d)

    assert tri == n_tri

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

_PROFILES = {
    "tractrix": get_tractrix,
    "lecleach": get_lecleach,
    "iwata":    get_iwata,
}


def resolve_profile(args: argparse.Namespace) -> str:
    if args.profile != "auto":
        return args.profile
    if args.profile == "iwata" or (args.length is not None and args.fc is not None):
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
