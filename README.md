# Load Forge

Load Forge is a Streamlit simulator for acoustic loudspeaker loads.  It supports
**DCCAV** / double resonator in series, conventional **bass reflex**,
**acoustic suspension** (sealed box) and ideal **infinite baffle**, all derived
from driver Thiele/Small parameters.

The app starts from a T/S set, proposes an editable first-pass alignment, then
simulates the lumped acoustic circuit and plots:

- estimated total SPL
- driver and port contributions when present
- cone excursion
- electrical impedance
- port volume velocity for ported loads
- MIL/MOL limit curves when `Xmax` or `Pe` are available

The current model is a frequency-domain engineering simulator.  It is useful
for comparing alignments and understanding trends; it is not a calibrated
far-field measurement substitute.

## Running it

```bash
make install
make run
```

`make run` starts Streamlit headless on `localhost:8501` and opens Safari.  You
can also run it directly:

```bash
.venv/bin/streamlit run ui_app.py
```

## Load Models

The simulated topology is:

```text
driver -> upper volume || upper port -> lower volume || lower port
```

The upper chamber `Vh` is tuned to `fh`; its port discharges into the lower
chamber `Vl`, which is tuned to `fl` and vents to the outside.

The first-pass alignment is:

```text
Vh = 2.05 * Qts^2 * Vas
Vl = 4.13 * Qts^2 * Vas
fh = 1.22 * Fs / Qts
fl = 0.466 * Fs / Qts
f3 = 0.83 * fl
```

The simulator solves the acoustic impedance network with complex arithmetic and
uses the driver T/S data to derive missing `Mms`, `Cms`, `Rms`, `Qes` and `Bl`
when measured values are not supplied.

The normal bass-reflex path uses:

```text
driver -> box volume || vent
```

Its automatic starting point is intentionally conservative: `Vb = Vas` and
`Fb = Fs`, with manual controls for final tuning.

The acoustic-suspension path uses a closed `Vb` and reports its classical
`Fc` and `Qtc`; its starter targets `Qtc=0.707` when the driver's `Qts` permits.
Infinite baffle has no box or tuning controls and assumes perfect isolation of
the rear wave.

## Project Structure

```text
ui_app.py          Streamlit dashboard
src/dccav.py       DCCAV/reflex/sealed/infinite-baffle simulation engine
docs/dccav.md      module contract and formulas
tests/test_all.py  custom test runner, including acoustic-load tests
```

## Tests

Targeted acoustic-load checks:

```bash
.venv/bin/python tests/test_all.py -m dccav
```

Full active suite:

```bash
.venv/bin/python tests/test_all.py
```

For UI changes, run a Streamlit `AppTest` that loads `ui_app.py` and asserts no
exceptions.

## Development Contract

The repo follows the local contract in `AGENTS.md` and `GOLDEN_STD.md`:

- every `src/*.py` change must update its matching `docs/<module>.md`
- new or changed behavior needs tests in the same change
- run targeted tests while patching
- run the full active suite before any commit touching Python
- do not push unless explicitly requested
