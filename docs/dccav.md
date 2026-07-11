# `src/dccav.py` — acoustic-load simulators

Implements the audio-domain simulators for the app: DCCAV / double series
resonator based on the PCPaudio/G.P. Matarazzo article `Teoría y práctica del
doble resonador en serie`, plus a conventional one-box bass-reflex load.

The module works in the frequency domain with lumped acoustic impedances and
returns arrays for plotting SPL, cone excursion, impedance and port volume
velocities.

## Models

The DCCAV topology is:

```text
driver -> upper volume || upper port -> lower volume || lower port
```

The upper chamber `Vh` is tuned to `fh`; its port discharges into the lower
chamber `Vl`, which is tuned to `fl` and vents to the outside.

The woofer cone is treated as exposed on its front side.  Internally, the
acoustic circuit solves the cone volume velocity entering the rear DCCAV load;
the externally radiated cone contribution has the opposite sign.  Total LF
response is therefore the vector sum of the front cone radiation and the lower
port radiation, not a scalar sum.

The driver free-air acoustic impedance is:

```text
Zas = Rat + j*w*Mas + 1/(j*w*Cas)
```

with:

- `Mas = Mms / Sd^2`
- `Cas = Cms * Sd^2`
- `Rat = (Rms + Bl^2 / Re) / Sd^2`

Volume losses use the compliance branch `Zab = (Rab + 1/(j*w*Cab)) // Ral`.
Port tuning uses `Zap = Rap + j*w*Map`, with `Map` solved from the requested
box volume and tuning frequency.

The bass-reflex topology is:

```text
driver -> box volume || vent
```

`simulate_reflex()` uses the same driver model, exposed front cone radiation,
box compliance, port mass/loss and electrical impedance calculation as the
DCCAV solver, but with a single acoustic node.

## Public API

### `DriverTS`

Dataclass for the input Thiele/Small parameters:

- required: `fs_hz`, `vas_l`, `qts`, `qms`, `re_ohm`, `sd_cm2`
- optional: `le_mh`, `xmax_mm`, `pe_w`, `mms_g`, `cms_mm_per_n`, `bl_tm`

If optional `Mms`, `Cms` or `Bl` are not supplied, they are derived from
`Fs`, `Vas`, `Qts`, `Qms`, `Re` and `Sd`.

### `sd_from_diameter(diameter_mm) -> float`

Convenience helper returning piston area in `cm^2`.

### Built-in driver presets

`DRIVER_PRESETS` contains named `DriverTS` sets for quick UI setup.

Current presets:

- `KEF B110B article example`
- `Beyma 12CMV2`
- `Beyma 12G40`
- `Beyma 12LX60V2`
- `Beyma 12BR70`
- `Beyma 12MC500`
- `Beyma 12MCS500`
- `Beyma 12WRS400`
- `Beyma 12P80Nd/V2`
- `Beyma 12P1000/Nd`
- `Beyma 12LEX1000Fe`
- `Beyma 12LEX1300Nd`
- `Beyma 12CMV3`
- `Turbosound TS-12W350/8W`
- `Turbosound TS-15W300/8A`
- `Scan-Speak 30W/4558T00`
- `Scan-Speak 15W/4531G00`
- `Dayton Audio RSS315HO-4`
- `SB Audience BIANCO-12OB150-01`
- `LaVoce WSF122.02`
- `LaVoce WSF122.50`
- `MarkAudio CHR-70`

`driver_preset_names()` returns the names in display order.
`get_driver_preset(name)` returns the matching `DriverTS` or raises
`ValueError`.

The Beyma 12CMV2 preset is transcribed from the manufacturer sheet shown in the
working session:

- `Fs=49 Hz`
- `Re=6 ohm`
- `Qms=3.9`
- `Qts=0.47`
- `Vas=76 L`
- `Sd=0.053 m^2`
- `Cms=193 um/N`
- `Mms=54 g`
- `Bl=13.7 Tm`
- `Xmax=7 mm`
- `Le=1 mH`
- `Pe=320 W`

The preset uses the specified effective surface area `Sd`, not the nominal
300 mm frame diameter.

The additional Beyma 12" presets are transcribed from Beyma's official catalog
XLS (`/en/download-catalog-in-xls/`, downloaded 2026-07-07).  Catalog units are
converted for the simulator: `Sd` from m^2 to cm^2, moving mass from kg to g and
`Cms` from um/N to mm/N.

`LaVoce WSF122.02` and `LaVoce WSF122.50` are transcribed from technical-specification screenshots
provided in the working session.

