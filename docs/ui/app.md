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
