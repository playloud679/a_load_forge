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
    name: str          # e.g. '1⅜"-18'
    major_diam: float  # mm — outer thread diameter
    bore_diam: float   # mm — clear acoustic passage after the thread
    pitch: float       # mm
    tpi: float         # threads per inch (informational)
```

### `THREAD_SPECS: dict[str, ThreadSpec]`

| Key | Name | Major Diam (mm) | Acoustic Bore (mm) | Pitch (mm) | TPI |
|---|---|---|---|---|---|
| `"1_375in"` | 1⅜"-18 | 34.925 | 25.00 | 1.411 | 18 |

The nominal `1⅜"` dimension describes the female thread, not the acoustic opening. The integrated transition starts from a clear 25 mm bore.

---

## Embedded Morph Placement

### `embedded_morph_span(requested_length: float, safe_extent: float, desired_overlap: float = 6.0, min_transition: float = 0.5) -> tuple[float, float, float]`

Returns `(trim_length, overlap, target_length)` for the UI's embedded adapter
path. `safe_extent` is the end of the flare's safe advancing branch; the
adapter target is guaranteed not to pass it.

- On a long flare, the requested trim distance is preserved and the adapter
  follows the flare for the full desired overlap, up to 6 mm by default.
- When space is limited, the trim distance is shortened first to preserve the
  weld overlap.
- On very short flares, the overlap is reduced so
  `target_length <= safe_extent`.
- A flare whose safe extent is not greater than `min_transition` is rejected
  with `ValueError`, because it cannot contain a valid embedded transition.

---

## Private Helpers — 2-D Cross-Section Generation

All return `np.ndarray` of shape `(n, 2)` — XY points.

### `_circle_points(r: float, n: int = 64, phase: float = 0.0) -> np.ndarray`

Returns `n` equally-spaced points on a circle of radius `r`. First point is at `θ = phase`; default `phase = 0` gives the rightmost point `(r, 0)`. Polygonal adapters pass `phase = π/2` so the circular driver/socket rings and the target N-gon use the same vertex phase, preventing a helical twist through the transition.

### `_ellipse_points(rx: float, ry: float, n: int = 64) -> np.ndarray`

Returns `n` angularly spaced points on an ellipse with semi-axes `rx` and `ry`. Elliptical adapter targets use full UI axes `W`, `H` as `rx=W/2`, `ry=H/2`, with area-equivalent radius `sqrt(W·H)/2`.

### `_rect_points(hw: float, hh: float, n: int = 64, lockstep: bool = False) -> np.ndarray`

Returns `n` points on a rectangle of half-width `hw` and half-height `hh`. The four corners are **always anchored as exact vertices**: the perimeter is split at the start point + 4 corners into five arcs, and the `n` points are spread proportionally to arc length (≥1 interval per arc). A plain uniform-by-perimeter sampling only lands a vertex on every corner for a **square** (corner fractions `1/8, 3/8, 5/8, 7/8` → integer indices); for a non-square rectangle the corners fall *between* samples, so the connecting edge cuts across them and the morph renders a **chamfered corner** on both inner and outer walls. Anchoring the corners removes that bevel. Square output is unchanged (arcs `1:2:2:2:1` → counts `8,16,16,16,8`).

**`lockstep`** (default `False`): when `True` the per-arc point counts are fixed at the **square ratio `1:2:2:2:1`** regardless of `hw/hh`, instead of being proportional to arc length. Arc-length counts shift points between arcs as the aspect ratio changes, so **lofting or welding rings of varying aspect twists over the whole height** (jagged thin triangles up the wall). Lockstep keeps point `j` on the same arc at the same fraction across every ring → twist-free, while still anchoring the corners. Used for the embedded rect adapter weld: both the rect horn walls (`rectangular_horn.generate_rectangular_3d_mesh(perim_n=N)`) and the adapter sections sample with `lockstep=True` so the coincident weld surfaces share vertices. Single-section / short-morph uses keep `False` (arc-length gives finer sampling on the long edges).

