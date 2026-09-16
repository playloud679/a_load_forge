# src/ui/styles.py — global CSS and card styling

- `GLOBAL_CSS` — the full app stylesheet (verbatim from the original
  `ui_app.py` `st.markdown` block).
- `inject_global_css()` — renders it once per run. `ui_app.py` calls it right
  after `st.set_page_config` and before the auth gate.
- `_load_type_card_styles(version)` — cached CSS for the illustrated
  load-type cards. `version` is the cache-busting key; bump it (`square_v5`,
  `square_v6`, ...) whenever `assets/load_types/*.png` are regenerated.
- `_workspace_tab_styles()` — cached CSS for the workspace tabs.
- `_focused_port_flare_style(state)` — per-state port flare styling used by
  the Ports tab.

## Invariants

- The stylesheet must keep tooltips visible (`z-index: 1000000`, no
  `display: none` on `[data-testid="stTooltipContent"]`) and design-tab
  labels wrapping (`white-space: normal !important`); regression tests assert
  these strings.
- CSS is injected before any auth/widget rendering so reruns do not reflow.

## Project-first UX

The original logo, illustrated workspace buttons, load diagrams, colors and card
styles are preserved. The native sidebar opener stays visible when the Streamlit
toolbar is hidden, including mobile.

The app header (`header[data-testid="stHeader"]`) is kept transparent instead of
`display: none` so the sidebar opener remains reachable. It is a fixed bar over
the first main-area widgets (account, subscription, logout), so it carries
`pointer-events: none !important` and only
`[data-testid="stExpandSidebarButton"]` re-enables `pointer-events: auto`.
Removing that guard makes the top-row buttons visible but unclickable.

### Bass Match result toolbar

- `.lf-run-stats*` styles run-statistics tiles inside the collapsed Run details
  expander. On Results this appears below the table, alongside diagnostics.
- `.st-key-bass_match_result_actions` is a compact unbordered selection toolbar
  with a primary Box Design button; it adds no card padding or large heading.
- Run and Results are separate lazily rendered native tabs. No CSS hiding or
  results-presence selector is needed to demote a competing Run action.
