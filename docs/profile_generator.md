# `profile_generator.py` — Axisymmetric Horn Profiles & 3-D Mesh Engine

**Path:** `src/profile_generator.py`

---

## Imports

| Library | Symbols Used |
|---|---|
| `argparse` | `ArgumentParser`, `Namespace` |
| `logging` | `getLogger` |
| `sys` | `path`, `exit` |
| `pathlib` | `Path` |
| `numpy` | `np` |
| `trimesh` | `Trimesh` |
| `stl.mesh` | `Mesh` |
| `scipy.integrate` | `solve_ivp` |
| `_constants` | `SOUND_SPEED` |
| `_utils` | `compute_profile_normals` |

---

## Constants

```python
SOUND_SPEED = 344_000  # mm/s, aligned with Hornresp
```

Imported from `src/_constants.py`.

---

## CLI

### `parse_args(args: list[str] | None = None) -> argparse.Namespace`

| Argument | Type | Default | Description |
|---|---|---|---|
| `--throat` | `float` | **required** | Throat diameter in mm |
| `--mouth` | `float` | `None` | Mouth diameter (tractrix / exponential / R-OSSE) |
| `--fc` | `float` | `None` | Cutoff frequency in Hz (exponential / salmon) |
| `--length` | `float` | `None` | Axial length in mm (salmon / oblate) |
| `--coverage` | `float` | `90.0` | Total coverage angle in degrees (oblate / conical / R-OSSE; formula uses half-angle) |
| `--T` | `float` | `0.707` | Salmon flare parameter T (0=catenoidal, <1=cosh, 1=exponential, >1=sinh) |
| `--max-angle` | `float` | `160.0` | Termination angle in degrees (lecleach only, 90-180, default 160) |
| `--complete-rollback` | `flag` | `False` | Extend Le Cléac'h / R-OSSE with an inward return curl after the acoustic rollback lip |
| `--rollback-angle` | `float` | `330.0` | Final tangent angle for `--complete-rollback`, measured in degrees from +Z |
| `--profile` | `str` | `"auto"` | Choices: `"auto"`, `"tractrix"`, `"salmon"`, `"iwata"`, `"lecleach"`, `"oblate"`, `"conical"`, `"rosse"` |
| `--thickness` | `float` | `4.0` | Wall thickness in mm |
| `--segments` | `int` | `300` | Number of profile sample points |
| `--rings` | `int` | `64` | Circumferential tessellation rings |
| `--output` | `str` | **required** | Output STL file path |

---

## 2-D Profile Functions

All profile functions return `tuple[np.ndarray, np.ndarray]` — `(z_array, r_array)` where `z` is axial coordinate (mm) and `r` is radius (mm). Both arrays have shape `(n,)`.

### `get_tractrix(throat: float, mouth: float, n: int) -> tuple[np.ndarray, np.ndarray]`

**Algorithm:** Pure tractrix curve.

```
z(r) = a · arcosh(a / r) − √(a² − r²)
```

where `a = mouth / 2`. The curve is computed from `r ∈ [throat/2, mouth/2]` and shifted so `z(throat/2) = 0`. The tractrix naturally terminates when the tangent is horizontal (90° from the Z axis) — this occurs exactly at `r = a`, i.e. `r = mouth/2`. Returns `z` monotonically increasing from 0 to `L`, where `L = z(mouth/2)`.

### `get_exponential(throat: float, mouth: float, fc: float, n: int) -> tuple[np.ndarray, np.ndarray]`

**Algorithm:** Pure exponential horn.

```
S(z) = Sₜ · exp(m · z)       m = 4π · fc / c
R(z) = (throat/2) · exp(m/2 · z)
```

Length is derived from the target mouth: `L = (2/m) · ln(mouth / throat)`. Z linearly sampled on `[0, L]`.

### `get_oblate_spheroidal(throat: float, coverage_angle: float, length: float, n: int) -> tuple[np.ndarray, np.ndarray]`

**Algorithm:** Constant-directivity oblate spheroidal waveguide profile.

The wall radius is:

```
r(x) = sqrt(r₀² + (x · tan(theta))²)
theta = coverage_angle / 2
```

where `r₀ = throat/2`, `x` is the axial coordinate, and `coverage_angle` is the total desired dispersion. This gives the two required CD constraints:

- **Parallel throat:** `dr/dx = x·tan²(theta) / r(x)`, so `dr/dx = 0` at `x = 0`.
- **Conical asymptote:** for large `x`, `r(x) ≈ x·tan(theta)`, so the wall tends to the requested half-angle.

