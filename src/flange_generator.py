"""
Parametric Circular Flange — CSG boolean operations.

  z_top    = offset          (flush with horn throat)
  z_bottom = offset - thickness

Inner hole radius = throat_R  (matches horn throat).
Outer radius      = flange_R.
Bolt holes        = genuine cutouts via trimesh boolean difference.
"""

import logging
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import trimesh
from trimesh import creation

_src = str(Path(__file__).resolve().parent)
if _src not in sys.path:
    sys.path.insert(0, _src)

logger = logging.getLogger(__name__)

# Legacy defaults
OUTER_DIAM = 60.0
INNER_DIAM = 29.0
THICKNESS = 6.0
BOLT_RADIUS = 22.0
BOLT_COUNT = 4
BOLT_DIAM = 3.5


@dataclass(frozen=True)
class DriverFlangeSpec:
    """Industrial bolt-on compression-driver mounting pattern."""

    name: str
    throat_diam: float
    outer_diam: float
    bolt_count: int
    bolt_diam: float
    pcd: float
    bolt_phase: float = 0.0


DRIVER_FLANGE_SPECS: dict[str, DriverFlangeSpec] = {
    "bolt_on_1in_2": DriverFlangeSpec(
        '1" bolt-on, 2-hole', 25.4, 100.0, 2, 6.5, 76.2
    ),
    "bolt_on_1in_3": DriverFlangeSpec(
        '1" bolt-on, 3-hole', 25.4, 90.0, 3, 6.5, 57.2
    ),
    "bolt_on_1_4in_4": DriverFlangeSpec(
        '1.4" bolt-on, 4-hole', 35.6, 135.0, 4, 6.5, 101.6
    ),
    "bolt_on_2in_4": DriverFlangeSpec(
        '2" bolt-on, 4-hole', 50.8, 135.0, 4, 6.5, 101.6
    ),
}


def driver_mounting_hole_centers(driver_type: str) -> np.ndarray:
    """Return the XY centres of a standard bolt-on driver's mounting holes."""
    spec = DRIVER_FLANGE_SPECS[driver_type]
    angles = spec.bolt_phase + 2.0 * np.pi * np.arange(spec.bolt_count) / spec.bolt_count
    radius = spec.pcd / 2.0
    return np.column_stack([radius * np.cos(angles), radius * np.sin(angles)])


def generate_driver_mounting_flange(
    driver_type: str,
    thickness: float = 6.0,
    throat_clearance: float = 0.3,
    offset: float = 0.0,
    seg: int = 96,
    output_path: str | None = None,
    bolt_phase: float | None = None,
) -> trimesh.Trimesh | None:
    """Generate a standard bolt-on compression-driver mounting flange.

    ``driver_type`` selects an entry from ``DRIVER_FLANGE_SPECS``. The centre
    bore is the nominal driver throat plus ``throat_clearance``; all mounting
    dimensions remain fixed by the selected industrial pattern. ``bolt_phase``
    overrides the catalog phase when provided; adapter assemblies use it to
    rotate the 3-hole preset toward the open corridor of the flare.
    """
    spec = DRIVER_FLANGE_SPECS[driver_type]
    phase = spec.bolt_phase if bolt_phase is None else bolt_phase
    return generate_flange(
        throat_R=max(1.0, (spec.throat_diam + throat_clearance) / 2.0),
        flange_R=spec.outer_diam / 2.0,
        thickness=thickness,
        bolt_R=spec.pcd / 2.0,
        bolt_n=spec.bolt_count,
        bolt_d=spec.bolt_diam,
        offset=offset,
        seg=seg,
        output_path=output_path,
        bolt_phase=phase,
    )


