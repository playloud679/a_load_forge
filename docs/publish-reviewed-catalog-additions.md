# Reviewed append-only catalog additions

`tools/publish_reviewed_catalog_additions.py` promotes only crawler records
whose product URLs were explicitly reviewed. It is intended for small,
high-confidence catalog batches after a staging crawl.

The command validates the required T/S fields, official-manufacturer source
label and minimum extraction confidence. It rejects duplicate names,
brand/model identities and the tolerant runtime identities used by the app.
One official URL may back several genuine MPN/impedance variants when the
manufacturer publishes a shared matrix page. Existing rows are hashed before publication and the
same hashes must remain at the start of the resulting catalog; the operation
therefore appends records without enriching, replacing or deleting the
pre-existing catalog.

Runtime deduplication follows the loader's exact sequence: manufacturer alias,
model override, conservative part-number extraction, impedance normalization
and T/S-backed identity. This prevents a decorated retailer title from passing
review only to replace or disappear behind an already loaded driver.

Use `--dry-run` first, repeat `--accept-url` for every approved product, then
run without `--dry-run` and execute `make test-catalog`.

The latest approved batch is summarized in
`data/catalog_additions_latest_report.json`; the application shows it in the
sidebar crawl-report expander, separately from staging and retailer discovery.
The report can aggregate a review cycle while `latest_batch_added` identifies
the most recent publication inside that cycle. Large batches use
`latest_batch_by_brand`, `added_names_count` and `added_names_sample` so the UI
shows exact totals and provenance without rendering hundreds of product names.
When raw publication and loader growth differ, `latest_batch_visible_added`
and `latest_batch_visible_by_brand` report the measured Bass Match delta
separately from append-only rows.
`latest_batch_existing_aliases_collapsed` records pre-existing display
duplicates removed by a newly verified manufacturer alias; it changes no raw
catalog row and is included in the net app-visible delta.

Structured official catalog APIs use the same staging format. The SICA/Jensen
importer is one example: official product-category evidence keeps both brands
separate while publication still applies the shared exact runtime identity gate
and append-only invariant.

Manufacturer-published impedance variants remain distinct when their official
product IDs and T/S records differ. The FaitalPRO importer therefore stages
4/8/16-ohm variants separately, while the runtime identity gate still removes
retailer duplicates and already loaded variants before publication.

Current and archived manufacturer families may be staged together when the
source marks archive state explicitly. Ciare uses this path: archive rows remain
fully official engineering records, but incomplete legacy pages are rejected
instead of being filled from retailer claims.

External driver libraries are discovery radar only. The official-hunt radar
may use all of their brand/model/impedance identities to prioritize missing
manufacturer pages, but it never copies their T/S fields. A radar candidate
must be independently reconstructed from first-party evidence before it can
reach this publication gate.
