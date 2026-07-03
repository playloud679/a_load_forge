# `src/polygonal_horn.py` — Polygonal Horn

Builds a watertight horn with a regular N-gon (triangle, square, hexagon,
octagon, up to 12-gon) cross-section from any expansion profile. Corners can
be **filleted** (`corner_radius > 0`): the section becomes a rounded regular
N-gon, still area-matched to the equivalent circle.

Uses `numpy-stl` (`from stl import mesh`) — NOT trimesh.

---

## Rounded-corner model (corner_radius > 0)

The rounded section is the **Minkowski sum of a regular N-gon core**
(circumradius `Rc`, vertices at `π/2 + k·2π/N`) **and a disk of radius `f`**:

- faces at apothem `Rc·cos(π/N) + f`
- corner arcs of radius `f` centred on the core vertices
- across-corner (max) radial extent `Rc + f`
- area `A = s2·Rc² + s1·Rc·f + π·f²` with `s2 = N/2·sin(2π/N)`,
  `s1 = 2N·sin(π/N)`

Area matching solves that quadratic for `Rc` given `A = π·r_eq²`
(`rounded_poly_core`). **Per-station clamp**: `f = min(corner_radius,
0.995·r_eq)` — at `f = r_eq` the exact solution is `Rc = 0` (the section IS
the equivalent circle), so a fillet larger than the local `r_eq` collapses
the section to a circle. A horn with a small throat therefore morphs
**circular throat → rounded-polygon mouth** automatically; the 0.995 keeps a
sliver of flat face so ring topology stays valid.

**Wall offset**: Minkowski sums compose, so the outer surface is a true
in-plane parallel offset — same core, fillet `f + t·n_r` (`n_r` from the
meridian normal of the across-corner curve), plus the axial shift `t·n_z`
with ends pinned like the sharp engine. Erosion past the fillet (return
curls with `t·n_r < −f`) shrinks the core along the face normals instead
(`offset_rounded_poly`, `min_fillet = 0.02` keeps constant point count).

### Rounded-N-gon API

| Function | Purpose |
|---|---|
| `rounded_poly_core(r_eq, n, fillet)` → `(Rc, f)` | Area-matched core circumradius + clamped fillet. Arrays or scalars. |
| `rounded_poly_area(core_R, fillet, n)` | Analytic area of the rounded N-gon. |
| `offset_rounded_poly(core_R, fillet, dist, n, min_fillet=0.02)` → `(Rc', f')` | Signed in-plane parallel offset (dilation grows the fillet; deep erosion shrinks the core). |
| `rounded_polygon_ring(core_R, fillet, n_sides, arc_seg=8, phase=π/2)` | CCW boundary, `n_sides·(arc_seg+1)` points (corner arcs; faces are the implicit connecting segments). |
| `rounded_poly_radius_at_angle(core_R, fillet, n_sides, angle, phase=π/2)` | Radial extent along a ray (star-shaped; arc vs face regimes split at the tangent-point angle). |
| `rounded_poly_ring_resampled(core_R, fillet, n_sides, n, phase=π/2)` | `n` points evenly spaced along the perimeter, starting at the corner-0 arc midpoint — same convention as `throat_adapter._poly_points`, for twist-free adapter lofts. |
| `rounded_poly_wall(z, r_eq, n_sides, thickness, corner_radius)` → dict | **Single source of truth** for per-station wall arrays (`core`, `f_in`, `core_out`, `f_out`, `z_out`, `R_in`, `R_out`, `r_eq_out`) shared by the mesh engine, the UI preview/flange sizing and the adapter stack. Don't re-derive the offset. |

The UI exposes the fillet as **Corner radius (mm)** next to **Sides**
(`poly_fillet` in session state / `.flr`). `corner_radius = 0` takes the
legacy sharp code path, byte-identical to before.

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
    corner_radius: float = 0.0,
    arc_seg: int = 8,
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
| `corner_radius` | `float` | `0.0` | Corner fillet radius (mm). `0` = sharp N-gon (legacy path below, byte-identical). `>0` = rounded N-gon via `rounded_poly_wall` + `_ring_loft_mesh`; ring point count `M = n_sides·(arc_seg+1)`, triangle budget `4·M·(nz−1) + 4·M`. |
| `arc_seg` | `int` | `8` | Segments per corner arc (rounded path only). |

**Returns:** Watertight `stl.mesh.Mesh` of the N-gon horn.

**Raises:** `ValueError` if `n_sides < 3`.

`_ring_loft_mesh(rings_i, rings_o, z_i, z_o, ...)` is the generic two-wall
loft used by the rounded path: same topology as the sharp engine with M
points per ring instead of N. Everything below this point describes the
**sharp** (`corner_radius = 0`) path.

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
