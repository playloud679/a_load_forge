# `src/dccav.py` — acoustic-load public API

Public API reference for the acoustic-load simulators: DCCAV / double series
resonator based on the PCPaudio/G.P. Matarazzo article `Teoría y práctica del
doble resonador en serie`, fourth-order bandpass, conventional bass reflex,
closed-box acoustic suspension and infinite baffle.

`src/dccav.py` is a compatibility facade: the implementation lives in
`src/engine.py` (physics, simulation, optimizer, analysis — see
`docs/engine.md`), `src/presets.py` (driver catalog — `docs/presets.md`) and
`src/pricing.py` (retailer prices — `docs/pricing.md`).  Importing `dccav`
exposes everything documented here, both as a top-level module (`import
dccav` with `src/` on `sys.path`, used by `ui_app.py`) and as part of the
package (`from src import dccav`, used by the tests).

The engine works in the frequency domain with lumped acoustic impedances and
returns arrays for plotting SPL, cone excursion, impedance and port volume
velocities.

## Models

The DCCAV topology is:

```text
driver -> upper volume || upper port -> lower volume || lower port
```

The upper chamber `Vh` is tuned to `fh`; its port discharges into the lower
chamber `Vl`, which is tuned to `fl` and vents to the outside.

The woofer cone is treated as exposed on its front side.  Internally, the
acoustic circuit solves the cone volume velocity entering the rear DCCAV load;
the externally radiated cone contribution has the opposite sign.  Total LF
response is therefore the vector sum of the front cone radiation and the lower
port radiation, not a scalar sum.

The driver free-air acoustic impedance is:

```text
Zas = Rat + j*w*Mas + 1/(j*w*Cas)
```

with:

- `Mas = Mms / Sd^2`
- `Cas = Cms * Sd^2`
- `Rat = (Rms + Bl^2 / Re) / Sd^2`

Volume losses use the compliance branch `Zab = (Rab + 1/(j*w*Cab)) // Ral`.
Port tuning uses `Zap = Rap + j*w*Map`, with `Map` solved from the requested
box volume and tuning frequency.

The bass-reflex topology is:

```text
driver -> box volume || vent
```

`simulate_reflex()` uses the same driver model, exposed front cone radiation,
box compliance, port mass/loss and electrical impedance calculation as the
DCCAV solver, but with a single acoustic node.

The fourth-order bandpass topology encloses the driver between two chambers:

```text
sealed rear chamber -> driver -> ported front chamber || vent -> listener
```

Both chamber impedances load the cone in series. Only the front vent radiates
externally; the returned cone SPL is an internal-motion diagnostic and is not
summed into total response.

The acoustic-suspension topology is a sealed compliance behind the driver:

```text
driver -> closed box volume
```

`simulate_sealed()` returns only the exposed front-cone radiation.  Its
classical system metrics are `Fc = Fs*sqrt(1+Vas/Vb)` and
`Qtc = Qts*sqrt(1+Vas/Vb)`; `Qabs` and `Qleak` add acoustic loss to the closed
volume.

`simulate_infinite_baffle()` assumes a perfectly isolating partition with no
finite rear volume, leakage or rear radiation reaching the listener.  It has
no port output and no box parameter to optimize.  The default panel-air-load
correction lowers the mounted resonance; finite-panel diffraction and baffle
step remain outside this ideal model.

## Public API

### `DriverTS`

Dataclass for the input Thiele/Small parameters:

- required: `fs_hz`, `vas_l`, `qts`, `qms`, `re_ohm`, `sd_cm2`
- optional: `le_mh`, `xmax_mm`, `pe_w`, `mms_g`, `cms_mm_per_n`, `bl_tm`,
  `panel_air_load` (default `True`), `panel_coupling` (default `0.90`) and
  `radiating_pistons` (default `1`)

If optional `Mms`, `Cms` or `Bl` are not supplied, they are derived from
`Fs`, `Vas`, `Qts`, `Qms`, `Re` and `Sd`.

### `panel_air_load_metrics(ts) -> tuple[float, float]`

Returns added panel-coupled air mass in grams and mounted resonance in Hz.
The increment is `panel_coupling * (8/3) * rho * a^3`, where
`a=sqrt(Sd/pi)`.  It is enabled by default and uses a 90% partial-baffle
coupling.  The UI exposes both the on/off choice and coupling; disabling it
restores the classical free-air T/S results.  This models the resonance and
sensitivity change from diaphragm air loading, but not diffraction or baffle
step. For a composite set of separate identical drivers, the total `Sd` is
split across `radiating_pistons` before applying the cubic radius term and the
per-cone air masses are summed. Isobaric pairs keep one radiating piston.

The AFW FE126 validation (`Fs=89.4 Hz`, `Sd=63.61727 cm²`) gives 0.2581 g of
additional mass, mounted Fs 85.2385 Hz and sealed Fc 155.1741 Hz at 3 L,
within 0.1% of AFW's saved 155.0854 Hz result.

### `sd_from_diameter(diameter_mm) -> float`

Convenience helper returning piston area in `cm^2`.

### Built-in driver presets

`DRIVER_PRESETS` contains named `DriverTS` sets for quick UI setup.

Current presets:

- `KEF B110B article example`
- `Beyma 12CMV2`
- `Beyma 12G40`
- `Beyma 12LX60V2`
- `Beyma 12BR70`
- `Beyma 12MC500`
- `Beyma 12MCS500`
- `Beyma 12WRS400`
- `Beyma 12P80Nd/V2`
- `Beyma 12P1000/Nd`
- `Beyma 12LEX1000Fe`
- `Beyma 12LEX1300Nd`
- `Beyma 12CMV3`
- `Turbosound TS-12W350/8W`
- `Turbosound TS-15W300/8A`
- `Scan-Speak 30W/4558T00`
- `Scan-Speak 15W/4531G00`
- `Dayton Audio RSS315HO-4`
- `SB Audience BIANCO-12OB150-01`
- `LaVoce WSF122.02`
- `LaVoce WSF122.50`
- `Aiyima 4ohm 5w 40mm black`
- `Aiyima 6ohm 8w 56mm`
- `Aiyima 4ohm 20w 58mm`
- `Aiyima 4ohm 20w 1.75in`
- `Aiyima 4ohm 5w 40mm zinc`
- `Aiyima 4ohm 10w 40mm`
- `Aiyima 8ohm 15w 3in flat`
- `Aiyima 8ohm 4w 1in for harman`
- `Aiyima 4ohm 12w 2in`
- `Aiyima 8ohm 3w 40mm`
- `Aiyima 4ohm 3w 1in`
- `Aiyima 4ohm 3w 36mm`
- `Aiyima 4ohm 10w 53mm`
- `Aiyima 10ohm 10w 50mm`
- `Aiyima 4ohm 10w 53mm LY1124-2`
- `Aiyima 4ohm 2w 33mm`
- `Aiyima 8ohm 1w 25mm altavoz portatil`
- `Aiyima 8ohm 3w 30mm altavoz portatil`
- `Aiyima 4ohm 5w 1.5in`
- `MarkAudio CHR-70`

