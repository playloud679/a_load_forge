# `rectangular_horn.py` — Rectangular Horn Profiles & 3-D Lofting Engine

**Path:** `src/rectangular_horn.py`

---

## Imports

| Library | Symbols Used |
|---|---|
| `logging` | `getLogger` |
| `sys` | `path` |
| `pathlib` | `Path` |
| `numpy` | `np` |
| `stl.mesh` | `Mesh` |
| `_constants` | `SOUND_SPEED` |
| `_utils` | `compute_profile_normals`, `ensure_positive_volume` |
| `profile_generator` | `get_tractrix`, `get_salmon` (used by area-preserving wrappers) |

---

## 2-D Profile Functions

All profile functions return `tuple[np.ndarray, np.ndarray, np.ndarray]` — `(z_array, w_array, h_array)` where `z` is the axial coordinate (mm), `w` is the width in X (mm), and `h` is the height in Y (mm). All three arrays have shape `(n,)`.

### `get_rectangular_exponential(throat_w: float, throat_h: float, mouth_w: float, fc: float, n: int = 300) -> tuple[np.ndarray, np.ndarray, np.ndarray]`

Rectangular horn with both exponential area expansion and exponential width expansion.

**Algorithm:**
```
S(z) = Sₜ · exp(m · z)          m = 4π · fc / c
W(z) = Wₜ · exp(m/2 · z)       (exponential, matched to area rate)
H(z) = Hₜ · exp(m/2 · z)       (same rate → aspect ratio preserved)
```

where `Sₜ = throat_w · throat_h`, `Wₜ = throat_w`, `Hₜ = throat_h`. The length `L` is solved from `W(L) = mouth_w`:
```
L = (2/m) · ln(mouth_w / throat_w)
```
`z` is linearly sampled on `[0, L]` with `n` points. Aspect ratio `W/H = throat_w / throat_h` is preserved for all z.

**Raises** `ValueError` if `mouth_w ≤ throat_w`.

---

### `_area_to_rect(z: np.ndarray, r: np.ndarray, throat_w: float, throat_h: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]`

**Private** converter that takes an axisymmetric profile `(z, r)` and produces an area-preserving rectangular profile `(z, w, h)`.

**Algorithm:**
```
A(z) = π · r(z)²                     (cross-sectional area from circular)
AR   = throat_w / throat_h           (preserved aspect ratio)
W(z) = √(A(z) · AR)
H(z) = A(z) / W(z)
```
The throat aspect ratio is maintained throughout the entire horn length.

---

### `get_rectangular_tractrix(throat_w: float, throat_h: float, mouth_w: float, n: int = 300) -> tuple[np.ndarray, np.ndarray, np.ndarray]`

Area-preserving rectangular tractrix.

**Algorithm:**
1. Computes area-equivalent circular throat: `throat_eq = √(throat_w · throat_h · 4/π)`
2. Computes area-equivalent circular mouth: `mouth_eq = √(mouth_w · throat_h · 4/π)` (uses throat_h as the height reference for the mouth area)
3. Generates a circular tractrix profile via `profile_generator.get_tractrix(throat_eq, mouth_eq, n)`
4. Converts to rectangular via `_area_to_rect(z, r, throat_w, throat_h)`

---

### `get_rectangular_salmon(throat_w: float, throat_h: float, fc: float, length: float, n: int = 300) -> tuple[np.ndarray, np.ndarray, np.ndarray]`

Area-preserving rectangular Salmon (Hypex).

**Algorithm:**
1. Computes area-equivalent circular throat: `throat_eq = √(throat_w · throat_h · 4/π)`
2. Generates a circular Salmon profile via `profile_generator.get_salmon(throat_eq, fc, length, n)`
3. Converts to rectangular via `_area_to_rect(z, r, throat_w, throat_h)`

---

## Iwata Horn — Faithful Rectangular Dual-Flare

The Iwata horn is a **rectangular** horn whose two planes expand at **different rates** (unlike the axisymmetric Salmon Iwata approximation in `profile_generator.py`, which is area-law-only). This implementation is a faithful reproduction of the original l'Audiophile construction drawing for JBL 2440/375 1.5" compression drivers:

- Width W: ~×15 expansion over the length (fast — horizontal coverage)
- Height H: ~×6.4 expansion (slow — vertical coverage)
- Aspect ratio grows from ~1:1 at throat to ~2.3:1 at mouth

### Digitized Station Arrays

Stations are 50 mm apart on the native plan. Units are mm.

```python
_IWATA_Z = [0, 50, 100, 150, 200, 250, 300, 350, 400, 450, 500, 550]
_IWATA_W = [50.0, 50.0, 63.2, 81.4, 100.0, 140.2, 184.7, 245.7, 335.8, 485.0, 648.0, 740.0]
_IWATA_H = [50.0, 52.2, 57.3, 64.7, 74.2, 86.0, 99.6, 116.5, 137.0, 171.2, 247.4, 320.0]
```

### Native Constants

```python
_IWATA_L0    = 550.0   # Native plan length (mm) = _IWATA_Z[-1]
_IWATA_W0    = 50.0    # Native plan throat width (mm)
_IWATA_ARC_R0  = 692.0   # mm — mouth arc radius about point R
_IWATA_AXIAL0  = 572.0   # mm — native axial length (throat → mouth centre)
```

