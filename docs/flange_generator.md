# `flange_generator.py` — Parametric Circular & Polygonal Flanges

**Path:** `src/flange_generator.py`

---

## Imports

| Library | Symbols Used |
|---|---|
| `logging` | `getLogger` |
| `sys` | `path` |
| `pathlib` | `Path` |
| `numpy` | `np` |
| `trimesh` | `Trimesh`, `boolean`, `creation` |
| `shapely.geometry` | `Polygon` |

---

## Legacy Defaults (module-level constants)

```python
OUTER_DIAM   = 60.0   # mm
INNER_DIAM   = 29.0   # mm
THICKNESS    = 6.0    # mm
BOLT_RADIUS  = 22.0   # mm
BOLT_COUNT   = 4
BOLT_DIAM    = 3.5    # mm
```

---

## Standard compression-driver bolt-on flanges

### `DriverFlangeSpec`

Immutable industrial mounting pattern with nominal throat diameter, outer
diameter, bolt count, bolt-hole diameter, PCD, and bolt-pattern phase.

### `DRIVER_FLANGE_SPECS`

| Key | Pattern | Nominal throat | Outer Ø | Holes | Hole Ø | PCD |
|---|---|---:|---:|---:|---:|---:|
| `bolt_on_1in_2` | 1" bolt-on, horizontal 2-hole | 25.4 mm | 100 mm | 2 | 6.5 mm | 76.2 mm |
| `bolt_on_1in_3` | 1" bolt-on, 3-hole | 25.4 mm | 90 mm | 3 | 6.5 mm | 57.2 mm |
| `bolt_on_1_4in_4` | 1.4" bolt-on, 4-hole cross | 35.6 mm | 135 mm | 4 | 6.5 mm | 101.6 mm |
| `bolt_on_2in_4` | 2" bolt-on, 4-hole cross | 50.8 mm | 135 mm | 4 | 6.5 mm | 101.6 mm |

### `driver_mounting_hole_centers(driver_type: str) -> np.ndarray`

Returns the XY centres of the selected standard bolt pattern. With the default
phase, the 2-hole pattern lies on the horizontal X axis and the 4-hole pattern
forms a cross.

### `generate_driver_mounting_flange(driver_type: str, thickness: float = 6.0, throat_clearance: float = 0.3, offset: float = 0.0, seg: int = 96, output_path: str | None = None, bolt_phase: float | None = None) -> trimesh.Trimesh | None`

Generates the selected standard circular flange using `generate_flange()`.
The central through-hole diameter is `nominal throat + throat_clearance`; outer
diameter, M6 clearance holes, PCD, count, and angular layout remain fixed by
the industrial preset unless `bolt_phase` is supplied. Adapter assemblies use
that override to rotate the 2-hole preset vertical and to rotate the 3-hole
preset toward the flare contour with the largest screw clearance. The default
0.3 mm clearance turns a nominal 25.4 mm 1" throat into a 25.7 mm printed bore.

---

## `generate_flange(throat_R: float, flange_R: float, thickness: float = 6.0, bolt_R: float = 22.0, bolt_n: int = 4, bolt_d: float = 3.5, offset: float = 0.0, seg: int = 64, output_path: str | None = None, outer_n_sides: int = 0, bolt_phase: float = 0.0) -> trimesh.Trimesh | None`

Generates a circular-inner flange via CSG boolean difference.

