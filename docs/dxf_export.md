# `dxf_export.py` — 2D DXF drilling/cut template from a flange mesh

**Path:** `src/dxf_export.py`

Produces a flat 2-D **DXF** template (bolt holes + bore + outline) for any
generated flange, so the user can drill a mounting plate, laser/CNC a gasket,
or check the bolt pattern in CAD. No third-party dependency — writes plain
**AutoCAD R12 (AC1009) ASCII DXF** by hand (like `_step_export.py` does for
STEP). Units are millimetres (`$INSUNITS = 4`).

## How it works

The template is taken **straight from the flange mesh** by cutting one
horizontal cross-section through the plate, so every flange type (circular /
polygonal / rectangular / elliptical, custom or bolt-on, even the bolt-on
driver-adapter plate) exports without re-deriving any parameters. Each closed
loop of the section becomes a DXF entity, sorted onto layers:

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

### Helpers (private)

- `_fit_circle(pts) -> (cx, cy, r_fit, r_min, r_max)` — least-squares circle + inscribed/circumscribed vertex radii.
- `_is_round(r_min, r_max, n_pts)` — `True` when `n_pts ≥ 16` and `(r_max−r_min)/r_max < 0.05`.
- `_best_section_z(mesh, samples=11)` — auto-locate the drilling plane; returns `(z, polygons)`.
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
