"""
Parametric Rectangular Flange.

Supports both circular outer (disc) and rectangular outer (plate).
Inner hole is always rectangular.
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
    bolt_count: int = 4,
    bolt_diam: float = 3.5,
    outer_type: str = "rectangular",
    outer_w: float | None = None,
    outer_h: float | None = None,
    output_path: str | None = "io/rect_flange.stl",
) -> trimesh.Trimesh | None:
    """
    Rectangular-hole flange.

    outer_type = "circular"   → circular disc outer, bolts on a circle
    outer_type = "rectangular" → rectangular plate outer, bolts at corners
    """
    # ---- Outer body ----------------------------------------------------
    if outer_type == "rectangular":
        outer_w_val = outer_w if outer_w is not None else inner_w + 20
        outer_h_val = outer_h if outer_h is not None else inner_h + 20
        outer = creation.box(
            extents=[outer_w_val, outer_h_val, thickness],
            transform=np.array([
                [1, 0, 0, 0],
                [0, 1, 0, 0],
                [0, 0, 1, thickness / 2],
                [0, 0, 0, 1],
            ]),
        )
    else:
        outer = creation.cylinder(
            radius=outer_diam / 2.0,
            height=thickness,
            sections=80,
            transform=np.array([
                [1, 0, 0, 0],
                [0, 1, 0, 0],
                [0, 0, 1, thickness / 2],
                [0, 0, 0, 1],
            ]),
        )

    # ---- Rectangular centre hole ---------------------------------------
    centre_hole = creation.box(
        extents=[inner_w, inner_h, thickness * 2],
    )

    # ---- Bolt holes ----------------------------------------------------
    bolt_holes = []
    if outer_type == "rectangular":
        # Bolts at the 4 corners (10mm inset from outer edge)
        hw = outer_w_val / 2 - 10; hh = outer_h_val / 2 - 10
        for x, y in [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]:
            bh = creation.cylinder(
                radius=bolt_diam / 2.0,
                height=thickness * 2,
                sections=16,
                transform=np.array([
                    [1, 0, 0, x],
                    [0, 1, 0, y],
                    [0, 0, 1, 0],
                    [0, 0, 0, 1],
                ]),
            )
            bolt_holes.append(bh)
    else:
        angles = np.linspace(0, 2 * np.pi, int(bolt_count), endpoint=False)
        for a in angles:
            x = bolt_radius * np.cos(a)
            y = bolt_radius * np.sin(a)
            bh = creation.cylinder(
                radius=bolt_diam / 2.0,
                height=thickness * 2,
                sections=16,
                transform=np.array([
                    [1, 0, 0, x],
                    [0, 1, 0, y],
                    [0, 0, 1, 0],
                    [0, 0, 0, 1],
                ]),
            )
            bolt_holes.append(bh)

    # ---- Boolean subtraction -------------------------------------------
    to_sub = [centre_hole] + bolt_holes
    flange = trimesh.boolean.difference([outer] + to_sub, engine="manifold")

    if flange is None:
        logger.error("Boolean operation returned None")
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
