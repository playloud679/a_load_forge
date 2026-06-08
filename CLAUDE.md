# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> ## ⛔ MANDATORY — DOCS STAY IN SYNC WITH CODE
> **If you modify any `src/*.py` module, you MUST update its matching
> `docs/<module>.md` in the same change.** The per-module docs in `docs/` are the
> token-saving source of truth: agents read them *instead of* the full source. A
> stale doc silently misleads every future agent — it is worse than no doc.
>
> This applies to every signature change, new function, renamed profile, or
> behaviour change. No exceptions. If a `docs/<module>.md` does not yet exist for
> a module you touched, create it. Treat an out-of-sync doc as a broken build.

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
| `src/profile_generator.py` | Axisymmetric profiles (tractrix, salmon, exponential, **Le Cléac'h**) + shared 3D revolution engine |
| `src/polygonal_horn.py` | Polygonal N-gon section engine (area-matched to circular equivalent) |
| `src/rectangular_horn.py` | Rectangular area-preserving profiles + the faithful **Iwata** dual-flare profile (`get_iwata_horn`) + dedicated lofting engine |
| `src/radial_horn.py` | 360° omnidirectional radial horn, two-piece output (bottom + top) |
| `src/throat_adapter.py` | Throat adapter: round driver → rect/poly transition, threaded (1"/1¼"/2" UNF) or flanged interface |
| `src/flange_generator.py` | Parametric circular mounting flange |
| `src/rectangular_flange.py` | Circular-outer / rectangular-inner flange |
| `src/_step_export.py` | STEP AP203 export utility |
| `src/dxf_export.py` | 2D DXF drilling-template export from a flange mesh (bolt holes + bore + outline on layers) |
| `src/_utils.py` | Shared math: profile normals, volume sign, Z-align |
| `src/_constants.py` | `SOUND_SPEED = 344000 mm/s` (Hornresp default; UI-adjustable, see below) |
| `src/main.py` | CLI orchestrator (thin wrapper over profile_generator) |
| `ui_app.py` | Streamlit single-page dashboard — sections: Acoustic Profile, Mounting Flanges, Generate Assembly (merge is step 3e), Slice STL |

### Iwata profile (special case)

The "Iwata" profile is **not** axisymmetric. It is the real horn from the
l'Audiophile plan (for JBL 2440/375): a *rectangular dual-flare* whose width and
height expand at different rates (mouth ≈ 740×320 over 550 mm, throat ≈ 50×50),
digitized into `get_iwata_horn(throat, length)` in `rectangular_horn.py`. The noisy
hand-read stations are fitted with a smooth monotone curve (`_iwata_smooth`: cubic in
log-space, both endpoints anchored) rather than interpolated through every point —
PCHIP-through-all-points reproduced the reading noise as visible ripples on the wall.
A uniform scale (`throat`) + axial stretch (`length`) preserve the plan's proportions.

In the UI, selecting Iwata **forces `is_rect = True` and ignores the Section
selector** (like radial is special), and the inputs collapse to throat Ø + length
(no mouth/aspect/Fc — those are intrinsic; Fc is derived ≈ c·ln(Sm/St)/(4π·L) and
shown as a result). The axisymmetric `get_iwata` in `profile_generator.py` (Salmon
T=0.707) is now CLI-only; the UI never calls it.

**Curved mouth**: the wide (plan) plane mouth is a circular arc (native r=692 mm
about apex "point R", ~120 mm behind the throat), the height plane stays flat.
`iwata_arc_mouth(throat, length)` returns the `(radius, center_z)` of a height-axis
(Y) cylinder; the generation step in `ui_app.py` **boolean-intersects** the straight
rectangular loft with that cylinder (manifold engine) to roll the corners back. Because
the mouth is curved, the **mouth flange is disabled** for Iwata (only throat/mid).
Per Petoin's analysis the Iwata is essentially a Le Cléac'h horn (hypex area law,
F≈207 Hz, T≈0.5), but the geometry here is taken from the digitized drawing
(constant-z stations), not re-derived from the isophase ODE.

### Acoustic constants

- Exponential expansion rate: `m = 4π·fc/c`
- Salmon: hyperbolic-exponential with `T = 0.707` (Hypex), `x₀ = c/(2π·fc)`
- Radial: `S(R) = S_t · exp(m·(R−Rt))`, `H(R) = S(R)/(2πR)`

**Adjustable speed of sound**: `c` defaults to `_constants.SOUND_SPEED` (344000 mm/s)
but is a UI input (Advanced settings, m/s). The flare functions read `SOUND_SPEED`
from their *module* global at call time, so `ui_app.py` overrides it after the
`importlib.reload` block — `_core.SOUND_SPEED = _rh.SOUND_SPEED = _rd.SOUND_SPEED =
c_val` — and every cutoff/mouth calc picks it up. Don't reintroduce hardcoded `c`
literals in `ui_app.py`; use `c_val`.

**Mouth-size adequacy warning**: the Computed panel warns when the area-equivalent
mouth Ø is below `c/(π·fc)` (mouth circumference < one wavelength at cutoff), i.e.
the horn won't actually load down to the stated Fc.

### STL output directory

All generated files go to `io/`. The directory must exist (kept via `io/.gitkeep`).

## Critical rule: UI must stay in sync with `src/`

When modifying any Python module under `src/`:

| Change | Required UI update in `ui_app.py` |
|---|---|
| New profile function | Add to `st.selectbox()`, add parameter inputs, add generation branch |
| New 3D engine module | Add lazy import + generation branch + download buttons |
| New flange generator | Add flange type in the Mounting Flanges section with inputs and generation branch |
| Changed function signature | Update the profile-dispatch call in the Generate Assembly section (the `profile_type.startswith(...)` branch), not a `gen_args` list |
| Changed profile name/label format | Update the `profile_type.startswith()` / `section_type.startswith()` checks and the merge step (3e) in Generate Assembly |
| Profile that can't be merged (like radial) | Update the merge guard in the Generate Assembly merge step (3e) |

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
