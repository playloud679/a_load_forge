# src/engine.py — acoustic-load engine

Physics, simulation and analysis for the supported loads (DCCAV, fourth-order
bandpass, sixth-order bandpass, bass reflex, sealed, infinite baffle, passive radiator).  `src/dccav.py` re-exports this module's
public API; the full reference — formulas, assumptions, per-function
contracts and the test list — lives in `docs/dccav.md`.

## Owns

- Physical constants (`RHO_AIR`, `SPEED_OF_SOUND`, `P_REF`, `EPS`,
  `OPTIMIZER_COARSE_POINTS`, `OPTIMIZER_F3_REFINE_POINTS`,
  `PORT_VELOCITY_GUIDELINE_MS`, `PORT_K_FACTOR`, `OPTIMIZER_MAX_PORT_DIAMETER_CM`,
  `PORT_MAX_VOLUME_FRACTION`,
  `PORT_PIPE_RESONANCE_GUARD`) and every dataclass except
  `DriverPresetInfo`: `DriverTS`, `DerivedDriver`, alignments and boxes
  (including `Bandpass4Alignment` / `Bandpass4Box`, `Bandpass6Alignment` / `Bandpass6Box`),
  `OptimizationGoals`, `OptimizedAlignment`, `SimulationResult`,
  `ToleranceBand`, `DesignSpaceMap`, `DriverReferenceMetrics`,
  `DriverBandwidthClass`
- Waveguide topologies: `WaveguideSegment`, `TransmissionLineBox`, `MltlBox`,
  `HornBox` and `TappedHornBox`
- Derivation and alignment: `sd_from_diameter`, `panel_air_load_metrics`,
  `panel_loaded_fs_hz`, `complete_driver`,
  `suggest_alignment`, `suggest_reflex_alignment`,
  `suggest_bandpass4_alignment`, `suggest_bandpass6_alignment`, `suggest_sealed_alignment`,
  `suggest_pr_alignment`,
  `sealed_system_metrics`
- Simulators: `simulate`, `simulate_reflex`, `simulate_bandpass4`, `simulate_bandpass6`, `simulate_passive_radiator`, `simulate_sealed`,
  `simulate_infinite_baffle`, `simulate_transmission_line`, `simulate_mltl`,
  `simulate_quarter_wave`, `simulate_back_loaded_horn` and
  `simulate_tapped_horn` (shared `_electrical_source`, `_limit_curves`,
  `_unported_result` internals)
- Optimizer: `optimize_alignment` with `_optimizer_metrics` /
  `_score_alignment`; untargeted `extension` searches scale advisory ripple,
  excursion and group-delay excesses to 1% and use a 0.002 volume regularizer
  so the lowest credible F3 dominates compactness. The optional
  `frequency_points` / `refine_f3_points` controls let hosted Finder runs use
  30 logarithmic points over the complete band and give only the winner 20
  points around its estimated F3; defaults remain the original 160/0 for local
  optimizer fidelity. If refinement puts DCCAV just below its credibility
  boundary, both tunings are reduced together by the minimum required factor
  and the winner is checked again
- Analysis: `response_metrics`, `response_threshold_frequencies` (using logarithmic frequency interpolation across dB/oct roll-off slopes for sub-Hz F3/F6/F10 accuracy),
  `impedance_peak_frequencies`, `group_delay_ms`, `response_phase_deg`,
  `export_frd_text`, `export_zma_text`, `monte_carlo_response_band`,
  `design_space_box`, `design_space_map`, port geometry helpers,
  `driver_reference_metrics`, `classify_driver_bandwidth`,
  `apply_driver_configuration`, diagnostics and sanity warnings

`apply_driver_configuration` supports one driver, 2–8-driver parallel or
series arrays, mixed `S × P` arrays up to eight drivers, and isobaric arrays up
to 16 total drivers (eight isobaric pairs). Isobaric volume and radiating area
scale per pair; the electrical topology scales Re/Le and total thermal power
scales with the physical driver count.

## Panel air loading

## Distributed waveguides

