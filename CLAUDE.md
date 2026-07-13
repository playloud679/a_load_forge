# CLAUDE.md

Guidance for coding agents working in this repository.

## Mandatory Documentation Contract

If you modify any `src/*.py` module, update the matching `docs/<module>.md` in
the same change.  The docs are the token-saving source of truth for future
agents.  A stale doc is treated as a broken build.

## Mandatory Test Contract

While patching Python:

```bash
.venv/bin/python -m py_compile ui_app.py src/dccav.py tests/test_all.py
.venv/bin/python tests/test_all.py -m dccav
```

For UI changes:

```bash
.venv/bin/python -c 'from streamlit.testing.v1 import AppTest; at = AppTest.from_file("ui_app.py", default_timeout=30); at.run(); assert not at.exception, at.exception'
```

Before any commit touching Python, run the full active suite fresh:

```bash
.venv/bin/python tests/test_all.py
```

Do not claim a test passed unless it was actually run.

## Active Architecture

Load Forge is a Streamlit acoustic-load simulator.

```text
ui_app.py -> src/dccav.py -> docs/dccav.md -> tests/test_all.py
```

The current simulator supports DCCAV / double asymmetric reflex:

```text
driver -> upper volume || upper port -> lower volume || lower port
```

plus conventional bass reflex, acoustic suspension / sealed box and ideal
infinite baffle.

Inputs are driver T/S parameters plus chamber/tuning/loss controls.  Outputs are
response plots, metrics and CSV export.

## Commands

```bash
make install
make run
.venv/bin/python tests/test_all.py -m dccav
make test
```

## Module Notes

| Module/File | Role |
|---|---|
| `ui_app.py` | Streamlit single-page dashboard |
| `src/dccav.py` | DCCAV/reflex/sealed/infinite-baffle formulas and simulation |
| `docs/dccav.md` | Public API, formulas, assumptions and tests |
| `tests/test_all.py` | Focused custom runner with 42 acoustic-load tests |

## Streamlit Reload Rule

Any `src/` module used in `ui_app.py` must be imported as a module and reloaded:

```python
import dccav as _dccav
import importlib
importlib.reload(_dccav)
```

Add new imports/reloads when adding new active helper modules.

## Change Scope

Keep edits narrow and inside the active acoustic-load simulation surface unless
the user explicitly changes the product direction.  Do not push unless
explicitly requested.
