# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Setup
make install          # create .venv and install dependencies

# Run web UI
make run               # launch headless + open in Safari
streamlit run ui_app.py   # or run directly (default browser)

# CLI usage
python -m src.main --throat 20 --mouth 100
python -m src.main --throat 20 --fc 800
python -m src.main --profile salmon --throat 20 --fc 600 --length 80

# Run tests
.venv/bin/python tests/test_all.py
```

## Architecture

### Data flow

```
Parameters → 2D Profile (z, r) → generate_3d_mesh_from_profile() → STL

Rectangular: (z, w, h) → generate_rectangular_3d_mesh() → STL
Radial:      (R, Zb, Zt) → _revolve_polygon() → radial_bottom.stl + radial_top.stl
```

### Key invariant: two-layer system

Every profile has two separate layers:
1. **2D math layer** (`get_tractrix`, `get_salmon`, `get_exponential`, etc.) — returns `(z, r)` arrays only, no side effects.
2. **3D mesh engine** (`generate_3d_mesh_from_profile` or `generate_rectangular_3d_mesh`) — profile-agnostic, takes any valid `(z, r)` and produces watertight STL via revolution + normal offset.

The axisymmetric engine in `profile_generator.py` is shared by tractrix, salmon, and exponential. Rectangular and radial have their own dedicated engines.

**Constant-thickness invariant**: the axisymmetric engine offsets the inner profile along the meridian normal (a true parallel offset → constant perpendicular wall thickness, no axial shift). This leaves a slanted throat rim, so the engine slices the base flat with a plane (`slice_plane(..., cap=True)`) and re-caps it. Anything that needs the wall's *axial* extent at the mouth (e.g. the mouth-flange flush thickness in `ui_app.py`) must replicate the same `z_o = z_i + n_z·thickness` offset — keep them in sync.

### Modules

| Module | Role |
|---|---|
| `src/profile_generator.py` | Axisymmetric profiles (tractrix, salmon, exponential) + shared 3D revolution engine |
| `src/rectangular_horn.py` | Rectangular area-preserving profile + dedicated lofting engine |
| `src/radial_horn.py` | 360° omnidirectional radial horn, two-piece output (bottom + top) |
| `src/flange_generator.py` | Parametric circular mounting flange |
| `src/rectangular_flange.py` | Circular-outer / rectangular-inner flange |
| `src/_step_export.py` | STEP AP242 export utility |
| `src/_utils.py` | Shared math: profile normals, volume sign, Z-align |
| `src/_constants.py` | `SOUND_SPEED = 343000 mm/s` |
| `src/main.py` | CLI orchestrator (thin wrapper over profile_generator) |
| `ui_app.py` | Streamlit web UI — three tabs: Generate, Flange, Merge |

### Acoustic constants

- Exponential expansion rate: `m = 4π·fc/c`
- Salmon: hyperbolic-exponential with `T = 0.707` (Hypex), `x₀ = c/(2π·fc)`
- Radial: `S(R) = S_t · exp(m·(R−Rt))`, `H(R) = S(R)/(2πR)`

### STL output directory

All generated files go to `io/`. The directory must exist (kept via `io/.gitkeep`).

## Critical rule: UI must stay in sync with `src/`

When modifying any Python module under `src/`:

| Change | Required UI update in `ui_app.py` |
|---|---|
| New profile function | Add to `st.selectbox()`, add parameter inputs, add generation branch |
| New 3D engine module | Add lazy import + generation branch + download buttons |
| New flange generator | Add flange type in Tab 2 with inputs and generation branch |
| Changed function signature | Update `gen_args` list and the function call |
| Changed profile name/label format | Update the `_label.startswith()` check in Tab 3 (merge) |
| Profile that can't be merged (like radial) | Update merge guard in Tab 3 |

Always add a test case in `tests/test_all.py` for new profiles.

### Radial petal joint

`slice_into_petals()` accepts `joint_depth` and `joint_margin`. When `joint_depth > 0`:
- **2 petals**: the two halves share a single diametric seam plane that crosses the axis, so its cross-section yields **two** wall strips (one either side). Each half gets a **tongue on one strip and a groove on the other** (hermaphrodite — one male + one female per petal). The strip assignment flips between the two halves (`side = +1` for petal 0, `-1` for petal 1, against a fixed global `axis`) so a tongue always faces a groove. The two halves come out as **identical parts** (one is the other rotated 180° about Z).
- **3+ petals**: centred groove on left seam + centred tongue on right seam (both via boolean ops)

For n==2, `add_radial_tongue`/`add_radial_groove` take a `side`/`axis` selector (via `_filter_polys_by_side`) to restrict the joint to one of the two strips; for n>=3 there is a single strip and `side=0` (no filter). The tongue extrudes from `z=-overlap` so it overlaps the petal body volumetrically — a bare coplanar touch does not reliably weld in a boolean union.

Key helper functions in `_slicer.py`:
- `add_radial_tongue()` — extrudes inset polygon(s) outward along seam normal
- `add_radial_groove()` — booleans out inset polygon(s) inward along seam normal
- `_seam_face_polygons()` — returns all significant seam-face polygons + `to_3D` transform (uses `to_2D(normal=...)`); drops slivers below `min_area_frac` of the largest
- `_buffer_single()` — shapely buffer returning single Polygon (handles MultiPolygon)
