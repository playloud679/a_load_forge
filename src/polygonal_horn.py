"""
Polygonal horn — regular N-gon cross-section with any expansion profile.

The cross-section at every Z slice is a regular N-gon whose area equals
the area of the equivalent circle derived from the chosen profile:

    A_polygon = A_circle = π · r_eq²
    circumradius  R = r_eq · sqrt(2π / (N · sin(2π/N)))
    outer offset  R_outer = R + t / cos(π/N)    (uniform face-normal thickness)

Input r_eq is the area-equivalent circular radius returned by any profile
function (get_tractrix, get_salmon, or computed for Exponential).

Rounded corners (corner_radius > 0): the section becomes the Minkowski sum
of a regular N-gon core (circumradius Rc) and a disk of radius f, still
area-matched to the equivalent circle:

    A = s2·Rc² + s1·Rc·f + π·f²     s2 = N/2·sin(2π/N), s1 = 2N·sin(π/N)

f is clamped to 0.995·r_eq per station — at f = r_eq the core collapses and
the section degenerates into the equivalent circle, so a small throat rounds
itself into a circle automatically while the mouth stays visibly polygonal.
The wall is a true in-plane parallel offset: same core, fillet f + t·n_r.
"""

import logging
import sys
from pathlib import Path

import numpy as np
from stl import mesh

_src = str(Path(__file__).resolve().parent)
if _src not in sys.path:
    sys.path.insert(0, _src)

import _utils

logger = logging.getLogger(__name__)

# area-equivalent circle radius → N-gon circumradius
def _r_to_circumradius(r_eq: np.ndarray, n: int) -> np.ndarray:
    return r_eq * np.sqrt(2.0 * np.pi / (n * np.sin(2.0 * np.pi / n)))


# ── Rounded-corner (filleted) regular N-gon ──────────────────────────────
#
# Shape model: core regular N-gon (circumradius Rc, vertices at π/2 + k·2π/N)
# Minkowski-summed with a disk of radius f. Faces sit at apothem
# Rc·cos(π/N) + f, corners are arcs of radius f centred on the core vertices,
# max radial extent (across corners) is Rc + f.

def rounded_poly_area(core_R, fillet, n: int):
    """Area of the rounded N-gon (core ⊕ disk)."""
    s2 = 0.5 * n * np.sin(2.0 * np.pi / n)
    s1 = 2.0 * n * np.sin(np.pi / n)
    return s2 * np.asarray(core_R, float) ** 2 \
        + s1 * np.asarray(core_R, float) * np.asarray(fillet, float) \
        + np.pi * np.asarray(fillet, float) ** 2


def rounded_poly_core(r_eq, n: int, fillet: float):
    """Area-matched core circumradius + per-station clamped fillet.

    Solves  s2·Rc² + s1·Rc·f + π·f² = π·r_eq²  for Rc (positive root).
    f is clamped to 0.995·r_eq: at f = r_eq the exact solution is Rc = 0
    (the section IS the equivalent circle); the clamp keeps a sliver of flat
    face so ring topology stays valid. Scalars in → scalars out.
    """
    r = np.asarray(r_eq, dtype=float)
    scalar = r.ndim == 0
    r = np.atleast_1d(r)
    f = np.clip(float(fillet), 0.0, None) * np.ones_like(r)
    f = np.minimum(f, 0.995 * r)
    s2 = 0.5 * n * np.sin(2.0 * np.pi / n)
    s1 = 2.0 * n * np.sin(np.pi / n)
    disc = (s1 * f) ** 2 - 4.0 * s2 * np.pi * (f * f - r * r)
    Rc = (-s1 * f + np.sqrt(disc)) / (2.0 * s2)
    if scalar:
        return float(Rc[0]), float(f[0])
    return Rc, f


def offset_rounded_poly(core_R, fillet, dist, n: int, min_fillet: float = 0.02):
    """In-plane parallel offset of a rounded N-gon by signed *dist*.

    Dilation (or erosion within the fillet) keeps the core and changes the
    fillet to f+dist (Minkowski composition). Erosion beyond the fillet
    shrinks the core along the face normals instead and leaves ~sharp
    corners; *min_fillet* keeps the ring topology valid (constant point
    count across stations).
    """
    Rc = np.asarray(core_R, dtype=float)
    f_new = np.asarray(fillet, dtype=float) + np.asarray(dist, dtype=float)
    core_new = np.where(f_new >= min_fillet, Rc,
                        Rc + (f_new - min_fillet) / np.cos(np.pi / n))
    return np.maximum(core_new, 1e-6), np.maximum(f_new, min_fillet)


