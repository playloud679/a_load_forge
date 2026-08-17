# src/ranking.py — Bass Match candidate rows

Pure ranking functions for the `Bass Match` workspace, importable by
worker processes (the module is picklable-by-name in both the package and
top-level import contexts).  `src/dccav.py` re-exports the public API;
detailed contracts live in `docs/dccav.md`.

## Owns

- `rank_preset_row(name, load_type, max_volume_l, voltage_v, f_min_hz,
  f_max_hz, points, goals=None, driver_configuration="Single driver") -> dict | None`:
  applies the selected single/pair/isobaric configuration to the preset, then
  simulates one candidate at the
  best optimized volume at or below the requested cap (reflex/sealed `Vb`,
  bandpass chamber total, DCCAV `Vh+Vl`). Goal mode uses
  `max_total_volume_l`, never `fixed_total_volume_l`, with
  `max_evaluations=140` and forwards every Finder constraint, including
  minimum peak SPL. Without goals, the physical starter is retained when it
  already fits and is reduced only when it exceeds the cap;
  the function returns the ranking-table row, including `MOL @ F3 dB`
  interpolated at the candidate's actual -3 dB frequency from the simulated
  excursion/thermal maximum-output curve, nominal `Size in` metadata and the
  active single/composite driver's effective piston area `Sd cm²`;
  unusable presets return `None` instead of raising
- `sort_ranked_rows(rows)`: deepest F3 first, then F6/F10 and loudest peak
- `rank_sort_value(value)`: `inf` for non-finite sort keys
- `RankingCandidate` / `ranking_candidate(name)`: resolve a named preset in the
  catalog-owning parent into the compact T/S and table metadata sent to workers
- `rank_candidate_row(candidate, ...)`: simulate that compact payload without
  loading the external preset databases in each worker; `rank_preset_row()`
  remains the name-based public wrapper. Each returned row includes hidden
  `_driver_ts` and `_box_params` snapshots so opening it in Box Design uses
  the exact driver and enclosure-loss parameters that produced its F3 even if
  the live catalog or the previous design session has since changed
- `finder_worker_ready()`: return only the worker PID for the bounded startup
  health check; it deliberately does not touch the runtime catalog
- `finder_optimizer_evaluation_limit(module_path=None)`: use 30 global search
  evaluations per driver (24 on Cloud Run); the winning alignment receives the
  engine's separate 20-point F3 refinement pass
- `finder_optimizer_frequency_plan(module_path=None)`: select the 30-point broad
  scan plus 20-point winning-F3 refinement
- `response_sparkline(spl, points=48, floor_db=-30)` plus the
  `SPARKLINE_POINTS` / `SPARKLINE_FLOOR_DB` constants used by the UI's
  `LineChartColumn`

## Invariants

- Depends on `engine` and `presets`; no Streamlit imports, no session state:
  everything a `ProcessPoolExecutor` worker needs comes in as arguments.
- `ui_app._batch_rank_presets` (cached reference path),
  `_batch_rank_presets_with_progress` (serial UI path up to 8 candidates) and
  `_batch_rank_presets_parallel` (worker-process UI path above 8 candidates)
  must produce identical rows for identical inputs. Both UI paths feed one
  live progress bar across every selected load; the optimizer is deterministic.
- The UI applies `OptimizationGoals.min_spl_db` as a hard result-list filter
  after simulation; the optimizer also receives it as a soft scoring penalty
  so it can prefer a compliant alignment before the row is accepted or rejected.
- The UI's minimum `MOL @ F3` constraint is a hard post-simulation filter.
  Missing/non-finite MOL values cannot satisfy a non-zero minimum.
- Finder volume is always an upper bound. Rows may therefore report different
  enclosure volumes, but no finite-box result may exceed the selected maximum.
