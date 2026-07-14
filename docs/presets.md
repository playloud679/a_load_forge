# src/presets.py — driver preset catalog

Built-in driver presets plus the optional Loudspeaker Database import, with
brand/size metadata and retailer price enrichment.  `src/dccav.py`
re-exports the public API; detailed contracts live in `docs/dccav.md`.

## Owns

- `DriverPresetInfo` dataclass and `LOUDSPEAKER_DATABASE_PATH`
- `DRIVER_PRESETS`: the curated built-in catalog (KEF article example,
  Beyma, Turbosound, Scan-Speak, Dayton, SB Audience, LaVoce, MarkAudio,
  Aiyima minis, …)
- `_load_loudspeaker_database_presets()` (`lru_cache(maxsize=1)`): lazy
  loader for `data/loudspeaker_database_drivers.json`; missing or invalid
  files degrade to the built-in catalog only
- Public catalog API: `driver_preset_names()`, `driver_preset_info(name)`,
  `get_driver_preset(name)`

## Invariants

- Depends on `engine` (for `DriverTS`/`sd_from_diameter`) and `pricing`
  (for `_preset_price`/`_valid_price`); never the other way around.
- Preset info enriches prices at read time, so refreshed price data shows
  up after `_load_loudspeaker_database_presets.cache_clear()` (tests rely
  on clearing both this cache and the pricing loader's).
- Importable both as `src.presets` and top-level `presets`.
