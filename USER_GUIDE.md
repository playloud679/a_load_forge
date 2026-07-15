# Load Forge User Guide

Load Forge simulates acoustic loudspeaker loads from driver Thiele/Small
parameters. It supports DCCAV, fourth-order bandpass, conventional bass reflex,
acoustic suspension (sealed box) and ideal infinite baffle.

## Workspaces

The switch below the header separates two different jobs:

- **Design a box** starts from one driver, chooses an alignment strategy and
  exposes the simulation results and plots.
- **Find a driver** starts from enclosure and ranking constraints, evaluates
  only the catalog candidates allowed by the sidebar filters, and preserves the
  current design until a candidate is explicitly applied.

The **Project** popover contains preset save/load and URL sharing so these
occasional actions do not compete with the main workflow.

## Inputs

### Driver T/S

Enter the driver parameters in the sidebar:

- `Fs`
- `Vas`
- `Qts`
- `Qms`
- `Re`
- piston diameter or `Sd`
- optional `Le`, `Xmax`, `Pe`

Optional measured values `Mms`, `Cms` and `Bl` can be supplied in the optional
parameters panel.  If they are left at zero, the simulator derives them from the
T/S set.

`Qms` must be greater than `Qts`; otherwise `Qes` cannot be derived.

The **Load type** selector switches between `Infinite baffle`, `Sealed`,
`Bass reflex`, `Bandpass 4th order` and `DCCAV`. Search, source, brand, size, class
and price filters narrow the driver library in both workspaces.

In **Design a box**, the **Driver preset** selector loads built-in examples
immediately. **Driver T/S values** stays collapsed for catalog presets and
opens automatically for `Custom`; expand it whenever the values need to be
inspected or overridden.

`Beyma 12CMV2` uses the manufacturer T/S values from the supplied datasheet
screenshot, including `Sd=0.053 m2`; the nominal 300 mm diameter is not used as
piston area.

The preset list also includes selected Beyma 12" low/mid and woofer models from
Beyma's official XLS catalog.  Catalog units are converted internally to the
simulator units.

### Box Strategy

One optimizer computes every automatic box; the strategy control only selects
its objective:

- **Max extension** favors the deepest F3 the constraints allow.
- **Balanced** trades extension against smoothness and box practicality.
- **Flattest** favors the smoothest passband.
- **Manual** unlocks direct volume and tuning edits with `-3%` / `+3%` nudges.

With an objective selected the box re-applies automatically whenever the
driver, load or an optimization constraint changes; the **Optimization
constraints** expander sets max volume, target F3, ripple, excursion and group
delay. Every result recalculates the active vent diameters for a positive
Helmholtz length and the 5%-of-c air-speed guideline; stored boxes are
recalculated automatically after a physics-engine update. If no candidate
satisfies credibility, geometry and air-speed limits, the app keeps a starter
box and reports why instead of applying a warning-laden result.

Projects saved by earlier versions load transparently: the old **Suggested**
strategy maps to **Balanced** and the old **Optimized** strategy maps to its
stored goal.

Infinite baffle has no enclosure, so the strategy control is disabled.

### DCCAV Alignment

The empirical first-pass alignment seeds the optimizer search:

```text
Vh = 2.05 * Qts^2 * Vas
Vl = 4.13 * Qts^2 * Vas
fh = 1.22 * Fs / Qts
fl = 0.466 * Fs / Qts
f3 = 0.83 * fl
```

The selected objective refines it automatically; with **Manual** the editable
`Vh`, `fh`, `Vl` and `fl` controls also provide `-3%` and `+3%` nudges.

### Bass Reflex Alignment

The reflex optimizer search is seeded from the plain starting point (not a
named QB3/SBB4/EBS alignment):

```text
Vb = Vas
Fb = Fs
```

### Acoustic Suspension Alignment

The sealed-box starter targets `Qtc=0.707` when that is possible from the
driver's `Qts`, and displays `Vb`, `Fc` and achieved `Qtc`.  `Vb`, `Qabs` and
`Qleak` remain editable; there are no port controls or port traces.

### Fourth-order Bandpass Alignment

The driver is enclosed between a sealed rear chamber `Vs` and ported front
chamber `Vp`; only the front vent radiates. The symmetrical starter targets
`Qbp=0.707` and seeds the optimizer, which searches both chamber volumes and
the tuning for the selected objective; Manual unlocks `Vs`, `Vp` and `Fp`.

### Infinite Baffle

