# Agent Instructions for AI Coding Assistants

## Critical Rule: Web UI must stay in sync with Python modules

Whenever you modify a Python module under `src/` (add a new profile, change a function signature, add a new generator, etc.), you **must** update the Streamlit UI in `ui_app.py` accordingly:

### Checklist for changes

| Python change | Required UI update |
|---|---|
| New profile function (e.g. `get_xxx()` in `profile_generator.py`) | Add profile to the `st.selectbox()` in Tab 1, add parameter inputs, add generation branch |
| New 3D engine or slicer module (e.g. `_slicer.py`) | Add lazy import + UI section with controls and download buttons |
| New flange generator | Add flange type in Tab 2, add parameter inputs and generation branch |
| Changed function signature (e.g. added/removed a parameter) | Update the `gen_args` list and the function call in Tab 1 |
| Changed profile name or label format | Update the `_label.startswith()` check in Tab 3 (merge) |
| Added a new profile type that can/cannot be merged | Update the merge logic in Tab 3 |
| New radial joint feature (tongue & groove) | Add checkbox + depth control in Tab 3; `slice_into_petals()` accepts `joint_depth` |
| Changed radial joint behaviour | `slice_into_petals()`: n>=3 → groove on left seam + tongue on right; n==2 → the single diametric seam has two wall strips, so each half gets a tongue on one strip + groove on the other (hermaphrodite, identical parts). No UI change needed. |

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

### Running the test suite

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

import importlib
importlib.reload(_core)
importlib.reload(_fg)
importlib.reload(_rf)
importlib.reload(_rh)
importlib.reload(_rd)
```

### Important Rules
1. `importlib.reload()` must be called **after** the module is imported.
2. If you add a new module under `src/` that is used in `ui_app.py`, you **must** add both its import and its reload call to this block.
3. Always import the full module (e.g. `import rectangular_horn as _rh`) rather than importing names from it, so that the module reference can be passed to `importlib.reload()`.
4. This ensures that every hot-reload picks up your latest changes immediately, without requiring a manual restart of Streamlit.

