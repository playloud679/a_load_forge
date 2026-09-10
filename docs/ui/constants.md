# src/ui/constants.py — shared UI constants

Pure data used across the dashboard: asset paths, load-type image/slug maps,
response defaults, finder defaults and scenario presets, project
serialization keys, preset filter tuples, table formats and catalog report
paths.

`_PROJECT_ROOT` resolves to the repository root
(`src/ui/constants.py` → `parents[2]`); every asset/report path is built from
it, so constants no longer depend on `ui_app.py`'s working directory.

## Invariants

- No Streamlit calls and no function calls at import time. Constants may only
  reference stdlib/third-party modules (`Path`, `_acoustics`) and each other.
- Version-like constants that gate default migrations
  (`_FINDER_DEFAULTS_VERSION`, `_RESPONSE_DEFAULTS_VERSION`,
  `_PRICE_CURRENCY_DEFAULTS_VERSION`, `_LFP_FORMAT_VERSION`,
  `_FINDER_RANKING_VERSION`, `_FINDER_CONTEXT_FILTERED_POOL_VERSION`) are
  asserted by tests; bump them together with the matching migration.
- `_EXPLORE_FILTER_DEFAULTS` lives here even though it was defined late in the
  original script, because explorer helpers read it as a global.

## Tests

`_check_ui_finder_defaults_*`, `_check_ui_pin_response_overlay`,
`_check_ui_response_*` and the version-consistency checks cover the values
that gate behavior.
