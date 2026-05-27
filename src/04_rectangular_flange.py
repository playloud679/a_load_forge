"""
Parametric Flange — Circular outer, rectangular inner hole.

Outer: disc with diameter *outer_diam*
Inner: rectangular hole *inner_w* × *inner_h*
Bolts: N holes on a bolt circle of radius *bolt_radius*
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
    output_path: str | None = "io/rect_flange.stl",
) -> trimesh.Trimesh | None:
    """
    Circular flange with a centred rectangular hole and bolt holes on a circle.
    """
    # ---- 1. Outer disc ----------------------------------------------------
    disc = creation.cylinder(
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

    # ---- 2. Rectangular centre hole --------------------------------------
    centre_hole = creation.box(
        extents=[inner_w, inner_h, thickness * 2],
    )

    # ---- 3. Bolt holes on a circle ---------------------------------------
    bolt_holes = []
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

    # ---- 4. Boolean subtraction -------------------------------------------
    to_sub = [centre_hole] + bolt_holes
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
    m = generate_rectangular_flange(
        outer_diam=70, inner_w=20, inner_h=10,
        thickness=6, bolt_radius=26, bolt_count=4, bolt_diam=3.5,
    )
    if m:
        print(f"WT:{m.is_watertight} B:{m.body_count} V:{m.volume:.0f}")
