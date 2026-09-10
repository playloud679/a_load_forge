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
- Workspace UI: `_render_find_driver_workspace`, `_render_bass_match_hero`,
  `_render_finder_run_statistics`, `_finder_per_load_stats_str`,
  `_render_candidate_pool` (`@st.fragment`), `_render_find_driver_actions`,
  `_render_find_driver_goal_sidebar`, `_render_find_driver_target_sidebar`,
  `_render_finder_scenario_selector`, `_apply_finder_scenario`,
  `_show_advanced_controls`, `_run_find_driver_search`.
- Atlas: `_design_space_cached`, `_atlas_frame`, `_render_atlas_tab`,
  `_queue_atlas_point`, `_apply_pending_atlas_point`.

## Invariants

- Worker pools are process-first with a thread fallback on Streamlit Cloud or
  denied process semaphores. Tests patch `ui.finder.ProcessPoolExecutor` and
  `ui.finder._finder_executor_backend`.
- Search progress renders immediately below the CTA; result reruns are
  avoided (stats refresh in place) so scroll position is preserved.
- The initial render must not be disabled by an unloaded catalog
  (`_check_ui_finder_main_action_runs_search`).

## Tests

Finder tests (`_check_ui_finder_*`, `_check_ui_parallel_ranking_*`,
`_check_ui_stale_finder_workers_*`) plus the AppTest workspace flows.
