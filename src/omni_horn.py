"""
Omnidirectional Compression-Driver Horn (curved axial → 360° radial expansion).

A compression driver fires *axially* into the throat at the apex; a curved
central **deflector** turns the wavefront 90° and the curved outer **reflector**
opens it to a full 360° radial mouth.  Unlike `radial_horn.py` (which uses a
crude linear deflector ramp `z = (R-Rt)·0.3`), the channel here follows a true
*curved meridian*: the flow angle eases smoothly from 90° (axial) at the throat
to `lip_angle` at the mouth, so the wall sweeps like the trumpet-bell in the
reference photo.

Geometry (the clean part):
    The channel centerline starts at radius ρ₀ = Rt/2.  With area law S(Rt)=St,
    the throat gap is h₀ = St/(2π·ρ₀) = Rt, so the *inner* wall starts at ρ=0
    (deflector nose on the axis) and the *outer* wall at ρ=Rt (the circular
    driver throat).  Throat area = π·Rt² exactly — no fudge factor.

Acoustic law (gap follows the chosen expansion profile):
    S(s) along the centerline arc length s; gap H = S / (2π·ρ_centerline)
    measured *perpendicular* to the local flow (not vertically).

Output:  omni_deflector.stl  — solid central body (nose on axis)
         omni_reflector.stl  — outer shell with central throat hole (Ø = throat)
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

_EPS = 1e-3  # avoids degenerate triangles on the Z axis


# ======================================================================
#  Profile math
# ======================================================================

def _cumtrapz0(y: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Cumulative trapezoid integral with a leading 0 (no scipy dependency)."""
    out = np.zeros_like(y, dtype=float)
    out[1:] = np.cumsum(0.5 * (y[1:] + y[:-1]) * np.diff(x))
    return out


def get_omni_profile(
    throat_diam: float,
    mouth_diam: float,
    fc: float | None = None,
    n: int = 300,
    profile: str = "Exponential",
    lip_angle_deg: float = 0.0,
    bend_scale: float = 1.0,
) -> dict:
    """
    Build the curved omni channel: centerline, gap, and the two channel walls.

    The centerline bends from axial (90° from horizontal) at the throat to
    `lip_angle_deg` at the mouth via a cosine-eased flow angle, then the
    cross-sectional area `S` is laid out along the resulting arc length using
    the chosen expansion profile.

    Returns a dict of parallel 1-D arrays (all length `n`):
        rho_c, z_c   — centerline (meridian radius, axial)
        h            — channel gap (perpendicular to flow)
        nrho, nz     — unit meridian normal (gap direction)
        low_r, low_z — inner / deflector-side wall  (M − h/2·N)
        up_r,  up_z  — outer / reflector-side wall   (M + h/2·N)
        St, Sm       — throat and mouth cross-sectional area
    """
    Rt = throat_diam / 2.0
    Rm = mouth_diam / 2.0
    St = np.pi * Rt ** 2

    t = np.linspace(0.0, 1.0, n)
    lip = np.radians(lip_angle_deg)

    # Flow angle from horizontal: 90° (axial) → lip, smooth (zero slope at ends).
    theta = lip + (np.pi / 2.0 - lip) * 0.5 * (1.0 + np.cos(np.pi * t))

    # Integrate unit tangents to get the centerline shape, then scale so the
    # meridian radius spans [Rt/2, Rm].  z descends from 0 (mouth below throat).
    cos_th, sin_th = np.cos(theta), np.sin(theta)
    rho_u = _cumtrapz0(cos_th, t)
    z_u = _cumtrapz0(sin_th, t)

    rho_start = Rt / 2.0
    span = rho_u[-1] if rho_u[-1] > 1e-9 else 1.0
    L = (Rm - rho_start) / span
    rho_c = rho_start + L * rho_u
    z_c = -bend_scale * L * z_u

    # True arc length of the (scaled) centerline.
    ds = np.hypot(np.diff(rho_c), np.diff(z_c))
    s = np.concatenate([[0.0], np.cumsum(ds)])

    # ---- area law S(s) -------------------------------------------------------
    if profile == "Exponential":
        m = 4.0 * np.pi * (fc or 1000.0) / SOUND_SPEED
        S = St * np.exp(m * s)
    else:
        from profile_generator import (
            get_tractrix, get_salmon, get_oblate_spheroidal_for_mouth,
        )
        if profile == "Tractrix":
            z_p, r_p = get_tractrix(throat_diam, mouth_diam, n)
        elif profile == "Salmon":
            z_p, r_p = get_salmon(throat_diam, fc or 1000.0, float(Rm - Rt), n)
        elif profile == "Oblate spheroidal":
            z_p, r_p = get_oblate_spheroidal_for_mouth(throat_diam, mouth_diam, 90.0, n)
        else:
            raise ValueError(f"Unknown profile: {profile}")
        S_prof = np.pi * r_p ** 2
        sn = s / s[-1] if s[-1] > 1e-9 else s
        tp = np.linspace(0.0, 1.0, len(z_p))
        S = np.interp(sn, tp, S_prof)
        S = np.maximum(S, St)  # monotone: never narrower than throat

    h = S / (2.0 * np.pi * rho_c)

    # ---- meridian normal (gap direction) ------------------------------------
    t_rho = np.gradient(rho_c)
    t_z = np.gradient(z_c)
    tn = np.hypot(t_rho, t_z)
    tn[tn < 1e-12] = 1.0
    t_rho /= tn
    t_z /= tn
    # Rotate tangent so N points to +ρ at the throat (axial flow → radial gap).
    nrho = -t_z
    nz = t_rho

    low_r = np.maximum(rho_c - 0.5 * h * nrho, _EPS)
    low_z = z_c - 0.5 * h * nz
    up_r = rho_c + 0.5 * h * nrho
    up_z = z_c + 0.5 * h * nz

    return {
        "rho_c": rho_c, "z_c": z_c, "h": h, "nrho": nrho, "nz": nz,
        "low_r": low_r, "low_z": low_z, "up_r": up_r, "up_z": up_z,
        "St": float(St), "Sm": float(S[-1]),
    }


