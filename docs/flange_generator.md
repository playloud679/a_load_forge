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

### `generate_driver_mounting_flange(driver_type: str, thickness: float = 6.0, throat_clearance: float = 0.3, offset: float = 0.0, seg: int = 96, output_path: str | None = None) -> trimesh.Trimesh | None`

Generates the selected standard circular flange using `generate_flange()`.
The central through-hole diameter is `nominal throat + throat_clearance`; outer
diameter, M6 clearance holes, PCD, count, and angular layout remain fixed by
the industrial preset. The default 0.3 mm clearance turns a nominal 25.4 mm
1" throat into a 25.7 mm printed bore.

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

## `generate_polygonal_flange(inner_circumR: float, n_sides: int, flange_R: float, thickness: float = 6.0, bolt_R: float = 22.0, bolt_n: int = 4, bolt_d: float = 3.5, offset: float = 0.0, seg: int = 64, output_path: str | None = None, outer_n_sides: int = 0, bolt_phase: float = 0.0) -> trimesh.Trimesh | None`

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

**Algorithm:**

1. **Outer body:** Same as `generate_flange` (circular cylinder or polygon prism). For polygonal outer, `flange_R` is clamped to `max(flange_R, inner_circumR / cos(π/outer_n_sides) + 1)`.

2. **Bolt clamping:** For polygonal outer, `bolt_R ≤ inradius - bolt_d/2 - 1`. For circular outer, `bolt_R ≤ flange_R - bolt_d/2 - 1`.

3. **Inner hole subtraction:** An N-gon prism is extruded from `shapely.geometry.Polygon` with vertices at `inner_circumR · (cos θ, sin θ)` where `θ = linspace(0, 2π, n_sides) + π/2` (same rotation as the horn). Extruded `thickness + 2` and translated to overlap the flange body.

4. **Bolt holes:** Same as `generate_flange`, placed on the bolt circle with `bolt_phase` offset.

5. **Boolean difference** via manifold engine, same cleanup.

**Returns:** A `trimesh.Trimesh` (watertight flange) or `None` if the boolean operation fails.

---

## `generate_profile_flange(...) -> trimesh.Trimesh | None`

Common outward-flange generator used by the UI for **Mouth** and **Mid**. The
throat flange continues to use the legacy generators above.

- Inner opening types: `circular`, `polygonal`, `rectangular`, `elliptical`.
- `outer_mode="offset"` automatically follows the opening shape and grows it by
  `outer_offset`.
- `outer_mode="custom"` accepts `circular`, `polygonal`, or `rectangular`
  explicit outer dimensions.
- `bolt_mode="auto"` places every hole halfway between the inner and outer
  boundary along its radial direction.
- `bolt_mode="fixed"` places every hole on the requested `bolt_R`, clamped to a
  conservative range that clears both opening and outer boundary.
- The top face is at `offset`; the flange grows downward, matching
  `generate_flange()` and `generate_polygonal_flange()`.

The function builds centered Shapely polygons, extrudes the outer plate, and
subtracts the opening and bolt cylinders with the manifold boolean engine.

---

## Bolt Phase Parameter

The `bolt_phase` parameter (in radians) rotates the entire bolt hole pattern around the Z axis. By default `bolt_phase = 0.0`, which places the first bolt at angle 0 (along the +X axis). For a polygon with `outer_n_sides ≥ 3`, the polygon's first face edge is vertical (vertex at `π/2` offset), so the bolt pattern is independent of the polygon rotation unless `bolt_phase` is set to align them.