The function raises `ValueError` if throat or length are non-positive, or if `coverage_angle` is not between 0° and 180°.

The CD oblate law itself is angle/length driven and does not contain an exponential cutoff parameter. The CLI and UI report the approximate lower loading limit at which throat resistance reaches about 0.2 of its asymptotic value:

```
f_load ≈ 0.2 · c · sin(coverage_angle/2) / (π · throat_radius)
```

This is still a loading estimate, not a prediction of the complete driver/waveguide response or polar pattern.

### `get_oblate_spheroidal_for_mouth(throat: float, mouth: float, coverage_angle: float, n: int) -> tuple[np.ndarray, np.ndarray]`

Convenience wrapper for cases that start from a target mouth diameter. It solves:

```
length = sqrt((mouth/2)² − (throat/2)²) / tan(coverage_angle/2)
```

and delegates to `get_oblate_spheroidal()`.

### `get_oblate_spheroidal_asymmetric(throat_w: float, throat_h: float, coverage_h: float, coverage_v: float, length: float, n: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]`

Asymmetric constant-directivity oblate profile. Horizontal and vertical axes are calculated independently:

```
w(x) = 2 · sqrt((throat_w/2)² + (x · tan(coverage_h/2))²)
h(x) = 2 · sqrt((throat_h/2)² + (x · tan(coverage_v/2))²)
```

This supports waveguides such as 90° horizontal × 45° vertical, with both axes starting parallel at the throat and tending toward their independent conical asymptotes.

### `get_conical(throat: float, coverage_angle: float, length: float, n: int) -> tuple[np.ndarray, np.ndarray]`

Conical horn — the constant-directivity **reference** shape. Straight wall from the throat at the half-coverage angle:

```
r(x) = r0 + x · tan(theta),   theta = coverage_angle / 2
```

Same `(throat, coverage, length)` interface as `get_oblate_spheroidal`, so the UI dispatches both through one handle (`is_cd`). Unlike oblate, the throat slope is **non-zero** (a sharp cone). The wall angle is nominal/asymptotic; actual directivity remains frequency- and driver-dependent. Mouth Ø and a one-wavelength mouth-loading estimate are derived (not inputs). The rectangular counterpart is `rectangular_horn.get_rectangular_conical`.

### `complete_rollback_profile(z: np.ndarray, r: np.ndarray, n: int | None = None, target_angle: float = 330.0, curl_scale: float = 0.30) -> tuple[np.ndarray, np.ndarray]`

Post-process for rollback profiles. The base Le Cléac'h and R-OSSE equations
stop at the acoustic rollback lip: axial `z` has turned back, while radius is
still at or near the largest value. This helper appends a smooth circular-arc
return whose tangent starts from the existing final tangent and ends at
`target_angle`, then resamples by meridian arc length.

The default mode in `get_lecleach()` and `get_rosse()` leaves profiles
unchanged. The UI exposes this helper as **Rollback lip: Truncated / Extended**
for Le Cléac'h and **Normal / Extended** for R-OSSE; `Extended` adds the inward
curl without changing the upstream airway profile.
If the requested return angle would push the appended curl below the throat
plane (`z[0]`), the helper reduces only the curl radius so the mesh engine does
not later crush that below-zero geometry into a flat cap.

### `get_rosse(throat: float, mouth: float, coverage_angle: float, n: int, throat_angle: float = 15.0, k: float = 1.8, r: float = 0.3, m: float = 0.8, b: float = 0.3, q: float = 3.7, complete_rollback: bool = False, rollback_angle: float = 330.0) -> tuple[np.ndarray, np.ndarray]`

Implements Marcel Batík's **R-OSSE Acoustic Waveguide rev.7** parametric expansion. Unlike a function `r(z)`, R-OSSE uses `[z(t), r(t)]` for `0 <= t <= 1`, allowing the mouth to roll back toward free space. The public `coverage_angle` and `throat_angle` arguments are total angles; the published formula's `a` and `a0` are their half-angles.

The defaults reproduce the document's ST260 example when called as `get_rosse(25.4, 260, 78, n)`: outer radius `130 mm`, maximum axial depth approximately `77.70 mm`, and rolled-back edge at approximately `57.47 mm`. With `complete_rollback=True`, the published endpoint is extended by the shared inward return curl and the profile is resampled back to `n` points.

