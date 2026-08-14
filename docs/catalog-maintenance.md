# Catalog Maintenance

`ui_app.py` exposes an administrator-only maintenance workspace at
`?maintenance=1`. Local desktop mode treats localhost access as the
administrator boundary. SaaS mode requires the authenticated email configured
by `LOAD_FORGE_ADMIN_EMAIL`, or the exact user ID configured by
`LOAD_FORGE_ADMIN_UID`.

The catalog selector opens one of the four source-specific unified catalogs:

- `data/catalog_proprietario.json`
- `data/catalog_lsdb.json`
- `data/catalog_vituixcad.json`
- `data/catalog_speakerboxlite.json`

The editor renders every record that matches the current search; it has no
1,000-row display cap. Search narrows the editable table without changing the
underlying catalog.

## Editing and selection

Manufacturer, normalized part number, `Xmax` in mm, `Pmax` in W, `Le` in mH,
price, currency, product link and availability are editable. The three driver
values map to `driver.xmax_mm`, `driver.pe_w` and `driver.le_mh`; saving them
preserves every other T/S field. Source-decorated catalog names remain stored
as hidden internal keys instead of being repeated in the table. Retailer and
manufacturer titles are normalized through the same runtime identity parser,
including Beyma labels such as `LOUDSPEAKER 8\"MC300Nd 8 OH` → `8MC300Nd`.
When no reliable manufacturer code exists, the complete model title remains
visible instead of being reduced to a generic category such as `WOOFER`.
Known source aliases are shown under one manufacturer name; for example,
`Eminence Speaker` is presented as `Eminence`, and the repeated manufacturer
prefix is removed from its part number.
Published mounting dimensions, weight, nominal impedance, sensitivity,
voice-coil diameter, `Xmech` and nominal diameter appear as read-only columns.
Nominal and physical overall diameter are separate: a published 12-inch class
does not imply a 304.8 mm frame. Blank cells mean
the source did not publish a verified value; Maintenance never fills them from
nominal size, `Sd`, brand averages or other estimates.

Three coverage metrics distinguish records with any verified mechanical field,
records with the essential four (`overall`, `cutout`, `depth`, `weight`) and
records with all eight tracked mechanical fields. A field-by-field count is
shown underneath, so partial enrichment is never presented as completeness.
`Save` persists only rows whose visible editable values changed; unchanged rows
retain their original source provenance. A saved part-number correction is an
explicit override of the imported `model`, so the edited value remains visible
after reruns and is also used by runtime identity and deduplication.
The unified-catalog rebuild preserves rows marked `Manual catalog maintenance`
and explicit `part_number_override` values, including edited optional driver
fields and commercial fields, so an automatic enrichment cycle cannot erase
administrator corrections.

`Select` is an independent checkbox for every row and permits any number of
simultaneous selections. `Duplicate selected` creates one uniquely named copy
for each selected row. `Delete selected` removes all selected rows. Both
actions require at least one selection, persist atomically to the selected JSON
catalog and clear the selection on the refreshed table.

Deletion is intentionally explicit and separate from selection: checking a row
never deletes it by itself.

## Box Design admin update

When an authenticated administrator opens an external catalog preset in Box
Design, the Driver panel shows `Save T/S to catalog`. It remains available
after editing the T/S values (which normally marks the design as Custom), writes
those values back to the original source catalog, and reloads the driver
library. The control is absent for built-in presets and for non-admin users. As
with the maintenance workspace, a Cloud Run container's local catalog change is
ephemeral until it is promoted through the catalog release workflow.

## Backup and restore

`Download backup` exports the complete selected catalog, including rows hidden
by the current search. `Restore backup` accepts only a JSON object containing a
`presets` list or `prices` mapping, replaces the complete selected catalog and
clears the runtime price cache.

The maintenance surface writes repository-local JSON in desktop mode. A
production Cloud Run filesystem is ephemeral, so durable production catalog
updates must still be promoted through the catalog release/storage workflow;
an in-container edit is not a persistent catalog deployment.
