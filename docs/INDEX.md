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
| `radial_horn.py` | [radial_horn.md](radial_horn.md) | 360° omnidirectional radial horn (two‑piece: bottom plate + top reflector) |

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
| `_constants.py` | _(no separate doc — see source)_ | Global constants (SOUND_SPEED) |
| `main.py` | [main.md](main.md) | Compatibility CLI wrapper that delegates to `profile_generator.main()` |

## UI

| File | Doc | What it does |
|---|---|---|
| `ui_app.py` | _(no separate doc — see source)_ | Streamlit single-page dashboard — sections: Acoustic Profile, Mounting Flanges, Generate Assembly, Slice STL |

### UI Geometry Contracts

- Mouth flange holes are based on the horn's **actual outer wall at the mouth**, then reduced by `_FLANGE_WALL_BITE = 0.5 mm` so the flange overlaps the wall and booleans cleanly. Circular, polygonal and rectangular modes must keep the displayed hole, ring sizing, bolt-circle limits and generated mesh on this same value.
- Inward roll-back mouth flanges use full load-bearing pillars that are boolean-clipped to the real flare surface before union. The external flare cut is shaft-diameter only. Screw-head seats are cut after the pillar union, stay axial and concentric with the vertical screw holes, and share one coplanar floor controlled by `Head depth`. Rectangular modes place bolts and pillars on the actual rectangular rim.
- Standard throat-driver bolt-on presets are defined only in `flange_generator.DRIVER_FLANGE_SPECS`. The UI and `throat_adapter.make_adapter_assembly()` consume those keys directly so nominal throat, outer diameter, M6 clearance holes, PCD, and angular pattern cannot drift apart.
- In the UI, throat-adapter morphs replace the first requested millimetres of the flare rather than being prepended to it. The original flare is trimmed at the morph handoff, the adapter matches the real section and slope there, and a 0.5 mm overlap avoids coplanar-contact unions. This preserves the horn's mouth position and acoustic depth; only the mechanical driver flange or threaded socket may protrude behind the throat plane.
- Generated assemblies with a throat adapter store `_adapter_cut_z` at the embedded morph handoff; the Slice STL UI uses it for the "Adapter as axial segment" option so flare Count/Height segmentation starts above the adapter.
- Radial tongue/groove joints protect the external seam skin through `outer_margin` (`Outer skin keep` in UI, default 1.5 mm); interlock features should stay biased inward rather than thinning the visible outer wall.
- Polygonal adapters use the same `+π/2` phase as `polygonal_horn.py`; do not reintroduce a circular `θ=0` source phase for polygonal morphs.
- The **Elliptical** section forces `is_rect = True` (reuses rectangular profile math + W/H inputs) and calls `generate_elliptical_3d_mesh_from_profiles(z, w/2, h/2)` for the body. Its outer wall is a true full-3D normal offset, including through roll-back; UI outer dimensions come from the same helper. Throat, mouth, and mid flanges use `rectangular_flange.generate_rectangular_flange(..., inner_type="elliptical")`; shape adapters use a true elliptical morph target and `sqrt(W·H)/2` equivalent radius.

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