# ======================================================================
#  Solid-of-revolution helper (own engine — closed meridian, no center caps)
# ======================================================================

def _revolve_polygon(r_poly: np.ndarray, z_poly: np.ndarray, rings: int = 64) -> mesh.Mesh:
    """Revolve a CLOSED 2-D meridian polygon (r, z) around the Z axis."""
    n_pts = len(r_poly)
    theta = np.linspace(0.0, 2.0 * np.pi, rings, endpoint=False)
    ct, st = np.cos(theta), np.sin(theta)

    n_tri = 2 * rings * (n_pts - 1)
    data = np.zeros(n_tri, dtype=mesh.Mesh.dtype)
    tri = 0
    for i in range(n_pts - 1):
        r0, r1 = r_poly[i], r_poly[i + 1]
        z0, z1 = z_poly[i], z_poly[i + 1]
        for j in range(rings):
            jj = (j + 1) % rings
            a = [r0 * ct[j], r0 * st[j], z0]
            b = [r1 * ct[j], r1 * st[j], z1]
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

def generate_omni_horn(
    throat_diam: float = 25.0,
    mouth_diam: float = 200.0,
    fc: float | None = None,
    rings: int = 64,
    output_dir: str = "io",
    profile: str = "Exponential",
    lip_angle_deg: float = 0.0,
    bend_scale: float = 1.0,
    thickness: float = 4.0,
    n: int = 300,
):
    """Generate the central deflector and outer reflector STLs."""
    P = get_omni_profile(throat_diam, mouth_diam, fc, n, profile,
                         lip_angle_deg, bend_scale)

    low_r, low_z = P["low_r"], P["low_z"]
    up_r, up_z = P["up_r"], P["up_z"]
    nrho, nz = P["nrho"], P["nz"]

    logger.info("Omni horn:  throat=%.0f  mouth=%.0f  fc=%s  profile=%s",
                throat_diam, mouth_diam, fc, profile)
    logger.info("  Gap throat H=%.2f  mouth H=%.2f  St=%.0f  Sm=%.0f",
                P["h"][0], P["h"][-1], P["St"], P["Sm"])

    # ---- Deflector (solid central body under the inner wall) ----------------
    z_base = float(min(low_z.min(), up_z.min())) - thickness
    r_def = np.concatenate([low_r, [low_r[-1], _EPS, _EPS]])
    z_def = np.concatenate([low_z, [z_base, z_base, low_z[0]]])
    deflector = _revolve_polygon(r_def, z_def, rings)
    deflector.save(f"{output_dir}/omni_deflector.stl")
    logger.info("  Deflector:  closed=%s  Z=[%.0f,%.0f]  tris=%d",
                _wt(deflector), deflector.vectors[:, :, 2].min(),
                deflector.vectors[:, :, 2].max(), len(deflector.vectors))

    # ---- Reflector (outer shell of constant thickness, central throat hole) -
    out_r = up_r + thickness * nrho
    out_z = up_z + thickness * nz
    # Close the band: forward inner wall, reversed outer wall, back to start.
    r_ref = np.concatenate([up_r, out_r[::-1], [up_r[0]]])
    z_ref = np.concatenate([up_z, out_z[::-1], [up_z[0]]])
    reflector = _revolve_polygon(r_ref, z_ref, rings)
    reflector.save(f"{output_dir}/omni_reflector.stl")
    logger.info("  Reflector:  closed=%s  Z=[%.0f,%.0f]  tris=%d",
                _wt(reflector), reflector.vectors[:, :, 2].min(),
                reflector.vectors[:, :, 2].max(), len(reflector.vectors))

    return deflector, reflector


def _wt(m):
    try:
        return str(m.is_closed(exact=True))
    except Exception:
        return "?"


# ======================================================================
#  Standalone
# ======================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    generate_omni_horn(throat_diam=25, mouth_diam=200, fc=600, lip_angle_deg=-10)
