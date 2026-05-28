import numpy as np
from stl import mesh


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
        if m.get_mass_properties()[0] < 0:
            m.vectors = m.vectors[:, [0, 2, 1]]
    except Exception:
        pass
    return m


def align_z_to_zero(m: mesh.Mesh) -> mesh.Mesh:
    """Shift mesh so the lowest Z vertex sits at Z=0."""
    z_min = m.vectors.reshape(-1, 3)[:, 2].min()
    if abs(z_min) > 1e-4:
        m.vectors[:, :, 2] -= z_min
    return m
