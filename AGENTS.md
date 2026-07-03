# Agent Instructions for AI Coding Assistants

## ⛔ Rule 0: docs/ MUST stay in sync with src/

Editing any `src/*.py` REQUIRES updating its `docs/<module>.md` in the same
change. The docs are read instead of the source to save tokens — a stale doc
misleads every future agent. No exceptions; create the doc if missing.

## ⛔ Rule 1: targeted tests while patching, fresh full suites before commit

- **While patching**: after every meaningful change to `src/*.py` or
  `ui_app.py`, immediately run the targeted tests for the touched area —
  `.venv/bin/python tests/test_all.py -m "<keyword>"` (e.g. `-m poly`,
  `-m omni`, `-m flange`, `-m adapter`, `-m slicer`). New/changed behaviour
  REQUIRES a new/updated test in the same change. `ui_app.py` is not covered
  by the suite: its targeted test is a `streamlit.testing.v1.AppTest` run
  that exercises the touched path (set `session_state`, click **Generate
  Assembly STL**, assert `not at.exception`).
- **Before EVERY commit touching any `*.py`**: run BOTH full suites fresh,
  after the last edit (earlier session results do not count, even for
  "UI-only" changes): `.venv/bin/python tests/test_all.py` AND
  `.venv/bin/python tests/test_geometry.py` (or `make test`). Commit only on
  0 failures and record the pass counts in the `CHANGELOG.md` entry.

## Critical Rule: Web UI must stay in sync with Python modules

Whenever you modify a Python module under `src/` (add a new profile, change a function signature, add a new generator, etc.), you **must** update the Streamlit UI in `ui_app.py` accordingly:

### Checklist for changes

> **Layout note:** the UI is now a single-page dashboard, not tabs. Map the
> legacy labels below as: **Tab 1 → "Acoustic Profile"**, **Tab 2 → "Mounting
> Flanges"**, **Tab 3 → "Generate Assembly"** (the merge is step 3e there).
> There is no `gen_args` list anymore — dispatch is via `profile_type.startswith(...)`.