def rounded_polygon_ring(core_R: float, fillet: float, n_sides: int,
                         arc_seg: int = 8, phase: float = np.pi / 2.0
                         ) -> np.ndarray:
    """CCW boundary points of the rounded N-gon: n_sides·(arc_seg+1) points.

    Corner k's arc sweeps the vertex's exterior angle [θ_k−π/N, θ_k+π/N];
    consecutive corners' end/start points are the tangent points on the
    shared face, so the straight faces are the implicit connecting segments.
    """
    th_v = phase + 2.0 * np.pi * np.arange(n_sides) / n_sides
    sweep = np.linspace(-np.pi / n_sides, np.pi / n_sides, arc_seg + 1)
    ang = th_v[:, None] + sweep[None, :]
    x = core_R * np.cos(th_v)[:, None] + fillet * np.cos(ang)
    y = core_R * np.sin(th_v)[:, None] + fillet * np.sin(ang)
    return np.column_stack([x.ravel(), y.ravel()])


def rounded_poly_radius_at_angle(core_R: float, fillet: float, n_sides: int,
                                 angle, phase: float = np.pi / 2.0):
    """Radial extent of the rounded N-gon along a ray from its centre.

    The shape is star-shaped about the centre: within the tangent-point
    half-angle of a vertex direction the ray hits the corner arc, otherwise
    it hits the flat face.
    """
    a = np.asarray(angle, dtype=float)
    scalar = a.ndim == 0
    a = np.atleast_1d(a)
    pn = np.pi / n_sides
    rel = (a - phase + pn) % (2.0 * pn) - pn      # to nearest vertex direction
    phi_t = np.arctan2(fillet * np.sin(pn), core_R + fillet * np.cos(pn))
    apothem = core_R * np.cos(pn) + fillet
    r_face = apothem / np.cos(pn - np.abs(rel))
    s = core_R * np.sin(np.abs(rel))
    r_arc = core_R * np.cos(rel) + np.sqrt(np.maximum(fillet ** 2 - s * s, 0.0))
    out = np.where(np.abs(rel) <= phi_t, r_arc, r_face)
    return float(out[0]) if scalar else out


def rounded_poly_ring_resampled(core_R: float, fillet: float, n_sides: int,
                                n: int, phase: float = np.pi / 2.0
                                ) -> np.ndarray:
    """*n* points evenly spaced along the rounded N-gon perimeter.

    Starts at the corner-0 arc midpoint (the +π/2 vertex direction) — the
    same start/winding convention as ``throat_adapter._poly_points`` — so
    adapter lofts pair sections without a rotational twist.
    """
    dense = rounded_polygon_ring(core_R, fillet, n_sides, arc_seg=64,
                                 phase=phase)
    dense = np.roll(dense, -32, axis=0)           # corner-0 arc midpoint first
    seg = np.diff(np.vstack([dense, dense[:1]]), axis=0)
    seg_len = np.hypot(seg[:, 0], seg[:, 1])
    cum = np.concatenate([[0.0], np.cumsum(seg_len)])
    t = np.linspace(0.0, cum[-1], n, endpoint=False)
    idx = np.clip(np.searchsorted(cum, t, side="right") - 1, 0, len(dense) - 1)
    frac = (t - cum[idx]) / np.maximum(seg_len[idx], 1e-12)
    nxt = (idx + 1) % len(dense)
    return dense[idx] + (dense[nxt] - dense[idx]) * frac[:, None]


