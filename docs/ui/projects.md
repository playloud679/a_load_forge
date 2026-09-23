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
  `_render_cloud_persistence_status`, `_render_static_status_badge`,
  `_cloud_project_summaries`, `_last_cloud_workspace`,
  `_resume_last_cloud_project`, `_is_project_name_taken`,
  `_cloud_persistence_error_message`, `_detach_cloud_project`,
  `_duplicate_active_project`, `_create_new_project`.
- Studio entry: `_render_studio_start` (no-context landing with Bass Match /
  Box Design cards and a secondary recent-project list). Opening a cloud record
  resumes its saved engineering workspace via `_apply_pending_cloud_record`.
  Clean app startup resumes the latest active cloud project via `_resume_last_cloud_project`,
  preventing duplicate untitled drafts on app open/reload.
- Manage Projects/community: `_render_manage_projects_workspace`,
  `_render_manage_projects_cloud_list/history/trash/publish`,
  `_set_project_selection_batch`,
  `_render_public_project_page`, `_render_embed_project_widget`,
  `_render_explore_projects_directory`, `_render_community_sidebar`,
  `_render_public_project_sidebar`, `_fork_project_to_sandbox`,
  `_toggle_community_project_like`, `_render_hud_explore_community_button`.
- Account/billing UI: `_render_main_account_header` (consolidated Global Application Bar with primary navigation, project rename, persistence indicator, visibility popover, prominent WOW-effect Upgrade / subscription CTA button, and compact account popover containing billing and admin tools),
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
- **Duplicate names forbidden**: Project names must be unique within a tenant
  (case-insensitive). Duplicate checks in `_is_project_name_taken` protect header
  renaming, Manage Projects renaming and creation, and file imports. Duplicating an
  existing project automatically generates unique suffixes `(Copy)`, `(Copy 2)`, etc.
- **New Project never discards work**: `_create_new_project(name)` keeps the
  active design and Bass Match state, detaches from any previous cloud record
  and autosaves the work into the new project. The old clean-slate behaviour
  is an explicit opt-in through the "Start from a blank design" checkbox
  (`start_blank=True`), which is the only caller of
  `_clear_active_project_state`.

## Tests

`_check_lfp_*`, `_check_cloud_*`, `_check_public_*`, `_check_ui_share_*`,
`_check_saas_*` (billing/credits), `_check_ui_new_project_preserves_work`.
The account/billing AppTests drive the header buttons by their stable keys,
and the Finder workspace AppTest asserts the collapsed `Account`
panel is present on the Bass Match screen.

## Project-first UX

Manage Projects puts the private project list before the collapsed current-
project details/export/sharing panel. Search matches project names case-
insensitively; sorting supports recent updates and names. Opening a list item
queues activation before widget creation on the next run and enters the
project's saved engineering workspace (Box Design fallback).
Cached project summaries are keyed by tenant and user identity. The original
community artwork and visual styling remain intact. Duplicate and Trash actions
are grouped under each project’s More menu.

### Multi-selection and batch project actions

- **Project cards checkboxes**: Every active project card includes a checkbox (`mp_sel_<project_id>`) for multi-item selection.
- **Batch action bar**: Above the card list, controls display selection count (`N of M selected`), `Select all`, `Deselect all`, and a `🗑️ Delete (N)` action backed by a confirmation popover. Confirming moves all selected projects to Trash simultaneously, cleanly detaches if the currently active project was included, and refreshes the list.
- **Batch restore in Trash**: The Trash tab mirrors multi-selection checkboxes (`mp_trash_sel_<project_id>`) with `Select all`, `Deselect all`, and a bulk `♻️ Restore (N)` action. Individual single-item restore remains available on each card.

### Studio entry

`_render_studio_start` is the no-context landing screen (GOLDEN_STD studio
entry). It offers Bass Match and Box Design as the two primary actions and
lists recent projects as a secondary element, never as the dominant content.
`_last_cloud_workspace` resolves a returning user's most recent engineering
workspace without opening the project. Projects and Explore are reached only
by explicit selection, deep link or public URL.

### Consolidated single-row main header architecture

`_render_main_account_header` renders an ultra-clean, CAD-grade single-row horizontal toolbar:
- **Left**: Project context (`📁 Project name` popover with rename, precision `● Saved` LED status badge, and `🔒 Private ▾` / `🌐 Public ▾` visibility popover).
- **Right**: Secondary navigation & account (`Projects` button, `Community` button, and floating `Account ▾` popover with credits, plan, admin tools, and sign out, backed by a hidden test compatibility anchor).
- **Sidebar Integration**: Primary engineering mode switching lives in the sidebar under the brand logo, keeping the main workbench 100% focused on execution and results.

Tests in `tests/test_phase_b.py`, registered in the active runner, cover direct
entry, identity/rename/comparison, save failures, publication updates, withdrawal
and public/version/embed access. Storage tests also exercise Firestore checks
with a mocked client; they do not contact production.

## Phase B project context

Engineering pages and Projects share `_render_project_header`: name/rename,
acknowledged save state and Private/Unlisted/Public access. Empty names become
Untitled project and can autosave without a naming wizard. Local-only sessions
say Session only, never Saved. The header mounts the single persistence timer.
Merely browsing Projects with no active work does not create an empty record;
the Untitled project starts when entering either engineering workspace.
Save errors use user-facing recovery instructions; backend detail stays in logs.
Phase C Projects is a browser: cards show name, modified time, save state and
Private/Unlisted/Public visibility. Technical metrics and backend revision
identifiers are removed from the default list. Project actions remain in a
collapsed secondary panel; import, history, trash and publication workflows
remain available in their contextual tabs.

Opening another saved project first flushes edits; failed saves prevent the
switch. Publication lookup uses authenticated owner/tenant/project identity,
including legacy publications and withdrawn records. Access changes preserve
the published content; explicit Update public version publishes current saved
content. Private withdraws every legacy link. A content hash detects unpublished
edits. Publication access is enforced by the public store, never private reads.

The image-tab navigation returns to the technical sidebar; Manage Projects is
reached from the Account panel (legacy key `sidebar_manage_projects_btn`).
Account keeps its billing/sign-out actions and the existing secondary Community
entry; the Manage Projects sidebar also keeps a Community action. No billing
policy, credits calculation, physics or result ranking changes in Phase B.
