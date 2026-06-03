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


def _area_to_rect(z: np.ndarray, r: np.ndarray, throat_w: float, throat_h: float
                  ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Convert axisymmetric profile (z, r) to area-preserving rectangular (z, w, h)."""
    A = np.pi * r**2
    AR = throat_w / throat_h
    W = np.sqrt(A * AR)
    H = A / W
    return z, W, H


def get_rectangular_tractrix(
    throat_w: float, throat_h: float, mouth_w: float, n: int = 300,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Rectangular tractrix: area-preserving conversion from circular tractrix."""
    from profile_generator import get_tractrix
    throat = np.sqrt(throat_w * throat_h * 4 / np.pi)
    mouth = np.sqrt(mouth_w * throat_h * 4 / np.pi)
    z, r = get_tractrix(throat, mouth, n)
    return _area_to_rect(z, r, throat_w, throat_h)


def get_rectangular_salmon(
    throat_w: float, throat_h: float, fc: float, length: float, n: int = 300,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Rectangular Salmon: area-preserving from circular Salmon."""
    from profile_generator import get_salmon
    throat = np.sqrt(throat_w * throat_h * 4 / np.pi)
    z, r = get_salmon(throat, fc, length, n)
    return _area_to_rect(z, r, throat_w, throat_h)


# ======================================================================
#  Iwata horn — faithful rectangular dual-flare from the l'Audiophile plan
# ======================================================================
#
# Digitized from the original Iwata construction drawing published in
# l'Audiophile (for the JBL 2440 / 375 1.5" compression drivers). Unlike the
# axisymmetric "Iwata ≈ Salmon T=0.707" loading approximation, the real Iwata
# is a *rectangular* horn whose two planes expand at *different* rates:
#   • width  W: ~×15 over the length (fast — horizontal coverage)
#   • height H: ~×6.4 (slow — vertical coverage)
# so the cross-section aspect ratio grows from ~1:1 at the throat to ~2.3:1 at
# the mouth. The mouth also carries a curved roll-back lip (omitted here — it is
# a finishing edge, not part of the acoustic loading).
#
# Stations are 50 mm apart on the native plan; the first station is the
# (≈square) rectangular throat downstream of the round driver adaptor.
_IWATA_Z = np.array(
    [0, 50, 100, 150, 200, 250, 300, 350, 400, 450, 500, 550], dtype=float)
_IWATA_W = np.array(
    [50.0, 50.0, 63.2, 81.4, 100.0, 140.2, 184.7, 245.7, 335.8, 485.0, 648.0, 740.0])
_IWATA_H = np.array(
    [50.0, 52.2, 57.3, 64.7, 74.2, 86.0, 99.6, 116.5, 137.0, 171.2, 247.4, 320.0])
_IWATA_L0 = float(_IWATA_Z[-1])   # native plan length (mm)
_IWATA_W0 = float(_IWATA_W[0])    # native plan throat width (mm)


# Plan-view mouth arc: the wide-plane mouth is a circular arc of radius 692 mm
# centred on "Point R", a virtual apex on the axis ~120 mm *behind* the throat
# (692 − 572 axial). Native values; both scale with the width factor f = throat/50.
_IWATA_ARC_R0 = 692.0          # mm, mouth arc radius about point R
_IWATA_AXIAL0 = 572.0          # mm, native axial length (throat → mouth centre)


def iwata_arc_mouth(throat: float, length: float) -> tuple[float, float]:
    """
    Geometry of the Iwata's curved (plan-view) mouth, for terminating the mesh.

    Returns (radius, center_z) of a cylinder whose axis runs along the *height*
    (Y) direction: intersecting the straight rectangular loft with this solid
    cylinder rolls the wide-plane mouth back into the plan arc (r=692 native),
    while leaving the height-plane mouth flat — exactly as drawn in l'Audiophile.

        keep material where  x² + (z − center_z)² ≤ radius²

    The mouth centre (x=0) sits at z=length (furthest forward); the corners roll
    back ~107·f mm. Radius scales with the width factor f = throat/50, so the arc
    curvature follows the cross-section size independently of the chosen length.
    """
    f = throat / _IWATA_W0
    radius = _IWATA_ARC_R0 * f
    center_z = length - radius
    return radius, center_z


def get_iwata_horn(
    throat: float = 50.0, length: float = 572.0, n: int = 300,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Faithful Iwata horn (rectangular, asymmetric dual-flare) from the
    l'Audiophile plan, scaled to the requested throat size and axial length.

    The plan's normalized W(z)/H(z) proportions are preserved exactly: a
    uniform scale factor f = throat / W0 resizes the cross-section, while *length*
    stretches the axis. With the defaults (throat=50, length=572) this reproduces
    the original drawing: mouth ≈ 740 × 320 mm, throat ≈ 50 × 50 mm. The wide-plane
    mouth arc (see iwata_arc_mouth) is applied at the mesh stage, not here.

    Returns (z, w, h) — same interface as the other rectangular profiles, so it
    feeds straight into generate_rectangular_3d_mesh().
    """
    f = throat / _IWATA_W0
    t = np.linspace(0.0, 1.0, n)
    z = t * length
    w = _iwata_smooth(_IWATA_W, t) * f
    h = _iwata_smooth(_IWATA_H, t) * f
    return z, w, h


def _iwata_smooth(arr: np.ndarray, t: np.ndarray, deg: int = 3) -> np.ndarray:
    """
    Smooth, monotone curve through the hand-digitized plan stations.

    Interpolating every station (e.g. with PCHIP) faithfully reproduces the few-%
    reading noise of the scan as visible ripples on the printed wall. Instead we
    fit a low-degree polynomial in *log* space (natural for the near-exponential
    growth, keeps it positive and monotone) and anchor *both* endpoints exactly so
    the throat and mouth still match the drawing. Result: ~5× smoother wall, same
    overall shape, throat/mouth spot on.
    """
    lraw = np.polyval(np.polyfit(_IWATA_Z, np.log(arr), deg), t * _IWATA_L0)
    corr = (np.log(arr[0]) - lraw[0]) * (1.0 - t) + (np.log(arr[-1]) - lraw[-1]) * t
    return np.exp(lraw + corr)



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
    # Clip Z offset to be within the original Z range to avoid protrusions
    z_o = np.clip(z_o, z[0], z[-1])
    z_o[0] = z[0]    # Force bottom frame to be perfectly flat/flush at Z=0
    z_o[-1] = z[-1]  # Force top frame to be perfectly flat/flush at Z=L

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
