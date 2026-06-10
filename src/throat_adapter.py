"""
Throat adapter — transitions from circular driver interface to horn throat shape.

Designed for circular/rectangular/polygonal horns that mate with a round compression driver.
The adapter maintains the cross-sectional area expansion from the horn profile.

Driver interfaces:
  - Flanged: custom circular flange with bolt holes (reuses flange_generator)
  - Bolt-on: standard 1", 1.4", and 2" compression-driver mounting patterns
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

    The four corners are **always** sampled as exact vertices: the perimeter
    is split at the start point and the four corners into five arcs, and the
    `n` points are spread proportionally to arc length (≥1 interval each).
    A uniform-by-perimeter sampling only lands a vertex on every corner for a
    *square* (corner fractions 1/8, 3/8, 5/8, 7/8 → integer indices). For a
    non-square rectangle the corners fall between samples, so the connecting
    edge cuts across them and the morph produces a **chamfered corner** on both
    the inner and outer walls. Anchoring the corners removes that bevel.
    """
    perim = 4.0 * (hw + hh)

    # Forced break positions along the perimeter: start (mid-right) + 4 corners.
    keys = np.array([0.0, hh, hh + 2.0 * hw, 3.0 * hh + 2.0 * hw,
                     3.0 * hh + 4.0 * hw])
    arc_len = np.diff(np.append(keys, perim))          # 5 arc lengths

    # Distribute n intervals proportional to arc length, ≥1 per arc.
    counts = np.maximum(1, np.round(arc_len / perim * n).astype(int))
    while counts.sum() > n:                             # trim from longest arc
        counts[np.argmax(arc_len / counts)] -= 1
    while counts.sum() < n:                             # pad the longest arc
        counts[np.argmax(arc_len / counts)] += 1

    # Evenly place each arc's points, the first sitting exactly on its key.
    p = np.concatenate([
        keys[k] + arc_len[k] * np.arange(counts[k]) / counts[k]
        for k in range(5)
    ])

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
    curv1: float | None = None,
    curv0: float = 0.0,
) -> float:
    """Equivalent-radius progression with optional end slope (and curvature).

    With only ``slope1`` it is a **cubic** Hermite matching value + first
    derivative at the flare end (C1). When ``curv1`` (the flare's ``d²r/dz²``
    at the join) is also given it upgrades to a **quintic** Hermite that
    additionally matches the second derivative, so the adapter meets the flare
    with continuous curvature (C2). Cubic Hermite, starting flat, overshoots
    the end slope and curls back — its curvature near the join flips sign
    relative to the flare and shows up as an inflection line; matching curvature
    removes it. ``slope0``/``curv0`` default to 0 (the circular driver end).
    """
    if slope1 is None or length <= 1e-9:
        return (1.0 - t) * r0 + t * r1

    t = float(np.clip(t, 0.0, 1.0))
    m0 = float(slope0) * length
    m1 = float(slope1) * length
    if curv1 is None:
        h00 = 2.0 * t**3 - 3.0 * t**2 + 1.0
        h10 = t**3 - 2.0 * t**2 + t
        h01 = -2.0 * t**3 + 3.0 * t**2
        h11 = t**3 - t**2
        return max(1e-6, h00 * r0 + h10 * m0 + h01 * r1 + h11 * m1)

    # Quintic Hermite: position, 1st and 2nd derivative matched at both ends.
    # Derivatives are taken into normalized-t space (slope·L, curv·L²).
    a0 = float(curv0) * length * length
    a1 = float(curv1) * length * length
    t2 = t * t; t3 = t2 * t; t4 = t3 * t; t5 = t4 * t
    H0 = 1.0 - 10.0 * t3 + 15.0 * t4 - 6.0 * t5      # r0
    H1 = t - 6.0 * t3 + 8.0 * t4 - 3.0 * t5          # m0
    H2 = 0.5 * t2 - 1.5 * t3 + 1.5 * t4 - 0.5 * t5   # a0
    H3 = 0.5 * t3 - t4 + 0.5 * t5                    # a1
    H4 = -4.0 * t3 + 7.0 * t4 - 3.0 * t5             # m1
    H5 = 10.0 * t3 - 15.0 * t4 + 6.0 * t5            # r1
    return max(1e-6,
               H0 * r0 + H1 * m0 + H2 * a0 + H3 * a1 + H4 * m1 + H5 * r1)


