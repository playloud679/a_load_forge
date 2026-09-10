# src/ui/projects.py — persistence, cloud autosave, community and billing UI

- LFP v2: `_build_lfp_project`, `_apply_lfp_project`,
  `_collect_bass_match_project_state`, `_serialize_bass_match_context`,
  `_compact_result_row`, `_process_project_cover_image`,
  `_bass_match_results_signature`, `_record_lfp_export`,
  `_project_download_filename`, `_project_name_is_placeholder`,
  `_project_display_name`, `_clear_active_project_state`,
  `_apply_loaded_params`.
- Sharing: `_encode_share_payload`, `_decode_share_payload`,
  `_share_link_url`, `_public_project_url`.
- Cloud autosave: `_mark_cloud_project_dirty`, `_set_active_cloud_record`,
  `_apply_cloud_record`, `_queue_cloud_record_activation`,
  `_apply_pending_cloud_record`, `_cloud_autosave_step`,
  `_cloud_persistence_fragment` (`@st.fragment(run_every=2)`),
  `_render_cloud_persistence_status`, `_cloud_project_summaries`,
  `_cloud_persistence_error_message`, `_detach_cloud_project`,
  `_duplicate_active_project`, `_create_new_project`.
- Manage Projects/community: `_render_manage_projects_workspace`,
  `_render_manage_projects_cloud_list/history/trash/publish`,
  `_render_public_project_page`, `_render_embed_project_widget`,
  `_render_explore_projects_directory`, `_render_community_sidebar`,
  `_render_public_project_sidebar`, `_fork_project_to_sandbox`,
  `_toggle_community_project_like`, `_render_hud_explore_community_button`.
- Account/billing UI: `_render_main_account_header`,
  `_render_authenticated_account_controls`, `_open_billing_modal`
  (`@st.dialog`), `_render_credits_purchase_popover`,
  `_render_billing_action_button`, `_render_user_management`.

## Invariants

- `.lfp` payloads stay backward compatible: `_LFP_FORMAT_VERSION` gates
  migrations and unknown keys must be ignored, not crash.
- Autosave is debounced (`_AUTOSAVE_DEBOUNCE_SECONDS`) with bounded retries;
  failures surface via `_cloud_persistence_error_message` and never silently
  drop user edits.
- Cloud lists are invalidated explicitly (`_invalidate_cloud_project_list`)
  after writes.

## Tests

`_check_lfp_*`, `_check_cloud_*`, `_check_public_*`, `_check_ui_share_*`,
`_check_saas_*` (billing/credits).
