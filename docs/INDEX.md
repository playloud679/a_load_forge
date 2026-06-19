# flare_forge — Module Index

Each module has its own hyper‑detailed documentation in this directory.
When modifying code, read the relevant module doc **instead of the full
source** to save tokens.

> ⛔ **Two-way contract:** you read these docs instead of the source to save
> tokens — so when you change a `src/*.py` module you MUST update its
> `docs/<module>.md` in the same change, or the next agent gets lied to.

## Core (Profile Math + 3-D Engines)

| Module | Doc | What it does |
|---|---|---|
| `profile_generator.py` | [profile_generator.md](profile_generator.md) | Axisymmetric profiles (Tractrix, Salmon, Exponential, Le Cléac'h, Oblate spheroidal, Conical, R-OSSE) + shared 3-D revolution engine |
| `rectangular_horn.py` | [rectangular_horn.md](rectangular_horn.md) | Rectangular profiles (Exponential, Tractrix, Salmon, Oblate spheroidal, Conical) + faithful **Iwata** dual‑flare + rectangular loft engine |
| `polygonal_horn.py` | [polygonal_horn.md](polygonal_horn.md) | Polygonal N‑gon section engine (area‑matched to circular equivalent) |
| `radial_horn.py` | [radial_horn.md](radial_horn.md) | Experimental 360° radial API; retained in source but not exposed in the UI |
| `osse_horn.py` | [osse_horn.md](osse_horn.md) | Full **OS-SE waveguide** (ATH-style): round throat → superelliptical mouth, azimuth-dependent coverage → diagonal ridges; own `r(z,φ)` loft engine |

## Flanges + Adapter

| Module | Doc | What it does |
|---|---|---|
| `flange_generator.py` | [flange_generator.md](flange_generator.md) | Circular/polygonal flange with CSG bolt holes |
| `rectangular_flange.py` | [rectangular_flange.md](rectangular_flange.md) | Rectangular/elliptical-hole flange (circular or rectangular outer) |
| `throat_adapter.py` | [throat_adapter.md](throat_adapter.md) | Throat adapter: round driver → circular/elliptical/rect/poly throat with flanged or 1⅜"-18 threaded interface, 25 mm acoustic bore, and C1 raccordo |

## Utilities

| Module | Doc | What it does |
|---|---|---|
| `_slicer.py` | [_slicer.md](_slicer.md) | Axial slicing + radial petal cutting with tongue‑&‑groove joints |
| `_utils.py` | [_utils.md](_utils.md) | Profile normals, volume sign, Z‑alignment + `CircularProfile`/`RectProfile` type aliases |
| `_step_export.py` | _(no separate doc — see source)_ | STEP AP203 export for triangulated meshes |
| `dxf_export.py` | [dxf_export.md](dxf_export.md) | 2-D DXF drilling templates from flange meshes or exact elliptical parameters |
| `_constants.py` | _(no separate doc — see source)_ | Global constants (SOUND_SPEED) |
| `main.py` | [main.md](main.md) | Compatibility CLI wrapper that delegates to `profile_generator.main()` |

## UI

| File | Doc | What it does |
|---|---|---|
| `ui_app.py` | _(no separate doc — see source)_ | Streamlit single-page dashboard — sections: Acoustic Profile, Mounting Flanges, Generate Assembly, Slice STL |

### UI Geometry Contracts

- On mobile-width viewports the sidebar is forced to `100vw`, so the parameter
  panel opens as a full-width drawer instead of partially overlaying the
  preview/output workspace.
- OS-SE and R-OSSE shape factors are base profile-definition controls in the
  sidebar, rendered inline under `Shape Factors` rather than inside a collapsible
  expander.
- The top header uses `assets/flare_forge_logo.png` as a full-span banner; the
  Terms of Service download and Buy Me a Coffee link live in the Generate
  Assembly sidebar block immediately above the STL generation button.
- The 2-D cross-section preview is rendered with a black plot background and
  light axes/grid/legend styling to match the dark Streamlit theme.
- Mouth flange holes are based on the horn's **actual outer wall at the mouth**, then reduced by `_FLANGE_WALL_BITE = 0.5 mm` so the flange overlaps the wall and booleans cleanly. Circular, polygonal and rectangular modes must keep the displayed hole, ring sizing, bolt-circle limits and generated mesh on this same value.
- Inward roll-back mouth flanges are geometry-detected and available for circular, polygonal, rectangular, and elliptical sections when the returning lip has enough depth. They use a cavity plate matching the real rim, embedded 0.5 mm into the flare to avoid coplanar contact, plus full load-bearing pillars boolean-clipped to the flare surface before union. The external flare cut is shaft-diameter only. Screw-head seats are cut after the pillar union, stay axial and concentric with the vertical screw holes, and share one coplanar floor controlled by `Head depth`; each section shape places bolts and pillars on its actual rim.
- Standard throat-driver bolt-on presets are defined only in `flange_generator.DRIVER_FLANGE_SPECS`. The UI and `throat_adapter.make_adapter_assembly()` consume those keys directly so nominal throat, outer diameter, M6 clearance holes and PCD cannot drift apart; the adapter rotates the 2-hole preset vertical and computes the asymmetric 3-hole phase against the flare outer contour to maximize screw clearance.
- Flange **DXF** drilling templates use `dxf_export.mesh_to_flange_dxf`: candidate sections include midpoints between horizontal-face levels so thin plates on tall adapters are not skipped. Off-axis loops are bolt holes (emitted as exact nominal circles via the circumscribed vertex radius); the loop centred on the axis is the bore. Inward mouth-flange shaft cuts are applied to a DXF-only plate copy before mesh sectioning.
- Outward **Mouth/Mid** flanges use `flange_generator.generate_profile_flange()`. Offset mode follows the opening shape and auto-centres holes in the available material; custom mode supports circular/polygonal/rectangular outer shapes and auto or fixed-radius bolt placement. Throat flange generation stays on the legacy paths.
- In the UI, throat-adapter morphs replace the first requested millimetres of the flare rather than being prepended to it. The original flare is trimmed at the morph handoff, the adapter matches the real section and slope there, and an overlap of up to 6 mm avoids coplanar-contact unions. `_ta.embedded_morph_span()` shortens the trim distance and then the overlap when the advancing flare branch is short, so the adapter target never passes the safe profile extent. This preserves the horn's mouth position and acoustic depth; only the mechanical driver flange or threaded socket may protrude behind the throat plane.
- When `Include shape adapter` is enabled, the sidebar's `Driver / Adapter`
  block owns adapter flange thickness and all driver-side sizing. The separate
  `Throat Flange` block must remain visible only as a status note and must not
  render thickness, bolt, ring, offset, or shape inputs for that generated
  throat component.
- The adapter's perimeter point count is inherited from its custom inner/outer section stacks (`make_adapter` uses `n = len(custom_pts[-1])`), so the UI builds those sections at `_adapter_n` = the **flare's revolution resolution** (`rings_ellip` for elliptical, else `rings_n` from "Angular segments"; OS-SE samples its own `nphi` grid). Matching it is mandatory: a coarse 64-gon adapter against a fine flare leaves a ~28 µm radial step through the weld overlap that prints as a visible seam ring. This count also drives the threaded-socket facets and end caps, so the whole adapter stays smooth.
- Generated assemblies with a throat adapter store `_adapter_cut_z` at the embedded morph handoff; the Slice STL UI uses it for the "Adapter as axial segment" option so flare Count/Height segmentation starts above the adapter.
- Radial tongue/groove joints protect the external seam skin through `outer_margin` (`Outer skin keep` in UI, default 1.5 mm); the value is a hard minimum and slicing fails if the wall cannot support it.
- Polygonal adapters use the same `+π/2` phase as `polygonal_horn.py`; do not reintroduce a circular `θ=0` source phase for polygonal morphs.
- The **Elliptical** section forces `is_rect = True` (reuses rectangular profile math + W/H inputs) and calls `generate_elliptical_3d_mesh_from_profiles(z, w/2, h/2)` for the body. Its outer wall is a true full-3D normal offset, including through roll-back; UI outer dimensions come from the same helper. The throat flange keeps `rectangular_flange.generate_rectangular_flange(..., inner_type="elliptical")`; outward Mouth/Mid use `generate_profile_flange()`, and shape adapters use a true elliptical morph target with `sqrt(W·H)/2` equivalent radius.
- **OS-SE** uses a true 3-D surface normal offset to guarantee constant perpendicular `thickness` everywhere. The throat is flattened via a boolean slice, while the mouth remains naturally slanted to avoid tapering (it is enveloped by the flange). The UI's `_osse_contour_xy` defines the flange inner bounds so flanges follow the ridges perfectly.

## Data Flow

```
UI parameters → 2-D Profile (z,r) → 3-D Mesh Engine → STL
                    ↓                        ↓
              Flange params          Boolean union (horn + flange + adapter)
                    ↓
              Flange generator → CSG boolean → watertight STL
```

## Critical Rules (see `AGENTS.md`)

- UI must stay in sync with `src/` modules
- Every new profile / generator needs a UI section + test case
- Use `importlib.reload()` in `ui_app.py` for hot‑reload
