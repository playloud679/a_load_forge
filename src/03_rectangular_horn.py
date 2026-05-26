"""
Rectangular horn profile + dedicated 3-D lofting engine.

Area-preserving rectangular horn: the user defines the Width expansion W(z);
Height H(z) = S(z) / W(z) so the cross-sectional area follows an exponential
expansion derived from the cutoff frequency Fc.
"""

import logging

import numpy as np
from stl import mesh

logger = logging.getLogger(__name__)
SOUND_SPEED = 343_000


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
    Area-preserving rectangular horn.

    The throat area  S_t = throat_w · throat_h  expands exponentially
    with rate m derived from the cutoff frequency Fc.
    The Width W(z) flares linearly from *throat_w* to *mouth_w*.
    The Height H(z) = S(z) / W(z) preserves the acoustic impedance.

    Returns (z_array, w_array, h_array).
    """
    St = throat_w * throat_h
    m  = 4.0 * np.pi * fc / SOUND_SPEED

    # Maximum length: stop when area has expanded by a reasonable factor
    L = (1.0 / m) * np.log(400.0) if m > 0 else 200.0  # exp(m·L) = 400 → large mouth

    z = np.linspace(0, L, n)

    # Area expansion
    S = St * np.exp(m * z)

    # Width: linear flare
    W = np.linspace(throat_w, mouth_w, n)

    # Height: area / width
    H = S / W

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
    def _normals(arr: np.ndarray) -> np.ndarray:
        dz = np.gradient(z)
        da = np.gradient(arr)
        tan = np.column_stack([dz, da])
        tn = np.sqrt(tan[:, 0] ** 2 + tan[:, 1] ** 2)

        # Boundary protection
        tiny = tn < 1e-10
        if tiny.any():
            valid = np.where(~tiny)[0]
            if len(valid):
                for idx in np.where(tiny)[0]:
                    nbr = valid[np.argmin(np.abs(valid - idx))]
                    dz[idx], da[idx] = dz[nbr], da[nbr]
                    tn[idx] = tn[nbr]
        tn[tn < 1e-15] = 1.0
        tan /= tn.reshape(-1, 1)

        nml = np.column_stack([-tan[:, 1], tan[:, 0]])
        if nml[0, 1] < 0:
            nml = -nml
        return nml

    nw = _normals(w)   # normals for width  (X-Z plane)
    nh = _normals(h)   # normals for height (Y-Z plane)

    # ---- 2. Offset profiles -----------------------------------------------
    # Width extends in ±X → total offset = 2× thickness × Nx
    # Height extends in ±Y → total offset = 2× thickness × Ny
    w_o = w + 2.0 * thickness * nw[:, 1]
    h_o = h + 2.0 * thickness * nh[:, 1]

    # Z offset: use the mean of the two Z-normal components
    z_o = z + thickness * (nw[:, 0] + nh[:, 0]) / 2.0
    shift = z_o.min()
    if shift < 0:
        z_o -= shift

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

    # Z-alignment
    z_min = m_obj.vectors.reshape(-1, 3)[:, 2].min()
    if abs(z_min) > 1e-4:
        m_obj.vectors[:, :, 2] -= z_min

    # Flip normals if volume is negative
    try:
        vol = m_obj.get_mass_properties()[0]
        if vol < 0:
            m_obj.vectors = m_obj.vectors[:, [0, 2, 1]]
    except Exception:
        pass

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