def rounded_poly_wall(z: np.ndarray, r_eq: np.ndarray, n_sides: int,
                      thickness: float, corner_radius: float) -> dict:
    """Per-station wall arrays for the rounded polygonal horn.

    Single source of truth shared by the mesh engine, the UI preview, the
    flange sizing and the adapter section stack — keep them in sync by
    calling this, not by re-deriving the offset.

    Returns dict of parallel arrays: ``core``/``f_in`` (inner section),
    ``core_out``/``f_out`` (outer section = true in-plane parallel offset by
    t·n_r), ``z_out`` (outer axial stations, ends pinned like the sharp
    engine), ``R_in``/``R_out`` (across-corner radial extents) and
    ``r_eq_out`` (area-equivalent radius of the outer section).
    """
    core, f_in = rounded_poly_core(r_eq, n_sides, corner_radius)
    nml = _utils.compute_profile_normals(z, core + f_in, flip_if_negative=True)
    d = thickness * nml[:, 1]
    z_out = np.clip(z + thickness * nml[:, 0], np.min(z), np.max(z))
    z_out[0] = z[0]
    z_out[-1] = z[-1]
    core_out, f_out = offset_rounded_poly(core, f_in, d, n_sides)
    return {
        "core": core, "f_in": f_in,
        "core_out": core_out, "f_out": f_out,
        "z_out": z_out,
        "R_in": core + f_in, "R_out": core_out + f_out,
        "r_eq_out": np.sqrt(rounded_poly_area(core_out, f_out, n_sides) / np.pi),
    }


def _ring_loft_mesh(rings_i, rings_o, z_i, z_o,
                    output_path: str | None = None,
                    log_label: str = "") -> mesh.Mesh:
    """Watertight two-wall loft from per-station inner/outer 2-D rings.

    All rings must share the same point count M and winding; frames bridge
    inner→outer at both ends. Same topology as the sharp N-gon engine with
    M in place of N.
    """
    nz = len(rings_i)
    M = len(rings_i[0])
    n_tri = 4 * M * (nz - 1) + 4 * M
    data = np.zeros(n_tri, dtype=mesh.Mesh.dtype)
    tri = 0

    def emit(a, b, c):
        nonlocal tri
        data["vectors"][tri] = [a, b, c]
        tri += 1

    def ring3d(ring, zv):
        return [[p[0], p[1], zv] for p in ring]

    for i in range(nz - 1):
        ci  = ring3d(rings_i[i],   z_i[i])
        ci1 = ring3d(rings_i[i+1], z_i[i+1])
        co  = ring3d(rings_o[i],   z_o[i])
        co1 = ring3d(rings_o[i+1], z_o[i+1])
        for k in range(M):
            kk = (k + 1) % M
            emit(ci[k],  ci1[k],  ci[kk])
            emit(ci[kk], ci1[k],  ci1[kk])
            emit(co[k],  co[kk],  co1[k])
            emit(co[kk], co1[kk], co1[k])

    ci_b = ring3d(rings_i[0], z_i[0])
    co_b = ring3d(rings_o[0], z_o[0])
    for k in range(M):
        kk = (k + 1) % M
        emit(ci_b[k],  co_b[k],  ci_b[kk])
        emit(co_b[k],  co_b[kk], ci_b[kk])

    ci_t = ring3d(rings_i[-1], z_i[-1])
    co_t = ring3d(rings_o[-1], z_o[-1])
    for k in range(M):
        kk = (k + 1) % M
        emit(ci_t[k],  ci_t[kk], co_t[k])
        emit(ci_t[kk], co_t[kk], co_t[k])

    assert tri == n_tri, f"Triangle count mismatch: {tri} vs {n_tri}"
    m_obj = mesh.Mesh(data)
    _utils.ensure_positive_volume(m_obj)
    if output_path:
        m_obj.save(output_path)
        logger.info("Exported: %s  (%d tris%s)", output_path, n_tri,
                    f", {log_label}" if log_label else "")
    return m_obj


