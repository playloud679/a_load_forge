from __future__ import annotations

import numpy as np
from stl import mesh

# Canonical type aliases for the 2-D math layer (see CLAUDE.md "two-layer system").
# A profile is a tuple of parallel 1-D arrays describing the meridian.
CircularProfile = tuple[np.ndarray, np.ndarray]  # (z, r) — axisymmetric
RectProfile = tuple[np.ndarray, np.ndarray, np.ndarray]  # (z, w, h) — rectangular


def compute_profile_normals(
    z: np.ndarray,
    r: np.ndarray,
    flip_if_negative: bool = False,
) -> np.ndarray:
    """
    Compute outward unit normals (n_z, n_r) for a 2-D profile (z, r).

    Uses finite-difference gradient with boundary protection.
    When *flip_if_negative* is True, the normals are flipped if the
    first entry has a negative r-component (needed for rectangular horn).
    """
    dz = np.gradient(z)
    dr = np.gradient(r)
    tan = np.column_stack([dz, dr])
    tn = np.sqrt(tan[:, 0] ** 2 + tan[:, 1] ** 2)

    tiny = tn < 1e-10
    if tiny.any():
        valid = np.where(~tiny)[0]
        if len(valid) > 0:
            for idx in np.where(tiny)[0]:
                neighbour = valid[np.argmin(np.abs(valid - idx))]
                dz[idx] = dz[neighbour]
                dr[idx] = dr[neighbour]
                tn[idx] = tn[neighbour]
    tn[tn < 1e-15] = 1.0
    tan /= tn.reshape(-1, 1)

    nml = np.column_stack([-tan[:, 1], tan[:, 0]])

    if flip_if_negative and nml[0, 1] < 0:
        nml = -nml

    return nml


def ensure_positive_volume(m: mesh.Mesh) -> mesh.Mesh:
    """Flip triangle winding if volume is negative."""
    try:
        v = np.asarray(m.vectors, dtype=np.float64)
        x0, x1, x2 = v[:, 0, 0], v[:, 1, 0], v[:, 2, 0]
        y0, y1, y2 = v[:, 0, 1], v[:, 1, 1], v[:, 2, 1]
        z0, z1, z2 = v[:, 0, 2], v[:, 1, 2], v[:, 2, 2]
        a1, b1, c1 = x1 - x0, y1 - y0, z1 - z0
        a2, b2, c2 = x2 - x0, y2 - y0, z2 - z0
        d0 = b1 * c2 - b2 * c1
        signed_volume = np.sum(d0 * (x0 + x1 + x2)) / 6.0
        if signed_volume < 0:
            m.vectors = m.vectors[:, [0, 2, 1]]
            m.update_normals()
    except Exception:
        pass
    return m


def align_z_to_zero(m: mesh.Mesh) -> mesh.Mesh:
    """Shift mesh so the lowest Z vertex sits at Z=0."""
    z_min = m.vectors.reshape(-1, 3)[:, 2].min()
    if abs(z_min) > 1e-4:
        m.vectors[:, :, 2] -= z_min
    return m