`driver_preset_names()` returns the names in display order.
`get_driver_preset(name)` returns the matching `DriverTS` or raises
`ValueError`.
`driver_preset_info(name)` returns source, brand, model, nominal size, optional
price/currency and URL metadata used by the UI filters.  Prices are volatile:
the loader first uses the optional `data/driver_prices.json` enrichment file
and then falls back to any price embedded in the preset dataset.  Enriched
retailer records are checked against their matched product fields before they
enter the UI, so coherent low prices are allowed while accessory/part matches
(including kits, crossovers and grilles) are ignored. When enriched offers use
different currencies, the UI converts them to the selected display currency
with the latest available ECB daily reference rates before showing the
library, applying the maximum-price filter or calculating the price-aware
ranking. The UI shows the reference date; if the live feed is unavailable,
only prices already denominated in the selected currency remain comparable.

### Four external preset catalogs — kept separate, never merged

`src/presets.py` loads built-ins, then four independent optional catalogs, in
this order: Loudspeaker Database, manufacturer crawl, VituixCAD online
database, then the physically validated Speaker Box Lite tier. See
`docs/presets.md` for the loader contract:

- `data/loudspeaker_database_drivers.json` (`tools/import_loudspeaker_database.py`)
  — third-party aggregated data. **Not safe to redistribute in a public
  build.** Names get the `LSDB: ...` prefix.
- `data/manufacturer_drivers.json` (`tools/crawl_thiele_small.py` and
  `tools/crawl_driver_datasheets.py`) — extracted directly from manufacturer
  HTML/PDF/JSON-API sources. Safe to redistribute publicly. Names get the
  `WEB: ...` or `PDF: ...` prefix depending on extraction method.
- `data/vituixcad_drivers.json` (`tools/import_vituixcad_database.py`) —
  validated additions from VituixCAD's public online Enclosure-driver
  database. It remains a third-party aggregate in its own optional tier;
  names get the `VCD: ...` prefix.
- `data/speakerboxlite_drivers.json`
  (`tools/import_speakerboxlite_database.py`) — community records that pass
  LF bounds, the `Qts/Qes/Qms` identity, and unit-aware `Sd` validation
  against `Vas/Cms`; names get the `SBL: ...` prefix.

Each loader keeps the app usable if its file is missing or a single row is
invalid; bad rows are skipped during load. If multiple imported rows in the
same catalog share a display name, the later ones receive an `[LSDB id]` /
`[MFR id]` / `[VCD id]` / `[SBL id]` suffix so the UI does not silently drop
duplicate model variants. Aggregate importers remove normalized brand/model
matches already present in earlier tiers before generating their files.
External presets may also carry optional `price` and
`currency` fields; the separate local price-enrichment file supplies
retailer prices when the catalog itself has none. Without either source, the
max-price controls remain disabled. Generated presets also preserve a
`website_fields` block with the original card/page metadata and detected
commerce links.

The Finder exposes a compact provenance-category filter backed by
`driver_preset_provenance_category()`: Load Forge's built-ins, direct crawls,
official archives, retailer observations and user-supplied records share the
`Load Forge database` category, while LSDB, VituixCAD and Speaker Box Lite
remain independently selectable third-party databases. The candidate library
still shows both the compact category and the exact source string.

`tools/crawl_thiele_small.py` discovers manufacturer pages from seeds or XML
sitemaps, extracts HTML/JSON-LD/PDF measurements, normalizes units, derives
missing `Qms`, `Qts` or `Vas` when possible, and merges by brand/model without
overwriting populated values unless `--overwrite` is requested. These rows
carry `source="Manufacturer website"` (or `"Web crawler"` for the generic
default); exact URLs, confidence and raw measurements remain in
`website_fields`. See [crawl_thiele_small.md](crawl_thiele_small.md).

`tools/crawl_driver_datasheets.py` supplies the PDF-first document layer. It
follows external datasheet links, archives unique PDF bytes by SHA-256, records
provenance and observations in SQLite, and merges part-number/marketing-name
aliases only when stable T/S identity fields agree. Both tools default to
`data/manufacturer_drivers.json`; neither ever writes into the LSDB file. See
[crawl_driver_datasheets.md](crawl_driver_datasheets.md).

Retailer prices are generated separately by `tools/enrich_driver_prices.py`.
Supported providers are SoundImports (JSON-LD search/product/category pages),
Blue Aran (JSON-LD product sitemap), Madisound (CollectionPage JSON-LD category
pages with `?page=N` pagination) and Parts Express (public SuiteCommerce items
API driven by the product sitemap), selected with `--provider` plus
`--sitemap`.  The output file is
`data/driver_prices.json` and stores `price`, `currency`, seller URL,
availability, matched product fields, confidence and fetch timestamp per preset.
This keeps pricing refreshes independent from the acoustic T/S dataset.
For bulk refreshes, run the tool with `--soundimports-sitemap`; it reads the
public English sitemap, skips non-product paths, respects the site's
`Crawl-delay` through `--sleep`, stores every product offer in a SoundImports
catalog section, and links high-confidence matches back to driver preset names.
Use `--prune-prices` to revalidate an existing price file with the current
matcher and remove stale, low-confidence or invalid preset price matches; its
optional `--min-price` argument is off by default.
Use `--rematch-catalog` to relink the already cached retailer offers against
the complete runtime driver library. Add `--presets <catalog.json>` only to
restrict that operation to one catalog. The default includes built-ins, LSDB,
manufacturer, VituixCAD and Speaker Box Lite instead of silently targeting
LSDB alone, without issuing network requests. The rematcher uses exact
normalized brand/model identities and the
same confidence/accessory guards as live ingestion. Exact product URLs stored
by manufacturer/retailer imports are treated as strong identity evidence.
Known manufacturer brands must also appear in the retailer product identity;
a matching model code alone is insufficient because codes are not globally
unique across speaker brands.
Use `--refresh-preset-urls` to fetch offers only for currently unpriced
presets whose source URL belongs to a supported retailer. Parts Express URLs
use its public item API; other supported retailer pages use their JSON-LD.

The importer partitions requests by the site's brand filters, writes
`data/loudspeaker_database_checkpoint.json` after each completed brand, and
exits with code `75` on HTTP 429 or runtime-budget exhaustion after writing a
partial dataset.  A later run with the same `--checkpoint` resumes from the
completed brand list instead of restarting from zero.  The importer also keeps
`data/loudspeaker_database_brands.json` as a local brand-cache fallback; if a
brand URL returns a product page or any non-search response, that brand is
stored in the checkpoint's `deferred_brands` list and the run moves on without
adding those unrelated cards.
Use `--rebuild-from-checkpoint` to regenerate the output JSON from the local
checkpoint without new network requests.