The UI exposes all six shape controls from the paper. Circular and polygonal sections use the axisymmetric profile directly. Rectangular and elliptical sections use an area-preserving conversion at a constant throat aspect ratio. The experimental Radial 360° engine is not exposed in the UI.

### `get_salmon(throat: float, fc: float, length: float, n: int, T: float = 0.707) -> tuple[np.ndarray, np.ndarray]`

**Algorithm:** Axisymmetric Salmon / Hyperbolic-Exponential horn.

```
S(x) = Sₜ · (cosh(x/x₀) + T · sinh(x/x₀))²
R(x) = √(S(x) / π)
x₀   = c / (2π · fc)
```

where `Sₜ = π · (throat/2)²`. The parameter `T` controls the flare family:
- `T = 0` → catenoidal (cosh²)
- `0 < T < 1` → cosh-dominant
- `T = 1` → exponential
- `T > 1` → sinh-dominant
- Default `T = 0.707` → classical Hypex alignment (used by Iwata and Hornresp "Le Cléac'h")

### `get_iwata(throat: float, fc: float, length: float, n: int) -> tuple[np.ndarray, np.ndarray]`

Wrapper that calls `get_salmon(throat, fc, length, n, T=0.707)`. Iwata = Salmon Hypex preset.

### `get_lecleach(throat: float, fc: float, n: int, T: float = 0.707, max_angle: float = 160.0, complete_rollback: bool = False, rollback_angle: float = 330.0) -> tuple[np.ndarray, np.ndarray]`

**Algorithm:** Le Cléac'h isophase wavefront horn — Salmon area law + parallel wavefronts, solved via ODE.

**Governing equations** (in arc-length `s`):

```
S(s) = Sₜ · (cosh(s/x₀) + T · sinh(s/x₀))²   (area law)
cos α = 2πr² / S(s) − 1                        (wavefront curvature)
dr/ds = sin α                                   (wall follows normal)
dz/ds = cos α
```

where `Sₜ = π · (throat/2)²` and `x₀ = c / (2π · fc)`.

**ODE Solver:** `scipy.integrate.solve_ivp` with:
- Method: `RK45`
- `rtol = 1e-9`, `atol = 1e-9`
- `max_step = 0.5`
- Initial conditions: `s=0, r=throat/2, z=0`
- Integration domain: `[0, 50000]`; the mouth is defined by the termination-angle event, not by an axial-length input.
- `complete_rollback=True` appends the shared inward return curl after the ODE endpoint, clamps the curl radius if needed to stay above the throat plane, then resamples the whole meridian back to `n` points.

**Termination event:**
```
_event(s, y): cos α − cos(max_angle) = 0
```
The event is `terminal=True`, `direction=-1`. Integration stops when the wall tangent angle `α` (where `cos α` drops below `cos(max_angle)`) reaches the threshold. The resulting raw ODE solution is resampled to `n` points via linear interpolation.

**Practical range for max_angle:** 90° (gentle roll-back) to 180° (full roll-back, mouth curls back toward throat). J.M. Le Cléac'h recommends 160°–180°.

If the ODE returns a single point (degenerate), the function returns `z = zeros(n)`, `r = full(n, throat/2)`.

---

## 3-D Mesh Engine

### `generate_3d_mesh_from_profile(z_i: np.ndarray, r_i: np.ndarray, thickness: float = 4.0, rings: int = 64, output_path: str | None = None) -> mesh.Mesh`

**Profile-agnostic** engine that takes any valid 2-D profile `(z_i, r_i)` and produces a watertight STL with constant perpendicular wall thickness.

**Algorithm steps:**

1. **Normals** — `_utils.compute_profile_normals(z_i, r_i)` returns unit normals `(n_z, n_r)` as `(n_pts, 2)` array computed via finite-difference gradient. The normal points outward from the inner surface.

2. **Parallel offset** — The outer profile is computed as a true parallel offset:
   ```
   z_o = z_i + n_z · thickness
   r_o = r_i + n_r · thickness
   ```
   For a body of revolution, the 3-D surface normal lies in the meridian plane, so this yields a constant perpendicular wall thickness everywhere (a true 3-D offset).

3. **Revolution** — Both inner and outer profiles are revolved around Z at `rings` angular divisions (`θ ∈ [0, 2π)`). This produces 4 vertex grids: outer wall and inner wall, each with `n_pts × rings` vertices.

