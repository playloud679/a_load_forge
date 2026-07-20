# Changelog

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
