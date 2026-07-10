# `src/__init__.py` — package exports

Defines the public package surface for Load Forge's active audio simulator.

Exports the acoustic-load dataclasses and helpers from `src/dccav.py`:

- `DriverTS`, `DerivedDriver`, `DccavAlignment`, `DccavBox`,
  `ReflexAlignment`, `ReflexBox`, `SimulationResult`
- `driver_preset_names()`, `get_driver_preset()`
- `sd_from_diameter()`, `complete_driver()`, `suggest_alignment()`,
  `suggest_reflex_alignment()`
- `simulate()`, `simulate_reflex()`, `response_metrics()`,
  `response_threshold_frequencies()`, `impedance_peak_frequencies()`,
  `equivalent_sealed_fc_hz()`

The Streamlit app imports `dccav` directly for hot-reload behavior, but tests and
future package users can import these names from `src`.