4. **Triangulation** — All surfaces are triangulated manually:
   - **Outer wall** — quad strips between consecutive profile rings, forward winding
   - **Inner wall** — quad strips, reverse winding (inward normals)
   - **Bottom annulus** — at `z = z[0]`, connecting inner and outer rims
   - **Top annulus** — at `z = z[-1]`, connecting inner and outer rims

5. **Watertight merge** — All triangle vertices are packed into a single array; `trimesh.Trimesh` is constructed with `process=True`, then `merge_vertices()` is called.

6. **Throat base flattening** — Because the constant-thickness parallel offset leaves the outer throat rim at a different Z than the inner rim, the raw base is slanted. It is sliced flat: `tm.slice_plane([0,0,base_z], [0,0,1], cap=True)` where `base_z = max(z_i[0], z_o[0])`. This yields a planar throat face while keeping the wall uniformly thick everywhere else.

7. **Normals fix** — `tm.fix_normals()` ensures outward-facing normals.

8. **Export** — If `output_path` is provided, exports STL. Returns a `mesh.Mesh` (numpy-stl) object.

### `generate_elliptical_3d_mesh_from_profiles(z_i: np.ndarray, rx_i: np.ndarray, ry_i: np.ndarray, thickness: float = 4.0, rings: int = 96, output_path: str | None = None) -> mesh.Mesh`

Builds a watertight elliptical-section horn from independent X/Y radii. This is the mesh path for asymmetric oblate CD waveguides with different horizontal and vertical coverage angles.

Each inner slice is:

```
x = rx(z) · cos(phi)
y = ry(z) · sin(phi)
```

The outer wall uses `_elliptical_parallel_offset_vertices()` to offset every
surface point along its full 3-D unit normal:

```
V_outer(u, phi) = V_inner(u, phi) + thickness · normal(u, phi)
```

Unlike the old radial-only `rx + thickness`, `ry + thickness` construction,
this includes the axial normal component and preserves constant perpendicular
wall thickness through steep and roll-back regions such as R-OSSE.

The function triangulates inner wall, outer wall, throat annulus, and mouth annulus, runs the result through `trimesh.Trimesh(..., process=True)`, merges vertices, **flattens the throat base** (same invariant as the axisymmetric engine: `slice_plane([0,0,base_z], [0,0,1], cap=True)` with `base_z = max(z_i[0], max(V_o[0,:,2]))` — the 3-D normal offset pushes the outer throat rim below `z_i[0]` on an expanding throat, and without the slice the mesh `z_min` sat ~`thickness·|n_z|` below the profile origin, shifting everything the UI anchors to `z_min` — embedded throat adapter trim/positioning, flange Z offsets — and leaving a visible step at the adapter↔flare junction for elliptical R-OSSE), fixes normals, optionally exports STL, and returns a `mesh.Mesh`.

Note for the embedded throat adapter (UI): the outer wall's ring Z varies with
azimuth (per-vertex 3-D normal offset), so the wall's true constant-Z contour
is **not** an ellipse through the `(w, h)` extremes at mean-Z stations. The UI
samples the `_elliptical_parallel_offset_vertices` field per azimuth column at
`_ta._NP` rings for the adapter's `custom_outer_pts` (same approach as OS-SE).

### `_elliptical_parallel_offset_vertices(z_i, rx_i, ry_i, thickness, rings) -> tuple[np.ndarray, np.ndarray]`

Returns the inner vertex grid and its true parallel-offset outer grid. The UI
uses the same helper when deriving elliptical outer dimensions and adapter
raccordo values, keeping generated accessories synchronized with the mesh.

---

## Dispatch

### `resolve_profile(args: argparse.Namespace) -> str`

Automatic profile resolution logic:
- If `args.profile == "auto"`, selects based on provided arguments:
  - `--length` and `--fc` present → `"salmon"`
  - only `--fc` present → `"exponential"`
  - `--mouth` present → `"tractrix"`
  - otherwise → raises `ValueError`
- If `args.profile` is not `"auto"`, returns it as-is.

### `main(argv: list[str] | None = None) -> None`

Full CLI entry point:
1. Parses args via `parse_args(argv)`
2. Resolves profile name via `resolve_profile(args)`
3. Calls the appropriate profile function with CLI parameters
4. Calls `generate_3d_mesh_from_profile(z, r, thickness=..., rings=..., output_path=...)` with the resulting profile
5. Logs metrics (length, mouth diameter) for each profile type
6. Catches exceptions, logs them, and exits with code 1
