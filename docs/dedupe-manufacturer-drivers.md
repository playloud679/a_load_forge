# Manufacturer driver deduplication

`tools/dedupe_manufacturer_drivers.py` removes only conservative duplicates
from `data/manufacturer_drivers.json`.

Two rows must have the same normalized brand, be strong aliases of the same
model, and have exactly identical six required simulation parameters (`Fs`,
`Vas`, `Qts`, `Qms`, `Re`, `Sd`). A row is removed only when every non-zero
parameter it contains is present with the same value in a more complete or
equally complete row. Conflicting optional parameters keep both rows.
Different compact manufacturer model codes always remain separate, even when
every published T/S value happens to match. Explicitly different nominal
impedances (for example, 4 Ω and 8 Ω variants) also remain separate.

The retained row favors more measured parameters and then a compact canonical
model name. Removed model spellings and URLs are preserved in
`website_fields.aliases`, `additional_sources` and `merged_duplicates`.

Preview and write the audit report without changing the database:

```bash
.venv/bin/python tools/dedupe_manufacturer_drivers.py
```

Apply the deletion atomically:

```bash
.venv/bin/python tools/dedupe_manufacturer_drivers.py --apply
```

The complete decision log is written to
`data/manufacturer_driver_dedup_report.json`.

## Latest cleanup

The cleanup run on 2026-07-22 reduced the database from 4,697 to 4,424
presets. It removed 273 verified aliases: 154 had every non-zero driver
parameter identical and 119 were less-complete parameter subsets. A second
dry-run removed zero rows, confirming idempotence.