# ======================================================================
#  Golden-Standard circle→ellipse morph (acoustic-first)
# ======================================================================

def morph_circle_to_ellipse(
    throat_radius: float = 12.7,
    throat_angle_deg: float = 7.5,
    transition_length_z: float = 30.0,
    target_ellipse_a: float = 40.0,
    target_ellipse_b: float = 20.0,
    z_steps: int = 100,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Morph a circular throat into an elliptical cross-section over Z.

    The cross-sectional area expansion ``A(z) = π·r_eq(z)²`` is the primary
    acoustic driver (the "Golden Standard").  The shape (circle → ellipse)
    adapts to the area, not the other way around.  First-derivative continuity
    at z=0 matches the compression driver's exit angle exactly.

    Parameters
    ----------
    throat_radius : float
        Radius of the circular throat at z=0 (mm).  Default 12.7 mm (0.5").
    throat_angle_deg : float
        Throat half-angle in degrees.  ``dr_eq/dz|_{z=0} = tan(θ)``.
        Default 7.5° (industry standard for 1" compression drivers).
    transition_length_z : float
        Total length of the transition (mm).  Default 30 mm.
    target_ellipse_a : float
        Target semi-major axis at z=L (mm).
    target_ellipse_b : float
        Target semi-minor axis at z=L (mm).
    z_steps : int
        Number of evenly-spaced Z positions to generate.

    Returns
    -------
    z : np.ndarray      shape (z_steps,)
        Z positions (mm).
    a : np.ndarray      shape (z_steps,)
        Semi-major axis at each Z (mm).
    b : np.ndarray      shape (z_steps,)
        Semi-minor axis at each Z (mm).
    r_eq : np.ndarray   shape (z_steps,)
        Equivalent radius ``r_eq(z) = sqrt(A(z)/π)`` (mm).

    Notes
    -----
    **Area-first design (Golden Standard):**

    * ``r_eq(z)`` drives the expansion via a **quintic Hermite** polynomial
      that is C²-continuous (smooth first and second derivatives) and
      monotonically increasing.
    * ``R(z) = a(z)/b(z)`` morphs from 1 (circle) to ``target_a / target_b``
      (ellipse) via a quintic smoothstep with zero derivatives at both ends.
    * Semi-axes enforce the area rule at every slice:
      ``a(z) = r_eq(z)·√R(z)``,  ``b(z) = r_eq(z)/√R(z)``.

    **Boundary conditions at z=0:**

    * ``r_eq(0) = throat_radius``
    * ``dr_eq/dz(0) = tan(throat_angle)`` — matches driver exit cone
    * ``d²r_eq/dz²(0) = 0`` — smooth launch
    * ``R(0) = 1`` — circle

    **Boundary conditions at z=L:**

    * ``r_eq(L) = sqrt(target_a·target_b)`` — area-equivalent radius
    * ``dr_eq/dz(L) = d²r_eq/dz²(L) = 0`` — smooth handoff to waveguide
    * ``R(L) = target_a/target_b`` — ellipse
    """
    L = float(transition_length_z)
    if L <= 1e-9:
        raise ValueError("transition_length_z must be > 0")
    if z_steps < 2:
        raise ValueError("z_steps must be >= 2")

    theta = np.radians(float(throat_angle_deg))
    slope_0 = np.tan(theta)                          # dr_eq/dz at z=0 (mm/mm)

    r0 = float(throat_radius)
    r1 = np.sqrt(float(target_ellipse_a) * float(target_ellipse_b))

    R_target = float(target_ellipse_a) / float(max(target_ellipse_b, 1e-9))

    # ---- Equivalent-radius quintic Hermite (C²) ----
    # H(t), t = z/L ∈ [0,1]
    #   H(0)=r0,  H'(0)=m0=slope_0·L,  H''(0)=0
    #   H(1)=r1,  H'(1)=0,              H''(1)=0
    m0 = slope_0 * L
    dr = r1 - r0
    # Closed-form coefficients derived from the 6×6 Hermite system
    # a₀=r0, a₁=m0, a₂=0, a₃=10·(r1-r0)−6·m0, a₄=8·m0−15·(r1-r0), a₅=6·(r1-r0)−3·m0
    a3 = 10.0 * dr - 6.0 * m0
    a4 = 8.0 * m0 - 15.0 * dr
    a5 = 6.0 * dr - 3.0 * m0

    z = np.linspace(0.0, L, int(z_steps))
    t = z / L
    t2 = t * t
    t3 = t2 * t
    t4 = t3 * t
    t5 = t4 * t

    r_eq = r0 + m0 * t + a3 * t3 + a4 * t4 + a5 * t5

    # ---- Aspect-ratio morph (quintic smoothstep) ----
    s = t3 * (t * (t * 6.0 - 15.0) + 10.0)          # quintic smoothstep
    R = 1.0 + (R_target - 1.0) * s

    # ---- Semi-axes from area + aspect ratio ----
    sqrt_R = np.sqrt(np.maximum(R, 1e-12))
    a = r_eq * sqrt_R
    b = r_eq / sqrt_R

    return z, a, b, r_eq

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
    # C2 raccordo (equivalent-radius curvature at the horn throat)
    target_curv: float | None = None,
    outer_target_curv: float | None = None,
    # Exact target section (horn_shape="custom")
    custom_pts: np.ndarray | None = None,
    custom_outer_pts: np.ndarray | None = None,
    custom_pts_z: np.ndarray | None = None,
    output_path: str | None = None,
    return_cutter: bool = False,
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
    horn_shape : "circular" | "elliptical" | "rectangular" | "polygonal" | "custom"
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
    target_curv, outer_target_curv : float, optional
        Equivalent-radius curvature ``d²r/dz²`` of the inner/outer flare at the
        horn throat. When given alongside the matching slope, the radius
        progression uses a quintic Hermite so the adapter reaches the flare
        with continuous curvature (C2) — removes the inflection line at the
        join that a cubic (C1-only) raccordo leaves.
    custom_pts : np.ndarray, optional
        With ``horn_shape="custom"``: the EXACT target inner section(s) as
        closed polygons centred on the axis, vertices ordered CCW by
        ascending azimuth from φ=0 (same parametrisation as the source
        circle). Either a single ``(m, 2)`` section at the handoff plane, or
        a ``(K, m, 2)`` stack of sections at the local-z stations
        ``custom_pts_z`` — then each loft slice morphs toward the section
        interpolated *at its own z*, so the adapter's tail follows the real
        flare shape (aspect ratio included) through the weld overlap, not a
        uniformly scaled copy of the end section. Used for non-analytic
        sections — e.g. the OS-SE ``r(z, φ)`` contour, which is *not* an
        ellipse: an area-matched ellipse leaves a visible step ring at the
        adapter↔flare junction; a single scaled end-section still leaves a
        small one (the OS-SE aspect ratio changes with z).
    custom_outer_pts : np.ndarray, optional
        Matching OUTER-wall contour(s) (same shape as ``custom_pts``). When
        given, the loft's outer wall blends from the plain miter offset
        (driver end) into the exact contour (horn end), so the outer skin is
        also flush. Needed when the horn engine offsets along the true 3-D
        normal (OS-SE): its in-plane wall is ``thickness / cos(slope)``,
        wider than the 2-D miter offset.
    custom_pts_z : np.ndarray, optional
        Local-z stations (driver plane = 0 … ``adapter_length`` = horn end)
        for a ``(K, m, 2)`` ``custom_pts`` stack; the last station must be
        the handoff plane. Ignored for a single ``(m, 2)`` section.
    output_path : str, optional

    Returns a watertight Trimesh.
    """
    # The outer wall is always a constant-thickness parallel offset of the
    # morphed inner (see the transition loop below), so only the *inner* target
    # shape is needed here. The ``outer_target_*``/``outer_rect_*`` parameters
    # are accepted for signature/back-compat but no longer drive the wall — a
    # parallel offset is inherently flush with the horn and never balloons the
    # wall into a solid wedge on the narrow axis of an elongated target.
    if horn_shape == "circular":
        target_R = horn_R_eq
        def _target_fn():
            return _circle_points(target_R)
    elif horn_shape == "elliptical":
        target_R = horn_R_eq
        def _target_fn():
            return _ellipse_points(horn_w / 2.0, horn_h / 2.0)
    elif horn_shape == "rectangular":
        hw, hh = horn_w / 2.0, horn_h / 2.0
        target_R = np.sqrt(horn_w * horn_h / np.pi)
        def _target_fn():
            return _rect_points(hw, hh)
    elif horn_shape == "polygonal":
        def _target_fn():
            return _poly_points(horn_n_sides, horn_circumR)
        target_R = horn_R_eq
    elif horn_shape == "custom":
        if custom_pts is None:
            raise ValueError("horn_shape='custom' requires custom_pts")
        _stack_in = np.asarray(custom_pts, dtype=float)
        if _stack_in.ndim == 2:                       # single end section
            _stack_in = _stack_in[None]
            _stack_z = np.array([float(adapter_length)])
        else:                                          # (K, m, 2) stack
            if custom_pts_z is None:
                raise ValueError("a custom_pts stack requires custom_pts_z")
            _stack_z = np.asarray(custom_pts_z, dtype=float)
            if len(_stack_z) != len(_stack_in):
                raise ValueError("custom_pts_z length must match custom_pts")
        _custom_in = _stack_in[-1]                    # handoff-plane section
        target_R = horn_R_eq if horn_R_eq > 0 else float(
            np.sqrt(_polygon_area(_custom_in) / np.pi))
        def _target_fn():
            return _custom_in
    else:
        raise ValueError(f"unsupported horn_shape: {horn_shape!r}")
    _source_phase = np.pi / 2.0 if horn_shape == "polygonal" else 0.0

    # Outer-contour stack for "custom": per-slice deltas blended in along the
    # loft so the outer wall lands exactly on the horn's outer section at the
    # join (and through the weld overlap).
    _stack_z = None
    if custom_pts_z is not None:
        _stack_z = np.asarray(custom_pts_z, dtype=float)

    _stack_delta = None
    if custom_outer_pts is not None and custom_pts is not None:
        _stack_out = np.asarray(custom_outer_pts, dtype=float)
        _stack_in_ref = np.asarray(custom_pts, dtype=float)
        if _stack_out.ndim == 2:
            _stack_out = _stack_out[None]
            _stack_in_ref = _stack_in_ref[None]
        if _stack_out.shape != _stack_in_ref.shape:
            raise ValueError("custom_outer_pts must match custom_pts shape")
        _stack_delta = _stack_out - _stack_in_ref

    def _stack_at(stack, z_loc):
        """Linear interpolation of a (K, m, 2) section stack at local z."""
        if len(stack) == 1:
            return stack[0]
        if _stack_z is None:
            idx = (z_loc / adapter_length) * (len(stack) - 1) if adapter_length > 0 else 0.0
            i = int(np.clip(np.floor(idx), 0, len(stack) - 2))
            w = idx - i
            return (1.0 - w) * stack[i] + w * stack[i + 1]
        z_loc = float(np.clip(z_loc, _stack_z[0], _stack_z[-1]))
        i = int(np.clip(np.searchsorted(_stack_z, z_loc) - 1, 0, len(stack) - 2))
        dz_st = _stack_z[i + 1] - _stack_z[i]
        w = (z_loc - _stack_z[i]) / dz_st if dz_st > 1e-12 else 1.0
        return (1.0 - w) * stack[i] + w * stack[i + 1]

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

    # A custom section keeps its own vertex count so the adapter's end ring
    # is vertex-exact against the section it was sampled from.
    n = len(_custom_in) if horn_shape == "custom" else _NP

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

    def _slice_target(zi):
        """Per-slice morph target: the custom section interpolated at this z
        (so the tail follows the real flare), else the fixed end target."""
        if horn_shape == "custom" and len(_stack_in) > 1:
            sec = _stack_at(_stack_in, zi)
            return lambda: sec
        return _target_fn

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
            t = zi / adapter_length if adapter_length > 0 else 1.0
            shape_t = _smoothstep5(t)
            inner_R = _hermite_radius(t, driver_R, target_R,
                                      adapter_length, target_slope,
                                      curv1=target_curv)
            inner = _morph_slice(t, driver_R, _slice_target(zi), target_R, n,
                                 shape_t=shape_t, r_eq_des=inner_R,
                                 source_phase=_source_phase)
            # Constant-thickness wall: the outer is a true parallel (miter)
            # offset of the morphed inner, so the transition stays exactly
            # *wall_thickness* thick. Morphing the outer independently toward the
            # horn's area-equivalent outer used to make the narrow axis of an
            # elongated target overshoot *more* than the inner did, packing the
            # space between the threaded collar and the flare with solid material
            # ("lo spazio tra flangia e flare non deve essere pieno"). A parallel
            # offset is also automatically flush with the horn at the join — the
            # horn wall is the same constant offset of the same inner profile.
            outer = _offset_polygon_outward(inner, wall_thickness)
            if _stack_delta is not None:
                outer_target = _stack_at(_stack_out, zi)
                outer = (1.0 - shape_t) * outer + shape_t * outer_target
            is_thread.append(False)
        else:
            # Flanged transition: double‑wall with a true outward-normal
            # (miter) offset → constant perpendicular wall thickness matching
            # the horn's wall, so the adapter↔horn junction is flush on the
            # OUTSIDE.  (A radial-from-origin offset under-extends the corners
            # and leaves a visible step there — "dentro ok, fuori il gradino".)
            # The parallel offset is used unconditionally: morphing the outer
            # independently to the horn's area-equivalent outer made the narrow
            # axis of an elongated target overshoot more than the inner did,
            # filling the wall solid. The constant offset is inherently flush
            # (the horn wall is the same offset of the same inner) and keeps the
            # wall exactly *wall_thickness* thick.
            t = zi / adapter_length if adapter_length > 0 else 1.0
            shape_t = _smoothstep5(t)
            inner_R = _hermite_radius(t, driver_R, target_R,
                                      adapter_length, target_slope,
                                      curv1=target_curv)
            inner = _morph_slice(t, driver_R, _slice_target(zi), target_R, n,
                                 shape_t=shape_t, r_eq_des=inner_R,
                                 source_phase=_source_phase)
            outer = _offset_polygon_outward(inner, wall_thickness)
            if _stack_delta is not None:
                # Blend the plain miter wall into the horn's true outer
                # contour so the OUTER skin is also flush at the join (a 3-D
                # normal-offset horn wall is wider in-plane than the miter).
                outer_target = _stack_at(_stack_out, zi)
                outer = (1.0 - shape_t) * outer + shape_t * outer_target
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


    if return_cutter:
        # Build cutter mesh using only the inner walls (the first (n_slices)*n vertices)
        n_slices_c = len(verts) // (2 * n)
        c_verts = [verts[k * 2 * n : k * 2 * n + n] for k in range(n_slices_c)]
        c_verts_flat = np.vstack(c_verts)
        
        c_faces = []
        for i in range(n_slices_c - 1):
            lo = i * n
            hi = (i + 1) * n
            c_faces.append(_quad_strip(list(range(lo, lo + n)), list(range(hi, hi + n))))
            
        # Bottom cap (z=0, simple fan)
        c_faces.append(np.array(
            [[[0, j, i]] for i in range(1, n-1) for j in [i+1]]
        ).reshape(-1, 3))
        
        # Top cap
        t_c = (n_slices_c - 1) * n
        c_faces.append(np.array(
            [[[t_c+i, t_c+j, t_c+0]] for i in range(1, n-1) for j in [i+1]]
        ).reshape(-1, 3)) # simple fan triangulation since it's convex
        
        c_faces_flat = np.concatenate(c_faces, axis=0)
        # flip normals so it's a solid facing outward
        c_faces_flat = c_faces_flat[:, ::-1]
        cutter_tm = trimesh.Trimesh(vertices=c_verts_flat, faces=c_faces_flat, process=True)
        cutter_tm.fix_normals()
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

    return (tm, cutter_tm) if return_cutter else tm


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
    driver_type: str,         # "flanged" | DRIVER_FLANGE_SPECS key | thread_key
    driver_diam: float | None,  # for flanged only (mm)
    thread_key: str | None,     # for threaded only
    # Horn throat shape
    horn_shape: str,          # "circular" | "elliptical" | "rectangular" | "polygonal" | "custom"
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
    driver_clearance: float = 0.3,
    # Threaded socket params
    socket_length: float = 15.0,
    # Outer target (for threaded mode — horn's OUTER throat eq. radius)
    outer_target_R: float | None = None,
    outer_rect_w: float | None = None,
    outer_rect_h: float | None = None,
    target_slope: float | None = None,
    outer_target_slope: float | None = None,
    target_curv: float | None = None,
    outer_target_curv: float | None = None,
    # Exact target section (horn_shape="custom") — see make_adapter
    custom_pts: np.ndarray | None = None,
    custom_outer_pts: np.ndarray | None = None,
    custom_pts_z: np.ndarray | None = None,
    # Positioning: the horn-throat end of the transition sits at *z_offset*
    z_offset: float = 0.0,
    # Output
    output_path: str | None = None,
) -> trimesh.Trimesh:
    """Assemble the complete throat adapter: driver interface + transition.

    The adapter is centered on the Z axis. The driver interface is at
    z = *z_offset* − *adapter_length*, the horn throat is at z = *z_offset*.
    When a flange is present, the transition body is shortened by the flange
    thickness so the requested *adapter_length* stays measured from the
    flange's lower face instead of creating a collar inside the throat.

    Returns a single watertight Trimesh (or None on failure).
    """
    import trimesh as _tm

    from flange_generator import DRIVER_FLANGE_SPECS

    is_custom_flange = driver_type == "flanged"
    is_bolt_on = driver_type in DRIVER_FLANGE_SPECS
    is_threaded = driver_type in THREAD_SPECS
    if not (is_custom_flange or is_bolt_on or is_threaded):
        raise ValueError(f"Unsupported driver_type: {driver_type}")
    if is_bolt_on:
        driver_R = (DRIVER_FLANGE_SPECS[driver_type].throat_diam + driver_clearance) / 2.0
    elif is_custom_flange:
        driver_R = driver_diam / 2.0
    else:
        driver_R = 0.0

    # ---- 1. Build the seamless adapter (threads + transition) ----
    if adapter_length > 0.5:
        tk = thread_key if is_threaded else None
        sl = socket_length if is_threaded else 0.0
        adapter, cutter_tm = make_adapter(
            THREAD_SPECS[thread_key].bore_diam / 2.0 if is_threaded else driver_R,
            horn_shape, rect_w, rect_h,
            poly_n_sides, horn_R_eq, poly_circumR,
            axial_steps, adapter_length, wall_thickness,
            thread_key=tk, socket_length=sl,
            outer_target_R=outer_target_R,
            outer_rect_w=outer_rect_w,
            outer_rect_h=outer_rect_h,
            target_slope=target_slope,
            outer_target_slope=outer_target_slope,
            target_curv=target_curv,
            outer_target_curv=outer_target_curv,
            custom_pts=custom_pts,
            custom_outer_pts=custom_outer_pts,
            return_cutter=True,
            custom_pts_z=custom_pts_z,
            output_path=None,
        )
    else:
        # No transition — just a thin ring
        r0 = THREAD_SPECS[thread_key].bore_diam / 2.0 if is_threaded else driver_R
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
    if is_bolt_on or (is_custom_flange and flange_R > 0):
        from flange_generator import generate_driver_mounting_flange, generate_flange
        if is_bolt_on:
            f_throat = generate_driver_mounting_flange(
                driver_type,
                thickness=flange_thickness,
                throat_clearance=-1000.0,
                offset=flange_thickness,
            )
        else:
            f_throat = generate_flange(
                throat_R=driver_R + max(driver_clearance / 2.0, wall_thickness),
                flange_R=flange_R,
                thickness=flange_thickness,
                bolt_R=flange_bolt_R,
                bolt_n=int(flange_bolt_n),
                bolt_d=flange_bolt_d,
                bolt_phase=flange_bolt_phase,
                offset=flange_thickness,
                outer_n_sides=flange_outer_n,
                output_path=None,
            )
        if f_throat is not None:
            try:
                if is_bolt_on:
                    # Bolt-on flange has a straight hole (driver_R), but the airway expands.
                    # Subtract the airway cutter from the flange before unioning,
                    # so the expanding airway remains perfectly clean.
                    try:
                        cut_flange = _tm.boolean.difference([f_throat, cutter_tm], engine="manifold")
                        if not cut_flange.is_empty:
                            f_throat = cut_flange
                    except Exception:
                        pass
                bodies.append(f_throat)
                result = _tm.boolean.union(bodies, engine="manifold")
            except Exception:
                # If union fails, bodies is already appended
                if f_throat not in bodies:
                    bodies.append(f_throat)
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
    # When a driver flange is present, the flange occupies the first portion
    # of the requested length, but the transition keeps the full adapter
    # length so the throat↔flare raccordo is not compressed.
    result.apply_translation([0, 0, z_offset - adapter_length])

    if output_path:
        result.export(output_path)
        logger.info("Exported adapter assembly: %s  (%d triangles, WT=%s)",
                     output_path, len(result.faces), result.is_watertight)

    return result


# ======================================================================
#  Verification plot (run: python src/throat_adapter.py)
# ======================================================================

if __name__ == "__main__":
    import matplotlib
    matplotlib.use("TkAgg")
    import matplotlib.pyplot as plt

    z, a, b, r_eq = morph_circle_to_ellipse(
        throat_radius=12.7,
        throat_angle_deg=7.5,
        transition_length_z=30.0,
        target_ellipse_a=60.0,
        target_ellipse_b=30.0,
        z_steps=200,
    )

    L = z[-1]
    A = np.pi * r_eq ** 2
    dA_dz = np.gradient(A, z)
    d2A_dz2 = np.gradient(dA_dz, z)

    theta = np.radians(7.5)
    expected_slope = 2.0 * np.pi * 12.7 * np.tan(theta)

    fig, axes = plt.subplots(2, 3, figsize=(16, 10))
    fig.suptitle("morph_circle_to_ellipse — Acoustic Verification", fontsize=14,
                 fontweight="bold")

    # (0,0) Equivalent radius r_eq(z)
    ax = axes[0, 0]
    ax.plot(z, r_eq, "b-", lw=2, label=r"$r_{eq}(z)$")
    z_tang = np.linspace(0, L, 50)
    ax.plot(z_tang, 12.7 + z_tang * np.tan(theta), "r--", lw=1,
            label=f"Tangent at z=0 ({7.5}° half-angle)")
    ax.axvline(0, color="gray", ls=":", lw=0.8)
    ax.axhline(12.7, color="gray", ls=":", lw=0.8)
    ax.axvline(L, color="gray", ls=":", lw=0.8)
    target_R = np.sqrt(60 * 30)
    ax.axhline(target_R, color="gray", ls=":", lw=0.8)
    ax.set_xlabel("Z (mm)")
    ax.set_ylabel("r_eq (mm)")
    ax.set_title("Equivalent Radius $r_{eq}(z)$ — C² Quintic Hermite")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # (0,1) Semi-axes a(z), b(z)
    ax = axes[0, 1]
    ax.plot(z, a, "r-", lw=2, label="a(z) — semi-major")
    ax.plot(z, b, "g-", lw=2, label="b(z) — semi-minor")
    ax.plot(z, r_eq, "b--", lw=1, label=r"$r_{eq}(z)$")
    ax.axvline(0, color="gray", ls=":", lw=0.8)
    ax.axhline(12.7, color="gray", ls=":", lw=0.8)
    ax.axvline(L, color="gray", ls=":", lw=0.8)
    ax.axhline(60.0, color="red", ls=":", lw=0.5)
    ax.axhline(30.0, color="green", ls=":", lw=0.5)
    ax.set_xlabel("Z (mm)")
    ax.set_ylabel("Semi-axis (mm)")
    ax.set_title("Ellipse Semi-Axes $a(z), b(z)$")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # (0,2) Aspect ratio R(z)
    ax = axes[0, 2]
    R_z = a / b
    ax.plot(z, R_z, "m-", lw=2)
    ax.axhline(1.0, color="gray", ls=":", lw=0.8, label="R=1 (circle)")
    ax.axhline(60.0 / 30.0, color="gray", ls=":", lw=0.8)
    ax.set_xlabel("Z (mm)")
    ax.set_ylabel("Aspect Ratio R = a/b")
    ax.set_title("Aspect Ratio $R(z)$ — Quintic Smoothstep")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # (1,0) Area A(z)
    ax = axes[1, 0]
    ax.plot(z, A, "b-", lw=2, label=r"$A(z) = \pi r_{eq}^2$")
    ax.axvline(0, color="gray", ls=":", lw=0.8)
    ax.axhline(np.pi * 12.7 ** 2, color="gray", ls=":", lw=0.8)
    ax.axvline(L, color="gray", ls=":", lw=0.8)
    ax.set_xlabel("Z (mm)")
    ax.set_ylabel("Cross-Sectional Area (mm²)")
    ax.set_title("Area Expansion $A(z)$")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # (1,1) dA/dz — MUST NOT spike or drop at z=0
    ax = axes[1, 1]
    ax.plot(z, dA_dz, "r-", lw=2, label=r"$dA/dz$")
    ax.axhline(expected_slope, color="orange", ls="--", lw=1,
               label=f"Expected at z=0: {expected_slope:.1f} mm²/mm")
    ax.axvline(0, color="gray", ls=":", lw=0.8)
    ax.axhline(0, color="gray", ls=":", lw=0.8)
    ax.set_xlabel("Z (mm)")
    ax.set_ylabel("dA/dz (mm²/mm)")
    ax.set_title(r"Area Slope $dA/dz$ — No spike/drop at z=0")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # (1,2) d²A/dz² — curvature, verify C² smoothness
    ax = axes[1, 2]
    ax.plot(z, d2A_dz2, "purple", lw=2, label=r"$d^2A/dz^2$")
    ax.axhline(0, color="gray", ls=":", lw=0.8)
    ax.axvline(0, color="gray", ls=":", lw=0.8)
    ax.axvline(L, color="gray", ls=":", lw=0.8)
    ax.set_xlabel("Z (mm)")
    ax.set_ylabel("d²A/dz² (mm²/mm²)")
    ax.set_title(r"Area Curvature $d^2A/dz^2$ — C² Smoothness")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()

    # Print numerical verification
    actual_slope = dA_dz[0]
    print(f"\n{'='*60}")
    print(f"  Verification: morph_circle_to_ellipse")
    print(f"{'='*60}")
    print(f"  Throat radius          : {12.7} mm")
    print(f"  Target ellipse a×b     : {60.0} × {30.0} mm")
    print(f"  Transition length      : {L} mm")
    print(f"  Throat half-angle      : {7.5}°")
    print(f"  Expected r_eq(0)       : {12.7:.6f} mm  →  got {r_eq[0]:.6f}")
    print(f"  Expected r_eq(L)       : {target_R:.6f} mm  →  got {r_eq[-1]:.6f}")
    print(f"  Expected dr_eq/dz(0)   : {np.tan(theta):.6f}  →  got {(r_eq[1]-r_eq[0])/(z[1]-z[0]):.6f}")
    print(f"  Expected dA/dz(0)      : {expected_slope:.3f} mm²/mm")
    print(f"  Actual dA/dz(0)        : {actual_slope:.3f} mm²/mm")
    print(f"  dA/dz(0) error         : {abs(actual_slope - expected_slope):.4f} mm²/mm")
    print(f"  d²A/dz²(0)             : {d2A_dz2[0]:.6f} mm²/mm²  (≈ 0)")
    print(f"  a(L)                   : {a[-1]:.6f} mm  (target: {60.0})")
    print(f"  b(L)                   : {b[-1]:.6f} mm  (target: {30.0})")
    print(f"  r_eq monotonic         : {bool(np.all(np.diff(r_eq) >= 0))}")
    print(f"  a monotonic            : {bool(np.all(np.diff(a) >= 0))}")
    print(f"  b monotonic            : {bool(np.all(np.diff(b) >= 0))}")
    print(f"  dA/dz ≥ 0 everywhere   : {bool(np.all(dA_dz >= -1e-9))}")
    print(f"{'='*60}\n")

    # Cross-section shapes at selected z positions
    fig2, ax2 = plt.subplots(figsize=(8, 8))
    n_cross = 6
    idx = np.linspace(0, len(z) - 1, n_cross, dtype=int)
    colors = plt.cm.viridis(np.linspace(0, 1, n_cross))
    phi = np.linspace(0, 2 * np.pi, 200)
    for i, (j, c) in enumerate(zip(idx, colors)):
        x = a[j] * np.cos(phi)
        y = b[j] * np.sin(phi)
        ax2.plot(x, y, color=c, lw=1.5,
                 label=f"z={z[j]:.1f} mm  a={a[j]:.1f}  b={b[j]:.1f}")
    ax2.set_aspect("equal")
    ax2.set_xlabel("X (mm)")
    ax2.set_ylabel("Y (mm)")
    ax2.set_title("Cross-Section Evolution: Circle → Ellipse")
    ax2.legend(fontsize=7, loc="upper right")
    ax2.grid(True, alpha=0.3)

    plt.show()