`Turbosound TS-12W350/8W` is transcribed from the manufacturer specification
PDF linked by Gear4music in the working session: `Fs=61 Hz`, `Re=5.5 ohm`,
`Qms=11.37`, `Qes=0.45`, `Qts=0.43`, `Mms=67.78 g`, `Cms=0.1 mm/N`,
`Bl=17.9 Tm`, `Vas=19.26 L`, `Xmax=3.8 mm`, `Sd=551.55 cm^2`, `Le=1.6 mH`,
`Pe=350 W`.

`Turbosound TS-15W300/8A` is transcribed from the specification-sheet screenshot
provided in the working session: `Fs=46 Hz`, `Re=6.5 ohm`, `Qms=16.6`,
`Qes=0.49`, `Qts=0.47`, `Mms=96.4 g`, `Cms=0.12 mm/N`, `Bl=19.3 Tm`,
`Vas=130.2 L`, `Xmax=4.9 mm`, `Sd=865.7 cm^2`, `Le=1.2 mH`, `Pe=300 W`.

`Scan-Speak 30W/4558T00` is transcribed from Scan-Speak's official Discovery
datasheet, updated 2022-12-07: `Fs=17 Hz`, `Re=2.6 ohm`, `Qms=5.01`,
`Qes=0.34`, `Qts=0.32`, `Mms=135 g`, `Cms=0.65 mm/N`, `Bl=10.5 Tm`,
`Vas=197 L`, `Xmax=12.5 mm`, `Sd=466 cm^2`, `Le=0.83 mH`, `Pe=150 W`.

`Scan-Speak 15W/4531G00` is transcribed from the Scan-Speak Revelator datasheet
provided as a local PDF in the working session, updated 2013-01-30: `Fs=40 Hz`,
`Re=3.4 ohm`, `Qms=4.60`, `Qes=0.34`, `Qts=0.32`, `Mms=13 g`,
`Cms=1.25 mm/N`, `Bl=5.7 Tm`, `Vas=15.8 L`, `Xmax=6.5 mm`, `Sd=95 cm^2`,
`Le=0.25 mH`, `Pe=60 W`.

`Dayton Audio RSS315HO-4` is transcribed from Dayton Audio's official product
page/specification sheet: `Fs=26.2 Hz`, `Re=3.2 ohm`, `Qms=3.63`, `Qes=0.33`,
`Qts=0.31`, `Mms=251 g`, `Cms=0.15 mm/N`, `Bl=20 Tm`, `Vas=53.7 L`,
`Xmax=12.3 mm`, `Sd=514.7 cm^2`, `Le=1.75 mH`, `Pe=700 W`.

`SB Audience BIANCO-12OB150-01` is transcribed from the specification screenshot
provided in the working session: `Fs=44 Hz`, `Re=7.2 ohm`, `Qms=6.39`,
`Qes=0.69`, `Qts=0.63`, `Mms=52.4 g`, `Cms=0.25 mm/N`, `Bl=12.2 Tm`,
`Vas=103.8 L`, `Xmax=6.79 mm`, `Sd=539.1 cm^2`, `Le=1.18 mH`, `Pe=150 W`.

`MarkAudio CHR-70` is transcribed from the Markaudio parameter screenshot
provided in the working session: `Fs=65.4 Hz`, `Re=7.2 ohm`, `Sd=50.2 cm^2`,
`Vas=5.17 L`, `Cms=1.44 mm/N`, `Mms=4.10 g`, `Bl=4.20 Tm`, `Qms=2.66`,
`Qes=0.69`, `Qts=0.55`, `Le=0.03244 mH`, `SPL=85.4 dB`, `Pe=20 W`,
`Xmax=4.3 mm`.

### `complete_driver(ts) -> DerivedDriver`

Converts the T/S set to SI/mechanical/acoustic-domain values.  Raises
`ValueError` on non-positive inputs or `Qms <= Qts`, because `Qes` could not be
derived.

### `suggest_alignment(ts) -> DccavAlignment`

First-pass empirical DCCAV alignment from the article:

```text
Vh = 2.05 * Qts^2 * Vas
Vl = 4.13 * Qts^2 * Vas
fh = 1.22 * Fs / Qts
fl = 0.466 * Fs / Qts
f3 = 0.83 * fl
```

For the KEF B110-like example in the article (`Fs=48.14`, `Qts=0.362`,
`Vas=11.52`) this yields approximately `Vh=3.1 L`, `Vl=6.2 L`,
`fh=162 Hz`, `fl=62 Hz`.

### `suggest_reflex_alignment(ts) -> ReflexAlignment`

Returns a conservative normal bass-reflex starting point:

```text
Vb = Vas
Fb = Fs
```

This is intentionally plain; it is meant as an editable starting point rather
than a named classic alignment.

