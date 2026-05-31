# Changelog

## 2.2.6 (2026-05-31)

- **Renamed to flare_forge**: new brand name throughout — UI title, page tab, STEP export header, package name, download filenames
- **Full English translation**: all UI labels, captions, subheaders, button text, metrics, variable names (`espansione` → `profile_type`, `spessore` → `thickness`, `gola_out` → `throat_outer`, etc.), session state keys
- **STEP export rewritten**: correct AP203 schema — `FACETED_BREP` + `FACE_OUTER_BOUND` + `POLY_LOOP` (previously `MANIFOLD_SOLID_BREP` + `POLY_LOOP` was invalid and rejected by FreeCAD / Fusion 360 / SolidWorks); correct `PRODUCT_DEFINITION` chain; file 5× smaller (no per-triangle `DIRECTION`/`PLANE` entities)
- **Bug fix**: `_get_rect_profile` was defined after its first call — rectangular exponential metrics were silently never shown
- **Dead code removed**: unreachable second `elif is_rect` block in 2D preview; duplicate `get_rectangular_lecleach` / `get_rectangular_iwata` definitions with unreachable code in `rectangular_horn.py`; unused `_PROFILES` dict in `profile_generator.py`; unreachable `args.profile == "iwata"` condition in `resolve_profile`
- **Anti-pattern fix**: `'_var' not in dir()` checks replaced with explicit default initialization for all flange dimension variables

## 2.2.5 (2026-05-30)

- **Z-offset flat bottom fix**: Clipped `z_o` coordinates to the original `[z[0], z[-1]]` range in `rectangular_horn.py` to completely eliminate negative Z protrusions ("bordino") under the throat flange, ensuring a perfectly flat base.
- **Streamlit hot reload**: Added explicit `importlib.reload()` for all core generator modules at the top of `ui_app.py` to bypass Streamlit's module caching, ensuring that all subsequent code modifications immediately take effect in the active dashboard.
- **Agent instructions**: Updated `AGENTS.md` with guidelines on Streamlit module caching and hot reloading to prevent future caching issues.

## 2.2.4 (2026-05-29)

