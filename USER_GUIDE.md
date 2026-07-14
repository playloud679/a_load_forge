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

Boxed loads use one three-state control:

- **Suggested** follows the current driver and load automatically. Box volume
  and tuning fields remain visible but locked.
- **Optimized** exposes extension, ripple, excursion, group-delay and volume
  goals. **Run optimizer and apply** updates the active box.
- **Manual** unlocks direct volume and tuning edits, `-3%` / `+3%` nudges and a
  reset action for the selected load.

Infinite baffle has no enclosure, so the strategy control is disabled.

### DCCAV Alignment

The app computes a first-pass alignment:

```text
Vh = 2.05 * Qts^2 * Vas
Vl = 4.13 * Qts^2 * Vas
fh = 1.22 * Fs / Qts
fl = 0.466 * Fs / Qts
f3 = 0.83 * fl
```

With **Suggested**, these values are applied and kept synchronized
automatically. With **Manual**, **Reset to suggested alignment** restores them;
the editable `Vh`, `fh`, `Vl` and `fl` controls also provide `-3%` and `+3%`
nudges.

### Bass Reflex Alignment

The normal reflex path starts from:

```text
Vb = Vas
Fb = Fs
```

With **Suggested**, these values are applied automatically. With **Manual**,
**Reset to suggested reflex** restores them. This is a plain starting point,
not a named QB3/SBB4/EBS alignment.

### Acoustic Suspension Alignment

The sealed-box starter targets `Qtc=0.707` when that is possible from the
driver's `Qts`, and displays `Vb`, `Fc` and achieved `Qtc`.  `Vb`, `Qabs` and
`Qleak` remain editable; there are no port controls or port traces.

### Fourth-order Bandpass Alignment

The driver is enclosed between a sealed rear chamber `Vs` and ported front
chamber `Vp`; only the front vent radiates. The symmetrical starter targets
`Qbp=0.707` and exposes `Vs`, `Vp` and `Fp`. Suggested keeps it synchronized,
Optimized searches both chamber volumes and tuning, and Manual unlocks them.

### Infinite Baffle

Infinite baffle has no box or optimizer controls.  It keeps the driver's
free-air `Fs` and `Qts` and assumes the rear wave is perfectly isolated.  The
ideal model does not include finite-panel diffraction, baffle step or leakage.

The suggested alignment is an empirical small-signal starting point, not a full
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

### Find a Driver

The **Find a driver** workspace has independent search constraints; it does not
reuse or alter the active design controls:

- **Comparison volume** is exact: `Vh+Vl` for DCCAV, `Vs+Vp` for bandpass, or `Vb` for reflex and
  acoustic suspension. Infinite baffle ignores it.
- **Ranking goal** and **Comparison voltage** define the main comparison.
- **Optimize each candidate at the comparison volume** keeps the volume fixed
  while tuning the remaining alignment parameters.
- **Advanced ranking constraints** reveals desired bass extension F3, allowed
  ripple, maximum excursion relative to each driver's Xmax, group delay and the
  clearly labelled evaluation-frequency range.
- **Drivers to evaluate**, **Top results to show** and **Simulation resolution**
  control search cost and output size.

A new Finder starts with a practical quick-scan profile: 40 L, `Balanced`,
2.83 V, F3 target 0 Hz (deepest available extension), 3 dB ripple, 1× Xmax,
30 ms group delay, a 10-300 Hz evaluation range, 500 evaluated drivers, 20
results and 240 simulation points.
Per-candidate optimization is initially off because it is substantially
slower; enable it after filters have produced a useful shortlist. **Reset
defaults** restores this profile without changing the active design.

**Rank candidates** evaluates only the presets currently admitted by the
sidebar filters. Each result can include class, price, purchase link and a
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

The **Design a box** plots are organized into five tabs: `Response`,
`Excursion`, `Impedance`, `Ports` and `Group Delay`. Driver ranking lives in its
own workspace instead of a sixth tab.

Inside the `Response` tab:

- response pens select visible traces
- automatic cursors mark `F3`, `F6` and `F10`
- enabling the **Manual** cursor toggle reveals `M1` and `M2` positions
- **Pin response** stores the current total-response curve for A/B overlay
- **Compare loads** overlays all five loads at equal comparison volume

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
