"""
Parametric Circular Flange Generator.

Parameters:
  outer_diam  — outer diameter of the flange
  inner_diam  — centre hole diameter (sound path)
  thickness   — flange height (Z)
  bolt_radius — radius of the bolt hole circle
  bolt_count  — number of bolt holes
  bolt_diam   — diameter of each bolt hole

Outputs a watertight STL.
"""

import numpy as np
import trimesh
from trimesh import creation

OUTER_DIAM   = 60.0
INNER_DIAM   = 29.0
THICKNESS    = 6.0
BOLT_RADIUS  = 22.0      # centre of bolt holes from origin
BOLT_COUNT   = 4
BOLT_DIAM    = 3.5

OUTPUT       = "io/flange.stl"


def generate_flange(
    outer_diam:  float = OUTER_DIAM,
    inner_diam:  float = INNER_DIAM,
    thickness:   float = THICKNESS,
    bolt_radius: float = BOLT_RADIUS,
    bolt_count:  int   = BOLT_COUNT,
    bolt_diam:   float = BOLT_DIAM,
    output_path: str  | None = OUTPUT,
):
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

    # ---- 2. Centre hole ---------------------------------------------------
    centre_hole = creation.cylinder(
        radius=inner_diam / 2.0,
        height=thickness * 2,
        sections=64,
    )

    # ---- 3. Bolt holes ----------------------------------------------------
    bolt_holes = []
    angles = np.linspace(0, 2 * np.pi, bolt_count, endpoint=False)
    for a in angles:
        x = bolt_radius * np.cos(a)
        y = bolt_radius * np.sin(a)
        bh = creation.cylinder(
            radius=bolt_diam / 2.0,
            height=thickness * 2,
            sections=32,
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

    flange.remove_unreferenced_vertices()
    flange.update_faces(flange.nondegenerate_faces())
    flange.fix_normals()

    if output_path:
        flange.export(output_path)
        print(f"Exported: {output_path}")
        print(f"  Outer:   Ø{outer_diam:.0f} mm")
        print(f"  Inner:   Ø{inner_diam:.0f} mm")
        print(f"  Thick:   {thickness:.0f} mm")
        print(f"  Bolts:   {bolt_count} × Ø{bolt_diam:.1f} @ R{bolt_radius:.0f} mm")
        print(f"  Tris:    {len(flange.faces)}")
        print(f"  WT:      {flange.is_watertight}")

    return flange


if __name__ == "__main__":
    generate_flange()
