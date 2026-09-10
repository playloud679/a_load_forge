# src/ui/analysis.py — charts, pins, comparison and export

All plotting and analysis-tab rendering.

## Groups

- Chart data: `_series_frame`, `_response_series`, `_port_series`,
  `_response_y_domain`, `_cursor_rows`, `_cursor_label_rows`,
  `_chart_signature`, `_snapshot_revision`.
- Vega-Lite layers: `_line_chart`, `_tuning_marker_layer`,
  `_cursor_layer`, `_click_marker_layer`, `_band_layer`,
  `_pinned_metric_layer`, `_pinned_layer`, `_expand_y_domain_for_pins`.
- Plots: `_plot_response`, `_plot_excursion`, `_plot_impedance`, `_plot_mil`,
  `_plot_ports`, `_plot_group_delay`.
- Pins: `_pinned_responses`, `_pinned_response_snapshot`,
  `_pinned_metric_frame`, `_pinned_response_frame`, `_remove_pinned_response`,
  `_set_pinned_response_visible`, `_clear_pinned_responses`.
- Design comparison tabs: `_design_comparison_tabs`,
  `_update_active_design_comparison`, `_duplicate_*`,
  `_delete_*`, `_toggle_design_tab_visible`, `_end_design_comparison`,
  `_design_comparison_tab_colors`, `_design_comparison_tab_label`,
  `_design_tab_label_driver`, `_recover_design_tab_preset`,
  `_render_editable_design_tabs`.
- Simulation caches: `_simulate_design_cached`, `_tolerance_band_cached`,
  `_design_space_cached`, `_simulation_engine_revision`,
  `_design_simulation_signature`, `_topology_comparison_series`.
- Tabs/export: `_render_response_tab` (`@st.fragment`),
  `_render_ports_tab`, `_render_design_analysis_tabs` (`@st.fragment`),
  `_csv_bytes`, `_prepare_design_crw_download`, `_design_crw_*`.

## Invariants

- Chart layers must filter data to the zoom window; unclipped marks past the
  x-domain make Vega shrink the plot area.
- `@st.fragment` tabs rerun alone so switching Response/Ports/Atlas keeps the
  page scroll still.
- Design comparison is capped by `_MAX_COMPARISON_DESIGNS`; pinned responses
  by `_MAX_PINNED_RESPONSES`/`_MAX_PINNED_CHART_ROWS`.

## Tests

`_check_ui_pin_response_overlay`, `_check_ui_editable_design_comparison_tabs`,
`_check_ui_response_*`, `_check_ui_design_crw_*`.