**Perimeter ordering:** Starts at **mid-right** `(hw, 0)` and proceeds **counter-clockwise**:
1. Right edge, bottom→top: `(hw, 0)` → `(hw, hh)` 
2. Top edge, right→left: `(hw, hh)` → `(-hw, hh)`
3. Left edge, top→bottom: `(-hw, hh)` → `(-hw, -hh)`
4. Bottom edge, left→right: `(-hw, -hh)` → `(hw, -hh)`
5. Right edge bottom half: `(hw, -hh)` → `(hw, 0)`

This matched start point (mid-right = `θ=0` equivalent) ensures twist-free morphing lofts.

### `_poly_points(n_sides: int, circumradius: float, n: int = 64) -> np.ndarray`

Returns `n` points on a regular N-gon (convex polygon), distributed evenly along the perimeter.

- Vertices use the same `θ = k × 2π/N + π/2` phase as `polygonal_horn.py`, so the adapter's polygonal throat is rotationally aligned with the flare. The first vertex is always on the positive Y axis; do not use `π/N` here, because that rotates the adapter relative to the polygonal horn and creates visible corner slivers at the weld.
- When `n >= n_sides`, every true polygon corner is forced into the returned ring even if `n` is not divisible by `n_sides`. The remaining points are spread per edge. This matters for the UI's dense adapter rings (`rings_n`, often 160): uniform perimeter sampling can miss the real corners and create small chamfers/sliver triangles exactly on the polygon vertices.
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

### `_hermite_radius(t: float, r0: float, r1: float, length: float, slope1: float | None, slope0: float = 0.0, curv1: float | None = None, curv0: float = 0.0) -> float`

Equivalent-radius progression with optional end slope and curvature. With only `slope1` → **cubic** Hermite (C1). With `curv1` → **quintic** Hermite that additionally matches second derivative (C2), removing the inflection line at the adapter↔flare join.

---

## Golden-Standard Circle→Ellipse Morph

### `morph_circle_to_ellipse(throat_radius: float = 12.7, throat_angle_deg: float = 7.5, transition_length_z: float = 30.0, target_ellipse_a: float = 40.0, target_ellipse_b: float = 20.0, z_steps: int = 100) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]`

Morph a circular throat into an elliptical cross-section over Z. **Area-first design:** the cross-sectional area expansion `A(z) = π·r_eq(z)²` is the primary acoustic driver; the shape (circle→ellipse) adapts to the area, not the other way around.

**Returns** `(z, a, b, r_eq)` — four 1‑D arrays of length `z_steps`:
- `z` — Z positions (mm)
- `a` — semi-major axis at each Z (mm)
- `b` — semi-minor axis at each Z (mm)
- `r_eq` — equivalent radius `r_eq(z) = sqrt(A(z)/π)` (mm)

**Algorithm:**

| Component | Method | Properties |
|---|---|---|
| `r_eq(z)` | Quintic Hermite polynomial | C² continuous (smooth first & second derivatives), monotonically increasing |
| `R(z) = a(z)/b(z)` | Quintic smoothstep | Transitions from 1 (circle) to `target_a/target_b` with zero 1st & 2nd derivatives at both ends |
| `a(z)` | `r_eq(z) · √R(z)` | Enforces Golden Standard area rule at every slice |
| `b(z)` | `r_eq(z) / √R(z)` | |

**Boundary conditions at z=0 (driver exit):**
- `r_eq(0) = throat_radius` — matches 0.5" (12.7 mm) 1-inch throat
- `dr_eq/dz(0) = tan(throat_angle_deg)` — first-derivative continuity with driver exit cone; default 7.5° matches standard 1" compression drivers (Beyma/B&C)
- `d²r_eq/dz²(0) = 0` — smooth launch
- `R(0) = 1` → `a(0) = b(0) = throat_radius` — perfect circle

**Boundary conditions at z=L (waveguide handoff):**
- `r_eq(L) = sqrt(target_a · target_b)` — area-equivalent radius of target ellipse
- `dr_eq/dz(L) = d²r_eq/dz²(L) = 0` — smooth, flat handoff to waveguide
- `R(L) = target_a / target_b` → `a(L) = target_a`, `b(L) = target_b`

