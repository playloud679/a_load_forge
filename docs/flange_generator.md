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

## Bolt Phase Parameter

The `bolt_phase` parameter (in radians) rotates the entire bolt hole pattern around the Z axis. By default `bolt_phase = 0.0`, which places the first bolt at angle 0 (along the +X axis). For a polygon with `outer_n_sides ≥ 3`, the polygon's first face edge is vertical (vertex at `π/2` offset), so the bolt pattern is independent of the polygon rotation unless `bolt_phase` is set to align them.