### `simulate(ts, box, freq_hz=None, voltage_v=2.83) -> SimulationResult`

Solves the two-node acoustic circuit across the frequency array.  The source
pressure is approximated as `Eg*Bl/(Re*Sd)` and drives the network through
`Zas`.

Returned arrays:

- `spl_total_db`: exposed cone front plus lower port, summed as complex volume
  velocities before conversion to dB
- `spl_driver_db`: exposed cone front radiation alone
- `spl_port_db`: lower port radiation alone
- `excursion_mm`
- `impedance_ohm`
- `mil_w`: maximum input power by frequency, limited by `Xmax` and/or `Pe`
  when those driver fields are available
- `mol_db`: maximum output level estimate, produced by scaling `spl_total_db`
  up to the `MIL` limit
- `port_h_velocity`
- `port_l_velocity`
- complex `driver_volume_velocity` for the exposed cone front and
  `port_volume_velocity` for the lower port

`MIL` is computed from the linear excursion result at the requested simulation
voltage.  The excursion-limited RMS voltage is `voltage * Xmax / excursion`;
the thermal RMS voltage is approximated as `sqrt(Pe * Re)`.  The lower
available voltage limit is converted to watts as `V^2 / Re` for display and
CSV export.  `MOL` uses the same voltage ratio to scale SPL.  If neither `Xmax`
nor `Pe` is known, `MIL` and `MOL` are returned as `NaN` and the UI reports them
as unavailable.

The SPL values are useful for comparing alignments inside this simulator.  They
represent a low-frequency acoustic-load estimate.  They are not a calibrated
far-field model and do not include cone breakup, baffle step, horn/waveguide
directivity, or electrical crossover behaviour.

The electrical impedance should show the expected multi-resonance DCCAV shape;
the built-in Beyma alignment regression checks for three local impedance crests.

### `simulate_reflex(ts, box, freq_hz=None, voltage_v=2.83) -> SimulationResult`

Solves the conventional one-box reflex acoustic circuit across the frequency
array.  The returned `SimulationResult` uses the same fields as DCCAV:
`spl_total_db` is exposed cone front plus vent, `spl_port_db` is the vent alone,
`port_l_velocity` is the vent volume velocity and `port_h_velocity` is zero.

### `response_metrics(result) -> dict`

Returns compact UI metrics: peak SPL, estimated `F3`, maximum excursion and
minimum impedance.  `F3` is taken from the low-frequency crossing returned by
`response_threshold_frequencies()`.

### `impedance_peak_frequencies(result, min_ratio_to_minimum=1.2) -> list[float]`

Returns local electrical-impedance peak frequencies above a threshold relative
to the minimum impedance.  The UI uses this to display `Z peaks`; a normal
bass-reflex simulation should show two impedance peaks within the simulated
frequency range.

### `equivalent_sealed_fc_hz(ts, box) -> float`

Returns the closed-box resonance frequency that the same driver would have in
the total DCCAV chamber volume `Vh+Vl`.  This is used only as a sanity check; it
is not a replacement for the DCCAV simulation.

### `alignment_diagnostics(ts, box) -> list[str]`

Returns practical warnings for empirical alignments, including low-`Qts`
extrapolation and very small 12-inch boxes where port displacement, compression
and target SPL can dominate the small-signal formula.

### `response_sanity_warnings(ts, box, thresholds) -> list[str]`

Returns warnings when the computed low-frequency crossings contradict the box
tuning constraints.  For example, an `F3` far below the lower tuning `fl` or far
below the equivalent sealed `Fc` is flagged instead of being treated as a
credible design result.

### `response_threshold_frequencies(result, drops_db=(3, 6, 10)) -> dict`

Returns low-frequency response crossing frequencies relative to the maximum
total SPL in the reference band, currently 40-200 Hz.  The crossing search uses
the first rising low-frequency crossing so a later dip/notch inside the pass
band cannot move F3/F6/F10 to an upper-frequency recovery point.  The UI uses
this for the automatic F3/F6/F10 cursors and metrics.

If no true rising crossing exists in the simulated range, the returned value is
`NaN`; the UI displays `n/a` rather than inventing the nearest frequency.

## Tests

`tests/test_all.py` contains DCCAV coverage for:

- article alignment regression
- built-in driver presets, including Beyma 12CMV2
- T/S derivation from diameter/Sd
- finite response arrays and sane metric signs
- three local impedance crests for the DCCAV load
- two local impedance crests for the bass-reflex load
- F3/F6/F10 threshold ordering for cursor placement
- no fabricated F3 when a true threshold crossing is absent
- response sanity warnings for impossible F3 values
- input validation for invalid `Qms <= Qts`