**Verification:** Run `python src/throat_adapter.py` to produce a 6‑panel Matplotlib figure verifying area slope `dA/dz` has no spike/drop at z=0, the tangent matches the throat angle, and the morphing is C²-smooth throughout.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `throat_radius` | `float` | `12.7` | Circular throat radius (mm). Default = 0.5" = 12.7 mm. |
| `throat_angle_deg` | `float` | `7.5` | Throat half-angle (degrees). `dr_eq/dz\|_{z=0} = tan(θ)`. Standard for 1" drivers. |
| `transition_length_z` | `float` | `30.0` | Transition length (mm) |
| `target_ellipse_a` | `float` | `40.0` | Target semi-major axis at z=L (mm) |
| `target_ellipse_b` | `float` | `20.0` | Target semi-minor axis at z=L (mm) |
| `z_steps` | `int` | `100` | Number of Z positions to generate |

---

## Public API

### `make_adapter(driver_R: float, horn_shape: str, horn_w: float, horn_h: float, horn_n_sides: int, horn_R_eq: float, horn_circumR: float, axial_steps: int, adapter_length: float, wall_thickness: float, thread_key: str | None = None, socket_length: float = 0.0, collar_overlap: float = 5.0, outer_target_R: float | None = None, outer_rect_w: float | None = None, outer_rect_h: float | None = None, target_slope: float | None = None, outer_target_slope: float | None = None, target_curv: float | None = None, outer_target_curv: float | None = None, custom_pts: np.ndarray | None = None, custom_outer_pts: np.ndarray | None = None, custom_pts_z: np.ndarray | None = None, custom_match_from_z: float | None = None, return_cutter: bool = False, output_path: str | None = None) -> trimesh.Trimesh | tuple[trimesh.Trimesh, trimesh.Trimesh]`

Builds the morphing transition section, optionally with an integrated threaded extension at the circular (driver) end.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `driver_R` | `float` | Radius of the circular driver exit (mm) |
| `horn_shape` | `str` | `"circular"`, `"elliptical"`, `"rectangular"`, `"polygonal"`, or `"custom"` |
| `horn_w` | `float` | Throat width/full ellipse major axis (mm); unused for circular/polygonal |
| `horn_h` | `float` | Throat height/full ellipse minor axis (mm); unused for circular/polygonal |
| `horn_n_sides` | `int` | Number of polygon sides (for `"polygonal"`); unused for circular/rectangular |
| `horn_R_eq` | `float` | Area-equivalent radius at horn throat (mm) |
| `horn_circumR` | `float` | Circumradius of the polygon at horn throat (mm); unused for circular/rectangular |
| `axial_steps` | `int` | Number of Z slices for the loft |
| `adapter_length` | `float` | Axial length of the transition (mm) |
| `wall_thickness` | `float` | Wall thickness for outer offset (mm) |
| `thread_key` | `str \| None` | One of `THREAD_SPECS` keys — enables threaded mode |
| `socket_length` | `float` | Depth of the threaded section (mm), must be > 0.5 to activate threads |
| `collar_overlap` | `float` | Threaded mode only (default 5.0): the socket's outer cylinder continues this many mm ABOVE the throat plane, wrapping the cone wall, then tapers at 45° until it merges into the flare outer skin — a printable lap joint instead of the bare butt joint at z=0. Outer wall only; the airway is untouched. Clamped to half the smooth-morph span so the taper always lands before the handoff plane. `0` disables it |
| `outer_target_R` | `float \| None` | Outer equivalent radius for threaded mode outer profile (matches horn outer dimensions) |
| `outer_rect_w` | `float \| None` | Outer rectangle width (threaded mode) |
| `outer_rect_h` | `float \| None` | Outer rectangle height (threaded mode) |
| `target_slope` | `float \| None` | Inner equivalent-radius slope `dr/dz` at the horn throat; when set, the adapter reaches the flare with matching expansion derivative |
| `outer_target_slope` | `float \| None` | Outer equivalent-radius slope `dr/dz` at the horn throat, computed from the same parallel-offset wall as the horn mesh |
| `target_curv` | `float \| None` | Inner equivalent-radius curvature `d²r/dz²` at the horn throat; upgrades the inner raccordo to quintic Hermite (C2) |
| `outer_target_curv` | `float \| None` | Outer equivalent-radius curvature `d²r/dz²` at the horn throat; upgrades the outer raccordo to quintic Hermite (C2) |
| `custom_pts` | `np.ndarray \| None` | Exact target inner section(s): either a single `(m, 2)` closed polygon at the handoff plane, or a `(K, m, 2)` **stack** of sections at the `custom_pts_z` stations. Required for `horn_shape="custom"` and used by every UI embedded-adapter path to reproduce the real flare through the overlap |
| `custom_outer_pts` | `np.ndarray \| None` | Matching **outer-wall** contour(s) (same shape as `custom_pts`). The outer wall blends from the plain miter offset into the exact contour, then follows it exactly from `custom_match_from_z` |
| `custom_pts_z` | `np.ndarray \| None` | Local-z stations (0 = driver plane … `adapter_length` = handoff plane) for a `(K, m, 2)` stack; the last station must be the handoff plane. Ignored for a single `(m, 2)` section |
| `custom_match_from_z` | `float \| None` | Start of the weld overlap. With a section stack, the adapter reaches the exact stacked inner/outer contours at this Z and follows them through the rest of the overlap |
| `return_cutter` | `bool` | If True, returns a tuple `(adapter_mesh, cutter_mesh)` where `cutter_mesh` is the solid inner airway, useful for boolean subtraction from the horn throat. |
| `output_path` | `str \| None` | Optional STL export path |