### `iwata_arc_mouth(throat: float, length: float) -> tuple[float, float]`

Returns `(radius, center_z)` of the mouth arc cylinder for boolean-intersect trimming.

The Iwata's wide-plane mouth is a circular arc of radius `_IWATA_ARC_R0 = 692 mm` centred on "Point R", a virtual apex on the axis ~120 mm behind the throat. The arc cylinder's axis runs along the height (Y) direction.

**Algorithm:**
```
f = throat / _IWATA_W0         (uniform scale factor)
radius = _IWATA_ARC_R0 · f     (arc curvature scales with cross-section)
center_z = length - radius     (mouth centre at x=0, z=length)
```

Used to boolean-intersect the straight rectangular loft with a Y-axis cylinder: keep material where `x² + (z − center_z)² ≤ radius²`. This rolls the wide-plane mouth back into the plan arc while leaving the height-plane mouth flat — exactly as drawn in l'Audiophile.

### `get_iwata_horn(throat: float = 50.0, length: float = 572.0, n: int = 300) -> tuple[np.ndarray, np.ndarray, np.ndarray]`

Generates a full Iwata horn profile scaled from the digitized stations.

**Algorithm:**
```
f = throat / _IWATA_W0         (uniform scale factor)
z = linspace(0, length, n)     (linear sampling along axis)
t = z / length                 (parametric position [0, 1])
w = _iwata_smooth(_IWATA_W, t) · f
h = _iwata_smooth(_IWATA_H, t) · f
```

With defaults `(throat=50, length=572)`, this reproduces the original drawing: mouth ≈ 740 × 320 mm, throat ≈ 50 × 50 mm. Returns `(z, w, h)` — same interface as other rectangular profiles, ready for `generate_rectangular_3d_mesh()`.

### `_iwata_smooth(arr: np.ndarray, t: np.ndarray, deg: int = 3) -> np.ndarray`

**Private** — Smooth, monotone curve through digitized plan stations.

**Algorithm:**
1. Fits a degree-`deg` polynomial to `log(arr)` vs. `_IWATA_Z` (log-space to keep values positive and monotone, matching near-exponential growth):
   ```
   lraw = polyval(polyfit(_IWATA_Z, log(arr), deg), t · _IWATA_L0)
   ```
2. Applies a **linear end-point correction** that anchors both endpoints exactly to the drawing values:
   ```
   corr = (log(arr[0]) - lraw[0]) · (1 - t) + (log(arr[-1]) - lraw[-1]) · t
   result = exp(lraw + corr)
   ```
3. This produces a ~5× smoother wall than PCHIP interpolation while preserving the exact throat and mouth dimensions.

---

## 3-D Rectangular Lofting Engine

### `generate_rectangular_3d_mesh(z: np.ndarray, w: np.ndarray, h: np.ndarray, thickness: float = 4.0, output_path: str | None = None) -> mesh.Mesh`

Builds a watertight rectangular horn STL from `(z, w, h)` profiles. No CSG booleans are used — all surfaces are triangulated manually.

**Algorithm:**

1. **Normals** — `_utils.compute_profile_normals(z, w, flip_if_negative=True)` and `compute_profile_normals(z, h, flip_if_negative=True)`. The `flip_if_negative` flag ensures the outward normal's r-component is positive for expanding profiles.

2. **Outer profile offsets:**
   ```
   w_o = w + 2 · thickness · nw[:, 1]    (total X offset = 2× thickness × Nx)
   h_o = h + 2 · thickness · nh[:, 1]    (total Y offset = 2× thickness × Ny)
   z_o = z + thickness · (nw[:, 0] + nh[:, 0]) / 2
   ```
   The Z offset uses the mean of the two Z-normal components. It is clipped to `[z[0], z[-1]]` and the endpoints are forced to `z_o[0] = z[0]`, `z_o[-1] = z[-1]` to ensure flush bottom and top frames.

3. **Slice corners** — For each Z index, both inner and outer rectangular slices are represented by 4 corner vertices:
   ```
   corners(w, h, z) → [(-w/2, -h/2, z), (+w/2, -h/2, z), (+w/2, +h/2, z), (-w/2, +h/2, z)]
   ```

4. **Triangulation — 4 inner walls + 4 outer walls:** For each consecutive pair of slices `(i, i+1)`:
   - **Inner walls** (4 sides, normals point inward → reverse winding): bottom (-Y), right (+X), top (+Y), left (-X). Each side is 2 triangles connecting `ci[k], ci1[k], ci[k+1]` and `ci[k+1], ci1[k], ci1[k+1]`.
   - **Outer walls** (4 sides, normals outward → forward winding): same 4 sides with `co[k], co[k+1], co1[k]` and `co[k+1], co1[k+1], co1[k]`.

5. **Bottom frame:** 8 triangles connecting the 4 inner and 4 outer corners of the first slice. Outward normal = −Z.

6. **Top frame:** 8 triangles connecting the 4 inner and 4 outer corners of the last slice. Outward normal = +Z.

7. **Total triangle budget:** `16 · (n - 1) + 16` (16 per slice gap for walls, 16 for bottom + top frames).

8. **Volume fix:** `_utils.ensure_positive_volume(m_obj)` flips winding if mass-property volume is negative.

9. **Export:** If `output_path` is provided, saves STL. Returns `mesh.Mesh`.

**Returns:** A `mesh.Mesh` (numpy-stl) object.