- **Architecture**: removed all `importlib.machinery.SourceFileLoader` — standard Python imports throughout
- **File rename**: `0*_*.py` → descriptive names (`profile_generator.py`, `flange_generator.py`, etc.)
- **ODE solver**: `get_lecleach` refactored to `scipy.integrate.solve_ivp` with RK45 + termination event
- **No vertex inference**: flange hole dimensions from analytical profile values, not 3D mesh sampling
- **STEP export**: download button alongside STL, uses `_step_export.py` for AP242 conversion
- **State management**: `on_change` callbacks on horn widgets, targeted `pop()` instead of destructive `del`
- **Rectangular flange patch**: `offset` parameter, `bolt_inset`, safety clamps, `thickness*3` boolean cylinders
- **LeCléac'h mouth fix**: hole sized from roll-back endpoint with 30mm shrink + 5mm minimum wall
- **Radial assembly**: both bottom + top in one STL, properly spaced by acoustic gap, top reflector rebuilt solid
- **Expansion × Section**: all 4 expansion types (Tractrix, LeCléac'h, Iwata, Exponential) × 2 sections (Circular, Rectangular)
- **Import/export**: standard `from src import profile_generator`, all tests pass from project root

## 2.2.3 (2026-05-29)

- **Refactored UI**: single-view monotab dashboard — Horn Profile + 2D Preview | Flanges | Assembly
- **Per-flange outer shape selector**: Circular (disc) or Rectangular (plate) — independently for throat, mouth, mid
- **Inner hole always matches horn profile**: circular for axisymmetric, rectangular for rectangular horns
- **Live 2D preview**: reactive Matplotlib plot, no "Show Preview" button
- **Smart rectangular defaults**: outer OD = corner diagonal + wall + 15mm, bolt circle = midpoint
- **Mid flange**: Z-offset from throat input, dimensions auto-intercepted from horn profile at that position
- **Rectangular flange outer W×H**: adjustable independent dimensions when Rectangular outer selected
- **`generate_rectangular_flange`**: accepts optional `outer_w`/`outer_h` for custom rectangular plate dimensions

## 2.2.2 (2026-05-28)

- **Three-column wide layout**: Horn Profile (left) | Flanges (center) | Assembly + Download (right) — no scrolling needed
- **Compact flange inputs**: Throat / Mouth / Mid in 3 side-by-side columns with collapsed labels
- **Compact metrics**: replaced `st.metric` with markdown for smaller result display
- Mid flange always visible (removed expander)

## 2.2.1 (2026-05-28)

- **English UI**: complete rewrite with proper acoustic terminology (throat, mouth, bolt circle, PCD)
- **Auto-recalculate on profile change**: flange defaults update automatically when switching profiles
- **LeCleach safety clamp**: flange OD capped at mouth diameter, hole auto-adjusted to fit
- **Duplicate element ID fix**: unique keys for all repeated labels (thickness, bolt count, etc.)
- **Integration test**: 5-profile full assembly test (`tests/test_integration.py`) — tractrix, lecleach, iwata, rectangular, radial — all watertight
- Fixed LeCleach inward flange logic in integration test

## 2.2.0 (2026-05-28)

- **Mid flange**: third adjustable flange at any position (5-95% of horn length), auto-calculated hole & bolt circle
- **Selective generation**: checkboxes to toggle horn, throat flange, mid flange, mouth flange independently before assembly
- Fixed stray `NameError` on mid flange variable for radial profiles
- Fixed `_tris`/`_vol` variable ordering in metrics display

## 2.1.0 (2026-05-28)

- **Flange calculator**: "Calcola flange" button auto-computes all diameters (outer, bolt circle) from horn geometry with real 2D profile generation for Le Cleac'h / Iwata
- **Le Cleac'h mouth flange**: positioned at roll-back (max radius), extruded backward, 10mm flange ring goes *inward* (verso il centro) instead of outward — outer edge flush with mouth, hole 20mm smaller
- **Derived metrics**: automatic display of Fc (tractrix), length, and mouth diameter on every parameter change
- Mouth flange hole sizing now profile-aware: local radius for standard profiles, max radius for Le Cleac'h roll-back
- Simplified flange parameter UI: session-state driven inputs, removed scattered inline computations

## 2.0.0 (2026-05-28)

- Circular flange rewritten with CSG boolean operations (trimesh + manifold3d): bolt holes are now genuine cutouts, no more overlapping geometry artifacts
- Fixed throat Z-alignment: outer and inner profiles now share the same Z origin, ensuring a flat bottom annulus for perfect flange mating
- Fixed mouth flange positioning: uses max Z instead of max-radius vertex, eliminating gap (was 3mm on tractrix, 84mm on Le Cleac'h)
- Throat flange now grows upward (into horn body) instead of downward, ensuring proper boolean union merge
- Shared constants module (`src/_constants.py`): single source for SOUND_SPEED
- Shared utilities module (`src/_utils.py`): compute_profile_normals, ensure_positive_volume, align_z_to_zero
- CLI orchestrator rewritten: direct function calls via importlib instead of subprocess
- Web UI: unified lazy-import helper, radial horn uses temp files, circular flange returns trimesh directly
- Cleaned up dead code: removed unused `_bc()` function from radial horn, simplified redundant expression
- Added `pyproject.toml`, `manifold3d` and `streamlit` to dependencies
- README: corrected test count (16 → 18), updated project structure

## 1.4.0 (2026-05-26)

- Rectangular flange: circular outer shape, rectangular inner hole, N bolts on adjustable circle
- Web UI: flange type selector with circular/rectangular options
- Merge Tab: concatenation for rectangular horn+flange (no boolean)

## 1.3.0 (2026-05-26)

- Fixed radial horn: `_revolve_polygon` replaces `_revolve_profile` (no center caps, closed 4-loop)
- Fixed UI: guard `if profile not in ("rectangular", "radial")` prevents `z=None` error
- Added comprehensive test suite (`tests/test_all.py`): 16 tests, all profiles
- Added radial horn to Web UI (dual-piece download)
- Rectangular horn engine + Web UI integration

## 1.0.0 (2026-05-26)

- Initial release
- Three acoustic profiles: Tractrix, Le Cléac'h (Euler integration with 160° roll-back), Iwata (Salmon T=0.707)
- Shared 3D mesh engine: normal-vector offset, revolution, watertight STL
- Parametric circular flange generator (outer/inner diameter, bolt holes)
- Web UI (Streamlit) with horn, flange, and merge tabs
- CLI orchestrator (`python -m src.main`)
- Cutoff frequency (Fc) calculation and display for all profiles
- Boundary protection for degenerate profiles
- Automatic normal flip on negative volume
- Multi-section horn splitting for 250mm³ printers
- Merge flange + horn into single watertight STL