def generate_flange(
    throat_R: float,
    flange_R: float,
    thickness: float = 6.0,
    bolt_R: float = 22.0,
    bolt_n: int = 4,
    bolt_d: float = 3.5,
    offset: float = 0.0,
    seg: int = 64,
    output_path: str | None = None,
    outer_n_sides: int = 0,
    bolt_phase: float = 0.0,
) -> trimesh.Trimesh | None:
    """
    Circular-inner flange — CSG boolean difference.

    The flange sits with its TOP face at *offset* and grows downward (-Z).
    Inner hole radius = *throat_R* (circular, matches the horn throat).
    outer_n_sides: 0 = circular outer body; ≥3 = regular N-gon prism outer body.
    Bolt holes are genuine cutouts via trimesh boolean operations.
    """
    from shapely.geometry import Polygon as _ShapelyPolygon

    zb = offset - thickness
    disc_center_z = zb + thickness / 2.0

    # ── Outer body ──────────────────────────────────────────────────────
    if outer_n_sides >= 3:
        # The inner hole (circle of radius throat_R) must fit inside the polygon inradius.
        # inradius = flange_R * cos(π/N). Enforce flange_R ≥ throat_R / cos(π/N) + 1 mm.
        min_flange_R = throat_R / np.cos(np.pi / outer_n_sides) + 1.0
        flange_R = max(flange_R, min_flange_R)
        theta_out = np.linspace(0, 2 * np.pi, outer_n_sides, endpoint=False) + np.pi / 2
        verts_out = [[flange_R * np.cos(t), flange_R * np.sin(t)] for t in theta_out]
        disc = trimesh.creation.extrude_polygon(_ShapelyPolygon(verts_out), height=thickness)
        disc.apply_translation([0, 0, zb])
        # clamp bolt circle so holes stay inside the inradius
        bolt_R = min(bolt_R, flange_R * np.cos(np.pi / outer_n_sides) - bolt_d / 2.0 - 1.0)
    else:
        disc = creation.cylinder(
            radius=flange_R,
            height=thickness,
            sections=seg,
            transform=np.array([
                [1, 0, 0, 0],
                [0, 1, 0, 0],
                [0, 0, 1, disc_center_z],
                [0, 0, 0, 1],
            ]),
        )

    # ── Bodies to subtract ──────────────────────────────────────────────
    hole_height = thickness + 2.0
    to_sub: list[trimesh.Trimesh] = []

    # Throat hole
    throat_hole = creation.cylinder(
        radius=throat_R,
        height=hole_height,
        sections=seg,
        transform=np.array([
            [1, 0, 0, 0],
            [0, 1, 0, 0],
            [0, 0, 1, disc_center_z],
            [0, 0, 0, 1],
        ]),
    )
    to_sub.append(throat_hole)

    # Bolt holes
    for k in range(bolt_n):
        a = bolt_phase + 2 * np.pi * k / bolt_n
        cx, cy = bolt_R * np.cos(a), bolt_R * np.sin(a)
        bh = creation.cylinder(
            radius=bolt_d / 2.0,
            height=hole_height,
            sections=12,
            transform=np.array([
                [1, 0, 0, cx],
                [0, 1, 0, cy],
                [0, 0, 1, disc_center_z],
                [0, 0, 0, 1],
            ]),
        )
        to_sub.append(bh)

    # ── Boolean difference ──────────────────────────────────────────────
    flange = trimesh.boolean.difference([disc] + to_sub, engine="manifold")

    if flange is None:
        logger.error("Boolean operation returned None")
        return None

    flange.remove_unreferenced_vertices()
    flange.update_faces(flange.nondegenerate_faces())
    flange.fix_normals()

    if output_path:
        flange.export(output_path)
        logger.info(
            "Exported: %s  (%d triangles, WT=%s)",
            output_path, len(flange.faces), flange.is_watertight,
        )

    return flange


