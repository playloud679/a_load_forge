# Load Forge — Module Index

Each active source module has a matching document in this directory.  Future
agents should read the doc before source when possible, then keep docs and code
in sync in the same change.

> Required contract: modifying any `src/*.py` requires updating
> `docs/<module>.md` in the same change.  Create the doc if it is missing.

## Active App Path

| Module/File | Doc | Role |
|---|---|---|
| `ui_app.py` | source only | Streamlit acoustic-load dashboard with compact illustrated load cards, T/S inputs, alignment controls, plots, preset save/load and CSV export |
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
