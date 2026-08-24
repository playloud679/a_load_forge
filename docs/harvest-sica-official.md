# SICA/Jensen official catalog harvester

`tools/harvest_sica_official.py` reads SICA Loudspeakers' public official
WooCommerce Store API. The API exposes the current SICA and Jensen products as
structured records, including their product categories and published acoustic
attributes.

Brand assignment does not rely on a shared site header: a row is identified as
SICA or Jensen only through its official `/sica/` or `/jensen/` product-category
link. Products are accepted only when the structured attributes provide a
complete valid T/S core (`Fs`, `Vas`, `Qts`, `Qms`, `Re`, `Sd`). This naturally
rejects horns, compression drivers and other products without a simulatable
low-frequency moving system.

The importer reads `X max` as the one-way value after the site's `+/-` marker,
uses AES power instead of continuous program power, converts `Cms` from µm/N
to mm/N, and uses LF-specific fields for coaxial products. It writes a staging
artifact and never edits the proprietary catalog directly:

```bash
.venv/bin/python tools/harvest_sica_official.py
```

The default output is `data/sica_official_checkpoint.json`. Publication remains
a separate reviewed append-only operation followed by `make test-catalog`.
