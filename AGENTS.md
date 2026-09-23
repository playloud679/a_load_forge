# Agent Instructions for AI Coding Assistants

## Development mode: pre-production

Optimize for short, reviewable iterations. These project-specific rules override
production/release ceremony in `GOLDEN_STD.md` and older documentation.

- Read the relevant module doc, then search only the needed source sections.
  Do not load entire large modules, the changelog, or raw test logs by default.
- Update matching `docs/<module>.md` when a documented API, behavior, assumption
  or workflow changes. Pure CSS spacing, copy edits and internal refactors do
  not require ceremonial doc edits. Create a module doc for new source modules.
- Use the smallest relevant check once after a coherent edit. Do not run smoke,
  fast, UI and full suites in sequence for a small change.
- CSS/layout: inspect the affected view; use a targeted AppTest only if widget
  behavior changed. AppTest startup does not validate CSS appearance.
- UI behavior: `make test-match MATCH='relevant test label'`.
- Physics: `make test-smoke` (all load families) plus the affected regression.
- General Python: `make test` (fast local suite) when no narrower check fits.
- Test infrastructure or broad cross-module changes: `make test-all` once.
  The full simulator suite also runs in CI; it is not a local pre-commit gate.
- Keep test output concise. The runner writes complete logs to
  `.local/test-logs/`; read only relevant errors. Use `--verbose` only for debugging.
- Report checks actually run. Fix relevant failures; do not chase unrelated
  failures or expand the task without a concrete dependency.
- Do not bump versions, edit release references, add changelog entries, tag,
  deploy or create a release for routine edits. Do so for an explicit release.
- Do not add compatibility layers, fallback paths, extra approval workflows or
  broad refactors for hypothetical production requirements.
- Preserve acoustic correctness and existing user data. Do not push unless asked.

See [docs/development.md](docs/development.md) for test commands and groups.

## Active App: Load Forge Acoustic Loads

The app is a Streamlit dashboard for acoustic-load simulation.

Active path:

```text
ui_app.py -> src/ui/app.py -> src/ui/*.py -> src/acoustics.py -> src/engine.py
                                                  |                 |
                                                  v                 v
                                          docs/ui/*.md      docs/acoustics.md + docs/engine.md
                                                  |
                                                  v
                                          tests/test_all.py
```

`ui_app.py` is a thin entry point (bootstrap, hot-reload, re-exports,
`ui.app.main()`); the dashboard implementation lives in `src/ui/`
(see `docs/ui.md` for the module map).

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
| New input parameter | Add or update the matching sidebar control in `src/ui/app.py` or the owning `src/ui/*` module |
| Changed acoustic-load dataclass field | Update UI state keys, preset collection and tests |
| Changed alignment formula | Update displayed suggested metrics, `docs/engine.md`, the topology-specific docs, and regression tests |
| Changed simulation output | Update plots, CSV export, metrics and tests |
| Changed validation behavior | Update user-facing errors and regression tests |

## Streamlit module caching

Streamlit runs `ui_app.py` in a long-lived Python process. The `src/` physics
modules are imported as modules and hot-reloaded near the top of `ui_app.py`:

```python
sys.path.insert(0, str(Path(__file__).parent / "src"))
import acoustics as _acoustics

import importlib
importlib.reload(_acoustics)
```

The `src/ui/*` package follows the same contract, but with two extra rules:

1. **Module-qualified cross-references.** Inside `src/ui`, call
   `_finder._run_find_driver_search(...)`, never
   `from .finder import _run_find_driver_search`. `ui_app.py` re-executes on
   every rerun but imported modules stay cached, so only attribute access
   keeps call sites pointing at the live module object after
   `importlib.reload`.
2. **Reload the whole package.** `ui_app.py` loops over every `src/ui/*`
   module with `_reload_if_source_changed` before re-exporting names and
   calling `ui.app.main()`. Import cycles between `src/ui` modules are
   expected and safe because modules only bind module objects at import time.

If the UI starts using another `src/` module, add both its import and reload
call. Runtime globals (`_VERSION`, `_SAAS_SETTINGS`, `_CURRENT_SAAS_USER`,
`_ACCOUNT_STORE`, `logger`) live in `src/ui/runtime.py` and must be read as
`_runtime.X`; `ui_app.py` reassigns the mutable ones on every rerun.

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
