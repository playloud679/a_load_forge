# src/ui/state.py — session state, widget defaults and state models

Bridges `st.session_state` and the acoustic model objects.

## Groups

- Widget plumbing: `_persist_widget_selection`, `_mark_session_flag`,
  `_clean_style_str`, `_is_param_key`, `_finder_value`,
  `_finder_number_input`, `_finder_selectbox`, `_box_number_with_nudge`.
- Defaults/migrations: `_default`, `_optional_positive`,
  `_ensure_plot_control_state`, `_ensure_finder_defaults`,
  `_reset_finder_defaults`, `_ensure_price_currency_default`,
  `_reset_response_zoom`, `_reset_candidate_filters`.
- State snapshots: `_snapshot_manual_box`/`_restore_manual_box`,
  `_snapshot_design_state`/`_restore_design_state`,
  `_preserve_design_state`, `_preserve_library_filters`.
- Box strategy: `_normalize_box_strategy`, `_set_box_strategy_state`,
  `_box_strategy_is_auto`, `_manual_box_keys_for_load_type`.
- Load-type/workspace selectors: `_render_load_type_buttons`,
  `_render_workspace_tabs`, `_select_workspace`, `_available_workspaces`,
  `_render_engine_only_topologies_note`, `_reflex_uses_passive_radiator`.
- Model builders: `_driver_from_state`, `_single_driver_from_state`,
  `_box_from_state`, `_reflex_box_from_state`, `_pr_box_from_state`,
  `_sealed_box_from_state`, `_bandpass4/6/8_box_from_state`,
  `_driver_from_params`, `_box_from_params`, `_collect_params`.
- Table helpers: `_clean_display_table_frame`, `_table_value_missing`,
  `_json_safe`.

## Invariants

- Persistent parameter keys keep their domain prefixes (`driver_`, `box_`,
  `reflex_`, ...); action buttons use distinct prefixes so widget-state
  assignment never collides (GOLDEN_STD §3).
- Default migrations are gated by the version constants in `constants.py`;
  never reorder `_default` calls without bumping the matching version.
- `_json_safe` must return only JSON-serializable types (projects/LFP depend
  on it).

## Tests

`tests/test_all.py` covers param round-trips, box-strategy restoration,
`_normalize_stl_split_mode` and the editable-tab preset recovery.
