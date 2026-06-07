"""
Throat adapter — transitions from circular driver interface to horn throat shape.

Designed for circular/rectangular/polygonal horns that mate with a round compression driver.
The adapter maintains the cross-sectional area expansion from the horn profile.

Driver interfaces:
  - Flanged: circular flange with bolt holes (reuses flange_generator)
  - Threaded: 1⅜"-18 female thread with a 25 mm acoustic bore

Architecture:
  ThreadSpec        → thread geometry constants
  _morph_slice()    → 2-D cross-section at one Z position
  make_adapter()    → builds the transition section (morphing loft) as a trimesh
  make_threaded_socket() → threaded driver interface
  make_adapter_assembly() → combines socket + transition into one mesh
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import trimesh
from trimesh import creation as _tc

logger = logging.getLogger(__name__)

# ======================================================================
#  Thread specifications
# ======================================================================

@dataclass(frozen=True)
class ThreadSpec:
    """Standard compression driver thread geometry."""
    name: str
    major_diam: float        # mm — outer thread diameter
    bore_diam: float         # mm — clear acoustic passage after the thread
    pitch: float             # mm
    tpi: float               # threads per inch (informational)

THREAD_SPECS: dict[str, ThreadSpec] = {
    "1_375in": ThreadSpec('1\u215c"-18', 34.925, 25.0, 25.4 / 18.0, 18),
}

# ======================================================================
#  2-D cross-section helpers
# ======================================================================

_NP = 64  # points per perimeter


def _circle_points(r: float, n: int = _NP, phase: float = 0.0) -> np.ndarray:
    """Return N×2 array of points on a circle of radius *r*."""
    th = np.linspace(0, 2 * np.pi, n, endpoint=False) + phase
    return np.column_stack([r * np.cos(th), r * np.sin(th)])


def _ellipse_points(rx: float, ry: float, n: int = _NP) -> np.ndarray:
    """Return N×2 array of points on an ellipse with semi-axes *rx*, *ry*."""
    th = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return np.column_stack([rx * np.cos(th), ry * np.sin(th)])


def _rect_points(hw: float, hh: float, n: int = _NP) -> np.ndarray:
    """Return N×2 array of points on a rectangle (±hw, ±hh).

    Perimeter starts at MID-RIGHT (hw, 0) — matching θ=0 on the circle —
    and proceeds counter-clockwise so every vertex maps to the same
    parametric angle, producing a twist-free morphing loft.
    """
    th = np.linspace(0, 2 * np.pi, n, endpoint=False)
    perim = 4.0 * (hw + hh)
    p = th / (2 * np.pi) * perim

    x = np.empty(n); y = np.empty(n)

    # Segment 1: right edge top half — (hw, 0) → (hw, hh)
    s1 = hh
    m1 = p < s1
    x[m1] = hw
    y[m1] = p[m1]

    # Segment 2: top edge — (hw, hh) → (-hw, hh)
    s2 = s1 + 2.0 * hw
    m2 = (p >= s1) & (p < s2)
    x[m2] = hw - (p[m2] - s1)
    y[m2] = hh

    # Segment 3: left edge — (-hw, hh) → (-hw, -hh)
    s3 = s2 + 2.0 * hh
    m3 = (p >= s2) & (p < s3)
    x[m3] = -hw
    y[m3] = hh - (p[m3] - s2)

    # Segment 4: bottom edge — (-hw, -hh) → (hw, -hh)
    s4 = s3 + 2.0 * hw
    m4 = (p >= s3) & (p < s4)
    x[m4] = -hw + (p[m4] - s3)
    y[m4] = -hh

    # Segment 5: right edge bottom half — (hw, -hh) → (hw, 0)
    m5 = p >= s4
    x[m5] = hw
    y[m5] = -hh + (p[m5] - s4)

    return np.column_stack([x, y])


def _poly_points(n_sides: int, circumradius: float, n: int = _NP) -> np.ndarray:
    """Return N×2 array of *n* points on a regular N-gon.

    Vertices use the same +π/2 phase as ``polygonal_horn`` so the adapter
    throat lands on the horn without a rotational offset.
    Points are distributed evenly along the perimeter, always returning
    exactly *n* points for compatibility with the morphing engine.
    """
    # Match polygonal_horn.generate_polygonal_3d_mesh orientation.
    v_theta = np.linspace(0, 2 * np.pi, n_sides, endpoint=False) + np.pi / 2.0
    # Vertex positions
    verts = np.column_stack([circumradius * np.cos(v_theta),
                              circumradius * np.sin(v_theta)])

    # Edge lengths
    edges = np.roll(verts, -1, axis=0) - verts
    edge_len = np.sqrt((edges ** 2).sum(axis=1))
    perim = edge_len.sum()

    # Parametric positions along perimeter for *n* points
    t = np.linspace(0.0, perim, n, endpoint=False)
    cum_len = np.concatenate([[0.0], np.cumsum(edge_len)])

    xs = np.empty(n); ys = np.empty(n)
    for i in range(n):
        pos = t[i]
        edge_idx = int(np.searchsorted(cum_len, pos, side='right') - 1)
        edge_idx = max(0, min(edge_idx, n_sides - 1))
        frac = (pos - cum_len[edge_idx]) / max(edge_len[edge_idx], 1e-12)
        frac = np.clip(frac, 0.0, 1.0)
        j0, j1 = edge_idx, (edge_idx + 1) % n_sides
        pt = verts[j0] + frac * (verts[j1] - verts[j0])
        xs[i], ys[i] = pt

    return np.column_stack([xs, ys])


def _polygon_area(pts: np.ndarray) -> float:
    """Signed area of a 2-D polygon (shoelace).  Returns absolute value."""
    x, y = pts[:, 0], pts[:, 1]
    return 0.5 * abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))


def _centroid(pts: np.ndarray) -> np.ndarray:
    """Centroid of a 2-D polygon."""
    x, y = pts[:, 0], pts[:, 1]
    a = _polygon_area(pts)
    cx = np.sum((x + np.roll(x, 1)) * (x * np.roll(y, 1) - np.roll(x, 1) * y)) / (6.0 * a)
    cy = np.sum((y + np.roll(y, 1)) * (x * np.roll(y, 1) - np.roll(x, 1) * y)) / (6.0 * a)
    return np.array([cx, cy])


def _offset_polygon_outward(pts: np.ndarray, dist: float) -> np.ndarray:
    """Offset a closed 2-D polygon outward by *dist* along the edge normals.

    True parallel (miter) offset: every edge moves out by exactly *dist*
    perpendicular to itself, so the result has constant perpendicular wall
    thickness.  This matches how the horn engines build their outer wall
    (`R_o = R_i + thickness/cos(π/n)` for polygons, per-side for rectangles),
    so the adapter's outer wall lines up flush with the horn's at the throat
    junction.  A naive radial-from-origin offset under-extends the corners and
    leaves a visible step there.

    Assumes a simple, roughly convex polygon (circle / rect / N-gon blends),
    which is what the morphing loft produces.
    """
    n = len(pts)
    # Outward normal sign: +1 for CCW winding, −1 for CW.
    sign = 1.0 if _signed_area(pts) > 0 else -1.0
    out = np.empty_like(pts)
    for i in range(n):
        p_prev = pts[(i - 1) % n]
        p = pts[i]
        p_next = pts[(i + 1) % n]
        e1 = p - p_prev
        e2 = p_next - p
        # Outward edge normal for CCW polygon is (dy, -dx).
        n1 = np.array([e1[1], -e1[0]]) * sign
        n2 = np.array([e2[1], -e2[0]]) * sign
        l1 = np.linalg.norm(n1); l2 = np.linalg.norm(n2)
        if l1 > 1e-12: n1 /= l1
        if l2 > 1e-12: n2 /= l2
        m = n1 + n2
        ml = np.linalg.norm(m)
        if ml < 1e-9:           # 180° spike — fall back to edge normal
            out[i] = p + n2 * dist
            continue
        m /= ml
        cos_half = np.clip(np.dot(m, n2), 0.2, 1.0)  # clamp miter at sharp corners
        out[i] = p + m * (dist / cos_half)
    return out


def _signed_area(pts: np.ndarray) -> float:
    """Signed area of a 2-D polygon (shoelace).  >0 for CCW winding."""
    x, y = pts[:, 0], pts[:, 1]
    return 0.5 * (np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def _morph_slice(
    t: float,
    driver_R: float,
    target_fn,
    target_R_eq: float,
    n: int = _NP,
    shape_t: float | None = None,
    r_eq_des: float | None = None,
    source_phase: float = 0.0,
) -> np.ndarray:
    """Single cross-section at parametric position *t* ∈ [0, 1].

    At t=0: circle of radius *driver_R*.
    At t=1: shape returned by *target_fn* (callable returning N×2), scaled
            so its area equals π·target_R_eq².
    Intermediate: morph of vertices, then scaled to maintain the requested
    equivalent-radius progression.

    ``shape_t`` controls only the geometry blend. ``r_eq_des`` controls the
    acoustic area progression. Keeping those separate lets the shape morph
    finish with zero derivative while the area derivative matches the flare.
    """
    if shape_t is None:
        shape_t = t
    if r_eq_des is None:
        r_eq_des = (1.0 - t) * driver_R + t * target_R_eq

    # Source: circle at driver radius
    src = _circle_points(driver_R, n, phase=source_phase)

    # Target shape, scaled to target area
    raw_target = target_fn()
    A_t_raw = _polygon_area(raw_target)
    if A_t_raw < 1e-12:
        A_t_raw = 1e-12
    A_target = np.pi * target_R_eq ** 2
    s = np.sqrt(A_target / A_t_raw)
    c = _centroid(raw_target)
    target = c + (raw_target - c) * s

    # Morph
    pts = (1.0 - shape_t) * src + shape_t * target

    # Scale to match the desired equivalent radius at this z
    A_raw = _polygon_area(pts)
    if A_raw < 1e-12:
        A_raw = 1e-12
    r_eq_now = np.sqrt(A_raw / np.pi)
    scale = r_eq_des / r_eq_now
    c_now = _centroid(pts)
    pts = c_now + (pts - c_now) * scale

    return pts


def _smoothstep5(t: float) -> float:
    """Quintic smoothstep with zero first derivative at both ends."""
    t = float(np.clip(t, 0.0, 1.0))
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)


def _hermite_radius(
    t: float,
    r0: float,
    r1: float,
    length: float,
    slope1: float | None,
    slope0: float = 0.0,
) -> float:
    """Equivalent-radius progression with optional end slope in mm/mm."""
    if slope1 is None or length <= 1e-9:
        return (1.0 - t) * r0 + t * r1

    t = float(np.clip(t, 0.0, 1.0))
    m0 = float(slope0) * length
    m1 = float(slope1) * length
    h00 = 2.0 * t**3 - 3.0 * t**2 + 1.0
    h10 = t**3 - 2.0 * t**2 + t
    h01 = -2.0 * t**3 + 3.0 * t**2
    h11 = t**3 - t**2
    return max(1e-6, h00 * r0 + h10 * m0 + h01 * r1 + h11 * m1)


# ======================================================================
#  Adapter transition section (morphing loft)
# ======================================================================

def make_adapter(
    driver_R: float,
    horn_shape: str,
    horn_w: float,
    horn_h: float,
    horn_n_sides: int,
    horn_R_eq: float,
    horn_circumR: float,
    axial_steps: int,
    adapter_length: float,
    wall_thickness: float,
    # Optional threaded extension
    thread_key: str | None = None,
    socket_length: float = 0.0,
    # Outer target for threaded mode (horn outer dimensions)
    outer_target_R: float | None = None,
    outer_rect_w: float | None = None,
    outer_rect_h: float | None = None,
    # C1 raccordo to the horn throat
    target_slope: float | None = None,
    outer_target_slope: float | None = None,
    output_path: str | None = None,
) -> trimesh.Trimesh:
    """Build the morphing transition section, optionally with an integrated
    threaded extension at the circular (driver) end.

    When *thread_key* and *socket_length* > 0 are given, the circular start
    of the adapter is extended downward with modeled UNF threads — the whole
    piece is one seamless watertight mesh with no boolean seam.

    Parameters
    ----------
    driver_R : float
        Radius of the circular driver exit (mm).
    horn_shape : "circular" | "elliptical" | "rectangular" | "polygonal"
    horn_w, horn_h : float
        Full throat axes for elliptical or dimensions for rectangular (mm).
    horn_n_sides : int
        Number of polygon sides (for "polygonal"); unused for circular/rectangular.
    horn_R_eq : float
        Area-equivalent radius at the horn throat (mm).
    horn_circumR : float
        Circumradius of the polygon at the horn throat (mm); unused for circular/rectangular.
    axial_steps : int
        Number of Z slices for the loft.
    adapter_length : float
        Axial length of the transition (mm).
    wall_thickness : float
        Wall thickness for outer offset (mm).
    thread_key : str, optional
        One of ``THREAD_SPECS`` keys.  When set, a threaded socket is
        integrated below the transition (the threads end smoothly at the
        morphing start).
    socket_length : float
        Depth of the threaded section (mm).
    target_slope : float, optional
        Equivalent-radius slope ``dr/dz`` at the horn throat. When provided,
        the adapter reaches the horn with the same expansion derivative.
    outer_target_slope : float, optional
        Equivalent-radius slope for the horn's outer throat profile.
    output_path : str, optional

    Returns a watertight Trimesh.
    """
    if horn_shape == "circular":
        target_R = horn_R_eq
        def _target_fn():
            return _circle_points(target_R)
        _outer_target_fn = None
        _outer_target_R = outer_target_R
    elif horn_shape == "elliptical":
        target_R = horn_R_eq
        def _target_fn():
            return _ellipse_points(horn_w / 2.0, horn_h / 2.0)
        _outer_target_fn = None
        _outer_target_R = None
        if outer_target_R is not None and outer_rect_w is not None:
            _outer_target_fn = lambda: _ellipse_points(outer_rect_w / 2.0,
                                                        outer_rect_h / 2.0)
            _outer_target_R = outer_target_R
    elif horn_shape == "rectangular":
        hw, hh = horn_w / 2.0, horn_h / 2.0
        target_R = np.sqrt(horn_w * horn_h / np.pi)
        def _target_fn():
            return _rect_points(hw, hh)
        _outer_target_fn = None
        _outer_target_R = None
        if outer_target_R is not None and outer_rect_w is not None:
            _outer_target_fn = lambda: _rect_points(outer_rect_w / 2.0,
                                                     outer_rect_h / 2.0)
            _outer_target_R = outer_target_R
    elif horn_shape == "polygonal":
        def _target_fn():
            return _poly_points(horn_n_sides, horn_circumR)
        target_R = horn_R_eq
        _outer_target_fn = None
        _outer_target_R = outer_target_R
    else:
        raise ValueError(f"unsupported horn_shape: {horn_shape!r}")
    _source_phase = np.pi / 2.0 if horn_shape == "polygonal" else 0.0

    # ---- Thread parameters ----
    has_threads = thread_key is not None and socket_length > 0.5
    _major_R = driver_R
    _minor_R = _major_R
    _outer_R = _major_R + wall_thickness
    _pitch = 1.0
    if has_threads:
        spec = THREAD_SPECS[thread_key]
        driver_R = spec.bore_diam / 2.0
        _major_R = spec.major_diam / 2.0
        _pitch = spec.pitch
        _minor_R = _major_R - 0.6495 * _pitch
        _outer_R = _major_R + wall_thickness

    n = _NP

    # ---- Build Z positions ----
    if has_threads:
        n_turns = max(1, int(socket_length / _pitch))
        thread_len = n_turns * _pitch
        n_thread = max(16, n_turns * 8)
        # The final threaded ring stays below z=0; the exact z=0 slice is the
        # clear acoustic bore from which the morph starts.
        z_thread = np.linspace(-thread_len, 0.0, n_thread, endpoint=False)
        z_trans = np.linspace(0.0, adapter_length, axial_steps)
        z = np.concatenate([z_thread, z_trans])
    else:
        z = np.linspace(0.0, adapter_length, axial_steps)

    # ---- Build the cross-section profiles ----
    # Threaded mode: transition has no wall offset (flush with horn inner).
    # Flanged mode: transition keeps the wall thickness for standalone use.
    inner_slices = []
    outer_slices = []
    z_out = []
    is_thread = []

    for zi in z:
        if has_threads and zi < 0:
            # Thread section: circular socket with its own wall thickness
            t_abs = -zi
            turn_frac = (t_abs % _pitch) / _pitch
            r_thread = _major_R - (_major_R - _minor_R) * 0.5 * (
                1.0 - np.cos(2.0 * np.pi * turn_frac))
            inner = _circle_points(r_thread, n, phase=_source_phase)
            outer = _circle_points(_outer_R, n, phase=_source_phase)
            is_thread.append(True)
        elif has_threads:
            # Threaded transition: the female thread is 1⅜", but the acoustic
            # passage starts from the spec's 25 mm bore and morphs to the target.
            # outer morphs from outer_R → outer target
            t = zi / adapter_length if adapter_length > 0 else 1.0
            shape_t = _smoothstep5(t)
            inner_R = _hermite_radius(t, driver_R, target_R,
                                      adapter_length, target_slope)
            inner = _morph_slice(t, driver_R, _target_fn, target_R, n,
                                 shape_t=shape_t, r_eq_des=inner_R,
                                 source_phase=_source_phase)
            if _outer_target_fn is not None and _outer_target_R is not None:
                outer_R = _hermite_radius(t, _outer_R, _outer_target_R,
                                          adapter_length, outer_target_slope)
                outer = _morph_slice(t, _outer_R, _outer_target_fn,
                                     _outer_target_R, n,
                                     shape_t=shape_t, r_eq_des=outer_R,
                                     source_phase=_source_phase)
            elif outer_target_R is not None:
                outer_R = _hermite_radius(t, _outer_R, outer_target_R,
                                          adapter_length, outer_target_slope)
                outer = _morph_slice(t, _outer_R, _target_fn,
                                     outer_target_R, n,
                                     shape_t=shape_t, r_eq_des=outer_R,
                                     source_phase=_source_phase)
            else:
                outer = _morph_slice(t, _outer_R, _target_fn,
                                     target_R + 0.15, n,
                                     shape_t=shape_t,
                                     source_phase=_source_phase)
            is_thread.append(False)
        else:
            # Flanged transition: double‑wall with a true outward-normal
            # (miter) offset → constant perpendicular wall thickness matching
            # the horn's wall, so the adapter↔horn junction is flush on the
            # OUTSIDE.  (A radial-from-origin offset under-extends the corners
            # and leaves a visible step there — "dentro ok, fuori il gradino".)
            t = zi / adapter_length if adapter_length > 0 else 1.0
            shape_t = _smoothstep5(t)
            inner_R = _hermite_radius(t, driver_R, target_R,
                                      adapter_length, target_slope)
            inner = _morph_slice(t, driver_R, _target_fn, target_R, n,
                                 shape_t=shape_t, r_eq_des=inner_R,
                                 source_phase=_source_phase)
            if _outer_target_fn is not None and _outer_target_R is not None:
                outer_R = _hermite_radius(t, driver_R + wall_thickness,
                                          _outer_target_R, adapter_length,
                                          outer_target_slope)
                outer = _morph_slice(t, driver_R + wall_thickness,
                                     _outer_target_fn, _outer_target_R, n,
                                     shape_t=shape_t, r_eq_des=outer_R,
                                     source_phase=_source_phase)
            elif outer_target_R is not None:
                outer_R = _hermite_radius(t, driver_R + wall_thickness,
                                          outer_target_R, adapter_length,
                                          outer_target_slope)
                outer = _morph_slice(t, driver_R + wall_thickness,
                                     _target_fn, outer_target_R, n,
                                     shape_t=shape_t, r_eq_des=outer_R,
                                     source_phase=_source_phase)
            else:
                outer = _offset_polygon_outward(inner, wall_thickness)
            is_thread.append(False)

        inner_slices.append(inner)
        outer_slices.append(outer)
        z_out.append(zi)

    has_thread_section = any(is_thread)

    z_arr = np.array(z_out)
    n_slices = len(z_arr)

    # ---- Triangulate: uniform double‑ring layout for all slices ----
    # Thread: inner (thread profile), outer (circular shell at outer_R)
    # Transition (threaded): inner = outer (both at morphing shape, flush)
    # Transition (flanged): inner ≠ outer (wall thickness offset)
    def _quad_strip(lower, upper):
        N = len(lower)
        tris = []
        for i in range(N):
            j = (i + 1) % N
            tris.append([lower[i], upper[i], lower[j]])
            tris.append([lower[j], upper[i], upper[j]])
        return np.array(tris)

    # --- Build vertex array: 2 rings per slice ---
    verts_list = []
    for i in range(n_slices):
        verts_list.append(np.column_stack([outer_slices[i], np.full(n, z_arr[i])]))
        verts_list.append(np.column_stack([inner_slices[i], np.full(n, z_arr[i])]))
    verts = np.concatenate(verts_list, axis=0)

    all_faces = []

    # Inner wall
    for i in range(n_slices - 1):
        lo = i * 2 * n + n
        hi = (i + 1) * 2 * n + n
        faces = _quad_strip(list(range(lo, lo + n)),
                            list(range(hi, hi + n)))
        all_faces.append(faces)

    # Outer wall (reverse winding, outward normal).
    for i in range(n_slices - 1):
        lo = i * 2 * n
        hi = (i + 1) * 2 * n
        faces = _quad_strip(list(range(lo, lo + n)),
                            list(range(hi, hi + n)))
        # Only reverse if the rings actually differ, otherwise keep same
        # winding and let trimesh deduplicate.
        ri_lo = i * 2 * n + n
        ri_hi = (i + 1) * 2 * n + n
        diff = not (np.allclose(verts[lo:lo+n], verts[ri_lo:ri_lo+n]) and
                    np.allclose(verts[hi:hi+n], verts[ri_hi:ri_hi+n]))
        all_faces.append(faces[:, ::-1] if diff else faces)

    # Bottom cap (lowest z)
    b0 = 0; b1 = n
    all_faces.append(np.array(
        [[[b0+i, b1+j, b0+j], [b0+i, b1+i, b1+j]] for i in range(n) for j in [(i+1)%n]]
    ).reshape(-1, 3))

    # Top cap (highest z) — non-degenerate ring for flanged case, fan for threaded
    t0 = (n_slices - 1) * 2 * n
    t1 = t0 + n
    if not np.allclose(verts[t0:t0+n], verts[t1:t1+n]):
        all_faces.append(np.array(
            [[[t0+i, t0+j, t1+j], [t0+i, t1+j, t1+i]] for i in range(n) for j in [(i+1)%n]]
        ).reshape(-1, 3))

    all_faces_arr = np.concatenate(all_faces, axis=0)

    tm = trimesh.Trimesh(vertices=verts, faces=all_faces_arr, process=True)
    tm.merge_vertices()
    tm.fix_normals()

    if tm.body_count > 1:
        bodies = [b for b in tm.split() if b.volume > 0]
        if len(bodies) == 1:
            tm = bodies[0]

    if output_path:
        tm.export(output_path)
        logger.info("Exported adapter: %s  (%d triangles)", output_path, len(tm.faces))

    return tm


# ======================================================================
#  Revolve helper (trimesh version)
# ======================================================================

def _revolve_rz(r_poly: np.ndarray, z_poly: np.ndarray,
                rings: int = 64) -> trimesh.Trimesh:
    """Revolve an open 2‑D polygon (r, z) around the Z axis.

    The last segment implicitly connects the last vertex back to the
    first, forming a closed cross‑section that yields a watertight body
    of revolution.
    """
    n_pts = len(r_poly)
    theta = np.linspace(0, 2 * np.pi, rings, endpoint=False)
    ct, st = np.cos(theta), np.sin(theta)

    all_verts = []
    all_faces = []
    offset = 0

    for i in range(n_pts):
        ri, zi = float(r_poly[i]), float(z_poly[i])
        ring = np.column_stack([ri * ct, ri * st, np.full(rings, zi)])
        all_verts.append(ring)

    for i in range(n_pts - 1):
        n0 = offset
        n1 = offset + rings
        for j in range(rings):
            jj = (j + 1) % rings
            all_faces.append([n0 + j, n1 + j, n0 + jj])
            all_faces.append([n0 + jj, n1 + j, n1 + jj])
        offset += rings

    # Closing segment: last vertex → first vertex
    n_last = (n_pts - 1) * rings
    for j in range(rings):
        jj = (j + 1) % rings
        all_faces.append([n_last + j, j, n_last + jj])
        all_faces.append([n_last + jj, j, jj])

    verts = np.concatenate(all_verts, axis=0)
    faces = np.array(all_faces)

    tm = trimesh.Trimesh(vertices=verts, faces=faces, process=True)
    tm.merge_vertices()
    tm.fix_normals()
    return tm


# ======================================================================
#  Threaded socket
# ======================================================================

def make_threaded_socket(
    thread_key: str,
    length: float,
    wall_thickness: float,
    seg: int = 48,
) -> trimesh.Trimesh:
    """Generate a threaded socket (internal thread) for a compression driver.

    Models actual thread ridges by revolving the full thread cross‑section
    around Z — no boolean operations needed for the thread profile.

    Thread form: UNF 60° V-thread (0.6495 × pitch depth).

    Parameters
    ----------
    thread_key : str
        The supported ``THREAD_SPECS`` key: ``"1_375in"``.
    length : float
        Depth of the socket (mm).
    wall_thickness : float
        Material thickness around the bore (mm).
    seg : int
        Circumferential tessellation.

    Returns a watertight Trimesh.
    """
    spec = THREAD_SPECS[thread_key]
    major_R = spec.major_diam / 2.0
    pitch = spec.pitch
    minor_R = major_R - 0.6495 * pitch
    outer_R = major_R + wall_thickness

    n_turns = max(1, int(length / pitch))
    thread_len = n_turns * pitch

    # Build the (r, z) cross‑section polygon.
    # Inner boundary follows the thread profile (root→crest→root…),
    # outer boundary is a smooth cylinder at outer_R.
    # The final closing edge goes from the last vertex back to the
    # first automatically via _revolve_rz — do NOT duplicate the
    # first point.
    r_list = [major_R]
    z_list = [0.0]
    for i in range(n_turns):
        r_list.append(minor_R)
        z_list.append((i + 0.5) * pitch)
        r_list.append(major_R)
        z_list.append((i + 1) * pitch)

    # Top annulus + outer wall back to z=0
    r_list.append(outer_R)
    z_list.append(thread_len)
    r_list.append(outer_R)
    z_list.append(0.0)

    result = _revolve_rz(np.array(r_list), np.array(z_list), seg)

    # If the requested length is longer than the integer turns, add a
    # plain cylindrical extension at the bottom (overlapping for clean union).
    if length > thread_len + 0.1 and n_turns > 0:
        extra = length - thread_len
        ext = _tc.cylinder(radius=outer_R, height=extra, sections=seg)
        hole = _tc.cylinder(radius=minor_R, height=extra + 2.0, sections=seg)
        hole.apply_translation([0, 0, -1.0])
        try:
            ext = trimesh.boolean.difference([ext, hole], engine="manifold")
        except Exception:
            pass
        if ext is not None and not ext.is_empty:
            # Cylinder centred at 0: range [-extra/2, extra/2].
            # Translate so its top overlaps the main body's bottom by 0.5 mm.
            ext.apply_translation([0, 0, -extra / 2.0 + 0.5])
            try:
                result = trimesh.boolean.union([result, ext], engine="manifold")
            except Exception:
                result = trimesh.util.concatenate([result, ext])
            result.remove_unreferenced_vertices()
            result.fix_normals()

    return result


# ======================================================================
#  Full assembly
# ======================================================================

def make_adapter_assembly(
    # Driver interface
    driver_type: str,         # "flanged" | thread_key
    driver_diam: float | None,  # for flanged only (mm)
    thread_key: str | None,     # for threaded only
    # Horn throat shape
    horn_shape: str,          # "circular" | "elliptical" | "rectangular" | "polygonal"
    rect_w: float,
    rect_h: float,
    poly_n_sides: int,
    poly_circumR: float,
    horn_R_eq: float,         # area-equivalent radius at horn throat
    # Geometry
    adapter_length: float,
    wall_thickness: float,
    axial_steps: int = 50,
    # Flange params (flanged mode)
    flange_R: float = 0.0,
    flange_thickness: float = 6.0,
    flange_bolt_R: float = 0.0,
    flange_bolt_n: int = 4,
    flange_bolt_d: float = 3.5,
    flange_bolt_phase: float = 0.0,
    flange_outer_n: int = 0,
    # Threaded socket params
    socket_length: float = 15.0,
    # Outer target (for threaded mode — horn's OUTER throat eq. radius)
    outer_target_R: float | None = None,
    outer_rect_w: float | None = None,
    outer_rect_h: float | None = None,
    target_slope: float | None = None,
    outer_target_slope: float | None = None,
    # Positioning: the horn-throat end of the transition sits at *z_offset*
    z_offset: float = 0.0,
    # Output
    output_path: str | None = None,
) -> trimesh.Trimesh:
    """Assemble the complete throat adapter: driver interface + transition.

    The adapter is centered on the Z axis. The driver interface is at
    z = *z_offset* − *adapter_length*, the horn throat is at z = *z_offset*.

    Returns a single watertight Trimesh (or None on failure).
    """
    import trimesh as _tm

    driver_R = (driver_diam / 2.0) if driver_type == "flanged" else 0.0

    # ---- 1. Build the seamless adapter (threads + transition) ----
    if adapter_length > 0.5:
        tk = thread_key if driver_type != "flanged" else None
        sl = socket_length if driver_type != "flanged" else 0.0
        adapter = make_adapter(
            driver_R if driver_type == "flanged" else THREAD_SPECS[thread_key].bore_diam / 2.0,
            horn_shape, rect_w, rect_h,
            poly_n_sides, horn_R_eq, poly_circumR,
            axial_steps, adapter_length, wall_thickness,
            thread_key=tk, socket_length=sl,
            outer_target_R=outer_target_R,
            outer_rect_w=outer_rect_w,
            outer_rect_h=outer_rect_h,
            target_slope=target_slope,
            outer_target_slope=outer_target_slope,
            output_path=None,
        )
    else:
        # No transition — just a thin ring
        r0 = driver_R if driver_type == "flanged" else \
             (THREAD_SPECS[thread_key].bore_diam / 2.0)
        adapter = _tc.cylinder(radius=r0 + wall_thickness,
                                height=1.0, sections=64)
        hole = _tc.cylinder(radius=r0, height=3.0, sections=64)
        hole.apply_translation([0, 0, -1.0])
        try:
            adapter = _tm.boolean.difference([adapter, hole], engine="manifold")
        except Exception:
            pass
        if adapter is not None:
            adapter.remove_unreferenced_vertices()
            adapter.fix_normals()

    if adapter is None or adapter.is_empty:
        return None

    # ---- 2. Flanged driver interface (bolt flange on top of adapter) ----
    bodies = [adapter]

    if driver_type == "flanged" and flange_R > 0:
        from flange_generator import generate_flange
        f_throat = generate_flange(
            throat_R=driver_R,
            flange_R=flange_R,
            thickness=flange_thickness,
            bolt_R=flange_bolt_R,
            bolt_n=int(flange_bolt_n),
            bolt_d=flange_bolt_d,
            bolt_phase=flange_bolt_phase,
            offset=0.0,
            outer_n_sides=flange_outer_n,
            output_path=None,
        )
        if f_throat is not None:
            bodies.append(f_throat)
            try:
                result = _tm.boolean.union(bodies, engine="manifold")
            except Exception:
                result = _tm.util.concatenate(bodies)
            if result is not None:
                result.remove_unreferenced_vertices()
                result.fix_normals()
                bodies = [result]

    # ---- 3. Merge (flanged only — threaded is already integrated) ----
    if len(bodies) == 1:
        result = bodies[0]
    else:
        try:
            result = _tm.boolean.union(bodies, engine="manifold")
        except Exception:
            result = _tm.util.concatenate(bodies)

    if result is None:
        return None
    result.remove_unreferenced_vertices()
    result.fix_normals()

    # ---- 4. Position: translate so top (horn-throat end) is at z_offset ----
    # The adapter's top is at z=adapter_length.  For the threaded case the
    # thread section extends below z=0, but the top reference is unchanged.
    result.apply_translation([0, 0, z_offset - adapter_length])

    if output_path:
        result.export(output_path)
        logger.info("Exported adapter assembly: %s  (%d triangles, WT=%s)",
                     output_path, len(result.faces), result.is_watertight)

    return result
