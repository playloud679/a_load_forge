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
| `--mouth` | `float` | `None` | Mouth diameter (tractrix only) |
| `--fc` | `float` | `None` | Cutoff frequency in Hz (exponential / salmon) |
| `--length` | `float` | `None` | Axial length in mm (salmon / lecleach) |
| `--T` | `float` | `0.707` | Salmon flare parameter T (0=catenoidal, <1=cosh, 1=exponential, >1=sinh) |
| `--max-angle` | `float` | `300.0` | Termination angle in degrees (lecleach only, 90-180, default 160) |
| `--profile` | `str` | `"auto"` | Choices: `"auto"`, `"tractrix"`, `"salmon"`, `"iwata"`, `"lecleach"` |
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

### `get_lecleach(throat: float, fc: float, length: float, n: int, T: float = 0.707, max_angle: float = 160.0) -> tuple[np.ndarray, np.ndarray]`

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
- Integration domain: `[0, max(length*10, 50000)]` — the user-provided `length` is a **minimum**

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
