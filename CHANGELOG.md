# Changelog

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
- **Verification**: `.venv/bin/python tests/test_all.py` passes with 11 passed,
  0 failed and 0 skipped tests.
- **Design nudges**: added `-3%` / `+3%` buttons for `Vh`, `fh`, `Vl` and `fl`,
  and increased the response chart height.
- **Alignment sanity**: show suggested total volume and warn when the empirical
  DCCAV formula returns a very small 12" alignment.
