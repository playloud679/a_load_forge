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
) -> trimesh.Trimesh | None:
    """Generate a standard bolt-on compression-driver mounting flange.

    ``driver_type`` selects an entry from ``DRIVER_FLANGE_SPECS``. The centre
    bore is the nominal driver throat plus ``throat_clearance``; all mounting
    dimensions remain fixed by the selected industrial pattern.
    """
    if throat_clearance < 0.0:
        raise ValueError("throat_clearance must be non-negative")
    spec = DRIVER_FLANGE_SPECS[driver_type]
    return generate_flange(
        throat_R=(spec.throat_diam + throat_clearance) / 2.0,
        flange_R=spec.outer_diam / 2.0,
        thickness=thickness,
        bolt_R=spec.pcd / 2.0,
        bolt_n=spec.bolt_count,
        bolt_d=spec.bolt_diam,
        offset=offset,
        seg=seg,
        output_path=output_path,
        bolt_phase=spec.bolt_phase,
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

    def _radial_extent(shape: str, R: float, w: float, h: float,
                       n: int, angle: float) -> float:
        ca, sa = abs(np.cos(angle)), abs(np.sin(angle))
        if shape == "circular":
            return R
        if shape == "elliptical":
            a, b = w / 2.0, h / 2.0
            return 1.0 / np.sqrt((ca / a) ** 2 + (sa / b) ** 2)
        if shape == "rectangular":
            return min((w / 2.0) / max(ca, 1e-12),
                       (h / 2.0) / max(sa, 1e-12))
        # Polygon vertices use phase pi/2. Intersect a ray with its boundary.
        points = _shape_points(shape, R, w, h, n)
        ray = np.array([np.cos(angle), np.sin(angle)])
        best = np.inf
        for p0, p1 in zip(points, np.roll(points, -1, axis=0)):
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
    outer_pts = _shape_points(
        outer_type, outer_R, outer_w, outer_h, outer_n_sides)
    inner_poly = _ShapelyPolygon(inner_pts)
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
        inner_limit = max(_radial_extent(
            inner_type, inner_R, inner_w, inner_h, inner_n_sides, a)
            for a in sample) + margin
        outer_limit = min(_radial_extent(
            outer_type, outer_R, outer_w, outer_h, outer_n_sides, a)
            for a in sample) - margin
        if outer_limit <= inner_limit:
            raise ValueError("not enough flange material for a fixed bolt circle")
        bolt_R = float(np.clip(bolt_R, inner_limit, outer_limit))

    for angle in angles:
        ri = _radial_extent(
            inner_type, inner_R, inner_w, inner_h, inner_n_sides, angle)
        ro = _radial_extent(
            outer_type, outer_R, outer_w, outer_h, outer_n_sides, angle)
        radius = (ri + ro) / 2.0 if bolt_mode == "auto" else bolt_R
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
