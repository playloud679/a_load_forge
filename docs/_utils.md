# `_utils.py` - Shared Geometry Helpers

**Path:** `src/_utils.py`

---

## Purpose

Small, dependency-light math/mesh helpers shared across the profile and mesh
engines. No profile-specific logic lives here — only generic operations on
`(z, r)` profiles and `numpy-stl` meshes.

---

## Type Aliases

Canonical names for the 2-D math layer (the first layer of the two-layer system
described in `CLAUDE.md`). A profile is a tuple of parallel 1-D `numpy` arrays.

```python
CircularProfile = tuple[np.ndarray, np.ndarray]              # (z, r) — axisymmetric
RectProfile     = tuple[np.ndarray, np.ndarray, np.ndarray]  # (z, w, h) — rectangular
```

Use these in annotations when passing whole profiles around; the existing engine
functions still take the arrays positionally (`z, r`).

---

## Public API

```python
def compute_profile_normals(
    z: np.ndarray,
    r: np.ndarray,
    flip_if_negative: bool = False,
) -> np.ndarray
```
Outward unit normals `(n_z, n_r)` for a 2-D profile. Uses a finite-difference
gradient with boundary protection (degenerate/zero-length tangents borrow the
nearest valid neighbour). When `flip_if_negative` is `True`, the whole normal
field is flipped if the first sample's r-component is negative (needed by the
rectangular horn). This is the meridian normal used by the constant-thickness
parallel offset in the axisymmetric engine.

```python
def ensure_positive_volume(m: mesh.Mesh) -> mesh.Mesh
```
Flips triangle winding (`vectors[:, [0, 2, 1]]`) if the signed volume is
negative, so exported STLs have outward-facing normals. Swallows errors from
`get_mass_properties()` on degenerate meshes and returns the mesh unchanged.

```python
def align_z_to_zero(m: mesh.Mesh) -> mesh.Mesh
```
Shifts the mesh in Z so its lowest vertex sits at `Z = 0` (no-op within 1e-4).

---

## Notes

- Mutates the passed-in `mesh.Mesh` in place (and also returns it) for the two
  alignment helpers.
- Keep this module free of profile math and of heavy deps (`trimesh`,
  `manifold3d`, `shapely`) — those belong in the engine modules.