def generate_profile_flange(
    inner_type: str,
    thickness: float,
    bolt_n: int,
    bolt_d: float,
    offset: float,
    inner_R: float = 0.0,
    inner_w: float = 0.0,
    inner_h: float = 0.0,
    inner_n_sides: int = 0,
    outer_mode: str = "offset",
    outer_type: str = "circular",
    outer_offset: float = 15.0,
    outer_diam: float = 0.0,
    outer_w: float = 0.0,
    outer_h: float = 0.0,
    outer_n_sides: int = 0,
    bolt_mode: str = "auto",
    bolt_R: float = 0.0,
    bolt_phase: float = 0.0,
    seg: int = 128,
    output_path: str | None = None,
) -> trimesh.Trimesh | None:
    """Generate an outward Mouth/Mid flange around any supported flare opening.

    The flange top face is at ``offset`` and grows downward. ``outer_mode`` is
    either ``"offset"`` (outer shape follows the opening) or ``"custom"``
    (circular, polygonal, or rectangular outer dimensions). ``bolt_mode`` is
    either ``"auto"`` (each hole is centred radially in the available material)
    or ``"fixed"`` (all holes use the requested ``bolt_R``).
    """
    from shapely.geometry import Polygon as _ShapelyPolygon

    valid_inner = {"circular", "polygonal", "rectangular", "elliptical"}
    valid_outer = {"circular", "polygonal", "rectangular", "elliptical"}
    if inner_type not in valid_inner:
        raise ValueError(f"unsupported inner_type: {inner_type}")
    if outer_mode not in {"offset", "custom"}:
        raise ValueError("outer_mode must be 'offset' or 'custom'")
    if outer_type not in valid_outer:
        raise ValueError(f"unsupported outer_type: {outer_type}")
    if bolt_mode not in {"auto", "fixed"}:
        raise ValueError("bolt_mode must be 'auto' or 'fixed'")

    def _shape_points(shape: str, R: float, w: float, h: float, n: int) -> np.ndarray:
        if shape == "rectangular":
            return np.array([[-w / 2, -h / 2], [w / 2, -h / 2],
                             [w / 2, h / 2], [-w / 2, h / 2]], dtype=float)
        count = n if shape == "polygonal" else seg
        phase = np.pi / 2.0 if shape == "polygonal" else 0.0
        angles = np.linspace(0.0, 2.0 * np.pi, count, endpoint=False) + phase
        if shape == "elliptical":
            return np.column_stack([(w / 2.0) * np.cos(angles),
                                    (h / 2.0) * np.sin(angles)])
        return np.column_stack([R * np.cos(angles), R * np.sin(angles)])

    def _polygon_radial_extent(poly, angle: float) -> float:
        """Intersect a ray from the origin with an actual Shapely boundary."""
        points = np.asarray(poly.exterior.coords, dtype=float)[:, :2]
        ray = np.array([np.cos(angle), np.sin(angle)])
        best = np.inf
        for p0, p1 in zip(points, points[1:]):
            edge = p1 - p0
            cross = ray[0] * edge[1] - ray[1] * edge[0]
            if abs(cross) < 1e-12:
                continue
            t = (p0[0] * edge[1] - p0[1] * edge[0]) / cross
            u = (p0[0] * ray[1] - p0[1] * ray[0]) / cross
            if t > 0.0 and -1e-9 <= u <= 1.0 + 1e-9:
                best = min(best, t)
        return float(best)

    if inner_type == "polygonal" and inner_n_sides < 3:
        raise ValueError("polygonal inner requires inner_n_sides >= 3")
    if outer_mode == "offset":
        outer_type = inner_type
        if inner_type == "circular":
            outer_diam = 2.0 * (inner_R + outer_offset)
        elif inner_type == "polygonal":
            outer_n_sides = inner_n_sides
            outer_diam = 2.0 * (
                inner_R + outer_offset / np.cos(np.pi / inner_n_sides))
        else:
            outer_w = inner_w + 2.0 * outer_offset
            outer_h = inner_h + 2.0 * outer_offset
    elif outer_type == "polygonal" and outer_n_sides < 3:
        raise ValueError("polygonal outer requires outer_n_sides >= 3")

    outer_R = outer_diam / 2.0
    inner_pts = _shape_points(
        inner_type, inner_R, inner_w, inner_h, inner_n_sides)
    inner_poly = _ShapelyPolygon(inner_pts)
    bolt_mid_poly = None
    if outer_mode == "offset" and inner_type == "elliptical":
        # True geometric offset of an ellipse is a parallel curve, NOT an
        # ellipse. Shapely buffer() produces constant ring width all around;
        # the old outer_w/h = inner + 2·ring built a scaled ellipse that
        # thins at the diagonals.
        outer_poly = inner_poly.buffer(outer_offset)
        bolt_mid_poly = inner_poly.buffer(outer_offset / 2.0)
    else:
        outer_pts = _shape_points(
            outer_type, outer_R, outer_w, outer_h, outer_n_sides)
        outer_poly = _ShapelyPolygon(outer_pts)
    if not outer_poly.buffer(1e-7).contains(inner_poly):
        raise ValueError("outer flange dimensions do not contain the flare opening")

    zb = offset - thickness
    body = trimesh.creation.extrude_polygon(outer_poly, height=thickness)
    body.apply_translation([0.0, 0.0, zb])
    hole_h = thickness + 2.0
    bore = trimesh.creation.extrude_polygon(inner_poly, height=hole_h)
    bore.apply_translation([0.0, 0.0, zb - 1.0])
    cuts: list[trimesh.Trimesh] = [bore]

    angles = (bolt_phase + 2.0 * np.pi * np.arange(int(bolt_n)) /
              max(int(bolt_n), 1))
    margin = bolt_d / 2.0 + 1.0
    if bolt_mode == "fixed" and len(angles):
        sample = np.linspace(0.0, 2.0 * np.pi, 360, endpoint=False)
        inner_limit = max(_polygon_radial_extent(inner_poly, a)
                          for a in sample) + margin
        outer_limit = min(_polygon_radial_extent(outer_poly, a)
                          for a in sample) - margin
        if outer_limit <= inner_limit:
            raise ValueError("not enough flange material for a fixed bolt circle")
        bolt_R = float(np.clip(bolt_R, inner_limit, outer_limit))

    for angle in angles:
        ri = _polygon_radial_extent(inner_poly, angle)
        ro = _polygon_radial_extent(outer_poly, angle)
        if bolt_mode == "auto":
            radius = (_polygon_radial_extent(bolt_mid_poly, angle)
                      if bolt_mid_poly is not None else (ri + ro) / 2.0)
        else:
            radius = bolt_R
        if radius < ri + margin or radius > ro - margin:
            raise ValueError("not enough flange material around a bolt hole")
        cx, cy = radius * np.cos(angle), radius * np.sin(angle)
        cut = creation.cylinder(radius=bolt_d / 2.0, height=hole_h, sections=24)
        cut.apply_translation([cx, cy, zb + thickness / 2.0])
        cuts.append(cut)

    flange = trimesh.boolean.difference([body] + cuts, engine="manifold")
    if flange is None or flange.is_empty:
        logger.error("Profile flange boolean operation failed")
        return None
    flange.remove_unreferenced_vertices()
    flange.update_faces(flange.nondegenerate_faces())
    flange.fix_normals()
    if output_path:
        flange.export(output_path)
    return flange


