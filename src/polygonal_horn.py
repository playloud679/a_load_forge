"""
Polygonal horn — regular N-gon cross-section with any expansion profile.

The cross-section at every Z slice is a regular N-gon whose area equals
the area of the equivalent circle derived from the chosen profile:

    A_polygon = A_circle = π · r_eq²
    circumradius  R = r_eq · sqrt(2π / (N · sin(2π/N)))
    outer offset  R_outer = R + t / cos(π/N)    (uniform face-normal thickness)

Input r_eq is the area-equivalent circular radius returned by any profile
function (get_tractrix, get_lecleach, get_iwata, or computed for Exponential).
"""

import logging
import sys
from pathlib import Path

import numpy as np
from stl import mesh

_src = str(Path(__file__).resolve().parent)
if _src not in sys.path:
    sys.path.insert(0, _src)

import _utils

logger = logging.getLogger(__name__)

# area-equivalent circle radius → N-gon circumradius
def _r_to_circumradius(r_eq: np.ndarray, n: int) -> np.ndarray:
    return r_eq * np.sqrt(2.0 * np.pi / (n * np.sin(2.0 * np.pi / n)))


def generate_polygonal_3d_mesh(
    z: np.ndarray,
    r_eq: np.ndarray,
    n_sides: int,
    thickness: float = 4.0,
    output_path: str | None = None,
) -> mesh.Mesh:
    """
    Build a watertight N-gon horn STL from (z, r_eq) profile.

    z, r_eq  — profile arrays (r_eq = area-equivalent circular radius)
    n_sides  — number of polygon sides (3–12)
    thickness — uniform wall thickness applied along face normals
    """
    nz = len(z)
    if n_sides < 3:
        raise ValueError("n_sides must be >= 3")

    # Inner circumradii
    R_i = _r_to_circumradius(r_eq, n_sides)

    # Profile normals in the (z, R) plane
    nml = _utils.compute_profile_normals(z, R_i, flip_if_negative=True)
    n_z = nml[:, 0]
    n_r = nml[:, 1]

    # Outer circumradii and z — uniform thickness along the face normal
    # Moving each face outward by t → each vertex moves t / cos(π/N) in the
    # circumradius direction (standard polygon offset geometry).
    cos_pn = np.cos(np.pi / n_sides)
    R_o = R_i + thickness / cos_pn * n_r
    z_o = z + thickness * n_z
    z_o = np.clip(z_o, z[0], z[-1])
    z_o[0]  = z[0]
    z_o[-1] = z[-1]

    # Vertex angles (rotate by π/2 so flat face faces front for even N)
    theta = np.linspace(0, 2.0 * np.pi, n_sides, endpoint=False) + np.pi / 2.0

    def corners(R, zv):
        return [[R * np.cos(th), R * np.sin(th), zv] for th in theta]

    # Triangle budget
    #   inner walls: N × (nz-1) quads = 2·N·(nz-1) tris
    #   outer walls: same
    #   bottom frame: N quads = 2·N tris
    #   top frame:    same
    n_tri = 4 * n_sides * (nz - 1) + 4 * n_sides
    data = np.zeros(n_tri, dtype=mesh.Mesh.dtype)
    tri = 0

    def emit(a, b, c):
        nonlocal tri
        data["vectors"][tri] = [a, b, c]
        tri += 1

    # Walls
    for i in range(nz - 1):
        ci  = corners(R_i[i],   z[i])
        ci1 = corners(R_i[i+1], z[i+1])
        co  = corners(R_o[i],   z_o[i])
        co1 = corners(R_o[i+1], z_o[i+1])

        for k in range(n_sides):
            kk = (k + 1) % n_sides
            # Inner wall — normals inward → reversed winding
            emit(ci[k],  ci1[k],  ci[kk])
            emit(ci[kk], ci1[k],  ci1[kk])
            # Outer wall — normals outward → forward winding
            emit(co[k],  co[kk],  co1[k])
            emit(co[kk], co1[kk], co1[k])

    # Bottom frame (−Z outward normal)
    ci_b = corners(R_i[0], z[0])
    co_b = corners(R_o[0], z_o[0])
    for k in range(n_sides):
        kk = (k + 1) % n_sides
        emit(ci_b[k],  co_b[k],  ci_b[kk])
        emit(co_b[k],  co_b[kk], ci_b[kk])

    # Top frame (+Z outward normal)
    ci_t = corners(R_i[-1], z[-1])
    co_t = corners(R_o[-1], z_o[-1])
    for k in range(n_sides):
        kk = (k + 1) % n_sides
        emit(ci_t[k],  ci_t[kk], co_t[k])
        emit(ci_t[kk], co_t[kk], co_t[k])

    assert tri == n_tri, f"Triangle count mismatch: {tri} vs {n_tri}"

    m_obj = mesh.Mesh(data)
    _utils.ensure_positive_volume(m_obj)

    if output_path:
        m_obj.save(output_path)
        logger.info("Exported: %s  (%d tris, %d-gon)", output_path, n_tri, n_sides)

    return m_obj


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    from profile_generator import get_tractrix

    z, r = get_tractrix(20, 200, 300)
    for n in [3, 4, 6, 8, 12]:
        generate_polygonal_3d_mesh(z, r, n, thickness=4.0,
                                   output_path=f"io/poly_{n}.stl")
