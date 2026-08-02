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

Commercial name, brand, MPN, price, currency, product link and availability
are editable. `Save` persists only rows whose visible editable values changed;
unchanged rows retain their original source provenance.

`Select` is an independent checkbox for every row and permits any number of
simultaneous selections. `Duplicate selected` creates one uniquely named copy
for each selected row. `Delete selected` removes all selected rows. Both
actions require at least one selection, persist atomically to the selected JSON
catalog and clear the selection on the refreshed table.

Deletion is intentionally explicit and separate from selection: checking a row
never deletes it by itself.

## Backup and restore

`Download backup` exports the complete selected catalog, including rows hidden
by the current search. `Restore backup` accepts only a JSON object containing a
`presets` list or `prices` mapping, replaces the complete selected catalog and
clears the runtime price cache.

The maintenance surface writes repository-local JSON in desktop mode. A
production Cloud Run filesystem is ephemeral, so durable production catalog
updates must still be promoted through the catalog release/storage workflow;
an in-container edit is not a persistent catalog deployment.
