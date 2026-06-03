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
