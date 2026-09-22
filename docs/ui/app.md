# src/ui/app.py — Streamlit entry point

`main()` is the original module-level app body, indented into one function:

1. Session defaults (`_state._default(...)` calls) and migrations.
2. Query-param handling: share token (`d`), checkout status, logout, public
   project (`p`), explore, maintenance, `admin_users`.
3. Pending-result application (batch results, comparisons, atlas points).
4. `with st.sidebar:` — the full control surface, including the 14 locals
   consumed after the block (`workspace_mode`, `load_type`, `current_ts`,
   `derived`, alignment objects, `filtered_preset_names`, ...).
5. Special workspaces: public project, embed, explore, catalog maintenance,
   user management, manage projects.
6. Main workspace dispatch with the top-level error boundary.

## Invariants

- This is the only place allowed to call `ui_app`-level bootstrap state;
  functions in other modules receive their inputs as arguments.
- `main()` is called once per Streamlit rerun by `ui_app.py`; it must not be
  imported for side effects.
- The CSS injection and `set_page_config` happen in `ui_app.py` before
  `main()`, preserving the original ordering.
- The selected driver summary prints the published nominal frame, `Sd` and the
  equivalent effective piston diameter. When `DriverPresetInfo.size_sd_conflict`
  is set (published frame size and `Sd` cannot coexist) a warning states that
  the simulation uses the stored `Sd` and asks the user to verify the datasheet;
  the published size is never replaced by an Sd-derived estimate.

## Project-first UX

Studio entry follows intent (GOLDEN_STD studio entry). An explicit deep link
(`?view=`, the shared-design `?d=` token, `?p=` public project) routes straight
to its workspace; otherwise the last engineering workspace is resumed (session
memory first, then the most recent cloud project's saved `workspace_mode`);
otherwise the minimal Studio start screen (`_render_studio_start`) offers Bass
Match and Box Design with recent projects as a secondary list. Projects and
Explore are supporting destinations and are never the generic landing page.
The original branded sidebar remains. Primary engineering mode selection lives in the
sidebar directly beneath the brand logo via `_state._render_workspace_tabs()`, displaying
the authentic illustrated Bass Match and Box Design artwork cards to establish the active
control context for the parameters below.
In the main workspace, a single, perfectly aligned, compact Global Application Bar hosts
project context on the left (name, save state, visibility) and restrained secondary actions
on the right (Projects, Community, Account).
In Bass Match, the sidebar is organized as a clean Search Brief (Phase C):
the Advanced mode toggle is positioned directly at the top alongside the SEARCH BRIEF
header (`.st-key-sidebar_brief_header_container`) with mode captions. The enclosure topology
selector is condensed into a compact selector button (`🎛️ Enclosure: <selected> ▾`) that
opens the full illustrated topology card gallery via a Streamlit popover (`.st-key-finder_enclosure_popover_wrap`),
preventing sidebar clutter while preserving the illustrated topology identity. The bottom
Advanced toggle is scoped exclusively to Box Design to avoid duplicate widget keys.
Existing public, shared, billing and admin links retain their handling.