For unattended retry windows, `tools/run_loudspeaker_database_import_until_complete.py`
wraps the importer in fresh Python processes.  Each window gets a new cookie
jar, then the runner sleeps between windows and grows the pause if the usable
preset count does not increase.

Imported LSDB fields are normalized to `DriverTS` as follows:

- direct: `fs -> fs_hz`, `qts -> qts`, `re -> re_ohm`, `sd -> sd_cm2`,
  `le -> le_mh`, `xmax -> xmax_mm`, `pmax -> pe_w`, `bl -> bl_tm`
- `mmd` is stored as `mms_g`
- `cms` is stored as `cms_mm_per_n` after converting from um/N to mm/N
- `qms` is derived from `2*pi*Fs*Mms/Rms`
- `vas_l` is derived from `Cms*rho*c^2*Sd^2`

The Beyma 12CMV2 preset is transcribed from the manufacturer sheet shown in the
working session:

- `Fs=49 Hz`
- `Re=6 ohm`
- `Qms=3.9`
- `Qts=0.47`
- `Vas=76 L`
- `Sd=0.053 m^2`
- `Cms=193 um/N`
- `Mms=54 g`
- `Bl=13.7 Tm`
- `Xmax=7 mm`
- `Le=1 mH`
- `Pe=320 W`

The preset uses the specified effective surface area `Sd`, not the nominal
300 mm frame diameter.

The additional Beyma 12" presets are transcribed from Beyma's official catalog
XLS (`/en/download-catalog-in-xls/`, downloaded 2026-07-07).  Catalog units are
converted for the simulator: `Sd` from m^2 to cm^2, moving mass from kg to g and
`Cms` from um/N to mm/N.

`LaVoce WSF122.02` and `LaVoce WSF122.50` are transcribed from technical-specification screenshots
provided in the working session.

`Turbosound TS-12W350/8W` is transcribed from the manufacturer specification
PDF linked by Gear4music in the working session: `Fs=61 Hz`, `Re=5.5 ohm`,
`Qms=11.37`, `Qes=0.45`, `Qts=0.43`, `Mms=67.78 g`, `Cms=0.1 mm/N`,
`Bl=17.9 Tm`, `Vas=19.26 L`, `Xmax=3.8 mm`, `Sd=551.55 cm^2`, `Le=1.6 mH`,
`Pe=350 W`.

`Turbosound TS-15W300/8A` is transcribed from the specification-sheet screenshot
provided in the working session: `Fs=46 Hz`, `Re=6.5 ohm`, `Qms=16.6`,
`Qes=0.49`, `Qts=0.47`, `Mms=96.4 g`, `Cms=0.12 mm/N`, `Bl=19.3 Tm`,
`Vas=130.2 L`, `Xmax=4.9 mm`, `Sd=865.7 cm^2`, `Le=1.2 mH`, `Pe=300 W`.

`Scan-Speak 30W/4558T00` is transcribed from Scan-Speak's official Discovery
datasheet, updated 2022-12-07: `Fs=17 Hz`, `Re=2.6 ohm`, `Qms=5.01`,
`Qes=0.34`, `Qts=0.32`, `Mms=135 g`, `Cms=0.65 mm/N`, `Bl=10.5 Tm`,
`Vas=197 L`, `Xmax=12.5 mm`, `Sd=466 cm^2`, `Le=0.83 mH`, `Pe=150 W`.

`Scan-Speak 15W/4531G00` is transcribed from the Scan-Speak Revelator datasheet
provided as a local PDF in the working session, updated 2013-01-30: `Fs=40 Hz`,
`Re=3.4 ohm`, `Qms=4.60`, `Qes=0.34`, `Qts=0.32`, `Mms=13 g`,
`Cms=1.25 mm/N`, `Bl=5.7 Tm`, `Vas=15.8 L`, `Xmax=6.5 mm`, `Sd=95 cm^2`,
`Le=0.25 mH`, `Pe=60 W`.

`Dayton Audio RSS315HO-4` is transcribed from Dayton Audio's official product
page/specification sheet: `Fs=26.2 Hz`, `Re=3.2 ohm`, `Qms=3.63`, `Qes=0.33`,
`Qts=0.31`, `Mms=251 g`, `Cms=0.15 mm/N`, `Bl=20 Tm`, `Vas=53.7 L`,
`Xmax=12.3 mm`, `Sd=514.7 cm^2`, `Le=1.75 mH`, `Pe=700 W`.

`SB Audience BIANCO-12OB150-01` is transcribed from the specification screenshot
provided in the working session: `Fs=44 Hz`, `Re=7.2 ohm`, `Qms=6.39`,
`Qes=0.69`, `Qts=0.63`, `Mms=52.4 g`, `Cms=0.25 mm/N`, `Bl=12.2 Tm`,
`Vas=103.8 L`, `Xmax=6.79 mm`, `Sd=539.1 cm^2`, `Le=1.18 mH`, `Pe=150 W`.

The Aiyima mini-driver presets are imported from the supplied workbook
`/Users/marcoderossi/Downloads/driver data.xlsx`.  Only complete rows with
`Fs`, `Re`, `Qms`, `Qts`, `Mms`, `Cms`, `Vas`, `BxL`, piston area and power
rating are included.  Workbook `Apiston mm2` values are converted to simulator
`Sd` in `cm^2`; the workbook does not provide reliable `Le` or `Xmax`, so those
fields use the simulator default of `0`.

`MarkAudio CHR-70` is transcribed from the Markaudio parameter screenshot
provided in the working session: `Fs=65.4 Hz`, `Re=7.2 ohm`, `Sd=50.2 cm^2`,
`Vas=5.17 L`, `Cms=1.44 mm/N`, `Mms=4.10 g`, `Bl=4.20 Tm`, `Qms=2.66`,
`Qes=0.69`, `Qts=0.55`, `Le=0.03244 mH`, `SPL=85.4 dB`, `Pe=20 W`,
`Xmax=4.3 mm`.

### `complete_driver(ts) -> DerivedDriver`

Converts the T/S set to SI/mechanical/acoustic-domain values.  Raises
`ValueError` on non-positive inputs or `Qms <= Qts`, because `Qes` could not be
derived.

### `suggest_alignment(ts) -> DccavAlignment`

First-pass empirical DCCAV alignment from the article:

```text
Vh = 2.05 * Qts^2 * Vas
Vl = 4.13 * Qts^2 * Vas
fh = 1.22 * Fs,mounted / Qts
fl = 0.466 * Fs,mounted / Qts
f3 = 0.83 * fl
```

With panel loading disabled, the KEF B110-like example in the article (`Fs=48.14`, `Qts=0.362`,
`Vas=11.52`) this yields approximately `Vh=3.1 L`, `Vl=6.2 L`,
`fh=162 Hz`, `fl=62 Hz`.

