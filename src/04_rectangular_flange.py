"""
Parametric Rectangular Flange Generator — using trimesh + manifold3d.

For rectangular horn throats.  Uses proper boolean subtraction.
"""

import logging

import numpy as np
import trimesh
from trimesh import creation

logger = logging.getLogger(__name__)


def generate_rectangular_flange(
    outer_w: float = 60.0,
    outer_h: float = 60.0,
    inner_w: float = 20.0,
    inner_h: float = 10.0,
    thickness: float = 6.0,
    bolt_inset: float = 5.0,
    bolt_diam: float = 3.5,
    output_path: str | None = "io/rect_flange.stl",
) -> trimesh.Trimesh | None:
    """
    Rectangular flange with a centred rectangular hole and bolt holes.

    Uses trimesh with manifold3d engine for robust CSG.
    """
    # ---- 1. Outer box -----------------------------------------------------
    base = creation.box(
        extents=[outer_w, outer_h, thickness],
        transform=np.array([
            [1, 0, 0, 0],
            [0, 1, 0, 0],
            [0, 0, 1, thickness / 2],
            [0, 0, 0, 1],
        ]),
    )

    # ---- 2. Centre hole ---------------------------------------------------
    centre_hole = creation.box(
        extents=[inner_w, inner_h, thickness * 2],
    )

    # ---- 3. Bolt holes ----------------------------------------------------
    bolt_r = bolt_diam / 2
    bx = outer_w / 2 - bolt_inset
    by = outer_h / 2 - bolt_inset

    bolt_holes = []
    for cx, cy in [(-bx, -by), (bx, -by), (bx, by), (-bx, by)]:
        bh = creation.cylinder(
            radius=bolt_r,
            height=thickness * 2,
            sections=16,
            transform=np.array([
                [1, 0, 0, cx],
                [0, 1, 0, cy],
                [0, 0, 1, 0],
                [0, 0, 0, 1],
            ]),
        )
        bolt_holes.append(bh)

    # ---- 4. Boolean subtraction -------------------------------------------
    to_sub = [centre_hole] + bolt_holes
    flange = trimesh.boolean.difference([base] + to_sub, engine="manifold")

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
        outer_w=60, outer_h=50,
        inner_w=20, inner_h=10,
        thickness=6, bolt_inset=5, bolt_diam=3.5,
    )
    if m:
        print(f"WT:{m.is_watertight} B:{m.body_count} V:{m.volume:.0f}")
        print(f"X:[{m.bounds[0,0]:.1f},{m.bounds[1,0]:.1f}]  Y:[{m.bounds[0,1]:.1f},{m.bounds[1,1]:.1f}]  Z:[{m.bounds[0,2]:.1f},{m.bounds[1,2]:.1f}]")
