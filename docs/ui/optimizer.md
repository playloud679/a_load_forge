# src/ui/optimizer.py — alignment/box optimizer helpers

- Objective labels and goals: `_design_objective_label`,
  `_optimizer_goals_from_state`, `_alignment_uses_optimizer`.
- Applying optimized boxes/ports: `_apply_optimized_box`,
  `_optimized_port_diameter_cm`, `_apply_optimized_port_geometry`,
  `_optimized_summary`, `_optimizer_box_signature`,
  `_optimizer_result_context`, `_optimizer_context_box`.
- Alternatives: `_current_optimizer_summary`,
  `_current_optimizer_alternatives`, `_render_optimizer_alternatives`
  (renders up to `engine._OPTIMIZER_MAX_ALTERNATIVES`; applying one does not
  trigger a full app rerun).
- Strategy: `_run_box_optimizer`, `_apply_suggested_box_for`,
  `_apply_empirical_box_for`, `_on_box_strategy_change`,
  `_use_manual_box_strategy`, `_alignment_warning`.
- Formatting/geometry: `_fmt_hz`, `_fmt_db`, `_port_geometry_row`.

## Invariants

- Optimizer budgets are per-topology (`ranking.finder_optimizer_axis_count`,
  `finder_optimizer_evaluation_limit`); this module must not hardcode them.
- The optimizer result context keys include the engine revision so stale
  results never render after an engine bump.