### `suggest_reflex_alignment(ts) -> ReflexAlignment`

Returns a conservative normal bass-reflex starting point:

```text
Vb = Vas
Fb = Fs,mounted
```

This is intentionally plain; it is meant as an editable starting point rather
than a named classic alignment.

### `suggest_bandpass4_alignment(ts, target_qbp=0.707) -> Bandpass4Alignment`

Returns a symmetrical fourth-order starter with sealed rear volume
`Vs = Vas / ((Qbp/Qts)^2 - 1)` when feasible (otherwise `4*Vas`), ported
front volume `Vp = 2*Qbp^2*Vas`, and front tuning
`Fp = Fs,mounted*Qbp/Qts`.
`Bandpass4Box` adds independent absorption/leakage factors for both chambers
and `Qport` for the front vent.

### `suggest_sealed_alignment(ts, target_qtc=0.707) -> SealedAlignment`

Returns the classical closed-box volume for the requested `Qtc` when
`target_qtc > Qts`, together with achieved `Fc` and `Qtc`.  When a passive box
cannot reduce `Qtc` below the driver's `Qts`, the starter uses `Vb=4*Vas` as a
finite approximation to an infinite enclosure.  Starter volume is clamped to
the UI/optimizer minimum of 0.05 L.

### `sealed_system_metrics(ts, box) -> tuple[float, float]`

Returns `(Fc, Qtc)` for a `SealedBox` using the classical `Vas/Vb` relations,
with mounted Fs when panel loading is enabled.

### `optimize_alignment(ts, goals, load_type="DCCAV", box_template=None, voltage_v=2.83, max_evaluations=260, fixed_total_volume_l=None) -> OptimizedAlignment`

Goal-driven box optimizer used by the UI's `Optimized` box strategy.
It runs a bounded compass pattern search in log-space, starting from the
empirical article alignment (DCCAV: `Vh`, `Vl`, `fl`, `fh/fl`), bandpass
starter (`Vs`, `Vp`, `Fp`), reflex starting point (`Vb`, `Fb`) or classical
sealed alignment (`Vb`).  Loss factors are
copied from `box_template` when one is provided, otherwise defaults are used.
Accepted `load_type` values are `"DCCAV"`, `"Bandpass 4th order"`,
`"Bass reflex"` and `"Sealed"`;
the legacy labels `"Acoustic suspension"` and `"Suspension pneumatic"` are
canonicalized to `"Sealed"` for backward compatibility with old `.lfp` files
and callers.
Infinite baffle is intentionally rejected because it has no box parameter.
The optional `fixed_total_volume_l` argument constrains every candidate to an
exact `Vh+Vl`, `Vs+Vp` or `Vb` for callers that explicitly need an equality
constraint. The `Bass Match` workspace does not use it: Finder passes its
**Maximum volume** through `OptimizationGoals.max_total_volume_l`, allowing
each driver to retain a better, smaller alignment.

`OptimizationGoals` fields:

- `objective`: `"extension"` (lowest F3), `"balanced"` or `"flat"` — weight
  presets that trade simulated F3 against passband ripple
- `max_total_volume_l`: hard cap on `Vh+Vl` (or `Vb`); every search candidate
  is projected onto the feasible volume boundary.  The minimum usable cap is
  0.10 L for DCCAV/bandpass (two 0.05 L chambers) and 0.05 L for reflex/sealed
- `target_f3_hz`: pushing extension below the target earns nothing, and once
  the target is met a stronger size regularizer prefers the compact box
- `max_ripple_db`: allowed peak-to-valley SPL spread in the passband window
  `[1.2*F3, min(fmax, max(200, 2*F3))]`; excess is penalized
- `max_excursion_ratio`: cap on max excursion vs `Xmax` at the simulation
  voltage, evaluated for `f >= F10` (only when `Xmax` is known; `0`/`None`
  disables)
- `max_group_delay_ms`: cap on the maximum total-output group delay in the
  passband (`None` disables)

The score also re-applies the `response_sanity_warnings()` credibility limits.
With `Max extension` and no explicit target F3, F3 is dominant: ripple,
excursion and group-delay excesses remain advisory but are scaled to 1%, and
the size regularizer drops to 0.002. Physical port and response-credibility
boundaries remain hard. Setting a target F3 restores normal constraint
weighting and prefers the smallest box that reaches the target.
`F3 >= 0.67*fl` is the hard DCCAV feasibility boundary for balanced/flat
alignments. The explicit `Max extension` objective permits `F3 >= 0.65*fl`
to reach the deeper AFW-like alignment, while
`F3 >= 0.5*sealed Fc` remains penalized, so the optimizer cannot chase
loss-free fake extension. The DCCAV `fh/fl` ratio is bounded to `[1.2, 4.5]`
so the load keeps its double-resonator character. Ported candidates also derive
the zero-length Helmholtz diameter and the diameter required by the 5%-of-c air
speed guideline for every active vent; candidates requiring more than 95% of
`OPTIMIZER_MAX_PORT_DIAMETER_CM` (60 cm) are infeasible. A search that finds no
feasible candidate raises `ValueError` rather than returning an invalid box.

For bandpass, ripple/group delay stop at 90% of the upper -3 dB edge and the
score rejects a missing edge or passband narrower than 1.4:1.

`OptimizedAlignment` returns the winning `DccavBox`/`Bandpass4Box`/
`ReflexBox`/`SealedBox` plus achieved
`f3_hz`, `f10_hz`, `ripple_db`, `excursion_ratio`, `group_delay_ms`,
`total_volume_l`, the final score and the evaluation count.

### `group_delay_ms(result) -> np.ndarray`

Total-output group delay in milliseconds, computed as `-dφ/dω` from the
complex sum of `driver_volume_velocity` and `port_volume_velocity`.  The UI
plots it in the Group Delay tab and exports it in the response CSV as the
`group_delay_ms` column.

### `response_phase_deg(result) -> np.ndarray`

Total acoustic-output phase in degrees, wrapped to ±180.  The far-field
pressure is proportional to `jw * (Ud + Up)`, so the phase includes the
+90 degree radiation term on top of the volume-velocity phase.

### `export_frd_text(result) -> str` / `export_zma_text(result) -> str`

Text exports in the de-facto standard formats read by VituixCAD, XSim and
REW.  Both start with two `*` comment lines followed by tab-separated data
rows (`%.4f`), skipping rows with non-finite values:

- FRD: `frequency_hz`, `spl_total_db`, `response_phase_deg`
- ZMA: `frequency_hz`, `impedance_ohm`, `impedance_phase_deg` (zero phase
  when the result predates the `impedance_phase_deg` field)

The UI offers both next to the response CSV as `Download FRD (response)` and
`Download ZMA (impedance)`.