The waveguide solvers use a loss-bearing, one-dimensional pressure/volume-
velocity transfer matrix. `TransmissionLineBox` accepts stepped uniform
sections and supports open or closed termination; `simulate_quarter_wave()` is
the closed-end convenience wrapper. `MltlBox` places an external vent in
parallel with the line-mouth radiation impedance. `HornBox` generates conical
or exponential sections between throat and mouth for a first-order BLH model.
`TappedHornBox` solves the throat and mouth arms in parallel at the driver tap,
which is the appropriate lumped 1-D abstraction for a tapped horn.

Passive-radiator boxes accept `pr_added_mass_g`. The solver keeps the radiator
compliance fixed and calculates the shifted free-air resonance as
`Fp_eff = Fp * sqrt(Mmp / (Mmp + M_added))`, allowing selectable mechanical PR
presets to be tuned with washers, discs or another added-mass assembly.

These are distributed models, not replacements for a full FEM/BEM or a
measured impedance fit. They omit higher-order transverse modes, cabinet
leakage details, stuffing gradients and diffraction. `line_q` is therefore an
explicit fit parameter; it should be calibrated against an impedance or
near-field measurement before a build is considered final.
BLH and TH results are intended for the low-frequency module band. A real
design still needs an electrical high-pass to control subsonic excursion and a
low-pass/crossover to suppress higher-order modes; these filters are not part
of the distributed acoustic solver.

`DriverTS.le10k_mh` is an optional, display-only voice-coil inductance
measured at 10 kHz (some pro-audio datasheets publish it alongside the usual
1 kHz `le_mh`, e.g. to flag impedance rise at high frequency). It is not used
by any impedance/response formula in this module.

`DriverTS.panel_air_load` defaults to `True`; `panel_coupling` defaults to
`0.90`.  The engine calculates the finite-baffle air-mass increment from the
equivalent piston radius as

```text
Mair = panel_coupling * (8/3) * rho * a^3
a = sqrt(Sd/pi)
Fs,mounted = Fs / sqrt((Mms + Mair)/Mms)
```

The 0.90 coupling is the conventional partial-baffle approximation.  It is a
dimensionless finite-panel proxy rather than a hard-coded frequency offset:
the effect changes with `Sd/Mms`.  Alignment frequencies, simulations,
sealed metrics, reference sensitivity and EBP use mounted Fs.  `Vas`, `Qts`
and `Qms` remain the supplied T/S values; internal Mms/Rms/Bl are re-derived
consistently so the specified Q values remain the model's damping reference.
Set `panel_air_load=False` for the classical free-air equations.
For composite identical-driver sets, `radiating_pistons` keeps the per-cone
area explicit: separate cones each receive their own local `a^3` air mass,
while an isobaric pair still has one externally radiating piston. Monte Carlo
samples preserve that piston count, so tolerance bands do not silently revert
a multiple-driver system to the single-cone radiation-mass model.

The fourth-order bandpass starter uses target `Qbp=0.707`: rear sealed volume
from the classical target-Q relation, front volume `2*Qbp²*Vas`, and vent
tuning `Fs*Qbp/Qts`. The atlas preserves that starter chamber ratio while it
sweeps total volume and `Fp`.

`optimize_alignment(..., load_type="Bandpass 4th order")` searches sealed
volume, ported volume and front tuning; fixed-volume Finder searches project
both chamber volumes onto the exact requested total.
Bandpass optimizer ripple/group-delay metrics stop at the upper -3 dB edge,
and scoring penalizes a missing edge or a passband narrower than 1.4:1.
`bandpass4_diagnostics()` flags extreme tuning and a missing upper -3 dB
crossing when the simulated range is too short to verify the passband.

