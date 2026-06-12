# `src/_slicer.py` — STL Slicer

Cuts a horn mesh either **axially** (into Z-segments) or **radially** (into
petals like orange slices).  Uses trimesh for plane slicing with capping.

All distances in mm, angles in radians unless otherwise noted.

---

## Utility functions

### `_outer_polygon`

```python
def _outer_polygon(
    mesh: trimesh.Trimesh,
    origin: list[float] | np.ndarray,
    normal: list[float] | np.ndarray,
) -> shp.Polygon | None:
```

Slices `mesh` with a plane at `origin` with `normal`, then returns the
**largest-area** closed shapely `Polygon` from the 2-D cross-section. Returns
`None` if the section is empty, fails to convert to 2-D, or has no closed
polygons.

---

### `_wall_angle_deg`

```python
def _wall_angle_deg(mesh: trimesh.Trimesh, z: float) -> float:
```

Computes the **wall angle from vertical** (in degrees) at height `z`.

**Algorithm:**
1. `dz = max(1.0, (Zmax − Zmin) × 0.02)` — 2% of mesh height, minimum 1 mm.
2. Cross-sections at `z` and `z + dz`.
3. Mean radius `r0`, `r1` of each section's outer polygon.
4. `slope = (r1 − r0) / dz`, return `arctan(|slope|)` in degrees.

Used by `add_axial_lip` to shear lip vertices outward to follow the horn's
flare angle.

---

### `_precompute_angles`

```python
def _precompute_angles(
    mesh: trimesh.Trimesh,
    cuts: list[float],
) -> dict[float, float]:
```

Computes `_wall_angle_deg` for every Z in `cuts[1:-1]` (skips endpoints,
which have no wall). Returns `{z: angle_deg}`.

---

### `_seam_face_polygons`

```python
def _seam_face_polygons(
    petal: trimesh.Trimesh,
    origin: list[float] | np.ndarray,
    normal: list[float] | np.ndarray,
    min_area_frac: float = 0.0,
) -> tuple[list[shp.Polygon], np.ndarray | None]:
```

Slices a **single petal** at the seam plane and returns:
- A `list` of significant closed shapely `Polygon`s (one per wall strip on
  that seam face). Slivers below `min_area_frac × max_area` are discarded;
  the default keeps every seam strip so flanged petals are not trimmed away.
- The `to_3D` transformation matrix from the slice (or `None` if slice
  fails).

**For n ≥ 3:** The seam plane intersects the wall on a single strip, so the
returned list has 1 polygon.
**For n = 2:** The diametric seam plane crosses the axis and meets the wall
on **two** strips (one on each side of the axis). Both are returned.

---

### `_buffer_single`

```python
def _buffer_single(
    poly: shp.Polygon,
    distance: float,
) -> shp.Polygon | None:
```

Buffers a polygon by `distance` (positive = expand, negative = shrink) with
mitre joins. If the result is a `MultiPolygon` (can happen with negative
buffer on narrow walls), takes the largest part. Returns `None` if the
result is empty.

---

### `_joint_profile`

```python
def _joint_profile(
    poly: shp.Polygon,
    to_3D: np.ndarray,
    margin: float,
    clearance_offset: float = 0.0,
    outer_margin: float | None = None,
) -> shp.Polygon | None:
```

Builds the 2-D tongue/groove profile from a seam-face polygon.

It first applies the normal negative buffer (`margin + clearance_offset`).
When `outer_margin` is larger than that inset, the joint profile is eroded
further so the external skin stays at least that thick. If the geometry does
not have enough material to satisfy the requested skin, the slicer raises a
clear error instead of silently shrinking the request.

Returns the largest polygon if erosion produces a `MultiPolygon`, or raises
if the requested protected skin cannot be satisfied.

---

### `_filter_polys_by_side`

```python
def _filter_polys_by_side(
    polys: list[shp.Polygon],
    to_3D: np.ndarray,
    axis: np.ndarray | None,
    side: int,
) -> list[shp.Polygon]:
```

Keeps only polygons whose 3-D centroid, when projected onto `axis`, lies on
the requested `side`. `side = +1` keeps positive dot product, `side = -1`
keeps negative, `side = 0` keeps all. Used for n=2 to separate the two wall
strips on opposite sides of the axis.

---

## Axial slicing

### `add_axial_lip`

```python
def add_axial_lip(
    segment: trimesh.Trimesh,
    z: float,
    wall: float,
    direction: str = "up",
    angle_deg: float = 0.0,
) -> trimesh.Trimesh:
```

Adds a joint lip (registration collar) on the **OUTER** surface of `segment`
at height `z`.