Infinite baffle has no box or optimizer controls.  It keeps the driver's
free-air `Fs` and `Qts` and assumes the rear wave is perfectly isolated.  The
ideal model does not include finite-panel diffraction, baffle step or leakage.

The empirical starter is a small-signal starting point, not a full
mechanical enclosure design.  For low-Qts pro 12" drivers it can produce very
small volumes; the UI warns when the total suggested `Vh+Vl` is likely too small
to treat as a practical final box without checking port displacement, air speed,
compression and maximum SPL.

### Box Controls

The DCCAV topology is:

```text
driver -> upper volume || upper port -> lower volume || lower port
```

Controls:

- `Vh upper`: upper chamber volume
- `fh upper`: upper port tuning
- `Vl lower`: lower chamber volume
- `fl lower`: lower port tuning
- `Qabs`: absorber losses
- `Qleak`: enclosure leakage losses
- `Qport`: port losses

For `Bass reflex`, controls are:

- `Vb box`: single enclosure volume
- `Fb tuning`: vent tuning
- `Qabs`, `Qleak`, `Qport`: box, leakage and port losses

For `Sealed`, controls are sealed `Vb`, `Qabs` and `Qleak`.
For `Bandpass 4th order`, controls are rear `Vs`, front `Vp`, `Fp`, independent
chamber loss factors, front `Qport` and front-vent diameter.
`Infinite baffle` has no enclosure controls.

Higher Q means lower loss for leakage/ports.  Very low Q values intentionally
damp the response.

### Simulation Controls

The **Drive** section keeps voltage visible because it directly affects output
and excursion. **Advanced controls** reveals sweep limits, point count and
`Series R (ohm)`. Series resistance models amplifier output impedance, cable
resistance and crossover-coil DCR in series with the driver. Raising it reduces
drive, reduces electrical damping, raises the effective system `Qes/Qts` and
raises the impedance seen by the source.

### Port Geometry

Ported loads expose a **Port geometry** panel:

- bass reflex: vent diameter
- fourth-order bandpass: front-vent diameter
- DCCAV: upper-port and lower-port diameters

The app estimates physical tube length from the Helmholtz relation, reports the
peak air speed and warns when:

- the air speed exceeds the ~17 m/s chuffing guideline
- the requested volume/tuning pair is impossible for the selected diameter,
  quoting the zero-length tuning ceiling and the minimum feasible diameter
- the diameter is below the minimum-area golden rule
  `Dmin = 20.3 · (Vd²/Fb)^0.25` cm (Vd = Sd·Xmax in litres): unlike the
  air-speed check this floor does not depend on the simulated voltage, so a
  quiet simulation cannot hide an undersized vent
- the duct itself occupies more than 10% of the chamber it tunes: the box is
  too small for that tuning/diameter pair and the Helmholtz model is no longer
  reliable
- the duct's first pipe resonance `c/2L` falls below 4× the tuning, i.e. the
  port's own standing wave lands inside the working band

Automatic vent sizing (the objective strategies and the Finder) always applies
the largest of the tuning-feasibility, air-speed and golden-rule diameters,
and the optimizer rejects boxes whose smallest workable duct would break the
10% duct-volume directive.

### Find a Driver

The **Find a driver** workspace has independent search constraints; it does not
reuse or alter the active design controls. All Finder inputs live in the
sidebar in a three-step workflow, while the main workspace remains dedicated
to results, candidate preview and application:

1. **Target enclosure** selects the load, exact comparison volume and voltage.
2. **Candidate library** filters the catalog by text, source, size, brand,
   bandwidth class and optional price ceiling. Typing in **Search preset**
   immediately lists the first matching driver names before a scan is started.
3. **Ranking** selects the optimization goal and constraints, plus the scan
   range, then starts the search with **Find drivers**. Technical range,
   result-count and resolution controls stay inside **Advanced scan**.

- **Comparison volume** is exact: `Vh+Vl` for DCCAV, `Vs+Vp` for bandpass, or `Vb` for reflex and
  acoustic suspension. Infinite baffle ignores it.
- **Optimization goal** selects the same optimizer objective as the Design
  workspace — `Max extension`, `Balanced` or `Flattest`. Every candidate box
  is derived by that one optimizer at the fixed comparison volume and the
  comparison voltage; infinite baffle candidates are ranked in free air.
- **Optimization constraints** sets desired bass extension F3, allowed
  ripple, maximum excursion relative to each driver's Xmax, group delay and the
  clearly labelled evaluation-frequency range.