**Custom section mode (`horn_shape="custom"`):** built for the **OS-SE** flare,
whose cross-section is *not* an ellipse (elliptical-cone coverage under a square
root, plus the superellipse mouth morph). Targeting an area-matched ellipse
there left a visible **step ring** (~0.5 mm, max on the diagonals) at the
adapter↔flare junction. With `custom_pts` the adapter ends vertex-exact on the
real `r(z,φ)` contour. Pass a **stack** (`custom_pts_z`) and the overlap start
(`custom_match_from_z`): the adapter completes its morph at that plane, then
follows the real flare exactly — aspect-ratio change included — through up to
6 mm of weld overlap, dynamically reduced on short flares (a single uniformly
scaled end section still left a ~0.06 mm step,
because the OS-SE aspect ratio changes with z). `custom_outer_pts` fixes the
*outer* skin too: the OS-SE engine offsets along the true 3-D normal, whose
in-plane wall is `thickness/cos(slope)` — wider than the 2-D miter offset the
adapter uses, so without it the outer wall also stepped at the join. The UI
additionally builds the horn mesh on the **same `(nz, nphi)` grid** it samples
the sections from, so the adapter ring sits exactly on the horn facets
(measured residual ≤ 0.005 mm). Tests: `OS-SE adapter ends on exact r(z,φ)
section` and `OS-SE embedded adapter welds with no junction step`.

**Raccordo / expansion continuity:** The shape morph and acoustic area progression are controlled separately. For ordinary untargeted transitions the shape blend uses a quintic smoothstep, so it has zero shape-change derivative at the horn throat. With `custom_match_from_z`, the smooth morph ends at the overlap start using the stacked flare's local equivalent radius, slope, and curvature; every later slice is copied from the real inner/outer contour stack. The equivalent radius uses **cubic** Hermite interpolation when only a target slope is available, or **quintic** Hermite when curvature is also available, matching the flare C1/C2 at the start of the exact overlap.

**Algorithm — Three modes:**

**A. Threaded mode** (`thread_key` is not None AND `socket_length > 0.5`):
1. Z range: `[-thread_len, adapter_length]` where `thread_len = n_turns * pitch`
2. **Thread section** (`z < 0`): 1⅜"-18 circular socket with sinusoidal thread profile `r_thread = major_R − (major_R − minor_R) · 0.5 · (1 − cos(2π · turn_frac))`. Outer wall is a smooth cylinder at `outer_R = major_R + wall_thickness`.
3. **Acoustic handoff** (`z = 0`): the inner passage reduces to the specified 25 mm bore.
4. **Transition section** (`z ≥ 0`): Inner morphs from the 25 mm bore to the inner target via `_morph_slice`; the outer is a true **parallel (miter) offset** of that inner via `_offset_polygon_outward(inner, wall_thickness)`. The threaded collar (outer `≈ major_R + wt`) therefore steps down to a thin-walled funnel at `z = 0`.

