# Agent Instructions for AI Coding Assistants

## Critical Rule: Web UI must stay in sync with Python modules

Whenever you modify a Python module under `src/` (add a new profile, change a function signature, add a new generator, etc.), you **must** update the Streamlit UI in `ui_app.py` accordingly:

### Checklist for changes

| Python change | Required UI update |
|---|---|
| New profile function (e.g. `get_xxx()` in `01_profile_generator.py`) | Add profile to the `st.selectbox()` in Tab 1, add parameter inputs, add generation branch |
| New 3D engine module (e.g. `03_xxx.py`) | Add lazy import + generation branch in Tab 1, add download buttons |
| New flange generator | Add flange type in Tab 2, add parameter inputs and generation branch |
| Changed function signature (e.g. added/removed a parameter) | Update the `gen_args` list and the function call in Tab 1 |
| Changed profile name or label format | Update the `_label.startswith()` check in Tab 3 (merge) |
| Added a new profile type that can/cannot be merged | Update the merge logic in Tab 3 |

### Concrete pattern for adding a new profile

1. Add the profile name to the `st.selectbox()` in Tab 1:
   ```python
   profile = st.selectbox("Profile",
       ["tractrix", "lecleach", "iwata", "rectangular", "radial", "newprofile"], ...)
   ```

2. Add parameter inputs for the new profile in the `if/elif` chain below the selectbox.

3. Add a generation branch in the `if profile == "newprofile":` block inside the `gen_btn` handler.

4. Add metrics and download buttons for the new profile in the metrics section.

5. If the profile can't be merged (like radial), update the merge guard in Tab 3.

6. Add a test case in `tests/test_all.py`.

### Running the test suite

```bash
.venv/bin/python tests/test_all.py
```

All tests must pass before committing.