- `wall` — lip width (radial thickness of the collar ring in mm).
- `direction` — `"up"` (lip extends upward from the cut face) or `"down"`.
- `angle_deg` — wall angle from vertical at this Z. When > 0.5°, lip
  vertices are **sheared outward** to follow the wall flare, so the lip does
  not protrude perpendicular to the surface.

**Algorithm:**
1. Cross-section the segment at `z − ε` to get the outer polygon.
2. Buffer outward by `wall` (mitre join), subtract the original to get a
   ring.
3. Extrude the ring vertically by `h = wall × cos(angle_deg)` (direction
   indicates sign).
4. If `angle_deg > 0.5°`, shear vertices: for each vertex at height `frac`
   of the extrusion, offset radially by `wall × sin(angle_deg) × frac`.
5. Boolean union the lip with the segment (Manifold engine). Falls back to
   `concatenate` if union fails.

---

### `slice_at_z`

```python
def slice_at_z(
    mesh: trimesh.Trimesh,
    z: float,
    keep: str = "below",
) -> trimesh.Trimesh | None:
```

Cuts `mesh` with a horizontal plane at Z=`z`, keeping the `"below"` or
`"above"` half (capped). Returns a watertight `Trimesh` or `None` if empty.

---

### `slice_into_segments`

```python
def slice_into_segments(
    mesh: trimesh.Trimesh,
    n: int,
    joint_wall: float = 0.0,
) -> list[trimesh.Trimesh]:
```

Cuts `mesh` into `n` axial segments of **equal Z-height** (uniform
intervals between `mesh.bounds[0,2]` and `mesh.bounds[1,2]`). Each slab is
capped.

When `joint_wall > 0`, a joint lip is added at each **intermediate** cut
face (the top face of every segment except the last). Lips are sheared to
match the wall angle at that Z.

---

### `slice_at_heights`

```python
def slice_at_heights(
    mesh: trimesh.Trimesh,
    heights: list[float],
    joint_wall: float = 0.0,
) -> list[trimesh.Trimesh]:
```

Like `slice_into_segments` but cuts at explicitly specified Z heights.
Heights are sorted and clamped to `[Zmin, Zmax]`. Returns capped slabs
between consecutive heights. Joint lips added when `joint_wall > 0`.

---

### `slice_with_adapter_segment`

```python
def slice_with_adapter_segment(
    mesh: trimesh.Trimesh,
    adapter_cut_z: float,
    flare_segments: int = 1,
    flare_height: float | None = None,
    joint_wall: float = 0.0,
) -> list[trimesh.Trimesh]:
```

Cuts the throat adapter off as its own bottom axial segment, then segments
only the flare side above `adapter_cut_z`.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `mesh` | `trimesh.Trimesh` | (required) | Full generated/uploaded mesh to slice. |
| `adapter_cut_z` | `float` | (required) | Z height where the adapter enters the horn throat. |
| `flare_segments` | `int` | `1` | Number of equal axial segments above the adapter cut when `flare_height` is not set. |
| `flare_height` | `float \| None` | `None` | If set, cut the flare side every this many mm above `adapter_cut_z`. |
| `joint_wall` | `float` | `0.0` | Axial lip wall. `0` = plain cut; `>0` adds lips through `slice_at_heights()`. |

**Behavior:**

1. Adds `adapter_cut_z` as the first intermediate cut when it lies inside
   the mesh Z bounds.
2. If `flare_height` is provided, adds repeated cuts at
   `adapter_cut_z + k·flare_height` up to `Zmax`.
3. Otherwise divides only `[adapter_cut_z, Zmax]` into `flare_segments`
   equal parts.
4. Calls `slice_at_heights()` so all cuts, including adapter→flare, receive
   the usual axial lip when `joint_wall > 0`.
5. If `adapter_cut_z` is outside the mesh bounds, falls back to
   `slice_into_segments(mesh, flare_segments, joint_wall)`.

---

### `slice_to_print_volume`

```python
def slice_to_print_volume(
    mesh: trimesh.Trimesh,
    max_x: float,
    max_y: float,
    max_z: float,
    keep_z_max: float | None = None,
    strategy: str = "center_up",
    joint_depth: float = 0.0,
    joint_margin: float = 1.0,
    clearance: float = 0.1,
) -> list[trimesh.Trimesh]:
```

Cuts `mesh` into axis-aligned parallelepiped chunks sized for a printer build
volume.

With `strategy="center_up"` (the UI default), the slicer builds X/Y intervals
from the model centre outward and balanced Z intervals from bottom to top, so a
large central stack does not end with a very thin residual slab. Output order is
the central stack first, bottom-up, then larger side-wing regions split only as
much as needed to fit the print volume. This avoids filling the output with tiny
global-grid slivers.

