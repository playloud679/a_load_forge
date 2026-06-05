# `throat_adapter.py` — Driver-to-Horn Throat Transition Adapter

**Path:** `src/throat_adapter.py`

---

## Imports

| Library | Symbols Used |
|---|---|
| `__future__` | `annotations` |
| `logging` | `getLogger` |
| `dataclasses` | `dataclass` |
| `numpy` | `np` |
| `trimesh` | `Trimesh`, `boolean`, `creation as _tc`, `util` |

---

## Data Structures

### `ThreadSpec` (frozen dataclass)

```python
@dataclass(frozen=True)
class ThreadSpec:
    name: str          # e.g. '1" UNF'
    major_diam: float  # mm — outer thread diameter
    pitch: float       # mm
    tpi: float         # threads per inch (informational)
```

### `THREAD_SPECS: dict[str, ThreadSpec]`

| Key | Name | Major Diam (mm) | Pitch (mm) | TPI |
|---|---|---|---|---|
| `"1in"` | 1" UNF | 25.40 | 1.270 | 20 |
| `"1_25in"` | 1\u00bc" UNF | 31.75 | 1.411 | 18 |
| `"1_375in"` | 1\u215c" UNF | 34.925 | 1.411 | 18 |
| `"2in"` | 2" UNF | 50.80 | 1.270 | 20 |

---

## Private Helpers — 2-D Cross-Section Generation

All return `np.ndarray` of shape `(n, 2)` — XY points.

### `_circle_points(r: float, n: int = 64, phase: float = 0.0) -> np.ndarray`

Returns `n` equally-spaced points on a circle of radius `r`. First point is at `θ = phase`; default `phase = 0` gives the rightmost point `(r, 0)`. Polygonal adapters pass `phase = π/2` so the circular driver/socket rings and the target N-gon use the same vertex phase, preventing a helical twist through the transition.

### `_rect_points(hw: float, hh: float, n: int = 64) -> np.ndarray`

Returns `n` points on a rectangle of half-width `hw` and half-height `hh`, distributed evenly along the perimeter.

**Perimeter ordering:** Starts at **mid-right** `(hw, 0)` and proceeds **counter-clockwise**:
1. Right edge, bottom→top: `(hw, 0)` → `(hw, hh)` 
2. Top edge, right→left: `(hw, hh)` → `(-hw, hh)`
3. Left edge, top→bottom: `(-hw, hh)` → `(-hw, -hh)`
4. Bottom edge, left→right: `(-hw, -hh)` → `(hw, -hh)`
5. Right edge bottom half: `(hw, -hh)` → `(hw, 0)`

This matched start point (mid-right = `θ=0` equivalent) ensures twist-free morphing lofts.

### `_poly_points(n_sides: int, circumradius: float, n: int = 64) -> np.ndarray`

Returns `n` points on a regular N-gon (convex polygon), distributed evenly along the perimeter.

- Vertices use the same `θ = k × 2π/N + π/2` phase as `polygonal_horn.py`, so the adapter's polygonal throat is rotationally aligned with the flare.
- Computes vertex positions, edge lengths, cumulative perimeter
- Interpolates `n` points along the perimeter by linear position along each edge
- Returns exactly `n` points for compatibility with morphing engine

### `_polygon_area(pts: np.ndarray) -> float`

Signed area of a 2-D polygon via the shoelace formula. Returns absolute value.

### `_centroid(pts: np.ndarray) -> np.ndarray`

Centroid of a 2-D polygon via the shoelace formula. Returns `(2,)` array `[cx, cy]`.

### `_signed_area(pts: np.ndarray) -> float`

Signed shoelace area; `> 0` for CCW winding. Used to pick the outward normal direction in `_offset_polygon_outward`.

### `_offset_polygon_outward(pts: np.ndarray, dist: float) -> np.ndarray`