def generate_polygonal_flange(
    inner_circumR: float,
    n_sides: int,
    flange_R: float,
    thickness: float = 6.0,
    bolt_R: float = 22.0,
    bolt_n: int = 4,
    bolt_d: float = 3.5,
    offset: float = 0.0,
    seg: int = 64,
    output_path: str | None = None,
    outer_n_sides: int = 0,
    bolt_phase: float = 0.0,
) -> trimesh.Trimesh | None:
    """
    Polygonal flange — N-gon inner hole matching the horn cross-section.

    inner_circumR  — circumradius of the N-gon inner hole.
    n_sides        — sides of the inner hole (matches horn).
    outer_n_sides  — sides of the outer body: 0 = circular, ≥3 = N-gon prism.
    flange_R       — circumradius of the outer boundary.
    """
    from shapely.geometry import Polygon as _ShapelyPolygon

    zb = offset - thickness
    disc_center_z = zb + thickness / 2.0

    if outer_n_sides >= 3:
        # Inner N-gon circumradius must fit inside outer polygon inradius.
        # Worst case: inner polygon circumradius = inner_circumR.
        # Outer inradius = flange_R * cos(π/outer_N) must exceed inner circumradius.
        min_flange_R = inner_circumR / np.cos(np.pi / outer_n_sides) + 1.0
        flange_R = max(flange_R, min_flange_R)
        theta_out = np.linspace(0, 2 * np.pi, outer_n_sides, endpoint=False) + np.pi / 2
        verts_out = [[flange_R * np.cos(t), flange_R * np.sin(t)] for t in theta_out]
        disc = trimesh.creation.extrude_polygon(_ShapelyPolygon(verts_out), height=thickness)
        disc.apply_translation([0, 0, zb])
    else:
        disc = creation.cylinder(
            radius=flange_R,
            height=thickness,
            sections=seg,
            transform=np.array([
                [1, 0, 0, 0],
                [0, 1, 0, 0],
                [0, 0, 1, disc_center_z],
                [0, 0, 0, 1],
            ]),
        )

    # Clamp bolt_R so bolt cylinders stay inside the outer body
    if outer_n_sides >= 3:
        inradius = flange_R * np.cos(np.pi / outer_n_sides)
        bolt_R = min(bolt_R, inradius - bolt_d / 2.0 - 1.0)
    else:
        bolt_R = min(bolt_R, flange_R - bolt_d / 2.0 - 1.0)

    hole_h = thickness + 2.0
    to_sub: list[trimesh.Trimesh] = []

    # N-gon inner hole — same vertex rotation as the horn (offset π/2)
    theta_ngon = np.linspace(0, 2 * np.pi, n_sides, endpoint=False) + np.pi / 2
    verts_2d = [[inner_circumR * np.cos(t), inner_circumR * np.sin(t)] for t in theta_ngon]
    ngon_poly = _ShapelyPolygon(verts_2d)
    ngon_prism = trimesh.creation.extrude_polygon(ngon_poly, height=hole_h)
    ngon_prism.apply_translation([0, 0, zb - 1])
    to_sub.append(ngon_prism)

    # Bolt holes
    for k in range(bolt_n):
        a = bolt_phase + 2 * np.pi * k / bolt_n
        cx, cy = bolt_R * np.cos(a), bolt_R * np.sin(a)
        bh = creation.cylinder(
            radius=bolt_d / 2.0,
            height=hole_h,
            sections=12,
            transform=np.array([
                [1, 0, 0, cx],
                [0, 1, 0, cy],
                [0, 0, 1, disc_center_z],
                [0, 0, 0, 1],
            ]),
        )
        to_sub.append(bh)

    flange = trimesh.boolean.difference([disc] + to_sub, engine="manifold")

    if flange is None:
        logger.error("Boolean operation returned None")
        return None

    flange.remove_unreferenced_vertices()
    flange.update_faces(flange.nondegenerate_faces())
    flange.fix_normals()

    if output_path:
        flange.export(output_path)
        logger.info(
            "Exported: %s  (%d triangles, WT=%s)",
            output_path, len(flange.faces), flange.is_watertight,
        )

    return flange


