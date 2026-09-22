# src/ui/finder.py — Bass Match search, ranking and results

The Bass Match workspace: alignment application, ranking workers, batch
results, the candidate pool and the run statistics.

## Groups

- Alignment: `_initialize_alignment_defaults`, `_sync_auto_alignment_if_needed`,
  `_auto_align_current_driver`, `_apply_alignment`, `_apply_reflex_alignment`,
  `_apply_sealed_alignment`, `_apply_bandpass4/6/8_alignment`,
  `_optimizer_goals_signature`, `_auto_alignment_signature`.
- Ranking workers: `_batch_rank_presets`,
  `_batch_rank_presets_parallel`, `_batch_rank_presets_with_progress`,
  `_finder_worker_pool`, `_drop_finder_worker_pool`,
  `_finder_executor_backend`, `_finder_worker_limit`,
  `_finder_pool_fingerprint`, `_is_streamlit_community_cloud`.
- Result handling: `_apply_batch_result`, `_finder_result_snapshot`,
  `_apply_pending_batch_result`, `_add_finder_designs_to_comparison`,
  `_apply_pending_batch_comparison`, `_finder_row_driver`,
  `_finder_total_volume_l`.
- Workspace UI: `_render_find_driver_workspace`, `_finder_results_current`,
  `_render_finder_results`, `_render_bass_match_hero`,
  `_render_finder_run_statistics`, `_finder_per_load_stats_str`,
  `_render_candidate_pool` (`@st.fragment`), `_render_find_driver_actions` (search brief summary),
  `_render_find_driver_goal_sidebar`, `_render_find_driver_target_sidebar`,
  `_render_finder_scenario_selector`, `_apply_finder_scenario`,
  `_show_advanced_controls`, `_run_find_driver_search`.
- Atlas: `_design_space_cached`, `_atlas_frame`, `_render_atlas_tab`,
  `_queue_atlas_point`, `_apply_pending_atlas_point`.

## Invariants

- Worker pools are process-first with a thread fallback on Streamlit Cloud or
  denied process semaphores. Tests patch `ui.finder.ProcessPoolExecutor` and
  `ui.finder._finder_executor_backend`.
- Search progress renders below the Run CTA. Completion queues Results and
  reruns once to remove setup controls; it never reruns the search itself.
- The batch results table and its CSV download expose the nominal `Le mH`
  (when present) and never the internal `Le10k mH` ranking key; only the
  visible columns are rendered/exported.
- The initial render must not be disabled by an unloaded catalog
  (`_check_ui_finder_main_action_runs_search`).

## Tests

Finder tests (`_check_ui_finder_*`, `_check_ui_parallel_ranking_*`,
`_check_ui_stale_finder_workers_*`) plus the AppTest workspace flows.

## Separate Run and Results pages (v0.18.7)

- Main-area stateful workflow (`temp_bass_match_page`) functions as sequential workflow
  states rather than peer navigation tabs (the tablist header is hidden via CSS).
  Run displays a compact technical brief hierarchy (Phase D): primary specs (`Loads · Configuration · Volume`),
  secondary specs (`Objective · Profile`), and a monospace telemetry row (`<N> candidates ready · <M> simulations`),
  while individual metric boxes and the constraint grid are organized neatly inside the `Search details ▸` expander.
  Results (Phase E) makes the ranked candidates table visually dominant, presenting a compact two-tier header
  (`<count> matches · <loads> · <volume> · <objective> · <profile>` over `<N> evaluated · <T> s` telemetry)
  with an `Edit search` button (invoking `_on_finder_edit_search` to cleanly transition back to the brief), rank mode selector,
  and the primary `Open this design in Box Design` / `Compare N designs in Box Design` toolbar positioned directly above the 680 px table.
- Search details expander hosts prefilter diagnostic metrics (`Pre-qualified`, `Ready simulations`, `Skipped a priori`, `Duplicates removed`),
  credits breakdown, the `Show disabled constraints` toggle and the full technical constraint grid.
- `_finder_results_current` owns the existing context validation and legacy
  migration. Invalidating search inputs forces Run before tab creation.
  Ordering and row selection preserve Results; background catalog updates do
  not invalidate the existing input signature.
- A completed run queues Results and reruns once after storing results. Empty
  successful searches also open Results with the existing no-match explanation.
  Restored valid contexts open Results automatically. Users can revisit Run
  without spending credits or starting a search; returning retains selection.
- The toolbar points to the far-left checkboxes. One selection enables Open;
  two through eight enable Compare; excess selections disable the action.
  Selected names stay compact (two names plus a remainder count).
- Fresh runs clear both table selections. Existing queued Box Design handoff
  preserves independent editable design tabs.
- The ranked table badges data quality through `driver_data_coverage()`: ✓
  complete, ⚠ partial, ⛔ incomplete. A driver whose **published** nominal frame
  size cannot host its `Sd` (70–115 % window) shows ⚠ with `Size/Sd` in the
  missing-fields list; the published size stays in the `Size (in)` column and
  the box/port numbers still use the stored `Sd`, so the conflict is visible
  rather than silently relabelled.

The Finder workspace AppTest covers automatic transitions, hidden setup UI,
manual tab round trips, selection persistence, input invalidation and opening
Box Design, including volume/voltage/objective edits, presentation-only changes
and completed searches with no matches; the restored-project AppTest covers
saved results.