With `strategy="adaptive"`, the slicer recursively inspects the actual
bounding box of each current piece and cuts only the axis that exceeds the
build volume most. This produces fewer, larger chunks than a global grid but
does not guarantee centre-bottom ordering.

With `strategy="grid"`, the slicer uses fixed global intervals no larger than
`max_x`, `max_y`, and `max_z`, then clips each occupied box with capped X/Y/Z
planes.

If `keep_z_max` is provided, the throat-side range `[Zmin, keep_z_max]` is kept
inside the first center-bottom core chunk. The throat adapter and/or throat
flange remain monolithic, but they are not exported as a separate part; the
first core chunk may exceed the requested print volume when this is necessary
to preserve that hardware.

When `joint_depth > 0`, the slicer adds tongue/groove alignment joints between
neighboring print-volume chunks. For a shared face along X/Y/Z, the chunk on the
negative side receives the tongue on its positive face and the chunk on the
positive side receives the matching groove on its negative face. `joint_margin`
insets the feature from the cut-face perimeter and `clearance` opens the groove
relative to the tongue.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `mesh` | `trimesh.Trimesh` | (required) | Full generated/uploaded mesh to slice. |
| `max_x` | `float` | (required) | Maximum printable X dimension in mm. |
| `max_y` | `float` | (required) | Maximum printable Y dimension in mm. |
| `max_z` | `float` | (required) | Maximum printable Z dimension in mm. |
| `keep_z_max` | `float \| None` | `None` | Optional protected throat-side Z height. |
| `strategy` | `str` | `"center_up"` | `"center_up"` for central bottom-up order, `"adaptive"` for largest practical pieces, `"grid"` for fixed cells. |
| `joint_depth` | `float` | `0.0` | Tongue/groove depth on print-volume cut faces. 0 = plain cuts. |
| `joint_margin` | `float` | `1.0` | Inset from the cut-face perimeter before placing each joint feature. |
| `clearance` | `float` | `0.1` | Total mating clearance between tongue and groove in mm. |

---

## Radial petals

### `seam_phase_avoiding_holes`

```python
def seam_phase_avoiding_holes(
    n: int,
    hole_angles: list[float],
    samples: int = 1440,
) -> float:
```

Finds an optimal rotation `phase ∈ [0, 2π/n)` for `n` evenly-spaced radial
seams that maximises the minimum angular distance between any seam and any
bolt/obstruction hole.

- `hole_angles` — obstruction angles in radians (e.g. flange bolt
  positions).
- `samples` — number of candidate phases to evaluate.
- Returns the phase that yields the largest minimum gap between seams and
  holes (circular distance, mod 2π). Returns `0.0` if `n < 2` or no holes.

**Algorithm:** For each candidate `phase`, compute `n` seam angles `i·2π/n +
phase`. Compute the minimum angular distance (0 to π) from each seam to each
hole. Pick the phase that maximises this minimum.

---

### `add_radial_tongue`

```python
def add_radial_tongue(
    petal: trimesh.Trimesh,
    angle: float,
    joint_depth: float = 2.0,
    margin: float = 1.0,
    clearance: float = 0.1,
    outer_margin: float | None = None,
    side: int = 0,
    axis: np.ndarray | None = None,
) -> trimesh.Trimesh:
```

Adds a **tongue** (male protrusion) on the **RIGHT** seam at `angle` of a
radial petal. The seam normal points in the +seam direction (tangent to the
circle). The profile is biased toward the inner side when `outer_margin` is
set, preserving a solid external skin.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `petal` | `trimesh.Trimesh` | (required) | The petal to modify. |
| `angle` | `float` | (required) | Angle (rad) of the seam plane normal. Right seam of the petal. |
| `joint_depth` | `float` | `2.0` | How far the tongue protrudes outward from the seam face (mm). |
| `margin` | `float` | `1.0` | Inset from the wall edge before the tongue starts (mm). |
| `clearance` | `float` | `0.1` | Total radial gap between tongue and groove when mated (split equally). |
| `outer_margin` | `float \| None` | `None` | Protected external-skin width. Keeps tongue away from the visible outer wall. |
| `side` | `int` | `0` | For n=2: which side of the axis to apply the tongue to (+1 or −1). 0 = both sides. |
| `axis` | `np.ndarray \| None` | `None` | For n=2: the in-plane direction used by `_filter_polys_by_side`. |

**Algorithm:**
1. Section the petal at the seam plane to get the wall cross-section
   polygon(s).
