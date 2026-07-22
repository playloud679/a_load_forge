# Manufacturer metadata enrichment

`tools/enrich_manufacturer_metadata.py` fills only values supported by a
physical identity or a verified retailer offer. It never guesses `Le`, `Xmax`
or power handling.

The deterministic T/S completion uses:

- `Qes = Qts*Qms/(Qms-Qts)`;
- `Cms = Vas/(rho*c^2*Sd^2)` with the same air constants as the simulator;
- `Mms = 1/((2*pi*Fs)^2*Cms)`;
- `BL = sqrt(2*pi*Fs*Mms*Re/Qes)`.

Published non-zero values always win. Every generated field is listed under
`website_fields.derived_fields` and its formula is retained in
`website_fields.derivations`.

Missing `size_in` first uses an explicitly labelled inch dimension in the
model/title (including mixed fractions), then falls back to the nearest
conventional frame-size class from `Sd`. For example, an effective piston area
near 530 cm² maps to 12 in. The fallback is stored explicitly as an estimate
with confidence, not as a published dimension. `Sd` itself is never changed.
Generated mechanical values must also remain inside the crawler's physical
bounds; inconsistent source inputs are flagged by remaining unfilled instead
of propagating an implausible unit conversion.

Prices are synchronized from `data/driver_prices.json` only when the cached
retailer product passes the same brand/model/accessory confidence checks used
by the live price crawler. The snapshot keeps currency, availability, seller,
URL, fetch time and matched product identity. Rows without a defensible offer
receive `price_status=no_confident_retailer_match`; no average or invented
price is substituted.

Preview:

```bash
.venv/bin/python tools/enrich_manufacturer_metadata.py
```

Apply atomically:

```bash
.venv/bin/python tools/enrich_manufacturer_metadata.py --apply
```

The audit is written to
`data/manufacturer_metadata_enrichment_report.json`.

## Latest run

The 2026-07-22 run enriched 4,424 manufacturer presets. It derived 4,321
`Qes`, 2,654 `Cms`, 176 `Mms`, 701 `BL` and 2,157 nominal-size values. Final
coverage is 100% for `Qes` and `size_in`, 99.98% for `Cms`/`BL`, and 99.93%
for `Mms`. Three small-driver/source-unit conflicts remain unfilled rather
than forcing implausible mechanical values.

Cached-catalog rematching plus a live refresh of 97 retailer URLs attached
verified price snapshots to 2,860 presets (64.6%). The other 1,564 rows carry
an explicit no-confident-match status. A missing price is not replaced with a
brand average because model, impedance, region and availability materially
change real purchase prices.
