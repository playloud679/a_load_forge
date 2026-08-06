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

`size_in` is reconciled even when an earlier crawler supplied a value. Complete
mixed fractions such as `6-1/2"` are parsed as 6.5 in (never as the denominator
`2"`), and model-number guesses are accepted only when the effective diameter
represented by `Sd` is physically compatible. Otherwise the nearest
conventional frame-size class is estimated from `Sd`; for example, an
effective piston area near 530 cm² maps to 12 in. Every replacement retains the
old value, reason and confidence under
`website_fields.field_corrections`/`derivations`.

`Sd` is corrected only with traceable evidence:

- a rechecked manufacturer page/datasheet;
- reparsing the stored raw value with its unit and decimal/thousands separator;
- restoring a missing power of ten when the result is independently
  corroborated by `Fs`, published `Vas`, published `Mms` and the nominal frame
  size.

The audit compares nominal frame diameter with the circular effective-piston
diameter `sqrt(4*Sd/pi)`. These are deliberately not treated as equal: the
effective piston is normally smaller. A 70–115% effective/nominal diameter
window matches the crawler and keeps tolerance for differing suspensions without
accepting model-family numbers as inches. The Markaudio Alpair 10P is a
verified example: the manufacturer specifies a 5 in cone and 88.25 cm² `Sd`,
so the model's `10P` token must not become a 10 in size. Round-driver records that remain
physically incompatible are marked
`quality_status=rejected_size_sd_conflict` and excluded by the runtime catalog;
compound rectangular dimensions are not subjected to the circular check.
The verified-correction table also records explicit Markaudio archive values
that need unit-aware normalization (for example µH → mH and µM/N → mm/N),
including published `Mms` and nominal power for Alpair 6P/6.2, 7.3, 10P,
10.3 and 12PW, plus the archive Pluvia 7 inductance. Each correction retains
the official Markaudio URL in `website_fields.field_provenance`.
Generated mechanical values must also remain inside the crawler's physical
bounds; inconsistent source inputs are flagged by remaining unfilled instead
of propagating an implausible unit conversion.

Prices are synchronized from `data/driver_prices.json` only when the cached
retailer product passes the same brand/model/accessory confidence checks used
by the live price crawler. The snapshot keeps currency, availability, seller,
URL, fetch time and matched product identity. Rows without a defensible offer
receive `price_status=no_confident_retailer_match`; no average or invented
price is substituted. An explicit administrator `part_number_override` is the
model identity used for rematching. If a previously synchronized offer no
longer passes the current identity checks, its value and provenance move to
`website_fields.invalidated_price` and the active commercial fields are
cleared; manually curated prices without crawler provenance are not removed.

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

The current applied run and its exact correction/coverage counts are stored in
`data/manufacturer_metadata_enrichment_report.json` and summarized in
`docs/manufacturer-database-status.md`. A missing price is not replaced with a
brand average because model, impedance, region and availability materially
change real purchase prices.
