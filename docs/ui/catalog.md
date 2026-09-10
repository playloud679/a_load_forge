# src/ui/catalog.py — driver/preset library, catalog maintenance and prices

Everything that reads or edits the driver catalog and the preset library.

## Groups

- Catalog administration: `_render_catalog_maintenance`,
  `_render_catalog_crawl_report`, `_maintenance_allowed`,
  `_catalog_path_for_preset`, `_driver_catalog_mapping`,
  `_update_catalog_driver_from_box_design` (writes the admin
  `admin_save_box_design_driver` action).
- Preset identity: `_driver_preset_family`, `_driver_preset_source`,
  `_driver_preset_exact_source`, `_driver_preset_identity_fields`,
  `_driver_preset_display_label`, `_available_driver_preset_names`,
  `_catalog_record_display_identity`, `_driver_class_label`,
  `_driver_preset_class`, `_size_bucket`, `_driver_preset_size`.
- Prices: `_driver_preset_price`, `_driver_preset_currency`,
  `_current_exchange_rates` (ECB, cached 6 h), `_normalized_preset_price`,
  `_preset_price_currencies`, `_preset_price_values`,
  `_normalize_price_frame`, `_value_sorted_frame`, `_purchase_markdown`.
- Library UI and filters: `_render_finder_library_filters`,
  `_filter_driver_preset_names`, `_sync_finder_library_selection`,
  `_render_driver_library`, `_render_driver_mechanical_drawing`,
  `_passive_radiator_library_frame`, `_render_passive_radiator_library`,
  `_finder_filter_summary`, `_finder_brief_constraints`,
  `_render_finder_constraint_grid`.
- Candidate prefiltering: `_finder_candidate_precheck`,
  `_finder_prefilter`, `_prefilter_finder_candidate_pools`,
  `_deduplicate_finder_preset_names`, `_filter_finder_performance_rows`,
  `_driver_coverage_summary`, `_refresh_finder_result_catalog_metadata`,
  `_finder_load_context`, `_finder_result_context_signature`,
  `_finder_controls_signature`.
- `_poll_catalog_refresh` (`@st.fragment(run_every=2)`) keeps the library
  fresh without blocking the UI.

## Invariants

- The UI never mutates the source catalog implicitly: only the explicit admin
  action writes, and only through `presets`/`tools` merge helpers.
- Tests patch price internals on **this** module
  (`ui.catalog._current_exchange_rates`), because module-qualified call sites
  resolve here.

## Tests

`_check_admin_can_save_box_design_ts_to_catalog`,
`_check_ui_driver_preset_price_filter_uses_optional_metadata`,
`_check_ecb_rates_normalize_library_prices`,
`_check_ui_finder_filters_*`, `_check_driver_coverage_*`.