def generate_polygonal_3d_mesh(
    z: np.ndarray,
    r_eq: np.ndarray,
    n_sides: int,
    thickness: float = 4.0,
    output_path: str | None = None,
    corner_radius: float = 0.0,
    arc_seg: int = 8,
) -> mesh.Mesh:
    """
    Build a watertight N-gon horn STL from (z, r_eq) profile.

    z, r_eq  — profile arrays (r_eq = area-equivalent circular radius)
    n_sides  — number of polygon sides (3–12)
    thickness — uniform wall thickness applied along face normals
    corner_radius — fillet radius (mm) of the section corners. 0 = sharp
        N-gon (legacy path, byte-identical). >0 = rounded N-gon,
        area-matched; each corner arc uses *arc_seg* segments.
    """
    nz = len(z)
    if n_sides < 3:
        raise ValueError("n_sides must be >= 3")

    if corner_radius > 0.0:
        W = rounded_poly_wall(z, r_eq, n_sides, thickness, corner_radius)
        rings_i = [rounded_polygon_ring(W["core"][i], W["f_in"][i],
                                        n_sides, arc_seg) for i in range(nz)]
        rings_o = [rounded_polygon_ring(W["core_out"][i], W["f_out"][i],
                                        n_sides, arc_seg) for i in range(nz)]
        return _ring_loft_mesh(
            rings_i, rings_o, z, W["z_out"], output_path,
            log_label=f"{n_sides}-gon r={corner_radius:g}")

    # Inner circumradii
    R_i = _r_to_circumradius(r_eq, n_sides)

    # Profile normals in the (z, R) plane
    nml = _utils.compute_profile_normals(z, R_i, flip_if_negative=True)
    n_z = nml[:, 0]
    n_r = nml[:, 1]

    # Outer circumradii and z — uniform thickness along the face normal
    # Moving each face outward by t → each vertex moves t / cos(π/N) in the
    # circumradius direction (standard polygon offset geometry).
    cos_pn = np.cos(np.pi / n_sides)
    R_o = R_i + thickness / cos_pn * n_r
    z_o = z + thickness * n_z
    z_o = np.clip(z_o, z[0], z[-1])
    z_o[0]  = z[0]
    z_o[-1] = z[-1]

    # Vertex angles (rotate by π/2 so flat face faces front for even N)
    theta = np.linspace(0, 2.0 * np.pi, n_sides, endpoint=False) + np.pi / 2.0

    def corners(R, zv):
        return [[R * np.cos(th), R * np.sin(th), zv] for th in theta]

    # Triangle budget
    #   inner walls: N × (nz-1) quads = 2·N·(nz-1) tris
    #   outer walls: same
    #   bottom frame: N quads = 2·N tris
    #   top frame:    same
    n_tri = 4 * n_sides * (nz - 1) + 4 * n_sides
    data = np.zeros(n_tri, dtype=mesh.Mesh.dtype)
    tri = 0

    def emit(a, b, c):
        nonlocal tri
        data["vectors"][tri] = [a, b, c]
        tri += 1

    # Walls
    for i in range(nz - 1):
        ci  = corners(R_i[i],   z[i])
        ci1 = corners(R_i[i+1], z[i+1])
        co  = corners(R_o[i],   z_o[i])
        co1 = corners(R_o[i+1], z_o[i+1])

        for k in range(n_sides):
            kk = (k + 1) % n_sides
            # Inner wall — normals inward → reversed winding
            emit(ci[k],  ci1[k],  ci[kk])
            emit(ci[kk], ci1[k],  ci1[kk])
            # Outer wall — normals outward → forward winding
            emit(co[k],  co[kk],  co1[k])
            emit(co[kk], co1[kk], co1[k])

    # Bottom frame (−Z outward normal)
    ci_b = corners(R_i[0], z[0])
    co_b = corners(R_o[0], z_o[0])
    for k in range(n_sides):
        kk = (k + 1) % n_sides
        emit(ci_b[k],  co_b[k],  ci_b[kk])
        emit(co_b[k],  co_b[kk], ci_b[kk])

    # Top frame (+Z outward normal)
    ci_t = corners(R_i[-1], z[-1])
    co_t = corners(R_o[-1], z_o[-1])
    for k in range(n_sides):
        kk = (k + 1) % n_sides
        emit(ci_t[k],  ci_t[kk], co_t[k])
        emit(ci_t[kk], co_t[kk], co_t[k])

    assert tri == n_tri, f"Triangle count mismatch: {tri} vs {n_tri}"

    m_obj = mesh.Mesh(data)
    _utils.ensure_positive_volume(m_obj)

    if output_path:
        m_obj.save(output_path)
        logger.info("Exported: %s  (%d tris, %d-gon)", output_path, n_tri, n_sides)

    return m_obj


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    from profile_generator import get_tractrix

    z, r = get_tractrix(20, 200, 300)
    for n in [3, 4, 6, 8, 12]:
        generate_polygonal_3d_mesh(z, r, n, thickness=4.0,
                                   output_path=f"io/poly_{n}.stl")