def generate_contour_flange(
    inner_xy: np.ndarray,
    thickness: float,
    bolt_n: int,
    bolt_d: float,
    offset: float,
    wall: float = 0.0,
    ring: float = 15.0,
    bite: float = 0.5,
    bolt_R: float = 0.0,
    bolt_phase: float = 0.0,
    output_path: str | None = None,
    outer_xy: np.ndarray | None = None,
) -> trimesh.Trimesh | None:
    """Flat flange whose hole and outer ring follow an **arbitrary closed
    contour** (e.g. the superelliptical OS-SE mouth, ridges included), instead
    of being forced to a circle/ellipse/rectangle.

    ``inner_xy`` is the airway (inner-wall) contour, (N, 2). The hole is that
    contour pulled **in** by ``bite`` so the constant-thickness wall pokes
    through and fuses; the outer body is the contour pushed **out** by
    ``wall + ring`` (``wall`` clears the wall, ``ring`` is the bolting land).
    When ``outer_xy`` is supplied, it is used as the explicit outer boundary
    instead, so inward roll-back plates can follow two real sampled contours
    without fitting either one to a scaled ellipse.
    Bolts are spaced evenly by arc length along the mid-line of the land, so
    they follow the contour shape. Top face at ``offset``, grows down by
    ``thickness`` (same convention as the other flanges)."""
    from shapely.geometry import Polygon as _ShapelyPolygon

    inner_poly = _ShapelyPolygon(np.asarray(inner_xy, dtype=float))
    if not inner_poly.is_valid:
        inner_poly = inner_poly.buffer(0)
    hole_poly = inner_poly.buffer(-abs(bite))
    if outer_xy is None:
        outer_poly = inner_poly.buffer(wall + ring)
    else:
        outer_poly = _ShapelyPolygon(np.asarray(outer_xy, dtype=float))
        if not outer_poly.is_valid:
            outer_poly = outer_poly.buffer(0)
    if hole_poly.is_empty or outer_poly.is_empty:
        logger.error("contour flange: degenerate buffer (ring/bite too large)")
        return None
    if not outer_poly.buffer(1e-7).contains(hole_poly):
        raise ValueError("explicit outer contour does not contain flange hole")
    land_poly = outer_poly.difference(hole_poly)
    if land_poly.is_empty:
        return None

    zb = offset - thickness
    body = trimesh.creation.extrude_polygon(
        land_poly if land_poly.geom_type == "Polygon"
        else max(land_poly.geoms, key=lambda g: g.area),
        height=thickness)
    body.apply_translation([0.0, 0.0, zb])

    cuts: list[trimesh.Trimesh] = []
    hole_h = thickness + 2.0
    n = int(bolt_n)
    if n > 0:
        midline = inner_poly.buffer(wall + ring * 0.5).exterior
        total = midline.length
        for k in range(n):
            p = midline.interpolate((bolt_phase / (2.0 * np.pi) + k / n) % 1.0 * total,
                                    normalized=False)
            cut = creation.cylinder(radius=bolt_d / 2.0, height=hole_h, sections=24)
            cut.apply_translation([p.x, p.y, zb + thickness / 2.0])
            cuts.append(cut)

    flange = trimesh.boolean.difference([body] + cuts, engine="manifold") if cuts else body
    if flange is None or flange.is_empty:
        logger.error("contour flange boolean failed")
        return None
    flange.remove_unreferenced_vertices()
    flange.update_faces(flange.nondegenerate_faces())
    flange.fix_normals()
    if output_path:
        flange.export(output_path)
    return flange


