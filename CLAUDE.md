# CLAUDE.md

Guidance for coding agents working in this repository.

## Mandatory Documentation Contract

If you modify any `src/*.py` module, update the matching `docs/<module>.md` in
the same change.  The docs are the token-saving source of truth for future
agents.  A stale doc is treated as a broken build.

## Mandatory Test Contract

While patching Python:

```bash
.venv/bin/python -m py_compile ui_app.py src/*.py tests/test_all.py
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
ui_app.py -> src/dccav.py (facade) -> src/engine.py + src/presets.py + src/pricing.py
          -> docs/dccav.md (+ docs/<module>.md) -> tests/test_all.py
```

The current simulator supports DCCAV / double asymmetric reflex:

```text
driver -> upper volume || upper port -> lower volume || lower port
```

plus fourth-order bandpass (sealed rear chamber + vented front chamber),
conventional bass reflex, acoustic suspension / sealed box and ideal infinite
baffle.

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
| `src/dccav.py` | Compatibility facade re-exporting the public API of the three modules below |
| `src/engine.py` | Physics, simulation, optimizer, atlas, Monte Carlo, exports, classification |
| `src/presets.py` | Built-in + Loudspeaker Database driver catalog and metadata |
| `src/pricing.py` | Retailer price records, safe matching and value scoring |
| `src/ranking.py` | Find-a-driver candidate rows (worker-process safe) |
| `docs/dccav.md` | Public API, formulas, assumptions and tests (facade-level reference) |
| `docs/engine.md`, `docs/presets.md`, `docs/pricing.md` | Per-module contracts |
| `tests/test_all.py` | Focused custom runner with the acoustic-load suite |

## Streamlit Reload Rule

Any `src/` module used in `ui_app.py` must be imported as a module and
reloaded, dependencies first and the `dccav` facade last:

```python
import dccav as _dccav
import engine as _engine
import presets as _presets
import pricing as _pricing
import ranking as _ranking

for _module in (_engine, _pricing, _presets, _ranking, _dccav):
    importlib.reload(_module)
```

Add new imports/reloads when adding new active helper modules.

## Change Scope

Keep edits narrow and inside the active acoustic-load simulation surface unless
the user explicitly changes the product direction.  Do not push unless
explicitly requested.
