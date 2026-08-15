# `src/__init__.py` — package exports

Defines the public package surface for Load Forge's active audio simulator.

Exports the acoustic-load dataclasses and helpers from the neutral
`src/acoustics.py` facade:

- `DriverTS`, `DerivedDriver`, `DccavAlignment`, `DccavBox`,
  `ReflexAlignment`, `ReflexBox`, `SealedAlignment`, `SealedBox`,
  `OptimizationGoals`, `OptimizedAlignment`, `SimulationResult`
- `driver_preset_names()`, `get_driver_preset()`
- `sd_from_diameter()`, `complete_driver()`, `suggest_alignment()`,
  `suggest_reflex_alignment()`, `suggest_sealed_alignment()`,
  `sealed_system_metrics()`
- `simulate()`, `simulate_reflex()`, `simulate_sealed()`,
  `simulate_infinite_baffle()`, `optimize_alignment()`, `group_delay_ms()`,
  `response_metrics()`,
  `response_threshold_frequencies()`, `impedance_peak_frequencies()`,
  `equivalent_sealed_fc_hz()`

The Streamlit app imports `acoustics` directly for hot-reload behavior. Package
users can import the facade as `src.acoustics` or these names from `src`;
`src.dccav` remains a compatibility alias only.
