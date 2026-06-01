"""
STL slicer — cut a horn mesh lengthwise or into radial petals.

Uses trimesh for plane slicing with capping.
"""

import numpy as np
import trimesh


def slice_at_z(mesh: trimesh.Trimesh, z: float, keep: str = "below"
               ) -> trimesh.Trimesh | None:
    """
    Cut *mesh* with a plane at Z=*z*, keep one side.

    Parameters
    ----------
    mesh : trimesh.Trimesh
    z : float
        Z-coordinate of the cutting plane.
    keep : "below" | "above"
        Which side to keep.

    Returns a single watertight Trimesh (capped) or None if empty.
    """
    plane_normal = np.array([0.0, 0.0, 1.0])
    plane_origin = np.array([0.0, 0.0, z])
    if keep == "above":
        plane_normal = -plane_normal
    result = mesh.slice_plane(plane_origin, plane_normal, cap=True)
    if result is None or result.is_empty:
        return None
    return result


def slice_into_segments(mesh: trimesh.Trimesh, n: int
                        ) -> list[trimesh.Trimesh]:
    """
    Cut *mesh* into *n* axial segments of equal Z-height.

    Returns a list of *n* watertight Trimesh objects (capped at both cut ends).
    """
    z_min = mesh.bounds[0, 2]
    z_max = mesh.bounds[1, 2]
    dz = (z_max - z_min) / n

    segments: list[trimesh.Trimesh] = []
    lo = z_min
    for i in range(n):
        hi = lo + dz
        seg = mesh.slice_plane([0.0, 0.0, lo], [0.0, 0.0, 1.0], cap=True)
        if seg is not None and not seg.is_empty:
            seg = seg.slice_plane([0.0, 0.0, hi], [0.0, 0.0, -1.0], cap=True)
            if seg is not None and not seg.is_empty:
                segments.append(seg)
        lo = hi
    return segments


def slice_into_petals(mesh: trimesh.Trimesh, n: int
                      ) -> list[trimesh.Trimesh]:
    """
    Cut *mesh* into *n* radial petals (like an orange).

    Each cut is a vertical plane through the Z-axis, rotated by k·π/n.

    Returns a list of *n* watertight Trimesh objects.
    """
    petals: list[trimesh.Trimesh] = []
    for i in range(n):
        angle0 = i * 2 * np.pi / n
        angle1 = (i + 1) * 2 * np.pi / n
        mid = (angle0 + angle1) / 2.0

        normal0 = np.array([np.sin(angle0), -np.cos(angle0), 0.0])
        normal1 = np.array([-np.sin(angle1), np.cos(angle1), 0.0])

        petal = mesh.slice_plane([0.0, 0.0, 0.0], normal0, cap=True)
        if petal is None or petal.is_empty:
            continue
        petal = petal.slice_plane([0.0, 0.0, 0.0], normal1, cap=True)
        if petal is None or petal.is_empty:
            continue
        petals.append(petal)

    return petals
