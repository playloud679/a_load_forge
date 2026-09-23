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
- Library UI and filters: `_render_finder_library_filters` (complete in both Simple
  and Advanced modes: Provenance, Manufacturer, Size, Class, Price),
  `_filter_driver_preset_names` (supports `pinned` drivers preserved at the top of the pool),
  `_table_selection_rows`, `_sync_pinned_from_library_table`,
  `_sync_finder_library_selection`, `_clear_library_selection`,
  `_render_driver_library` (supports single and multi-driver Box Design simulation actions),
  `_render_driver_mechanical_drawing`, `_passive_radiator_library_frame`,
  `_render_passive_radiator_library`, `_finder_filter_summary`,
  `_finder_brief_constraints`, `_render_finder_constraint_grid`.
- Candidate prefiltering: `_finder_candidate_precheck`,
  `_finder_prefilter`, `_prefilter_finder_candidate_pools`,
  `_deduplicate_finder_preset_names`, `_filter_finder_performance_rows`,
  `_driver_coverage_summary`, `_refresh_finder_result_catalog_metadata`,
  `_finder_load_context`, `_finder_result_context_signature`,
  `_finder_controls_signature`.
- `_poll_catalog_refresh` (`@st.fragment(run_every=2)`) keeps the library
  fresh without blocking the UI.

## Invariants

- Library filters use two columns (Provenance/Size and Manufacturer/Class),
  keeping all filters available in both modes. Driver and passive-radiator
  tables stretch inside keyed 320px containers; desktop CSS sizes their
  viewport to the window height with internal table scrolling. The driver
  count, currency and selection hint share one caption above the table.
  Currency and price-filter enablement share a row. The catalog radio group
  hides its redundant label; selection guidance below the table is one caption.
- The Search preset row bottom-aligns its 🔄 refresh icon button with the input
  (`st.columns([5, 1], vertical_alignment="bottom")`); the button takes its
  square size from the shared data-entry control CSS, not a fixed spacer.

- Programmatic table row selection in `st.session_state["finder_driver_library_table"]`
  always assigns a new dictionary (`{"selection": {"rows": ...}}`) instead of
  mutating nested attributes or calling `.setdefault("selection", ...)`, remaining
  fully compatible with Streamlit's read-only widget state proxies (`ReadOnlyAttributeDictionary`).

- The UI never mutates the source catalog implicitly: only the explicit admin
  action writes, and only through `presets`/`tools` merge helpers.
- `_driver_coverage_summary` and `_refresh_finder_result_catalog_metadata` pass
  `DriverPresetInfo.size_sd_conflict` into `driver_data_coverage`, so a
  published frame size that cannot host the stored `Sd` appears as a `Size/Sd`
  data gap (⚠) in the library and ranked tables instead of being silently
  replaced by an Sd-derived size class. Saved Finder rows refresh the flag from
  the live catalog and persist it as `_size_sd_conflict`.
- Tests patch price internals on **this** module
  (`ui.catalog._current_exchange_rates`), because module-qualified call sites
  resolve here.

## Tests

`_check_admin_can_save_box_design_ts_to_catalog`,
`_check_ui_driver_preset_price_filter_uses_optional_metadata`,
`_check_ecb_rates_normalize_library_prices`,
`_check_ui_finder_filters_*`, `_check_driver_coverage_*`.

## Filter alignment

The Finder search and refresh action live in `search_row_finder`: a fluid input
track plus one control-width action track. Library filters are rendered in
explicit paired rows (`field_row_library_*`), so a tall multiselect expands its
own row and the next pair remains aligned. Filter values and callbacks are unchanged.