**B. Flanged mode** (`thread_key` is None):
1. Z range: `[0, adapter_length]`
2. Inner profile morphs from `driver_R` to inner target via `_morph_slice`.
3. Outer profile is a true outward-**normal (miter) offset** of the inner via `_offset_polygon_outward(inner, wall_thickness)`.

**Constant-thickness wall (both modes):** the transition outer is *always* a parallel offset of the morphed inner, so the wall is exactly `wall_thickness` thick on every axis and the airway behind it stays hollow. This is also inherently **flush** with the horn at the join — the horn's own outer wall is the same constant offset of the same inner profile, so matching the inner slope/curvature (C1/C2) makes the outer match too. An earlier design morphed the outer *independently* toward the horn's area-equivalent outer; for an elongated (non-square) rectangular target the area-preserving intermediate is rounder than the final shape, so the **narrow axis of the outer overshot more than the inner did and packed the wall solid** between the threaded collar/flange and the flare ("lo spazio tra flangia e flare non deve essere pieno"). The `outer_target_*` / `outer_rect_*` / `outer_target_slope` / `outer_target_curv` parameters are still accepted for signature/back-compat but no longer drive the wall.

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

### `make_adapter_assembly(driver_type: str, driver_diam: float | None, thread_key: str | None, horn_shape: str, rect_w: float, rect_h: float, poly_n_sides: int, poly_circumR: float, horn_R_eq: float, adapter_length: float, wall_thickness: float, axial_steps: int = 50, flange_R: float = 0.0, flange_thickness: float = 6.0, flange_bolt_R: float = 0.0, flange_bolt_n: int = 4, flange_bolt_d: float = 3.5, flange_bolt_phase: float = 0.0, flange_outer_n: int = 0, driver_clearance: float = 0.3, socket_length: float = 15.0, collar_overlap: float = 5.0, outer_target_R: float | None = None, outer_rect_w: float | None = None, outer_rect_h: float | None = None, target_slope: float | None = None, outer_target_slope: float | None = None, target_curv: float | None = None, outer_target_curv: float | None = None, custom_pts: np.ndarray | None = None, custom_outer_pts: np.ndarray | None = None, custom_pts_z: np.ndarray | None = None, custom_match_from_z: float | None = None, z_offset: float = 0.0, return_cutter: bool = False, output_path: str | None = None) -> trimesh.Trimesh | tuple[trimesh.Trimesh, trimesh.Trimesh]`

Assembles the complete throat adapter: driver interface + morphing transition.

**Driver interface positioning:** The adapter is centered on Z. The driver interface sits at `z = z_offset - adapter_length`, the horn throat sits at `z = z_offset`.

When the driver interface includes a flange, the flange overlaps the first portion of the requested length while the transition keeps the full `adapter_length`. This keeps the throat↔flare raccordo uncompressed and measures the visible assembly length from the flange's lower face.

