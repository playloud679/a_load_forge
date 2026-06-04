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
| `profile_generator.py` | [profile_generator.md](profile_generator.md) | Axisymmetric profiles (Tractrix, Salmon, Exponential, Le Cléac'h) + shared 3-D revolution engine |
| `rectangular_horn.py` | [rectangular_horn.md](rectangular_horn.md) | Rectangular profiles (Exponential, Tractrix, Salmon) + faithful **Iwata** dual‑flare + rectangular loft engine |
| `polygonal_horn.py` | [polygonal_horn.md](polygonal_horn.md) | Polygonal N‑gon section engine (area‑matched to circular equivalent) |
| `radial_horn.py` | [radial_horn.md](radial_horn.md) | 360° omnidirectional radial horn (two‑piece: bottom plate + top reflector) |

## Flanges + Adapter

| Module | Doc | What it does |
|---|---|---|
| `flange_generator.py` | [flange_generator.md](flange_generator.md) | Circular/polygonal flange with CSG bolt holes |
| `rectangular_flange.py` | [rectangular_flange.md](rectangular_flange.md) | Rectangular‑hole flange (circular or rectangular outer) |
| `throat_adapter.py` | [throat_adapter.md](throat_adapter.md) | Throat adapter: round driver → circular/rect/poly throat with flanged or threaded (1"/1¼"/2" UNF) interface and C1 raccordo |

## Utilities

| Module | Doc | What it does |
|---|---|---|
| `_slicer.py` | [_slicer.md](_slicer.md) | Axial slicing + radial petal cutting with tongue‑&‑groove joints |
| `_utils.py` | _(no separate doc — see source)_ | Profile normals, volume sign, Z‑alignment |
| `_step_export.py` | _(no separate doc — see source)_ | STEP AP203 export for triangulated meshes |
| `_constants.py` | _(no separate doc — see source)_ | Global constants (SOUND_SPEED) |
| `main.py` | _(no separate doc — see source)_ | CLI orchestrator |

## UI

| File | Doc | What it does |
|---|---|---|
| `ui_app.py` | _(no separate doc — see source)_ | Streamlit single-page dashboard — sections: Acoustic Profile, Mounting Flanges, Generate Assembly, Slice STL |

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