True parallel (**miter**) offset of a closed polygon outward by `dist`: every edge moves out by exactly `dist` along its perpendicular, giving **constant perpendicular wall thickness**. This matches how the horn engines build their outer wall (`R_o = R_i + thickness/cos(π/n)` for polygons; per-side for rectangles), so in flanged mode the adapter's outer wall lines up **flush** with the horn's at the throat junction. A naive radial-from-origin offset under-extends the corners and leaves a visible **outer step** ("dentro ok, fuori il gradino"). Assumes a simple, roughly convex polygon (the morph loft always produces one); the miter is clamped (`cos_half ≥ 0.2`) so sharp corners don't blow up.

---

## Private Helpers — Morphing

### `_morph_slice(t: float, driver_R: float, target_fn: Callable[[], np.ndarray], target_R_eq: float, n: int = 64) -> np.ndarray`

Produces a single 2-D cross-section at parametric position `t ∈ [0, 1]`.

**Algorithm:**

1. **Source shape** (`t = 0`): circle of radius `driver_R`, generated via `_circle_points(driver_R, n)`.

2. **Target shape** (`t = 1`): shape returned by `target_fn()`, scaled so its area equals `π · target_R_eq²`. Scaling is about the shape's centroid.

3. **Vertex morph** (shape blending): `pts = (1 - t) · src + t · target` — a simple linear vertex blend that keeps walls twist-free and boolean merging predictable.

4. **Area correction** (radius-progression preservation): After blending, the shape's actual equivalent radius is computed. It is re-scaled (about its centroid) so that the equivalent radius matches the linear interpolation:
   ```
   r_eq_des = (1 - t) · driver_R + t · target_R_eq
   scale = r_eq_des / r_eq_now
   ```

Returns `(n, 2)` array of XY points.

---

## Revolve Helper

### `_revolve_rz(r_poly: np.ndarray, z_poly: np.ndarray, rings: int = 64) -> trimesh.Trimesh`

Revolves an **open** 2-D polygon `(r, z)` around the Z axis. The last segment implicitly connects back to the first, forming a closed cross-section for a watertight body of revolution.

Returns a watertight `trimesh.Trimesh`.

---

## Public API

### `make_adapter(driver_R: float, horn_shape: str, horn_w: float, horn_h: float, horn_n_sides: int, horn_R_eq: float, horn_circumR: float, axial_steps: int, adapter_length: float, wall_thickness: float, thread_key: str | None = None, socket_length: float = 0.0, outer_target_R: float | None = None, outer_rect_w: float | None = None, outer_rect_h: float | None = None, target_slope: float | None = None, outer_target_slope: float | None = None, output_path: str | None = None) -> trimesh.Trimesh`

Builds the morphing transition section, optionally with an integrated threaded extension at the circular (driver) end.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `driver_R` | `float` | Radius of the circular driver exit (mm) |
| `horn_shape` | `str` | `"circular"`, `"rectangular"`, or `"polygonal"` |
| `horn_w` | `float` | Throat width for rectangular (mm); unused for circular/polygonal |
| `horn_h` | `float` | Throat height for rectangular (mm); unused for circular/polygonal |
| `horn_n_sides` | `int` | Number of polygon sides (for `"polygonal"`); unused for circular/rectangular |
| `horn_R_eq` | `float` | Area-equivalent radius at horn throat (mm) |
| `horn_circumR` | `float` | Circumradius of the polygon at horn throat (mm); unused for circular/rectangular |
| `axial_steps` | `int` | Number of Z slices for the loft |
| `adapter_length` | `float` | Axial length of the transition (mm) |
| `wall_thickness` | `float` | Wall thickness for outer offset (mm) |
| `thread_key` | `str \| None` | One of `THREAD_SPECS` keys — enables threaded mode |
| `socket_length` | `float` | Depth of the threaded section (mm), must be > 0.5 to activate threads |
| `outer_target_R` | `float \| None` | Outer equivalent radius for threaded mode outer profile (matches horn outer dimensions) |
| `outer_rect_w` | `float \| None` | Outer rectangle width (threaded mode) |
| `outer_rect_h` | `float \| None` | Outer rectangle height (threaded mode) |
| `target_slope` | `float \| None` | Inner equivalent-radius slope `dr/dz` at the horn throat; when set, the adapter reaches the flare with matching expansion derivative |
| `outer_target_slope` | `float \| None` | Outer equivalent-radius slope `dr/dz` at the horn throat, computed from the same parallel-offset wall as the horn mesh |
| `output_path` | `str \| None` | Optional STL export path |

