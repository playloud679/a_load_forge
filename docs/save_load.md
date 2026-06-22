# `src/save_load.py` — Parameter persistence (.flr)

Saves and loads flare_forge generation parameters to/from ``.flr`` files.

``.flr`` is plain JSON with a branded extension.  Every file carries a small
``_flare_forge_meta`` block (version + format) so future readers can migrate
old parameter sets.

## API

### `save(params, path) → Path`

Writes a flat ``dict`` of parameter names to JSON-serialisable values.
``.flr`` is appended to *path* if missing.

### `load(path) → dict`

Reads a ``.flr`` file and returns the parameter dictionary (without the
internal meta key).

## File structure

```json
{
  "_flare_forge_meta": {"version": "2.20.0", "format": 1},
  "throat_d": 25.4,
  "mouth_d": 300.0,
  "fc": 500.0,
  ...
}
```

## UI integration

In `ui_app.py` the module is imported and reloaded alongside the other
generator modules.  Two buttons (💾 Save parameters / 📂 Load parameters)
appear in the sidebar; they collect every `st.session_state` key that starts
with a known parameter prefix and serialize / deserialize them through
`save()` / `load()`.
