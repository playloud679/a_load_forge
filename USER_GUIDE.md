# Load Forge User Guide

Load Forge simulates acoustic loudspeaker loads from driver Thiele/Small
parameters. It supports DCCAV, fourth- and sixth-order bandpass, conventional
bass reflex with either a port or passive radiator, acoustic suspension
(sealed box) and ideal infinite baffle.

## Workspaces

The two large image tabs below the header separate two different jobs. The red
**Bass Match** artwork and blue **Box Design** artwork are themselves clickable;
the active workspace has a matching illuminated outline.

- **Design a box** starts from one driver, chooses an alignment strategy and
  exposes the simulation results and plots.
- **Bass Match** starts from enclosure and ranking constraints, evaluates
  only the catalog candidates allowed by the sidebar filters, and preserves the
  current design until a candidate is explicitly applied.

The collapsible **Project** section sits at the top of the sidebar. Load Forge creates a
browser-local project automatically on first use and autosaves it after every
interaction. One existing project opens automatically; when the browser holds
several projects, the normal app opens immediately with **Project** expanded so
one can be opened or **New project** can be chosen. The section renames, creates,
switches, downloads and imports projects without a separate landing page.

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

The compact **Load type** cards switch between `Infinite baffle`, `Sealed`,
`Bass reflex`, `Bandpass 4th order`, `Bandpass 6th order` and `DCCAV`.
Each small diagram is itself clickable, its name is overlaid on
the image and the active load has a red outline plus a check indicator. The
cards use a compact 3+3 grid and remain keyboard-focusable. In the Finder the
same cards toggle multiple loads for comparison. Search, source, brand, size,
class and price filters narrow the driver library in both workspaces.

In **Design a box**, the **Driver preset** selector loads built-in examples
immediately. **Driver T/S values** stays collapsed for catalog presets and
opens automatically for `Custom`; expand it whenever the values need to be
inspected or overridden.

`Beyma 12CMV2` uses the manufacturer T/S values from the supplied datasheet
screenshot, including `Sd=0.053 m2`; the nominal 300 mm diameter is not used as
piston area.

For catalog presets, the Driver panel shows nominal frame size, `Sd` and the
equivalent circular effective-piston diameter together. The Finder candidate
library exposes the same three columns. The nominal frame diameter is a
commercial/mechanical size and is normally larger than the effective piston;
it must not be converted directly into `Sd`.

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

### Sixth-order Bandpass Alignment

The driver separates two vented chambers. The rear chamber uses `Vr` / `Fr`
and the front chamber uses `Vp` / `Fp`; both vents contribute acoustic loading,
while their geometry and volume velocity are reported separately. The starter
uses symmetrical chamber targets and the optimizer searches the four active
box parameters within the selected constraints.

### Passive Radiator Resonator

Inside a Bass-reflex design, **Ports → Resonator type** replaces the duct with
a suspended passive diaphragm without changing the acoustic-load topology.
Manual controls expose box `Vb`, radiator area `Sp`, resonance `Fp`, mechanical
`Qmp`, moving mass `Mmp` and radiator `Xmax`. The Ports tab reports radiator
volume velocity and warns when simulated travel exceeds its rating. Legacy
presets saved with `load_type="Passive radiator"` are migrated automatically.
Selecting the PR switches Box strategy to `Manual`, because the generic Atlas
optimizer sweeps duct tuning rather than radiator mass and suspension.

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
- `Ports → Resonator type`: `Port` or `Passive radiator`
- for a port: `Fb tuning`, vent diameter and `Qport`
- for a passive radiator: `Sp`, `Fp`, `Qmp`, `Mmp` and radiator `Xmax`
- `Qabs`, `Qleak`: box and leakage losses

For `Sealed`, controls are sealed `Vb`, `Qabs` and `Qleak`.
For `Bandpass 4th order`, controls are rear `Vs`, front `Vp`, `Fp`, independent
chamber loss factors, front `Qport` and front-vent diameter.
For `Bandpass 6th order`, controls are rear `Vr` / `Fr`, front `Vp` / `Fp`,
independent losses and both vent diameters.
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
- sixth-order bandpass: rear- and front-vent diameters
- bass reflex with passive radiator: equivalent diaphragm diameter and travel
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

### Bass Match

The **Bass Match** workspace has independent search constraints; it does not
reuse or alter the active design controls. Target and performance controls use
the sidebar, while the denser library filters use the wider main workspace in
a three-step workflow:

1. **Target enclosure** selects the load, maximum enclosure volume and voltage.
2. **Performance goal** selects the optimization objective, F3 target and
   ripple allowance, plus optional maximum `Mms` and nominal/1 kHz `Le`
   filters. A zero maximum disables either filter; while active, candidates
   without the corresponding published value are excluded. Excursion,
   group-delay and minimum-SPL limits stay in **Advanced constraints**; scan
   range, result count and resolution stay in **Advanced scan**.
