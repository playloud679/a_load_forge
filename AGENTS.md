# Agent Instructions for AI Coding Assistants

## Rule 0: docs/ MUST stay in sync with src/

Editing any `src/*.py` REQUIRES updating its matching `docs/<module>.md` in the
same change.  The docs are read instead of source to save tokens, so stale docs
mislead every future agent.  No exceptions; create the doc if missing.

## Rule 1: targeted tests while patching, fresh suite before commit

After every meaningful change to `src/*.py` or `ui_app.py`, run the smallest
relevant check:

```bash
.venv/bin/python -m py_compile ui_app.py src/acoustics.py src/engine.py tests/test_all.py
.venv/bin/python tests/test_all.py -m "acoustic-load smoke"   # or: make test-smoke
.venv/bin/python tests/test_all.py --fast                     # or: make test-fast (95 unit/physics tests in ~10s)
```

For UI changes, also run a Streamlit AppTest:

```bash
.venv/bin/python -c 'from streamlit.testing.v1 import AppTest; at = AppTest.from_file("ui_app.py", default_timeout=30); at.run(); assert not at.exception, at.exception'
# or: make test-ui
```

Before every commit touching Python, run the full active suite fresh after the
last edit:

```bash
.venv/bin/python tests/test_all.py   # or: make test (164 tests)
```

Commit only on 0 failures and record pass counts in `CHANGELOG.md`.

## Active App: Load Forge Acoustic Loads

The app is a Streamlit dashboard for acoustic-load simulation.

Active path:

```text
ui_app.py -> src/acoustics.py -> src/engine.py -> docs/acoustics.md + docs/engine.md
                                             -> tests/test_all.py
```

The supported loads are peers behind one neutral acoustic API: DCCAV / double
asymmetric reflex:

```text
driver -> upper volume || upper port -> lower volume || lower port
```

and conventional bass reflex:

```text
driver -> box volume || vent
```

acoustic suspension / sealed box:

```text
driver -> closed box volume
```

and ideal infinite baffle (rear radiation isolated, no box parameters).

The same surface also supports fourth- and sixth-order bandpass, passive
radiator, transmission line, MLTL, quarter-wave, back-loaded horn and tapped
horn. Targeted smoke tests must exercise every load family; do not use DCCAV as
a proxy for the whole engine.

The app starts from driver T/S parameters, suggests an editable alignment,
solves the lumped acoustic circuit and plots SPL estimate, cone excursion,
impedance, port volume velocity and MIL/MOL limits.

## Acoustic-load source-to-UI contract

Whenever `src/engine.py` or the public `src/acoustics.py` facade changes:

| Python change | Required UI/doc/test update |
|---|---|
| New input parameter | Add or update the matching sidebar control in `ui_app.py` |
| Changed acoustic-load dataclass field | Update UI state keys, preset collection and tests |
| Changed alignment formula | Update displayed suggested metrics, `docs/engine.md`, the topology-specific docs, and regression tests |
| Changed simulation output | Update plots, CSV export, metrics and tests |
| Changed validation behavior | Update user-facing errors and regression tests |

## Streamlit module caching

Streamlit runs `ui_app.py` in a long-lived Python process.  Any helper module
under `src/` used by the UI must be imported as a module and reloaded near the
top of `ui_app.py`:

```python
sys.path.insert(0, str(Path(__file__).parent / "src"))
import acoustics as _acoustics

import importlib
importlib.reload(_acoustics)
```

If the UI starts using another `src/` module, add both its import and reload
call.

## Running the app

```bash
make run
```

`make run` starts Streamlit headless and opens `localhost:8501` in Safari.

## Autonomous Catalog Crawler Daemon (Separated Project)

The continuous background crawler that harvests manufacturer/distributor T/S parameters and real prices is separated in its dedicated standalone workspace: `../load_forge_crawler` (or `/Users/marcoderossi/Documents/Codes/load_forge_crawler`).

To run the daemon independently:

```bash
cd ../load_forge_crawler
make run-daemon
```

See [`load_forge_crawler/docs/autonomous_crawler_daemon.md`](../load_forge_crawler/docs/autonomous_crawler_daemon.md) for daemon architecture, log monitoring, and staging configuration.

## Scope

This repository is scoped to acoustic-load simulation. Treat DCCAV, reflex,
passive radiator, sealed, infinite baffle, bandpass and distributed waveguides
as peer load families. Keep new work inside that simulation surface unless the
user explicitly changes the product direction. Do not push unless explicitly
requested.