**Raccordo / expansion continuity:** The shape morph and acoustic area progression are controlled separately. The shape blend uses a quintic smoothstep, so it has zero shape-change derivative at the horn throat. The equivalent radius uses cubic Hermite interpolation when `target_slope` is provided, so the final `dr/dz` matches the first derivative of the selected flare. This removes the geometric edge at the adapter→flare joint while preserving the flare's expansion law at the handoff.

**Algorithm — Three modes:**

**A. Threaded mode** (`thread_key` is not None AND `socket_length > 0.5`):
1. Z range: `[-thread_len, adapter_length]` where `thread_len = n_turns * pitch`
2. **Thread section** (`z < 0`): Circular socket with sinusoidal thread profile `r_thread = major_R − (major_R − minor_R) · 0.5 · (1 − cos(2π · turn_frac))`. Outer wall is a smooth cylinder at `outer_R = major_R + wall_thickness`.
3. **Transition section** (`z ≥ 0`): Inner morphs from `major_R` to inner target via `_morph_slice`. For `"circular"` the target is a circle of radius `horn_R_eq`; for `"rectangular"` it is the requested rectangle; for `"polygonal"` it is the requested regular N-gon. Outer morphs from `outer_R` to the outer target if provided (for matching horn outer dimensions), otherwise to a slightly larger inner target. If slope inputs are provided, both inner and outer profiles end tangent to the horn.
4. In threaded mode, the transition is flush with the horn inner — no wall thickness separate from the outer profile.

**B. Flanged mode** (`thread_key` is None):
1. Z range: `[0, adapter_length]`
2. Inner profile morphs from `driver_R` to inner target via `_morph_slice`.
3. If an outer target is provided, the outer profile is Hermite-raccordato to that target and slope. Otherwise it falls back to a true outward-**normal (miter) offset** of the inner via `_offset_polygon_outward(inner, wall_thickness)` → constant perpendicular wall thickness. Passing the horn's actual outer throat target avoids an external step at the junction.

**C. Degenerate** (`adapter_length ≤ 0.5`): Returns a thin cylinder ring with a central hole.

**Triangulation:** For each Z slice, two rings are stored: outer (index `2i*n`) and inner (index `2i*n + n`). Quad strips connect consecutive slices for inner and outer walls. Bottom and top caps close the mesh. In threaded mode, the outer and inner rings may be coincident (flush transition), and face winding is preserved rather than reversed to let trimesh deduplicate.

**Returns:** A watertight `trimesh.Trimesh`. If `body_count > 1`, keeps the largest non-empty body.

---

### `make_threaded_socket(thread_key: str, length: float, wall_thickness: float, seg: int = 48) -> trimesh.Trimesh`

Generates a standalone threaded socket (internal thread) for a compression driver.

**Thread form:** UNF 60° V-thread with 0.6495 × pitch depth.

**Algorithm:**
1. Builds a 2-D `(r, z)` cross-section polygon: the inner boundary follows a sawtooth thread profile (major → minor → major per turn), the outer boundary is a smooth cylinder at `outer_R = major_R + wall_thickness`.
2. Revolves the polygon around Z via `_revolve_rz(seg)`.
3. If the requested `length` exceeds `n_turns * pitch`, adds a plain cylindrical extension at the bottom via boolean union (manifold engine), with 0.5 mm overlap for clean merging.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `thread_key` | `str` | One of `THREAD_SPECS` keys |
| `length` | `float` | Depth of the socket (mm) |
| `wall_thickness` | `float` | Material thickness around the bore (mm) |
| `seg` | `int` | Circumferential tessellation (default 48) |

