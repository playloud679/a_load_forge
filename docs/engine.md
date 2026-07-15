# src/engine.py — acoustic-load engine

Physics, simulation and analysis for the supported loads (DCCAV, fourth-order
bandpass, bass reflex, sealed, infinite baffle).  `src/dccav.py` re-exports this module's
public API; the full reference — formulas, assumptions, per-function
contracts and the test list — lives in `docs/dccav.md`.

## Owns

- Physical constants (`RHO_AIR`, `SPEED_OF_SOUND`, `P_REF`, `EPS`,
  `PORT_VELOCITY_GUIDELINE_MS`, `OPTIMIZER_MAX_PORT_DIAMETER_CM`,
  `PORT_DISPLACEMENT_COEFFICIENT_CM`, `PORT_MAX_VOLUME_FRACTION`,
  `PORT_PIPE_RESONANCE_GUARD`) and every dataclass except
  `DriverPresetInfo`: `DriverTS`, `DerivedDriver`, alignments and boxes
  (including `Bandpass4Alignment` / `Bandpass4Box`),
  `OptimizationGoals`, `OptimizedAlignment`, `SimulationResult`,
  `ToleranceBand`, `DesignSpaceMap`, `DriverReferenceMetrics`,
  `DriverBandwidthClass`
- Derivation and alignment: `sd_from_diameter`, `complete_driver`,
  `suggest_alignment`, `suggest_reflex_alignment`,
  `suggest_bandpass4_alignment`, `suggest_sealed_alignment`,
  `sealed_system_metrics`
- Simulators: `simulate`, `simulate_reflex`, `simulate_bandpass4`, `simulate_sealed`,
  `simulate_infinite_baffle` (shared `_electrical_source`, `_limit_curves`,
  `_unported_result` internals)
- Optimizer: `optimize_alignment` with `_optimizer_metrics` /
  `_score_alignment`
- Analysis: `response_metrics`, `response_threshold_frequencies`,
  `impedance_peak_frequencies`, `group_delay_ms`, `response_phase_deg`,
  `export_frd_text`, `export_zma_text`, `monte_carlo_response_band`,
  `design_space_box`, `design_space_map`, port geometry helpers,
  `driver_reference_metrics`, `classify_driver_bandwidth`,
  `apply_driver_configuration`, diagnostics and sanity warnings

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

Ported optimizer candidates are construction-aware: the Helmholtz zero-length
diameter is calculated for every vent (both DCCAV ports), and candidates needing
more than 95% of the UI's 60 cm diameter ceiling are treated as infeasible. The
required diameter also includes the area needed to keep peak air speed at or
below 5% of sound speed at the optimization voltage, plus the drive-independent
displacement floor `port_displacement_min_diameter_cm()` (the Small/Dickason
minimum-area golden rule `20.3*(Vd²/Fb)^0.25` cm with `Vd = Sd*Xmax` in litres;
0 when Xmax is unpublished). A second reflex directive rejects candidates whose
smallest workable duct would displace more than `PORT_MAX_VOLUME_FRACTION`
(10%) of the chamber it tunes (`port_volume_fraction()`, evaluated per port at
that port's own required diameter): small chambers tuned low would otherwise
demand metre-long ducts that invalidate the lumped Helmholtz model.
`port_pipe_resonance_hz()` reports the duct's first half-wave resonance
(`c/2L`); the UI warns when it falls below `PORT_PIPE_RESONANCE_GUARD` (4×)
times the tuning. DCCAV candidates below
`F3 >= 0.67*fl` are likewise excluded from normal objective trade-offs. If the
search never reaches the feasible region it raises an explicit optimizer error
instead of returning its least-bad invalid candidate.

## Invariants

- No knowledge of presets or prices: functions take `DriverTS`/box values.
- SI units internally; litre/Hz/mm/cm² at the API boundary.
- Fourth-order bandpass uses an enclosed driver between a sealed rear chamber
  and vented front chamber. Only the front vent enters the far-field total;
  the cone trace is retained as an internal-motion diagnostic.
- Importable both as `src.engine` (package) and `engine` (top-level with
  `src/` on `sys.path`); it must not import `presets`/`pricing`.
