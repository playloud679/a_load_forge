# src/presets.py — driver preset catalog

Built-in driver presets plus two optional external catalogs, with brand/size
metadata and retailer price enrichment. `src/dccav.py` re-exports the public
API; detailed contracts live in `docs/dccav.md`.

## Two external catalogs — do not merge them

- `data/loudspeaker_database_drivers.json` (`LOUDSPEAKER_DATABASE_PATH`):
  the loudspeakerdatabase.com import (`tools/import_loudspeaker_database.py`).
  **Not safe to redistribute in a public build** — it is third-party
  aggregated data, not manufacturer-original. Keep it out of any public
  export/release artifact; it stays fine as a tracked file in this private repo.
- `data/manufacturer_drivers.json` (`MANUFACTURER_DATABASE_PATH`): presets
  extracted directly from manufacturer sites — HTML product pages, PDF
  datasheets, public JSON APIs — by `tools/crawl_thiele_small.py` and
  `tools/crawl_driver_datasheets.py`, whose catalog defaults both point here.
  Independent of LSDB and safe to ship publicly.

Never write LSDB-sourced fields into a manufacturer-catalog row or vice versa;
if a fix needs to move data between them, do it through the crawler tools'
own merge functions, not a hand edit, so provenance in `website_fields` stays
correct.

## Owns

- `DriverPresetInfo` dataclass, `LOUDSPEAKER_DATABASE_PATH`, `MANUFACTURER_DATABASE_PATH`
- `DRIVER_PRESETS`: the curated built-in catalog (KEF article example,
  Beyma, Turbosound, Scan-Speak, Dayton, SB Audience, LaVoce, MarkAudio,
  Aiyima minis, …)
- `_load_external_presets(path, ...)`: shared lazy loader used by both
  catalogs; missing or invalid files degrade to whatever tiers remain.
- `_load_loudspeaker_database_presets()` / `_load_manufacturer_presets()`
  (`lru_cache(maxsize=1)` each): the two catalog-specific loaders. The
  manufacturer loader dedupes its names against the LSDB tier's, so a name
  never collides across catalogs.
- `_external_tiers()`: the ordered list `[LSDB, manufacturer]` that
  `driver_preset_names/info/get_driver_preset` walk after the built-ins.
- Public catalog API: `driver_preset_names()`, `driver_preset_info(name)`,
  `get_driver_preset(name)`

## Invariants

- Depends on `engine` (for `DriverTS`/`sd_from_diameter`) and `pricing`
  (for `_preset_price`/`_valid_price`); never the other way around.
- Preset info enriches prices at read time, so refreshed price data shows
  up after clearing both external-loader caches and the pricing loader's.
- Importable both as `src.presets` and top-level `presets`.
- Provenance stays in each row's `source` / `website_fields`, never
  mislabelled as the other catalog's origin.
- Imported rows whose case-insensitive brand and model match a curated
  built-in preset are omitted from the runtime list. The generated catalog
  keeps their crawl provenance, while the app exposes the richer built-in
  record only once. The same identity check runs LSDB-then-manufacturer, so a
  manufacturer row matching an LSDB entry is skipped rather than duplicated.
- `_driver_ts_from_mapping(values)` reads a JSON "driver" record into
  `DriverTS`; optional fields (`le10k_mh`, `mms_g`, `cms_mm_per_n`, `bl_tm`)
  stay `None` when absent rather than defaulting to `0.0`, matching how
  `engine.DriverTS` distinguishes "not measured" from "measured as zero".
External web listings are deduplicated by normalized brand/model and nominal
electrical resistance.  Impedance, inch and generic product words are removed
from the comparison key, while the resistance keeps real 4/8-ohm variants
separate.  When duplicate listings remain, the record with more complete T/S
data is retained, then the lower valid price breaks ties.