3. **Candidate library** filters the catalog in the main workspace by text,
   provenance, size, brand, bandwidth class and optional price ceiling.
   Provenance groups built-ins, direct manufacturer sources, official
   archives, retailer observations and user-supplied records under **Load
   Forge database**. LSDB, VituixCAD and Speaker Box Lite remain separate
   external database choices. The table retains the exact source beside the
   compact category. The numeric price limit appears only when its checkbox is
   active. Typing in **Search preset** immediately lists the first matching
   driver names before a scan is started.

   In each checkbox group, **All** is a true group toggle. When active, every
   option is visibly checked. Unchecking one option clears **All** while
   preserving every other selection; checking all individual options restores
   **All**. Turning **All** off clears the complete group, after which
   individual options can be enabled.

**Run a Match** appears once as the primary action above the candidate-library
table; it is not duplicated in the sidebar. Before a scan, the workspace is
titled **Candidate library**; completed scans use
**Recommended drivers** and show the active load, volume cap and objective.
Missing values render as em dashes and columns with no data are omitted, while
the ranked table and candidate CSV expose nominal `Size`, piston area `Sd` and
only the compact `Vtot` value for enclosure volume.
Individual chamber volumes, tuning/system frequencies and alignment details
remain internal so a selected candidate can still be applied to Design.

`Minimum SPL` is evaluated against each row's simulated **Peak LF SPL** at the
selected comparison voltage. Values below the threshold are excluded from the
result list; when none remain, Finder shows a dedicated no-match message.

- **Maximum volume** is a ceiling, not a forced size. Finder optimizes each
  driver independently and may return a smaller `Vh+Vl` for DCCAV, chamber
  total for bandpass, or `Vb` for reflex/sealed when that alignment scores
  better. Infinite baffle ignores the setting.
- **Optimization goal** selects the same optimizer objective as the Design
  workspace — `Max extension`, `Balanced` or `Flattest`. Every candidate box
  is derived by that one optimizer without exceeding the maximum volume and at
  the comparison voltage; infinite baffle candidates are ranked in free air.
- **Optimization constraints** sets desired bass extension F3, allowed
  ripple, maximum excursion relative to each driver's Xmax, group delay and the
  clearly labelled evaluation-frequency range.
- **Top results to show** and **Simulation resolution** control output size
  and search cost. Every scan evaluates the entire filtered library; the
  matching-preset count above **Run a Match** updates live as filters change.
  Every match shows a live per-candidate progress bar. Small scans advance on
  the serial path; scans above eight candidates use worker processes and keep
  the same progress indicator through every selected load.

A new Finder starts with a practical profile: 40 L, `Balanced`, 2.83 V, F3
target 0 Hz (deepest available extension), 3 dB ripple, 1× Xmax, 30 ms group
delay, a 10-300 Hz evaluation range, 20 results and 240 simulation points.
**Reset Finder defaults** restores this profile without changing the active
design.

**Run a Match** evaluates every preset currently admitted by the active library
filters. Each result can include class, price, purchase link and a
normalized response sparkline. The compact result table omits brand, nominal
size, F6, F10, ripple and maximum excursion; these values still participate in
the underlying simulation and constraints where applicable. Selecting a row
opens a preview focused on F3, MOL at F3, peak LF SPL and minimum impedance
without changing the active design. **Apply candidate to design** is the only
action that replaces it; the app then returns to **Design a box** in
**Manual** mode so the ranked enclosure is preserved exactly.

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
`Subwoofer`, `Woofer` or `Midbass`.

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

The **Design a box** plots use contextual tabs. `Response`, `Excursion`,
`Impedance` and `Group Delay` are always available. `Ports` appears only for
ported, passive-radiator and bandpass loads; `Atlas` is hidden for infinite
baffle and passive-radiator designs because the generic design-space sweep is
defined for duct geometry. Driver ranking lives in its own workspace.

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

- The active project is autosaved in this browser through IndexedDB. Browser
  projects remain on the current device and browser profile; private browsing,
  clearing site data or changing browser does not carry them across.
- **Download .lfp** creates a portable backup containing the complete design
  plus the Bass Match brief, library filters, ranked results and result
  context. Non-finite simulation placeholders are normalized to strict JSON.
- **Open .lfp project or CRW driver** restores current v2 projects. Older flat
  `.lfp` and JSON parameter presets remain compatible and load into the active
  project.
- **Share via URL** serializes the current design into the browser URL so the
  same state can be reopened or sent to someone else; older presets using the
  former auto-align fields remain compatible.
- **Download response CSV** exports all simulated arrays.

## Validation Status

The acoustic-load module has regression tests for the PCPaudio article example,
reflex, sealed and infinite-baffle paths, T/S derivation, finite arrays and
input validation.  The model is still a first engineering pass; measured
prototypes should be used to calibrate losses and radiation assumptions.
