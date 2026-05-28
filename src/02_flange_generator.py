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
    output_path: str | None = "io/flange.stl",
) -> trimesh.Trimesh | None:
    """
    Circular flange — CSG boolean difference.

    The flange sits with its TOP face at *offset* and grows downward (-Z).
    Inner hole radius = *throat_R* (matches the horn throat).
    Bolt holes are genuine cutouts via trimesh boolean operations.
    """
    zt = offset
    zb = offset - thickness
    disc_center_z = zb + thickness / 2.0

    # ── Outer disc ──────────────────────────────────────────────────────
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
        a = 2 * np.pi * k / bolt_n
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