def generate_throat_chamfer(
    base_xy: np.ndarray,
    top_xy: np.ndarray,
    base_z: float,
    height: float,
    width: float,
    overlap: float = 0.35,
    tip: float = 0.35,
    samples: int = 128,
    output_path: str | None = None,
) -> trimesh.Trimesh | None:
    """Weld-reinforcement chamfer ring that bridges a flange top to the horn
    body, producing a watertight trimesh suitable for boolean union.

    Cross-section (radial slice)::

            top_inner (top_xy)              top_outer (top_xy + tip·width)
            |                               |
            |  inner wall (on horn body)    |  outer wall (sloped)
            |                               |
            bottom_inner                   bottom_outer
          (base_xy − overlap·width)     (base_xy + width)

    **Parameters**

    base_xy : (N, 2) float
        Outer contour of the horn at the flange-top level (z = base_z).
    top_xy : (N, 2) float
        Outer contour of the horn at the higher z level (z = base_z + height).
    base_z : float
        Z coordinate of the bottom face (flange top).
    height : float
        Axial extent of the chamfer (mm).
    width : float
        Radial extent of the chamfer foot on the flange (mm).
    overlap : float
        Fraction of *width* that the inner wall bites inward from the horn
        surface for volumetric fusion (0 = flush, 0.35 typical).
    tip : float
        Fraction of *width* for the outer-wall offset at the top edge. Must
        be > 0 to keep the top cap non-degenerate.
    samples : int
        Circumferential vertex count per ring (≥ 16).
    output_path : str | None
        Optional STL export path.

    **Non-manifold root causes (diagnosed)**

    1. ``tip == 0`` → top-inner ≡ top-outer → top cap collapses to a line;
       three faces meet at every top edge *without* a closing cap, producing
       non-manifold edges.  **Fix:** internally clamp ``tip ≥ 0.01``.

    2. ``overlap`` or ``width`` too large for a tightly-curved contour →
       Shapely ``buffer(-d)`` collapses the polygon → inner ring is empty.

    3. Non-convex or self-intersecting contours (e.g. OS-SE ridges) —
       Shapely ``buffer(+d)`` can self-intersect; the resulting exterior
       has duplicate/crossing vertices that break the loft triangulation.

    4. ``base_xy`` and ``top_xy`` have different winding orders → loft
       faces twist and cross → self-intersection.

    Returns a watertight ``trimesh.Trimesh`` or ``None`` on failure.
    """
    from shapely.geometry import Polygon as _ShapelyPolygon

    if not (np.isfinite(base_z) and np.isfinite(height)
            and np.isfinite(width) and np.isfinite(overlap)
            and np.isfinite(tip)):
        raise ValueError("throat chamfer dimensions must be finite")
    if height <= 0 or width <= 0:
        raise ValueError("throat chamfer height and width must be positive")
    if overlap <= 0 or tip <= 0:
        raise ValueError("throat chamfer overlap and tip must be positive")
    if samples < 16:
        raise ValueError("throat chamfer samples must be at least 16")
    tip = max(tip, 0.01)

    top_z = base_z + height

    # --- uniform resample of an (N,2) contour to *samples* CCW points ---
    def _resample(pts: np.ndarray, n: int) -> np.ndarray:
        pts = np.asarray(pts, dtype=float)
        poly = _ShapelyPolygon(pts)
        if not poly.is_valid:
            poly = poly.buffer(0)
        ring = poly.exterior
        total = ring.length
        out = np.empty((n, 2), dtype=float)
        for i in range(n):
            p = ring.interpolate(total * i / n)
            out[i] = [p.x, p.y]
        return out

    # --- offset a contour inward (-) or outward (+) ---
    def _offset(pts: np.ndarray, dist: float) -> np.ndarray | None:
        poly = _ShapelyPolygon(np.asarray(pts, dtype=float))
        if not poly.is_valid:
            poly = poly.buffer(0)
        result = poly.buffer(dist)
        if result.is_empty:
            return None
        ring = result.exterior
        total = ring.length
        out = np.empty((samples, 2), dtype=float)
        for i in range(samples):
            p = ring.interpolate(total * i / samples)
            out[i] = [p.x, p.y]
        return out

    # --- ensure CW or CCW consistently ---
    def _ensure_ccw(pts: np.ndarray) -> np.ndarray:
        signed = np.sum(
            (pts[:, 0] * np.roll(pts[:, 1], -1)
             - np.roll(pts[:, 0], -1) * pts[:, 1]))
        return pts[::-1].copy() if signed < 0 else pts.copy()

    base_r = _resample(base_xy, samples)
    top_r = _resample(top_xy, samples)
    base_r = _ensure_ccw(base_r)
    top_r = _ensure_ccw(top_r)

    inner_bottom = _offset(base_r, -overlap * width)
    if inner_bottom is None:
        logger.error("throat chamfer inner ring collapsed (overlap·width too large)")
        return None
    outer_bottom = _offset(base_r, width)
    if outer_bottom is None:
        logger.error("throat chamfer outer ring collapsed on bottom")
        return None
    inner_top = top_r
    outer_top = _offset(top_r, tip * width)
    if outer_top is None:
        logger.error("throat chamfer outer ring collapsed on top")
        return None

    # --- build vertices: 4 rings × samples points ---
    verts = np.concatenate([
        np.column_stack([outer_bottom, np.full(samples, base_z)]),
        np.column_stack([inner_bottom, np.full(samples, base_z)]),
        np.column_stack([outer_top,    np.full(samples, top_z)]),
        np.column_stack([inner_top,    np.full(samples, top_z)]),
    ], axis=0)

    O_B, I_B = 0 * samples, 1 * samples
    O_T, I_T = 2 * samples, 3 * samples

    def _quad_strip(lo, hi):
        n = len(lo)
        tris = []
        for i in range(n):
            j = (i + 1) % n
            tris.append([lo[i], hi[i], lo[j]])
            tris.append([lo[j], hi[i], hi[j]])
        return np.array(tris)

    faces = []

    # inner wall (bottom → top, along horn contour)
    faces.append(_quad_strip(
        list(range(I_B, I_B + samples)),
        list(range(I_T, I_T + samples))))

    # outer wall (reverse winding for outward normals)
    faces.append(_quad_strip(
        list(range(O_B, O_B + samples)),
        list(range(O_T, O_T + samples)))[:, ::-1])

    # bottom cap (annular ring)
    for i in range(samples):
        j = (i + 1) % samples
        faces.append([[O_B + i, I_B + j, O_B + j],
                      [O_B + i, I_B + i, I_B + j]])

    # top cap (annular ring — only if non-degenerate)
    if not np.allclose(outer_top, inner_top):
        for i in range(samples):
            j = (i + 1) % samples
            faces.append([[O_T + i, O_T + j, I_T + j],
                          [O_T + i, I_T + j, I_T + i]])

    faces_arr = np.concatenate(faces, axis=0)

    chamfer = trimesh.Trimesh(vertices=verts, faces=faces_arr, process=True)
    chamfer.merge_vertices()
    chamfer.update_faces(chamfer.nondegenerate_faces())
    chamfer.remove_unreferenced_vertices()
    chamfer.fix_normals()

    if not chamfer.is_watertight:
        logger.error("Throat chamfer loft is not watertight")
        return None

    if output_path:
        chamfer.export(output_path)

    return chamfer


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    m = generate_flange(
        throat_R=INNER_DIAM / 2,
        flange_R=OUTER_DIAM / 2,
        thickness=THICKNESS,
        bolt_R=BOLT_RADIUS,
        bolt_n=BOLT_COUNT,
        bolt_d=BOLT_DIAM,
    )
    if m:
        print(f"WT:{m.is_watertight} B:{m.body_count} V:{m.volume:.0f}")
