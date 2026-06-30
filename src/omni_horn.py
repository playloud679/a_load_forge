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

# Standoff ribs (deflector-only self-centering struts across the channel).
_STANDOFF_OVERLAP = 1.0    # mm the rib root sinks into the deflector body (clean weld)
_STANDOFF_CLEARANCE = 0.2  # mm air gap between the rib tip and the reflector wall
_STANDOFF_T0, _STANDOFF_T1 = 0.35, 0.95  # rib spans this fraction of the meridian


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
#  Standoff ribs (deflector-only)
# ======================================================================

def _sector_wedge(low: np.ndarray, up: np.ndarray,
                  phi_c: float, half_ang: float, a_steps: int):
    """Triangulate one rib: the channel band (low→up) swept over a thin sector.

    `low`/`up` are (K,2) meridian arrays (r, z). The closed band loop is swept
    over [phi_c-half_ang, phi_c+half_ang] (lateral surface) and capped flat at
    both angular ends → a watertight wedge. Returns (verts, faces).
    """
    K = len(low)
    loop = np.vstack([low, up[::-1]])          # (2K, 2) closed meridian loop
    L = len(loop)
    angles = np.linspace(phi_c - half_ang, phi_c + half_ang, a_steps)

    verts = np.empty((a_steps * L, 3), dtype=float)
    for a, th in enumerate(angles):
        ct, st = np.cos(th), np.sin(th)
        verts[a * L:(a + 1) * L, 0] = loop[:, 0] * ct
        verts[a * L:(a + 1) * L, 1] = loop[:, 0] * st
        verts[a * L:(a + 1) * L, 2] = loop[:, 1]

    def vid(a, l):
        return a * L + l

    faces = []
    # Lateral sweep of the closed loop.
    for a in range(a_steps - 1):
        for l in range(L):
            l2 = (l + 1) % L
            faces.append((vid(a, l), vid(a, l2), vid(a + 1, l2)))
            faces.append((vid(a, l), vid(a + 1, l2), vid(a + 1, l)))
    # Flat caps at both angular ends (quad strip between low[k] and up[k]).
    for a in (0, a_steps - 1):
        for k in range(K - 1):
            lo0, lo1 = vid(a, k), vid(a, k + 1)
            up0, up1 = vid(a, 2 * K - 1 - k), vid(a, 2 * K - 2 - k)
            faces.append((lo0, lo1, up1))
            faces.append((lo0, up1, up0))
    return verts, np.asarray(faces, dtype=np.int64)


def _mesh_to_trimesh(m: mesh.Mesh):
    import trimesh
    v = np.asarray(m.vectors, dtype=float).reshape(-1, 3)
    f = np.arange(len(v), dtype=np.int64).reshape(-1, 3)
    return trimesh.Trimesh(vertices=v, faces=f, process=True)


def _trimesh_to_mesh(tm) -> mesh.Mesh:
    tri = np.asarray(tm.triangles, dtype=float)
    data = np.zeros(len(tri), dtype=mesh.Mesh.dtype)
    data["vectors"] = tri
    return mesh.Mesh(data)


def _add_standoffs(deflector: mesh.Mesh, P: dict, thickness: float,
                   count: int, width: float, z_shift: float, rings: int) -> mesh.Mesh:
    """Weld `count` self-centering ribs onto the deflector (deflector-only).

    Each rib sinks `_STANDOFF_OVERLAP` into the deflector body and reaches to
    `_STANDOFF_CLEARANCE` short of the reflector wall, so the printed deflector
    self-centers against the (separately printed) reflector. `z_shift` maps the
    design-frame z onto the already Z-aligned deflector mesh.
    """
    import trimesh

    low_r, low_z = P["low_r"], P["low_z"]
    up_r, up_z = P["up_r"], P["up_z"]
    nrho, nz = P["nrho"], P["nz"]
    n = len(low_r)
    i0 = max(1, int(_STANDOFF_T0 * n))
    i1 = min(n, int(_STANDOFF_T1 * n))
    sl = slice(i0, i1)

    # Rib root sinks into the deflector (−N), tip stops short of the reflector.
    root_r = low_r[sl] - _STANDOFF_OVERLAP * nrho[sl]
    root_z = low_z[sl] - _STANDOFF_OVERLAP * nz[sl] - z_shift
    tip_r = up_r[sl] - _STANDOFF_CLEARANCE * nrho[sl]
    tip_z = up_z[sl] - _STANDOFF_CLEARANCE * nz[sl] - z_shift
    low_band = np.column_stack([root_r, root_z])
    up_band = np.column_stack([tip_r, tip_z])

    r_mid = float(np.mean(P["rho_c"][sl]))
    half_ang = max(np.radians(1.0), (width / 2.0) / max(r_mid, 1e-6))
    a_steps = max(3, int(np.ceil(rings * (2 * half_ang) / (2 * np.pi))) + 1)

    defl_tm = _mesh_to_trimesh(deflector)
    defl_tm.fix_normals()
    parts = [defl_tm]
    for k in range(count):
        phi_c = 2.0 * np.pi * k / count
        v, f = _sector_wedge(low_band, up_band, phi_c, half_ang, a_steps)
        wedge = trimesh.Trimesh(vertices=v, faces=f, process=True)
        # boolean union (manifold engine) needs each input to be a coherent
        # volume — fix winding so the wedge is recognised as solid.
        wedge.fix_normals()
        parts.append(wedge)

    try:
        merged = trimesh.boolean.union(parts)
        if isinstance(merged, list):
            merged = trimesh.util.concatenate(merged)
    except Exception as exc:  # pragma: no cover - engine-dependent
        logger.warning("Standoff boolean union failed (%s); concatenating", exc)
        merged = trimesh.util.concatenate(parts)
    merged.merge_vertices()
    out = _trimesh_to_mesh(merged)
    _utils.ensure_positive_volume(out)
    return out


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
    standoffs: int = 0,
    standoff_width: float = 3.0,
):
    """Generate the central deflector and outer reflector STLs.

    `standoffs` (>0) welds that many thin self-centering ribs onto the
    deflector (deflector-only) so it seats concentrically against the
    separately printed reflector; `standoff_width` is their tangential width.
    """
    P = get_omni_profile(throat_diam, mouth_diam, fc, n, profile,
                         lip_angle_deg, bend_scale)

    low_r, low_z = P["low_r"], P["low_z"]
    up_r, up_z = P["up_r"], P["up_z"]
    nrho, nz = P["nrho"], P["nz"]

    logger.info("Omni horn:  throat=%.0f  mouth=%.0f  fc=%s  profile=%s  standoffs=%d",
                throat_diam, mouth_diam, fc, profile, standoffs)
    logger.info("  Gap throat H=%.2f  mouth H=%.2f  St=%.0f  Sm=%.0f",
                P["h"][0], P["h"][-1], P["St"], P["Sm"])

    # ---- Deflector (solid central body under the inner wall) ----------------
    z_base = float(min(low_z.min(), up_z.min())) - thickness
    r_def = np.concatenate([low_r, [low_r[-1], _EPS, _EPS]])
    z_def = np.concatenate([low_z, [z_base, z_base, low_z[0]]])
    deflector = _revolve_polygon(r_def, z_def, rings)
    if standoffs > 0:
        # _revolve_polygon Z-aligned the mesh by −z_base; map ribs to that frame.
        deflector = _add_standoffs(deflector, P, thickness, standoffs,
                                   standoff_width, z_base, rings)
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
