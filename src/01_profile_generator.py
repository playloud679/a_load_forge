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

import numpy as np
from stl import mesh

logger = logging.getLogger(__name__)
SOUND_SPEED = 343_000           # mm / s


# ======================================================================
#  CLI
# ======================================================================

def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Horn .stl generator")
    p.add_argument("--throat", type=float, required=True)
    p.add_argument("--mouth", type=float, default=None)
    p.add_argument("--fc", type=float, default=None,
                   help="Cutoff frequency in Hz (lecleach mode)")
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
    Le Cléac'h profile — terminates at 90° (θ = π/2) like tractrix.

    Parametric equations on tangent angle θ ∈ [0, π/2]:

        r(θ) = rt / √(1 − m²·sin²θ)

        z(θ) = rt·√(1−m²)·m² · ∫ sin²θ / (1−m²·sin²θ)^(3/2) dθ

    The mouth diameter and length are determined by fc and rt:
        rm = rt / √(1 − m²)     where  m = 2π·fc·rt / c
    """
    rt = throat / 2.0

    m = 2.0 * np.pi * fc * rt / SOUND_SPEED
    if m >= 1.0:
        raise ValueError(
            f"m={m:.3f} ≥ 1 — no roll-back.  Use smaller throat or lower Fc."
        )

    theta = np.linspace(0, np.pi / 2, n)
    s2 = np.sin(theta) ** 2
    denom = 1.0 - m * m * s2

    r = rt / np.sqrt(denom)

    dz_dθ = rt * np.sqrt(1.0 - m * m) * m * m * s2 / (denom ** 1.5)
    z = np.empty_like(theta)
    z[0] = 0.0
    for i in range(1, n):
        z[i] = z[i - 1] + 0.5 * (dz_dθ[i - 1] + dz_dθ[i]) * (
            theta[i] - theta[i - 1]
        )

    return z, r


# ---- Iwata (axisymmetric) -----------------------------------------------

def get_iwata(throat: float, mouth: float, length: float, n: int
              ) -> tuple[np.ndarray, np.ndarray]:
    """
    Axisymmetric Iwata (Hyperbolic-Exponential / Salmon family) horn.

        S(x) = S_t · (cosh(m·x) + T · sinh(m·x))²
        R(x) = √(S(x)/π)

    T = 0.7 (standard flare parameter).
    The expansion rate m is solved so that R(length) ≈ mouth/2.
    Returns (z, r) — same interface as get_tractrix.
    """
    rt = throat / 2.0
    rm = mouth / 2.0
    T = 0.7

    # Solve for m such that sqrt(S(length)/π) = rm
    # S(L)/S_t = (cosh(m·L) + T·sinh(m·L))² = (rm/rt)²
    # cosh(m·L) + T·sinh(m·L) = rm/rt
    # (e^{mL}+e^{-mL})/2 + T·(e^{mL}-e^{-mL})/2 = rm/rt
    # e^{mL}·(1+T)/2 + e^{-mL}·(1-T)/2 = rm/rt
    # Let u = e^{mL}:
    # u·(1+T)/2 + 1/u·(1-T)/2 = rm/rt
    # u·(1+T) + 1/u·(1-T) = 2·rm/rt
    # u·(1+T) − 2·rm/rt + (1-T)/u = 0
    # Multiply by u:  (1+T)·u² − 2·rm/rt·u + (1-T) = 0

    A = 1.0 + T
    B = -2.0 * rm / rt
    C = 1.0 - T
    disc = B * B - 4.0 * A * C
    if disc < 0:
        raise ValueError("Iwata: throat/mouth/length impossible for T=0.7")
    u = (-B + np.sqrt(disc)) / (2.0 * A)
    if u <= 0:
        u = (-B - np.sqrt(disc)) / (2.0 * A)
    if u <= 0:
        raise ValueError("Iwata: cannot solve expansion rate")

    m = np.log(u) / length

    x = np.linspace(0, length, n)
    ch = np.cosh(m * x)
    sh = np.sinh(m * x)
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
    dz = np.gradient(z_i)
    dr = np.gradient(r_i)
    tan = np.column_stack([dz, dr])
    tn = np.sqrt(tan[:, 0] ** 2 + tan[:, 1] ** 2)

    # Boundary protection: if tangent magnitude collapses (dz≈dr≈0 at profile
    # end-points), extrapolate the normal from the nearest valid neighbour.
    for bound_idx in [0, -1]:
        if tn[bound_idx] < 1e-12:
            neighbour = 1 if bound_idx == 0 else -2
            dz[bound_idx] = dz[neighbour]
            dr[bound_idx] = dr[neighbour]
            tn[bound_idx] = tn[neighbour]
    tn[tn < 1e-15] = 1.0
    tan /= tn.reshape(-1, 1)

    nml = np.column_stack([-tan[:, 1], tan[:, 0]])

    # ---- 2. Outer profile -------------------------------------------------
    z_o = z_i + nml[:, 0] * thickness
    r_o = r_i + nml[:, 1] * thickness

    shift_o = z_o.min()
    if shift_o < 0:
        z_o -= shift_o

    # ---- 3. Revolution (single pass, shared theta) -----------------------
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

    # ---- 4. Z-alignment ---------------------------------------------------
    z_min = m_obj.vectors.reshape(-1, 3)[:, 2].min()
    if abs(z_min) > 1e-4:
        m_obj.vectors[:, :, 2] -= z_min

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
    if args.fc is not None:
        return "lecleach"
    if args.length is not None:
        return "iwata"
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
            if args.mouth is None or args.length is None:
                raise ValueError("--mouth and --length required for iwata")
            logger.info("Iwata: throat=%s  mouth=%s  length=%s",
                        args.throat, args.mouth, args.length)
            z, r = get_iwata(args.throat, args.mouth, args.length, args.segments)
            fc = SOUND_SPEED / (np.pi * r.max() * 2)
            logger.info("Mouth ø: %.1f mm  Fc: %.0f Hz", r.max() * 2, fc)

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
