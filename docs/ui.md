# src/ui — Load Forge Streamlit UI package

`ui_app.py` is a thin entry point (bootstrap + re-exports). The dashboard
implementation lives in `src/ui/`. This split replaced a single ~15.6k-line
script with focused modules; behavior is unchanged.

## Module map

| Module | Doc | Role |
|---|---|---|
| `src/ui/__init__.py` | this file | Package marker; puts `src/` on `sys.path` |
| `src/ui/runtime.py` | [ui/runtime.md](ui/runtime.md) | `_VERSION`, SaaS settings, current user/account store, `logger` |
| `src/ui/constants.py` | [ui/constants.md](ui/constants.md) | Assets, defaults, labels, catalog paths, version defaults |
| `src/ui/styles.py` | [ui/styles.md](ui/styles.md) | Global CSS and load-type/workspace card styles |
| `src/ui/state.py` | [ui/state.md](ui/state.md) | Session-state defaults, widget keys and box/driver models from state |
| `src/ui/catalog.py` | [ui/catalog.md](ui/catalog.md) | Driver/preset library, catalog maintenance, prices |
| `src/ui/finder.py` | [ui/finder.md](ui/finder.md) | Bass Match search, ranking workers, results, candidate pool |
| `src/ui/optimizer.py` | [ui/optimizer.md](ui/optimizer.md) | Alignment/box optimizer helpers and alternatives |
| `src/ui/analysis.py` | [ui/analysis.md](ui/analysis.md) | Charts, pins, design comparison, CSV export, analysis tabs |
| `src/ui/projects.py` | [ui/projects.md](ui/projects.md) | LFP persistence, cloud autosave, community/public pages, billing UI |
| `src/ui/account.py` | [ui/account.md](ui/account.md) | Auth gate, account/project/public stores, admin helpers |
| `src/ui/app.py` | [ui/app.md](ui/app.md) | `main()`: defaults, query params, sidebar, workspace dispatch |

## Import and hot-reload contract

- Cross-module references are **module-qualified** (`_finder._run_find_driver_search`),
  never `from .finder import _run_find_driver_search`. Streamlit reloads
  `ui_app.py` on every rerun but keeps imported modules cached; qualified
  access keeps call sites pointing at the live module object after
  `importlib.reload`.
- `ui_app.py` reloads every `src/ui/*` module through `_reload_if_source_changed`
  before re-exporting names and calling `ui.app.main()`.
- `src/ui/__init__.py` inserts `src/` into `sys.path`, so modules can
  `import acoustics as _acoustics` even when imported outside `ui_app.py`.
- Import cycles between modules are expected and safe because modules only
  bind module objects at import time; attributes are resolved at call time.

## Runtime globals

`_VERSION`, `_SAAS_SOURCE_TOKEN`, `_SAAS_SETTINGS`, `_CURRENT_SAAS_USER`,
`_ACCOUNT_STORE` and `logger` live in `runtime.py`. Modules read them as
`_runtime.X`; `ui_app.py` assigns `_CURRENT_SAAS_USER` and `_ACCOUNT_STORE`
on every rerun after `initialize_saas_settings()`.

## Test contract

- `tests/test_all.py` imports `ui_app` and uses the re-exported names
  (`_ui._plot_response`, `_ui._batch_rank_presets`, ...). Keep the re-export
  block in `ui_app.py` when adding a module.
- Tests that patch internals must patch the owning module
  (`ui.finder.ProcessPoolExecutor`, `ui.catalog._current_exchange_rates`),
  not the `ui_app` re-export.
- Source-text assertions use `_ui_source_bundle()` (thin `ui_app.py` plus all
  `src/ui/*.py`).
