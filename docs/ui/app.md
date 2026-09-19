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

Authenticated fresh sessions start in Manage Projects. Workspace changes survive
ordinary reruns; successful local sign-in/registration queues a one-time return
to Cloud Projects. Explicit shared-design links open Box Design and public,
community, checkout and admin routes retain their handling. The original branded
sidebar and workspace artwork remain intact. The projects landing also exposes
the original illustrated Community action alongside Bass Match and Box Design.
