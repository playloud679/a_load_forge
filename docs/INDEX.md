# Load Forge — Module Index

Each active source module has a matching document in this directory.  Future
agents should read the doc before source when possible, then keep docs and code
in sync in the same change.

> Required contract: modifying any `src/*.py` requires updating
> `docs/<module>.md` in the same change.  Create the doc if it is missing.

## Active App Path

| Module/File | Doc | Role |
|---|---|---|
| `ui_app.py` | source only | Streamlit dashboard with compact 3+3 illustrated load cards, a Bass-reflex Ports submenu for vent/passive-radiator resonators, target/performance/library Finder flow, contextual design tabs, T/S controls, plots, project state and CSV export |
| `src/__init__.py` | [__init__.md](__init__.md) | Public package exports for acoustic-load helpers |
| `src/dccav.py` | [dccav.md](dccav.md) | DCCAV/reflex/sealed/infinite-baffle formulas, T/S derivation and lumped acoustic-circuit simulation |
| `tests/test_all.py` | source only | Active regression runner for the acoustic-load models and Streamlit workflows |

## Data Flow

```text
T/S parameters -> derived driver components -> selected acoustic-load alignment
        -> acoustic impedance network -> response arrays -> plots / CSV
```

## Acoustic-load UI Contract

When changing `src/dccav.py`:

- update `ui_app.py` controls, metrics and plots for any new/changed parameter
- update `tests/test_all.py`
- update [dccav.md](dccav.md)
- run a Streamlit `AppTest` for the touched UI path

The UI keeps selection/action semantics red and plot/data semantics blue. Load
cards are fully clickable with overlaid labels, a checked active state and
keyboard focus; the full-width 1200×100 app header preserves its native ratio and the active design uses a
44 px topology chip so controls and metrics remain above the fold. The Finder
follows target enclosure → performance goal → candidate library, keeps its
primary action pinned to the sidebar bottom, and hides empty result columns.