Ported optimizer candidates are construction-aware, and one function decides
every automatic vent diameter: `port_diameter_for_load()`, called identically
by the optimizer's feasibility metric and by the UI's applied port sizing.
Its floor is `max(port_min_diameter_cm(), port_displacement_min_diameter_cm(),
rated_velocity_diameter_cm())` — Helmholtz zero-length, the drive-independent
gold standard `K*(2*pi*Fb*Sd*Xmax)/v_amm` (`K = PORT_K_FACTOR`, 0 when
Xmax is unpublished), and the diameter keeping peak air speed at or below 5%
of sound speed at the driver's excursion-limited voltage (scaled from the
simulation voltage to the level that reaches Xmax). Above that floor it grows toward a
fabricable ~5 cm duct, but stops at `PORT_MAX_VOLUME_FRACTION` (10%) of the
chamber even if that leaves a shorter duct: small chambers tuned low would
otherwise demand metre-long ducts that invalidate the lumped Helmholtz model.
The result snaps to the sidebar's 0.5 cm grid, rounding *down* whenever that
still clears the floor so grid rounding cannot itself re-break the 10% cap —
rounding up was the exact gap that first let a compliant-looking box round,
in the UI, to an oversized duct. Returns `None` when even the (grid-rounded)
floor breaks the cap: no diameter works for that volume/tuning pair, and
`_optimizer_metrics` reports the *floor's own* smoothly-varying
`port_volume_fraction` for scoring rather than collapsing straight to an
infinite diameter — an earlier version did that and flattened the pattern
search's gradient across the whole infeasible region, making
`optimize_alignment` falsely report "no buildable box" whenever the empirical
starting point sat in that region, even with a compliant box nearby.
Candidates needing more than 95% of the 60 cm diameter ceiling, or whose
`port_diameter_for_load` diameter breaks the duct-volume cap, are treated as
infeasible. `port_pipe_resonance_hz()` reports the duct's first half-wave
resonance (`c/2L`); the UI warns when it falls below
`PORT_PIPE_RESONANCE_GUARD` (4×) times the tuning. A third, independent
rejection tier compares the sized duct's length against
`port_max_straight_length_cm()` (the box treated as a cube): a duct can stay
a small fraction of a large chamber's *volume* while still being longer than
the chamber can hold in a straight *run* — a thin, deeply-tuned vent moves
little air per length, so `port_volume_fraction()` alone misses it. DCCAV
candidates below `F3 >= 0.67*fl` are likewise excluded from normal objectives
trade-offs.

If the primary search (from the empirical starting alignment) lands in the
infeasible score tier, `optimize_alignment` retries from a handful of
deterministic points spread along the search box's diagonal (fixed fractions
`0.75, 0.25, 0.5` of the log-space bounds, no randomness) before giving up:
local coordinate descent can stall in an infeasible neighborhood even with a
fully smooth score, when the compliant region sits far from the starting
point (found via a reflex box search that stayed stuck for a driver whose
golden-rule/velocity port floor made every box near the empirical Vas/Fs
starting point need an over-long duct, while a compliant box existed
elsewhere in the search bounds). If every attempt still lands in the
infeasible tier, `optimize_alignment` raises an explicit optimizer error
instead of returning its least-bad invalid candidate.

## Invariants

- No knowledge of presets or prices: functions take `DriverTS`/box values.
- SI units internally; litre/Hz/mm/cm² at the API boundary.
- Fourth-order bandpass uses an enclosed driver between a sealed rear chamber
  and vented front chamber. Only the front vent enters the far-field total;
  the cone trace is retained as an internal-motion diagnostic.
- Sixth-order bandpass uses an enclosed driver between two ported chambers.
  The rear and front vents have opposite acoustic polarity and their vector
  difference forms the far-field total; the cone trace is an internal-motion
  diagnostic. Equal chambers/tunings cancel externally.
  `suggest_bandpass6_alignment` returns an asymmetric `Bandpass6Alignment`
  with rear/front volume ratio 2:1 and tuning ratio 1:2;
  `simulate_bandpass6()` solves the coupled acoustic circuit (rear port+box,
  front port+box in series with the driver acoustic impedance).
  `optimize_alignment(load_type="Bandpass 6th order")` searches rear volume,
  rear tuning, front volume and front tuning in log-space.
- Importable both as `src.engine` (package) and `engine` (top-level with
  `src/` on `sys.path`); it must not import `presets`/`pricing`.

Cloud Run Finder optimization uses an adaptive 80-point frequency grid around
the loaded resonance; local runs retain the original 160-point grid.
