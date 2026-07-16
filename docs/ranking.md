# src/ranking.py — Find-a-driver candidate rows

Pure ranking functions for the `Find a driver` workspace, importable by
worker processes (the module is picklable-by-name in both the package and
top-level import contexts).  `src/dccav.py` re-exports the public API;
detailed contracts live in `docs/dccav.md`.

## Owns

- `rank_preset_row(name, load_type, max_volume_l, voltage_v, f_min_hz,
  f_max_hz, points, goals=None) -> dict | None`: simulates one preset at the
  best optimized volume at or below the requested cap (reflex/sealed `Vb`,
  bandpass chamber total, DCCAV `Vh+Vl`). Goal mode uses
  `max_total_volume_l`, never `fixed_total_volume_l`, with
  `max_evaluations=140` and forwards every Finder constraint, including
  minimum peak SPL. Without goals, the physical starter is retained when it
  already fits and is reduced only when it exceeds the cap;
  the function returns the ranking-table row;
  unusable presets return `None` instead of raising
- `sort_ranked_rows(rows)`: deepest F3 first, then F6/F10 and loudest peak
- `rank_sort_value(value)`: `inf` for non-finite sort keys
- `response_sparkline(spl, points=48, floor_db=-30)` plus the
  `SPARKLINE_POINTS` / `SPARKLINE_FLOOR_DB` constants used by the UI's
  `LineChartColumn`

## Invariants

- Depends on `engine` and `presets`; no Streamlit imports, no session state:
  everything a `ProcessPoolExecutor` worker needs comes in as arguments.
- `ui_app._batch_rank_presets` (cached, serial) and
  `_batch_rank_presets_parallel` (uncached, real progress bar, used for
  optimizer scans of more than 8 candidates) must produce identical rows for
  identical inputs — the optimizer is deterministic.
- The UI applies `OptimizationGoals.min_spl_db` as a hard result-list filter
  after simulation; the optimizer also receives it as a soft scoring penalty
  so it can prefer a compliant alignment before the row is accepted or rejected.
- Finder volume is always an upper bound. Rows may therefore report different
  enclosure volumes, but no finite-box result may exceed the selected maximum.
