# Changelog

## 0.2.0 (2026-07-13)

- **Brand identity**: added the official Load Forge artwork as the application
  header and repository banner.
- **New acoustic loads**: added acoustic suspension (sealed box) and ideal
  infinite baffle alongside DCCAV and conventional bass reflex, with matching
  alignment metrics, plots, exports, Batch LF Finder routing and preset
  persistence.
- **Goal-driven optimizer**: added extension/balanced/flat objectives, target
  F3, ripple, excursion, group-delay and volume constraints for DCCAV, reflex
  and sealed boxes, backed by a faster vectorized DCCAV solver.
- **Exact Batch volume**: optimized Batch LF Finder results now use the exact
  optimizer max-volume value; its duplicate Batch volume input was removed.
  DCCAV keeps `Vh+Vl` fixed and reflex/sealed keep `Vb` fixed while their
  remaining alignment parameters are optimized.
- **Optimizer UI consistency**: apply buttons respect optimized alignment mode,
  active-box metrics report the simulated enclosure, and stale optimizer
  summaries are hidden when the driver, load, goals, voltage or box changes.
- **Driver catalog and pricing**: expanded Loudspeaker Database records, added
  runtime price metadata, currency-aware filtering, purchase links and Batch
  price columns.
- **Price enrichment tools**: added validated enrichment for SoundImports, Blue
  Aran, Madisound and Parts Express, including sitemap/category crawling,
  provider-specific extraction, accessory rejection and safe model matching.
  The scheduled enrichment cycle runs all four providers concurrently against
  isolated shards, then performs a locked atomic merge into the shared dataset.
- **Chart robustness**: filter non-finite points, keep SPL zoom anchored to the
  total response and protect plot scaling from cursor labels and port spikes.
- **Response workflow**: reorganized the UI into tabs for Response, Excursion,
  Impedance, Ports, Group Delay and Batch LF Finder; added response pinning,
  four-load comparison and share-via-URL design links.
- **Port diagnostics**: added Helmholtz-based port geometry estimates, peak
  air-speed reporting, chuffing warnings and explicit impossible-tuning
  messages with zero-length tuning ceilings and minimum feasible diameters.
- **Reference driver metrics**: added `Eta0 ref`, SPL at 1 W / 1 m, SPL at
  2.83 V / 1 m, EBP, voice-coil inductive corner and T/S-based bandwidth
  classification (`Subwoofer` / `Woofer` / `Midbass-capable`) in the UI and
  Batch output.
- **Series resistance**: added `Series R (ohm)` to the simulators and UI so
  source impedance, cable resistance and crossover DCR affect drive level,
  damping, impedance and thermal-limit reporting.
- **Batch comparison polish**: each result row now includes a normalized
  response sparkline, class metadata and CSV export of the visible table
  columns.
- **Terminology and compatibility**: use the standard English term `Acoustic
  suspension` while migrating presets saved with the former label.
- **Documentation**: synchronized README, user guide, module contracts, agent
  guidance and changelog with the four supported acoustic loads and workflows.
- **Verification**: `.venv/bin/python tests/test_all.py` passes with 55 passed,
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