**UI embedded-morph behavior:** `ui_app.py` uses this positioning API to place the driver end on the original throat plane and the horn-shape end inside the flare. It trims away the original first `adapter_length` millimetres and targets the actual profile dimensions and derivatives at the handoff. Therefore the morph changes shape without increasing the horn's mouth position or acoustic depth. A flange or threaded socket remains a mechanical attachment and may extend behind the original throat plane.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `driver_type` | `str` | — | `"flanged"`, a `DRIVER_FLANGE_SPECS` bolt-on key, or a `THREAD_SPECS` key |
| `driver_diam` | `float \| None` | — | Driver exit diameter (for flanged only) |
| `thread_key` | `str \| None` | — | Thread spec key (for threaded only) |
| `horn_shape` | `str` | — | `"circular"`, `"elliptical"`, `"rectangular"`, `"polygonal"`, or `"custom"` |
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
| `driver_clearance` | `float` | `0.3` | Added to a standard bolt-on preset's nominal throat diameter |
| `socket_length` | `float` | `15.0` | Threaded socket depth (mm) |
| `collar_overlap` | `float` | `5.0` | Lap collar above the throat plane in threaded mode (see `make_adapter`); `0` = legacy butt joint |
| `outer_target_R` | `float \| None` | `None` | Outer equiv. radius for threaded mode (matches horn outer) |
| `outer_rect_w` | `float \| None` | `None` | Outer rect width (threaded mode) |
| `outer_rect_h` | `float \| None` | `None` | Outer rect height (threaded mode) |
| `target_slope` | `float \| None` | `None` | Inner equivalent-radius slope `dr/dz` at horn throat |
| `outer_target_slope` | `float \| None` | `None` | Outer equivalent-radius slope `dr/dz` at horn throat |
| `target_curv` | `float \| None` | `None` | Inner equivalent-radius curvature `d²r/dz²` at horn throat (quintic C2 raccordo) |
| `outer_target_curv` | `float \| None` | `None` | Outer equivalent-radius curvature `d²r/dz²` at horn throat (quintic C2 raccordo) |
| `custom_pts` | `np.ndarray \| None` | `None` | Exact target inner section(s) for `horn_shape="custom"` — passed through to `make_adapter` (see above; used for OS-SE) |
| `custom_outer_pts` | `np.ndarray \| None` | `None` | Exact outer-wall contour(s) for `horn_shape="custom"` — passed through to `make_adapter` |
| `custom_pts_z` | `np.ndarray \| None` | `None` | Local-z stations for a `(K, m, 2)` `custom_pts` stack — passed through to `make_adapter` |
| `custom_match_from_z` | `float \| None` | `None` | Start of exact stacked-contour matching / weld overlap — passed through to `make_adapter` |
| `z_offset` | `float` | `0.0` | Z position of horn-throat end of transition |
| `return_cutter` | `bool` | `False` | If True, returns `(assembly, cutter_mesh)` |
| `output_path` | `str \| None` | `None` | Optional STL export path |

**Algorithm:**
1. Builds the adapter (transition + optional integrated threads) via `make_adapter()`.
2. For custom flanged mode: if `flange_R > 0`, creates a custom bolt flange. For a standard bolt-on `driver_type`, loads the fixed industrial pattern from `flange_generator.DRIVER_FLANGE_SPECS` and creates it via `generate_driver_mounting_flange()`. The adapter rotates the 2-hole preset vertical (`+π/2`) and computes a phase override for the asymmetric 3-hole preset by maximizing the minimum distance between the bolt holes and the adapter's outer flare contour; this keeps screws away from the tighter side of non-round throats. The flange overlaps the first portion of the transition so the overall length still measures from the flange bottom face without compressing the morph.
3. Translates the full assembly so the horn-throat end is at `z = z_offset`.
4. Returns a single watertight `trimesh.Trimesh` (or `None` on failure).

**Flange bore weld bite (custom flanged mode):** the custom flange's bore is set to
`driver_R + max(driver_clearance/2, wall_thickness) − _FLANGE_WELD_BITE`. The
subtracted **`_FLANGE_WELD_BITE` (module constant, 0.5 mm)** is essential: the adapter
outer wall is a *miter-offset polygon*, so at the driver plane its radius is
`driver_R + wall_thickness` only at the edge midpoints and slightly larger at the
vertices. A bore at exactly `driver_R + wall_thickness` is therefore ~tangent
(≈0.02 mm overlap), and the manifold union then emits a **ring of sliver triangles
at `r ≈ bore`, `z = 0`** that the slicer renders as surface "irregolarità" on the
flange face (measured 21 faces < 1e-5 mm², 97 < 1e-3 mm²). Biting the bore 0.5 mm
inside the wall turns the tangency into a clean interpenetration → **0 slivers** for
circular and elliptical custom-stack flanges; the bore still clears the airway by the
full wall thickness, so nothing protrudes into the passage. Bolt-on flanges are
unaffected (their bore is cut by the actual airway `cutter_tm`, not a fixed radius);
threaded mode has no flange union (the collar is built into the mesh). For the
standard bolt-on presets, the adapter rotates the 2-hole pattern by `+π/2`
and searches the 3-hole phase against the final outer contour, choosing the
rotation with the largest minimum screw clearance. Regression test:
`flanged adapter bore has no sliver ring`.