**Coordinate system:** The flange sits with its **TOP face** at `z = offset` and grows **downward** in negative Z (`z_bottom = offset - thickness`). The inner hole is centered on the Z axis.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `throat_R` | `float` | — | Radius of the circular inner hole (matches horn throat, mm) |
| `flange_R` | `float` | — | Radius of the outer disc / circumradius of the outer polygon (mm) |
| `thickness` | `float` | `6.0` | Flange thickness in Z (mm) |
| `bolt_R` | `float` | `22.0` | Bolt circle radius (mm) |
| `bolt_n` | `int` | `4` | Number of bolt holes |
| `bolt_d` | `float` | `3.5` | Diameter of each bolt hole (mm) |
| `offset` | `float` | `0.0` | Z position of the top face (see coordinate system above) |
| `seg` | `int` | `64` | Circumferential segments for cylinders |
| `output_path` | `str \| None` | `None` | Optional STL export path |
| `outer_n_sides` | `int` | `0` | Outer body shape: `0` = circular disc; `≥3` = regular N-gon prism |
| `bolt_phase` | `float` | `0.0` | Angular offset (radians) applied to the bolt pattern rotation |

**Algorithm:**

1. **Outer body construction:**
   - **Circular** (`outer_n_sides = 0`): A `trimesh.creation.cylinder` of radius `flange_R`, height `thickness`, centered at `z = offset - thickness/2`.
   - **Polygonal** (`outer_n_sides ≥ 3`): A regular N-gon prism extruded from `shapely.geometry.Polygon`. The polygon vertices are at `flange_R · (cos θ, sin θ)` with `θ = linspace(0, 2π, N) + π/2` (first face edge is vertical, so the flat aligns with the horizontal). 

2. **`_flange_R_from_ring` concept for polygonal outer:**
   When `outer_n_sides ≥ 3`, `flange_R` is the **circumradius** of the N-gon. The minimum wall thickness (at the flat faces) is given by the **inradius**: `inradius = flange_R · cos(π / N)`. If the user requests a polygonal outer body, `flange_R` is clamped to `max(flange_R, throat_R / cos(π/N) + 1)` to ensure the inner circular hole fits with at least 1 mm margin. Similarly, `bolt_R` is clamped to `min(bolt_R, flange_R · cos(π/N) − bolt_d/2 − 1)` to keep bolt holes inside the inradius.

3. **Subtraction bodies:**
   - **Throat hole:** A cylinder of radius `throat_R`, height `thickness + 2` (extra for clean boolean cut).
   - **Bolt holes:** For each of `bolt_n` bolts, a cylinder of radius `bolt_d/2` at position `(bolt_R · cos(θ_k + bolt_phase), bolt_R · sin(θ_k + bolt_phase))` where `θ_k = 2πk/bolt_n`. Uses 12 segments per hole.

4. **Boolean difference:** `trimesh.boolean.difference([disc] + to_sub, engine="manifold")`. The outer disc is the positive body; all subtraction bodies are unioned and removed.

5. **Cleanup:** `remove_unreferenced_vertices()`, `update_faces(nondegenerate_faces())`, `fix_normals()`.

**Returns:** A `trimesh.Trimesh` (watertight flange) or `None` if the boolean operation fails.

---

## `generate_polygonal_flange(inner_circumR: float, n_sides: int, flange_R: float, thickness: float = 6.0, bolt_R: float = 22.0, bolt_n: int = 4, bolt_d: float = 3.5, offset: float = 0.0, seg: int = 64, output_path: str | None = None, outer_n_sides: int = 0, bolt_phase: float = 0.0, inner_fillet: float = 0.0) -> trimesh.Trimesh | None`

Generates a flange with a polygonal (N-gon) inner hole matching the horn cross-section.

