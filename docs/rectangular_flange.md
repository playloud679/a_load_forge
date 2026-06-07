# `src/rectangular_flange.py` — Rectangular / Elliptical-Hole Flange

Parametric flange with a rectangular or elliptical centre hole and three outer
shapes (circular, rectangular, elliptical-offset). All dimensions in mm.

---

## `generate_rectangular_flange`

```python
def generate_rectangular_flange(
    outer_diam: float = 70.0,
    inner_w: float = 20.0,
    inner_h: float = 10.0,
    thickness: float = 6.0,
    bolt_radius: float = 26.0,
    bolt_inset: float = 10.0,
    bolt_count: int = 4,
    bolt_diam: float = 3.5,
    outer_type: str = "rectangular",
    outer_w: float | None = None,
    outer_h: float | None = None,
    offset: float = 0.0,
    output_path: str | None = None,
    bolt_phase: float = 0.0,
    inner_type: str = "rectangular",
) -> trimesh.Trimesh | None:
```

**Return:** Watertight `trimesh.Trimesh` of the flange, or `None` if boolean
difference fails (e.g. bolt holes intersect each other or the outer boundary).

---

### Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `outer_diam` | `float` | `70.0` | Outer diameter (circular mode only). Clamped by `min_diam`. |
| `inner_w` | `float` | `20.0` | Width (X) of the rectangular centre hole. |
| `inner_h` | `float` | `10.0` | Height (Y) of the rectangular centre hole. |
| `thickness` | `float` | `6.0` | Z-extent of the flange plate. |
| `bolt_radius` | `float` | `26.0` | Radius of the bolt circle (circular mode only). Clamped by `safe_radius`. |
| `bolt_inset` | `float` | `10.0` | Distance from the outer boundary to each bolt centre (rectangular mode only). Clamped by `min_x`/`min_y`. |
| `bolt_count` | `int` | `4` | Number of equally-spaced bolt holes (circular mode only). |
| `bolt_diam` | `float` | `3.5` | Diameter of each bolt hole. |
| `outer_type` | `str` | `"rectangular"` | `"circular"`, `"rectangular"` or `"elliptical"`. |
| `outer_w` | `float \| None` | `None` | Explicit outer width (rectangular/elliptical modes). Auto-computed from `inner_w` + `safe_margin` when `None`. |
| `outer_h` | `float \| None` | `None` | Explicit outer height (rectangular/elliptical modes). Auto-computed from `inner_h` + `safe_margin` when `None`. |
| `offset` | `float` | `0.0` | Z coordinate of the flange **bottom** face. |
| `output_path` | `str \| None` | `None` | If set, the mesh is exported to this STL path after cleaning. |
| `bolt_phase` | `float` | `0.0` | Angular phase offset (radians) for the bolt circle (circular mode only). Added to each bolt angle. |
| `inner_type` | `str` | `"rectangular"` | Centre hole shape: `"rectangular"` or `"elliptical"`. Elliptical dimensions use `inner_w` and `inner_h` as full axis lengths. |

---

### `offset` vs `generate_flange` semantics

In `flange_generator.py` the `offset` parameter positions the flange **top**
face.  **This function uses `offset` as the Z position of the bottom face.**
The centre of the plate is always at `Z = offset + thickness / 2.0`.

---

### Outer type modes

#### `"circular"` — disc with bolts on a circle

- Outer body is a cylinder of radius `max(outer_diam, min_diam) / 2`, centred
  at `(0, 0, center_z)`.
- **Safety clamp `min_diam`:**
  ```
  min_diam = sqrt(inner_w² + inner_h²) + bolt_diam * 4 + 10.0
  ```
  Ensures bolt holes never breach the outer boundary.
- `bolt_count` bolts are placed on a circle of radius
  `max(bolt_radius, safe_radius)` where:
  ```
  safe_radius = sqrt(inner_w² + inner_h²) / 2 + bolt_diam / 2 + 2.0
  ```
  This prevents bolt holes from intersecting the rectangular centre hole.
- Bolt angles: `linspace(0, 2π, bolt_count, endpoint=False) + bolt_phase`.
- The `outer_w`, `outer_h`, and `bolt_inset` parameters are **ignored** in this
  mode.

#### `"rectangular"` — plate with bolts at corners

- Outer body is a box of size `(outer_w_val, outer_h_val, thickness)` centred
  at `(0, 0, center_z)`.
- **Safety clamp `safe_margin`:**
  ```
  safe_margin = bolt_inset * 2 + bolt_diam + 10.0
  ```
  So when `outer_w`/`outer_h` are `None`, the auto-computed size guarantees
  bolts fit with at least 10 mm of material beyond the bolt holes.
- Bolts are placed at the **4 corners** of the outer plate, inset toward
  centre by `bolt_inset` from each edge:
  ```
  x = ±max(outer_w_val/2 - bolt_inset, inner_w/2 + bolt_diam/2 + 1)
  y = ±max(outer_h_val/2 - bolt_inset, inner_h/2 + bolt_diam/2 + 1)
  ```
  The `max(…, min_x / min_y)` clamp prevents bolt holes from colliding with
  the centre hole.
- `bolt_count`, `bolt_radius`, `bolt_phase`, and `outer_diam` are **ignored**
  in this mode.

#### `"elliptical"` — elliptical-offset ring with bolts on the mid-ring ellipse

- Outer body is a 128-section unit cylinder scaled to semi-axes
  `(outer_w_val/2, outer_h_val/2)`, centred at `(0, 0, center_z)`. The caller
  passes `outer_w = inner_w + 2·ring` / `outer_h = inner_h + 2·ring`, so the
  outer contour is the hole's ellipse offset outward by a constant ring width —
  the natural shape for an elliptical horn flange (no rectangular corners, no
  circular ledge).
- `bolt_count` bolts ride the **mid-ring ellipse** with semi-axes
  `((inner_w/2 + outer_w_val/2)/2, (inner_h/2 + outer_h_val/2)/2)`, at angles
  `linspace(0, 2π, bolt_count, endpoint=False) + bolt_phase`. This keeps them
  centred in the elliptical wall for any aspect ratio.
- `outer_diam`, `bolt_radius`, and `bolt_inset` are **ignored** in this mode.

---

### Algorithm

1. Compute `center_z = offset + thickness / 2.0`.
2. **Outer body:** box (rectangular), cylinder (circular), or a unit cylinder
   scaled to the outer semi-axes (elliptical) at `center_z`.
3. **Centre hole:** box `(inner_w, inner_h, thickness * 3)` for rectangular,
   or a 128-section unit cylinder scaled to ellipse axes `(inner_w, inner_h)`.
   Extra height ensures a clean through-cut.
4. **Bolt holes:** cylinders `(bolt_diam/2, thickness * 3)` at the computed
   positions (extra height for clean cuts).
5. **Boolean subtraction** (Manifold engine):
   `(outer + centre_hole + bolt_holes...)` — manifold's quirky API requires
   *adding* the objects you want to subtract.
6. **Cleanup:** `remove_unreferenced_vertices()`,
   `update_faces(nondegenerate_faces())`, `fix_normals()`.
7. If `output_path` is set, export STL and log watertight status.

### UI inward-mouth assembly

`generate_rectangular_flange()` creates the flat flange body only. The inward
roll-back assembly is owned by `ui_app.py`: rectangular bolt and pillar
positions follow the actual rectangular rim, full pillars are clipped to the
real flare surface before union, and the final axial/concentric screw-head
seats share one coplanar floor.
