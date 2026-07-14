# src/engine.py — acoustic-load engine

Physics, simulation and analysis for the four supported loads (DCCAV, bass
reflex, sealed, infinite baffle).  `src/dccav.py` re-exports this module's
public API; the full reference — formulas, assumptions, per-function
contracts and the test list — lives in `docs/dccav.md`.

## Owns

- Physical constants (`RHO_AIR`, `SPEED_OF_SOUND`, `P_REF`, `EPS`,
  `PORT_VELOCITY_GUIDELINE_MS`) and every dataclass except
  `DriverPresetInfo`: `DriverTS`, `DerivedDriver`, alignments, boxes,
  `OptimizationGoals`, `OptimizedAlignment`, `SimulationResult`,
  `ToleranceBand`, `DesignSpaceMap`, `DriverReferenceMetrics`,
  `DriverBandwidthClass`
- Derivation and alignment: `sd_from_diameter`, `complete_driver`,
  `suggest_alignment`, `suggest_reflex_alignment`,
  `suggest_sealed_alignment`, `sealed_system_metrics`
- Simulators: `simulate`, `simulate_reflex`, `simulate_sealed`,
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

## Invariants

- No knowledge of presets or prices: functions take `DriverTS`/box values.
- SI units internally; litre/Hz/mm/cm² at the API boundary.
- Importable both as `src.engine` (package) and `engine` (top-level with
  `src/` on `sys.path`); it must not import `presets`/`pricing`.
