# `tools/import_speakerboxlite_database.py`

Imports low-frequency driver records from Speaker Box Lite's public JSON API
into the separate optional catalog `data/speakerboxlite_drivers.json`.

Speaker Box Lite is a third-party, community-edited aggregate. The importer
therefore never merges its rows into the manufacturer catalog and does not
trust upstream units blindly. Review upstream terms before redistributing the
generated catalog publicly.

## Validation

A row is accepted only when it has usable `Fs`, `Vas`, `Qts`, `Qms`, `Qes`,
`Re`, and `Sd` and all values remain inside LF-driver bounds. It also requires:

- `Qms > Qts` and `Qes > Qts`;
- `Qes*Qms/(Qes+Qms)` to agree with `Qts` within 5%;
- the ambiguous upstream `Sd` to resolve as mm², cm², or m² to a plausible
  area for the nominal frame diameter;
- when `Cms` is available, resolved `Sd` to agree within 25% with the
  independent acoustic-compliance identity
  `Vas = rho*c²*Cms*Sd²`.

The source value, chosen unit, independently derived `Sd`, Q-identity error,
upstream ID/check/rating, URL, and import timestamp remain in
`website_fields`. Optional `Le`, `Xmax`, RMS power, `Mms`, `Cms`, and `BL` are
kept only when bounded.

## Usage

```bash
.venv/bin/python tools/import_speakerboxlite_database.py
.venv/bin/python tools/import_speakerboxlite_database.py \
  --input /tmp/speakerboxlite.json --dry-run
```

By default the importer deduplicates normalized brand/model identities against
the manufacturer, Loudspeaker Database, and VituixCAD tiers, then atomically
writes the generated JSON. `--existing PATH` may be repeated to override that
list.
