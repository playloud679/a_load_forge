# src/ui/styles.py — global CSS and card styling

- `GLOBAL_CSS` — the full app stylesheet (verbatim from the original
  `ui_app.py` `st.markdown` block).
- `inject_global_css()` — renders it once per run. `ui_app.py` calls it right
  after `st.set_page_config` and before the auth gate.
- `_load_type_card_styles(version)` — cached CSS for the illustrated
  load-type cards. `version` is the cache-busting key; bump it (`square_v5`,
  `square_v6`, ...) whenever `assets/load_types/*.png` are regenerated.
- `_workspace_tab_styles()` — cached CSS for the illustrated Bass Match / Box Design mode selectors (with embedded base64 artwork in sidebar) and the precision CAD top application bar (`.st-key-global_app_bar`, LED status badge, aligned button controls, and floating popover menus).
- `_focused_port_flare_style(state)` — per-state port flare styling used by
  the Ports tab.

## Invariants

- The stylesheet must keep tooltips visible (`z-index: 1000000`, no
  `display: none` on `[data-testid="stTooltipContent"]`) and design-tab
  labels wrapping (`white-space: normal !important`); regression tests assert
  these strings.
- CSS is injected before any auth/widget rendering so reruns do not reflow.

## Project-first UX

The original logo, load diagrams, colors and card styles are preserved. Phase B
restores the iconic illustrated Bass Match and Box Design selectors as the primary
engineering mode switcher, while Projects and Community are secondary header controls.
The native sidebar opener stays visible when the Streamlit toolbar is hidden, including mobile.

Global CSS hides the legacy compatibility workspace widget independently of
the old illustrated stylesheet, avoiding duplicate navigation. Primary text
labels can wrap at narrow widths and use Streamlit's native column layout.

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

### Sidebar search specification brief

- `section[data-testid="stSidebar"] div[data-testid="stTabs"]` styles the sidebar tabs
  as a clean segmented control bar with dark container, subtle borders, and an emerald active indicator.
  Single-tab lists (`:not(:has(button:nth-of-type(2)))`) are suppressed so Simple mode displays without redundant tab buttons.
- `.st-key-sidebar_brief_header_container` and `.sidebar-brief-title` style the top brief header
  row housing the Search Brief title and aligned Advanced mode toggle switch.
- The 7-card enclosure topology selector grid (`_load_type_card_styles()`) is always visible directly
  in the sidebar across both simple and advanced modes, retaining full brand artwork and instant click states.
- Non-advance (Simple) mode organizes the entire workflow in a single unified panel without artificial tab headers,
  exposing enclosure setup, volume, goal, and library filters without tab-switching.
- `.sidebar-section-title` provides subtle CAD-like technical subsection titles.
- `.sidebar-brief-summary-card`, `.sidebar-brief-tag`, and `.sidebar-brief-count` style
  the persistent summary card at the bottom of the sidebar.

### Pre-Run Workbench Canvas (Phase D)

- `.st-key-temp_bass_match_page div[data-testid="stTabs"] div[role="tablist"]` hides the Run/Results
  tablist header so workflow states operate sequentially rather than as competing tabs.
- `.st-key-bass_match_brief` unifies the search brief into a sleek CAD telemetry panel
  with `.bass-match-hero-title`, `.bass-match-brief-row`, `.bass-match-spec-line-primary` (emerald specs),
  `.bass-match-spec-line-secondary`, and `.bass-match-readiness-row` (monospace readiness badge) on a clean horizontal line.
- `.finder-constraint-grid` and `.finder-constraint` format active constraints as an
  integrated specification matrix organized inside the collapsed `Search details ▸` expander.
- `.st-key-finder_run_search_main` styles the primary dominant emerald Run CTA positioned prominently in the hero area.
- `.st-key-finder_candidate_pool_expander` styles the secondary candidate pool accordion.

### Results State Styling (Phase E)

- `.bass-match-results-summary` and its child selectors (`.bass-match-results-summary-primary`,
  `.bass-match-results-match-count`, `.bass-match-results-summary-meta`) structure the compact
  two-line post-run header, giving prominence to the match count and simulation parameters while
  keeping execution telemetry in muted monospace.
- `.st-key-bass_match_result_actions` styles the Box Design launch action bar with
  floating dark blur container, glowing emerald primary CTA on selection, and high-readability hints.
- `.st-key-finder_edit_search_btn` styles the compact secondary "Edit search" button
  beside the results summary line to easily return to the search brief.
- `.st-key-finder_match_preview_card` and `.st-key-finder_comparison_preview_card`
  style the bottom deep-dive and comparison cards with dark CAD surfaces and monospace telemetry.

### Visual Polish & Cohesion (Phase F)

- `.st-key-global_app_bar` utilizes glassmorphism backdrop blur (`backdrop-filter: blur(12px)`)
  and high-contrast CAD navigation tab styling (`[class*="st-key-workspace_tab_"]`) with bottom
  accent borders and subtle transitions.
- Restrained typography: removed aggressive uppercase transforms across brief metrics
  (`.st-key-bass_match_brief .stMetric`), general metric labels (`.stMetric label`), constraint labels
  (`.finder-constraint-label`), run statistics (`.lf-run-stat-label`), and preview cards
  (`.st-key-finder_match_preview_card .stMetric`), establishing a clean sentence-case engineering hierarchy.
- Softened multiselect tags (`div[data-baseweb="tag"]`) from loud green pills to dark translucent surfaces
  (`rgba(255, 255, 255, 0.05)`) with subtle borders (`rgba(255, 255, 255, 0.14)`) and neutral glyphs, eliminating
  visual noise when multiple driver brands or topologies are selected.
- Calmed input and selectbox hover states (`border-color: rgba(255, 255, 255, 0.32)`), reserving saturated emerald
  (`#10b981`) exclusively for active `:focus-within` and primary call-to-actions.
- Menu dropdown hover items use clean neutral highlighting (`rgba(255, 255, 255, 0.08)`) with emerald reserved for
  the currently active selection.
### Viewport Height Optimization & High Legibility

- Root font size anchored to `16px` with antialiased and legible rendering across devices.
- Sidebar width anchored stably at `23.5rem` (376px) on desktop viewports with pure black background and `box-sizing: border-box`, completely eliminating horizontal content clipping and right-edge truncation across browser viewports (Chrome, Safari, Firefox).
- Enclosure load-type cards use explicit `3.4rem` button heights and `1.8rem` label flex containers, preventing Safari/WebKit `aspect-ratio` height-collapsing bugs where rows previously overlapped.
- Sidebar tabs scaled to `0.86rem` with `0.20rem 0.40rem` padding to ensure `Driver`, `Load Selection`, and `Enclosure Parameters` render on a single line without truncation or overflow scroll arrows.
- Vertical block gaps and container padding optimized to fit the entire CAD telemetry panel within standard 900p / 1080p desktop viewports without vertical scrolling.
- Legibility-first typography hierarchy: widget labels boosted to `0.96rem` (main) and `0.94rem` (sidebar), captions to `0.88rem` with high-contrast `rgba(255, 255, 255, 0.85)`.
- Metric widgets (`.stMetric`) scaled to `0.88rem` labels (`#cbd5e1`) and `1.25rem` values (`#ffffff`).
- Constraint grid labels boosted to `0.80rem` with values at `0.96rem`.
- Main tabs scaled to `0.95rem` (`font-weight: 600`) and dataframe grid cells scaled to `0.92rem`.
- Top app bar buttons scaled to `0.88rem` with bottom margin reduced to `0.45rem`.
- Sidebar illustrated workspace mode switch buttons adjusted to `3.4rem` height.



