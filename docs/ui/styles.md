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
  Only tab headers inside `.st-key-bass_match_simple_tab_container` are hidden.
  The sidebar-scoped selector overrides the general tablist display rule by specificity.
  Global single-tab `:not(:has(button:nth-of-type(2)))` selectors were removed:
  Box Design and Bass Match Advanced tab bars remain visible across workspace switches.
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

### Data-entry control system

One `:root` token block drives every data-entry surface so the sidebar and the
main workbench can no longer drift apart:

- `--lf-control-bg`, `--lf-control-border`, `--lf-control-radius` and
  `--lf-control-height` are shared by `st.number_input`, `st.text_input`,
  `st.selectbox` and `st.multiselect`; the select/multiselect control div is
  repainted from the same token so all four surfaces match.
- Streamlit widget markup changed across versions: `<=1.58` renders BaseWeb
  (`data-baseweb`), while `1.64+` renders react-aria (`div[role="group"]`). The
  select/multiselect rules therefore target **both** structures; the numeric
  text/number fields keep matching through `.stNumberInput input` /
  `.stTextInput input`. `requirements.txt` pins `streamlit==1.58.0` (the version
  the suite is verified against) so the locally checked DOM matches production
  instead of silently drifting to the latest release.
- `--lf-stepper-width` and `--lf-stepper-icon` size the number-input `+`/`-`
  buttons uniformly. A single global rule replaces the earlier competing
  sidebar/main declarations: the compact sidebar width was silently outranked
  by a higher-specificity `section[…]` rule, so it never applied.
- `.st-key-refresh_presets_btn_finder` and
  `.st-key-refresh_presets_btn_box_design` render the 🔄 library-refresh icon
  as a square button at `--lf-control-height`, aligned with the adjacent Search
  preset input. The rows use
  `st.columns([5, 1], vertical_alignment="bottom")`; the previous hardcoded
  28px spacer and `use_container_width` stretch are gone.

### Responsive spacing and legibility

The workbench may scroll vertically: fitting every control into one screen is
not a layout requirement. Sidebar blocks use the shared 0.75rem gap token, 0.9rem labels and a
shared 2.4rem control height (`--lf-control-height`); captions use a 1.4
line-height without negative bottom margins. Number-input steppers, text
inputs, selectboxes and multi-selects share one charcoal surface and radius
through the data-entry token block.

Response controls wrap at a 10rem column minimum; trace pills occupy their own
row. Summary metrics wrap at a 9rem column minimum and labels can wrap.
The global application bar uses intrinsic heights, wrapping labels and columns
with a 6.5rem minimum (10rem for the project name), so project names and actions cannot overflow fixed rows. The decorative spacer can shrink to zero.
These rules preserve widget keys and the scoped Simple-mode tab-header hiding.

Candidate library containers use `clamp(240px, 100dvh - 580px, 460px)` on
desktop. Enclosure artwork uses a square aspect ratio and intrinsic card height.
The desktop sidebar scales responsively with `clamp(28rem, 28vw, 42rem)` to take
full advantage of wide desktop screens while preserving room for the main area.
Logo and version share a vertically centered header row, reserving 2.25rem
on the right for the native sidebar collapse button. Sidebar tabs use
separate bordered surfaces with 0.5rem gaps, a three-rem minimum height,
wrapping labels and an emerald selected border; the shared underline is hidden.
Load-type enclosure cards maintain a 1:1 square aspect ratio with full
square background sizing. A single four-column grid owns the complete cards,
including captions with reserved two-line space and a 0.375rem image/caption gap;
row spacing is 0.75rem. HTML captions avoid Markdown height underestimation; illustrated workspace tabs use a 3:1 aspect ratio (`aspect-ratio: 3 / 1`,
`min-height: 4.2rem`) with edge-to-edge background sizing to restore their
full-height form factor; the sidebar logo scales responsively with
`max-height: 3.8rem` to match the wider sidebar header. Root typography stays at 16px;
navigation, tooltips and native scrolling remain available.


### Shared sidebar alignment

`--lf-gap-xs/sm/md` define spacing once. Named `field_row_*` containers align
paired controls at the bottom and keep filter pairs in independent rows, so
multiselect wrapping cannot move just one column's following fields.
`search_row_*` uses a fluid input track and a fixed control-width action track
in both workspaces. Fields draw one outer border, never nested input borders.
Number stepper CSS targets only `stNumberInputStepUp/Down`, leaving the label's
help button at its natural size. Native widget keys and interactions are retained.

The upgrade-button selectors cover both `bm_upgrade_callout` and
`bm_upgrade_callout_shortfall`, whose separate keys allow simultaneous rendering.
