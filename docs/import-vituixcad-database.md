# VituixCAD online driver database import

`tools/import_vituixcad_database.py` imports the public tab-delimited online
driver database used by VituixCAD's Enclosure tool:

`https://kimmosaunisto.net/Software/VituixCAD/VituixCAD_Drivers.txt`

The result is written to `data/vituixcad_drivers.json` as a third optional
runtime tier. It is deliberately kept separate from both manufacturer-original
records and the Loudspeaker Database import. The source is a public online
database, but its rows are third-party aggregated data; review upstream terms
before including the generated file in a public redistribution.

The importer requires the six Load Forge simulation inputs (`Fs`, `Vas`,
`Qts`, `Qms`, `Re`, `Sd`), enforces physical ranges and `Qms > Qts`, derives
`Qes` from `Qts+Qms` when needed, and retains published `Qes`, `Le`, `Xmax`,
`Pmax`, `Mms`, `Cms` and `BL`. Tweeters and passive radiators are excluded
because this catalog tier feeds low-frequency acoustic-load simulation.

Before writing, normalized brand/model identities are compared with
`data/manufacturer_drivers.json` and `data/loudspeaker_database_drivers.json`.
Known aliases such as Eighteen Sound/18Sound, B&C, PHL, JBL Professional,
PURIFI and AE Speakers/Acoustic Elegance are canonicalized so the generated
tier contains additions rather than obvious duplicates.

Online refresh:

```bash
.venv/bin/python tools/import_vituixcad_database.py
```

Qualification from a previously downloaded file:

```bash
.venv/bin/python tools/import_vituixcad_database.py \
  --input /tmp/VituixCAD_Drivers.txt --dry-run
```

Writes are atomic. The output records source URL, import timestamp, driver
type, active/vintage status, source revision and upstream update attribution.
