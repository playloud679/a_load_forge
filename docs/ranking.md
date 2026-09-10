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
  bandpass chamber total—including eighth-order `V1+V2+V3`—or DCCAV
  `Vh+Vl`). Goal mode uses
  `max_total_volume_l`, never `fixed_total_volume_l`, with the selected
  Standard/Deep evaluation budget scaled to the load topology and forwards
  every Finder constraint, including
  minimum peak SPL, allowed ripple and frequency ceiling (`ripple_max_freq_hz`),
  using `segmented_frequency_grid` to sample densely below the ceiling and sparsely (9 points) above.
  Without goals, the physical starter is retained when it
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
  the live catalog or the previous design session has since changed. Every row
  also carries `Data` (coverage status), `Data %` (coverage score) and hidden
  `_data_missing` from `driver_data_coverage()`, so the UI can badge records
  with missing optional parameters. Eighth-order
  rows expose `V1 L`, `f1 Hz`, `V2 L`, `f2 Hz`, `V3 L` and `f3 Hz`; other
  loads leave those topology-specific columns empty
- `finder_optimizer_axis_count(load_type)`: returns the number of free
  optimizer axes for a lumped load (Sealed 1, Bass reflex 2, Bandpass 4th 3,
  Bandpass 6th/DCCAV 4, Bandpass 8th 6) or `None` for loads without a box
  search (infinite baffle, passive-radiator starter). Legacy
  `Suspension pneumatic`/`Acoustic suspension` map to `Sealed`.
- `finder_optimizer_evaluation_limit(module_path=None, profile="Standard",
  load_type=None)`: returns the per-driver evaluation budget. With a known
  `load_type` the budget scales with the free axes as
  `overhead + evaluations_per_axis × axes`, clamped to the profile floor and
  cap (Standard: 20/axis + 10, floor 24, cap 120 → Sealed 30, Reflex 50,
  BP4 70, BP6/DCCAV 90, BP8 120; Deep: 40/axis + 20, floor 48, cap 240).
  Without a load type the historical flat budget is returned
  (Standard 60, Deep 120). `module_path` is accepted for API compatibility
  and ignored; there is no Cloud Run reduction.
- `finder_optimizer_frequency_plan(module_path=None, profile="Standard")`:
  returns box-search frequency grid and finalist-F3 refinement counts (Standard:
  30/20, Deep: 30/20). The engine adds deterministic tuning/extrema/curvature
  samples only for competitive finalists.
- `search_profile_credit_multiplier(profile="Standard")`:
  returns the credit cost multiplier (Standard: 1x, Deep: 2x per candidate).
- `SEARCH_PROFILES` / `SEARCH_PROFILE_STANDARD`, `SEARCH_PROFILE_DEEP`:
  named search profiles tailoring search fidelity and cost.
- `response_sparkline(spl, points=48, floor_db=-30)` plus the
  `SPARKLINE_POINTS` / `SPARKLINE_FLOOR_DB` constants used by the UI's
  `LineChartColumn`
- `candidate_precheck(ts, load_type, voltage_v, min_spl_db, max_ripple_db, ...)`:
  evaluates feasibility against Xmax, reference SPL drive headroom, loaded Fs
  and acoustic volume displacement MOL @ F3 before numerical optimization.
- `driver_data_coverage(ts, size_in=None, price=None)`: percentage and status
  (`Complete` / `Partial` / `Incomplete`) of the optional
  engineering/commercial fields Xmax, Pe, Le, Mms, Bl, Cms, Le10k, nominal
  size and price. Missing fields are never invented: callers keep their
  existing fallbacks and use the badge to warn the user.
- `DRIVER_COVERAGE_LABELS`: tuple of the tracked optional field labels, used
  by the UI coverage summary.
- `prefilter_finder_candidate_pools(preset_names, load_types, ...)` (`lru_cache(maxsize=128)`):
  builds per-topology candidate pools using pure analytical pre-simulation checks
  with persistent module-level caching across UI reruns.
- `invalidate_ranking_caches()`: clears candidate pool caches and the bounded
  optimizer-result memoization.
- internal `_optimizer_brief_key` / `_cached_optimized_alignment`: thread-safe
  `OrderedDict` (max 512 entries) memoizing `engine.optimize_alignment` results
  keyed by engine revision, load type, search profile, frequency plan and the
  full driver T/S + `OptimizationGoals` fingerprint. Repeated Finder runs with
  the same brief (for example after only a post-simulation filter changes)
  skip the expensive search; each call still rebuilds a fresh row dict so
  caller mutations never poison the cache.
- `FINDER_SPL_PREFILTER_HEADROOM_DB`: default reference SPL drive headroom (6.0 dB).

## Invariants

- Depends on `engine` and `presets`; no Streamlit imports or session state.
- Finder uses a shared-memory `ThreadPoolExecutor` by default, so Bass Match
  and Box Design always execute the same live optimizer module. This avoids
  process workers re-importing `ui_app.py` outside Streamlit or retaining an
  older engine revision after a hot reload.
- The guarded process-pool compatibility path exposes
  `finder_worker_ready()`, which returns the PID together with
  `FINDER_WORKER_PROTOCOL_REVISION` and `engine.OPTIMIZER_ENGINE_REVISION`.
  The parent rejects a process pool whose loaded revisions differ and falls
  back to current-process threads, preventing stale F3/ripple rows after a hot
  engine update even when Python's forkserver itself remains alive.
- `ui_app._batch_rank_presets` (cached reference path),
  `_batch_rank_presets_with_progress` (serial UI path up to 8 candidates) and
  `_batch_rank_presets_parallel` (threaded UI path above 8 candidates)
  must produce identical rows for identical inputs. Both UI paths feed one
  live progress bar across every selected load; the optimizer is deterministic.
- The UI applies `OptimizationGoals.min_spl_db` as a hard result-list filter
  after simulation; the optimizer also receives it as a soft scoring penalty
  so it can prefer a compliant alignment before the row is accepted or rejected.
- `OptimizationGoals.max_ripple_db` is enforced by the optimizer as a
  feasibility constraint. Finder measures ripple again on the final
  display-resolution response and uses that value in the row; candidates that
  exceed the limit there are omitted rather than ranked with a coarse-grid
  value that disagrees with Box Design.
- The UI's minimum `MOL @ F3` constraint is a hard post-simulation filter.
  Missing/non-finite MOL values cannot satisfy a non-zero minimum.
- The compact Finder result table omits the internal `Class` and `Sd cm²`
  metadata columns. Its currency heading is `CUR`, and the maximum-output
  heading is the concise `MOL`; manufacturer, part number and minimum impedance
  are displayed as `Mfr`, `Part #` and `Min Z`; the underlying ranking-row keys
  remain stable. The visible order is identity/load, size and total volume,
  price/currency, then F3/MOL/peak/response and electrical limits; optional
  `Value`, `Buy` and `Le10k` fields occupy their corresponding nearby slots.
  The Finder dataframe uses content width and leaves column widths automatic,
  so its initial layout is compact without requiring a header double-click.
- Finder volume is always an upper bound. Rows may therefore report different
  enclosure volumes, but no finite-box result may exceed the selected maximum.
