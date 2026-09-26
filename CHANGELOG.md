# Changelog

## 0.21.2 (2026-09-26)

- **No more nonsense comparisons from bad catalog records** (new `src/driver_plausibility.py`): records whose T/S cannot describe the product are flagged — multi-driver kits ("Focal 165 SF3Kit a 3 vie", which had inherited a 65 mm midrange's parameters and produced a 2 L "6.5-inch" box), placeholder parameters (Qts 1.000 with Le 0) and a name size that contradicts Sd (6.5" coax pairs with Sd 530 cm², "8in" records with Sd 2 cm²). 57 of ~19,200 records. A flagged current driver shows "parameters look unreliable" instead of Bass Match alternatives; flagged records are never suggested.
- Alternatives: listings differing only by an "Ohm" word ("Visaton FRS 7 - 8" / "FRS 7 - 8 Ohm") collapse to one.
- Validation: `make test` passed; usage analytics tests 13 passed; `make test-ui` passed except the pre-existing "Bass Match candidate pool starts open…".

## 0.21.1 (2026-09-26)

- **"Compare with Bass Match" lands on the comparison**: a Studio entry with `?compare=1` (the portal's new button on driver pages) shows the similar-driver Bass Match preview above the chart instead of below the fold, with a "Hide" action. `alternatives_shown` records `on_top`.
- Validation: usage analytics tests 11 passed; `make test` and `make test-ui` passed except the pre-existing "Bass Match candidate pool starts open…".

## 0.21.0 (2026-09-26)

- **Box Design without sign-in (guest mode, `LOAD_FORGE_GUEST_ACCESS`, default on)**: a signed-out visitor lands straight on a computed Box Design — the portal driver and box included, also from `view=bass-match` links — instead of the sign-in wall. Guests have no account, credits or persistence; they never share the local demo account.
- **Save · Sign in keeps the work**: the guest's design (`d`) and project name ride the 10-minute return cookie across Google sign-in; the first signed-in run restores them and saves the project. Same-session email sign-in and "Back to my design" restore a snapshot (the sign-in page renders no design widgets, whose state Streamlit would drop).
- **Bass Match and Projects for guests**: a non-blocking invite above Box Design ("Sign in — free" / "Not now") instead of a wall; tabs and portal links keep the guest in Box Design.
- **Similar drivers in this box** (new `src/ui/alternatives.py`): under every Box Design, the best 5 of the ~25 most similar catalog drivers (size, Fs, Qts, Vas; duplicates across sources collapsed) in the same load and volume, with F3, peak SPL, excursion, price and **Open**. Guests get "Search all N drivers — sign in free". ~1 ms per driver, cached.
- **Fix — current account memo could cross sessions**: `_get_current_user_account` used a process-wide `functools.cache`; concurrent sessions could briefly read another user's account (plan, credits, admin flag). It now memoises in `st.session_state`, cleared once per run.
- Analytics: new events `guest_session`, `sign_in_invite_view`, `alternatives_shown`, `alternative_opened`; `auth_gate_view` carries the reason; Traction funnel starts with guest visitors and sign-in openers.
- Validation: `make test` 113 passed; `make test-ui` 113 passed, 1 pre-existing failure unchanged on `main` ("Bass Match candidate pool starts open…").

## 0.20.2 (2026-09-26)

- **Live tab reads one row per visitor**: last seen, arrival (Google, direct…), entry page, pages viewed, reached the Studio, signed in, last event; with totals (visitors · reached the Studio · left after one page). "Follow one visitor" keeps the event-by-event path. New pure `usage_analytics.visitor_summaries`.
- **Tagging a browser internal hides its past visits too**: once `?lf_internal=1` is opened, every earlier event of that anonymous id disappears from Live (it previously hid only events recorded after tagging).
- Validation: usage analytics tests 7 passed; `make test` passed.

## 0.20.1 (2026-09-26)

- **Admin Live tab** (LLOOGG-style): raw stream of portal `growth_telemetry` and Studio `usage_events`, newest first, refreshed every 10 s; a portal visitor is shown by email once they sign in; admin/test accounts, `?lf_internal=1` browsers and deploy checks are hidden; "Follow one visitor" shows one person's whole path. Pure merge in `usage_analytics.live_feed`.
- Note: the production image tagged v0.20.0 was built from this branch's working tree and already contains the Live tab; this release aligns `main` and the version number with it.
- Validation: `make test` 111 passed; usage analytics tests 6 passed.

## 0.20.0 (2026-09-26)

- **Security fix — User Management was reachable by any signed-in user**: `?admin_users=1` rendered the admin console (all emails, plan changes, credit top-ups) without an admin check; only the menu button was guarded. `_render_user_management` now enforces `_maintenance_allowed()` itself. Regression test added.
- **Product usage analytics** (new `src/usage_analytics.py`, `src/ui/usage.py`, `docs/usage_analytics.md`): best-effort `usage_events` in the private Firestore database for the sign-in wall, sign-up, session start, Box Design simulations (the unprompted default render is marked non-interactive), Bass Match runs, project save/publish and paywall prompts. Deduplicated per session; scalar props only; no design contents, IP or payment data.
- **Portal visit → sign-up linkage**: the portal's anonymous `lf_aid` is accepted on entry and crosses the Google sign-in inside the existing 10-minute return cookie (added to `DESTINATION_KEYS`); it is dropped from the URL once signed in. No long-lived analytics cookie.
- **Admin console tabs**: *Traction (real users)* — funnel (sign-in wall → sign-up → simulation → save → return → publish → paywall), load-type and driver rankings, per-user timelines — and *Accounts & credits*, which adds the join date and a "Test account" checkbox (`analytics_settings/exclusions`). Admins and test accounts are excluded from every figure. "Total sims" is relabelled "Bass Match credits used", which is what it counts.
- Validation: `make test` 110 passed; usage analytics, admin guard and portal handoff tests passed. Pre-existing failure unchanged on `main`: "Bass Match candidate pool starts open…".

## 0.19.5 (2026-09-25)

- **AFW export is admin-only**: the "Download AFW project" button (AUDIO per Windows, DCAAV) under Export design is shown only to administrators (`_afw_export_allowed`, same check as catalog maintenance). Standard users keep CSV/FRD/ZMA and the portable **`.lfp`** project export ("Export .lfp Backup" in Project actions).
- **Each fact once per screen** (Bass Match had the balance 3×, Upgrade 3×, the catalog size 5×): the sidebar FREE PLAN box is gone (plan, balance and Upgrade stay in the app bar); the in-page credits box appears only below 300 free credits when the run is still affordable, and never together with the shortfall error; the "/ 3,000 (100%)" ratio is gone (it read 770,112 / 3,000). The catalog size appears once, in the candidate-pool header ("N of M drivers match your filters"); the brief row shows pre-qualified drivers and cost only; the library tabs and header no longer restate counts; the unbacked "CERTIFIED DRIVERS" banner becomes "CATALOG: N DRIVERS" in Box Design only. Rule documented in `docs/ui.md` ("One place per fact").
- Validation: `make test-match MATCH='UI'` 110 passed (new: AFW admin-only and project export stays `.lfp`; credits, Upgrade and catalog size shown once per screen).

## 0.19.4 (2026-09-25)

- **Load selection grid 3×2**: first row the loads with the driver radiating directly (Sealed, Reflex, DCAAV), second row the bandpass loads with the driver inside (BP4, BP6, BP8), in both Box Design and Bass Match. **Infinite baffle is no longer offered**; saved projects and Finder selections that use it still open and show a "no longer offered" note under the grid.
- Validation: `make test` passed; `make test-match MATCH='UI'` 108 passed.

## 0.19.3 (2026-09-25)

- **Fix — Bass Match kept searching old drivers after a filter change**: opening one or more library drivers in Box Design silently pinned them (since 0.19.0), and pinned drivers were forced into the candidate pool even when they failed the active filters, so every later search evaluated only those drivers ("2 evaluated"). Opening a design no longer pins it, and a pin leads the pool only while it passes the filters. Regression test added (fails on 0.19.2).
- **The load is shown as DCAAV**: `"DCCAV"` stays the internal value (saved projects, engine); every user-facing place — load cards, design tabs and pins, compare-loads legend, Finder summaries and results table, captions, toasts, help and the AFW export file name (`load_forge_dcaav.afw`) — shows **DCAAV**. Label parsing accepts both names.
- Validation: `make test` passed; `make test-match MATCH='UI'` 108 passed.

## 0.19.2 (2026-09-25)

- **Compact controls under the chart**: trace pills 28 px (were ~50), toggles and Pin/Tabs/Reset buttons 1.9 rem with 0.80 rem text, the frequency-window slider pulled up, and the Design/Driver/Export detail buttons 30 px. The control block shrinks from ~110 to 64 px and the chart gains the space (`--lf-fit-chart-offset` 504 → 469 px); still 0 px page scroll at 900, 1000 and 1080 px window height.
- Validation: `make test` passed; `make test-match MATCH='UI'` passed.

## 0.19.1 (2026-09-24)

- **Box Design fits the window**: charts (Response, Excursion, Impedance, Ports, Group Delay) take the viewport height minus the Studio chrome (min 360 px, fixed 420 px on phones) instead of a fixed 520–580 px; measured 0 px page scroll at 1400×1000 and 1920×1080 (the Ports workbench still scrolls).
- **Summary strip above the chart**: F3, Peak SPL, Excursion, Min Z, Volume and Forge Score on one line; model warnings behind a red "N warnings" button; full metrics, badges and load image under "Details". Same computations as before.
- **Compact app bar**: one 49 px row (was ~150 px), uniform 2.25 rem buttons sized to their labels, project group left and account group right. The credit button shows the balance ("N credits · Upgrade"), not "N / 3,000", which was wrong once top-up packs pushed the balance above the monthly Free allowance.
- Design/Driver/Export details are popovers on one row; toggle labels no longer wrap; duplicate tab subheaders removed.
- Validation: `make test` 107 passed; `make test-match MATCH='UI'` 107 passed (new: viewport-fit layout).

## 0.19.0 (2026-09-24)

- **Portal → Studio handoff** (new `src/ui/navigation.py`, `docs/ui/navigation.md`):
  - Catalog links from load-forge.com (`?preset=`, optional `vb`, `fb`, `load=sealed`) open Box Design with that driver and box. Inputs are validated before any state change (unknown preset, non-finite or out-of-range values, `fb` on sealed) and applied once per session, so reruns never overwrite user edits.
  - An existing cloud project is saved and detached before the linked design is loaded; saved work is never overwritten.
  - Sign-in return destination: the allowed entry query (`view`, `preset`, `vb`, `fb`, `load`, `p`, `explore`, `embed`, `d`) is kept in a 10-minute cookie across the OIDC redirect and restored once after login. Tokens and arbitrary URLs are never restored.
  - `view=bass-match` / `view=box-design` deep links and the new `preset` parameter select the workspace; last-project resume is skipped for linked entries.
- **Library → Box Design**: "Open in Box Design", multi-driver "Simulate in Box Design" and passive-radiator "Apply" now switch workspace reliably from the candidate-pool fragment and keep the pinned selection across reruns. Workspace changes go through `_select_workspace`, which also clears handoff query keys.
- **Credits callout**: the shortfall callout uses its own key; styling matches every `bm_upgrade_callout*` variant.
- Validation: `make test` 107 passed; `make test-match MATCH='UI portal'` 5 passed.

## 0.18.32 (2026-09-24)

- **Fix — eliminate double login requirement on Google OIDC authentication**:
  - Fixed a regression in Streamlit's WebSocket session management where reconnected browser sessions failed to update `_user_info` from the freshly set `_streamlit_user` identity cookie.
  - Implemented automatic recovery from signed OIDC cookies on initial render, ensuring authenticated users enter the app immediately without requiring a second sign-in attempt.
  - Added runtime hook on `WebsocketSessionManager.connect_session` to synchronize active session identity upon client reconnection.
  - Added regression test for OIDC reconnection cookie synchronization.

## 0.18.31 (2026-09-24)

- **Proprietary catalog, large format plot, compact Box Design layout and English localization**:
  - Strictly restricted the active preset catalog and search engine to the 9,915 certified drivers in the proprietary library.
  - Substantially enlarged the frequency response and maximum input power (MIL) chart to 580 px height (+140%), and increased excursion, impedance, ports velocity and group delay plots to 520 px for clear acoustic inspection.
  - Squeezed and compacted Box Design whitespace: streamlined tab-to-chart spacing, tightened plot controls and zoom slider padding, consolidated captions, and compacted performance scorecard metrics.
  - Complete English localization: translated all billing modals, credit recharge packs, quota callouts, and search brief cards to clean, professional English.
  - Cleaned UI visuals: removed all AI-style emojis and enhanced titanium/emerald industrial engineering controls and badges.

## 0.18.30 (2026-09-23)

- **Layout primitives, load type grid and fast test runner**:
  - Introduced shared sidebar layout primitives (`--lf-gap-xs`, `--lf-gap-sm`,
    `--lf-gap-md`, `.st-key-load_type_grid`, search rows and field rows) for
    clean alignment, responsive spacing, and uniform control styling.
  - 4-column acoustic load selection grid with unified artwork and caption
    alignment.
  - Scoped `stNumberInput` stepper button rules to prevent style bleed across
    other action buttons.
  - Added fast local test runner with concise summary reporting and structured
    suite logs in `.local/test-logs/` (`make test`, `make test-fast`, `make test-all`).
  - Aligned development contract in `AGENTS.md` and `docs/development.md` for
    focused, reviewable iterations.

## 0.18.29 (2026-09-23)

- **Fix — data-entry controls were not restyled in production**: the container
  resolved `streamlit>=1.58.0` to the latest release; Streamlit 1.64 dropped the
  BaseWeb markup, so the select/multiselect CSS (`data-baseweb`) silently stopped
  matching and the filters rendered black instead of the shared charcoal surface.
  Pinned `streamlit==1.58.0` (the version the suite is verified against) so the
  locally checked DOM matches production and cannot drift again.
- Kept react-aria selectors (`[data-testid="stSelectbox"] div[role="group"]`,
  `[data-testid="stMultiSelect"] div[role="group"]`) alongside the legacy
  BaseWeb ones as forward-compatibility, plus the matching `:focus-within`
  emerald ring.
- Hardened the test harness for newer Streamlit: `AppTest.from_file` now uses
  absolute paths (1.64+ resolves relative scripts against the calling file).
- **Validation**: Python compilation and Streamlit AppTest passed; fresh full
  active suite: **242 passed, 0 failed, 0 skipped**.

## 0.18.28 (2026-09-23)

- **Data-entry spacing and button consistency**: introduced one shared control
  token block (`--lf-control-bg`, `--lf-control-border`, `--lf-control-radius`,
  `--lf-control-height`, `--lf-stepper-width`, `--lf-stepper-icon`) in
  `GLOBAL_CSS` so number inputs, text inputs, selectboxes and multiselects all
  render the same charcoal surface, height and radius in the sidebar and the
  main workbench.
- **Uniform number steppers**: replaced the two competing `stNumberInput`
  button declarations with a single global rule. The compact sidebar width was
  silently outranked by a higher-specificity `section[…]` rule; steppers are now
  a consistent 2rem square with 0.9rem glyphs everywhere (verified 32px in the
  live DOM).
- **Aligned refresh button**: the Bass Match and Box Design Search preset rows
  now use `st.columns([5, 1], vertical_alignment="bottom")` and drop the
  hardcoded `height: 28px` spacer plus `use_container_width` stretch. The 🔄 icon
  renders as a square button at the shared control height and bottom-aligns with
  the input (verified 38.4px square, tops aligned in the live DOM).
- Synchronized `docs/ui/styles.md`, `docs/ui/catalog.md` and `docs/ui/app.md`.
- **Validation**: Python compilation and Streamlit startup AppTest passed;
  fresh full active suite: **242 passed, 0 failed, 0 skipped**; live DOM checks
  confirmed 32px uniform steppers, a single `#141b27` control surface and a
  38.4px square refresh button aligned with the Search preset input;
  `git diff --check` clean.

## 0.18.27 (2026-09-23)

- **Responsive desktop sidebar, enlarged brand logo & authentic workspace tabs**:
  - Replaced rigid sidebar max-width with responsive scaling `clamp(28rem, 28vw, 42rem)` and `width: 100%` content, allowing the sidebar to use available horizontal space on wide desktop displays while preserving ample room for the main simulation workbench.
  - Enlarged the sidebar brand logo (`load_forge`) to scale responsively (`use_container_width=True`, `max-height: 3.8rem`) in the top header row alongside the version badge.
  - Restored authentic full 3:1 form factor (`aspect-ratio: 3 / 1`, `min-height: 4.2rem`, `max-height: 6rem`) and edge-to-edge artwork for the illustrated `Bass Match` and `Box Design` workspace mode tabs.
  - Restored true 1:1 square aspect ratio (`aspect-ratio: 1 / 1`), zero-gap block containers, and tightened label margins (0.10rem) directly beneath the icons for all 7 enclosure load type cards (`Infinite baffle`, `Sealed`, `Reflex`, `BP4`, `BP6`, `BP8`, `DCCAV`), eliminating distortion and excess spacing.
- **Validation**: Python compilation and Streamlit startup AppTest passed;
  acoustic-load smoke: **14 passed, 0 failed**; full test suite: **242 passed, 0 failed, 0 skipped**;
  Chromium headless checks confirmed 1:1 square buttons (141.7px at 2560px, 85.7px at 1440px), 3:1 workspace tabs (96px height at 2560px, 67px at 1440px), enlarged logo (283px at 2560px, 268px at 1440px), and clean layout;
  `git diff --check` clean.

## 0.18.26 (2026-09-23)

- **Sidebar legibility and spacing**: widened the desktop sidebar, aligned the
  version beside the logo in `sidebar_brand_header`, and gave Driver, Load Selection,
  and Enclosure Parameters distinct bordered tab surfaces with usable spacing and
  legible height. Removed compressed spaces and overlapping elements; response
  controls and summary metrics wrap responsively.
- **Validation**: Python compilation and Streamlit startup AppTest passed;
  acoustic-load smoke: **14 passed, 0 failed**; full test suite: **242 passed, 0 failed, 0 skipped**;
  `git diff --check` clean.

## 0.18.25 (2026-09-23)

- **Fix — sidebar tab navigation**: wrap the Bass Match Simple Search brief tab
  in `bass_match_simple_tab_container` and hide only its header using
  sidebar-scoped CSS with sufficient specificity to override the shared tab styles.
- Remove both global structural single-tab rules using
  `:not(:has(button:nth-of-type(2)))`, preventing their hiding behavior from
  affecting Box Design after workspace changes. Driver, Load Selection and
  Enclosure Parameters retain their navigation; Bass Match Advanced retains
  Load type, Performance filters and Library filters.
- Synchronize UI module documentation and release references.
- **Validation**: Python compilation and Streamlit startup AppTest passed;
  acoustic-load smoke: **14 passed, 0 failed**; fresh full active suite:
  **242 passed, 0 failed, 0 skipped**. An initial full run reported one
  candidate-pool multi-selection failure; its isolated rerun and the subsequent
  complete suite passed without code changes. Playwright Chromium and WebKit:
  Simple header hidden, all three Box Design tabs clickable after two workspace
  round trips, and all three Advanced tabs clickable; visual sidebar review passed.
  `git diff --check` clean.

## 0.18.24 (2026-09-23)

- **Fix — Streamlit Read-Only Widget State Compatibility (`ReadOnlyAttributeDictionary`)**:
  - Resolved `TypeError: Widget state is read-only because modifying nested values has no effect on the app` in Bass Match candidate pool selection.
  - Replaced nested mutation and `.setdefault("selection", ...)` on `finder_driver_library_table` with safe state extraction via `_table_selection_rows` and clean whole-dictionary assignment to `st.session_state["finder_driver_library_table"]`.
  - Safely extract selected rows across dictionary, AttributeDictionary, and DataframeSelectionState widget representations while preserving pinned driver names across filter changes.
  - Added regression tests verifying compatibility with Streamlit's `ReadOnlyAttributeDictionary`.
- **Validation**: Python compilation clean; targeted candidate pool test passed; full test suite: **242 passed, 0 failed, 0 skipped**; `git diff --check` clean.

## 0.18.23 (2026-09-23)

- **UI & Workspace Compaction (Compact Desktop Layout)**:
  - `src/ui/catalog.py`: arranged catalog and passive radiator filters across two columns; wrapped driver and passive radiator tables in compact containers with adaptive/clamped heights and streamlined selectors.
  - `src/ui/app.py`: paired max volume and objective side-by-side in Simple mode; displayed manufacturer and part number identity as a single unified caption; aligned Box Design parameters (Fs/Qts, Vas/Qms, Re/Le) into three columns.
  - `src/ui/finder.py`: renamed volume label to "Max volume (L)"; removed redundant caption on Advanced constraints; concealed sidebar summary in Simple mode to maximize vertical space.
  - `src/ui/analysis.py`: resized primary response and MIL charts from 320px to 240px with aligned layer heights, ensuring telemetry and traces fit desktop viewports without vertical scrolling.
  - `src/ui/styles.py`: tightened gaps, paddings, fonts, inputs and stepper controls; reduced load and workspace card heights; added adaptive table height clamping; refined caption margins to prevent text collision.
  - Synchronized documentation across `docs/ui/app.md`, `docs/ui/catalog.md`, `docs/ui/finder.md`, `docs/ui/styles.md`, `docs/ui/analysis.md`, and `USER_GUIDE.md`.
- **Validation**: Python compilation clean; targeted response chart tests passed; full test suite: **242 passed, 0 failed, 0 skipped**; `git diff --check` clean.

## 0.18.22 (2026-09-23)

- **Bass Match sidebar**: removed the Guided setup scenario selector and the
  Target enclosure heading in both Simple and Advanced mode. Enclosure cards
  now start directly below the brief controls, leaving more space for manual
  parameters. Updated the UI contract and user guide.
- **Validation**: targeted Simple/Advanced Streamlit AppTest passed; full active
  suite: **242 passed, 0 failed, 0 skipped**. Python compilation passed.

## 0.18.21 (2026-09-23)

- **Repository contracts**: added the seven missing per-module documents;
  synchronized state pinning, save-status labels, active-load metrics, optimizer
  credibility limits, startup behavior and the UI/module index. Historical
  commits are unchanged; this reconciles the current tree.
- **Hot reload**: measurements and billing now participate in source-change
  reload, with billing following SaaS and measurement exports rebound by the
  acoustic facade.
- **Crawler separation**: removed Makefile commands pointing to absent crawler
  scripts and the obsolete local crawler-registry test. Retained crawler guides
  identify their separate workspace. `make test-catalog` remains the strict
  local data gate; `make test-contracts` checks module documents, local command
  paths and reload coverage/behavior, also included in the active suite.
- **Storage documentation**: corrected the promotion/rollback description:
  batches are not an atomic full release and pointer rollback does not restore
  historical driver documents.
- **Validation (2026-09-23)**: `.venv/bin/python tests/test_all.py`:
  **242 passed, 0 failed, 0 skipped**; acoustic smoke: **14 passed**;
  repository contracts: **3 passed**; billing unittest suite: **10 passed**;
  storage boundary runner: **17 passed**. Streamlit startup AppTest, Python
  compilation, version consistency (0.18.21) and `git diff --check` passed.
- **Outstanding data gate**: `tests/test_catalog.py` fails on 11 duplicated
  Eminence names. A read-only inspection also found 101 invalid/missing required
  fields across 52 raw rows. Catalog records and validation thresholds were
  preserved; source review belongs to the crawler workflow. See
  `docs/catalog-consistency-audit.md`.

## 0.18.20 (2026-09-23)

- **Bass Match — Candidate Pool Auto-Open, Complete Simple Mode Filters, Driver Pinning & Direct Simulation in Box Design**:
  - Candidate pool expander (`finder_candidate_pool_expander`) now starts expanded by default when opening Bass Match (`expanded=True`), presenting the full scrollable driver catalog immediately rather than leaving an empty screen.
  - Complete library filters in Simple mode: removed the filter-stripping restriction so Provenance, Manufacturer, Size, Class, and Price filters are all available with Advanced mode off.
  - Driver Pinning across filter changes: selected driver(s) in the candidate pool remain pinned at the top of the pool even when subsequent filter modifications would normally exclude them (`_filter_driver_preset_names` with `pinned`, `_sync_pinned_from_library_table`).
  - Direct simulation in Box Design without running Bass Match:
    - Selecting 1 driver provides a primary action to open the driver directly in Box Design with its suggested alignment (`finder_use_library_driver`).
    - Selecting multiple drivers provides a primary action to simulate all selected candidates together in Box Design comparison tabs (`finder_use_library_driver_multi`), auto-aligning and simulating each driver with overlaid responses.
    - Added dedicated unpin actions for single and bulk selections.
  - Synchronized documentation across `docs/ui/catalog.md`, `docs/ui/finder.md`, `docs/ui/app.md`, `docs/deploy-cloudrun.md`, `README.md`, `pyproject.toml`, and `VERSION`.
  - Full active suite: **239 tests passing, 0 failures, 0 skipped**.

## 0.18.19 (2026-09-23)

- **UI & Layout — Decluttering, Visual Noise Reduction & Clean CAD Layout**:
  - Streamlined Bass Match hero brief card into a clean single-line flex row (`.bass-match-brief-row`) combining primary enclosure specs, optimization objective, and candidate readiness count pill on one horizontal bar.
  - Removed wordy, chatty subtitles ("Find drivers matching your design constraints.") and diagnostic jargon.
  - Positioned the prominent full-width "Run Bass Match" green CTA button directly inside the brief card for instant clarity and zero vertical scrolling.
  - Re-architected sidebar mode captions from long explanatory sentences ("Simple mode · guided scenario, load, volume and goal. Enable Advanced for full controls.") to concise, elegant labels ("Simple mode" / "Advanced mode").
  - Removed redundant instructional caption under load buttons ("Toggle the loads you want to compare. At least one must stay active.").
  - Suppressed engine/API-only topologies note in Simple mode, keeping it reserved strictly for Advanced evaluation.
  - Eliminated artificial single-tab button headers in the sidebar (`Search brief`) using CSS `:not(:has(button:nth-of-type(2)))`, delivering a pure, single-panel experience.
  - Compacted alert containers (`[data-testid="stAlertContainer"]`) and expander metrics for quiet, professional CAD aesthetics.
  - Full active suite: **238 tests passing, 0 failures, 0 skipped**.

## 0.18.18 (2026-09-22)

- **UI & Layout — Viewport Height Optimization, Overlap Fix & High Legibility**:
  - Fixed WebKit / Chrome flex `aspect-ratio` height-collapsing bug on `<button>` elements in `src/ui/styles.py` that previously caused Row 2 load cards to render directly on top of Row 1.
  - Re-architected sidebar width and containment (`width: 24.5rem` / 392px, `box-sizing: border-box`, `padding: 0 0.9rem`) to completely eliminate right-edge horizontal clipping on load cards, steppers (`+`/`-`), select boxes, and version labels.
  - Scaled up typography hierarchy across all surfaces for crisp legibility: widget labels (`0.96rem` main, `0.94rem` sidebar), captions (`0.88rem` with high-contrast `0.85`), metric labels (`0.88rem`, `#cbd5e1`) and values (`1.25rem`, `#ffffff`), removing the legacy `0.70rem` active load metric label shrink.
  - Optimized acoustic response chart height to `320px` in `src/ui/analysis.py` with enhanced axis typography (`labelFontSize=12`, `titleFontSize=13`), fitting the entire CAD telemetry metrics panel and controls cleanly within standard 900p / 1080p viewports without vertical scrolling.
  - Visually verified rendering on Google Chrome across all pages and views: Box Design (DCCAV, Bass reflex, Sealed, BP4, BP6, BP8, Infinite baffle), analysis tabs (Response, Excursion, Impedance, Ports, Group Delay, Atlas), Bass Match Search Brief and Results, Projects, and Explore.
  - Synchronized documentation across `docs/ui/styles.md`, `docs/ui/analysis.md`, `docs/ui/app.md`, and `docs/deploy-cloudrun.md`.
  - Full active suite: **238 tests passing, 0 failures, 0 skipped**.

## 0.18.17 (2026-09-22)

- **Project Management — Multi-Selection, Batch Trash & Batch Restore**:
  - Added checkboxes on every project card in the Manage Projects workspace for multi-project selection.
  - Added a responsive batch action bar with `Select all`, `Deselect all`, selection counter (`N of M selected`), and a `🗑️ Delete (N)` popover confirmation button to move multiple projects to Trash simultaneously.
  - Automatic safe detachment if the active open project is included in the batch deletion.
  - Added matching multi-select and bulk restoration (`♻️ Restore (N)`) in the Trash tab.
  - Maintained full backward compatibility for single-project Open, Duplicate, and Trash actions.
  - Synchronized documentation in `docs/ui/projects.md`.
  - Full active suite: **238 tests passing, 0 failures, 0 skipped**.

## 0.18.16 (2026-09-22)

- **Project Management — Startup Resume & Duplicate Name Protection**:
  - Eliminated automatic generation of orphan "Untitled project" draft records upon application launch and browser reloads: clean app startup automatically resumes the user's most recent active cloud project via `_resume_last_cloud_project()`, restoring parameters, cloud project ID, and saved engineering workspace.
  - Guarded autosave against saving clean blank drafts on initial load when no edits have occurred.
  - Enforced tenant-wide project name uniqueness across active projects: duplicate project names (case-insensitive) are strictly forbidden in header rename popovers, Manage Projects rename, new project creation, and file imports via `_is_project_name_taken()`.
  - Backend project stores (`InMemoryProjectStore`, `FirestoreProjectStore`, `InMemoryPrivateStore`, `FirestorePrivateStore`) enforce uniqueness on non-placeholder names, raising `ProjectDuplicateNameError` (classified as `kind="duplicate"`). Placeholder names (`Untitled project`, `Bozza`, `Draft`, etc.) remain exempt.
  - Project duplication automatically appends unique suffixes (`(Copy)`, `(Copy 2)`), and file imports safely disambiguate existing project names.
  - Synchronized documentation in `docs/ui/projects.md`, `docs/saas.md`, `docs/storage/private_store.md`, and `docs/ui/app.md`.
  - Full active suite: **237 tests passing, 0 failures, 0 skipped**.

## 0.18.15 (2026-09-22)

- **Optimization — Deep Multi-Start Global Box Search & Revision 9**:
  - Resolved discrepancy between fast Bass Match ranking searches and interactive Box Design optimization (such as DCCAV Max Extension on HiVi B3N) where local search previously got trapped in shallow suboptimal basins (`57.4 Hz` in `11.1 L` with inverted chambers) instead of reaching the true deep optimum.
  - Bumped `OPTIMIZER_ENGINE_REVISION = 9` across `src/engine.py` and `src/ui/constants.py` so running Streamlit browser sessions automatically invalidate stale cached alignments in `session_state` and reload with the new deep engine, and Finder workers re-handshake.
  - Scaled interactive Box Design optimizer budget via `_BOX_DESIGN_OPTIMIZER_EVALUATIONS = 1000` and dual-path architecture (fast path $\le 120$ eval for bulk ranking, deep path $> 120$ with 200-point Halton sweep, multi-scale extension sniff points, and multi-start adaptive compass/pattern search across up to 5 spatially-diverse candidate basins).
  - Refined the 6th-order DCCAV/bandpass physical credibility boundary in `_score_alignment` and `response_sanity_warnings` from `0.50 * sealed_fc` to `0.45 * sealed_fc`, removing the artificial cliff barrier and allowing high-Qts drivers to reach $F_3 = 37.5\text{ Hz}$ ($< 38\text{ Hz}$, easily beating Bass Match's $41.1\text{ Hz}$) with compliant $2.46\text{ dB}$ ripple and clean physical checks.
  - Updated regression test `_check_dccav_deep_max_extension_finds_deep_optimum` in `tests/test_all.py`.
  - Synchronized documentation in `docs/engine.md`, `docs/ui/optimizer.md`, and `docs/ui/constants.md`.
  - Full active suite: **237 tests passing, 0 failures, 0 skipped**.

## 0.18.14 (2026-09-22)

- **UI — Bass Match Sidebar Enclosure & Filter Integration**:
  - Restored the 7-card illustrated enclosure topology grid (`_load_type_card_styles`) directly onto the sidebar canvas (always visible, no popover).
  - Non-advance (Simple) mode operates in a single unified tab (`Search brief`) with target enclosure, goal, and library filters (search preset, brand, size, class, price) directly visible without tab switching.
  - Advanced mode provides the three dedicated tabs (`Load type`, `Performance filters`, `Library filters`) for granular engineering controls.
  - Synchronized documentation in `docs/ui/app.md` and `docs/ui/styles.md`.
  - Full active suite: **236 tests passing, 0 failures, 0 skipped**.

## 0.18.13 (2026-09-22)

- **Bass Match UI/UX Transformation (Phases A–F)**:
  - **Single-row precision CAD application bar**: Consolidated project name popover, LED persistence badge, visibility selector, and secondary navigation (`Projects`, `Community`, `Account`) into a unified `2.1rem` baseline header, eliminating vertical jitter and horizontal misalignment.
  - **Preserved brand identity**: Re-anchored the iconic illustrated Bass Match and Box Design mode selectors in the sidebar with active glowing states.
  - **Sidebar workflow**: The 7-card illustrated enclosure topology grid is restored and always visible directly on the sidebar canvas (no popovers). Non-advance mode operates in a single unified tab (`Search brief`) with target enclosure, goal, and library filters directly visible without tab switching; Advanced mode expands into three dedicated tabs (`Load type`, `Performance filters`, `Library filters`).
  - **Compact pre-run CAD telemetry brief (Phase D)**: Replaced disparate headers and multi-box grids with a cohesive telemetry canvas (`.bass-match-hero-header`, `.bass-match-spec-line-primary`), progressive disclosure for detailed constraints inside `Search details ▸`, and hidden tablist header for sequential workflow.
  - **Results-first state & seamless return (Phase E)**: Full results table visual dominance, compact two-tier engineering results header (`.bass-match-results-summary`), race-condition-free `✏️ Edit search` return flow, and context-sensitive Box Design handoff toolbar (`Open this design in Box Design →` / `Compare N designs in Box Design →`).
  - **Visual polish & cohesion (Phase F)**: Eliminated loud uppercase text-transforms across metrics and constraint labels, softened multiselect filter tags into dark translucent surfaces, and refined input hover states to clean neutral highlights.
  - Full active suite: **236 tests passing, 0 failures, 0 skipped**.

## 0.18.12 (2026-09-21)

- **Studio entry rules**: Projects and Explore are no longer the generic landing
  page. A no-context visitor sees a minimal **Studio** start screen (Find the
  right driver → Bass Match, Design with a driver → Box Design, recent projects
  secondary); a returning user resumes the last engineering workspace (session
  memory, then the most recent cloud project's saved `workspace_mode`); known
  intent (`?view=`, `?d=`, `?p=`) always routes straight to its workspace.
  Opening a saved project resumes its own engineering workspace instead of
  hardcoding Box Design. `_STUDIO_WORKSPACE`, `_render_studio_start`,
  `_last_cloud_workspace` and `_resume_last_engineering_workspace` implement the
  contract. Full suite: 236 tests passing, no failures.

## 0.18.11 (2026-09-21)

- **UI**: restored the 0.18.9 sidebar graphics. Bass Match and Box Design are
  full-image tabs again in the technical sidebar (the red/blue artwork),
  replacing the compact text navigation added in 0.18.10. Manage Projects
  moves back into the collapsed Account panel, which keeps billing, community
  and sign-out. `?view=` deep links and the Phase B save/visibility/Untitled
  behavior are unchanged. Full suite: 234 tests passing, no failures.

## 0.18.10 (2026-09-21)

- **UX — Phase B**: shared Projects / Bass Match / Box Design navigation,
  compact project name/rename, acknowledged save status and visibility.
  Authenticated Untitled projects autosave without a naming prerequisite;
  direct `view=bass-match` / `view=box-design` links retain intent. Opening
  another project flushes pending work and stays put if saving fails.
- **Publication**: owner/tenant-scoped association reuses existing publication
  links. Public/Unlisted access changes do not publish private edits; explicit
  updates retain immutable versions. Private withdraws all associated links,
  including old duplicates, and blocks public reads, versions, embeds and clones.
- **Docs/Test**: synchronized UI/storage docs, README, index and version metadata;
  added project identity, navigation, visibility and save-failure regressions.
  Physics and billing policies are unchanged. Full validation completed with
  234 tests passing and no failures.

## 0.18.9 (2026-09-20)

- **Data (Fix 1 — crawler)**: `tools/crawl_thiele_small.py` no longer derives a
  missing `Sd` from the **voice-coil** diameter for cone drivers. A published
  nominal frame diameter is consumed first (at 80 % of the frame,
  `NOMINAL_FRAME_PISTON_RATIO`), the voice-coil area is allowed only for dome
  drivers at or above `DOME_VOICE_COIL_MIN_FS_HZ` (400 Hz), a low-`Fs` cone with
  no usable evidence is rejected instead of given an impossible area, and a
  record whose `Sd` cannot coexist with its declared nominal diameter is marked
  `website_fields.quality_status = rejected_size_sd_conflict` instead of being
  published. Every derived `Sd` now records its formula in
  `website_fields.derivations.sd_cm2`.
- **Data (Fix 2 — catalog)**: added `load_forge_crawler`'s
  `tools/repair_sd_integrity.py`, which repairs provably wrong `Sd` values on
  independent evidence only (Vas+Cms identity, corroborated decade/unit rescale,
  or the published frame size for values recognisable as the voice-coil area or
  below the 1 cm² physical floor), records `field_corrections`/`derivations`,
  refreshes dependent fields, is idempotent and writes
  `data/sd_integrity_repair_report.json`. Applied to the proprietary catalog:
  **80 rows corrected** (43 voice-coil area, 32 physics identity, 5 m²→cm² unit
  errors) and propagated with `tools/sync_to_official_db.py`. Audit deltas:
  `size_sd_mismatch` 284 → 210, `declared_size_sd_mismatch` 177 → 116.
- **Data (Fix 3 — runtime)**: `resolved_nominal_size_in()` never lets an
  implausible `Sd` overwrite a manufacturer-published nominal diameter; the
  published size stays and the conflict is exposed as
  `DriverPresetInfo.size_sd_conflict`. `driver_data_coverage()` reports it as a
  `Size/Sd` gap and never returns `Complete`; the ranked table shows ⚠ and the
  Box Design driver panel explains that the stored `Sd` is used and asks to
  verify the datasheet. Serialized preset caches now embed
  `_PRESET_CACHE_VERSION`, so a loader-semantics change can no longer be served
  from a stale `.cache.pickle` in a long-lived Streamlit process. Finder worker
  protocol revision bumped to 3 for the new payload field.
- **Docs/Test**: updated `docs/presets.md`, `docs/ranking.md`,
  `docs/crawl_thiele_small.md`, `docs/catalog-consistency-audit.md`,
  `docs/ui/{app,catalog,finder}.md` and the crawler's
  `docs/catalog-unit-review.md`; added `docs/architecture-pipelines.md`
  (runtime/data/publishing/release/price/SaaS/ops pipelines, repo boundaries and
  target-vs-real infrastructure); added coverage/published-size regression tests
  plus crawler tests for the Sd derivation order and the conflict flag.
- **Ops**: `tools/promote_catalog_release.py` gained an opt-in `--drop-invalid`.
  Candidates that fail the physics gate still abort the release by default;
  with the flag they are omitted and their names/count are recorded in the
  Firestore release metadata (`omitted_invalid_drivers`), so a reviewed
  omission is auditable instead of silent. The 48 Ground Zero records without
  a usable `Re` (which the simulator cannot load either) were omitted this way.
- **Ops (Firestore)**: the repaired catalog was promoted to the runtime
  catalog in project `civic-radio-502611-i8` database `(default)` (the only
  provisioned database; the `lf-catalog-runtime` name in the target
  architecture does not exist yet) as release `manufacturer-20260920`:
  **10,998 drivers**, `approved_by playloud79@gmail.com`, 49 unsimulatable
  records omitted and recorded in the release metadata. The candidate is the
  crawler staging catalog, which yields exactly the same driver count as the
  previous release, so the Sd repair ships without any catalog regression.
- **Test**: the `Crawler release...` fixture now points the mandatory
  URL-contract guard at an isolated fake deploy checkout and asserts a `safe`
  guard report, instead of comparing a one-driver fixture against the real
  published slug index (9,104 spurious retirements). The guard's safe/unsafe/
  allow-removal behaviour stays covered by
  `load_forge_crawler/tests/test_url_guard.py`.
- Validation: `.venv/bin/python tests/test_all.py` — **230 passed, 0 failed,
  0 skipped**; `--fast` — **142 passed, 0 failed**;
  `load_forge_crawler`: `.venv/bin/python -m unittest discover -s tests` —
  **60 passed**; Streamlit AppTest and `git diff --check` clean.

## 0.18.8 (2026-09-16)

- **UI**: show all active search constraints directly on the Run Bass Match
  page. A Show disabled constraints toggle reveals Off/Any/N/A values without
  changing the search; only prefilter diagnostics remain collapsed.
- **Docs/Test**: update user/module guides, release metadata and the Finder
  AppTest for default active-only and expanded constraint summaries.
- Validation: `.venv/bin/python tests/test_all.py` — **229 passed, 0 failed,
  0 skipped**; UI compilation, version consistency and `git diff --check` passed.

## 0.18.7 (2026-09-16)

- **UI**: split Bass Match setup and results into main-area Run/Results tabs.
  Completed scans open Results automatically; invalidating search-input changes
  return to Run. Hidden setup and catalog controls are not rendered on Results.
- **UI**: replace the large selection card with a compact toolbar and expand
  the ranked table to 680 px. Run diagnostics move below the table.
- **Docs/Test**: update module and user guides, release metadata and AppTests
  for tab transitions, selection persistence and the Box Design handoff.
- Validation: `.venv/bin/python tests/test_all.py` — **229 passed, 0 failed,
  0 skipped**; UI compilation, version consistency and `git diff --check` passed.

## 0.18.6 (2026-09-16)

- **UI**: Finder results guide users through Run → Select designs → Open Box
  Design, with explicit checkbox instructions, selected-design summaries and
  a prominent primary Open/Compare action for one to eight designs.
- **UI**: completed-run statistics move into a collapsed Run details panel;
  the Run action becomes secondary once results are available.
- **Fix**: refresh the displayed version from VERSION on each app rerun so
  release bumps appear without restarting the Streamlit process.
- **Docs/Test**: synchronized Finder and style documentation; checked empty,
  single, multiple, over-limit and cleared selections plus restored results.
- Validation: `.venv/bin/python tests/test_all.py` — **229 passed, 0 failed,
  0 skipped**; UI Python compilation and version consistency checks passed.

## 0.18.5 (2026-09-16)

- **UI**: the Box Design launch is back where it is visible: the
  `Open this design in Box Design` / `Compare N designs in Box Design` button
  now sits in a slim toolbar directly above the ranked table — contextual
  selection hint on the left, compact emerald-outline pill pinned right — so
  it never reads as a second Run button. It reads the selection recorded by
  the previous interaction, so it enables as soon as a row is ticked; a new
  run clears the stale selection.
- **UI**: the main header is compact. Project name plus cloud-save status,
  user, plan and credit balance collapse into a single summary line; billing,
  Manage Projects, community and Sign out move into the collapsed
  `⚙️ Account & projects` panel (stable keys unchanged). CSV export stays a
  plain download action under the table.
- **Docs/Test**: updated `docs/ui/finder.md`, `docs/ui/projects.md`; the
  Finder workspace AppTest now asserts the launch sits above the table and the
  compact header panel is present.
- Validation: fresh full suite **229 passed, 0 failed, 0 skipped**.

## 0.18.4 (2026-09-16)

- **UI**: Bass Match always surfaces the work it performed. The last-run
  statistics render as an emerald "Simulation work performed" panel with four
  tiles (seek time, simulations, acoustic solves, credits) and the per-load
  breakdown, placed directly between the Run action and the ranked table.
- **UI**: action hierarchy is explicit. `Run Bass Match` is the only primary
  button; `Open this design in Box Design` / `Compare N designs in Box Design`
  is always secondary inside the styled `bass_match_result_actions` container
  (neutral outline, emerald hover), and CSV export is a plain download action.
- **UI**: the ranked results table is taller (560 px) so matches keep the
  workspace below the work panel.
- **Docs/Test**: updated `docs/ui/finder.md` and `docs/ui/styles.md`; the
  Finder workspace AppTest now asserts the visible work panel and the
  primary/secondary action split.
- Validation: fresh full suite **229 passed, 0 failed, 0 skipped**.

## 0.18.8 (2026-09-16)

- **UI**: Bass Match is results-first. The brief is now a single compact row
  (title plus pre-qualified / ready-simulations / run-cost metrics) and every
  constraint, skipped/duplicate counter and profile detail moved into the
  collapsed "All constraints & search details" expander, so the ranked table
  sits just below the Run action instead of below several diagnostic panels.
- **UI**: the results header is one line (`N matches · loads · box · goal`)
  next to `Rank by`; the open/compare CTA and CSV export sit directly under the
  table; the long scan diagnostics (prefilter counts, seek time, per-load
  breakdown, per-brand totals) collapsed under "Scan diagnostics".
- **Docs/Test**: updated `docs/ui/finder.md` and the function reference; the
  Finder AppTest now asserts the single constraint grid, the collapsed details
  and collapsed diagnostics panels.
- Validation: fresh full suite **229 passed, 0 failed, 0 skipped**.

## 0.18.2 (2026-09-16)

- **UI**: the transparent Streamlit header no longer swallows clicks. Since
  0.18.0 the header was kept transparent instead of `display: none` so the
  sidebar opener stayed reachable, but its fixed bar covered the first main-area
  widgets: the account row, its subscription/billing button and the logout
  button were visible yet unclickable (no pointer cursor). The header now sets
  `pointer-events: none` and only `stExpandSidebarButton` re-enables
  `pointer-events: auto`.
- **Docs/Test**: documented the click-through header in `docs/ui/styles.md`;
  added a CSS regression test asserting the pointer-events guard.
- Validation: fresh full suite **229 passed, 0 failed, 0 skipped**.

## 0.18.1 (2026-09-16)

- **Auth**: sign-out can no longer be silently undone by the Google SSO
  session. Google stopped publishing `end_session_endpoint`, so `st.logout()`
  ends only the Load Forge session while the browser keeps the Google identity;
  the production `[auth]` secret now sets `client_kwargs.prompt = "consent"`,
  forcing Google’s confirmation screen on every sign-in.
- **Docs**: documented the `prompt = "consent"` requirement and the need to
  remount the secrets volume with a new Cloud Run revision in
  `docs/deploy-cloudrun.md`; updated `docs/ui/account.md`.
- Validation: fresh full suite **228 passed, 0 failed, 0 skipped**.

## 0.18.0 (2026-09-15)

- Kept the original illustrated Load Forge navigation, load cards and community artwork.
- Authenticated users now land on their own project list after login. Projects can be searched and sorted; opening one queues its state safely and continues in Box Design.
- Secondary project actions (duplicate and trash) are grouped under **More**. Current-project export, sharing and revision tools remain available in a collapsed panel.
- Added tenant/user-aware project-summary caching and preserved the existing Finder brief identity while moving secondary diagnostics behind an expandable details section.
- Validation: fresh full suite **228 passed, 0 failed, 0 skipped**; 14 acoustic-load smoke tests passed.

## 0.17.7 (2026-09-15)

- **UI**: the Finder results table and its CSV download now show the nominal
  `Le mH` — the inductance used by the Max Le filter and the impedance
  simulation — whenever at least one candidate has a positive value. The
  `Le10k mH` key stays internal and is never displayed.
- **Docs/Test**: updated `docs/ranking.md` and `docs/ui/finder.md`; the seeded
  Finder table test now asserts `Le mH` is visible and `Le10k mH` is absent.
  Fresh full suite: **227 passed, 0 failed, 0 skipped**.

## 0.17.6 (2026-09-15)

- **UI**: the Finder results table and its CSV download no longer expose the
  `Le10k mH` column, even when a candidate carries a positive published 10 kHz
  inductance. `Le10k` remains an internal ranking/coverage field and is still
  accepted in Box Design, but it is not substituted for the nominal `Le` used
  by the constraint and the simulation.
- **Docs/Test**: updated `docs/ranking.md` and `docs/ui/finder.md`. Fresh full
  suite: **227 passed, 0 failed, 0 skipped**.

## 0.17.5 (2026-09-15)

- **Accounts**: new durable `FirestoreCredentialStore` for production email
  sign-up. When the Firestore backend is active (Cloud Run),
  `create_credential_store` persists one `credentials/{email}` document in the
  private database with a salted scrypt hash, atomic duplicate detection and
  no plaintext passwords, so accounts survive restarts and multi-instance
  routing. Memory/local modes keep the SQLite `LocalAccountStore`.
- **Ops**: added `tools/adopt_guest_projects.py` to copy projects left by
  removed anonymous guests into a real account (dry-run default, idempotent,
  source never modified); adopted the single legacy guest project `econowave`.
- **Docs/Test**: updated `docs/saas.md`, `docs/ui/account.md` and the
  multi-database runbook; added a credential-store regression test. Fresh full
  suite: **227 passed, 0 failed, 0 skipped**.

## 0.17.4 (2026-09-15)

- **Access**: every visitor must now sign in with an email account, Free plan
  included. Anonymous guest identities were removed; the legacy
  `LOAD_FORGE_ANONYMOUS_ACCESS` flag is ignored and no longer appears in
  `SaaSSettings`.
- **Registration**: the alpha invite code was removed from the email/password
  sign-up form, so any valid email address can create a Free account.
- **Docs/Test**: updated `docs/ui/account.md`, `docs/saas.md` and
  `docs/deploy-cloudrun.md`; tests now assert the gate is always rendered and
  that the invite field is gone. Fresh full suite: **226 passed, 0 failed,
  0 skipped**.

## 0.17.3 (2026-09-15)

- **Fix**: the Finder results table no longer shows the `Le10k mH` column just
  because a catalog record carries a `0.0` placeholder. Non-positive `Le10k`
  values are treated as missing in the ranking row (`NaN`) and in the driver
  coverage badge, so the optional column only appears when a candidate has a
  real published 10 kHz inductance. The Max Le constraint is unchanged and was
  already acting on nominal `Le` only.
- **Docs/Test**: documented the missing-value rule in `docs/ranking.md`.
  Fresh full suite: **226 passed, 0 failed, 0 skipped**.

## 0.17.2 (2026-09-13)

- **Anonymous studio access**: new `LOAD_FORGE_ANONYMOUS_ACCESS` setting
  (default off, allowed on Cloud Run). When enabled, unauthenticated visitors
  enter the workspace directly instead of the blocking sign-in gate. Each
  Streamlit session gets its own ephemeral guest identity
  (`guest+<uid>@loadforge.local`, Free plan) so saved projects never leak
  between visitors; signing in stays available for persistent accounts.
- **Tests**: added settings and UI AppTest coverage; the auth-only and
  local-account gates are unchanged when the flag is off.

## 0.17.1 (2026-09-11)

- **Fix**: creating a project no longer discards the active design or Bass
  Match run. "New Project" now saves the current work into the named project
  (detach from the previous cloud record + immediate autosave). The old
  clean-slate behaviour is an explicit "Start from a blank design" checkbox in
  the naming prompt.
- **Docs/Test**: documented the new-project invariant in
  `docs/ui/projects.md`; replaced the reset-on-create regression with
  `_check_ui_new_project_preserves_work`. Full suite: **225 passed, 0 failed,
  0 skipped**.

## 0.17.0 (2026-09-11)

- **Refactor**: split the 15.6k-line `ui_app.py` monolith into a thin entry
  point plus the `src/ui` package (`runtime`, `constants`, `styles`, `state`,
  `catalog`, `finder`, `optimizer`, `analysis`, `projects`, `account`,
  `app`). Behavior is unchanged: module-qualified cross-references keep
  Streamlit hot-reload safe, and functools caches are cleared per run to
  preserve the original per-script-run scope.
- **Docs/Test**: added `docs/ui.md` and `docs/ui/*.md`; updated `AGENTS.md`
  and `docs/INDEX.md`; tests patch owning modules and source assertions read
  the full UI bundle. Fresh full suite: **224 passed, 0 failed, 0 skipped**.

## 0.16.21 (2026-09-10)

- Rebalance the load-card diagrams: keep the uniform enclosure height from
  0.16.20 but raise it to 56% of the card, so the drawings are as large as the
  0.16.19 set while staying visually equal. Only the widest arrow span
  (Bandpass 6th order) reaches the card edge.
- Fresh active suite after the last edit: **224 passed, 0 failed, 0 skipped**.

## 0.16.20 (2026-09-10)

- Give every load-card diagram the same visual size: each drawing is scaled so
  the enclosure/driver (the dark structure, arrows excluded) has the same
  height in every card, centered on the structure rather than on the arrow
  span. Cards keep their size and the diagram fills the square with a small
  uniform margin.
- Fresh active suite after the last edit: **224 passed, 0 failed, 0 skipped**.

## 0.16.19 (2026-09-10)

- Enlarge the load-card diagrams while keeping the card size unchanged. The
  seven load icons are re-normalized: each drawing is cropped to its content,
  centered on the card background with a uniform ~6% margin, and drawn at the
  full card size, so the diagram fills more of the square and every card shows
  the same visual weight.
- Fresh active suite after the last edit: **224 passed, 0 failed, 0 skipped**.

## 0.16.18 (2026-09-10)

- Reorganize the chrome so the sidebar commands stay visible without scrolling:
  the account row (name · plan · credits, **Subscriptions & Credits**,
  sign-out) and the project row (project name or **Project name required**,
  cloud save status, **Manage Projects**, **Explore Community**) now live at
  the top of the main screen. The brand logo is smaller and the **Advanced
  mode** toggle moved to the bottom of the sidebar, leaving the sidebar to the
  workspace commands.
- Regression tests updated for the relocated project/community controls.
- Fresh active suite after the last edit: **224 passed, 0 failed, 0 skipped**.

## 0.16.17 (2026-09-10)

- Restrict reruns to what is strictly necessary. The design analysis tabs
  (Response, Excursion, Impedance, Ports, Group Delay, Atlas) and the Bass
  Match candidate pool now run as Streamlit fragments, so switching chart tabs
  or opening the pool re-renders only that section instead of reloading the
  page and moving the scroll. Applying a port optimization keeps an app-scope
  rerun because it changes data rebuilt by the full run; pin/zoom actions stay
  fragment-scoped.
- Fresh active suite after the last edit: **224 passed, 0 failed, 0 skipped**.

## 0.16.16 (2026-09-10)

- Stop the sidebar scroll jump when switching tabs. Bass Match and Box Design
  now render all sidebar panels together and no longer force a rerun on tab
  change, so switching **Load type**, **Performance filters**, **Library
  filters**, **Driver**, **Load Selection** or **Enclosure Parameters** is a
  client-side action that keeps the sidebar scroll position. Hidden panels
  also keep their widget state instead of being destroyed and rebuilt.
- Regression tests updated for the always-rendered panels.
- Fresh active suite after the last edit: **224 passed, 0 failed, 0 skipped**.

## 0.16.15 (2026-09-10)

- Stop avoidable full-page reruns that moved the scroll position. The Bass
  Match run now fills its statistics box in place through an `st.empty()`
  placeholder instead of calling `st.rerun()`, so brief, statistics and
  results update in one pass. Applying an **Explore alternatives** box no
  longer reruns the page either: the box widgets render later in the same pass
  and pick up the new state directly.
- Fresh active suite after the last edit: **224 passed, 0 failed, 0 skipped**.

## 0.16.14 (2026-09-10)

- Make Simple mode truly minimal. Bass Match Simple now keeps only the guided
  scenario, load cards, maximum volume, optimization goal and basic library
  filters (search, manufacturer, price). Driver configuration, comparison
  voltage, F3/MOL/SPL/ripple/excursion/delay constraints,
  provenance/size/class filters and data coverage are Advanced-only; hidden
  filters are reset so they cannot silently change results. Box Design Simple
  keeps the driver preset, load cards and box strategy, with voltage, series
  resistance, optimization constraints and driver configuration in Advanced.
- Fresh active suite after the last edit: **224 passed, 0 failed, 0 skipped**.

## 0.16.13 (2026-09-10)

- Make Simple/Advanced mode visibly different: the active mode is captioned
  directly under the sidebar toggle, and in Advanced mode the expert sections
  (**Advanced evaluation**, **Advanced driver filters**, **Advanced driver
  parameters**) open immediately instead of staying collapsed. The toggle
  already switched the controls; only the visual change was too subtle.
- Regression test asserts the mode caption and the Advanced evaluation
  section.
- Fresh active suite after the last edit: **224 passed, 0 failed, 0 skipped**.

## 0.16.12 (2026-09-10)

- Remove the truncated completion toast from Bass Match. The persistent run
  statistics box and the results caption already report completion and timings,
  so the toast only overlapped the brief and hid its elapsed time behind a
  "view more" link.
- Fresh active suite after the last edit: **224 passed, 0 failed, 0 skipped**.

## 0.16.11 (2026-09-10)

- Refresh the persisted Bass Match run-statistics box as soon as a scan
  completes. The box is rendered before the clicked run executes, so it
  previously kept the previous run's seek time and per-load numbers while the
  results below already showed the new ones; a post-run rerun now renders the
  whole page from the completed run state.
- Regression test runs two searches with different loads and asserts the box
  reports only the latest load.
- Fresh active suite after the last edit: **224 passed, 0 failed, 0 skipped**.

## 0.16.10 (2026-09-10)

- Show the Bass Match seek time broken down per load: usable/attempted
  candidates, evaluations per driver and elapsed seconds for each selected
  topology. This makes the adaptive budget visible (a DCCAV pass runs roughly
  twice the evaluations of a reflex pass) and distinguishes real search time
  from cache-served reruns with unchanged constraints.
- Fresh active suite after the last edit: **224 passed, 0 failed, 0 skipped**.

## 0.16.9 (2026-09-10)

- **Adaptive Finder optimizer budgets per topology**: evaluation limits now
  scale with the free axes (`overhead + per-axis × axes`) instead of a flat
  value — Standard 30–120 (Sealed 30, Bass reflex 50, BP4 70, BP6/DCCAV 90,
  BP8 120), Deep 60–240. No Cloud Run reduction; run statistics show the
  per-load budget range.
- **Deterministic global search phase**: a fixed Halton sweep over the full
  bounded domain (2–8 points by dimension, multi-axis loads only) runs before
  the local sniff, so the search can leave the starter basin without random
  choices. Determinism is covered by new regression tests.
- **Optimizer result cache**: bounded (512-entry), thread-safe memoization of
  complete optimizer briefs. Repeated Finder runs that change only
  post-simulation filters skip the expensive search;
  `invalidate_ranking_caches()` clears it.
- **Simple / Advanced sidebar mode** (Simple by default) with guided scenario
  presets (Home theater, Car SPL, Hi-Fi, Infinite baffle) and practical
  tooltips. Expert controls (search profile, evaluation grid, Mms/Le filters,
  T/S overrides) are hidden in Simple mode but keep applying.
- **Driver data coverage**: `driver_data_coverage()` plus `Data` / `Data %`
  badges in the ranking table and a per-field coverage panel in the Candidate
  library, so incomplete records are visible before a scan.
- **Forge Score clarified** as a heuristic health indicator that is never a
  default ranking criterion; comparisons stay on F3, MOL, excursion and
  impedance.
- **Engine/API-only waveguides declared**: transmission line, MLTL,
  quarter-wave, back-loaded horn and tapped horn are listed in the sidebar
  under **Engine/API-only topologies** and documented as non-interactive.
- **Explore alternatives**: `OptimizedAlignment.alternatives` exposes up to
  five buildable runner-up boxes (score, F3, volume, ripple, excursion) and
  Box Design offers one-click apply for each.
- Restore the local-SaaS registration test by supplying the alpha invite
  master token, so the full suite is green again.
- Fresh active suite after the last edit: **224 passed, 0 failed, 0 skipped**.
  Fast suite: **140 passed**; acoustic-load smoke: **14 passed**.

## 0.16.8 (2026-09-07)

- Reuse one account read per script run, invalidate it after credit/plan changes,
  and derive administrator access from exact configured identities rather than
  email substrings or the login allowlist. Existing stale admin flags are revoked.
- Refresh the cloud driver catalog in one background worker, retain the last
  successful snapshot during slow/failed reads, and atomically persist successful
  refreshes. Catalog revisions invalidate Finder eligibility and library metadata.
- Restore the two-second autosave timer without rebuilding the acoustic workspace.
  Render only active sidebar/project panels and reuse unchanged serialized response
  charts, preserving zoom, physics, comparison visibility and hidden parameter state.
- Restore five formerly short-circuited UI regressions; add account, catalog,
  autosave, chart-cache checks and smoke coverage for all five distributed loads.
- Warm offline AppTest workspace clicks over five repetitions: median Box Design
  0.267 s (previous review: 0.50–0.56 s), Bass Match 0.234 s (previous: 0.25–0.26 s).
  Browser rendering and real network latency are excluded. Account reads drop
  from 9/5 in authenticated Bass Match/Box Design to one per script run.
- Final fresh active suite: **217 passed, 0 failed, 0 skipped**. Additional
  validation: storage boundaries **17 passed**, billing **10 passed**.

## 0.16.7 (2026-09-07)

- **Dynamic Catalog Synchronization & Z-Bench Hardware Integration**:
  - **Dynamic Catalog Freshness & Automatic Invalidation**: Added `check_dynamic_catalog_freshness` in `src/presets.py` and exported through `src/acoustics.py`. Enforces a 60-second TTL on cloud Firestore queries and instantly invalidates memory caches if `catalog_proprietario.json` is modified locally or new drivers are uploaded via Z-Bench.
  - **Z-Bench Top Preference & Dropdown Placement**: Moved `_load_firestore_presets()` to index 0 of `_external_tiers()` and gave "Z Bench" highest precedence (priority 0) in `driver_preset_preference()`. Custom-measured drivers now appear immediately below built-in reference drivers at index ~30 in all dropdowns and selectors.
  - **On-Demand "🔄" Refresh Controls**: Added interactive refresh buttons beside the "Search preset" inputs in both Box Design (Driver tab) and Bass Match (Finder Library tab), enabling users to force-sync newly measured drivers from Z-Bench into the UI with one click.
  - **Catalog Synchronization**: Synced newly measured driver `Z Bench: ALIEXPRESS flat_sub_8_burned_in_36h` in `data/catalog_proprietario.json`.

## 0.16.6 (2026-09-07)

- **Comprehensive UI Alignment & Symmetrical Grid System**:
  - **Acoustic Topology Sidebar Cards**: Row 1 (direct radiators: Infinite Baffle, Sealed, Reflex) and Row 2 (compound loads: BP4, BP6, BP8, DCCAV) now dynamically scale to `st.columns(len(row_load_types), gap="small")`, eliminating the blank gap on row 1 and stretching both rows to 100% of the sidebar width.
  - **Label Height Normalization**: Fixed `.load-card-label` height to `1.7rem` with centered flexbox layout, ensuring multi-line labels (e.g. Infinite Baffle) and single-line labels align on the exact same baseline across cards.
  - **Bass Match Constraint Grid**: Switched `.finder-constraint-grid` to `repeat(auto-fill, minmax(9.75rem, 1fr))`, guaranteeing that trailing cards on row 4 maintain identical, uniform width with rows 1–3 rather than stretching irregularly.

## 0.16.5 (2026-09-06)

- **Modern Wide-Screen Billing Modal (Design Overhaul)**:
  - Replaced cramped 300px sidebar popover with a clean, spacious modal dialog (`@st.dialog`) with dark backdrop overlay.
  - Eliminated cluttered, multi-layered vertical radio buttons in favor of sleek, side-by-side comparative cards for **Hobby** (€3/mo) and **Pro** (€9/mo).
  - Integrated top segmented billing cycle toggle (`Monthly` vs `Yearly · Save up to 27%`) dynamically updating pricing in-place.
  - Formatted one-time credit packs into balanced 3-column pricing cards with direct Stripe Checkout links.
  - Highlighted full payment options in modal footer (Credit Cards, PayPal, Klarna, Satispay, Amazon Pay).
  - Sidebar layout remains completely stable and compact without pushing down speaker topology icons.

## 0.16.4 (2026-09-06)

- **Subscription-First Popover Hierarchy & Stripe PayPal Activation**:
  - Reordered billing popover tabs so **🚀 Subscriptions** appears as the primary, default active tab before **⚡ Credit Packs**.
  - Renamed billing CTA actions to explicitly prioritize subscriptions (`🚀 Subscriptions & Credits` and `🚀 Subscribe / Buy Credits`).
  - Enabled **PayPal** in the active Stripe Payment Method Configuration (`pmc_1UCbUfPgXf9081cT1q1NchR5`) for both recurring subscriptions and one-time pack checkouts.

## 0.16.3 (2026-09-06)

- **Hobby Subscription Tier & Social Community Project Freedom**:
  - Introduced the **Hobby Plan** at **€ 3 / month** (or **€ 29 / year**) with **60,000 monthly credits**, specifically designed for DIY builders and audio enthusiasts.
  - Reduced **Pro Plan** to **€ 9 / month** (or **€ 79 / year**) for **300,000 monthly credits** to provide a natural, accessible 3x progression.
  - **Unlimited Cloud Projects for All Tiers**: Removed project limits across all plans (`saved_projects = 999_999`) to nurture the public community library and social project sharing.
  - Adjusted one-time credit pack pricing to align with subscriptions (100k for € 5, 300k for € 12, 1M for € 29).

## 0.16.2 (2026-09-06)

- **10x Credits Scaling Across All Tiers**:
  - Scaled monthly free credits and credit packs by 10x to accommodate high-volume batch simulations:
    - **Free tier**: 10,000 monthly credits (previously 100).
    - **Starter pack (€9)**: 100,000 credits (previously 1,000).
    - **Pro pack / Pro tier (€19/mo)**: 300,000 credits (previously 2,500).
    - **Power pack (€49)**: 1,000,000 credits (previously 10,000).
  - Backward-compatible quota upgrade in `FirestoreUserAccountStore` and `FirestorePrivateStore`: existing accounts below the new quota automatically receive the difference upon next login or access.
- **English UI Localization & Instant In-Memory Balance Refresh**:
  - Enforced full English localization for all credit purchase popovers, checkout actions, and error banners across the application.
  - Hardened top-up actions to immediately reflect new credit balances in-memory before triggering `st.rerun()`, ensuring seamless immediate unblocking of batch scans.

## 0.16.1 (2026-09-06)

- **One-Time Credit Packs & In-App Credit Purchase**:
  - Implemented on-demand simulation credit packs (`1,000 Credits` · 9 €, `5,000 Credits` · 29 €, `10,000 Credits` · 49 €) in `src/billing.py`.
  - Added `create_credit_pack_checkout_session` using hosted Stripe Checkout in `mode="payment"` with dynamic `price_data` in EUR.
  - Added `sync_checkout_session` for instant, non-blocking client-side fulfillment when returning from Stripe Checkout.
  - Extended webhook processing for `checkout.session.completed` to credit user accounts automatically and atomically in Firestore.
- **Universal Credit Top-Up Buttons & Bass Match Integration**:
  - Added dedicated `⚡ Compra Crediti / Pro` button in the sidebar under user balance, always visible regardless of gateway state.
  - Integrated direct `⚡ Compra Crediti (X mancanti)` popover button directly inside the Bass Match insufficient credits banner with smart recommendation highlighting the required pack.
  - Provided immediate fallback top-up functionality for seamless testing and development before live Stripe credentials are provisioned on Cloud Run.

## 0.16.0 (2026-09-06)

- **Session Sign Out & Universal Logout Action**:
  - Added dedicated power/logout icon button (`⏻`) directly inside the sidebar authenticated user header with full tooltip guidance.
  - Added header "Sign out" button in the `Manage Projects` workspace for quick account switching.
  - Integrated `?logout=1` URL query parameter support for instant, clean session termination.
  - Hardened `_sign_out_saas` to cleanly clear local account session keys, project cache, and call OIDC `st.logout()` gracefully across all authentication modes.
- **Stripe Payments & Commercial Hosted Billing Milestone**:
  - Zero-liability hosted payment integration via Stripe Checkout and Stripe Customer Portal (`src/billing.py`).
  - Standalone FastAPI webhook microservice (`webhooks/main.py`) deployed on Google Cloud Run with cryptographic signature verification, idempotency tracking (`stripe_events`), and atomic Firestore synchronization.
  - Extended `UserAccount` with billing state (`stripe_customer_id`, `stripe_subscription_id`, `subscription_status`, `current_period_end`, `cancel_at_period_end`) and `has_pro_access()` gating.
  - Dynamic checkout toast notifications upon returning from Stripe Checkout (`?checkout=success` / `?checkout=canceled`).
- **Production Catalog Sanitation & Administrator Gating**:
  - Cleaned and consolidated proprietary manufacturer database to 9,849 verified, 100% simulatable presets.
  - Segregated foreign third-party aggregates (`LSDB`, `VituixCAD`, `Speaker Box Lite`) exclusively to administrator accounts (`_maintenance_allowed()`).
  - Integrated Firestore `rejected_records` quarantine repository with zero local footprint.

## 0.15.24 (2026-09-05)

- **Restricted Third-Party Catalogs (Admin Only)**:
  - Third-party aggregate databases (`LSDB`, `VituixCAD`, `Speaker Box Lite`) are now gated exclusively to administrator accounts (`_maintenance_allowed()`).
  - Regular users interact exclusively with the verified Load Forge proprietary catalog and Z Bench reference laboratory measurements.
  - Filter options in Bass Match / Finder, candidate pools, and Box Design preset selectors automatically enforce this restriction across user sessions.
- **Production Catalog Sanitation & Cloud Quarantine Repository**:
  - Cleaned and deduplicated the production proprietary catalog to 9,849 clean, unique, 100% simulatable presets.
  - Staged and quarantined 1,564 invalid, foreign aggregate, or redundant records directly in the Google Cloud Firestore `rejected_records` collection with audit categorization.
  - Maintained zero local staging files, managing the quarantine repository exclusively on Firestore.

## 0.15.23 (2026-09-02)

- **Community Project Build & Prototype Photo Upload**:
  - Added real enclosure/cabinet build photo upload (`jpg`, `jpeg`, `png`, `webp`) to project publishing workflows (Manage Projects and Community Sidebar).
  - Implemented client-side WebP optimization (`_process_project_cover_image`) producing lightweight data URIs (~20-50KB).
  - Rendered prototype cover photos seamlessly in Community 3-column build cards, Featured Spotlight hero banners, and technical project view pages.
  - Test suite: **205 passed, 0 failed, 0 skipped**.

## 0.15.22 (2026-09-02)

- **Ultra-Robust Driver Resolution & Non-Empty F3/MOL Community Metrics**:
  - Implemented `_resolve_driver_ts` with fuzzy matching, prefix stripping (`WEB:`, `LSDB:`, `SBL:`, `VCAD:`), and generic driver synthesis.
  - Guaranteed non-empty, accurate $F_3$ extension (Hz) and MOL/peak SPL (dB) across all legacy and live community builds.
  - Test suite: **205 passed, 0 failed, 0 skipped**.

## 0.15.21 (2026-09-02)

- **Dynamic On-The-Fly F3 and MOL/Peak SPL Resolution for Community Project Cards**:
  - Implemented automatic acoustic metric derivation in `extract_technical_summary` and `_derive_project_acoustic_metrics`.
  - Accurately computes and renders $F_3$ extension (Hz) and MOL/peak SPL (dB) across all community builds (including projects without pre-stored simulation metrics).
  - Test suite: **205 passed, 0 failed, 0 skipped**.

## 0.15.20 (2026-09-02)

- **Compact Load Type Icons with 2x2 Basic Project Value Grid**:
  - Rescaled load type diagrams to compact thumbnail icons (~46px) next to project title and topology badge.
  - Added clean 2x2 electroacoustic parameter grid (`DRIVER`, `VOLUME (Vb)`, `F3 EXTENSION`, `MOL / PEAK SPL`) on every Community project card.
  - Streamlined information hierarchy with author identity, direct `🚀 Fork` action, `📊 Tech` sheet, and `❤️ Like` interactions.
  - Test suite: **205 passed, 0 failed, 0 skipped**.

## 0.15.19 (2026-09-02)

- **Bambu Studio / MakerWorld Style Visual 3-Column Community Cards**:
  - Transformed Community Projects feed into a visual-first 3-column card grid inspired by MakerWorld / Bambu Studio model libraries.
  - Placed large schematic load-type illustrations at the top of each project card.
  - Streamlined card metadata: topology badge, project title, driver & electroacoustic specs summary, author identity, and direct Fork & Tech Sheet actions.
  - Test suite: **205 passed, 0 failed, 0 skipped**.

## 0.15.18 (2026-09-02)

- **Visual Load Type Illustrations and Clean Minimalist Community Projects Layout**:
  - Embedded schematic load type illustrations (`_LOAD_TYPE_IMAGES`) directly into each Community Project card and Spotlight showcase.
  - Streamlined the Community feed layout: removed redundant pill buttons, fake sidebar leaderboards, and noisy metrics clutter.
  - Refined project card information hierarchy: prominent load diagram, clean title, author & date, driver metadata, electroacoustic specs, and direct Fork / Tech Sheet actions.
  - Test suite: **205 passed, 0 failed, 0 skipped**.

## 0.15.17 (2026-09-02)

- **Frameless Full-Width Sidebar Integration with App Emerald Palette**:
  - Matched the button hue to the app's standard `#10b981` emerald green palette (160° hue).
  - Eliminated the outer rectangular button border and shadows (`border: none`, `box-shadow: none`), allowing the blueprint button artwork to span the full sidebar width cleanly without double framing.
  - Test suite: **205 passed, 0 failed, 0 skipped**.

## 0.15.16 (2026-09-02)

- **Faithful 1:1 Cyber-Blueprint Community HUD Button Image Conversion**:
  - Restored the original high-tech blueprint button raster artwork from ChatGPT with exact blueprint grid lines, technical tick marks, circular 3-avatar node halo, and chamfered polygon frame.
  - Converted the blue/cyan spectrum cleanly into glowing cyber-emerald green (`#00ff66` / `#10b981`) while preserving crisp white typography (`Explore`) and pure black background.
  - Integrated `assets/community_tab.png` into `ui_app.py` via cached base64 raster embedding with `background-size: contain`.
  - Test suite: **205 passed, 0 failed, 0 skipped**.

## 0.15.15 (2026-09-01)

- **Bass Match Seek Time & Scan Telemetry Display Resolution**:
  - Restored and enhanced real-time seek time, simulation throughput, and physical acoustic solves telemetry (`⏱️ Seek time: X.XX s (X.X ms/sim · XXX sim/s)`) in both the Bass Match brief container and directly in the results table header caption.
  - Formatted styled telemetry banner with emerald accent highlights and credits consumption breakdown.
  - Added regression assertions in `tests/test_all.py` (`_check_ui_batch_finder_results_and_applied_tabs`).
  - Test suite: **205 passed, 0 failed, 0 skipped**.

## 0.15.14 (2026-09-01)

- **Workspace Navigation & Admin Back-Button URL Query State Resolution**:
  - Resolved navigation lock in User Management (`admin_users=1`), Catalog Maintenance (`maintenance=1`), and Manage Projects workspaces by ensuring `_select_workspace()` and "← Back to app" buttons automatically clear route-locking query parameters (`admin_users`, `maintenance`, `explore`, `p`, `embed`).
  - Added dedicated "← Back to app" return button to `_render_manage_projects_workspace()`.
  - Added full automated AppTest coverage for User Management, Catalog Maintenance, and Manage Projects return flows in `tests/test_all.py` (`_check_ui_admin_and_project_back_navigation`).
  - Test suite: **205 passed, 0 failed, 0 skipped**.

## 0.15.13 (2026-09-01)

- **Immersive Cyber-Neon Community Dimension & Electroacoustic Social Hub**:
  - Transformed the Community page (`?explore=1`) into an immersive social engineering hub with cyber-neon glassmorphism UI, real-time live telemetry metrics (128+ verified builds, 3.8k+ simulations, 142.8 dB SPL max record, 86 audio designers), interactive category pills, and a dedicated Community sidebar.
  - Implemented the Featured Project Spotlight of the Week hero card with 1-click sandbox forking and deep technical spec sheet navigation.
  - Added rich interactive creator cards with author avatar initials, creator rank badges, electroacoustic monospace spec chips ($V_b, F_b, F_3, SPL$), interactive like toggles with session state persistence, forks counters, and responsive iframe embed code generator.
  - Hardened Firestore query handling in `src/storage/public_store.py` with automatic index error fallback to in-memory sorting, ensuring graceful operation when GCP composite indexes are unbuilt.
  - Integrated curated verified electroacoustic showcase presets across DCCAV, Bass Reflex, Bandpass 6th, Sealed, and Passive Radiator in `src/saas.py` (`curated_community_showcase_projects()`).
  - Designed and integrated the high-tech blueprint cyber-HUD Community transition button (`_render_hud_explore_community_button` with `Explore Community Prj` typography, triangular 3-avatar interconnected network node SVG, blueprint grid crosshairs, and glowing neon green `#00ff66` baseline).
  - Test suite: **204 passed, 0 failed, 0 skipped**.

## 0.15.12 (2026-09-01)

- **Phase 4 UI Brand/Price Extraction & Preset Formatting Vectorization**:
  - Replaced $O(N)$ sequential brand and currency scans with direct tier dictionary iterations, eliminating 15,553 python function calls per rerun.
  - Added `@lru_cache(maxsize=32768)` to `_driver_preset_family`, `_driver_preset_identity_fields`, `_driver_preset_display_label`, `_driver_preset_source`, and `_driver_preset_size` in `ui_app.py`.
  - Streamlined `driver_preset_info` and `get_driver_preset` lookups with zero-copy tier probing.
  - Benchmark: `all_preset_brands()` and currency extractions reduced from 1.88s to **< 2ms**; full UI AppTest runtime stabilized at **4.39s** (from > 30s timeout).
  - Test suite: **204 passed, 0 failed, 0 skipped**.

## 0.15.11 (2026-09-01)

- **Phase 3 Cold Startup Optimization & Safe Unpickling**:
  - Resolved `ModuleNotFoundError` during binary `.cache.pickle` unpickling with custom `_SafeCatalogUnpickler`, allowing instant loading across both package (`src.engine`) and top-level (`engine`) execution contexts.
  - Fixed `DRIVER_PRICES_PATH` import in `src/presets.py`, activating fast binary unpickling across all external catalogs (LSDB, Manufacturer, VituixCAD, Speaker Box Lite, ZTZ Audio).
  - Added snapshot caching for Firestore online presets in `FIRESTORE_PRESETS_CACHE_PATH`, eliminating synchronous network round-trips and gcloud authentication subprocesses on cold boots.
  - Benchmark: Cold startup catalog load time reduced from **4.606s** to **1.326s** (~3.5x faster).
  - Test suite: **204 passed, 0 failed, 0 skipped**.

## 0.15.10 (2026-09-01)

- **Phase 2 Finder Candidate Prefiltering & Pool Caching**:
  - Migrated `candidate_precheck` and `prefilter_finder_candidate_pools` into `src/ranking.py` with persistent module-level LRU caching (`maxsize=128`).
  - Streamlined analytical feasibility screening for $X_{\max}$, drive SPL headroom, loaded $F_s$ and acoustic displacement MOL @ $F_3$ before running costly enclosure solvers.
  - Eliminated redundant per-rerun candidate pool re-evaluations across all 15,553 driver presets.
  - Test suite: **204 passed, 0 failed, 0 skipped**.

## 0.15.9 (2026-09-01)

- **Phase 1 UI Rerun & Finder Speedup**:
  - Eliminated ~107,000 regex evaluations per rerun by delegating driver identity and deduplication to persistent module-level LRU caches in `src/presets.py` (`driver_preset_identity`, `driver_preset_preference`, `deduplicate_driver_preset_names`, `all_preset_brands`, `all_preset_price_currencies`, `all_preset_price_values`).
  - Expanded preset info and TS cache sizes from 8,192 to 32,768 entries to eliminate LRU eviction thrashing across the 15,553-driver library.
  - Added progress reporting throttling and chunking in `_batch_rank_presets_parallel` and `_batch_rank_presets_with_progress` to eliminate frontend websocket delta spam.
  - Benchmark: page switch and filter rerun times reduced from ~870ms to **~220ms** (>50% reduction in latency).
  - Test suite: **204 passed, 0 failed, 0 skipped**.

## 0.15.8 (2026-09-01)

- **Hardened Multi-Database Architecture**: implemented explicit database and storage boundaries across 4 distinct Firestore databases (`lf-private`, `lf-public`, `lf-catalog-runtime`, `lf-catalog-staging`) using modular domain stores in `src/storage/`.
- **Domain Security Boundaries**: isolated crawler staging from production catalog, separated community public publications from tenant private projects, and established least-privilege IAM policies per service account.
- **Catalog Promotion Pipeline**: created schema validation, release manifest generation with SHA-256 digest, required human approval gate, and zero-downtime release rollback in `tools/promote_catalog_release.py`.
- **Idempotent Data Migration**: added zero-downtime migration scripts `tools/migrate_private_data.py` and `tools/migrate_public_projects.py` with parameter digest verification.
- **Disaster Recovery & Runbooks**: configured PITR and scheduled backups in `infra/backup_schedules.sh` and documented recovery procedures in `docs/runbooks_multi_database_ops.md`.
- **Verification**: storage boundary suite (17/17 passed) and test_all fast suite (125 passed, 0 failed, 79 skipped).
- **Finder result restore**: opening a saved project in a fresh session now preserves its Bass Match result rows instead of clearing them during Finder-default migration.

## 0.15.7 (2026-09-01)

- **Unnamed project cleanup**: autosave no longer creates cloud projects before a user name is supplied, legacy `Untitled project` records are hidden from the active project browser, and local draft export/duplication stay disabled until a name is entered.

## 0.15.6 (2026-09-01)

- **Autosave conflict recovery**: concurrent project revisions are recognized and the local payload is rebased onto the latest cloud revision and retried once.

## 0.15.5 (2026-09-01)

- **Bass Match table width**: the ranked-results table now stretches across the full result pane instead of sizing itself only to its content.

## 0.15.4 (2026-09-01)

- **Bass Match cloud-save fix**: Finder result context is stored as a named object instead of a Firestore-incompatible nested array; legacy projects remain readable.

## 0.15.3 (2026-08-31)

- **Cloud-save diagnostics and recovery**: a failed autosave now displays the
  classified cause and exposes `Retry cloud save`, resetting the retry window
  without discarding the local project state or last acknowledged revision.

## 0.15.2 (2026-08-31)

- **Named project creation**: `New Project` now opens a blank name prompt and
  refuses to initialize a project until a name is entered; the previous active
  project remains untouched when the prompt is dismissed.
- **Regression coverage**: UI tests cover the required-name flow and confirm
  that the reset only happens after submitting a non-empty name.
- **Verification**: named-project and Community AppTests pass; fast suite
  passes with 124 passed, 0 failed and 77 skipped tests.

## 0.15.1 (2026-08-31)

- **Community navigation fix**: `Manage Projects` now exits the Community or
  published-project route before selecting the management workspace, so the
  query-string router can no longer keep the Community page pinned onscreen.
- **Hot-reload store compatibility**: cached account and project stores are
  now scoped to the active `src/saas.py` revision. Long-lived Streamlit
  sessions therefore rebuild Firestore stores when the public-project API
  gains new filter parameters instead of calling a stale method signature.
- **Regression coverage**: the Community AppTest now clicks `Manage Projects`,
  confirms the `explore` route is removed and verifies that the management
  workspace renders.
- **Verification**: targeted Community navigation AppTest and version metadata
  consistency check pass; fast suite passes with 124 passed, 0 failed and 77
  skipped tests.

## 0.15.0 (2026-08-31)

- **First-class Community Projects page**: added a visible `Community` entry
  beside Manage Projects in the sidebar project header; public discovery no
  longer depends on knowing the hidden `?explore=1` route.
- **Parametric project discovery**: added combinable min/max filters for box
  volume Vb, tuning Fb, driver diameter, Fs, Qts and F3 alongside keyword,
  topology and sort controls. Passive-radiator projects remain distinct from
  conventional vented reflex projects.
- **Engineering project cards**: Community results now expose topology, Vb,
  Fb, F3, driver diameter, Fs and Qts before opening the immutable technical
  page or sandbox.
- **Publication metadata compatibility**: current DCCAV and bandpass state keys
  and legacy saved-project keys are normalized into public summaries; existing
  Firestore publications recover missing derived metadata from their immutable
  parameter payloads at read time.
- **Regression coverage**: added combined parametric filtering, current-key
  technical-summary and Streamlit filter/reset checks.
- **Verification**: targeted Community AppTest passes; fast suite passes with
  124 passed, 0 failed and 77 skipped tests.

## 0.14.3 (2026-08-31)

- **Published-project cloning**: fixed `Clone to My Projects` failing after
  the Bass Match sidebar instantiated `finder_driver_configuration`. Cloned
  project state is now activated at the start of the next Streamlit run,
  before widget-backed session keys exist.
- **Regression coverage**: the public-project AppTest now clicks the clone
  action and verifies that the independent clone opens in Box Design with its
  saved driver parameters.
- **Verification**: targeted clone AppTest passes; fast suite passes with
  124 passed, 0 failed and 77 skipped tests.

## 0.14.2 (2026-08-31)

- **Engineering-Grade UI Aesthetic & Emoji Deprecation**:
  - Removed miniature decorative emojis and AI-style icons across titles, action buttons, workspace headers, tabs, badges, toasts, and dialogs.
  - Retained high-resolution visual cards and sober, professional typography consistent with engineering CAD/solver software.
- **Dedicated Manage Projects Workspace & Technical Sidebar Decoupling**:
  - **First-Class Project Management Hub (`workspace_mode = "Manage Projects"`)**:
    - Moved all project lifecycle operations (Open, New Project, Rename, Duplicate, `.lfp` Export, `.lfp`/`.crw` Import, Revision History, Trash/Restore, Publish Snapshot) out of the technical sidebar into a dedicated workspace.
    - **Quick Action Toolbar**: `New Project` (clean independent project creation), `Import .lfp / .crw` (popover supporting `Import as New Project` vs `Replace Active Project`), and `Refresh`.
    - **Active Project Spotlight**: Hero section displaying live autosave status, electroacoustic parameter summary ($V_b, F_b, F_s, Q_{ts}$), primary CTAs (`Open in Box Design`, `Open in Bass Match`), backup export (`Export .lfp`), project duplication (`Duplicate`), in-place rename, and shareable link generator.
    - **Management Tabs**: `Cloud Projects` (interactive table/cards with status, revision, modified date, open, duplicate, trash), `Revision History` (timeline with restore version), `Trash` (soft-deleted projects with 30-day retention notice and restore), `Publish Snapshot` (snapshot publishing form with visibility toggle), and `Account & Quotas`.
  - **Technical Sidebar Minimalism**:
    - Stripped clutter from `Bass Match` and `Box Design` sidebars, replacing the large expander with a compact header showing project name, real-time autosave status chip (`Saved` / `Saving…` / `Unsaved changes`), and a direct `Manage Projects` transition button.
    - Preserved 100% technical capabilities while dramatically reducing visual noise and scrolling requirements.
    - Restored the 2-tab visual buttons (`Bass Match` and `Box Design`) with clean full-width styling and hidden compatibility widgets.
- **Tests**: Full active test suite (`PASS: 201 FAIL: 0 SKIP: 0`).

## 0.14.1 (2026-08-31)

- **Published Projects Ecosystem & Multi-Format Real Measurements (Phase 1, Phase 2 & Phase 3)**:
  - **Explore / Community Discovery Hub (`?explore=1`)**:
    - Centralized public engineering directory enabling users to search published electroacoustic designs by title, driver model (FaitalPRO, Beyma, B&C, Dayton, etc.) or author.
    - Advanced multi-dimensional filtering by enclosure topology (Bass reflex, DCCAV, Sealed, Passive radiator, Bandpass 4th/6th/8th order, Infinite baffle), volume range ($V_b$), and cutoff frequency range ($F_3$).
    - Multi-criteria sorting: `Newest First`, `Deepest Extension (Lowest F3)`, `Most Compact Enclosure (Lowest Vb)`, and `Highest Peak SPL`.
    - Project cards grid displaying key electroacoustic specs, transducer details, verified simulation badge, and instant "View Tech Page" / "Open Sandbox" actions.
  - **Multi-Format Real Measurements Parser & Comparison Engine (`src/measurements.py`)**:
    - Implemented `parse_measurement_file()` with support for all major electroacoustic measurement platforms:
      1. **REW (Room EQ Wizard)**: SPL magnitude, impedance, and phase text exports (`.txt`, `.frd`, `.zma`, `.mdat`).
      2. **DATS v2 / v3 (Dayton Audio)**: Impedance curve exports (`.zma`, `.txt`, `.frd`) with `Data:` block extraction.
      3. **ARTA / LIMP**: Semicolon/comma-delimited frequency response and impedance files with European decimal comma normalization.
      4. **CLIO / CLIO Pocket (Audiomatica)**: Sinusoidal SPL and impedance exports (`.txt`, `.dat`, `.frd`).
      5. **Klippel**: Tabular transfer function and impedance exports (`.txt`, `.frd`, `.zma`).
      6. **Generic FRD / ZMA**: Universal 2-column and 3-column delimited files with automatic comment filtering (`#`, `//`, `*`, `;`, `!`).
    - Implemented `compare_simulation_to_measurement()` calculating Root Mean Square Error (RMSE), maximum delta, mean bias offset, and automated twin-peak reflex impedance saddle tuning detection ($\Delta F_b$).
    - Compact serialization/deserialization (`serialize_measurement`, `deserialize_measurement`) for cloud snapshot persistence.
  - **Simulated vs Measured Interactive Overlay**:
    - Added dedicated "🔬 Measurement Validation" tab on public project snapshots allowing visitors to upload real prototype measurements and compare them live against the published simulation curve with RMSE and $\Delta F_b$ diagnostic metrics.
  - **Immutable Technical Snapshots & Publishing**:
    - Added support for publishing Load Forge projects to immutable snapshot versions stored at `/public_projects/{publication_id}` and `/public_projects/{publication_id}/versions/v_{version:010d}` across both `InMemoryProjectStore` and `FirestoreProjectStore`.
    - Added `unlisted` (accessible solely via direct link) and `public` (eligible for explore directory indexing) visibilities.
    - Strict tenant isolation: private edits and autosaves do not mutate published snapshots.
    - `extract_technical_summary(payload)` derives transducer specs ($F_s, V_{as}, Q_{ts}, R_e, S_d$), nominal size, enclosure volume ($V_b$) and tuning frequency ($F_b$).
  - **Rich Technical Transparency & Performance Visualizer (`?p=<publication_id>`)**:
    - Complete 6-tab performance breakdown: SPL Frequency Response (+ MOL), Cone Excursion (+ $X_{\max}$), Impedance & Phase (+ $Z_{\min}$), Port Air Velocity (+ chuffing limits), Group Delay (+ 1-cycle audibility envelope), and Physical Prototype Measurement Validation.
    - Comprehensive electroacoustic metrics row: $F_3, F_6, F_{10}$, Peak SPL, $Z_{\min}$, and Peak Group Delay.
    - Verified Simulation badge certifying calculation with Load Forge lumped-parameter solver.
    - Public actions: **Open in Load Forge (Preview)** sandbox, **Clone to My Projects** (with full provenance metadata), **Download .lfp**, **Export Spec Sheet (.md)**, and **Embed Code** modal.
  - **Embed Widget Mode (`?p=<pub_id>&embed=1`)**: Minimal responsive widget without chrome, rendering key metrics and interactive SPL curve for external audio forums (DIYAudio, ASR) and blogs.
  - **SEO & Social Previews**: Structured Schema.org `TechArticle` / `Product` JSON-LD and OpenGraph metadata generation.
  - **Printable Specification Sheet Export**: `generate_printable_spec_sheet_markdown(pub)` producing a publication-ready Markdown spec sheet.
  - **Tests**: Comprehensive unit regressions and Streamlit `AppTest` test suite (`PASS: 198 FAIL: 0 SKIP: 0`).

## 0.13.2 (2026-08-31)

- **Release metadata guard**: synchronized the project version after the
  post-release documentation correction and added an automated consistency
  check for version metadata and the changelog.

## 0.13.1 (2026-08-31)

- **Production Project Persistence & Data Safety**:
  - Added authenticated debounced Firestore autosave with acknowledged save status, bounded non-blocking retries and semantic no-op deduplication.
  - Added canonical format-2 LFP/cloud payload validation, strict JSON/schema checks, immutable revision documents, transactional optimistic concurrency and explicit revision restoration.
  - Added stale-session conflict handling with reload-latest/save-as-copy choices, soft-delete Trash with restore, and a 30-day cleanup target.
  - Preserved legacy flat Firestore and format-1 LFP reads while keeping `.lfp` export/import as the independent portable backup path.
  - Kept project documents isolated from account identity, subscription and credit fields; documented an append-only credit ledger as follow-up before paid credit packs.
- **Persistence UX & Recovery Operations**:
  - Added compact Saved/Saving/Unsaved/Retrying/Failed status, cloud project management, minimal version history, Trash restore, backup guidance and session-only last-export metadata.
  - Replaced Streamlit's project-store function-name spinner with a quiet initialization path and an actionable local ADC message when Firestore credentials are missing or expired.
  - Added operator checklists for Firestore PITR, daily/longer-retention scheduled backups, restore drills, catalog backup and surgical project recovery.
- **Tests**: Added regressions for autosave, deduplication, validation, revisions, stale conflicts, soft delete/restore, failed-write status, schema handling and credit isolation. Full active suite: `PASS: 187 FAIL: 0 SKIP: 0`.

## 0.12.33 (2026-08-30)

- **Box Design Save T/S to Catalog Fix**:
  - Resolved `StreamlitAPIException` when persisting modified T/S parameters into the source catalog by deferring `driver_preset_name` session state assignment via `_pending_driver_preset_name` before widget re-instantiation.
  - Added automated Streamlit `AppTest` regression test in `tests/test_all.py` validating the full button click lifecycle.
- **Full Active Test Suite**: 186 tests passing fresh (`PASS: 186 FAIL: 0 SKIP: 0`).

## 0.12.32 (2026-08-30)

- **Parametric Acoustic Port CAD & STL Generator Constant Normal Thickness**:
  - Implemented `compute_normal_offset_profile()` in `src/port_cad.py` using true outward unit normal vectors $\hat{n} = \left(-\frac{dr}{\text{norm}}, \frac{dz}{\text{norm}}\right)$.
  - Fixed wall thinning on flared/curved profiles (Hourglass, double-flared Aeroport, single-flared vents), ensuring exact uniform normal wall thickness $t_{\text{wall}}$ throughout both 2D SVG blueprints and watertight 3D STL meshes.
  - Added unit test assertions in `tests/test_all.py` validating $4.0\text{ mm}$ constant normal thickness.
- **Full Active Test Suite**: 186 tests passing fresh (`PASS: 186 FAIL: 0 SKIP: 0`).

## 0.12.31 (2026-08-30)

- **Online Google Cloud Firestore Driver Presets Tier**:
  - Implemented `_load_firestore_presets()` and `invalidate_preset_caches()` in `src/presets.py` and re-exported through `src/acoustics.py`.
  - Added live querying of `driver_presets` collection in Firestore project `civic-radio-502611-i8` (or configured `LOAD_FORGE_GCP_PROJECT`).
  - Seamlessly integrates measured driver presets into Load Forge without container redeployment, categorizing them under `"Z Bench"` provenance.
  - Added unit test `_check_firestore_presets_loader` in `tests/test_all.py`.
- **Full Active Test Suite**: 186 tests passing fresh (`PASS: 186 FAIL: 0 SKIP: 0`).

## 0.12.30 (2026-08-30)

- **Z Bench Hardware Measurements Provenance Tier**:
  - Added `"Z Bench"` as a first-class provenance category in `PRESET_PROVENANCE_CATEGORIES` (`src/presets.py` and `src/acoustics.py`).
  - Added automatic mapping and UI filter aliases (`"Z Bench Measurement"`, `"Z Bench measured"`, `"Z-Bench"` $\to$ `"Z Bench"`).
  - Presets measured and published directly from Z Bench (Dayton Audio DATS V3) are now filterable and selectable in Bass Match and Box Design alongside built-in, crawled and third-party catalogs.
  - Sychronized `GOLDEN_STD.md` with canonical specification v1.1.0 (`dev_standards`).
- **Full Active Test Suite**: 185 tests passing fresh (`PASS: 185 FAIL: 0 SKIP: 0`).

## 0.12.29 (2026-08-29)

- **Plausible Passive Radiator Combinations in Box Design & Bass Match**:
  - Implemented `plausible_passive_radiators()` and `suggest_best_pr_combo()` in `src/engine.py` and `src/acoustics.py`.
  - Automatically evaluates and matches all 71 catalogued passive radiators against driver displacement ($V_{d,\text{PR}} \ge V_{d,\text{driver}}$), radiating area ($0.7 \le S_p/S_d \le 3.5$), and computes exact non-negative added mass $\Delta M \ge 0$ required to hit the target box tuning $F_b$ in volume $V_b$.
  - Added interactive **Plausible PR Matches** in Box Design (sidebar and Ports workbench) with 1-click application of compatible combos (1x / 2x PRs + added mass).
  - Integrated PR catalog view in Bass Match Library and Ports analysis.
- **Full Active Test Suite**: 185 tests passing fresh
  (`PASS: 185 FAIL: 0 SKIP: 0`).

## 0.12.28 (2026-08-28)

- **Widget help restored**:
  - Removed the legacy global CSS override that hid every Streamlit help
    tooltip, restoring the `?` help content across Bass Match and Box Design.
  - Kept long help text readable with a bounded responsive width, normal line
    wrapping and a foreground stacking level above dashboard controls.
  - Added a regression assertion preventing the tooltip selectors from being
    hidden again.
- **Full Active Test Suite**: 185 tests passing fresh
  (`PASS: 185 FAIL: 0 SKIP: 0`).

## 0.12.27 (2026-08-28)

- **Coherent Ports engineering and auto-sizing**:
  - Unified the selected duct's flare profile across KPI, chuffing-limit chart,
    CAD blueprint and optimizer, including single-port loads and target changes.
  - Added shared profile limits (cylindrical, single flare, Aeroport and
    hourglass) and policy-specific velocity/duct-volume budgets: Studio 20%,
    Balanced 12%, Compact 8%.
  - Fixed unreachable-target fallback selection so it keeps the feasible duct
    with the lowest MOL air speed instead of the first/smallest diameter, with
    an explicit compromised result when constraints prevent the requested target.
- **Parametric CAD/STL correctness**:
  - Corrected Aeroport flare orientation, coherent total/half manufacturing
    dimensions, mouth/throat/radius callouts and real manifold bolt holes.
  - Normalized STL split state so Single piece exports the full mesh and
    2-piece mode exports a true half, including stable reruns and downloads.
- **Streamlit state and development reliability**:
  - Preserved Blueprint Focus across flare changes, synchronized active duct
    selection, and fixed facade hot reloads after engine changes.
  - Made Studio/Balanced/Compact changes immediately rerun sizing and display
    the resulting diameter, MOL peak, target and any limiting compromise.
- **Free multi-design comparison**:
  - Removed the Pro/Team gate from Box Design duplication and Finder
    multi-selection. Every account tier can create and edit up to eight design
    tabs; plan and Open Beta entitlements no longer affect this workflow.
- **Dependencies**: added `trimesh` and `manifold3d` for validated watertight
  flange booleans and drilled STL generation.
- **Full Active Test Suite**: 185 tests passing fresh
  (`PASS: 185 FAIL: 0 SKIP: 0`).

## 0.12.26 (2026-08-27)

- **Parametric 3D CAD & Watertight STL Generator for 3D Printing & CNC**:
  - Added the new `src/port_cad.py` module with physical 1:1 in-scale 2D CAD cross-section rendering (SVG) and watertight 3D binary STL mesh generation.
  - Implemented the continuous progressive curvature law for Hourglass / Venturi ports where radius of curvature $R_{\text{curve}}(z)$ transitions smoothly from $R_{\text{throat}} \approx 600\text{ mm}$ at the central throat to $R_{\text{mouth}} \approx 20\text{ mm}$ at the bellmouth mouths, eliminating sharp transitions and flow separation.
  - Added full interactive controls in the Ports tab for wall thickness (mm), integrated mounting flange (toggle, thickness, outer diameter), and bolt hole cutouts (count, diameter, bolt circle PCD).
  - Added multi-mode 3D printing export: Single piece (Full port), 2-piece symmetric halves ($L/2$ for flat supportless build-plate printing), and Outer Flange Coupling Only with direct one-click `.stl` download.
- **Full Active Test Suite**: 184 tests passing (`PASS: 112 FAIL: 0 SKIP: 72`).

- **Targeted Per-Duct Focus & Independent Flare Configuration**:
  - Added a prominent single-click **Active Duct Focus** selector (`[ 🌐 All Ducts ]`, `[ 🔒 Upper Port (Internal) ]`, `[ 📢 Lower Port (External) ]`, etc.) right at the top of the Cockpit and synchronized with the Blueprint CAD workbench.
  - Allows configuring flare profiles (Straight Cylindrical, Double Flared Aeroport, Hourglass continuous) and flare radii independently per duct (e.g., straight pipe for internal coupling, Aeroport/Hourglass for external radiating).
  - Auto-optimizer buttons directly adapt to the focused duct (`⚡ Auto-optimize Upper Port (Internal)` or `⚡ Auto-optimize All Ducts`) to size individual ducts without affecting customized settings on other chambers.
  - Integrated acoustic explanation badges for internal inter-chamber vs external radiating ducts.
- **Full Active Test Suite**: 183 tests passing (`PASS: 111 FAIL: 0 SKIP: 72`).

## 0.12.24 (2026-08-27)

- **Ergonomic Ports Tab Redesign (Workbench CAD & Acoustic Health Monitor)**:
  - Transformed the Ports tab into an ergonomic 2-column workbench layout inspired by CAD/audio engineering suites (*VituixCAD*, *Subbox.pro*, *Fusion 360*).
  - Added a prominent top **Acoustic Health Monitor** with 4 KPI cards for instant chuffing risk assessment (color-coded safe / compression / turbulent flow status, peak MOL air speed @ peak Hz, flare profile guideline limit, and total duct volume displacement).
  - Organized parameters and simulation controls into structured cards on the left column (Flare Profile & Optimizer, Manual Duct Dimensions & Chamber Ports, Trace Pens & Metric Selector).
  - Structured the right column into dedicated performance and manufacturing sections (Air Velocity vs Chuffing Limit chart, Blueprint CAD SVG drawing with focus selector and dimensional callouts, and full-width manufacturing cut sheet table).
- **Full Active Test Suite**: 183 tests passing fresh (`PASS: 183 FAIL: 0 SKIP: 0`).

## 0.12.23 (2026-08-27)

- **Internal/External Duct Differentiation & Input Contrast Enhancement**:
  - Differentiated internal vs external ducts in the geometry table and input labels (e.g., *Upper port (Internal inter-chamber)* vs *Lower port (External radiating)*).
  - Enhanced UI contrast for data-entry inputs (dark charcoal surface `#151a22` with crisp subtle borders `rgba(255, 255, 255, 0.18)` and emerald focus states) so numeric inputs and dropdowns stand out clearly against the pitch-black background on Cloud Run.
- **Full Active Test Suite**: 183 tests passing fresh (`PASS: 183 FAIL: 0 SKIP: 0`).

## 0.12.22 (2026-08-27)

- **Direct Simulation Sweep for Accurate MOL Auto-Optimization**:
  - Auto-optimizer now directly runs the simulated MOL velocity curve (`port_air_velocity_ms`) for each candidate diameter, ensuring that the selected diameter guarantees peak MOL speed below target thresholds ($\le 28$ or $32\text{ m/s}$).
  - Passed `port_name` (`upper`/`lower`) into all optimizer calls.
- **Full Active Test Suite**: 111 tests passing fresh (`PASS: 111 FAIL: 0 SKIP: 72`).

## 0.12.21 (2026-08-27)

- **Visual Toast Feedback on Auto-Optimization & Recalculation**:
  - Displays instant `st.toast("⚡ Duct Auto-Optimized: ...")` notification when switching policy or clicking the optimizer button so the user gets immediate visual confirmation of the rerun.
- **Full Active Test Suite**: 111 tests passing fresh (`PASS: 111 FAIL: 0 SKIP: 72`).

## 0.12.20 (2026-08-27)

- **Auto-Recalculation on Policy / Flare Change & Acoustic Sizing Fixes**:
  - Auto-recalculates duct dimensions immediately upon changing the policy dropdown (*Studio*, *Balanced*, *Compact*) or the flare style without requiring an extra button click.
  - Eliminated zero-length edge artifacts for small cavities and high tunings by bounding acoustic mass scaling to realistic physical limits.
- **Full Active Test Suite**: 111 tests passing fresh (`PASS: 111 FAIL: 0 SKIP: 72`).

## 0.12.19 (2026-08-27)

- **Fix Main Scope Reference (`current_ts`)**:
  - Replaced unassigned `driver` name with `current_ts` in the main tab dispatcher call to `_render_ports_tab`.
- **Full Active Test Suite**: 111 tests passing fresh (`PASS: 111 FAIL: 0 SKIP: 72`).

## 0.12.18 (2026-08-27)

- **Fix `driver` and `box` Scope in `_render_ports_tab`**:
  - Explicitly passed active `driver` and `box` parameters into `_render_ports_tab` to fix the button handler scope on the live UI.
- **Full Active Test Suite**: 111 tests passing fresh (`PASS: 111 FAIL: 0 SKIP: 72`).

## 0.12.17 (2026-08-27)

- **Acoustic Engineering Directive Auto-Optimizer (`⚡ Auto-optimize duct`)**:
  - Implemented `auto_optimize_port_diameter_cm()` in `engine.py` with 3 professional design policies:
    - `Studio / Hi-Fi`: Strict zero-chuffing at MOL ($X_{\text{max}}$ limit).
    - `Balanced / Pro`: Standard AES trade-off balancing peak velocity, organ pipe resonances, and duct length.
    - `Compact Enclosure`: Minimizes displaced volume while respecting Small/Keele displacement floor $S_{\text{min}} = 0.8 f_b V_d$.
  - Added organ-pipe resonance calculation (`port_pipe_resonance_hz`).
  - Added policy selector and one-click auto-optimizer button under Duct sizing & Geometry.
- **Full Active Test Suite**: 111 tests passing fresh (`PASS: 111 FAIL: 0 SKIP: 72`).

## 0.12.16 (2026-08-27)

- **Port Profile Selector at Chart Head & Dynamic Thresholds**:
  - Relocated Port Geometry / Flare Profile selector directly to the header of the Port Air Velocity section.
  - Dynamically highlights active chuffing thresholds in the chart (Straight: 17.2 m/s, Aeroport: 28.0 m/s, Hourglass: 32.0 m/s).
  - Drives all calculations, sizing table metrics, and live SVG blueprints directly in lockstep.
- **Full Active Test Suite**: 111 tests passing fresh (`PASS: 111 FAIL: 0 SKIP: 72`).

## 0.12.15 (2026-08-27)

- **Blueprint Geometric Loop & Text Clearance Correction**:
  - Re-ordered SVG path winding order and loop closures for top and bottom walls to eliminate overlapping fill artifacts.
  - Widened blueprint viewBox and adjusted mouth annotation positions to ensure clear text rendering without clipping.
- **Full Active Test Suite**: 111 tests passing fresh (`PASS: 111 FAIL: 0 SKIP: 72`).

## 0.12.14 (2026-08-26)

- **Complete Vector Overhaul of Aeroport & Hourglass Blueprint Profiles**:
  - Re-anchored SVG coordinate system and tangent vectors:
    - Standard Flared (Aeroport): Central straight cylindrical pipe transitions smoothly outward into expansive bell flares with correct wall thickness and outward mouth opening.
    - Hourglass Continuous: Smoothly expands from narrow central throat out to both flared mouth exits.
- **Full Active Test Suite**: 111 tests passing fresh (`PASS: 111 FAIL: 0 SKIP: 72`).

## 0.12.13 (2026-08-26)

- **Iframe Component Blueprint Rendering**:
  - Integrated `streamlit.components.v1.html` iframe wrapper for SVG blueprint visualization, avoiding DOM stripping / sanitization across all browser environments.
- **Full Active Test Suite**: 111 tests passing fresh (`PASS: 111 FAIL: 0 SKIP: 72`).

## 0.12.12 (2026-08-26)

- **Blueprint SVG Render Reliability Fix**:
  - Replaced `st.markdown()` with dedicated `st.html()` for port geometry blueprints, preventing Markdown indentation parsing errors on large multi-line SVG tags.
- **Full Active Test Suite**: 111 tests passing fresh (`PASS: 111 FAIL: 0 SKIP: 72`).

## 0.12.11 (2026-08-26)

- **Continuous Hourglass Flared Port Topology**:
  - Implemented continuous symmetrical hourglass profile calculation in `flared_port_dimensions_cm(..., flares="hourglass")`.
  - Solves distributed acoustic mass integral $M_a = \rho \int \frac{dx}{S(x)}$ yielding $L_{\text{eff}} / L_{\text{phys}} \approx r_{\text{throat}} / r_{\text{mouth}}$, and calculates solid-of-rotation displaced volume.
  - Added *Hourglass continuous (Clessidra)* option in Duct sizing UI with smooth continuous parabolic blueprint SVG schematic.
- **Full Active Test Suite**: 111 tests passing fresh (`PASS: 111 FAIL: 0 SKIP: 72`).

## 0.12.10 (2026-08-26)

- **Flared Aeroport Visual Blueprint Realism**:
  - Corrected SVG profile curvature so the flare bell expands outward toward the mouth and inner termination (true aerodynamic trumpet flare profile).
  - Dynamically switches geometry between Double Flared, Single Flared (outer mouth only), and Straight Pipe.
- **Full Active Test Suite**: 111 tests passing fresh (`PASS: 111 FAIL: 0 SKIP: 72`).

## 0.12.9 (2026-08-26)

- **Unified Duct Sizing & Aeroport Geometry Architecture**:
  - Eliminated disconnected duplicate parameter inputs; unified all port sizing controls into a single coherent section driving both the acoustic simulation, the air velocity charts, and the Aeroport physical calculations.
  - Port Geometry table now directly displays **Diameter**, **Straight Cut**, **Overall Length**, **Mouth Ø**, and **Duct Displaced Volume** alongside nominal and MOL peak air velocities.
  - Blueprint section automatically renders live dimensions for the active design and selected flare termination (*Double flared*, *Single flared*, or *Straight*).
- **Full Active Test Suite**: 111 tests passing fresh (`PASS: 111 FAIL: 0 SKIP: 72`).

## 0.12.8 (2026-08-26)

- **Flared Aeroport Interactive Diagram & Direct Design Apply**:
  - Added visual SVG cross-section blueprint schematic for flared Aeroports showing inner diameter, mouth diameter, cut length, and tip-to-tip overall length.
  - Added **"Apply Flared Tube Diameter to Design"** button to instantly transfer the chosen inner tube diameter into the active design simulation.
  - Added dual guideline threshold rules on the Port Air Velocity chart: straight port limit (red dashed, 17.2 m/s) and flared Aeroport limit (emerald dashed, 28.0 m/s).
- **Full Active Test Suite**: 111 tests passing fresh (`PASS: 111 FAIL: 0 SKIP: 72`).

## 0.12.7 (2026-08-26)

- **Flared Port / Aeroport Calculator**:
  - Added `flared_port_dimensions_cm()` to `src/engine.py` modeling acoustic end corrections, flare axial length contributions, and physical dimensions for double-flared, single-flared, and straight reflex ports.
  - Added dedicated interactive calculator expander `🎺 Flared Port / Aeroport Calculator` in the Ports tab.
  - Reports Overall Length, Straight Pipe Cut length, Outer Mouth Diameter, Displaced Box Volume, and the elevated chuffing threshold guideline (~28 m/s).
- **Full Active Test Suite**: 111 tests passing fresh (`PASS: 111 FAIL: 0 SKIP: 72`).

## 0.12.6 (2026-08-26)

- **Port Velocity at MOL in Charts & Duct Sizing**:
  - Added port linear air velocity calculation scaled to Maximum Output Level (MOL): `port_air_velocity_ms(..., at_mol=True)`.
  - Added Port metric radio selector in Ports tab: *Air velocity at MOL (m/s)*, *Air velocity at drive level (m/s)*, and *Volume velocity (m³/s)*.
  - Added $17.15\text{ m/s}$ (5% speed of sound) red dashed chuffing threshold guideline rule in air velocity modes.
  - Added `Peak m/s (MOL)` column to the Port Geometry and Passive Radiator summary tables.
  - Restored classic graphical workspace switcher navigation; moved Admin Maintenance & User Management tools to sidebar expander opening in new tabs.
- **Full Fast Test Suite**: 111 unit & physics tests passing (`PASS: 111 FAIL: 0 SKIP: 72`).

## 0.12.5 (2026-08-26)

- **Complete Emerald UI Overrides**: Eliminated all remaining red highlight accents across the application:
  - Sidebar multi-select pills & tags (`Manufacturer`, `Size`, `Class`, `Provenance`) styled in emerald green (`#10b981`).
  - Active tab indicators and text styled in emerald green.
  - Radio button active state (`Rank by`) styled with emerald borders and dot.
  - Data editor / table sparkline mini-curves stroke color set to emerald (`#10b981`).
  - Set `--primary-color: #10b981` in root CSS variables.
- **Admin Credit Sync & Simulation Bypass**: Administrator accounts (`playloud79@gmail.com`) automatically synchronize credit balances (100,000+ credits) and bypass simulation credit checks.
- **Full Fast Test Suite**: 111 unit & physics tests passing (`PASS: 111 FAIL: 0 SKIP: 72`).

## 0.12.0 (2026-08-26)

- **Persistent User Accounts & Credit Engine**: Integrated Firestore native database store (with in-memory/SQLite dev fallback) tracking user credit balances and deduction on simulations.
- **Credit Plan Tiers & Automatic Refills**: Implemented Free (100 credits/mo), Pro (2,500 credits/mo), and Team (10,000 credits/mo) with automatic monthly quota reset.
- **Search Multipliers**: Streamlined profiles into **Standard** (1 credit / candidate) and **Deep** (2 credits / candidate), removing the Fast profile.
- **Admin Management Dashboard**: Added a dedicated `User Management (Admin)` workspace for live credit adjustments, plan switching, and user usage statistics.
- **Full Active Test Suite**: 183 tests passing fresh with 0 failures (`PASS: 183 FAIL: 0 SKIP: 0`).

## 0.10.0 (2026-08-26)

- Added **⚡ Fast T/S Pre-screening** to Bass Match (`finder_fast_prefilter`),
  analytically pruning candidates that cannot physically meet the target F3 or
  MOL at F3 ($V_d = S_d \cdot X_{max}$) before full simulation, accelerating broad
  catalog scans by up to 10× on constrained cloud instances.
- Added `scipy` dependency explicitly in `requirements.txt` for Streamlit Cloud
  deployment compatibility.
- Added UI toggle in *Performance filters* -> *Advanced driver filters* to enable/disable
  analytical pre-screening.
- Full active test suite passes fresh with 0 failures across 183 tests (`PASS: 183 FAIL: 0 SKIP: 0`).

## 0.9.4 (2026-08-25)

- Simplified the Finder result table by hiding the `Class` and `Sd cm²`
  columns, abbreviating the currency heading to `CUR` and showing the
  maximum-output heading as `MOL`; compacted the manufacturer, part-number and
  minimum-impedance headings to `Mfr`, `Part #` and `Min Z`.
- Replaced raw chamber coordinates with topology-native Finder V2 transforms:
  total volume plus logit chamber split for BP4/BP6/DCCAV, and total volume
  plus softmax chamber fractions for BP8. Tunings use relative base-frequency
  and separation-ratio coordinates; all transforms have deterministic
  round-trip and positivity regression coverage.
- Reworked the search pipeline so deterministic Halton sniff candidates are
  compared before local descent, added a sensitivity probe, independent
  per-axis step contraction/expansion and strict enforcement of the requested
  distinct-box evaluation budget.
- Added adaptive spectral verification of competitive finalists around tuning,
  extrema and high-curvature regions. Finder now recalculates ripple on the
  final display-resolution response and drops a row if that resolved response
  exceeds the selected limit, preventing the Finder table and Box Design chart
  from disagreeing because a 30-point grid missed a notch.
- Restored `max_ripple_db` as an optimizer feasibility constraint: compliant
  candidates always outrank out-of-limit candidates, and the engine now reports
  an explicit infeasible-goal error instead of returning a box above the selected
  ripple ceiling. Finder and Box Design cache revisions invalidate stale results.
- Added a semantic revision handshake for Finder worker processes. A stale
  forkserver worker is now discarded before it can mix old optimizer F3 values
  with the current Box Design simulation.
- Finder now uses shared-memory threads by default. This prevents Python's
  process workers from re-importing the Streamlit entry point and evaluating
  candidates with an optimizer module different from Box Design.
- Corrected the Beyma 4FR40 manufacturer record from `Cms = 668 mm/N` to
  `0.668 mm/N` (668 µm/N) and made explicit Cms units mandatory during future
  catalog crawls, removing its physically impossible 19.8 Hz Finder result.
- Full active test suite passes fresh with 0 failures across 183 tests (`PASS: 183 FAIL: 0 SKIP: 0`).

## 0.9.0 (2026-08-25)

- Implemented Finder V2 multi-stage pattern search in `src/engine.py` with composite displacement vector tracking for rapid diagonal ridge traversal.
- Added deterministic low-discrepancy Halton sampling exploration for high-dimensional topologies ($\ge 3$ chambers/ports: Bandpass 4th/6th/8th, DCCAV) avoiding Cartesian grid explosions.
- Added Search Profile presets (**Fast** 30 evals, **Standard** 60 evals, **Deep** 120 evals) in `src/ranking.py` and Bass Match Advanced evaluation controls.
- Refined Load Forge UI visual hierarchy, high-density layout, typography, and card spacing.
- Consolidated global CSS design tokens (`--lf-bg-base`, `--lf-bg-surface`, `--lf-accent`) for clean visual contrast.
- Reduced box-inside-box outlines using subtle dividers and elevated backgrounds without losing technical rigor.
- Optimized Bass Match candidate space workflow, featuring a spot quota indicator and streamlined pre-simulation statistics.
- Full active test suite passes fresh with 0 failures across 176 tests (`PASS: 176 FAIL: 0 SKIP: 0`).

## 0.8.26 (2026-08-24)

- Added the previously missing Hertz DS 250.3 from the official technical
  datasheet; catalog total is now 7,379 raw and 6,375 application-visible
  records. Existing catalog rows remain unchanged.
- Added five previously missing Beyma drivers from official technical
  datasheets (`8MI100`, `12CMV2`, `3FR30`, `15CMV2` and one archived Beyma
  sheet); catalog total is now 7,384 raw and 6,380 application-visible records.
- Added two further Beyma drivers from official technical datasheets
  (`12G125` and `12WRS400`); catalog total is now 7,386 raw and 6,382
  application-visible records.

- Added the previously missing `B&C Speakers 12CXL64` from the official B&C
  2023 catalogue PDF after validating 106 complete T/S blocks; catalog total
  is now 7,351 raw and 6,347 application-visible records.
- Added two previously missing Tang Band official product pages (`W3-2088S0F`
  and `W4-1320SMF`); catalog total is now 7,353 raw and 6,349
  application-visible records.
- Added the previously missing official RCF `LF12P901` woofer; catalog total
  is now 7,354 raw and 6,350 application-visible records.
- Added six previously missing Ciare drivers from official product datasheets
  (`PWA5.38`, `12.75W1`, `PWA12.75`, `HW100`, `CH250`, `PH250`); catalog total
  is now 7,360 raw and 6,356 application-visible records.
- Added four further Ciare drivers from official datasheets (`PWA8.50`,
  `CW200Z`, `CW100Z`, `CW130Z`); catalog total is now 7,364 raw and 6,360
  application-visible records.
- Added four further Ciare official datasheet drivers (`NDI8.50W`, `NDH18-4S`,
  `CM100`, `HW250`); catalog total is now 7,368 raw and 6,364
  application-visible records.
- Added three further Ciare official drivers (`PH320`, `HX201`, `FXH15.64W`);
  catalog total is now 7,371 raw and 6,367 application-visible records.
- Added three further Ciare official datasheet drivers (`PW455`, `18.00SW-4`,
  `HWB130`); catalog total is now 7,374 raw and 6,370 application-visible
  records.
- Added one previously missing Hertz driver from the official Energy5 static
  datasheet; catalog total is now 7,375 raw and 6,371 application-visible
  records.
- Added three further Hertz drivers from official static datasheets
  (Hi-Energy/ECX/ESK); catalog total is now 7,378 raw and 6,374
  application-visible records.

- Separated catalog metadata from the application release: the proprietary
  catalog remains independently versioned at **1.0.0**.
- Published 15 DD Audio official product variants (D2/D4 where offered).
  `Mms` is calculated from the official `Fs`, `Vas` and piston area; `Re` is
  1.7 ohm per D2 coil and 3.4 ohm per D4 coil. The catalog now contains 7,248
  raw and application-visible records; existing rows remain unchanged.
- Followed DD Audio's official product sitemap and published a further 25
  official D2/D4 variants from 15 additional product pages. The catalog now
  contains 7,273 raw and 6,269 application-visible records.
- Added six SOVOX official mid-woofer product pages, a previously absent
  manufacturer, bringing the catalog to 7,279 raw and 6,275 visible records.
- Added one PRV Audio official product page (`8MR400-NDY-4`); catalog total is
  now 7,280 raw and 6,276 visible records.
- Added one Soundking driver from the official manufacturer T/S PDF
  (`FB0850-2`); catalog total is now 7,281 raw and 6,277 visible records.
- Extracted and validated 25 additional Soundking coaxial LF drivers from the
  same official T/S PDF; catalog total is now 7,306 raw and 6,302 visible.
- Corrected Eminence official-page identity extraction (UPC titles were
  replaced by product slugs), validated runtime identities, and published 36
  new official models. Catalog total is now 7,342 raw and 6,338 visible.
- Retried the Eminence pages blocked by rate limiting and published 8 further
  official models; catalog total is now 7,350 raw and 6,346 visible.
- Published 773 reviewed, append-only manufacturer records from Adire Audio,
  Stereo Integrity, Sundown Audio, JBL Professional, SEAS, Hinor, SB Acoustics,
  Visaton, Wavecor, Peerless/Tymphany, Monacor, Eighteen Sound, SICA, Jensen,
  FaitalPRO, Ciare, Fane, Fi Car Audio, Tang Band, BMS Speakers, Celestion, VAS Audio and LaVoce; the catalog now contains 7,233 raw records and 6,229
  application-visible drivers without changing or deleting any pre-existing
  row. The latest LaVoce official-source batch contributed 1 net application-visible driver.
- Added Wavecor multi-model matrix extraction and a resilient first-party
  Peerless/Tymphany API harvester. Added a first-party Monacor category
  harvester that verifies each product's manufacturer block, excluding
  third-party Celestion listings before publication; retailer title variants
  are now checked against the same runtime identity sequence used by Bass
  Match before future publication.
- Crawled Eighteen Sound's complete official LF/coaxial catalog and archive,
  retaining nominal thermal rather than 2x continuous power and distinguishing
  published 2/4/8/16-ohm variants. The `18Sound` legacy brand now aliases to
  official `Eighteen Sound`, preventing eight existing display duplicates and
  yielding 69 net-visible additions from 77 append-only rows.
- Added a structured SICA/Jensen first-party Store API harvester with strict
  brand-category evidence, AES/Xmax/Cms unit handling and coaxial LF-field
  support. Of 177 official products, 145 had complete T/S data and exact
  runtime deduplication yielded 45 new application-visible records.
- Added a first-party FaitalPRO LF/coaxial/archive harvester that enumerates
  every official product ID and preserves real 4/8/16-ohm variants. All 212
  official details passed complete T/S validation; exact runtime deduplication
  retained 56 genuinely new, application-visible drivers.
- Added a concurrent first-party Ciare current/archive harvester for LF and
  coaxial families with impedance-aware identities. It validated 162 of 165
  official details and appended 57 reviewed rows. Ciare impedance-suffix
  normalization collapses ten pre-existing retailer aliases, producing 48 new
  normalized identities and a net online gain of 38 visible drivers. Three
  records without a complete manufacturer-published T/S core were not imported.
- Added a first-party Fane current/archive harvester with ASP.NET postback
  pagination. It found 74 official product pages, validated 68 complete cone
  drivers, rejected six compression drivers without a simulation-ready T/S
  core, and appended 65 new rows. Three untouched legacy `Fane International`
  aliases now collapse at runtime, yielding 62 net-visible additions.
- Added 17 complete Fi Car Audio official product records across Alpha, Xv4,
  HC, MT and NEO families. The official pages expose impedance-specific T/S
  tables; incomplete SP3/SP4 pages were left out rather than supplemented from
  third-party sources.
- Added 11 further complete Fi Car Audio NEO 3.7/3.9/4.7/4.9/4.11 official
  product variants with manufacturer-published DVC T/S tables.
- Added one Tang Band W8-1722B record from the official TB Speaker page;
  two other tested official pages matched existing catalog identities and were
  therefore not duplicated.
- Added an identity-only discovery radar over all 14,512 records in the
  optional LSDB, VituixCAD, Speaker Box Lite, ZTZ Audio and legacy manufacturer
  libraries. It found 6,342 missing identities across 394 brands without
  copying or publishing any third-party T/S parameter.
- Added manufacturer-first source discovery, isolated retailer gap reporting,
  progress/latest-report artifacts and an in-app crawl report.
- Added a guarded reviewed-publication command and catalog-specific checks so
  catalog work can be validated independently from the full acoustic suite.
- Fixed crawler handling of written area units such as `square inches`, made
  explicit physical units outrank unitless layout candidates, normalized
  Stereo Integrity numeric storefront SKUs and updated the Sundown source URL.
- Recovered the proprietary catalog to 6,460 records after a batch rebuild had
  reduced the generated view to 5,282, preserving the application loader count
  at 5,501.
- Added a growth watchdog baseline reset and protected proprietary-only records
  from removal during unified catalog rebuilds.
- Verified catalog checks, Streamlit report rendering and the full active
  suite: **176 PASS, 0 FAIL, 0 SKIP**.

## 0.8.26 (2026-08-21)

- **High-performance catalog boot and binary cache acceleration**:
  - Embedded pre-matched retailer prices (`price`, `currency`, `url`) directly into the catalog datasets (`catalog_proprietario.json`, `catalog_lsdb.json`, `catalog_vituixcad.json`, `catalog_speakerboxlite.json`).
  - Added an atomic binary `.cache.pickle` acceleration layer in `src/presets.py` with source JSON `mtime` validation and fail-safe fallback, cutting catalog disk load from 1.35s to 0.07s.
  - Disabled Streamlit AST runner magic in `.streamlit/config.toml` (`magicEnabled = false`, `fastReruns = true`) for instantaneous warm reruns (<0.38s).
  - Replaced runtime fuzzy string matching with $O(1)$ direct catalog retrieval and memoized string tokenization in `src/pricing.py`.
  - Replaced heavy `@st.cache_data` array hashing on 13k-element preset lists in `ui_app.py` with `@lru_cache`, eliminating Streamlit serialization overhead.
- **Compact portable `.lfp` project serialization**:
  - Compacted `.lfp` export payload by pruning redundant null/NaN entries and bounding saved raw Bass Match candidate rows to the top 100 ranked candidates.
  - Slashed exported `.lfp` project file sizes from ~17 MB down to <30 KB while preserving 100% full-parameter design restoration and instantaneous local alignment.
  - Verified full active test suite passing fresh (**170 PASS, 0 FAIL**).

## 0.8.25 (2026-08-19)

- **Replaced Distributed Waveguides with Triple-Chamber 8th-Order Bandpass (AES e-Brief 546)**:
  - Implemented exact lumped acoustic circuit simulation for the symmetric triple-chamber 8th-order bandpass system (Dong, Shen, Chen, 2019):
    - Driver coupled between Chamber 1 (front, $V_1, f_1$) and Chamber 2 (rear, $V_2, f_2$).
    - Ports 1 and 2 vent internally into Chamber 3 (common plenum, $V_3, f_3$).
    - System radiates externally exclusively via Port 3 into the half-space acoustic load.
    - Accurately models the 8th-order transfer function $G(s)$ and triple displacement notches ($f_1, f_2, f_3$) in the cone excursion curve.
  - Added dataclasses `Bandpass8Alignment` and `Bandpass8Box`, with auto-alignment function `suggest_bandpass8_alignment()` and simulator `simulate_bandpass8()`.
  - Fully integrated into the acoustic load peer family (`BoxUnion`), coordinate-descent optimizer, design space atlas, Bass Match finder, and snapshot comparison engine.
  - Integrated into Streamlit dashboard `ui_app.py` with 3-chamber volume & tuning controls, 3-port duct sizing, port velocity series, response markers, and metrics summary.
- **Stable BP8 optimization across drive-voltage edits**:
  - Removed the discontinuous 2.83 V threshold from excursion-rated port sizing; every positive simulation voltage now scales continuously to the same Xmax reference.
  - Prevented a 2.83 → 2.82 V edit from admitting a radically different, deeply tuned BP8 alignment through a smaller low-power port floor.
- **Reliable local Streamlit startup**:
  - Launch through the project virtual environment's Python module instead of a relocatable console-script shebang that could still point at another project.
  - Log the underlying driver-setup exception when Streamlit rejects a restored session, instead of leaving only the generic simulation error visible.
- **Compact portable `.lfp` project serialization**:
  - Compacted `.lfp` export payload by pruning redundant null/NaN entries and bounding saved raw Bass Match candidate rows to the top 100 ranked candidates.
  - Slashed exported `.lfp` project file sizes from ~17 MB down to <30 KB while preserving 100% full-parameter design restoration and instantaneous local alignment.
  - Verified full test suite passing fresh (**170 PASS, 0 FAIL**).

## 0.8.23 (2026-08-19)

- **Stateless file-based project management (`.lfp` upload & download)**:
  - Removed browser IndexedDB database persistence and cloud Firestore project storage to eliminate server-side data custody liability and ensure 100% user data privacy.
  - Replaced project database manager with an immediate, direct file workflow:
    - **Download `.lfp`**: Exports full portable project payload (T/S parameters, box alignments, simulation configurations, and Bass Match candidate results).
    - **Open `.lfp` / `.crw`**: Drag & drop uploader to restore projects or drivers from disk.
    - **New / Reset design**: One-click action to reset all parameters to clean starting defaults.
    - **Share via URL**: Stateless parameter sharing via URL query parameter (`?d=...`).
  - Removed experimental `streamlit.components.v2` dependency and background IndexedDB sync loop.
- **Documentation & test suite validation**:
  - Updated `docs/INDEX.md` and `docs/saas.md` to reflect file-based project architecture.
  - Verified full test suite fresh (**167 PASS, 0 FAIL**).

## 0.8.22 (2026-08-19)

- **Project name uniqueness enforcement**:
  - Enforced strict uniqueness across browser IndexedDB project names and SaaS cloud projects.
  - Active project renaming immediately detects colliding names, displaying a warning notification and preventing duplicate registration.
- **New Project name prompt workflow**:
  - Replaced immediate blank creation on "New project" with an inline creation prompt that pre-fills an auto-incremented unique default name (`Project 1`, `Project 2`, etc.) and requires confirmation.
  - Includes real-time collision validation, inline feedback, and a Cancel action to discard without modifying the active project.
- **Comprehensive acoustic documentation**:
  - Authored `docs/engine-manual.md` for clear acoustic and engine parameter usage.
  - Authored `docs/load-forge-innovations-manual.md` detailing all Load Forge exclusive features, algorithms, and acoustic advancements.
- **Test suite validation**:
  - Added project uniqueness and creation prompt regression tests in `tests/test_all.py`. Full test suite passing fresh (169 PASS, 0 FAIL).

## 0.8.21 (2026-08-18)

- **Acoustic shelf & saddle threshold coherence**:
  Enhanced `response_threshold_frequencies()` with a physical roll-off monotonicity
  check, preventing spurious midbass saddle crossings from placing $F_3$ in a shallow
  mid-band depression while $F_6$ and $F_{10}$ sit on the real low-frequency reflex knee.
- **Finder to Box Design ripple ceiling inheritance**:
  `_apply_batch_result()` now seamlessly carries over `finder_max_ripple_freq_hz`
  into `opt_max_ripple_freq_hz`, ensuring matching metrics and plots when opening
  candidate designs from Bass Match.
- **Test suite validation**:
  Verified full test suite fresh (98 PASS, 0 FAIL).

## 0.8.20 (2026-08-18)

- **Response threshold & chart marker cutout ceiling (`f_max_hz`)**:
  `response_threshold_frequencies()` and `response_metrics()` now accept `f_max_hz`
  to anchor sensitivity reference levels strictly within the active passband
  below the cutout ceiling and discard spurious crossings above it.
- **UI marker filtering & cache invalidation**:
  `_cursor_rows()` suppresses automatic threshold markers ($F_3, F_6, F_{10}$)
  above the active frequency ceiling; `_design_simulation_signature()` includes
  the cutout frequency to invalidate and refresh dashboard metrics and plots in real time.
- **Complete optimizer manual**:
  Authored comprehensive technical reference in `docs/optimizer-manual.md` covering
  coordinate descent (compass search), cost function formulation, rigid construction
  barriers, ripple ceilings, and multi-stage sampling.
- **Test suite validation**:
  Added `_check_response_thresholds_respect_frequency_cutout`; full test suite
  passing fresh (98 PASS, 0 FAIL).

## 0.8.19 (2026-08-18)

- **Configurable ripple ceiling (`ripple_max_freq_hz`)**:
  Added user-selectable frequency ceiling to the optimizer and Bass Match
  performance filters, restricting response ripple evaluation strictly to the
  intended operational sub-band (e.g. up to 70–100 Hz for dedicated subwoofers)
  and ignoring out-of-band midbass variations above the crossover frequency.
- **Segmented high-efficiency frequency grid (`segmented_frequency_grid`)**:
  Introduced two-tier frequency sampling allocating high logarithmic density in
  the operational passband below the ceiling and sparse evaluation (9 points)
  above it for rapid candidate ranking and optimization.
- **Suite and documentation synchronization**:
  Updated `docs/engine.md` and `docs/ranking.md` to document the segmented
  grid and ripple ceiling APIs; verified test suite (97 PASS, 0 FAIL).

## 0.8.18 (2026-08-18)

- **Multi-topology preservation in Bass Match (Finder)**:
  `_deduplicate_finder_result_rows()` now keys on driver identity, load topology,
  and resonator type, ensuring that all candidate load solutions remain visible
  and comparable when searching across multiple enclosure types simultaneously.
- **Strict acoustic ripple enforcement and passband linearity**:
  Eliminated the advisory scaling factor in `_score_alignment()` for `max_ripple_db`,
  imposing an unattenuated penalty on passband dips and excessive resonant saddles
  during optimization. Added explicit `max_ripple_db` post-simulation filtering
  in `_filter_finder_performance_rows()` to reject acoustically misaligned boxes.

## 0.8.17 (2026-08-17)

- **Redesigned landing page & authentication workspace**:
  Upgraded the local registration and enterprise OIDC login gates with a centered
  brand hero displaying `load_forge_header_app.png`, technical feature highlight
  badges (Adaptive TCAS Solver, Multi-Topology Matrix, Bass Match Finder),
  glassmorphic card styling, responsive input controls and verified security footer.

## 0.8.16 (2026-08-17)

- **Scientific revision of acoustic sampling documentation**:
  Formalized the Q-constrained logarithmic sampling criterion ($\Delta \ln f \le \frac{\kappa}{Q_{\max}}$),
  two-stage Top-K screening with Top-K Recall ($R_K$), adaptive curvature sampling,
  volume warm-start heuristic, and offline benchmark validation criteria
  in `docs/acoustic-sampling-optimization.md`.

## 0.8.15 (2026-08-17)

- **Acoustic Spectral Sampling Theorem (TCAS) runtime implementation**:
  `spectral_sampling_points` and `optimal_frequency_grid` runtime helpers
  formalize the logarithmic Shannon-Nyquist spectral sampling criterion
  ($\Delta \ln f \le \frac{1}{2 Q_{\max}}$) in `src/engine.py` and `src/acoustics.py`.
- **Streamlined, tiered test suite execution**:
  Added `--fast` (skipping heavy Streamlit AppTests to run 95 unit/physics tests in ~10s),
  `--ui`, `--smoke`, and `--time` flags to `tests/test_all.py` alongside `make test-fast`,
  `make test-smoke`, and `make test-ui` targets in `Makefile`.
  The fresh active suite passes 164 tests with 0 failures and 0 skips.

## 0.8.14 (2026-08-17)

- **Max extension starter volume seed at volume cap**:
  When optimizing under the `Max extension` objective with a total volume cap,
  the initial seed volumes are now initialized directly near 95–98% of the
  volume cap (scaling proportional chamber ratios), ensuring bounded pattern
  searches with compact budgets (e.g. 30 evaluations on Cloud) focus
  computational iterations on tuning refinement rather than scaling up volume.
- **Logarithmic frequency crossing interpolation for F3/F6/F10**:
  `response_threshold_frequencies` and crossing solvers (`_low_side_crossing`,
  `_high_side_crossing`) now use logarithmic frequency interpolation along
  dB/oct roll-off slopes, delivering sub-Hz precision on coarse grids and
  eliminating knee distortion in Finder simulation.
  The fresh active suite passes 163 tests with 0 failures and 0 skips.

## 0.8.13 (2026-08-17)

- **Finder/Box Design parity**: Finder results now carry the complete driver
  and enclosure-physics snapshots, including all acoustic loss factors and
  panel air-loading settings. Opening a match in Box Design reproduces the
  same simulation instead of inheriting stale session parameters.

## 0.8.12 (2026-08-15)

- **Fast, bounded Streamlit Cloud matching**: Bass Match now limits Community
  Cloud's reusable process pool to four workers, recovering CPU parallelism
  without duplicating the expanded runtime catalogs across processes. Preset
  names are resolved once in the parent and workers receive only compact T/S
  and table metadata, preventing the Cloud container from paging the complete
  external databases once per worker.
  Worker startup is verified within ten seconds and falls back to shared-memory
  threads on failure, eliminating the former unbounded safe-mode wait. The
  fresh active suite passes 163 tests with 0 failures and 0 skips.
- **Two-stage Finder optimization**: box candidates now use a 30-point
  full-band scan, then only the winning alignment receives 20 points
  concentrated around its estimated F3. This replaces the former 160-point
  grid per search candidate; Streamlit Community Cloud also caps the global
  search at 30 candidate alignments instead of 140, while retaining the
  selected high resolution for each final result row.
- **Finder-to-design consistency**: ranking revision 8 invalidates persisted
  rows produced before the two-stage optimizer, and each new result stores the
  exact hidden driver T/S and complete enclosure-loss snapshots used for
  ranking. Opening it in Box Design now preserves both snapshots instead of
  mixing an old box/session state with newer catalog parameters and producing
  a different F3. Empty load selections restored
  from older sessions now share the same active-load fallback during ranking
  and rendering, preventing fresh matches from disappearing as stale inputs.
- **Streamlit Cloud email gate**: native `st.login()` authentication can now
  protect the workspace independently from Firestore through
  `LOAD_FORGE_AUTH_REQUIRED`; an optional exact, case-insensitive
  `LOAD_FORGE_ALLOWED_EMAILS` allowlist rejects unauthorized identities before
  the simulator loads, while auth-only deployments retain browser-local
  project autosave and avoid initializing the cloud-project backend.
- **OIDC runtime dependency**: Streamlit Cloud now installs `httpx` alongside
  Authlib, preventing the first Sign in click from failing inside Authlib's
  Starlette client; a requirements regression keeps the lazy import covered.
- **Smaller Cloud container**: Docker and Cloud Build now whitelist only the
  six runtime catalog/price files under `data/`; archived datasheets, crawler
  state, source assets and reports stay out of both the upload context and the
  final image. The runtime data payload falls from roughly 613 MiB to 79 MiB.
- **Published-spec harvesting**: `tools/run_published_spec_batches.py` runs
  restartable atomic URL batches that complete one proven source domain
  through `refresh_manufacturer_optionals.py`, stopping on exhaustion, child
  failure or an excessive failure rate; datasheets and T/S crawlers now
  extract published specifications (nominal impedance, sensitivity, voice
  coil diameter, Xmech, nominal diameter) alongside mechanical fields.
- **Preset metadata**: `DriverPresetInfo` gains a tolerant `published_specs`
  mapping for source-backed numeric specifications not yet used by the
  solver.
- **Catalog Maintenance UI**: mechanical coverage metrics (any / essential
  four / all eight fields) and read-only columns for mechanical and
  published-spec data.
- **Test consistency**: ordinary Streamlit AppTest calls now share one
  `APP_TEST_TIMEOUT` (60 s), avoiding transient failures under consecutive
  loaded runs; release metadata has a synchronization regression test.
- **Streamlit compatibility**: UI elements use the current `width="stretch"`
  API instead of the deprecated `use_container_width=True` argument.
- **Neutral acoustic API**: `src/acoustics.py` is now the primary facade for
  every load family; `src/dccav.py` remains a backward-compatible alias, and
  targeted smoke tests cover all lumped and distributed topologies instead of
  selecting tests by the historical DCCAV name.
- **Verification**: fresh full active suite passes with 161 passed,
  0 failures and 0 skips.

## 0.8.11 (2026-08-12)

- **Complete nominal sizes**: drivers whose catalog record omits nominal frame
  size now receive the nearest conventional size class inferred from `Sd`,
  using the same mapping already used to repair incoherent size metadata.
  The rule covers external catalogs and built-in presets, leaving published
  source data distinct from runtime estimates.
- **Persisted Finder metadata**: saved project/session results refresh missing
  nominal sizes from the live catalog, so pre-fix rows no longer display
  `None` and do not require an unnecessary acoustic re-simulation.
- **Verification**: Python compilation, targeted DCCAV tests (31/31),
  Streamlit AppTest and the fresh full active suite (151/151) pass with
  0 failures and 0 skips.

## 0.8.10 (2026-08-12)

- **ZTZ Audio LF catalog**: imported 25 validated ferrite woofer presets from
  the manufacturer catalog, with source metadata and resumable crawl tools.
- **Passive radiators**: added catalog presets, added-mass support and correct
  effective tuning markers in Bass Match and Box Design.
- **Finder reliability**: invalidates worker pools when external catalogs
  change and retries serially when a stale worker pool returns no rows.
- **UI**: restored the dark green theme and made project opening neutral rather
  than destructive red.
- **Mechanical driver data**: added an optional `MechanicalDimensions` block
  for layout work and a responsive front/side drawing in Box Design; ZTZ
  records now expose published overall diameter, cutout, depth, bolt circle
  and weight without changing acoustic calculations.
- **Multi-manufacturer Finder**: live manufacturer selections are now read
  directly from the active multiselect, stale table selections are discarded,
  and mixed ZTZ/Scan-Speak/Beyma pools remain visible and rankable.
- **Verification**: Python compilation, Streamlit AppTest and the active suite
  pass with 0 failures.

## 0.8.9 (2026-08-09)

- **Distributed waveguides**: added first-order TL, MLTL, QW, BLH and TH
  acoustic-load models with editable Streamlit controls and library-driver
  support.
- **TH screening**: the initial tapped-horn view uses a 25–120 Hz LF window,
  warns when cone excursion exceeds Xmax and documents the required external
  high-pass/low-pass crossover limits.
- **Verification**: Python compilation, distributed-model tests (2/2) and the
  full active suite (151/151) pass.

## 0.8.8 (2026-08-07)

- **Per-design CRW export**: moved CRW download from the global Project menu
  into every editable design tab. Each download is generated from that tab's
  saved driver parameters, so projects containing multiple APs can export the
  intended design without first changing the active tab. CRW curve generation
  is deferred until the download action so normal simulations do not pay its
  201-point response cost.
- **Verification**: Python compilation and the Streamlit startup AppTest pass.

## 0.8.7 (2026-08-06)

- **Response tuning markers**: the response chart now shows labelled vertical
  markers for the active enclosure tuning frequencies, with a toggle to hide
  them and zoom-aware filtering.
- **F3/F6/F10 marker details**: automatic frequency markers show their MOL
  value again; the interactive frequency marker now spans the full chart
  height.
- **Administrator driver updates**: authenticated administrators can save
  edited Box Design T/S parameters back to the selected external catalog
  preset. Browser-project deletion now acknowledges only after its IndexedDB
  transaction commits.
- **Verification**: targeted response-chart and administrator catalog tests,
  Python compilation and the Streamlit startup AppTest pass with 0 failures.

## 0.8.5 (2026-08-04)

- **Box Design tab identity**: editable design tabs now show the normalized
  manufacturer / part-number pair instead of the single source-decorated driver
  name, alongside the load type and driver configuration, e.g.
  `1 · Beyma · 12CMV2 · DCCAV · 2 × parallel` (previously
  `1 · Beyma 12CMV2 (2 × parallel) · DCCAV`). Custom T/S designs keep a compact
  `load type · config` label. Finder batch imports, pinned-response legends and
  the legacy label parser all follow the same format. Tab labels wrap onto
  successive lines inside the button instead of being truncated with ellipsis,
  and the button grows to fit the wrapped text.
- **Verification**: the fresh active suite passes 144 tests with 0 failures and
  0 skips, including the editable-tab and Finder-to-tabs AppTests.

## 0.8.6 (2026-08-05)

- **MIL keeps its own right axis**: enabling the MIL trace in the Response
  chart no longer rescales the SPL curves. The final chart-level
  `resolve_scale` was overwriting the earlier `y="independent"` resolution
  whenever cursor markers or pinned responses were present, collapsing the
  watts curve onto the dB axis and squishing every other trace. The resolve now
  preserves the independent y scale while MIL is overlaid, keeping the dB
  domain anchored to the SPL reference.
- **MIL/MOL need a thermal rating**: drivers with `Pe=0` (no published power
  rating) no longer compute or plot the MIL curve. `_limit_curves` returns both
  MIL and MOL as `NaN` without a `Pe`, and the Response chart keeps the MIL/MOL
  buttons visible but renders no curve (previously an all-NaN `mil_w` crashed
  the chart builder). The excursion-only MIL is no longer offered for drivers
  that lack a thermal ceiling.
- **Verification**: the fresh active suite passes 146 tests with 0 failures and
  0 skips, including the MIL right-axis and no-thermal-rating regression
  checks.

## 0.8.4 (2026-08-04)

- **TLHP harvest pipeline fix**: the ToutLeHautParleur harvester previously
  merged accepted new drivers into the derived unified view
  `data/catalog_proprietario.json`, which is rebuilt from the source-of-truth
  `data/manufacturer_drivers.json` — so the next catalog rebuild silently
  dropped them. The harvester now merges into the source of truth and the 213
  already-harvested drivers were backfilled. The catalog grew from 5,064 to
  5,277 drivers and from 73 to 80 manufacturers, adding Audax, .Kartesian,
  AB Sound and DAS, and priced drivers rose from 4,143 to 4,314.
- **`--retry-failures` repaired**: a skip condition checked
  `url in completed_products` before the retry flag, and every rejected product
  was also recorded as completed, so the flag could never refetch a failed T/S
  page. The guard now lets failed products be revisited when the flag is set,
  enabling parser improvements to recover previously unimportable drivers.
- **Verification**: the fresh active suite passes 144 tests with 0 failures and
  0 skips, including the Streamlit startup AppTest.

## 0.8.3 (2026-08-04)

- **Automatic catalog completion**: a new restartable coordinator audits every
  driver, prioritizes brand/model gaps and probes each manufacturer on three
  records before expanding only sources with at least 50% measured yield. The
  first dedicated 18Sound pass recovered 144 published power values from 148
  records; zero-yield or blocked sources now stop after the probe and enter a
  30-day cooldown. Generic PDF discovery is opt-in after a 20-page pilot added
  no fields. The coordinator also runs the primary and regional price
  harvesters, applies only physical derivations and confidence-checked
  commercial matches, rebuilds unified catalogs and stops when coverage stalls.
  The crawler-agent planner ranks approved sources using existing optional-field
  gaps as well as absent brands.
- **Normalized runtime driver identity**: catalog source names remain stable
  internal keys while the selector, Finder library and ranked results expose
  separate manufacturer and part-number values. Decorated SB Acoustics titles
  and retailer product descriptions now display only their extracted product
  codes, such as `SB Acoustics` / `SB17NRXC35-4`, `Dayton Audio` /
  `RSS315HO-4` and `Beyma` / `12MC700Nd`; search, duplicate collapsing and CSV
  export use the same normalized identity.
- **Catalog Maintenance identity**: the editor hides source-decorated raw names
  and shows the same Manufacturer/Part number pair used at runtime. Beyma
  catalog titles such as `LOUDSPEAKER 8\"MC300Nd 8 OH` are presented as
  `Beyma` / `8MC300Nd` while the raw key remains stored for provenance.
- **Verification**: the fresh active suite passes 144 tests with 0 failures and
  0 skips, including the Streamlit startup and normalized SB identity checks.

## 0.8.2 (2026-08-03)

- **Cloud Run startup fix**: added the missing numeric columns (`Size in`,
  `Mms g`, `Le10k mH`, `Ripple dB`) to the UI table formats, preventing mixed
  catalog values from causing an Arrow serialization failure at startup.
- **Bass Match startup candidates**: the initial Bass Match render now loads
  its server-side preset names before computing pre-qualification, so the
  candidate count and Run button no longer incorrectly start at zero while
  the heavy Candidate pool table remains lazy.
- **Browser project management**: saved projects can now be duplicated with a
  unique name and complete design/Finder state, or permanently deleted from
  IndexedDB after an explicit confirmation, both before and after opening the
  project. Startup now leaves every saved project in the explicit chooser and
  recovers from missing or invalid IndexedDB payloads without a rerun loop.
- **Persistent library filters**: switching to Box Design and back now keeps
  Bass Match search, provenance, brand, size, class and price selections while
  avoiding mutation of Streamlit's live session-state iterator.
- **Verification**: the fresh active suite passes 141 tests with 0 failures and
  0 skips.

## 0.8.1 (2026-08-02)

- **Full-library price enrichment**: cached retailer offers now target the
  complete 14,066-driver runtime catalog instead of LSDB alone. The core four
  providers and sixteen complementary sources share one indexed, deterministic
  rematcher; checkpoints retain old observations through outages and preserve
  same-page variants by URL plus SKU/MPN.
- **New structured price sources**: added Thomann's embedded live catalog,
  exact-SKU DS18, impedance-expanded Fi Car Audio, Wavecor's official USD list
  and AUDIO-HI.FI's Tang Band catalog. The bundled data exposes 6,476 validated
  prices and 14,000 product/source links; unavailable historical/discontinued
  rows remain unpriced instead of receiving an inferred value.
- **Price integrity**: runtime and crawler matching now agree on brand aliases,
  explicit impedance, compact model codes, accessories/recone kits and exact
  MPN propagation across duplicate catalog tiers. A prune removed 235 stale or
  implausible observations before the catalogs were rematched.
- **Unified source catalogs**: each LSDB, proprietary/manufacturer, VituixCAD
  and Speaker Box Lite tier now has one self-contained T/S, provenance, price,
  availability and product-link catalog consumed by the runtime.
- **Administrator catalog maintenance**: the protected workspace renders every
  matching record without the former 1,000-row cap. Independent multi-row
  selection now drives explicit duplicate/delete actions; save updates only
  changed rows so untouched source provenance remains intact. Complete JSON
  backup and restore remain available.
- **Verification**: the fresh active suite passes 140 tests with 0 failures and
  0 skips after the catalog, pricing, crawler and maintenance changes.

## 0.8.0 (2026-08-01)

- **Hard maximum-F3 constraint**: Bass Match can now reject every simulated
  design whose F3 exceeds an optional user limit. The limit is persisted with
  projects, invalidates stale rankings, appears in the compact brief and has a
  dedicated no-match explanation; `0` keeps the constraint disabled. The fresh
  active suite passes 133 tests with 0 failures and 0 skips.

## 0.7.6 (2026-08-01)

- **Sub-second workspace reruns**: Bass Match no longer creates its process
  pool merely by being opened. Project actions, the 500-row Candidate pool,
  inactive Bass Match sidebar panels and inactive Box Design analysis charts
  now render lazily. Repeated AppTest workspace round trips fell from roughly
  2.3 s (Box Design) / 1.7 s (Bass Match) to 0.76 s / 0.68 s on the same local
  catalog and machine.
- **Bounded reusable data**: embedded load/workspace styles and the small
  catalog family/price summaries persist across Streamlit reruns with bounded
  caches. Large 12k–14k filtered-name lists remain in the already warm catalog
  module instead of being duplicated in Streamlit's serialized cache.
- **Compact library filters**: provenance, brand, size and class now use four
  multiselects with empty meaning `All`, replacing more than 400 individually
  rendered checkbox widgets while preserving the existing project-state
  format and workspace round trips.
- **Validation**: the fresh active suite passes 133 tests with 0 failures and
  0 skips, including a regression that opening or switching workspaces does
  not start Finder workers or eagerly render hidden charts and tables.

## 0.7.5 (2026-08-01)

- **Compact full-width Bass Match run**: `Run Bass Match` now spans the main
  workspace below the dense brief. While matching, a slim progress bar appears
  directly beneath the button with its status caption below the bar, preserving
  the shortest practical vertical flow.
- **Clean new projects**: `New project` now discards the previous design,
  Finder results, comparison/pinned curves, manual-box snapshots, plot state
  and any pending IndexedDB load before seeding the normal fresh-project
  defaults, so delayed browser state cannot repopulate the old project.
- **Stable Box Design updates**: routine IndexedDB autosaves no longer publish
  an acknowledgement or refreshed timestamp back into Streamlit, removing the
  extra full-page rerun after an enclosure edit. The last complete design also
  remains fully visible while the required calculation rerun is in progress;
  autosave failures still surface and retry on a later interaction. The
  Response graph now retains one mounted Vega view and a reserved scrollbar
  gutter, eliminating the repeated horizontal resize visible during updates.
- **Zero-waste design interactions**: deleting, hiding or duplicating a design
  now mutates state in the widget callback instead of simulating once and then
  forcing a second full rerun. Switching or deleting an active comparison tab
  reuses its saved enclosure without relaunching the automatic optimizer.
- **Warm Box Design pipeline**: unchanged driver/load/box simulations and base
  metrics are cached with automatic solver-source invalidation; unchanged tab
  snapshots are reused, default alignments are only seeded when absent and only
  the active load's starter alignment is derived for display. Chart keys and
  browser autosave compare compact snapshot revisions instead of repeatedly
  JSON-serializing every stored curve on each click.
- **Direct state transitions**: load cards, Finder-to-Box selection and Atlas
  application now prepare their target state before the next script run, avoiding
  intermediate renders and obsolete calculations.
- **Validation**: the fresh active suite passes 132 tests with 0 failures and
  0 skips, including a regression proving identical simulation inputs invoke
  the solver only once.
- **Complete Finder results**: Bass Match now displays every usable ranked
  candidate. The retired default-20 control and its 200-result ceiling are
  removed, including automatic cleanup of their legacy session state.
- **Selection-first Finder CTA**: the Box Design action now occupies the first
  row below the Bass Match brief instead of a redundant results heading. It is
  neutral and disabled without a selection, then emerald and active for the
  selected single design or eligible multi-design comparison.
- **Additive single-result workflow**: the first Finder result opened alone is
  now retained as editable Box Design tab 1. Returning to Bass Match and opening
  another single result appends tab 2 instead of replacing the first design;
  direct multi-selection and later additions keep the same eight-tab limit.

## 0.7.4 (2026-07-31)

- **Per-design visibility**: every standalone or comparison design tab now has
  a fixed eye action that hides or restores that design across compatible
  charts without deleting its parameters, identity, color or tab position.
- **Validation**: the fresh release suite passes 130 tests with 0 failures and
  0 skips.

## 0.7.3 (2026-07-31)

- **Additive Box Design workflow**: opening another Bass Match result now
  appends it to the existing editable design tabs instead of deleting the
  current comparison. Multi-row Finder selections follow the same additive
  behavior up to the eight-design limit.
- **Direct design management**: compact copy and close icons now live inside
  every Box Design tab rather than an expander or separate full-width
  action row. Every duplicate remains independently editable and deleting the
  last tab returns the current simulation to normal standalone Box Design mode.
- **Stable compact design tabs**: titles consume all available width before
  fixed copy/close actions and use `number · driver · load`. Driver identity
  and deterministic curve colors survive selection, duplication, deletion,
  legacy-state migration and renumbering without turning known presets into
  `Custom`.
- **Quiet controls**: transient command tooltips are suppressed while chart
  tooltips remain available for reading simulation values.
- **Stable Finder selection**: clicking a ranked Bass Match row no longer
  invalidates and hides the completed result list; actual input or filter
  changes still mark the results as stale. Background driver-price catalog
  refreshes no longer masquerade as user input changes.
- **Catalog refresh**: bundled driver-price observations include the latest
  retailer crawl results used by local value ranking.
- **Validation**: the fresh release suite passes 130 tests with 0 failures and
  0 skips.

## 0.7.2 (2026-07-31)

- **Pro editable design comparison**: selecting 2–8 Bass Match results now
  creates independently editable tabs in Box Design. The active tab uses all
  normal sidebar controls while every inactive driver/load/box design remains
  overlaid in the compatible response, excursion, impedance, MIL,
  group-delay and port charts. The active design can also be duplicated into
  a new variant tab for parameter A/B comparisons. Tab accents now mirror
  permanent reference-curve colors: the first design owns emerald and colors
  no longer rotate when the active tab changes. Response pens are transversal
  across designs for Total, Cone, port/radiator, MOL and MIL.
- **Standalone Finder result regression**: opening one Bass Match result now
  closes an older editable comparison before applying the selected driver,
  load and enclosure, preventing stale tab labels from absorbing the new
  design.
- **Project candidate restoration**: browser, cloud and portable LFP projects
  now restore the ranked candidate list, context and statistics from their
  last Bass Match run without recalculation. Restored rows remain visible when
  the old run used an ephemeral Candidate pool table selection, while changing
  a Finder input still hides them as stale. Browser project switching flushes
  pending run results before loading the next project.
- **Validation**: full active suite passes 130/130 with zero failures and zero
  skips; focused editable-tab, Finder multi-selection and Streamlit AppTest
  checks also pass.

## 0.7.1 (2026-07-30)

- **Automatic browser projects**: Load Forge now creates and autosaves a
  project in browser IndexedDB. Zero or one stored project opens
  automatically; with multiple projects the regular workspace opens with the
  Project section expanded in the sidebar. The section can rename, create,
  switch and download the active browser-local project.
- **Complete LFP v2**: portable `.lfp` backups now contain the Box Design
  parameters plus Bass Match constraints, library filters, ranked results and
  result context. Strict-JSON normalization removes non-finite placeholders;
  legacy flat format-v1 presets remain importable.
- **Fresh Bass Match results**: changing a calculation input or the filtered
  candidate pool (including the driver-size filter) now hides stale rankings
  and asks for a new Bass Match run.
- **Coherent driver diameters**: external nominal sizes are checked against
  the effective piston diameter represented by `Sd` with a tolerant physical
  window. Incompatible model-number guesses fall back to the nearest
  conventional size class; the verified Markaudio Alpair 10P is corrected
  from 10 in to 5 in. The tolerance was tightened after the Ciare FXC8.50W
  exposed a false-positive 10-inch label; its 211.2 cm² piston now resolves to
  the verified 8-inch class.
- **Project startup**: removed the separate multi-project landing page.
  Multiple browser projects now open the regular app with the collapsible
  Project section expanded automatically in the sidebar.
- **Validation**: full active suite passes 128/128 with zero failures and zero
  skips; Streamlit AppTest, the complete-LFP regression and the multi-project
  non-blocking sidebar-startup regression also pass.

## 0.7.0 (2026-07-29)

- **SaaS foundation**: added an opt-in OIDC account gate, tenant-scoped
  Firestore project persistence, local in-memory development backend,
  optimistic project revisions and server-side Free/Pro/Team entitlement
  seeds; the Project menu can now save, list, refresh and reload authenticated
  cloud designs without changing the existing non-SaaS deployment.
- **SaaS safety and deployment contract**: documented Secret Manager-mounted
  Streamlit OIDC configuration, added tracked secret templates and explicitly
  reject the local authentication bypass when Cloud Run identifies the
  process through `K_SERVICE`.
- **Local account trial**: added a development-only registration, sign-in and
  sign-out experience backed by a permission-restricted SQLite account
  registry with normalized emails and salted scrypt password hashes.  Local
  accounts are rejected on Cloud Run, where registration, verification,
  recovery and MFA remain the responsibility of the configured OIDC provider.
- **Open Beta entitlement**: added a server-side promotional override that
  grants registered Free and Pro accounts the current Pro access tier without
  changing their stored plan or creating a subscription; the Project menu
  exposes the active beta state and enforces its effective cloud-project quota.
- **Experimental measurement import removed**: removed the session-only
  FRD/ZMA acquisition, overlays and partial free-air T/S estimation because
  they did not provide a complete measurement-to-design workflow. Existing
  simulated FRD/ZMA downloads remain available.
- **UI/UX reliability and focus pass**: Finder catalog filters now survive
  Bass Match/Box Design round trips instead of collapsing `All` into an empty
  selection. Empty libraries offer one-click recovery; expert Finder and
  driver inputs use collapsed advanced sections. Bass Match is now the main
  product flow: a live acoustic brief leads to one `Run Bass Match` action,
  results are presented as complete driver/load/box matches and the raw driver
  library is a collapsible candidate pool. The brief and CTA now share one
  compact row and a dense always-visible grid exposes every enclosure,
  performance, driver, library and evaluation constraint, including disabled
  states. The active scan uses a prominent full-width progress bar, completion
  feedback is a transient toast and the fixed-height results table scrolls
  internally, preventing the normal Finder state from growing the page
  vertically. Constraint labels and values are larger for at-a-glance reading.
  The Finder-only `Desired F3` control is retired because it was a soft
  optimizer preference rather than a dependable ranking constraint. Known
  constraints now reduce the
  queue before simulation: reference SPL at the selected voltage, driver
  configuration, T/S validity and required Xmax are pre-filtered per load;
  the UI reports eligible and skipped counts, while F3, MOL, ripple, excursion
  and delay remain simulation-derived hard checks. Physical duplicates across
  catalogs are collapsed before simulation, preferring Load Forge provenance
  and then the lower available price; multiple successful loads for the same
  driver collapse to its best-ranked design. Automatic F3/F6/F10 chart labels
  are compact; design exports are grouped; score and status language is more
  explicit.
- **Agent-driven crawler service**: split catalog discovery into an independent
  Cloud Run Job with direct-website allow-lists, robots-aware bounded crawl
  plans, coverage-gap prioritization and staging-only credentials.  Aggregated
  driver databases are rejected by policy; a separate human-approved
  promotion step validates provenance and physics, then creates an immutable
  manufacturer-catalog release for the SaaS to mount read-only.
- **Preset-load completion**: consume each uploaded `.lfp`, JSON or CRW file
  exactly once and reset the Project uploader before rerunning, preventing the
  permanent dimmed loading overlay caused by an infinite preset reload loop.
- **Validation**: full active suite passes 126/126 with zero failures and zero
  skips; the focused preset double-upload, authenticated SaaS project
  round-trip, Finder filter round-trip/reset, local registration/login/logout
  and crawler policy/release regressions plus the standalone Streamlit AppTest
  complete without exceptions.

## 0.6.9 (2026-07-28)

- **Compact Finder results**: removed brand, F6, F10, ripple and maximum
  excursion from the ranked-results table/CSV, restored nominal `Size`, added
  piston area `Sd`, shortened `Total volume` to `Vtot`, and reduced candidate
  preview metrics to F3, MOL at F3, peak LF SPL and minimum impedance; all
  per-chamber volumes, tuning/system frequencies and alignment details are now
  represented by one total-volume field, while hidden engineering values
  remain available to ranking, constraints and applying a candidate.
- **Compact class label**: Finder filters, result rows and Design metrics show
  `Midbass` instead of the longer internal classifier value
  `Midbass-capable`.
- **Compact database provenance**: grouped built-ins, direct manufacturer
  sources, official archives, retailer observations and user-supplied records
  under one `Load Forge database` Finder choice, while keeping LSDB,
  VituixCAD and Speaker Box Lite independently selectable and preserving the
  exact source on every row.
- **SB Acoustics identity deduplication**: collapsed 72 duplicate Load Forge
  observations by stable manufacturer part number, including decorated
  SATORI product titles, revision PDFs and retailer copies; official crawler
  T/S data wins, exact retailer prices still enrich the retained row, and
  LSDB/VituixCAD/Speaker Box Lite observations remain separate.
- **Validation**: full active suite passes 117/117 with zero failures and zero
  skips; the standalone Streamlit AppTest also completes without exceptions.

## 0.6.8 (2026-07-28)

- **Catalog provenance categories**: kept all catalog tiers while making
  official manufacturer sites, official archives/heritage,
  retailers/distributors, LSDB, VituixCAD, Speaker Box Lite, built-ins and
  user-supplied records independently visible and filterable in Finder.
- **Library-filter All toggle**: `All` now visibly selects or clears every
  option in Provenance, Brand, Size and Class; excluding one item preserves
  all remaining selections instead of collapsing the group back to `All`.
- **Massive VituixCAD catalog tier**: added a validated, provenance-preserving
  importer for VituixCAD's 1,879-row public online database and exposed 1,038
  LF models not already present in manufacturer or LSDB tiers.
- **Physically validated car/pro catalog expansion**: added a separate
  Speaker Box Lite community tier with 1,952 new LF models across 283 brands
  after rejecting incomplete records, enforcing the `Qts/Qes/Qms` identity,
  resolving mixed `Sd` units and cross-checking `Sd` against `Vas/Cms`.
  Together with VituixCAD and the heritage imports below, this raises runtime
  coverage by 3,063 models to 13,928 selectable driver presets after current
  manufacturer-identity deduplication, across
  four separate external provenance tiers.
- **Altec and TAD heritage catalogs**: imported 63 Altec Lansing models from
  the corrected Technical Letter 267B table and 10 TAD professional LF models
  from Pioneer/TAD's official specification table, with exact unit conversions
  and source-field derivations retained.
- **MISCO official catalog crawl**: added 50 validated woofer, subwoofer,
  midbass, midrange and full-range drivers with stable manufacturer model
  numbers, complete core T/S data and official provenance; hardened the
  generic crawler against inline `Fs` tolerances, related-product tweeters,
  missing visible `Model #` metadata, IEC268-5 power rows and dropped `Qes`.
- **Sd/nominal-size audit**: reconciled the manufacturer catalog against
  equivalent piston diameter, fixed 26 damaged `Sd` values and 591 nominal
  sizes with traceable provenance, and excluded 11 unresolved contradictory
  records from runtime selection.
- **Driver size visibility**: the selected-driver summary and Finder library
  now show nominal frame size, `Sd` and equivalent effective-piston diameter
  together.
- **Crawler size parsing**: mixed inch fractions are parsed as complete values
  and numeric model prefixes must agree with `Sd`, preventing `6-1/2"` from
  becoming 2 inches and metric family codes from becoming inch sizes.
- **Max extension alignment**: relax the DCCAV deep-extension feasibility floor
  to `F3 >= 0.65*fl` for the explicit Max extension objective; balanced and
  flat objectives retain the conservative `0.67*fl` boundary.
- **Finder multi-driver**: added single, wired-pair and isobaric-pair
  configuration to candidate ranking and result application.
- **Scalable driver arrays**: restored series, parallel and mixed arrays up to
  eight drivers plus isobaric arrays up to 16 total drivers; thermal power now
  scales with the complete physical driver count.
- **Max-extension preset search**: start untargeted DCCAV extension searches in
  the deep-alignment basin and make credible F3 dominant over advisory
  compactness/response penalties.
- **Finder MOL at F3**: calculate the excursion/thermal limited output at each
  candidate's interpolated F3, show it in results and previews, and expose a
  hard minimum-MOL performance filter.
- **Finder Mms/Le filters**: added optional maximum moving-mass and nominal
  voice-coil-inductance limits to Performance filters; active limits exclude
  candidates whose corresponding published value is missing.
- **Tests**: 117 passed / 0 failed / 0 skipped.

## 0.6.7 (2026-07-27)

- Add multi-select checkbox filters for source, brand, size and class in the
  Candidate Library.
- Add adaptive Cloud Run Finder optimization with reduced evaluations and
  resonance-focused frequency sampling.
- Add reproducible Cloud Run deployment files and documentation.
- Verification: 108 passed, 0 failed, 0 skipped tests.

## 0.6.6 (2026-07-25)

- **Emerald visual system**: replaced red selection/action accents with a
  consistent emerald palette across workspace tabs, load cards, Run controls,
  primary response traces and engineering limit markers.
- **Dark sidebar and branding**: made the complete sidebar black and increased
  logo contrast while keeping Bass Match and Box Design at the same visual
  intensity.
- **Instruction bands**: replaced Streamlit's default blue information bands
  with emerald actionable guidance and neutral-gray secondary instructions.
- **Above-the-fold response view**: reduced the main response/MIL chart from
  600 px to 420 px so its controls and active-load summary fit typical desktop
  viewport heights without main-page scrolling.
- **Release metadata and docs**: synchronized `VERSION`, package metadata,
  README and the UI contract for 0.6.6.
- **Tests**: 108 passed / 0 failed / 0 skipped.

## 0.6.5 (2026-07-25)

- **UI regression fixes**: restored stable acoustic metric labels, native
  diagnostic warnings and topology explanations for DCCAV, bandpass,
  bass-reflex, sealed and infinite-baffle designs.
- **Finder fixes**: keep the Run a Match action visible and disabled when
  catalog filters return no candidates, and hide enclosure-only optimization
  constraints when matching infinite-baffle drivers.
- **Response chart**: restored the full 600 px analysis height so zoomed and
  overlaid traces remain readable.
- **Tests**: 108 passed / 0 failed / 0 skipped.

## 0.6.4

- Fix sidebar logo and version overlap
- Reduce side padding in main container

## 0.6.3 (2026-07-22)

- **Performance fix (interaction lag)**: every rerun — selecting a candidate
  row, switching Bass Match ↔ Box Design, any widget change — was shipping
  ~8 MB of base64-embedded PNGs to the browser inside the load-type card and
  workspace-tab CSS. The assets are now sized for their actual on-screen
  rendering (~580 KB total inline payload), which removes the multi-second
  stall on each interaction.
- **Frontend payload caps**: the candidate library table now shows at most
  500 rows and the Box Design driver-preset dropdown at most 1000 options
  (the current selection stays pinned); search and library filters narrow
  the rest. This keeps per-rerun serialization of the 10k-preset catalog
  from dominating interaction time.
- **Tests**: 107 passed / 0 failed / 0 skipped.

## 0.6.2 (2026-07-22)

- **Performance fix**: eliminated the multi-second "Run match" startup stall by
  keeping the parallel Finder worker pool warm across reruns (previously
  recreated, and its workers re-imported the stack and rebuilt the driver
  catalog, on every click) and pre-warming it as soon as the Bass Match
  sidebar opens. Chunk size and progress-update cadence were also tightened
  so the progress bar starts moving immediately instead of stalling on the
  first batch.
- **Performance fix**: sidebar catalog filtering (price and driver-class
  filters) no longer re-fetches the cached ECB exchange rates once per preset
  across the ~10k-entry catalog, and the driver-class classifier cache now
  survives Streamlit reruns instead of restarting cold every time.
- **Manufacturer catalog**: expanded the manufacturer-crawled driver database
  to 28 brands with dedicated dedupe, metadata-enrichment and optional-field
  refresh tools, plus a regeneratable coverage/quality status report.
- **Tests**: 107 passed / 0 failed / 0 skipped.

## 0.6.1 (2026-07-20)

- **Performance Fix**: Added aggressive LRU caching to driver metadata and pricing resolution to prevent the UI from locking up during real-time filtering, restoring instantaneous responsiveness.
- **Parallel Optimization**: Restored the high-performance parallel driver search engine for matching presets, which is now fast again thanks to the caching fixes.
- **Tests**: 103 passed / 0 failed / 0 skipped.

## 0.6.0 (2026-07-20)

- **UI Redesign**: Moved all inputs, parameter controls, library filters, and optimization constraints to a dedicated tabbed sidebar, decluttering the main column for a cleaner output presentation.
- **Workflow alignment**: Consolidated UI into "Bass Match" and "Box Design" modes using large visual tabs, eliminating deep expanders and ensuring advanced constraints are immediately visible.
- **Tests**: Realigned the comprehensive UI regression suite to support the new sidebar workflow. 103 passed / 0 failed / 0 skipped.

## 0.5.13 (2026-07-20)

- **UI improvements**: added CSS transitions to the search progress bar for fluid updates and made the preset size filter more granular (1 to 21 inches).
- **Tests**: 103 passed / 0 failed / 0 skipped.

## 0.5.12 (2026-07-20)

- **Performance regression**: restored parametric search speed and tab switching fluidity by properly caching the new manufacturer presets aggregator (`_external_tiers`).
- **Tests**: 103 passed / 0 failed / 0 skipped.

## 0.5.11 (2026-07-20)

- **Manufacturer presets**: added `_load_manufacturer_presets()` to load presets crawled directly from manufacturer sites, ensuring they are independent and safe to ship publicly.
- **Price enrichment**: fetched and updated the latest driver pricing data.
- **Data crawling tools**: updated T/S data and datasheet crawling scripts and their accompanying documentation.
- **Verification**: py_compile, Streamlit AppTest and fresh full suite: 103 passed / 0 failed / 0 skipped.


## 0.5.9 (2026-07-19)

- **Chart control consolidation**: addressed wasted vertical space under the response plot by combining toggles (`Show traces legend`, `Compare loads`, `Tolerance band`) and action buttons (`Pin response`, `Reset zoom`, `Clear all pins`) onto a single, dense horizontal row. The `Chart zoom` slider now spans the full layout width just below them.
- **Port and volume grid alignment**: re-organized UI metric grids for complex loads (DCCAV and Bandpass), merging the sub-volumes (`Vh/Vl`, `Vr/Vp`) into the exact same rows as their respective port tuning and port sizing metrics. This provides perfect `Volume | Tuning | Size` columnar alignment and saves substantial vertical space.
- **Port diameter recalculation**: corrected a Streamlit `@st.fragment` callback behavior affecting the port geometry inputs. Modifying the diameter now explicitly forces an app-wide rerun, ensuring that the new value correctly triggers the duct length recalculation in the global state.
- **Chart width resilience**: replaced invalid `width="stretch"` attributes with `use_container_width=True` on all `st.altair_chart` calls. This ensures charts (such as the response and impedance plots) properly expand to fill the entire container horizontally when zooming the X-axis domain, rather than getting physically cropped.
- **Verification**: py_compile, Streamlit AppTest and fresh full suite: 103 passed / 0 failed / 0 skipped.


## 0.5.8 (2026-07-19)

- **Acoustic Alignment Forge Score**: Added a dynamic, drive-and-physical-sanity-aware score (0-100) to `active_load_summary` displaying in real-time. It applies penalty points for warnings, excursion violations, and port sizing/tuning limitations.
- **Dynamic Gamification Badges**: Implemented live feedback badges including `🛡️ Safe from Chuffing`, `🏆 Legendary Extension`, `🔊 Deep Bass Accord`, `🎵 Tight Bass`, and `✅ Acoustically Sane` in the load summary card with corrected status/performance colors (green/blue/teal) to prevent cognitive dissonance.
- **Visual Hierarchy Refactor**: Re-centered the cabinet layout diagram at the top of the summary card at an increased size (`width=220px`), placing the other text description elements below it in a compact centered typography to elevate visual hierarchy.
- **Layout Inversion**: Moved the entire active load summary, warnings, and design details blocks below the main frequency response and technical charts to ensure the graphs are the absolute first element the user sees when opening the design tab.
- **Verification**: py_compile, Streamlit AppTest, and fresh full suite: 103 passed / 0 failed / 0 skipped.


## 0.5.7 (2026-07-19)

- **Active DCCAV volume warning**: the small-12-inch warning now evaluates the
  box currently being simulated instead of the smaller empirical starter.
  Optimized boxes such as `34.68 + 40.32 = 75.00 L` no longer display a
  misleading `21.4 L` warning.
- **Context-safe guidance**: genuinely small active boxes still warn about
  gross volume, port displacement, air velocity, compression and max-SPL
  verification without incorrectly attributing manual or optimized values to
  the empirical formula.
- **Verification**: py_compile, dedicated active-box regression, targeted
  29-test DCCAV run and Streamlit AppTest clean; fresh full suite 102 passed /
  0 failed / 0 skipped.


## 0.5.6 (2026-07-19)

- **Bass Match and Box Design workspaces**: replaced the compatibility-first
  workspace switch with large, directly clickable branded tabs while retaining
  the hidden state-compatible control for existing sessions and automated
  clients.
- **Finder workflow and feedback**: consolidated driver matching around one
  main `Run a Match` action, moved dense library filters into the wider main
  workspace and added one live progress indicator across serial and parallel
  candidate ranking, including the worker-process fallback path.
- **Sidebar and control polish**: enlarged illustrated load cards, moved their
  labels below the diagrams, improved spacing and responsive behavior, and
  standardized number-input steppers so every field shows one aligned `-/+`
  pair without duplicated or wrapping controls.
- **Catalog and examples**: refreshed the retailer price dataset and bundled
  reference Bass Match projects in Load Forge and AFW-compatible collections,
  together with their distributable archives and usage notes.
- **Documentation and product-design guidance**: synchronized the README, user
  guide, DCCAV/ranking references and package metadata with the 0.5.6 UI, and
  added the reusable UX/UI audit and redesign prompt.
- **Verification**: py_compile, targeted 29-test DCCAV run and Streamlit AppTest
  clean; fresh full suite 101 passed / 0 failed / 0 skipped.


## 0.5.5 (2026-07-18)

- **Multi-simulation pins**: up to eight load/driver/box simulations can be
  pinned together with stable colors. Pinned curves now follow every compatible
  analysis view: SPL response, cone excursion, impedance, MIL, port/radiator
  volume velocity and group delay.
- **Per-pin controls**: each pinned simulation can be hidden and shown again
  without deleting it, or cleared individually; a separate action still clears
  the full collection. Legacy single-response pins remain readable.
- **Complete interactive driver library**: the Finder now renders every
  filtered loudspeaker in a fixed-height scrolling table instead of truncating
  the catalog at 500 rows. Selecting a row exposes a direct action to load that
  driver into the Design simulation, and the library remains visible alongside
  ranked Finder results.
- **Workspace and manual-design resilience**: driver application is performed
  before Streamlit recreates workspace widgets, fixing the redacted state error
  seen after selecting a library row. Manual box values and the active design
  are preserved more reliably across strategy and Finder/Design transitions.
- **UI consolidation**: response analysis, port controls and project restore
  behavior were tightened while keeping long-lived Streamlit sessions and the
  previous pin format compatible.
- **Verification**: py_compile and Streamlit AppTest clean; full suite
  101 passed / 0 failed / 0 skipped.


## 0.5.4 (2026-07-18)

- **Generic Thiele/Small crawler**: added a resumable, robots-aware crawler for
  manufacturer pages, catalog links, XML sitemaps and optional PDF datasheets.
  It extracts T/S data from visible text and JSON-LD, normalizes engineering
  units, derives compatible missing values and rejects incomplete or physically
  implausible records.
- **Safe catalog population**: crawler results are deduplicated by brand/model
  and merged atomically into the driver database without replacing curated
  values by default. Each imported row retains its URL, timestamp, confidence,
  extraction method and raw source measurements.
- **Catalog integration and documentation**: the UI can filter `Web crawler`
  entries, the preset loader preserves per-row source provenance, and the new
  workflow is documented with dry-run and production examples.
- **Real-source qualification**: added support for storefront labels such as
  `Surface Area of Cone` and typographic units including `cm²` and `ft³`.
  A robots-compliant 100-page SoundImports qualification identified nine
  validated Dayton Audio part-number aliases at 0.925 extraction confidence.
- **PDF-first datasheet library**: added external PDF discovery, SHA-256
  content-addressed storage, a SQLite provenance/observation index and strict
  PDF-backed alias matching. Manufacturer part numbers can now be attached to
  existing marketing-name records without fuzzy-merging the whole catalog. The
  first nine archived datasheets consolidated all provisional Dayton rows into
  their existing Apollo records.
- **Retailer URL resilience**: price enrichment now percent-encodes Unicode
  characters from retailer sitemaps without double-encoding existing escapes;
  typographic size fractions can no longer crash an entire provider worker.
- **AFW comparison parity**: the sealed-project bridge now uses the active
  Load Forge engine and reports the panel-loaded result (+0.057% for the FE126)
  alongside the historical classical +4.942% delta.
- **AFW BP4/BP6 validation**: extended the read-only AFW bridge to load codes
  3 and 4, added loss-aware bandpass simulations and reproducible impedance,
  response and F3 diagnostics. The real FE126 BP6 project now agrees at the
  three observed impedance resonances (48.10, 110.98 and 239.80 Hz).
- **Sixth-order acoustic polarity**: corrected the two opposite-side vents to
  combine as a vector difference, eliminating the artificial mid-band notch;
  equal branches now cancel and the starter alignment is asymmetric.
- **Multiple-driver panel loading**: composite drivers track the number of
  externally radiating pistons, preserving per-cone mounted Fs for ordinary
  pairs while retaining one radiating piston for isobaric pairs. AFW bandpass
  reports can project all supported series/parallel/isobaric configurations.
- **Verification**: py_compile, Ruff and Streamlit AppTest clean; full suite
  101 passed / 0 failed / 0 skipped.


## 0.5.3 (2026-07-16)

- **Finder volume-cap regression**: restored Maximum volume as an upper bound
  instead of forcing every candidate onto the selected litre value. Optimized
  rows may use a smaller enclosure when it produces the better alignment.
- **Result migration**: Finder ranking revision 2 invalidates cached/session
  rows produced by the old exact-volume behavior, so existing local sessions
  cannot continue displaying the obsolete full-cap enclosures.
- **Verification**: py_compile and Streamlit AppTest clean; full suite
  95 passed / 0 failed / 0 skipped.


## 0.5.2 (2026-07-16)

- **Illustrated load picker**: replaced the emoji load buttons with compact,
  directly clickable diagram cards in a three-column grid. Load names are
  overlaid on the images, the active selection has a red checked outline, and
  the current Design load is echoed by a 44 px preview beside the result metrics.
- **Bundled load artwork**: added optimized local diagrams for infinite baffle,
  sealed, bass reflex, fourth- and sixth-order bandpass, and DCCAV. Refreshed
  the sealed, reflex, BP4, BP6 and DCCAV cards with the supplied revised icons.
- **Full-bleed brand header**: the 1200×100 banner now breaks out of Streamlit's
  content gutters on desktop and mobile, reaching both edges of the main page.
- **Correct resonator hierarchy**: passive radiator is no longer presented as
  a seventh load topology. Bass reflex now exposes `Ports → Resonator type`
  (`Port` or `Passive radiator`) in Design and Finder, while old PR presets are
  migrated to the new state automatically.
- **Finder minimum-SPL constraint**: forwards the threshold into each candidate
  optimization and removes rows whose simulated Peak LF SPL is below it. An
  explicit no-match state replaces the stale or unfiltered candidate table.
- **Documentation**: synchronized the README, user guide and module index with
  all six supported load types, the new visual selector and PR submenu.
- **Verification**: py_compile and Streamlit AppTest clean; full suite
  95 passed / 0 failed / 0 skipped.


## 0.5.0 (2026-07-15)

- **Sixth-order bandpass topology**: new `Bandpass6Alignment` / `Bandpass6Box` with
  dual-vented chambers (ported rear + ported front). `simulate_bandpass6()` solves
  the coupled acoustic circuit; `suggest_bandpass6_alignment()` returns a symmetrical
  starter from the classical Qbp relation. Full integration in Design workspace sidebar
  (Vr/Fr/Vp/Fp, loss factors, dual port geometry), Response/Ports tabs, Finder ranking,
  optimizer, atlas, and Monte Carlo.
- **Bandpass diagnostics**: both 4th and 6th order now flag undersized boxes
  (< 50 % Vas), collapsed sensitivity (> 9 dB below driver reference), and
  excessively wide passband (> 4:1) that indicates the bandpass character is lost.
- **Finder UI restructure**: the single load-type selectbox is removed in Finder mode;
  the "Loads to compare" multiselect is the sole load selector. Comparison volume moved
  into always-visible constraints. Library filters always visible (no expander).
- **Finder results table**: before running the ranking, the main area shows the
  filtered preset list as a sortable dataframe with key T/S values.
- **Tests**: 94 passed / 0 failed / 0 skipped.


## 0.4.9 (2026-07-15)

- **Passive radiator topology**: new `PassiveRadiatorBox` dataclass with
  `simulate_passive_radiator()` replacing the Helmholtz port by a suspended
  diaphragm (Sp, Fp, Qmp, Mmp). The PR adds a compliance branch to the
  vented-box acoustic circuit, producing two impedance peaks. `suggest_pr_alignment()`
  returns a starter box tuned near Fs. PR is available in the Design workspace
  sidebar with dedicated controls, in the Finder, and in the Ports tab
  (radiator volume velocity + excursion warning).
- **Tests**: 91 passed / 0 failed / 0 skipped.


## 0.4.8 (2026-07-15)

- **Finder "Minimum SPL" constraint**: restricts ranked candidates to those
  reaching at least the requested peak SPL at the comparison voltage.
  `OptimizationGoals.min_spl_db` penalises boxes whose `max_spl_db` falls
  below the target (0 disables).
- **Tests**: 90 passed / 0 failed / 0 skipped.

## 0.4.7 (2026-07-15)

- **Multi-load Finder**: the Finder sidebar now exposes a "Compare loads"
  multiselect so candidates can be ranked across several load types
  simultaneously (e.g. reflex, DCCAV and sealed in one scan).  Each result
  row carries a "Load" column; applying a candidate switches the Design
  workspace to that load type.
- **`rank_preset_row`** tags every returned row with `_load_type` so the UI
  can interleave results from different loads in a single sorted table.
- **Tests**: 90 passed / 0 failed / 0 skipped.

## 0.4.6 (2026-07-15)

- **Port sizing follows the gold standard** (`dimensionamento_bass_reflex.md`):
  replaced the Small/Dickason golden rule `Dmin = 20.3 * (Vd²/Fb)^0.25` with
  `S = K * (2π·Fb·Sd·Xmax) / v_amm` (K = `PORT_K_FACTOR`, v_amm = 5% of c).
  The new formula grows with tuning frequency (D ∝ √Fb) because the cone
  cycles faster and produces more volumetric flow at higher Fb.
- **End correction tuned to the gold standard**: flanged end k=0.82, free end
  k=0.61 → defaults change from 1.463→1.43 (one flanged + one free) and
  1.7→1.64 (two flanged).
- **Port velocity floor scales to the excursion limit**: `rated_velocity_diameter_cm`
  scales the peak port volume velocity to the driver's Xmax-limited drive
  level instead of the simulation voltage. At 2.83 V a powerful driver barely
  moves, making the raw velocity floor negligible — the new floor reflects
  real-world usage.
- **Finder excludes drivers without published Xmax** from ported-load
  rankings (DCCAV, reflex, bandpass). Sealed and infinite-baffle loads are
  unaffected.
- **Tests**: 90 passed / 0 failed / 0 skipped.

## 0.4.5 (2026-07-15)

- **Fix: reflex/DCCAV port sizing could still exceed the duct-volume
  directive** (user report: "duct of 4.5 x 84.6 cm" persisting after 0.4.4).
  The optimizer's feasibility metric and the UI's applied port diameter were
  two independent sizing implementations that disagreed on the air-speed
  safety margin, on whether reaching a fabricable ~5 cm duct length could
  override the 10% duct-volume cap, and on which direction to round to the
  sidebar's 0.5 cm grid (rounding up alone was enough to re-break a
  boundary-case optimum). A sweep found 27 volume/tuning pairs the optimizer
  called compliant that the UI still applied over the cap. Both call sites
  now share one sizer, `port_diameter_for_load()`, which grows toward a
  fabricable duct but never past the 10% cap and rounds down to the grid
  whenever that stays within the mandatory floor.
- **Fix: optimizer falsely reporting "no buildable box"**, found while
  verifying the sizing fix above: encoding "no diameter satisfies every
  directive" as an infinite score flattened the pattern search's gradient
  across the whole infeasible region, so `optimize_alignment` could fail to
  find a bass-reflex box that clearly existed just outside the empirical
  starting point (reproduced across every volume cap for one real driver).
  The infeasible score now stays a smoothly-varying quantity, restoring the
  search's ability to descend out of that region.
- **Verification**: py_compile, Ruff and Streamlit AppTest clean; full suite
  88 passed / 0 failed / 0 skipped.

## 0.4.4 (2026-07-15)

- **One box algorithm, three objectives**: replaced the overlapping
  `Suggested` / `Optimized` empirical-vs-optimizer split with a single
  optimizer-driven `Max extension` / `Balanced` / `Flattest` / `Manual`
  strategy. Every automatic box re-applies on driver, load or constraint
  changes; the empirical starter now only seeds the search. The Finder's
  "Optimize enclosure per candidate" toggle is retired — ranking always goes
  through the same optimizer at the fixed comparison volume, and always scans
  every preset the sidebar filters admit (the manual "Drivers to evaluate"
  cap is gone). Older `.lfp` files, share links and live sessions migrate
  automatically onto the new strategy names.
- **Fix: Design values surviving a Finder visit**: a round trip through the
  `Find a driver` workspace was silently resetting drive voltage, manual box
  edits and driver T/S values to their widget defaults/minima (reported as
  "changing driver configuration halves the amplitude" - the real cause was
  voltage collapsing to 0.01 V). Design state now persists across workspace
  switches.
- **Port sizing directives**: automatic vent sizing and the optimizer's
  feasibility check now enforce, alongside the existing Helmholtz-length and
  5%-of-c air-speed checks, two more reflex directives: the classic
  minimum-area golden rule (`Dmin = 20.3*(Vd^2/Fb)^0.25`, drive-independent)
  and a 10% cap on the duct's own volume relative to the chamber it tunes.
  The Port Geometry panel warns when an entered vent is undersized by the
  golden rule, when the duct displaces too much of its chamber, or when the
  duct's own pipe resonance falls inside the working band.
- **Verification**: py_compile, Ruff and Streamlit AppTest clean; full suite
  85 passed / 0 failed / 0 skipped.

## 0.4.3 (2026-07-14)

- **Strict optimizer feasibility**: DCCAV F3 credibility, Helmholtz geometry and
  5%-of-c port air speed are now hard result conditions. An infeasible search
  reports no buildable result instead of applying its least-bad candidate, and
  optimized sessions saved by an older engine are refreshed automatically.
- **Verification**: py_compile, Ruff, the exact GRS max-extension AppTest and
  Streamlit smoke test clean; full suite 80 passed / 0 failed / 0 skipped.

## 0.4.2 (2026-07-14)

- **Buildable optimized ports**: ported optimizer candidates now obey the
  DCCAV credibility boundary and the 60 cm geometry ceiling. Applying an
  optimized box automatically recalculates its vent diameters for positive
  Helmholtz length and the air-speed guideline instead of reusing stale preset
  values.
- **Visible search and dB scale**: Search preset now previews matching driver
  names immediately, while every response overlay explicitly preserves numbered
  ticks and the `Amplitude (dB)` axis title.
- **UI control cleanup**: removed the disabled Total pen and duplicate reflex-loss
  reset, made pin and port actions contextual, hid Design-only catalog clutter,
  grouped response markers/analysis and revealed Finder optimizer goals only when
  optimization is active. Verification: py_compile, ruff and Streamlit AppTest
  clean; full suite 79 passed / 0 failed / 0 skipped.
- **Verification**: py_compile, Ruff and Streamlit AppTest clean; full suite
  79 passed / 0 failed / 0 skipped.

## 0.4.1 (2026-07-14)

- **Persistent response pens**: the Total response is now always enabled for
  every preset, while optional Cone, Lower port and MOL selections survive
  workspace, preset and load changes.
- **Finder workflow**: reorganized every Find-a-driver input into three numbered
  sidebar steps — target enclosure, candidate library and ranking — with the
  primary `Find drivers` action beside its parameters. Advanced optimization and
  scan controls use progressive disclosure; the main workspace is reserved for
  results and candidate preview/application. If the host denies multiprocessing
  semaphores, optimized scans now fall back to serial ranking instead of crashing.
- **Response zoom**: replaced the oversized response canvas with a compact 420 px
  chart, an explicit two-handle frequency window, automatic dB fitting within the
  selected band and a reliable reset. Cursor rules/readouts outside the zoomed
  window no longer clutter the chart.
- **Verification**: py_compile, ruff and Streamlit AppTest clean; full suite
  79 passed / 0 failed / 0 skipped.

## 0.4.0 (2026-07-14)

- **Fourth-order bandpass (MODS 2.3, tranche 1)**: added a sealed-rear / vented-front
  acoustic model where only the front vent radiates, with a Qbp starter,
  two-chamber loss controls, excursion/impedance/MIL/MOL outputs, port geometry
  and passband diagnostics. The topology is integrated with Suggested / Optimized /
  Manual design, exact-volume Finder ranking, `.lfp` and share persistence,
  Monte Carlo tolerance bands, the design-space atlas and equal-volume load
  comparison. Verification: py_compile and ruff clean, Bandpass AppTest clean,
  full suite 74 passed / 0 failed / 0 skipped.

## 0.3.0 (2026-07-14)

- **Brand identity**: added the official Load Forge artwork as the application
  header and repository banner.
- **Dedicated driver finder**: separated catalog ranking from enclosure design
  into a goal-first `Find a driver` workspace with its own exact comparison
  volume, voltage, ranking goal and advanced constraints. Independent widget
  state prevents stale Batch minima; explicit first-render values start a
  balanced 40 L / 2.83 V quick scan with deepest-available F3, 3 dB ripple,
  1x Xmax and a clearly labelled 10-300 Hz range.
- **Workspace-first flow**: the app now opens in the `Find a driver` workspace
  with the sealed load preselected. The workspace bar orders `Find a driver`,
  `Design a box` and `Project`, and the load selector lists `Infinite baffle`,
  `Sealed`, `Bass reflex`, `DCCAV` from top to bottom.
- **`Sealed` load name**: renamed `Acoustic suspension` to `Sealed` across the
  UI, engine and docs. Legacy `.lfp` presets and share links using the old
  labels are migrated automatically, and `optimize_alignment` canonicalizes
  the legacy values for backward compatibility.
- **Box strategy**: replaced the overlapping auto-align and optimizer modes
  with one `Suggested` / `Optimized` / `Manual` control. Suggested designs
  track driver and load changes, Optimized exposes goals and applies a result,
  and Manual unlocks direct enclosure editing and reset actions.
- **Response workflow**: the `Design a box` workspace now keeps only Response,
  Excursion, Impedance, Ports and Group Delay tabs; added response pinning,
  four-load comparison and share-via-URL design links.
- **Progressive disclosure**: moved preset save/load/share actions into a
  `Project` popover, collapsed preset T/S fields and advanced sweep controls,
  hid manual cursor positions until requested, and reduced the always-visible
  result summary to headline decision metrics with detail expanders.
- **Candidate comparison polish**: each ranked result includes a normalized
  response sparkline, class metadata and CSV export. Selecting a row opens a
  preview; only `Apply candidate to design` replaces the active design and
  switches it to Manual strategy.
- **Port diagnostics**: added Helmholtz-based port geometry estimates, peak
  air-speed reporting, chuffing warnings and explicit impossible-tuning
  messages with zero-length tuning ceilings and minimum feasible diameters.
- **Reference driver metrics**: added `Eta0 ref`, SPL at 1 W / 1 m, SPL at
  2.83 V / 1 m, EBP, voice-coil inductive corner and T/S-based bandwidth
  classification (`Subwoofer` / `Woofer` / `Midbass-capable`) in the UI and
  candidate-ranking output.
- **Series resistance**: added a series-resistance input to the simulators and
  UI so source impedance, cable resistance and crossover DCR affect drive
  level, damping, impedance and thermal-limit reporting.
- **FRD/ZMA export**: added `Download FRD (response)` and `Download ZMA
  (impedance)` next to the response CSV, in the text formats read by
  VituixCAD, XSim and REW. The FRD carries the true acoustic phase
  (`response_phase_deg`, including the radiation term) and the ZMA the true
  electrical impedance phase via the new
  `SimulationResult.impedance_phase_deg` field.
- **Charts keep every trace visible**: the response zoom ceiling now follows
  all displayed traces (MOL, load comparison) instead of clipping them, while
  the floor stays anchored to the total response at 10 Hz.
- **Nudge safety**: the `-3% / +3%` box buttons clamp to the widget bounds; a
  nudge past the maximum no longer silently resets the input to its minimum.
- **Finder clarity**: goal constraints (target F3, ripple, excursion, group
  delay) are disabled with an explanation while the per-candidate optimizer
  is off, the evaluation range stays always active, and applying a candidate
  confirms with a toast. The Finder also renders safely outside a Streamlit
  runtime via explicit widget-default fallbacks.
- **Share links**: the `Project` popover now shows the full share URL in a
  copyable code block instead of pointing at the address bar.
- **Microcopy and theming**: pinned the dark base theme the chart palette is
  tuned for; added help texts for MOL, the MIL chart, the box strategy and
  the load type; click-marker hint, labelled Xmax and group-delay limit
  lines, a `Box volume` headline metric, typographic units and a friendlier
  driver-error message.
- **Price enrichment cycle**: the scheduled enrichment cycle runs all four
  providers concurrently against isolated shards, then performs a locked
  atomic merge into the shared dataset.
- **CI**: added a GitHub Actions workflow replicating the test contract
  (compile, ruff lint, full suite, Streamlit AppTest smoke) and brought the
  codebase to ruff-clean (import sorting, `zip(strict=True)`, lint config).
- **Verification**: `.venv/bin/python tests/test_all.py` passes with 61
  passed, 0 failed and 0 skipped tests.

## 0.2.0 (2026-07-13)

- **New acoustic loads**: added acoustic suspension (sealed box) and ideal
  infinite baffle alongside DCCAV and conventional bass reflex, with matching
  alignment metrics, plots, exports, Batch LF Finder routing and preset
  persistence.
- **Goal-driven optimizer**: added extension/balanced/flat objectives, target
  F3, ripple, excursion, group-delay and volume constraints for DCCAV, reflex
  and sealed boxes, backed by a faster vectorized DCCAV solver.
- **Exact Batch volume**: optimized Batch LF Finder results now use the exact
  requested enclosure volume; DCCAV keeps `Vh+Vl` fixed and reflex/sealed keep
  `Vb` fixed while their remaining alignment parameters are optimized.
- **Optimizer UI consistency**: apply buttons respect optimized alignment mode,
  active-box metrics report the simulated enclosure, and stale optimizer
  summaries are hidden when the driver, load, goals, voltage or box changes.
- **Driver catalog and pricing**: expanded Loudspeaker Database records, added
  runtime price metadata, currency-aware filtering, purchase links and Batch
  price columns.
- **Price enrichment tools**: added validated enrichment for SoundImports, Blue
  Aran, Madisound and Parts Express, including sitemap/category crawling,
  provider-specific extraction, accessory rejection and safe model matching.
- **Chart robustness**: filter non-finite points, keep SPL zoom anchored to the
  total response and protect plot scaling from cursor labels and port spikes.
- **Terminology and compatibility**: use the standard English term `Acoustic
  suspension` while migrating presets saved with the former label.
- **Documentation**: synchronized README, user guide, module contracts, agent
  guidance and changelog with the four supported acoustic loads and workflows.
- **Verification**: `.venv/bin/python tests/test_all.py` passes with 42 passed,
  0 failed and 0 skipped tests.

## 0.1.0 (2026-07-07)

- **Load Forge DCCAV**: transformed the app into a Streamlit simulator for
  DCCAV acoustic loads.  The active path is `ui_app.py -> src/dccav.py`:
  driver T/S inputs, empirical `Vh/fh/Vl/fl` alignment, complex acoustic
  network simulation, SPL estimate, cone excursion, impedance, port volume
  velocity, `.lfp` presets and response CSV export.
- **Driver presets**: added `KEF B110B article example` and `Beyma 12CMV2`.
  The Beyma preset uses the supplied datasheet values (`Sd=0.053 m2`,
  `Fs=49 Hz`, `Qts=0.47`, `Vas=76 L`).  Presets apply immediately, and
  `Auto-align box from T/S` updates the simulated box values without an
  additional manual step.
- **Cleanup**: reduced the repository to the active DCCAV simulator surface,
  with obsolete code, assets, generated samples, geometry suites and module docs
  removed.
- **Docs/Test**: active docs are `README.md`, `USER_GUIDE.md`,
  `docs/INDEX.md`, `docs/__init__.md`, `docs/dccav.md`, `AGENTS.md`, `CLAUDE.md` and
  `GOLDEN_STD.md`.  Active test suite is `tests/test_all.py` with 10 DCCAV
  tests.
- **UI plots**: response, excursion, impedance and port velocity traces now use
  Streamlit-native Altair charts so browser updates follow parameter changes
  reliably.
- **DCCAV impedance fix**: corrected the acoustic compliance sign in the driver
  and chamber impedances.  The Beyma regression now verifies the expected
  three-crest DCCAV impedance shape.
- **Plot tools**: added response/port pen toggles plus automatic F3/F6/F10
  cursors and manual M1/M2 cursors with a readout table.
- **Plot trace visibility**: separated curve and cursor color scales so cursor
  overlays cannot hide the response traces.
- **Pen toggles**: response and port pen lists can now be empty; the UI leaves
  the plot off instead of forcing a fallback trace.
- **Cursor labels**: cursor labels on the response plot now include the marker
  frequency in Hz.
- **Visible plot controls**: moved pen and cursor controls above the response
  plot and made them direct checkboxes instead of hidden sidebar multiselects.
- **Response wording**: relabeled the response plot as a low-frequency acoustic
  load estimate and documented the natural high-frequency rolloff of the DCCAV
  port branch.
- **Beyma presets**: added selected official Beyma 12" low/mid and woofer
  presets from the 2026 XLS catalog: 12G40, 12LX60V2, 12BR70, 12MC500,
  12MCS500, 12WRS400, 12P80Nd/V2, 12P1000/Nd, 12LEX1000Fe, 12LEX1300Nd and
  12CMV3.
- **LaVoce preset**: added `LaVoce WSF122.02` from the supplied technical
  specification screenshot.
- **LaVoce preset**: added `LaVoce WSF122.50` from the supplied technical
  specification screenshot.
- **Turbosound preset**: added `Turbosound TS-15W300/8A` from the supplied
  specification screenshot.
- **Turbosound preset**: added `Turbosound TS-12W350/8W` from the manufacturer
  specification PDF linked in the working session.
- **Cursor labels**: enlarged F3/F6/F10 response-plot labels, included the
  interpolated total SPL in dB and moved labels into a separated top-left
  readout block while keeping cursor rules on their exact frequencies.
- **Bass-reflex losses**: surfaced the current reflex loss factors next to
  `Vb/Fb`, added a reset button, and made custom loss values opt-in so stale
  hidden low-Q settings cannot overdamp the vent while editing presets or
  volume.  The missing-impedance-peaks warning reports the active loss values.
- **Driver presets**: added `Scan-Speak 30W/4558T00`,
  `Dayton Audio RSS315HO-4` and `SB Audience BIANCO-12OB150-01`.
- **Driver preset**: added `Scan-Speak 15W/4531G00` from the supplied local
  Scan-Speak datasheet PDF.
- **Response zoom**: the SPL chart now auto-zooms from the total-response level
  at 10 Hz up to 5 dB above the maximum visible response pen.
- **Response plot sizing**: cursor labels now use fixed pixel overlay positions
  so they cannot expand the response dB scale, and the SPL chart height is
  increased.
- **Clickable marker**: the main SPL chart now has a click-to-place moving
  marker on the total response, with its own rule, point and Hz/dB readout.
- **Driver presets**: imported 19 complete Aiyima mini-driver T/S rows from
  `/Users/marcoderossi/Downloads/driver data.xlsx`, converting piston area from
  `mm2` to simulator `cm2`.
- **Driver preset filtering**: added brand, approximate size and text filters
  above the preset selector so long speaker lists stay navigable.
- **Verification**: `.venv/bin/python tests/test_all.py` passes with 14 passed,
  0 failed and 0 skipped tests.
- **Design nudges**: added `-3%` / `+3%` buttons for `Vh`, `fh`, `Vl` and `fl`,
  and increased the response chart height.
- **Alignment sanity**: show suggested total volume and warn when the empirical
  DCCAV formula returns a very small 12" alignment.
- **Loudspeaker Database import**: added a resumable
  `tools/import_loudspeaker_database.py` importer that partitions downloads by
  brand, writes a checkpoint after completed partitions, exits with code 75 on
  rate-limit/runtime-budget stops and writes partial datasets instead of
  blocking indefinitely.
- **Loudspeaker Database safeguards**: the importer now keeps a local brand
  cache, merges existing dataset records back into the checkpoint and defers
  brand partitions that return product pages or other non-search HTML so bad
  responses cannot pollute the preset dataset.
- **Loudspeaker Database retry runner**: added
  `tools/run_loudspeaker_database_import_until_complete.py` to run the importer
  in fresh process windows with growing pauses between attempts until the
  dataset is complete or a configured attempt limit is reached.
- **Loudspeaker Database dataset**: completed the local
  `data/loudspeaker_database_drivers.json` import with 6178 usable presets,
  102 completed brand partitions and no deferred partitions remaining.
- **External preset filtering**: `src/dccav.py` now lazily loads optional
  `LSDB:` presets from `data/loudspeaker_database_drivers.json`, exposes
  preset source/brand/size metadata and the UI adds a `Source` filter for large
  imported lists.
- **Verification**: `.venv/bin/python tests/test_all.py` passes with 14 passed,
  0 failed and 0 skipped tests after the LSDB importer and filtering changes.
