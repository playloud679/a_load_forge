# Changelog

## 2.4.2 (2026-06-02)

- **Fix giunto radiale a 2 petali**: prima il caso `n=2` faceva il joint su una sola faccia (lo step a tutta faccia cancellava il materiale della lingua, che falliva silenziosamente). Causa: con 2 petali i due piani di taglio sono complanari (`normal0 == normal1`) — un unico piano diametrale che attraversa l'asse e taglia la parete in **due strisce**, mentre `_seam_face_polygon` ne teneva solo la più grande.
- **Petali ermafroditi (maschio + femmina su ogni pezzo)**: nel caso `n=2` ogni metà riceve ora una **lingua su una striscia e una scanalatura sull'altra**; l'assegnazione si inverte fra le due metà (`side`/`axis` rispetto a un asse globale fisso) così che maschio e femmina si fronteggino sempre. Le due metà risultano **pezzi identici** (uno è l'altro ruotato di 180° attorno a Z). Per `n>=3` il comportamento (scanalatura a sinistra + lingua a destra) è invariato.
- **`_seam_face_polygon` → `_seam_face_polygons`**: ritorna tutte le strisce significative della sezione del seam (sliver sotto il 5% dell'area massima scartati); `add_radial_tongue`/`add_radial_groove` iterano su tutte le strisce e accettano un selettore `side`/`axis` (via `_filter_polys_by_side`) per limitare il giunto a una striscia.
- **Lingua con overlap nel corpo**: la lingua parte ora da `z=-overlap` così da compenetrare il petalo — un contatto puramente complanare non si saldava in modo affidabile nella union (causava `body_count == 2`). Rimossa la funzione `_apply_step_joint` non più usata.
- **Test**: check `n=2` rinforzato — verifica che ogni petalo abbia una lingua che sporge oltre il seam su una striscia e che le due metà siano pezzi identici (54 test, tutti verdi).

## 2.4.1 (2026-06-02)

- **Radial joint (tongue & groove)**: nuovo interlock per petali radiali. Ogni petalo riceve una lingua maschio su un seam e una scanalatura femmina sull'altro. Supportato per 2+ petali:
  - 2 petali: step joint (intera faccia arretrata 2mm) + lingua sporgente
  - 3+ petali: scanalatura centrale 2mm + lingua sporgente 2mm
  - `slice_into_petals()` ora accetta parametri `joint_depth` e `joint_margin`
- **Fix robustezza booleane**: overlap di 1mm nelle estrusioni per evitare facce coincidenti con manifold3d; re-merge dei corpi a volume negativo dopo union
- **Fix `_seam_face_polygon`**: `to_2D(normal=normal)` esplicito per allineamento corretto del sistema di riferimento; filtro `None` in `polygons_closed` che causava crash con 3 petali
- **UI — Controllo "Radial joint (tongue & groove)"**: checkbox + joint depth in Tab 3 (Slice STL), disabilitato di default

## 2.4.0 (2026-06-02)

- **Spessore parete costante (vero offset 3D)**: l'engine assisimmetrico (`profile_generator.py`) ora usa un offset parallelo puro lungo la normale del meridiano — per un solido di rivoluzione coincide con un offset 3D, quindi lo spessore perpendicolare è **costante ovunque** (verificato min=max=thickness). Rimosso lo shift assiale `z_o -= z_o[0]` che assottigliava progressivamente la parete verso la bocca (fino a ~0.8 mm su 4).
- **Base gola tagliata piatta**: poiché l'offset parallelo lascerebbe il bordo di gola inclinato, la base viene sezionata con un piano e richiusa via trimesh → faccia di gola perfettamente planare, mantenendo lo spessore uniforme sulle pareti.
- **Mouth flange a filo**: lo spessore di default della mouth flange ora è l'**estensione assiale** della parete alla bocca (`thickness·|n_z|`), non lo spessore lungo la normale. La flangia termina a filo con il flare, senza bordino sporgente. Si riallinea automaticamente al cambio di wall thickness.
- **Petali senza tasselli**: rimosso l'interlock a tassello (tab/slot alternati) dai seam radiali; `slice_into_petals()` taglia con seam piatti puliti. Rimosse le funzioni helper non più usate.
- **2D Preview parallelo**: la linea "+ wall" del preview ora disegna l'offset parallelo lungo la normale (sia circolare che poligonale), coerente con la geometria stampata, invece di un offset radiale a Z costante.
- **`make run` / `run.sh`**: avvia l'app e la apre in Safari (Streamlit headless + `open -a Safari`).
- **`requirements.txt` / `pyproject.toml`**: `trimesh[easy]` per includere le dipendenze opzionali (networkx, rtree, …) necessarie allo slicing dei petali.

## 2.3.0 (2026-06-01)

- **`get_iwata()`** renamed to **`get_salmon(T)`** — la formula è Salmon hyperbolic-exponential, non Iwata. Parametro `T` variabile (0=catenoidale, 0.707=Hypex, 1=exponenziale).
- **Nuovo preset `get_iwata()`** — wrapper per `get_salmon(T=0.707)`, per chi cerca il nome classico Iwata.
- **Nuovo `get_lecleach()`** — ODE isofase con legge d'area Salmon + parametro `max_angle` (roll-back 90-180°). Corrisponde al flare type "Le Cléac'h" di Hornresp.
- **Rimosso `get_rectangular_iwata()`** → rinominato `get_rectangular_salmon()`.
- **`src/_slicer.py`** — nuovo modulo per sezionare mesh STL in segmenti assiali e petali radiali.
- **UI — Sezione "Slice STL"**: taglio assiale (per conteggio o altezza) + petali radiali con conteggio variabile per segmento. Download singolo o ZIP.
- **UI — Flange**: Mouth flange disabilitata su Le Cléac'h (roll-back incompatibile). Mid-flange attivo di default su Le Cléac'h.
- **UI — Helper cm²**: sotto Throat/Mouth Ø mostra area equivalente in cm² (formato Hornresp).
- **Documentazione**: AGENTS.md, CLAUDE.md, README.md allineati ai nuovi nomi.

## 2.2.10 (2026-06-01)

- **Removed `get_lecleach()`**: profilo ODE isofase rimosso. Non corrispondeva al "Le Cléac'h horn" della comunità audio (che è `get_iwata(T=0.707)`). Rimossi tutti i riferimenti da UI, CLI, test, radial/rectangular horn e docs.

## 2.2.9 (2026-06-01)

- **Buy Me a Coffee button**: a "☕ Buy me a coffee" link button in the header. Set `BMC_USERNAME` at the top of `ui_app.py`; until it's filled in, the button hides and shows a reminder instead of a broken link.

## 2.2.8 (2026-06-01)

UI clarity pass on the dimensions inputs, plus three flange-parameter bugs found
by actually measuring the generated solid instead of trusting that the value reached
it. All in `ui_app.py`.

### Dimensions inputs

- Each profile is driven by a different set of inputs (Tractrix: throat+mouth; Le Cléac'h: throat+Fc; Iwata: throat+Fc+length; Exponential: throat+mouth+Fc). A one-line hint now states which you set and which follow.
- The fields you don't set are no longer blank or a cryptic "—". They show the **computed value live, greyed out** — Le Cléac'h shows the resulting mouth Ø, Tractrix shows the derived Fc and length, etc. Implemented by reading the editable inputs first, solving the profile once, then filling the read-only fields.
- Per-profile help on Fc (flare rate for Exponential vs cutoff for Le Cléac'h/Iwata); units unified (polygonal mouth shown as a diameter across corners).

### Flange bolt circle — three bugs

- **Polygonal outer was ignored on circular-hole flanges**: `generate_flange` rendered a circle no matter the selection. (Fixed in the engine in 2.2.7; the UI now passes `outer_n_sides` through for throat/mouth/mid.)
- **Editing the bolt circle did nothing**: the widgets used the `st.number_input(value=…, key=…)` anti-pattern, so the recomputed default fought the user's value on every rerun. Switched to the canonical pattern — seed `session_state` once if absent, then create the widget with `key` and no `value`. The radial throat bolt circle also shared key `ft_bc` with the non-radial one (a latent crash when switching sections); it now has its own key.
- **Moving bolts outward made them vanish, or (after a first fix) wrongly grew the flange**: the bolt circle is now clamped to a valid band inside the ring — from just outside the hole to just inside the outer edge (the inradius, on polygons). The flange size is set solely by the ring width; the bolts slide within it and can't be pushed off the edge. To seat bolts further out you widen the ring. Verified by measuring bolt-hole radii in the generated mesh across the range.

### Robustness

- `_clamp_state` keeps a persisted widget value within its current min/max before the widget is created, so changing the horn (which changes the flange bounds) can't raise `StreamlitValueAboveMaxError` mid-run.

## 2.2.7 (2026-05-31)

Cross-section overhaul plus a round of flange-correctness fixes. Most of these were
bugs that produced a plausible-looking but wrong solid — the kind you only catch when
you load the STL in a slicer, which is exactly why this release also rewrites the tests.

### Cross-section is now its own axis

- **Polygonal section** replaces Rectangular: regular N-gon (3–12 sides) at every Z slice, area-matched to the equivalent circle. The old rectangular lofting engine is gone.
- **Radial 360°** is no longer a separate "profile" — it's a section type, so it now composes with all four expansion curves (Tractrix, Le Cléac'h, Iwata, Exponential), not just exponential.
- The model is now cleanly **4 expansion profiles × 3 sections** (Circular, Polygonal, Radial), instead of profiles and sections being tangled together.

### Exponential + Circular was silently broken

`get_exponential` only existed inline in the UI, and only on the Polygonal path. With a
Circular section the code fell through to `get_iwata` in **five** places — mouth input,
derived metrics, 2D preview, flange sizing, and final generation — so you'd ask for an
exponential horn and quietly get an Iwata. Extracted `get_exponential` to
`profile_generator.py` as a first-class profile and wired all five paths to it.

### Polygonal flange outer shape

- `generate_flange` ignored `outer_n_sides`, so selecting a "Polygonal" outer on a circular-hole flange always rendered a **circle**. Added the parameter; the outer body can now be an N-gon prism.
- **Ring width on polygonal outers now means wall thickness at the flat faces** (the minimum wall), with circumradius `= (inner_R + ring) / cos(π/N)`. Before, ring width was the corner extension, so for a large hole the flat-face wall went negative and the round hole punched through the polygon edges — leaving four detached corner triangles. With the new definition the default 15 mm is valid for any side count and the wall is uniform where it's thinnest.
- **Auto-expand guard**: if the inner hole would still exceed the polygon inradius, `flange_R` grows to fit instead of producing a broken solid.
- Reordered the flange input blocks (outer-shape selector before ring width), which also removes a latent `NameError` that would fire the moment you picked Polygonal.

### Other fixes

- **Mid flange** distance is clamped to the horn length, and the midpoint percentage is clamped to 100 — it was indexing past the end of the profile array.
- **Le Cléac'h mouth flange** hole is now sized `inner_R + thickness` like every other circular profile; it was missing the wall offset, so the hole sat on the inner wall instead of the outer.
- `generate_flange` defaults `output_path=None` — it no longer writes `io/flange.stl` as a side effect on every UI generation.

### Tests

- `tests/test_all.py` rewritten: **18 → 54**. Real geometric assertions (watertight, single body, positive volume, correct mouth radius) across the full profile × section matrix, instead of "didn't throw".
- New `tests/test_geometry.py` (**36 tests**): checks output *shape* the way you would in a slicer — sections the mesh, isolates the outer contour, and measures `max_r / min_r` (1.0 = circle, `1/cos(π/N)` = N-gon). This is the test that catches "polygonal flange came out round" and "ring width isn't a uniform 15 mm wall".

### Dependencies

- `shapely>=2.0.0` (polygon extrusion for N-gon flange bodies)

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
