"""
360° Radial Horn (Omnidirectional Reflector).

Two interlocking solid revolutions:
  • Bottom Deflector — curved top, flat bottom, central throat hole
  • Top Reflector    — curved bottom (gap = H(R)), flat top

Acoustic law:   S(R) = S_t · exp(m · (R − R_t))
                S(R) = 2πR · H(R)    →    H(R) = S(R) / (2πR)

Output:  radial_bottom.stl  — flat base at Z=0, throat hole
         radial_top.stl     — exported upside‑down (flat side at Z=0)
"""

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
#  Radial profile math
# ======================================================================

def get_radial_profiles(
    throat_diam: float,
    mouth_diam: float,
    fc: float | None = None,
    n: int = 300,
    profile: str = "Exponential",
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Compute the 1-D radial functions for any expansion profile.

    The area law S(R) is derived from the chosen profile by normalising its
    axial coordinate to span [Rt, Rm]:

        Exponential — S(R) = St · exp(m·(R−Rt)),  m = 4π·fc/c
        Tractrix    — area re-parameterised from get_tractrix(throat, mouth)
        Salmon      — area re-parameterised from get_salmon with length=Rm−Rt

    H(R) = S(R) / (2πR),  Z_bottom = (R−Rt)·0.3,  Z_top = Z_bottom + H

    Returns (R, Z_bottom, Z_top) arrays.
    """
    Rt = throat_diam / 2.0
    Rm = mouth_diam / 2.0
    St = np.pi * Rt ** 2
    R = np.linspace(Rt, Rm, n)

    if profile == "Exponential":
        m = 4.0 * np.pi * (fc or 1000.0) / SOUND_SPEED
        S = St * np.exp(m * (R - Rt))
    else:
        from profile_generator import get_tractrix, get_salmon
        if profile == "Tractrix":
            z_p, r_p = get_tractrix(throat_diam, mouth_diam, n)
        elif profile == "Salmon":
            z_p, r_p = get_salmon(throat_diam, fc or 1000.0, float(Rm - Rt), n)
        else:
            raise ValueError(f"Unknown profile: {profile}")

        # Re-parameterise: stretch the profile's z-axis to fill [Rt, Rm]
        S_prof = np.pi * r_p ** 2
        t = np.linspace(0, 1, len(z_p))
        S = np.interp(np.linspace(0, 1, n), t, S_prof)
        S = np.maximum(S, St)  # monotone: never narrower than throat

    H = S / (2.0 * np.pi * R)
    Z_bottom = (R - Rt) * 0.3
    Z_top = Z_bottom + H
    return R, Z_bottom, Z_top


# ======================================================================
#  Solid‑of‑revolution helper
# ======================================================================

def _revolve_polygon(
    r_poly: np.ndarray,
    z_poly: np.ndarray,
    rings: int = 64,
) -> mesh.Mesh:
    """
    Revolve a CLOSED 2‑D polygon (r, z) around the Z axis.
    NO center caps.  NO gradient normal computation.
    """
    n_pts = len(r_poly)
    theta = np.linspace(0, 2 * np.pi, rings, endpoint=False)
    ct, st = np.cos(theta), np.sin(theta)

    n_tri = 2 * rings * (n_pts - 1)
    data = np.zeros(n_tri, dtype=mesh.Mesh.dtype)
    tri = 0

    for i in range(n_pts - 1):
        r0, r1 = r_poly[i], r_poly[i + 1]
        z0, z1 = z_poly[i], z_poly[i + 1]
        for j in range(rings):
            jj = (j + 1) % rings
            a = [r0 * ct[j],  r0 * st[j],  z0]
            b = [r1 * ct[j],  r1 * st[j],  z1]
            c = [r1 * ct[jj], r1 * st[jj], z1]
            d = [r0 * ct[jj], r0 * st[jj], z0]
            data["vectors"][tri] = [a, d, b]; tri += 1
            data["vectors"][tri] = [b, d, c]; tri += 1

    assert tri == n_tri

    m_obj = mesh.Mesh(data)

    _utils.align_z_to_zero(m_obj)
    _utils.ensure_positive_volume(m_obj)

    return m_obj


# ======================================================================
#  Public API
# ======================================================================

def generate_radial_horn(
    throat_diam: float = 25.0,
    mouth_diam:  float = 200.0,
    fc:          float | None = None,
    rings:       int   = 64,
    output_dir:  str   = "io",
    profile:     str   = "Exponential",
):
    """Generate both bottom deflector and top reflector STLs."""

    R, Zb, Zt = get_radial_profiles(throat_diam, mouth_diam, fc, 300, profile)

    logger.info("Radial horn:  throat=%.0f  mouth=%.0f  fc=%.0f",
                throat_diam, mouth_diam, fc)
    logger.info("  Gap at throat H(Rt)=%.2f  at mouth H(Rm)=%.2f",
                Zt[0] - Zb[0], Zt[-1] - Zb[-1])

    # ---- Bottom deflector ------------------------------------------------
    # Closed loop: Inner vertical → Top curve → Outer vertical → Bottom flat
    Rt, Rm = R[0], R[-1]
    r_bot = np.concatenate([[Rt], R, [Rm], [Rt]])
    z_bot = np.concatenate([[0.0], Zb, [0.0], [0.0]])

    bottom_mesh = _revolve_polygon(r_bot, z_bot, rings)
    bottom_mesh.save(f"{output_dir}/radial_bottom.stl")
    logger.info("  Bottom:  WT=%s  Z=[%.0f,%.0f]  tris=%d",
                _wt(bottom_mesh),
                bottom_mesh.vectors[:,:,2].min(),
                bottom_mesh.vectors[:,:,2].max(),
                len(bottom_mesh.vectors))

    # ---- Top reflector ---------------------------------------------------
    # Closed loop: Bottom curve → Outer vertical → Top flat → Inner vertical
    wall_T = 4.0
    Z_flat = Zt[-1] + wall_T

    eps = 0.01  # avoids degenerate triangles at r=0 while closing the center
    r_top = np.concatenate([[eps], R, [Rm, eps, eps]])
    z_top = np.concatenate([[Zt[0]], Zt, [Z_flat, Z_flat, Zt[0]]])

    top_mesh = _revolve_polygon(r_top, z_top, rings)

    # Flip upside-down for supportless printing
    zf = top_mesh.vectors[:, :, 2].copy()
    top_mesh.vectors[:, :, 2] = zf.max() - zf
    top_mesh.vectors = top_mesh.vectors[:, [0, 2, 1]]

    top_mesh.save(f"{output_dir}/radial_top.stl")
    logger.info("  Top:     WT=%s  Z=[%.0f,%.0f]  tris=%d",
                _wt(top_mesh),
                top_mesh.vectors[:,:,2].min(),
                top_mesh.vectors[:,:,2].max(),
                len(top_mesh.vectors))

    return bottom_mesh, top_mesh


def _wt(m):
    try:
        return str(m.get_mass_properties()[0] > 0)
    except Exception:
        return "?"


# ======================================================================
#  Standalone
# ======================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    generate_radial_horn(throat_diam=25, mouth_diam=200, fc=600)