Same coordinate system as `generate_flange`: top face at `z = offset`, grows downward.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `inner_circumR` | `float` | — | Circumradius of the N-gon inner hole (mm) |
| `n_sides` | `int` | — | Number of sides of the inner hole (matches horn polygon) |
| `flange_R` | `float` | — | Outer boundary circumradius (mm) |
| `thickness` | `float` | `6.0` | Flange thickness in Z (mm) |
| `bolt_R` | `float` | `22.0` | Bolt circle radius (mm) |
| `bolt_n` | `int` | `4` | Number of bolt holes |
| `bolt_d` | `float` | `3.5` | Bolt hole diameter (mm) |
| `offset` | `float` | `0.0` | Z position of the top face |
| `seg` | `int` | `64` | Circumferential segments for cylinders |
| `output_path` | `str \| None` | `None` | Optional STL export path |
| `outer_n_sides` | `int` | `0` | Outer body shape: `0` = circular disc; `≥3` = regular N-gon prism |
| `bolt_phase` | `float` | `0.0` | Angular offset (radians) for bolt pattern |
| `inner_fillet` | `float` | `0.0` | Corner fillet radius of the hole — matches a **rounded** polygonal horn section (`polygonal_horn.rounded_polygon_ring`, `arc_seg=16`). `inner_circumR` then means **across corners**; hole core circumradius = `inner_circumR − inner_fillet`. `0` = sharp N-gon hole (legacy). |

**Algorithm:**

1. **Outer body:** Same as `generate_flange` (circular cylinder or polygon prism). For polygonal outer, `flange_R` is clamped to `max(flange_R, inner_circumR / cos(π/outer_n_sides) + 1)` (valid for the rounded hole too — across-corners is its max extent).

2. **Bolt clamping:** For polygonal outer, `bolt_R ≤ inradius - bolt_d/2 - 1`. For circular outer, `bolt_R ≤ flange_R - bolt_d/2 - 1`.

3. **Inner hole subtraction:** An N-gon prism is extruded from `shapely.geometry.Polygon` with vertices at `inner_circumR · (cos θ, sin θ)` where `θ = linspace(0, 2π, n_sides) + π/2` (same rotation as the horn); with `inner_fillet > 0` the vertices come from `rounded_polygon_ring` instead. Extruded `thickness + 2` and translated to overlap the flange body.

4. **Bolt holes:** Same as `generate_flange`, placed on the bolt circle with `bolt_phase` offset.

5. **Boolean difference** via manifold engine, same cleanup.

**Returns:** A `trimesh.Trimesh` (watertight flange) or `None` if the boolean operation fails.

---

## `generate_profile_flange(...) -> trimesh.Trimesh | None`

Common outward-flange generator used by the UI for **Mouth** and **Mid**. The
throat flange continues to use the legacy generators above.

- Inner opening types: `circular`, `polygonal`, `rectangular`, `elliptical`.
- `inner_fillet` / `outer_fillet` round the corners of a **polygonal**
  inner/outer shape (rounded regular N-gon matching the rounded polygonal horn
  section). `inner_R` / `outer_diam` keep their across-corners meaning; the
  rounded shape's core circumradius is `R − fillet`.
- `outer_mode="offset"` automatically follows the opening shape and grows it by
  `outer_offset`. For **elliptical** inner openings — and for **polygonal ones
  with `inner_fillet > 0`** — this produces a **true geometric offset**
  (parallel curve via Shapely `buffer()`), giving constant ring width all
  around — not a scaled copy of the inner shape.
- `outer_mode="custom"` accepts `circular`, `polygonal`, or `rectangular`
  explicit outer dimensions.
- `bolt_mode="auto"` places every hole halfway between the **actual** inner and
  outer Shapely boundaries along its radial direction. For elliptical offsets,
  it uses the true half-offset curve `inner.buffer(outer_offset/2)` instead of
  falling back to a scaled-ellipse approximation.
- `bolt_mode="fixed"` places every hole on the requested `bolt_R`, clamped to a
  conservative range that clears both opening and outer boundary.
- The top face is at `offset`; the flange grows downward, matching
  `generate_flange()` and `generate_polygonal_flange()`.

The function builds centered Shapely polygons, extrudes the outer plate, and
subtracts the opening and bolt cylinders with the manifold boolean engine.

---

## `generate_contour_flange(inner_xy, thickness, bolt_n, bolt_d, offset, wall=0.0, ring=15.0, bite=0.5, bolt_R=0.0, bolt_phase=0.0, output_path=None, outer_xy=None) -> trimesh.Trimesh | None`

