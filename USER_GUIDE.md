# Load Forge User Guide

Load Forge simulates acoustic loudspeaker loads from driver Thiele/Small
parameters.  It supports DCCAV, conventional bass reflex, acoustic suspension
(sealed box) and ideal infinite baffle.

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

The **Load type** selector switches between `DCCAV`, `Bass reflex`,
`Acoustic suspension` and `Infinite baffle`.  The
**Driver preset** selector loads built-in examples immediately.  When
**Auto-align box from T/S** is enabled, changing a preset, load type or T/S
value also updates the active box controls, so the plots follow the selected
driver without an extra apply step.

`Beyma 12CMV2` uses the manufacturer T/S values from the supplied datasheet
screenshot, including `Sd=0.053 m2`; the nominal 300 mm diameter is not used as
piston area.

The preset list also includes selected Beyma 12" low/mid and woofer models from
Beyma's official XLS catalog.  Catalog units are converted internally to the
simulator units.

### DCCAV Alignment

The app computes a first-pass alignment:

```text
Vh = 2.05 * Qts^2 * Vas
Vl = 4.13 * Qts^2 * Vas
fh = 1.22 * Fs / Qts
fl = 0.466 * Fs / Qts
f3 = 0.83 * fl
```

Use **Apply suggested alignment** to copy those values into the editable box
controls.  The editable `Vh`, `fh`, `Vl` and `fl` controls also include `-3%`
and `+3%` buttons for quick tuning around the current design point.

### Bass Reflex Alignment

The normal reflex path starts from:

```text
Vb = Vas
Fb = Fs
```

Use **Apply suggested reflex** to copy those values into the editable `Vb` and
`Fb` controls.  This is a plain starting point, not a named QB3/SBB4/EBS
alignment.

### Acoustic Suspension Alignment

The sealed-box starter targets `Qtc=0.707` when that is possible from the
driver's `Qts`, and displays `Vb`, `Fc` and achieved `Qtc`.  `Vb`, `Qabs` and
`Qleak` remain editable; there are no port controls or port traces.

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

For `Acoustic suspension`, controls are sealed `Vb`, `Qabs` and `Qleak`.
`Infinite baffle` has no enclosure controls.

Higher Q means lower loss for leakage/ports.  Very low Q values intentionally
damp the response.

### Batch LF Finder

`Box volume (L)` is an exact comparison volume, including when **Optimize each
driver box** is enabled.  A 50 L batch therefore returns `Vh+Vl=50 L` for every
DCCAV candidate or `Vb=50 L` for every bass-reflex/acoustic-suspension
candidate.  Infinite baffle ignores this field because it has no enclosure.

## Outputs

### Metrics

The top metrics show:

- peak low-frequency SPL estimate
- estimated `F3`, `F6` and `F10`
- maximum cone excursion
- minimum electrical impedance

Suggested alignment metrics are shown separately for comparison.

### LF Load Response

The response plot shows the low-frequency acoustic-load estimate:

- total estimated response
- direct driver contribution
- lower external port contribution

For DCCAV, the lower-port branch naturally rolls off above the tuned range even
without an electrical crossover.  For bass reflex, the port trace is the vent
output.  Sealed and infinite-baffle total response is the exposed cone front
alone.  The SPL scale is an internal estimate for comparing alignments, not a
calibrated far-field or full-range front-driver radiation model.

### Plot Tools

The `Plot Tools` section above the response plot selects visible response and
port traces and enables cursors.  Pen controls can all be off for a plot.
Automatic cursors mark `F3`, `F6` and `F10`; manual cursors `M1` and `M2` can be
placed at any frequency in the simulated range.  The cursor table reports
frequency, total SPL, impedance and excursion at each cursor.

### Cone Excursion

The excursion plot shows cone movement.  If `Xmax` is supplied, a reference line
is drawn.

### Electrical Impedance

The impedance plot is an approximate electrical input impedance derived from
the same acoustic load.

### Port Volume Velocity

The port plot compares upper and lower port volume velocity for ported loads.
It is disabled for sealed and infinite-baffle simulations.

## Presets and Export

- **Save preset** downloads current parameters, including the selected load type,
  as `.lfp` JSON.
- **Load preset** reloads `.lfp` or JSON parameter files.
- **Download response CSV** exports all simulated arrays.

## Validation Status

The acoustic-load module has regression tests for the PCPaudio article example,
reflex, sealed and infinite-baffle paths, T/S derivation, finite arrays and
input validation.  The model is still a first engineering pass; measured
prototypes should be used to calibrate losses and radiation assumptions.
