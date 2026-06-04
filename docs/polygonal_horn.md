# `src/polygonal_horn.py` — Polygonal Horn

Builds a watertight horn with a regular N-gon (triangle, square, hexagon,
octagon, up to 12-gon) cross-section from any expansion profile.

Uses `numpy-stl` (`from stl import mesh`) — NOT trimesh.

---

## `_r_to_circumradius`

```python
def _r_to_circumradius(r_eq: np.ndarray, n: int) -> np.ndarray:
```

Converts area-equivalent circle radius to the circumradius of a regular N-gon:

```
R = r_eq × sqrt(2π / (n × sin(2π/n)))
```

**Derivation:** For a regular N-gon with circumradius R:
- Area = `(n/2) × R² × sin(2π/n)`
- For equal area, `π × r_eq² = (n/2) × R² × sin(2π/n)`
- Solving for R gives the formula above.

---

## `generate_polygonal_3d_mesh`

```python
def generate_polygonal_3d_mesh(
    z: np.ndarray,
    r_eq: np.ndarray,
    n_sides: int,
    thickness: float = 4.0,
    output_path: str | None = None,
) -> mesh.Mesh:
```

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `z` | `np.ndarray` | (required) | Z-coordinates of profile stations, length `nz`. |
| `r_eq` | `np.ndarray` | (required) | Area-equivalent circular radii at each Z, length `nz`. From any profile function (`get_tractrix`, `get_salmon`, etc.). |
| `n_sides` | `int` | (required) | Number of polygon sides (must be ≥ 3, typically 3–12). |
| `thickness` | `float` | `4.0` | Uniform wall thickness (mm). |
| `output_path` | `str \| None` | `None` | If set, saves STL to this path after construction. |

**Returns:** Watertight `stl.mesh.Mesh` of the N-gon horn.

**Raises:** `ValueError` if `n_sides < 3`.

---

## Uniform-thickness offset algorithm

### Inner polygon (meridian)

The inner wall vertices at each Z slice form a regular polygon with
circumradius `R_i` and Z-height `z`:

```
R_i = _r_to_circumradius(r_eq, n_sides)
```

### Profile normals

Normals in the `(z, R)` meridian plane are computed via central differences
by `_utils.compute_profile_normals(z, R_i, flip_if_negative=True)`:

```
nml[:, 0] = n_z    (Z component of normal)
nml[:, 1] = n_r    (R component of normal)
```

### Outer polygon (parallel offset)

The outer wall is obtained by offsetting each inner vertex **along the
meridian normal**, with a polygon-specific correction for face thickness.

In a regular N-gon, moving each face outward by `t` (wall thickness) means
the circumradius increases by `t / cos(π/N)` — standard polygon offset
geometry (the distance from centre to apothem, measured perpendicular to a
face):

```
cos_pn = cos(π / N)
R_o = R_i + thickness / cos_pn × n_r
z_o = z + thickness × n_z
```

**Clamping:** `z_o` is clipped to `[z[0], z[-1]]` and the endpoints are
pinned:
```
z_o[0]  = z[0]   (throat stays flat)
z_o[-1] = z[-1]  (mouth stays flat)
```

This ensures the throat and mouth openings sit in the same plane as the
inner wall, so the horn can mate with flanges.

---

## Vertex layout and orientation

### Rotation by π/2

Vertices at each polygon ring are generated at angles:
```
θ_k = k × 2π/N + π/2    for k = 0, 1, ..., N−1
```

The `+ π/2` rotation ensures that for even N, a **flat face** sits on the
front side (positive Y direction). Without this rotation, a corner vertex
would point forward. This matters for slicing into petals — the seam plane
cuts through a flat face rather than a vertex, giving a cleaner cross-section.

### Corner generation

```python
def corners(R_value, z_value):
    return [[R_value × cos(θ_k), R_value × sin(θ_k), z_value] for θ_k in θ]
```

---

## Triangle budget and mesh topology

| Element | Quads | Triangles | Formula |
|---|---|---|---|
| Inner wall | `N × (nz−1)` | `2 × N × (nz−1)` | Each layer ring: N quads, each quad = 2 tris |
| Outer wall | `N × (nz−1)` | `2 × N × (nz−1)` | Same as inner |
| Bottom frame | N | `2 × N` | Ring at Z=z[0], bridges inner→outer |
| Top frame | N | `2 × N` | Ring at Z=z[−1], bridges inner→outer |
| **Total** | | `4·N·(nz−1) + 4·N` | |

### Winding conventions

- **Inner wall:** Reversed winding (`ci[k] → ci1[k] → ci[kk]` and
  `ci[kk] → ci1[k] → ci1[kk]`) to point normals inward (toward the void
  inside the horn).
- **Outer wall:** Forward winding (`co[k] → co[kk] → co1[k]` and
  `co[kk] → co1[kk] → co1[k]`) to point normals outward.
- **Bottom frame:** Winding so normals point in −Z (downward).
- **Top frame:** Winding so normals point in +Z (upward).

### Loop structure

For each Z layer `i ∈ [0, nz−2]` and side index `k ∈ [0, N−1]` (wrap-around
`kk = (k+1) % N`):

```
Inner wall quad: ci[k] → ci1[k] → ci[kk],  ci[kk] → ci1[k] → ci1[kk]
Outer wall quad: co[k] → co[kk] → co1[k],  co[kk] → co1[kk] → co1[k]
```

---

## Post-processing

After mesh construction:
1. `_utils.ensure_positive_volume(m_obj)` — flips normals if the volume is
   negative (ensures outward-facing normals by winding order correction).
2. If `output_path` is set, saves STL via `m_obj.save(output_path)` and
   logs the triangle count and polygon side count.
