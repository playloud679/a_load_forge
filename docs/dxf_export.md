# `dxf_export.py` — 2D DXF drilling/cut templates for flanges

**Path:** `src/dxf_export.py`

Produces a flat 2-D **DXF** template (bolt holes + bore + outline) for any
generated flange, so the user can drill a mounting plate, laser/CNC a gasket,
or check the bolt pattern in CAD. No third-party dependency — writes plain
**AutoCAD R12 (AC1009) ASCII DXF** by hand (like `_step_export.py` does for
STEP). Units are millimetres (`$INSUNITS = 4`).

## How it works

Most templates are taken **straight from the flange mesh** by cutting one
horizontal cross-section through the plate, so circular, polygonal,
rectangular, custom and bolt-on flanges (including the driver-adapter plate)
export without re-deriving parameters. Elliptical-offset flanges use the
analytic `elliptical_flange_dxf()` path instead, because imperfect boolean
meshes can move the recovered hole centres. Each closed loop of a mesh section,
or each analytic elliptical entity, is sorted onto layers:

| Layer | Color | Content |
|---|---|---|
| `OUTLINE` | 7 | plate boundary (exterior loop) |
| `BORE` | 5 (blue) | the throat opening (the loop centred on the axis) |
| `HOLES` | 1 (red) | each off-axis loop → a bolt hole |
| `CENTERS` | 8 (grey) | a `POINT` mark at each bolt-hole centre |

Layers let the user keep only what they need (delete `OUTLINE`/`BORE` for a
pure hole template).

**Bore vs bolt hole:** an interior loop whose fitted centre is within
`max(2 mm, 0.25·r)` of the origin is the bore; everything else is a bolt hole.
Flanges are modelled centred on the Z axis, so this is unambiguous.

**Exact nominal circles:** bolt holes are always round, so they emit as true
`CIRCLE` entities with the centre at the least-squares fit and the radius taken
as the **circumscribed (max) vertex radius** — this recovers the exact nominal
diameter even though the mesh hole is a faceted 12-gon cylinder (e.g. a Ø6.5
hole comes back out as Ø6.5000 exactly, on the exact bolt circle). The bore and
outline keep their real shape: a round one becomes a `CIRCLE` (radius = fit), a
hexagonal or rectangular one stays a closed `POLYLINE`.

## API

### `mesh_to_flange_dxf(mesh, z: float | None = None, output_path: str | None = None) -> str | None`

Builds the DXF text for `mesh`. If `z` is `None` the drilling plane is located
automatically (`_best_section_z`: the sampled height whose section has the most
closed interior loops, ties broken by exterior area). Writes `output_path` when
given. Returns the DXF string, or `None` if the mesh yields no usable
cross-section (e.g. a radial horn piece with no flange).

### `elliptical_flange_dxf(inner_w, inner_h, ring=None, bolt_count=0, bolt_diam=0.0, bolt_phase=0.0, sections=128, output_path=None, outer_w=None, outer_h=None) -> str`

**Analytic** template for an elliptical-offset flange — built straight from the
source parameters, *not* by sectioning a mesh, so it is exact and immune to
boolean/mesh artefacts (the mesh path mis-centres holes when the solid is
imperfect). Matches `rectangular_flange.generate_rectangular_flange` with
`outer_type="elliptical"` — i.e. the semi-axis-scaled (concentric) ellipse the
flange actually uses, so the 2-D template and the 3-D part agree:

- `BORE` — the hole ellipse, semi-axes `(a, b) = (inner_w/2, inner_h/2)`.
- `OUTLINE` — the explicit `outer_w`/`outer_h` ellipse when supplied, otherwise
  the scaled offset ellipse with semi-axes `(a + ring, b + ring)`.
- `HOLES`/`CENTERS` — `bolt_count` circles of radius `bolt_diam/2` on the
  ellipse halfway between bore and outline, `+ bolt_phase`.

Always returns a string (never `None`). It remains available as a public API;
the UI exports generated Mouth/Mid geometry through the mesh-derived path so
custom and fixed-radius hole layouts are represented exactly.

### Helpers (private)

- `_fit_circle(pts) -> (cx, cy, r_fit, r_min, r_max)` — least-squares circle + inscribed/circumscribed vertex radii.
- `_is_round(r_min, r_max, n_pts)` — `True` when `n_pts ≥ 16` and `(r_max−r_min)/r_max < 0.05`.
- `_candidate_section_zs(mesh, samples)` — Z heights worth sectioning: midpoints between consecutive **horizontal-face** levels (each flange plate is bounded by two such faces, so its midplane is guaranteed to cut through every vertical bolt hole — even a thin plate on a long throat adapter), plus a uniform sweep as fallback.
- `_best_section_z(mesh, samples=11)` — auto-locate the drilling plane over `_candidate_section_zs`; returns `(z, polygons)`.
- `_circle` / `_polyline` / `_point` — R12 entity emitters.
- `_document(entities)` — wraps entities with HEADER + LAYER table + ENTITIES sections.
- `_ring_xy(ring)` — shapely ring → unique XY vertices (drops the closing duplicate).

## UI integration

`ui_app.py` stashes the individual flange bodies (`f_throat`, `f_mouth`,
`f_mid`) in `st.session_state["_flange_bodies"]` at merge time (radial throat
piece excluded), then offers one **“… flange DXF”** download button per flange
under the STL/STEP buttons in the Generate Assembly results. Buttons appear
only for flanges whose section actually yields holes (`mesh_to_flange_dxf`
returns non-`None`). The stash is cleared on parameter reset.

The **inward mouth flange** is modelled with `bolt_count=0` (its bolt shafts are
drilled into the merged assembly, not the plate), so `ui_app.py` subtracts those
shaft cuts into a DXF-only copy of the plate before stashing — otherwise its
template would come out with no holes.
