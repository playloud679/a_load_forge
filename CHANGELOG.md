# Changelog

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