2. For each polygon, shrink inward by `margin + clearance/2`, then clip away
   from the external side when `outer_margin` is set.
3. Extrude the profile by `joint_depth + overlap` (where `overlap = 1.0`
   mm) and translate by `−overlap` in Z so it starts **inside** the petal
   body. This volumetric overlap ensures the boolean union welds reliably
   (a coplanar touch does not).
4. Transform to 3-D and boolean union with the petal.

When `body_count > 1` after union, splits bodies and re-unions or
concatenates.

---

### `add_radial_groove`

```python
def add_radial_groove(
    petal: trimesh.Trimesh,
    angle: float,
    joint_depth: float = 2.0,
    margin: float = 1.0,
    clearance: float = 0.1,
    outer_margin: float | None = None,
    side: int = 0,
    axis: np.ndarray | None = None,
) -> trimesh.Trimesh:
```

Cuts a **groove** (female recess) on the **LEFT** seam at `angle` of a
radial petal. The seam normal points in the −seam direction (inward).

Parameters are identical to `add_radial_tongue`.

**Algorithm:**
1. Section the petal at the seam plane (normal reversed vs tongue) to get
   the wall cross-section polygon(s).
2. Shrink the polygon by `margin − clearance/2` (note: less shrinkage than
   tongue, creating a slightly wider slot), then clip away from the external
   side when `outer_margin` is set. Then extrude inward by `joint_depth + overlap`.
3. Boolean difference to cut the groove into the petal. Each groove is cut
   sequentially into `result`, checking that `body_count == 1` after each
   cut.

---

### `slice_into_petals`

```python
def slice_into_petals(
    mesh: trimesh.Trimesh,
    n: int,
    phase: float = 0.0,
    joint_depth: float = 0.0,
    joint_margin: float = 0.5,
    clearance: float = 0.1,
    outer_margin: float | None = None,
) -> list[trimesh.Trimesh]:
```

Cuts `mesh` into `n` equal-angle radial petals. Each petal is the wedge
between two seam planes:
- Left seam at `phase + i·2π/n` (plane normal: outward-left)
- Right seam at `phase + (i+1)·2π/n` (plane normal: outward-right)

Seams are capped. The phase rotates the entire seam pattern (use
`seam_phase_avoiding_holes` to pick a good one).

For `n == 2`, both angular boundaries describe the same diametric plane. The
mesh is therefore sliced and capped only once per half; capping the coincident
plane twice can retriangulate coplanar faces and appear as a horizontal
z-fighting artifact on roll-back profiles.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `mesh` | `trimesh.Trimesh` | (required) | The mesh to slice. |
| `n` | `int` | (required) | Number of petals (≥ 2). |
| `phase` | `float` | `0.0` | Angular offset (rad) of the first seam. |
| `joint_depth` | `float` | `0.0` | Tongue & groove depth. 0 = plain petals without joints. |
| `joint_margin` | `float` | `0.5` | Inset from wall edge for joint features (mm). |
| `clearance` | `float` | `0.1` | Total radial gap between mated tongue and groove (mm). |
| `outer_margin` | `float \| None` | `None` | Protected external-skin strip. UI default is 1.5 mm when radial joint is enabled. Treated as a hard minimum. |

#### Tongue & groove joint logic

##### n ≥ 3

Each petal gets:
- **Groove** on the left seam (at `angle0`): female cut going *into* the
  petal.
- **Tongue** on the right seam (at `angle1`): male protrusion going
  *outward* from the petal.

The assignment is consistent across all petals: when assembled, the tongue
of petal `i` slides into the groove of petal `i+1` (wrapping around).

##### n == 2 (hermaphrodite)

Two petals share a single diametric plane. The seam crosses the axis and
meets the wall on **two strips** (one on each side of the axis).

Each petal carries **one tongue + one groove** on opposite strips:
- Petal 0: tongue on side +1, groove on side −1.
- Petal 1: tongue on side −1, groove on side +1.

The assignment flips so each tongue faces a groove on the mating part. Both
petals are **identical** (one is the other rotated 180°), enabling
single-part production.

The `axis` for `_filter_polys_by_side` is derived from `phase`:
```
axis = [cos(phase), sin(phase), 0]
```

#### Clearance model

`clearance` is the *total* radial gap, split equally:
- **Tongue** shrinks by `margin + clearance/2` (smaller male part).
- **Groove** shrinks by `margin − clearance/2` (larger female slot — note
  the subtraction: `margin - clearance/2` is *less* shrinkage, so the groove
  is wider than the tongue by `clearance`).

Overlap of 1.0 mm is added to both tongue and groove extrusions to ensure
the features blend volumetrically into the petal body.