- **Top results to show** and **Simulation resolution** control output size
  and search cost. Every scan evaluates the entire filtered library; the
  matching-preset count above **Find drivers** updates live as filters change.
  Large optimized scans run across worker processes with a live progress bar.

A new Finder starts with a practical profile: 40 L, `Balanced`, 2.83 V, F3
target 0 Hz (deepest available extension), 3 dB ripple, 1× Xmax, 30 ms group
delay, a 10-300 Hz evaluation range, 20 results and 240 simulation points.
**Reset Finder defaults** restores this profile without changing the active
design.

**Find drivers** evaluates every preset currently admitted by the sidebar
filters. Each result can include class, price, purchase link and a
normalized response sparkline. Selecting a row opens a preview without
changing the active design. **Apply candidate to design** is the only action
that replaces it; the app then returns to **Design a box** in **Manual** mode so
the ranked enclosure is preserved exactly.

**Download candidate CSV** exports the visible table columns except the
sparkline.

## Outputs

### Metrics

The always-visible decision summary contains four metrics:

- estimated `F3`
- peak low-frequency SPL estimate
- maximum cone excursion
- minimum electrical impedance

**Design details** contains `F6`, `F10`, impedance peaks, active enclosure
values and suggested-alignment context.

**Driver details** contains reference values derived from the T/S set:

- `Eta0 ref`
- `SPL 1W/1m`
- `SPL 2.83V/1m`
- `EBP`
- `VC corner`
- `Class`

`VC corner` is `Re/(2*pi*Le)`: above this frequency the voice-coil inductance
starts to roll the response off.  `Class` is a T/S-based screening heuristic:
`Subwoofer`, `Woofer` or `Midbass-capable`.

### LF Load Response

The response plot shows the low-frequency acoustic-load estimate:

- total estimated response
- direct driver contribution
- lower external port contribution

For DCCAV, the lower-port branch naturally rolls off above the tuned range even
without an electrical crossover.  For bass reflex, the port trace is the vent
output. For fourth-order bandpass, total response is the front vent alone and
the cone trace is internal motion, not another radiating source. Sealed and
infinite-baffle total response is the exposed cone front
alone.  The SPL scale is an internal estimate for comparing alignments, not a
calibrated far-field or full-range front-driver radiation model.

### Response Tab Tools

The **Design a box** plots are organized into six tabs: `Response`, `Excursion`,
`Impedance`, `Ports`, `Group Delay` and `Atlas`. Driver ranking lives in its own
workspace.

Inside the `Response` tab:

- **Total** is always shown as the baseline without a redundant checkbox;
  optional **Cone** and **Lower port** pens remain immediately available
- **Response frequency window** zooms the log-frequency chart with two handles;
  the numbered **Amplitude (dB)** axis remains visible, auto-fits the selected band and
  **Reset zoom** restores the full simulation range
- **Markers & analysis** collects the `F3`/`F6`/`F10` selector, manual `M1`/`M2`
  positions, MOL/MIL limits, load comparison and the tolerance band
- **Pin response** stores the current total-response curve for A/B overlay;
  replace/clear actions appear only when a pin exists

The cursor table reports frequency, total SPL, impedance and excursion at each
cursor.

### Cone Excursion

The excursion plot shows cone movement.  If `Xmax` is supplied, a reference line
is drawn.

### Electrical Impedance

The impedance plot is an approximate electrical input impedance derived from
the same acoustic load.

### Port Volume Velocity

The port plot compares upper and lower port volume velocity for ported loads.
It is disabled for sealed and infinite-baffle simulations.

### Group Delay

The Group Delay tab plots the total-output group delay in milliseconds.  The
same `group_delay_ms` data is also exported in the response CSV.

## Presets and Export

- In the **Project** popover, **Save preset** downloads current parameters,
  including load and box strategy, as `.lfp` JSON.
- In the same popover, **Load preset** reloads `.lfp` or JSON parameter files.
- **Share via URL** serializes the current design into the browser URL so the
  same state can be reopened or sent to someone else; older presets using the
  former auto-align fields remain compatible.
- **Download response CSV** exports all simulated arrays.

## Validation Status

The acoustic-load module has regression tests for the PCPaudio article example,
reflex, sealed and infinite-baffle paths, T/S derivation, finite arrays and
input validation.  The model is still a first engineering pass; measured
prototypes should be used to calibrate losses and radiation assumptions.