Mounting flange around an **arbitrary closed contour** instead of a
circle/ellipse/rectangle. The UI uses it for the **OS-SE** waveguide and for
elliptical-section throat/mouth/mid flanges, which are generated from real mesh
sections rather than fitted/scaled W×H ellipses.

- `inner_xy` — the airway (inner-wall) contour, `(N, 2)`, in the flange plane.
- Hole = `inner_xy` buffered **inward** by `bite` (the constant-thickness wall
  pokes through and fuses).
- Outer body = `inner_xy` buffered **outward** by `wall + ring` (`wall` clears
  the wall, `ring` is the bolting land).
- Optional `outer_xy` replaces the buffered outer boundary. The UI uses it for
  elliptical inward roll-back plates so the rim-inset hole and rim outline
  follow real horn sections instead of scaled ellipses.
- Bolts are spaced evenly **by arc length** along the mid-line of the land
  (`inner.buffer(wall + ring/2)`), so they follow the contour shape.
- Top face at `offset`, grows down by `thickness` (same convention as the other
  flanges). Built with Shapely buffers + manifold boolean.

---

## `generate_throat_chamfer(base_xy, top_xy, base_z, height, width, overlap=0.35, tip=0.35, samples=128, output_path=None) -> trimesh.Trimesh | None`

Weld-reinforcement chamfer ring that bridges a flange top to the horn body.

**Cross-section (radial slice):**

```
    top_inner (top_xy)              top_outer (top_xy + tip·width)
    |                               |
    |  inner wall (on horn body)    |  outer wall (sloped)
    |                               |
    bottom_inner                    bottom_outer
  (base_xy − overlap·width)     (base_xy + width)
```

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `base_xy` | `(N, 2)` | — | Outer contour of the horn at flange-top level (z = base_z) |
| `top_xy` | `(N, 2)` | — | Outer contour of the horn at higher z (z = base_z + height) |
| `base_z` | `float` | — | Z of the bottom face (flange top) |
| `height` | `float` | — | Axial extent of the chamfer (mm) |
| `width` | `float` | — | Radial extent of the chamfer foot on the flange (mm) |
| `overlap` | `float` | `0.35` | Fraction of width that bites inward for fusion |
| `tip` | `float` | `0.35` | Fraction of width for outer-wall offset at top edge |
| `samples` | `int` | `128` | Circumferential vertex count per ring (≥ 16) |
| `output_path` | `str \| None` | `None` | Optional STL export path |

**Non-manifold root causes:**

1. **`tip == 0`** → top-inner ≡ top-outer → top cap collapses to a line; three faces meet at every top edge without a closing cap → non-manifold.  Internally clamped to `≥ 0.01`.

2. **`overlap · width` too large** for a small contour → Shapely `buffer(-d)` collapses the polygon → inner ring is empty → returns `None`.

3. **Non-convex or self-intersecting contours** (e.g. OS-SE ridges) → Shapely `buffer(+d)` can self-intersect; duplicate/crossing vertices break loft triangulation.

4. **Winding order mismatch** between `base_xy` and `top_xy` → loft faces twist and self-intersect.  Both are normalised to CCW internally.

**Algorithm:** Resamples both contours to `samples` CCW points, creates 4 rings (bottom outer/inner, top outer/inner), builds a loft with quad strips, caps both ends, and returns a watertight `trimesh.Trimesh`.

---

## Bolt Phase Parameter

The `bolt_phase` parameter (in radians) rotates the entire bolt hole pattern around the Z axis. By default `bolt_phase = 0.0`, which places the first bolt at angle 0 (along the +X axis). For a polygon with `outer_n_sides ≥ 3`, the polygon's first face edge is vertical (vertex at `π/2` offset), so the bolt pattern is independent of the polygon rotation unless `bolt_phase` is set to align them.