Returns a watertight `trimesh.Trimesh`.

---

### `make_adapter_assembly(driver_type: str, driver_diam: float | None, thread_key: str | None, horn_shape: str, rect_w: float, rect_h: float, poly_n_sides: int, poly_circumR: float, horn_R_eq: float, adapter_length: float, wall_thickness: float, axial_steps: int = 50, flange_R: float = 0.0, flange_thickness: float = 6.0, flange_bolt_R: float = 0.0, flange_bolt_n: int = 4, flange_bolt_d: float = 3.5, flange_bolt_phase: float = 0.0, flange_outer_n: int = 0, socket_length: float = 15.0, outer_target_R: float | None = None, outer_rect_w: float | None = None, outer_rect_h: float | None = None, target_slope: float | None = None, outer_target_slope: float | None = None, z_offset: float = 0.0, output_path: str | None = None) -> trimesh.Trimesh`

Assembles the complete throat adapter: driver interface + morphing transition.

**Driver interface positioning:** The adapter is centered on Z. The driver interface sits at `z = z_offset - adapter_length`, the horn throat sits at `z = z_offset`.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `driver_type` | `str` | — | `"flanged"` or a `THREAD_SPECS` key |
| `driver_diam` | `float \| None` | — | Driver exit diameter (for flanged only) |
| `thread_key` | `str \| None` | — | Thread spec key (for threaded only) |
| `horn_shape` | `str` | — | `"circular"`, `"rectangular"`, or `"polygonal"` |
| `rect_w` | `float` | — | Rectangular throat width (mm); unused for circular/polygonal |
| `rect_h` | `float` | — | Rectangular throat height (mm); unused for circular/polygonal |
| `poly_n_sides` | `int` | — | Polygon side count; unused for circular/rectangular |
| `poly_circumR` | `float` | — | Polygon circumradius at throat (mm); unused for circular/rectangular |
| `horn_R_eq` | `float` | — | Area-equivalent radius at horn throat (mm) |
| `adapter_length` | `float` | — | Transition length (mm) |
| `wall_thickness` | `float` | — | Wall thickness (mm) |
| `axial_steps` | `int` | `50` | Z slices for the loft |
| `flange_R` | `float` | `0.0` | Flange radius (flanged mode) |
| `flange_thickness` | `float` | `6.0` | Flange thickness (flanged mode) |
| `flange_bolt_R` | `float` | `0.0` | Bolt circle radius (flanged mode) |
| `flange_bolt_n` | `int` | `4` | Number of bolt holes |
| `flange_bolt_d` | `float` | `3.5` | Bolt hole diameter |
| `flange_bolt_phase` | `float` | `0.0` | Bolt pattern rotation (radians) |
| `flange_outer_n` | `int` | `0` | Outer polygon sides (0 = circular) |
| `socket_length` | `float` | `15.0` | Threaded socket depth (mm) |
| `outer_target_R` | `float \| None` | `None` | Outer equiv. radius for threaded mode (matches horn outer) |
| `outer_rect_w` | `float \| None` | `None` | Outer rect width (threaded mode) |
| `outer_rect_h` | `float \| None` | `None` | Outer rect height (threaded mode) |
| `target_slope` | `float \| None` | `None` | Inner equivalent-radius slope `dr/dz` at horn throat |
| `outer_target_slope` | `float \| None` | `None` | Outer equivalent-radius slope `dr/dz` at horn throat |
| `z_offset` | `float` | `0.0` | Z position of horn-throat end of transition |
| `output_path` | `str \| None` | `None` | Optional STL export path |

**Algorithm:**
1. Builds the adapter (transition + optional integrated threads) via `make_adapter()`.
2. For flanged mode: if `flange_R > 0`, imports `flange_generator.generate_flange` and creates a bolt flange at the driver interface, then booleans it with the adapter via `trimesh.boolean.union` (manifold engine).
3. Translates the full assembly so the horn-throat end is at `z = z_offset`.
4. Returns a single watertight `trimesh.Trimesh` (or `None` on failure).