| Python change | Required UI update |
|---|---|
| New profile function (e.g. `get_xxx()` in `profile_generator.py`) | Add profile to the `st.selectbox()` in Tab 1, add parameter inputs, add generation branch |
| New 3D engine or slicer module (e.g. `_slicer.py`) | Add lazy import + UI section with controls and download buttons |
| New flange generator | Add flange type in Tab 2, add parameter inputs and generation branch |
| Changed function signature (e.g. added/removed a parameter) | Update the `gen_args` list and the function call in Tab 1 |
| Changed profile name or label format | Update the `_label.startswith()` check in Tab 3 (merge) |
| Added a new profile type that can/cannot be merged | Update the merge logic in Tab 3 |
| New radial joint feature (tongue & groove) | Add checkbox + depth + clearance controls in Slice section; `slice_into_petals()` accepts `joint_depth`, `clearance` |
| Changed radial joint behaviour | `slice_into_petals()`: n>=3 → groove on left seam + tongue on right; n==2 → hermaphrodite (identical parts). No UI change needed. |
| Re‑enable Rectangular section | Add `"Rectangular"` to `section_type` radio; set `is_rect`; show W×H inputs for throat/mouth; add preview + flange + generation branches |
| New throat adapter feature (`src/throat_adapter.py`) | Add `import throat_adapter as _ta` + `importlib.reload(_ta)` at top of `ui_app.py`. In throat flange section (rect/poly): add "Include shape adapter" checkbox + "Driver interface" radio (Flanged / Threaded 1" / 1¼" / 2") + adapter length + socket depth. In generation: call `_ta.make_adapter_assembly()` for adapter path, falls through to existing rect/poly flange when adapter is off. |
| Changed `make_adapter_assembly` signature | If you change parameters, update both the UI call in the generation block and the test cases in `tests/test_all.py`. |
| New `throat_adapter.py` module | See module docstring. `THREAD_SPECS` dict for standard thread sizes. Key functions: `make_adapter()` (transition loft only), `make_threaded_socket()`, `make_adapter_assembly()` (full assembly). Add to the `importlib.reload()` block and test suite. |

### Concrete pattern for adding a new profile

1. Add the profile name to the `st.selectbox()` in Tab 1:
   ```python
   profile = st.selectbox("Profile",
        ["tractrix", "salmon", "exponential", "newprofile"], ...)
   ```

2. Add parameter inputs for the new profile in the `if/elif` chain below the selectbox.

3. Add a generation branch in the `if profile == "newprofile":` block inside the `gen_btn` handler.

4. Add metrics and download buttons for the new profile in the metrics section.

5. If the profile can't be merged (like radial), update the merge guard in Tab 3.

6. Add a test case in `tests/test_all.py`.

### Test execution hierarchy

Do **not** run the full 230+ test suite after every small edit by default.
Use a tiered approach:

1. **During focused development / bug fixing**, run only the smallest relevant
   checks:
   ```bash
   .venv/bin/python -m py_compile ui_app.py tests/test_all.py
   .venv/bin/python tests/test_all.py --match "complete rollback"
   .venv/bin/python tests/test_geometry.py --match "outer shape"
   make test-match MATCH="complete rollback"
   ```

2. **When touching shared geometry, flange, slicer, adapter, or profile code**,
   run the matching focused tests first, then broaden only to the affected
   suite:
   ```bash
   make test-all        # tests/test_all.py only
   make test-geometry   # tests/test_geometry.py only
   ```

3. **Before committing, opening a PR, or handing off a finished change**, run
   the full suite:
   ```bash
   make test
   ```

The test runners support repeated label filters:

```bash
.venv/bin/python tests/test_all.py --match "rollback" --match "adapter"
```

If a `--match` filter finds no tests, the runner exits with code `2`; adjust
the filter instead of treating it as a pass.

### Full pre-commit test suite

```bash
.venv/bin/python tests/test_all.py
.venv/bin/python tests/test_geometry.py
```

All tests must pass before committing.

### Running the app

```bash
make run          # Streamlit headless + opens in Safari
```

### Mesh engine sync

`generate_3d_mesh_from_profile` (`profile_generator.py`) builds the wall with a
true **parallel** normal offset (constant thickness) and slices the throat base
flat. Any UI logic that depends on the wall's axial extent — e.g. the mouth
flange's flush default thickness in `ui_app.py` — must replicate the same
`z_o = z_i + n_z·thickness` offset. If you change the offset in the engine,
update that helper too.

## Streamlit Module Caching & Live Reloading

### The Caching Problem
Streamlit runs the main script (`ui_app.py`) in a long-lived Python process. Helper and generator modules imported from `src/` are cached in `sys.modules` by Python. When coding assistants modify these source files and Streamlit automatically reruns the main script, the cached versions are still used, meaning **your changes will have absolutely no effect in the running UI** until the Streamlit process is fully restarted.

### Mandatory Fix
**At the very top of `ui_app.py`**, right after the standard imports, you **must** import and reload every helper/generator module that lives under `src/` using `importlib.reload()`. This forces Python to re-execute the module's code and ensures that all edits are picked up immediately on UI reload.

### Concrete Pattern to Use

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import profile_generator as _core
import flange_generator as _fg
import rectangular_flange as _rf
import rectangular_horn as _rh
import radial_horn as _rd
import polygonal_horn as _ph
import _slicer as _slc
import throat_adapter as _ta

import importlib
importlib.reload(_core)
importlib.reload(_fg)
importlib.reload(_rf)
importlib.reload(_rh)
importlib.reload(_rd)
importlib.reload(_ph)
importlib.reload(_slc)
importlib.reload(_ta)
```

### Important Rules
1. `importlib.reload()` must be called **after** the module is imported.
2. If you add a new module under `src/` that is used in `ui_app.py`, you **must** add both its import and its reload call to this block.
3. Always import the full module (e.g. `import rectangular_horn as _rh`) rather than importing names from it, so that the module reference can be passed to `importlib.reload()`.
4. This ensures that every hot-reload picks up your latest changes immediately, without requiring a manual restart of Streamlit.
