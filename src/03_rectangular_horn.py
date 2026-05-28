"""
Rectangular horn profile + dedicated 3-D lofting engine.

Area-preserving rectangular horn: the user defines the Width expansion W(z);
Height H(z) = S(z) / W(z) so the cross-sectional area follows an exponential
expansion derived from the cutoff frequency Fc.
"""

import logging
import sys
from pathlib import Path

import numpy as np
from stl import mesh

_src = str(Path(__file__).resolve().parent)
if _src not in sys.path:
    sys.path.insert(0, _src)

from _constants import SOUND_SPEED
import _utils

logger = logging.getLogger(__name__)


# ======================================================================
#  2-D profile  —  returns (z, w, h)
# ======================================================================

def get_rectangular_exponential(
    throat_w: float,
    throat_h: float,
    mouth_w: float,
    fc: float,
    n: int = 300,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Rectangular horn — exponential area expansion, exponential width.

    S(z) = St · exp(m · z)          (m = 4π·fc/c)
    W(z) = Wt · exp(m/2 · z)       (exponential, matched to area rate)
    H(z) = Ht · exp(m/2 · z)       (same rate → aspect ratio preserved)

    The mouth width is *mouth_w*.  The length L is solved so that
    W(L) = mouth_w.  Then H(L) is determined.

    Returns (z_array, w_array, h_array).
    """
    St = throat_w * throat_h
    m  = 4.0 * np.pi * fc / SOUND_SPEED

    if mouth_w <= throat_w:
        raise ValueError("mouth_w must be > throat_w")

    # Length such that W(L) = mouth_w = throat_w · exp(m/2 · L)
    L = 2.0 / m * np.log(mouth_w / throat_w)

    z = np.linspace(0, L, n)

    W = throat_w * np.exp(m / 2.0 * z)
    H = throat_h * np.exp(m / 2.0 * z)

    return z, W, H


# ======================================================================
#  3-D rectangular lofting engine
# ======================================================================

def generate_rectangular_3d_mesh(
    z: np.ndarray,
    w: np.ndarray,
    h: np.ndarray,
    thickness: float = 4.0,
    output_path: str | None = None,
) -> mesh.Mesh:
    """
    Build a watertight rectangular horn STL from (z, w, h) profiles.

    For each Z slice:
        inner corners:  (±w/2, ±h/2, z)
        outer corners:  (±w_outer/2, ±h_outer/2, z)

    The four walls (inner + outer), the bottom frame, and the top
    frame are triangulated manually — no CSG booleans required.
    """
    n = len(z)

    # ---- 1. Normals for the W-Z and H-Z profiles --------------------------
    nw = _utils.compute_profile_normals(z, w, flip_if_negative=True)
    nh = _utils.compute_profile_normals(z, h, flip_if_negative=True)

    # ---- 2. Offset profiles -----------------------------------------------
    # Width extends in ±X → total offset = 2× thickness × Nx
    # Height extends in ±Y → total offset = 2× thickness × Ny
    w_o = w + 2.0 * thickness * nw[:, 1]
    h_o = h + 2.0 * thickness * nh[:, 1]

    # Z offset: use the mean of the two Z-normal components
    z_o = z + thickness * (nw[:, 0] + nh[:, 0]) / 2.0

    # ---- 3. Triangle budget -----------------------------------------------
    # 4 inner walls + 4 outer walls = 8 walls × (n-1) quads × 2 tris = 16·(n-1)
    # bottom frame + top frame = 2 frames × 4 sides × 2 tris = 16
    n_tri = 16 * (n - 1) + 16
    data = np.zeros(n_tri, dtype=mesh.Mesh.dtype)
    tri = 0

    def emit(a, b, c):
        nonlocal tri
        data["vectors"][tri] = [a, b, c]
        tri += 1

    # Helper: build the 4 corners of a rectangular slice
    def corners(w_sz, h_sz, z_sz):
        hw = w_sz / 2.0
        hh = h_sz / 2.0
        return [
            [-hw, -hh, z_sz],   # 0  bottom-left
            [ hw, -hh, z_sz],   # 1  bottom-right
            [ hw,  hh, z_sz],   # 2  top-right
            [-hw,  hh, z_sz],   # 3  top-left
        ]

    # ---- 4. Walls ---------------------------------------------------------
    for i in range(n - 1):
        ci = corners(w[i], h[i], z[i])
        ci1 = corners(w[i+1], h[i+1], z[i+1])
        co = corners(w_o[i], h_o[i], z_o[i])
        co1 = corners(w_o[i+1], h_o[i+1], z_o[i+1])

        # Inner walls (4 sides, normals point inward → reverse winding)
        # Side 0→1  (bottom, -Y)      inner wall
        emit(ci[0], ci1[0], ci[1])
        emit(ci[1], ci1[0], ci1[1])
        # Side 1→2  (right, +X)
        emit(ci[1], ci1[1], ci[2])
        emit(ci[2], ci1[1], ci1[2])
        # Side 2→3  (top, +Y)
        emit(ci[2], ci1[2], ci[3])
        emit(ci[3], ci1[2], ci1[3])
        # Side 3→0  (left, -X)
        emit(ci[3], ci1[3], ci[0])
        emit(ci[0], ci1[3], ci1[0])

        # Outer walls (4 sides, normals point outward → forward winding)
        emit(co[0], co[1], co1[0])
        emit(co[1], co1[1], co1[0])
        emit(co[1], co[2], co1[1])
        emit(co[2], co1[2], co1[1])
        emit(co[2], co[3], co1[2])
        emit(co[3], co1[3], co1[2])
        emit(co[3], co[0], co1[3])
        emit(co[0], co1[0], co1[3])

    # ---- 5. Bottom frame --------------------------------------------------
    cib = corners(w[0], h[0], z[0])
    cob = corners(w_o[0], h_o[0], z_o[0])
    # Bottom face (outward normal = −Z)
    emit(cib[0], cob[0], cib[1])
    emit(cob[0], cob[1], cib[1])
    emit(cib[1], cob[1], cib[2])
    emit(cob[1], cob[2], cib[2])
    emit(cib[2], cob[2], cib[3])
    emit(cob[2], cob[3], cib[3])
    emit(cib[3], cob[3], cib[0])
    emit(cob[3], cob[0], cib[0])

    # ---- 6. Top frame -----------------------------------------------------
    cit = corners(w[-1], h[-1], z[-1])
    cot = corners(w_o[-1], h_o[-1], z_o[-1])
    # Top face (outward normal = +Z)
    emit(cit[0], cit[1], cot[0])
    emit(cit[1], cot[1], cot[0])
    emit(cit[1], cit[2], cot[1])
    emit(cit[2], cot[2], cot[1])
    emit(cit[2], cit[3], cot[2])
    emit(cit[3], cot[3], cot[2])
    emit(cit[3], cit[0], cot[3])
    emit(cit[0], cot[0], cot[3])

    assert tri == n_tri, f"Triangle mismatch {tri} vs {n_tri}"

    m_obj = mesh.Mesh(data)

    _utils.ensure_positive_volume(m_obj)

    if output_path:
        m_obj.save(output_path)
        logger.info("Exported: %s  (%d triangles)", output_path, n_tri)

    return m_obj


# ======================================================================
#  Standalone test
# ======================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    z, w, h = get_rectangular_exponential(
        throat_w=20, throat_h=10, mouth_w=200, fc=600, n=300,
    )
    logger.info("Profile: %d pts,  L=%.1f mm,  mouth W=%.0f H=%.0f",
                len(z), z[-1], w[-1], h[-1])

    generate_rectangular_3d_mesh(z, w, h, thickness=4.0,
                                  output_path="io/rectangular_horn.stl")