### `monte_carlo_response_band(ts, load_type="DCCAV", box=None, freq_hz=None, voltage_v=2.83, series_r_ohm=0.0, tolerance=0.15, runs=120, seed=20260714, percentiles=(5.0, 95.0)) -> ToleranceBand`

Monte Carlo estimate of driver manufacturing spread.  Each run multiplies
Fs, Vas, Qts and Qms by independent uniform factors in
`[1 - tolerance, 1 + tolerance]`; measured Mms/Cms/Bl overrides are dropped
so the perturbed set stays self-consistent and Qts is capped just below the
perturbed Qms.  The enclosure is kept fixed ("same box, driver unit
spread").  Runs that fail validation are skipped; fewer than `runs/4` valid
runs raise `ValueError`.  Returns `ToleranceBand(frequency_hz, lower_db,
upper_db, runs)` with the requested percentiles (default 5-95) of the total
SPL.  The seed is fixed so bands are reproducible; `tolerance=0` collapses
the band onto the nominal response.  The UI exposes it as the `Tolerance
band` toggle in the Response tab (cached per parameter set, shaded area
under the traces, disabled while comparing loads).

### `design_space_box(ts, load_type, x, y, box_template=None) -> DccavBox | Bandpass4Box | ReflexBox | SealedBox`

Builds the box for one point of the atlas plane.  `x`/`y` follow the atlas
axes: reflex `Vb`/`Fb`, sealed `Vb` (y ignored), bandpass total `Vs+Vp`/`Fp`,
or DCCAV total volume/`fl`. Two-chamber splits come from their starters.
Loss factors are copied from a matching-type `box_template`.  Shared by the
grid sweep and by the UI's click-to-apply so an applied point reproduces its
cell exactly.

### `design_space_map(ts, load_type="Bass reflex", box_template=None, resolution=15, voltage_v=2.83) -> DesignSpaceMap`

Sweeps the box plane and reports achievable `F3`/ripple per grid point via
the optimizer metrics.  Log-spaced axes around the empirical starter:
reflex `Vb` (0.3-3x starter) vs `Fb` (0.55-1.6x), DCCAV total volume vs
`fl`, bandpass total volume vs `Fp` (same spans), sealed a 1-D `Vb` sweep
(0.2-4x Vas, `y_values` collapsed
to one row).  Like the optimizer, evaluation is at `voltage_v` with zero
series resistance; invalid grid cells stay `NaN`; infinite baffle and
`resolution < 3` raise `ValueError`.  The UI exposes it as the `Atlas` tab:
computation is gated behind a `Compute atlas` toggle, cached per driver,
losses and voltage, colored by F3 or ripple, and clicking a cell offers
`Apply selected box` (switches the design to Manual strategy).

### `rank_preset_row(name, load_type, max_volume_l, voltage_v, f_min_hz, f_max_hz, points, goals=None) -> dict | None` / `sort_ranked_rows(rows)` / `response_sparkline(spl)`

Candidate-ranking primitives (implemented in `src/ranking.py`) used by the
`Bass Match` workspace. `rank_preset_row` simulates one preset at its
best alignment no larger than the maximum volume (goal mode passes a cap,
not an exact-volume constraint) and returns the table row or `None`;
`sort_ranked_rows` orders by deepest
F3/F6/F10 with the loudest peak as tie-breaker; `response_sparkline`
downsamples the total response to a peak-relative 48-point sparkline
clipped at `SPARKLINE_FLOOR_DB`.  The UI runs the quick scan serially
(cached) and fans optimizer scans of more than 8 candidates out to a
`ProcessPoolExecutor` with a real progress bar; both paths produce
identical rows because the optimizer is deterministic.

### `price_extension_score(f3_hz, price) -> float`

Lower-is-better value score for the price-aware `Bass Match` ranking:
`F3 * price` rewards candidates that are simultaneously cheap and deep.
Missing or non-positive F3/price returns `inf`, so unpriced candidates sink
below every priced one.  The UI applies it per currency — the sidebar price
currency when present among the ranked rows, otherwise the most common
currency — and re-sorts the already-simulated scan without re-running it;
the sidebar max-price filter acts as the budget constraint.

### `driver_reference_metrics(ts) -> DriverReferenceMetrics`

Classical small-signal reference metrics from the T/S set:

- `eta0 = 4*pi^2 * Fs^3 * Vas / (c^3 * Qes)` — half-space reference
  efficiency as a fraction
- `spl_1w_db` — SPL at 1 W / 1 m, derived from `eta0` with the module's
  `RHO_AIR`/`SPEED_OF_SOUND`/`P_REF` constants (~112.1 dB offset)
- `spl_2v83_db` — the same rescaled to 2.83 V across `Re`
- `ebp_hz = Fs / Qes` — efficiency bandwidth product; the UI shows the
  classical reading (< 50 sealed/infinite baffle, > 100 ported, in between
  either) as a caption under the derived-driver metrics

### `classify_driver_bandwidth(ts) -> DriverBandwidthClass`

Heuristic screening of the usable driver bandwidth, answering "pure subwoofer
or woofer that can reach the mids?" from the T/S set alone.  Indicators and
weights:

- voice-coil corner `f_Le = Re / (2*pi*Le)`: `< 400 Hz` counts 2 sub points,
  `> 800 Hz` counts 2 midbass points; unknown `Le` skips this indicator
- `Fs <= 35 Hz` sub / `Fs >= 45 Hz` midbass (1 point)
- moving-mass surface density `Mms/Sd >= 0.30 g/cm^2` sub / `<= 0.15` midbass
  (1 point)
- reference sensitivity `SPL(1 W) <= 90 dB` sub / `>= 94 dB` midbass (1 point)

A two-point margin yields `Subwoofer` or `Midbass-capable`; otherwise the
class is the neutral `Woofer`.  `DRIVER_CLASSES` lists the three values.  The
returned `DriverBandwidthClass` carries `driver_class`, `f_le_hz` (or `None`),
`mass_density_g_cm2`, `spl_1w_db` and the human-readable `reasons` tuple shown
by the UI caption.  Cone breakup and directivity are not in the T/S set, so
this is a catalog-screening aid, not a substitute for the manufacturer's
measured response.  The UI uses it for the main-workspace `Class` preset filter, the
`VC corner`/`Class` metrics and the `Bass Match` result column.

### `apply_driver_configuration(ts, configuration) -> DriverTS`

Composite T/S set for identical drivers sharing one enclosure, selected from
`DRIVER_CONFIGURATIONS`: single driver; 2–8-driver parallel/series arrays;
mixed `S × P` arrays up to eight drivers; and isobaric arrays up to 16 total
drivers. Fs, Qts and Qms are invariant for identical drivers; the composite
scales the rest:

- ordinary arrays: Sd, Vas, Pe and radiating-piston count scale with physical
  driver count; all-series, all-parallel or mixed wiring determines Re and Le
- isobaric arrays: every physical pair contributes one radiating piston,
  `0.5 × Vas`, `1 × Sd` and `2 × Pe`; wiring determines Re and Le

Measured Mms/Cms/Bl overrides are dropped so the composite is re-derived
self-consistently. Per-cone air loading therefore leaves mounted Fs invariant
for separate identical cones. The UI applies the sidebar `Driver configuration`
selector inside `_driver_from_state()`, so alignments, the optimizer,
metrics and plots all see the composite. `Bass Match` ranks every candidate
with its selected configuration and preserves that configuration when the
candidate is applied to Box Design.

### `port_air_velocity_ms(result, port_area_cm2, port="lower") -> np.ndarray`

Linear port air speed `|U|/S` in m/s for the requested port: `"lower"` (also
the reflex vent) uses `port_l_velocity`, `"upper"` uses `port_h_velocity`; any
other name raises `ValueError`.  `PORT_VELOCITY_GUIDELINE_MS` (5% of the speed
of sound, ~17 m/s) is the module-level chuffing guideline: speeds above it
commonly produce audible port noise and compression that the lumped model does
not simulate.  The UI shows per-port peaks in the Port Geometry table and
appends a chuffing warning when the peak exceeds the guideline.

### `port_length_cm(volume_l, fb_hz, port_diameter_cm, end_correction=1.43) -> float`

Physical tube length in cm of a circular port, from the Helmholtz relation
`L_eff = c^2 * S / (w^2 * V)` minus the end correction
`end_correction * radius`.  The default 1.43 models one flanged (k=0.82) plus one free
end (k=0.61); the UI uses 1.64 (k=0.82+0.82) for the DCCAV upper port, which
joins two chambers with two flanged ends.  A non-positive result means the
opening's end corrections alone exceed the required acoustic mass — the
diameter is too small for the volume/tuning pair — and the UI reports it as a
warning that quotes `port_max_tuning_hz()` and `port_min_diameter_cm()`
instead of a usable length.

### `port_max_tuning_hz(volume_l, port_diameter_cm, end_correction=1.43) -> float`

The tuning ceiling of a zero-length opening: with no duct at all, the port's
acoustic mass is just the end corrections, so this is the highest `fb` the
diameter can reach on the given volume.

### `port_min_diameter_cm(volume_l, fb_hz, end_correction=1.43) -> float`

The smallest circular-port diameter that can reach `fb_hz` on the given
volume, i.e. the diameter at which `port_length_cm()` crosses zero.  Both
helpers are exact inverses of `port_length_cm()` at the zero-length boundary.

### `port_volume_fraction(volume_l, fb_hz, diameter_cm, end_correction=1.43) -> float`

Fraction of the chamber volume occupied by the Helmholtz duct itself (the
cylinder `port_length_cm()` requires for the tuning).  Classic reflex practice
keeps it at or below `PORT_MAX_VOLUME_FRACTION` (10%): beyond that the duct
displaces the chamber it tunes and the lumped model stops being reliable.
Returns 0.0 when the diameter cannot reach the tuning at all (that case is
flagged by the zero-length warning instead).  Both `port_length_cm()` and this
function grow monotonically with diameter above `port_min_diameter_cm()`,
which is what makes `port_diameter_for_load()`'s bisections well-defined.

### `port_velocity_diameter_cm(peak_volume_velocity_m3s, margin=1.05) -> float`

Minimum port diameter keeping peak volume velocity within
`PORT_VELOCITY_GUIDELINE_MS`, with a 5% safety margin.  Shared by the
optimizer's feasibility metric and the UI's applied port sizing so both floor
the same port at the same diameter — before this helper existed, the two call
sites computed the velocity floor slightly differently (only the UI applied
the margin), which was enough on its own to make the optimizer approve a
diameter the UI would then round up past the duct-volume cap.

### `rated_velocity_diameter_cm(ts, result, sim_voltage_v, volume_velocity) -> float`

Velocity floor at the driver's excursion limit instead of the simulation
voltage.  When the simulation runs at a low voltage (e.g. 2.83 V) a powerful
driver barely moves, making the raw ``port_velocity_diameter_cm`` floor
negligible.  This helper scales the peak port volume velocity to the
excursion-limited drive level (``Xmax / max_excursion``) so the port is sized
for real-world usage.  Falls back to ``port_velocity_diameter_cm`` when the
simulation voltage is below 2.83 V or when ``Xmax`` is unpublished.

### `port_diameter_for_load(volume_l, fb_hz, end_correction, floor_cm, max_diameter_cm=OPTIMIZER_MAX_PORT_DIAMETER_CM, target_length_cm=5.0, grid_cm=0.5) -> float | None`

The single sizer behind every automatic vent, used identically by
`_optimizer_metrics` (optimizer feasibility scoring) and the UI's
`_optimized_port_diameter_cm` (the diameter actually applied) — this is a
deliberate consolidation: a "practical ~5 cm duct" preference and a "duct
≤10% of the chamber" cap pull in opposite directions once a chamber is small
(growing diameter to reach 5 cm can just as easily blow past 10%, since both
grow together), so having two independent implementations of that trade-off
is how a box could look feasible to the optimizer and still round, in the
UI, to an oversized duct. `floor_cm` bundles every mandatory minimum (zero-
length boundary, `port_displacement_min_diameter_cm`,
`port_velocity_diameter_cm`) and is never violated; above it, diameter grows
toward `target_length_cm` but stops at the `PORT_MAX_VOLUME_FRACTION`
boundary even if the resulting duct stays short. The result is snapped to
`grid_cm` (the sidebar's 0.5 cm control step), rounding *down* whenever that
still clears the floor — rounding up is what silently re-broke the cap when
the raw optimum sat exactly on it. Returns `None` when `floor_cm` itself
(after grid rounding) already exceeds the cap: no diameter satisfies every
directive for this volume/tuning pair, so the box itself needs to change, not
the port. Callers reporting a "None" case for scoring purposes must recompute
the fraction at the *grid-rounded* floor, not the raw one, or the reported
value looks compliant while the diameter that would actually be built is not.

`_optimizer_metrics`'s `required_port_diameter_cm`/`port_volume_fraction`
call this sizer per port and reject a candidate (score tier `1e5+`) when
`required_port_diameter_cm` exceeds the construction ceiling — deliberately
*not* by collapsing an unsatisfiable port straight to an infinite diameter:
that flattened the pattern search's score gradient across the entire
infeasible region (every candidate scored identically `inf`), stalling
`optimize_alignment` into a false "no buildable box" even when a compliant
box existed just outside the search's starting neighborhood. The
floor's own (smoothly-varying) `port_volume_fraction` is what actually drives
rejection and gradient in that region.

### `port_pipe_resonance_hz(length_cm) -> float`

First half-wave (organ-pipe) resonance of the duct, `c / (2 L)` on the
physical length.  The UI warns when it falls below
`PORT_PIPE_RESONANCE_GUARD` (4×) times the port tuning, i.e. when the duct's
own standing wave lands inside the vented passband.  Non-positive lengths
raise `ValueError`.

### `port_max_straight_length_cm(volume_l) -> float`

Rough ceiling for a straight duct inside a box of `volume_l`, treating the
enclosure as a cube (`side_cm = (volume_l*1000)**(1/3)`; real external
dimensions aren't modeled).  A duct can pass `port_volume_fraction()`'s 10%
cap while still being far longer than the box can plausibly hold in a
straight run — a thin, deeply-tuned vent moves little air per length, so its
volume stays low even as length grows unboundedly (found via a 5.5 cm ×
47.5 cm reflex vent in a 40 L box occupying only 2.8% of the chamber).
`_optimizer_metrics`'s `port_length_over_box_ratio` (length at the sized
diameter, divided by this ceiling) is a second, independent rejection tier in
`_score_alignment`, and the UI warns whenever an active vent's length exceeds
it, recommending an L-shaped/slot fold (not modeled here), a bigger box, or a
higher tuning.  Non-positive `volume_l` raises `ValueError`.

### `port_displacement_min_diameter_cm(ts, fb_hz) -> float`

Drive-independent minimum vent diameter from the port-area gold standard
``S >= K * (2*pi*Fb*Sd*Xmax) / v_amm`` where ``K = PORT_K_FACTOR`` (default
1.0, ideal simplified estimate) and ``v_amm = PORT_VELOCITY_GUIDELINE_MS``
(5% of the speed of sound, ~17 m/s).  Unlike the 5%-of-c
air-speed check this floor is drive-independent: it sizes the vent for the
driver's rated displacement even when the simulated voltage is low.  Returns
`0.0` when the driver has no published `Xmax`; non-positive `fb_hz` raises
`ValueError`.  It enters the optimizer's `required_port_diameter_cm`
feasibility metric for every ported load, floors the automatic vent sizing in
the UI, and drives a Port Geometry warning when an active vent is smaller
than the rule for the composite driver.

### `simulate(ts, box, freq_hz=None, voltage_v=2.83, series_r_ohm=0.0) -> SimulationResult`

Solves the two-node acoustic circuit across the frequency array.  The source
pressure is approximated as `Eg*Bl/(Re*Sd)` and drives the network through
`Zas`.

All four simulators accept an optional `series_r_ohm` (amplifier output,
cable and crossover-coil DCR in series with the driver; negative values raise
`ValueError`).  It enters the model in three places: the drive pressure uses
`Re+Rs`, the electrical damping term becomes `Bl^2/(Re+Rs)` (raising the
effective Qes/Qts of the system), and `impedance_ohm` reports the load seen
from the source terminals, i.e. it includes `Rs`.  The goal optimizer and the
`Bass Match` ranking always evaluate at `series_r_ohm=0`. The symmetric 2x2
nodal system is solved in closed form (vectorized over frequency), which keeps
the optimizer's repeated simulations fast.

Returned arrays:

- `spl_total_db`: exposed cone front plus lower port, summed as complex volume
  velocities before conversion to dB
- `spl_driver_db`: exposed cone front radiation alone
- `spl_port_db`: lower port radiation alone
- `excursion_mm`
- `impedance_ohm`
- `impedance_phase_deg`: electrical impedance phase in degrees (used by the
  ZMA export; `None` on results built before the field existed)
- `mil_w`: maximum input power by frequency, limited by `Xmax` and/or `Pe`
  when those driver fields are available
- `mol_db`: maximum output level estimate, produced by scaling `spl_total_db`
  up to the `MIL` limit
- `port_h_velocity`
- `port_l_velocity`
- complex `driver_volume_velocity` for the exposed cone front and
  `port_volume_velocity` for the lower port

`MIL` is computed from the linear excursion result at the requested simulation
voltage.  Limit voltages are at the source terminals: the excursion-limited
RMS voltage is `voltage * Xmax / excursion`; the thermal RMS voltage is
approximated as `sqrt(Pe * Re) * (Re+Rs)/Re`.  The lower available voltage
limit is converted to watts as the share reaching the driver's `Re` through
the resistive divider (`V^2 / Re` when `Rs=0`) for display and CSV export.  `MOL` uses the same voltage ratio to scale SPL.  Both curves require a
published thermal rating: when `Pe` is `0` or missing there is no credible
thermal ceiling to bound the drive limit, so the excursion-only scaling would
claim a near-infinite output where the cone barely moves.  Drivers without a
thermal rating therefore return `MIL` and `MOL` as `NaN` and the UI keeps the
trace buttons visible but renders no curve, instead of plotting an
excursion-only `MIL` with no counterpart `MOL`.  If neither `Xmax` nor `Pe` is
known, `MIL` and
`MOL` are likewise returned as `NaN` and the UI reports them as unavailable.

The SPL values are useful for comparing alignments inside this simulator.  They
represent a low-frequency acoustic-load estimate.  They are not a calibrated
far-field model and do not include cone breakup, baffle step, horn/waveguide
directivity, or electrical crossover behaviour.

The electrical impedance should show the expected multi-resonance DCCAV shape;
the built-in Beyma alignment regression checks for three local impedance crests.

### `simulate_reflex(ts, box, freq_hz=None, voltage_v=2.83, series_r_ohm=0.0) -> SimulationResult`

Solves the conventional one-box reflex acoustic circuit across the frequency
array.  The returned `SimulationResult` uses the same fields as DCCAV:
`spl_total_db` is exposed cone front plus vent, `spl_port_db` is the vent alone,
`port_l_velocity` is the vent volume velocity and `port_h_velocity` is zero.

### `simulate_bandpass4(ts, box, freq_hz=None, voltage_v=2.83, series_r_ohm=0.0) -> SimulationResult`

Solves the enclosed driver against the summed sealed-rear and vented-front
acoustic loads. Total SPL/phase/group delay come from the front vent alone;
cone excursion and electrical impedance include both chamber loads.

### `simulate_sealed(ts, box, freq_hz=None, voltage_v=2.83, series_r_ohm=0.0) -> SimulationResult`

Solves the driver against one closed acoustic compliance.  Total and cone SPL
are identical because there is no external port; all port velocity fields are
zero.  Electrical impedance includes the closed-box acoustic load and normally
shows one resonance peak near the achieved `Fc`.

### `simulate_infinite_baffle(ts, freq_hz=None, voltage_v=2.83, series_r_ohm=0.0) -> SimulationResult`

Solves driver motion while assuming perfect front/rear isolation.
Total and cone SPL are identical, all port fields are zero, and electrical
impedance normally shows one resonance peak near mounted Fs (or free-air Fs
when panel loading is disabled).

### `response_metrics(result) -> dict`

Returns compact UI metrics: peak SPL, estimated `F3`, maximum excursion and
minimum impedance.  `F3` is taken from the low-frequency crossing returned by
`response_threshold_frequencies()`.

### `impedance_peak_frequencies(result, min_ratio_to_minimum=1.2) -> list[float]`

Returns local electrical-impedance peak frequencies above a threshold relative
to the minimum impedance.  The UI uses this to display `Z peaks`; a normal
bass-reflex simulation should show two impedance peaks within the simulated
frequency range.

### `equivalent_sealed_fc_hz(ts, box) -> float`

Returns the closed-box resonance frequency for a `SealedBox`, `ReflexBox`
volume, total bandpass volume `Vs+Vp` or DCCAV volume `Vh+Vl`. For non-sealed
loads this remains a
sanity comparison rather than their simulated resonance.

### `alignment_diagnostics(ts, box) -> list[str]`

Returns practical warnings for empirical alignments, including low-`Qts`
extrapolation and very small 12-inch boxes where port displacement, compression
and target SPL can dominate the small-signal formula.

### `response_sanity_warnings(ts, box, thresholds) -> list[str]`

Returns warnings when the computed low-frequency crossings contradict the box
tuning constraints.  For example, an `F3` far below the lower tuning `fl` or far
below the equivalent sealed `Fc` is flagged instead of being treated as a
credible design result.

### `bandpass4_diagnostics(ts, box, result=None) -> list[str]`

Flags a front tuning far outside `0.5*Fs..4*Fs` and, when a result is supplied,
a missing upper -3 dB edge that requires a wider simulation range.

### `response_threshold_frequencies(result, drops_db=(3, 6, 10)) -> dict`

Returns low-frequency response crossing frequencies relative to the maximum
total SPL in the reference band, currently 40-200 Hz.  The crossing search uses
the first rising low-frequency crossing so a later dip/notch inside the pass
band cannot move F3/F6/F10 to an upper-frequency recovery point.  The UI uses
this for the automatic F3/F6/F10 cursors and metrics.

If no true rising crossing exists in the simulated range, the returned value is
`NaN`; the UI displays `n/a` rather than inventing the nearest frequency.

## Tests

`tests/test_all.py` contains acoustic-load coverage for:

- article alignment regression
- built-in driver presets, including Beyma 12CMV2
- T/S derivation from diameter/Sd
- finite response arrays and sane metric signs
- three local impedance crests for the DCCAV load
- two local impedance crests for the bass-reflex load
- fourth-order bandpass starter/simulation, two-chamber optimizer and exact
  fixed-volume Finder row, plus UI selection/persistence controls
- one local impedance crest plus zero port output for sealed and infinite-baffle loads
- F3/F6/F10 threshold ordering for cursor placement
- no fabricated F3 when a true threshold crossing is absent
- response sanity warnings for impossible F3 values
- input validation for invalid `Qms <= Qts`
- optimizer volume-cap, target-F3 compactness and extension-vs-empirical checks
  for DCCAV plus reflex/sealed volume-cap checks
- UI `Max extension` / `Balanced` / `Flattest` / `Manual` box strategies
  applying and locking the expected controls, and legacy `Suggested`/
  `Optimized` strategy names normalizing onto them
- independent `Bass Match` workspace routing for sealed and infinite-baffle
  loads, including practical defaults, candidate preview and explicit
  application
- finite non-zero group delay, its CSV export column and the UI Group Delay
  tab
- port length Helmholtz round-trip, impossible tiny-diameter flagging, air
  speed area scaling and the UI small-vent chuffing warning, including the
  quoted tuning ceiling and minimum feasible diameter
- displacement minimum-area golden rule: exact hand-computed diameter,
  tuning monotonicity, missing-Xmax and invalid-tuning handling, the floor in
  the applied vent sizing and optimizer feasibility metric at low drive, and
  the UI warning below/at the rule
- duct-volume directive: exact cylinder fraction, optimizer rejection above
  10% with a feasible box elsewhere, pipe-resonance helper value and the UI
  warnings for an oversized duct and an in-band pipe resonance
- shared port sizer `port_diameter_for_load`: length-target and cap-bound
  branches, 0.5 cm grid rounding that never re-breaks the cap, `None` on an
  infeasible floor
- optimizer feasibility and UI applied port sizing agree on the duct-volume
  cap across a volume/tuning sweep (regression for a mismatch that let a
  compliant-looking box round up, in the UI, past 10%)
- reflex optimizer reaches a buildable box across a range of volume caps
  when the empirical starting point sits in an infeasible neighborhood
  (regression for a flat infinite-score plateau that stalled the search, and
  for local search stalling even with a smooth score - fixed by the
  deterministic diagonal restarts in `optimize_alignment`)
- port-length-vs-box directive: exact cube-root ceiling, a compliant duct
  fraction that still exceeds it, optimizer rejection and a real optimized
  box steering clear of it, the UI warning appearing/disappearing with tuning
- reference efficiency/sensitivity/EBP formulas and their UI `Driver details`
  panel with the EBP topology hint
- series-resistance effects: impedance shift at the source terminals, reduced
  drive, damping change, driver-side thermal cap and the advanced UI `Series R`
  input
- bandwidth classifier: known subwoofer/midbass presets, voice-coil corner
  value, unknown-Le fallback and the UI class filter
- FRD/ZMA exports: column round-trip against the simulated arrays, wrapped
  phase ranges, impedance phase on all four loads, zero-phase fallback for
  legacy results and the UI download buttons
- price-aware value ranking: score ordering and missing-input handling,
  currency-consistent re-sort with unpriced candidates at the bottom and the
  UI `Rank by` control on ranked results
- Monte Carlo tolerance band: nominal response inside the band, deterministic
  seed, zero-tolerance collapse, width growing with tolerance, sealed and
  infinite-baffle smoke and the UI `Tolerance band` toggle
- driver configurations: exact parallel/series/isobaric T/S scaling,
  invariant Fs/Q, dropped measured overrides, classical ±3 dB efficiency
  shifts and the UI selector re-aligning the suggested box
- design-space atlas: grid shapes and axis ranges, cell/`design_space_box`
  round-trip, deeper-than-starter minimum F3, sealed 1-D monotonic sweep,
  infinite-baffle/resolution rejection and the UI Atlas tab with gated
  computation and pending click-to-apply
- module split: the `dccav` facade re-exports the same objects as
  `engine`/`presets`/`pricing`/`ranking` (including the cached loaders the
  price tests clear) and the engine imports neither catalog nor pricing
- parallel ranking: worker rows for junk names degrade to `None`, the
  process-pool optimizer path returns rows identical to the serial one, and
  process/semaphore denial automatically falls back to the safe serial path

Cloud Run Finder optimization uses 24 evaluations per candidate and caps the
response grid at 80 points; local runs retain the original profile.
