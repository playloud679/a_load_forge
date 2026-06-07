"""
Parametric Rectangular / Elliptical-Hole Flange.

Supports both circular outer (disc) and rectangular outer (plate).
Inner hole can be rectangular or elliptical.
Bolts: on a circle (circular outer) or at corners (rectangular outer).
"""

import logging
import numpy as np
import trimesh
from trimesh import creation

logger = logging.getLogger(__name__)


def generate_rectangular_flange(
    outer_diam: float = 70.0,
    inner_w: float = 20.0,
    inner_h: float = 10.0,
    thickness: float = 6.0,
    bolt_radius: float = 26.0,
    bolt_inset: float = 10.0,
    bolt_count: int = 4,
    bolt_diam: float = 3.5,
    outer_type: str = "rectangular",
    outer_w: float | None = None,
    outer_h: float | None = None,
    offset: float = 0.0,
    output_path: str | None = None,
    bolt_phase: float = 0.0,
    inner_type: str = "rectangular",
) -> trimesh.Trimesh | None:
    """
    Rectangular/elliptical-hole flange with safety clamps and Z-offset.

    outer_type = "circular"    → circular disc outer, bolts on a circle
    outer_type = "rectangular" → rectangular plate outer, bolts at corners
    outer_type = "elliptical"  → elliptical-offset outer (ring follows the hole),
                                 bolts on the mid-ring ellipse
    inner_type = "rectangular" | "elliptical"
    offset = Z position of the flange bottom face.
    """
    if inner_type not in {"rectangular", "elliptical"}:
        raise ValueError("inner_type must be 'rectangular' or 'elliptical'")
    if outer_type not in {"rectangular", "circular", "elliptical"}:
        raise ValueError("outer_type must be 'rectangular', 'circular' or 'elliptical'")

    zb = offset
    center_z = zb + thickness / 2.0
    _z_xform = np.array([
        [1, 0, 0, 0],
        [0, 1, 0, 0],
        [0, 0, 1, center_z],
        [0, 0, 0, 1],
    ])
    safe_margin = (bolt_inset * 2) + bolt_diam + 10.0

    # ---- Outer body ----------------------------------------------------
    if outer_type == "rectangular":
        outer_w_val = outer_w if outer_w is not None else inner_w + safe_margin
        outer_h_val = outer_h if outer_h is not None else inner_h + safe_margin
        outer = creation.box(
            extents=[outer_w_val, outer_h_val, thickness],
            transform=_z_xform,
        )
    elif outer_type == "elliptical":
        # Elliptical-offset outer: the ring follows the hole's ellipse, offset
        # outward by a constant ring width (caller passes outer_w/h = inner_w/h
        # + 2·ring). Built as a unit cylinder scaled to the outer semi-axes.
        outer_w_val = outer_w if outer_w is not None else inner_w + safe_margin
        outer_h_val = outer_h if outer_h is not None else inner_h + safe_margin
        outer = creation.cylinder(radius=1.0, height=thickness, sections=128)
        outer.apply_scale([outer_w_val / 2.0, outer_h_val / 2.0, 1.0])
        outer.apply_translation([0.0, 0.0, center_z])
    else:
        min_diam = np.sqrt(inner_w**2 + inner_h**2) + (bolt_diam * 4) + 10.0
        actual_diam = max(outer_diam, min_diam)
        outer_w_val = outer_h_val = actual_diam
        outer = creation.cylinder(
            radius=actual_diam / 2.0,
            height=thickness,
            sections=80,
            transform=_z_xform,
        )

    # ---- Centre hole ---------------------------------------------------
    if inner_type == "elliptical":
        centre_hole = creation.cylinder(
            radius=1.0,
            height=thickness * 3,
            sections=128,
        )
        centre_hole.apply_scale([inner_w / 2.0, inner_h / 2.0, 1.0])
        centre_hole.apply_translation([0.0, 0.0, center_z])
    else:
        centre_hole = creation.box(
            extents=[inner_w, inner_h, thickness * 3],
            transform=np.array([
                [1, 0, 0, 0],
                [0, 1, 0, 0],
                [0, 0, 1, center_z],
                [0, 0, 0, 1],
            ]),
        )

    # ---- Bolt holes ----------------------------------------------------
    bolt_holes = []

    if outer_type == "rectangular":
        hw = (outer_w_val / 2.0) - bolt_inset
        hh = (outer_h_val / 2.0) - bolt_inset
        min_x = (inner_w / 2.0) + (bolt_diam / 2.0) + 1.0
        min_y = (inner_h / 2.0) + (bolt_diam / 2.0) + 1.0
        hw = max(hw, min_x)
        hh = max(hh, min_y)
        for x, y in [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]:
            bh = creation.cylinder(
                radius=bolt_diam / 2.0,
                height=thickness * 3,
                sections=16,
                transform=np.array([
                    [1, 0, 0, x],
                    [0, 1, 0, y],
                    [0, 0, 1, center_z],
                    [0, 0, 0, 1],
                ]),
            )
            bolt_holes.append(bh)
    elif outer_type == "elliptical":
        # Bolts ride the mid-ring ellipse (halfway between hole and outer edge),
        # so they stay centred in the elliptical wall for any aspect ratio.
        bx = (inner_w / 2.0 + outer_w_val / 2.0) / 2.0
        by = (inner_h / 2.0 + outer_h_val / 2.0) / 2.0
        angles = np.linspace(0, 2 * np.pi, int(bolt_count), endpoint=False)
        for a in angles:
            x = bx * np.cos(a + bolt_phase)
            y = by * np.sin(a + bolt_phase)
            bh = creation.cylinder(
                radius=bolt_diam / 2.0,
                height=thickness * 3,
                sections=16,
                transform=np.array([
                    [1, 0, 0, x],
                    [0, 1, 0, y],
                    [0, 0, 1, center_z],
                    [0, 0, 0, 1],
                ]),
            )
            bolt_holes.append(bh)
    else:
        safe_radius = (np.sqrt(inner_w**2 + inner_h**2) / 2.0) + (bolt_diam / 2.0) + 2.0
        actual_bolt_radius = max(bolt_radius, safe_radius)
        angles = np.linspace(0, 2 * np.pi, int(bolt_count), endpoint=False)
        for a in angles:
            x = actual_bolt_radius * np.cos(a + bolt_phase)
            y = actual_bolt_radius * np.sin(a + bolt_phase)
            bh = creation.cylinder(
                radius=bolt_diam / 2.0,
                height=thickness * 3,
                sections=16,
                transform=np.array([
                    [1, 0, 0, x],
                    [0, 1, 0, y],
                    [0, 0, 1, center_z],
                    [0, 0, 0, 1],
                ]),
            )
            bolt_holes.append(bh)

    # ---- Boolean subtraction -------------------------------------------
    to_sub = [centre_hole] + bolt_holes
    flange = trimesh.boolean.difference([outer] + to_sub, engine="manifold")

    if flange is None or flange.is_empty:
        logger.error("Boolean operation failed — check dimensions")
        return None

    flange.remove_unreferenced_vertices()
    flange.update_faces(flange.nondegenerate_faces())
    flange.fix_normals()

    if output_path:
        flange.export(output_path)
        logger.info("Exported: %s  (%d triangles, WT=%s)",
                    output_path, len(flange.faces), flange.is_watertight)

    return flange


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for ot in ["circular", "rectangular"]:
        m = generate_rectangular_flange(
            outer_diam=70, inner_w=20, inner_h=10,
            thickness=6, bolt_radius=26, bolt_count=4, bolt_diam=3.5,
            outer_type=ot,
        )
        if m:
            print(f"{ot}: WT={m.is_watertight} V={m.volume:.0f}")
