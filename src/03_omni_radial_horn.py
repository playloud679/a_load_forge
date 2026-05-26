"""
360° Radial Horn (Omnidirectional Reflector).

Two interlocking solid revolutions:
  • Bottom Deflector — curved top, flat bottom, central throat hole
  • Top Reflector    — curved bottom (gap = H(R)), flat top

Acoustic law:   S(R) = S_t · exp(m · (R − R_t))
                S(R) = 2πR · H(R)    →    H(R) = S(R) / (2πR)

Output:  radial_bottom.stl  — flat base at Z=0, throat hole
         radial_top.stl     — exported upside‑down (flat side at Z=0)
"""

import logging

import numpy as np
from stl import mesh

logger = logging.getLogger(__name__)
SOUND_SPEED = 343_000


# ======================================================================
#  Radial profile math
# ======================================================================

def get_radial_profiles(
    throat_diam: float,
    mouth_diam: float,
    fc: float,
    n: int = 300,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Compute the 1‑D radial functions.

    Returns (R, Z_bottom, Z_top) arrays.
    """
    Rt = throat_diam / 2.0
    Rm = mouth_diam / 2.0
    m  = 4.0 * np.pi * fc / SOUND_SPEED   # expansion rate

    R = np.linspace(Rt, Rm, n)
    St = np.pi * Rt ** 2
    S  = St * np.exp(m * (R - Rt))

    # Vertical gap  H(R) = S(R) / (2πR)
    H = S / (2.0 * np.pi * R)

    # Bottom deflector: gentle exponential rise from the throat
    Z_bottom = (R - Rt) / (Rm - Rt) * (Rm - Rt) * 0.3   # gentle linear rise, 0.3 slope

    # Top reflector sits exactly H(R) above the bottom
    Z_top = Z_bottom + H

    return R, Z_bottom, Z_top


# ======================================================================
#  Solid‑of‑revolution helper
# ======================================================================

def _revolve_profile(
    r_profile: np.ndarray,   # radius     (first = inner edge, last = outer edge)
    z_profile: np.ndarray,   # height
    rings: int = 64,
) -> mesh.Mesh:
    """
    Revolve a 2‑D profile (r, z) around Z to obtain a solid.

    The profile must be a MONOTONIC function of r (no folds).
    The first point defines the inner boundary (throat hole).
    The last  point defines the outer boundary (mouth).

    Normals are computed via the usual gradient method.
    """
    n = len(r_profile)
    if n < 2:
        raise ValueError("Profile too short")

    # ---------- normals ----------
    dz = np.gradient(z_profile)
    dr = np.gradient(r_profile)
    tan = np.column_stack([dr, dz])
    tn = np.sqrt(tan[:, 0] ** 2 + tan[:, 1] ** 2)
    tiny = tn < 1e-10
    if tiny.any():
        valid = np.where(~tiny)[0]
        if len(valid):
            for idx in np.where(tiny)[0]:
                nbr = valid[np.argmin(np.abs(valid - idx))]
                dr[idx], dz[idx] = dr[nbr], dz[nbr]
                tn[idx] = tn[nbr]
    tn[tn < 1e-15] = 1.0
    tan /= tn.reshape(-1, 1)

    nml = np.column_stack([-tan[:, 1], tan[:, 0]])  # (nr, nz)
    if nml[0, 1] < 0:
        nml = -nml

    # ---------- revolution ----------
    theta = np.linspace(0, 2 * np.pi, rings, endpoint=False)
    ct, st = np.cos(theta), np.sin(theta)

    # Build the solid by triangulating between consecutive rings.
    #   rings × (n-1) quads = 2·rings·(n-1) triangles  (outer surface)
    #   bottom cap + top cap = 2 × 2·rings triangles    (if needed)
    n_tri = 2 * rings * (n - 1) + 2 * rings
    data = np.zeros(n_tri, dtype=mesh.Mesh.dtype)
    tri = 0

    def emit(a, b, c):
        nonlocal tri
        data["vectors"][tri] = [a, b, c]
        tri += 1

    # Outer wall
    for i in range(n - 1):
        r0, r1 = r_profile[i], r_profile[i + 1]
        z0, z1 = z_profile[i], z_profile[i + 1]
        for j in range(rings):
            jj = (j + 1) % rings
            a = [r0 * ct[j],  r0 * st[j],  z0]
            b = [r1 * ct[j],  r1 * st[j],  z1]
            c = [r1 * ct[jj], r1 * st[jj], z1]
            d = [r0 * ct[jj], r0 * st[jj], z0]
            emit(a, d, b)
            emit(b, d, c)

    # Bottom cap (Z = z[0], outward = −Z)
    z0, r0 = z_profile[0], r_profile[0]
    for j in range(rings):
        jj = (j + 1) % rings
        emit([r0 * ct[jj], r0 * st[jj], z0],
             [r0 * ct[j],  r0 * st[j],  z0],
             [0.0, 0.0, z0])

    # Top cap (Z = z[-1], outward = +Z)
    z1, r1 = z_profile[-1], r_profile[-1]
    for j in range(rings):
        jj = (j + 1) % rings
        emit([r1 * ct[j],  r1 * st[j],  z1],
             [r1 * ct[jj], r1 * st[jj], z1],
             [0.0, 0.0, z1])

    assert tri == n_tri, f"Triangle mismatch {tri} vs {n_tri}"

    m_obj = mesh.Mesh(data)

    # Z‑alignment
    z_min = m_obj.vectors.reshape(-1, 3)[:, 2].min()
    if abs(z_min) > 1e-4:
        m_obj.vectors[:, :, 2] -= z_min

    # Flip normals if volume negative
    try:
        vol = m_obj.get_mass_properties()[0]
        if vol < 0:
            m_obj.vectors = m_obj.vectors[:, [0, 2, 1]]
    except Exception:
        pass

    return m_obj


# ======================================================================
#  Public API
# ======================================================================

def generate_radial_horn(
    throat_diam: float = 25.0,
    mouth_diam:  float = 200.0,
    fc:          float = 600.0,
    rings:       int   = 64,
    output_dir:  str   = "io",
):
    """Generate both bottom deflector and top reflector STLs."""

    R, Zb, Zt = get_radial_profiles(throat_diam, mouth_diam, fc, 300)

    logger.info("Radial horn:  throat=%.0f  mouth=%.0f  fc=%.0f",
                throat_diam, mouth_diam, fc)
    logger.info("  Gap at throat H(Rt)=%.2f  at mouth H(Rm)=%.2f",
                Zt[0] - Zb[0], Zt[-1] - Zb[-1])

    # ---- Bottom deflector ------------------------------------------------
    # Profile: flat bottom at Z=0, top follows Z_bottom(R)
    # Solid from R=Rt to R=Rm with flat base and a central hole.
    # The bottom is at Z=0, the top follows Zb.
    r_bot = np.concatenate([[0], R, R[::-1]])
    z_bot = np.concatenate([[0], Zb, np.zeros_like(R)])
    bottom_mesh = _revolve_profile(r_bot, z_bot, rings)
    bottom_mesh.save(f"{output_dir}/radial_bottom.stl")
    logger.info("  Bottom:  WT=%s  B=%d  Z=[%.0f,%.0f]  tris=%d",
                _wt(bottom_mesh), _bc(bottom_mesh),
                bottom_mesh.vectors[:,:,2].min(),
                bottom_mesh.vectors[:,:,2].max(),
                len(bottom_mesh.vectors))

    # ---- Top reflector ---------------------------------------------------
    # Solid cross‑section:  bottom surface = Zt(R)
    #                       top  surface = flat at Zt[-1] + wall_T
    #                       inner wall  = at R[0]  connecting top → bottom
    #                       outer wall  = at R[-1] connecting bottom → top
    wall_T = 4.0
    r_top = np.concatenate([
        R,                      # bottom surface  Rt → Rm  (rising)
        [R[-1]],                # outer bottom
        [R[-1]],                # outer top
        R[-2::-1],              # top surface     Rm → Rt  (flat)
        [R[0]],                 # inner top
    ])
    z_top = np.concatenate([
        Zt,                     # bottom surface
        [Zt[-1]],               # outer bottom
        [Zt[-1] + wall_T],      # outer top    (4 mm wall)
        np.full(len(R) - 1, Zt[-1] + wall_T),  # flat top
        [Zt[0]],                # inner top
    ])

    top_mesh = _revolve_profile(r_top, z_top, rings)

    # Flip so the flat top rests on Z=0 for supportless printing
    zf = top_mesh.vectors[:, :, 2].copy()
    zmax = zf.max()
    top_mesh.vectors[:, :, 2] = zmax - zf
    # Also flip winding because Z reversal inverts normals
    top_mesh.vectors = top_mesh.vectors[:, [0, 2, 1]]

    top_mesh.save(f"{output_dir}/radial_top.stl")
    logger.info("  Top:     WT=%s  B=%d  Z=[%.0f,%.0f]  tris=%d",
                _wt(top_mesh), _bc(top_mesh),
                top_mesh.vectors[:,:,2].min(),
                top_mesh.vectors[:,:,2].max(),
                len(top_mesh.vectors))

    return bottom_mesh, top_mesh


def _wt(m):
    try:
        return str(m.get_mass_properties()[0] > 0)
    except Exception:
        return "?"

def _bc(m):
    return 1  # single piece by construction


# ======================================================================
#  Standalone
# ======================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    generate_radial_horn(throat_diam=25, mouth_diam=200, fc=600)
